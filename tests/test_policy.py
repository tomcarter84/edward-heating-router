import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from ha_stubs import policy as p

NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
def evidence(age=0, mode='auto', power='25', demand='on'):
    stamp = NOW - timedelta(seconds=age)
    return p.HeatingEvidence(p.Reading(mode, stamp), p.Reading(power, stamp),
        p.Reading(demand, stamp), p.Reading('20.4', NOW), p.Reading('22', stamp))

class PolicyTests(unittest.TestCase):
    def answer(self, e):
        return p.answer_heating_status(e, now=NOW)
    def test_seventeen_allowlisted_phrases(self):
        expected = {
            'is the heating on', 'is the heating on right now',
            'is the heating on or off', 'is the heating on or off right now',
            'is the downstairs heating on or off', 'is the downstairs heating actually on',
            'is the heating currently running or off', 'is the heating actively calling for heat now',
            'is the heating actually running', 'is the heating running',
            'is the boiler firing', 'is the boiler firing right now',
            'what is the current heating status', 'what is the heating status', 'heating',
            'how does the tado heating look', 'is the heating calling for heat',
        }
        self.assertEqual(p.STATUS_QUESTIONS, expected)
        self.assertEqual(len(expected), 17)
        for text in p.STATUS_QUESTIONS:
            with self.subTest(text=text):
                self.assertIsNotNone(p.respond_to_status_only(text, evidence(), now=NOW))
                self.assertTrue(p.is_status_question('  Edward, '+text.upper()+'?!  '))
    def test_commands_and_near_matches_do_not_match(self):
        for text in [None, 42, '', 'turn the heating on', 'turn the heating off',
            'set heating to 22', 'is the heating on and turn it off', 'heating off',
            'is the heating on; turn it off', 'is the heating on 2', 'héating',
            'is the heating on\nturn it off']:
            with self.subTest(text=text):
                self.assertIsNone(p.respond_to_status_only(text, evidence(), now=NOW))
    def test_boundary_600_seconds_is_recent(self):
        self.assertEqual(self.answer(evidence(600)).confidence, 'recent')
    def test_boundary_601_seconds_unverified(self):
        self.assertEqual(self.answer(evidence(601)).confidence, 'unverified')
    def test_each_required_timestamp_invalid_or_old(self):
        for name in ['mode', 'power_percent', 'demand']:
            for stamp in [None, '2026-11-03', NOW.replace(tzinfo=None), NOW+timedelta(seconds=1), NOW-timedelta(days=1)]:
                with self.subTest(name=name, stamp=stamp):
                    e = evidence()
                    e = replace(e, **{name: replace(getattr(e, name), reported_at=stamp)})
                    self.assertEqual(self.answer(e).confidence, 'unverified')
    def test_all_contradictory_combinations(self):
        for mode, power, demand in [('auto', 20, 'off'), ('heat', 0, 'on'),
                                     ('off', 20, 'on'), ('off', 20, 'off'), ('off', 0, 'on')]:
            with self.subTest(mode=mode, power=power, demand=demand):
                self.assertEqual(self.answer(evidence(mode=mode, power=power, demand=demand)).confidence, 'conflicting')
    def test_partial_fresh_conflict_still_reported(self):
        e = evidence(mode='off', power=20, demand='on')
        e = replace(e, demand=p.Reading(None, None))
        self.assertEqual(self.answer(e).confidence, 'conflicting')
    def test_stale_disagreement_not_current_conflict(self):
        self.assertEqual(self.answer(evidence(601, mode='off', power=20)).confidence, 'unverified')
    def test_invalid_power(self):
        for value in [None, True, False, 'unavailable', 'unknown', 'bad', float('nan'), float('inf'), '-inf', -1, 101]:
            with self.subTest(value=value):
                self.assertEqual(self.answer(evidence(power=value)).confidence, 'unverified')
    def test_invalid_mode_demand(self):
        for name in ['mode', 'demand']:
            for value in ['unavailable', 'unknown', None, 'bad']:
                with self.subTest(name=name, value=value):
                    self.assertEqual(self.answer(evidence(**{name:value})).confidence, 'unverified')
    def test_fresh_matter_does_not_freshen_tado(self):
        answer = self.answer(evidence(86400))
        self.assertEqual(answer.confidence, 'unverified')
        self.assertIn('20.4 degrees', answer.text)
        self.assertNotIn('Its target', answer.text)
    def test_valid_off_heat_auto(self):
        for mode in ['off', 'heat', 'auto']:
            a = self.answer(evidence(mode=mode, power=0, demand='off'))
            self.assertEqual(a.confidence, 'recent')
            self.assertIn('did not request heat', a.text)
    def test_fractional_request_not_rounded_to_zero(self):
        self.assertIn('0.01 percent', self.answer(evidence(power=.01)).text)
    def test_boiler_never_verified(self):
        for e in [evidence(), evidence(601), evidence(mode='off')]:
            a = self.answer(e)
            self.assertFalse(a.heating_now_verified)
            self.assertIn('actual boiler flame is not independently monitored', a.text)
    def test_temperature_invalid_stale_and_future(self):
        for value, stamp in [('nan', NOW), ('inf', NOW), (True, NOW), ('unavailable', NOW), (20,NOW-timedelta(seconds=601)), (20,NOW+timedelta(seconds=1)), (20,None)]:
            a = self.answer(replace(evidence(), hallway_temp_c=p.Reading(value,stamp)))
            self.assertIn('current hallway temperature is not verified', a.text)
            self.assertEqual(a.confidence, 'recent')
    def test_target_requires_valid_fresh_reading(self):
        for value, stamp in [('nan',NOW), (None,NOW), (20,None), (20,NOW-timedelta(seconds=601))]:
            self.assertNotIn('Its target', self.answer(replace(evidence(), target_c=p.Reading(value,stamp))).text)
    def test_now_must_be_aware(self):
        with self.assertRaises(ValueError):
            p.answer_heating_status(evidence(), now=NOW.replace(tzinfo=None))
