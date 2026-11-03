import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from ha_stubs import router_module as r, const as c, models, conversation

SOURCES = {
    c.CONF_CLIMATE: 'climate.test_zone',
    c.CONF_POWER: 'sensor.test_power',
    c.CONF_DEMAND: 'binary_sensor.test_demand',
    c.CONF_TEMPERATURE: 'sensor.test_temperature',
}
CLIMATE, POWER, DEMAND, TEMPERATURE = (SOURCES[key] for key in
    (c.CONF_CLIMATE, c.CONF_POWER, c.CONF_DEMAND, c.CONF_TEMPERATURE))

def entry(entry_id):
    return SimpleNamespace(entry_id=entry_id, data=dict(SOURCES))

class States:
    def __init__(self, values):
        self.values, self.reads = values, []
    def get(self, name):
        self.reads.append(name)
        return self.values.get(name)

class EntityFallback(conversation.ConversationEntity):
    supported_features = conversation.ConversationEntityFeature.CONTROL
    def __init__(self, hass, callback=None):
        self.hass, self.callback, self.calls, self.seen = hass, callback, 0, []
    async def async_process(self, user_input):
        self.calls += 1
        self.seen.append((user_input, user_input.agent_id, user_input.conversation_id))
        if self.callback:
            return await self.callback(user_input)
        return await super().async_process(user_input)
    async def _async_handle_message(self, user_input, chat_log):
        return models.ConversationResult(response=object(), conversation_id=chat_log.conversation_id, continue_conversation=False)

class LegacyFallback:
    def __init__(self, result=None, fail=False):
        self.result, self.fail, self.calls, self.seen = result, fail, 0, None
    async def async_process(self, user_input):
        self.calls += 1
        self.seen = (user_input, user_input.agent_id)
        if self.fail:
            raise RuntimeError('provider may already have executed a tool')
        return self.result

class RouterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        now = datetime.now(timezone.utc)
        def state(value, attrs=None):
            return SimpleNamespace(state=value, attributes=attrs or {}, last_reported=now,
                last_updated=now-timedelta(days=2), last_changed=now-timedelta(days=2))
        self.hass = SimpleNamespace(states=States({CLIMATE:state('auto', {'temperature':22}),
            POWER:state('25'), DEMAND:state('on'), TEMPERATURE:state('20.4')}),
            agents={}, logs={}, session_calls=[], counter=0,
            services=SimpleNamespace(async_call=Mock(side_effect=AssertionError('No service calls allowed'))))
        self.router = r.EdwardHeatingRouter(entry('test-entry'))
        self.router.hass, self.router.entity_id = self.hass, 'conversation.edward_heating_router'
    def input(self, text='turn the hallway light on', cid=None):
        return models.ConversationInput(text=text, context=object(), conversation_id=cid,
            device_id='device-id', satellite_id='satellite-id', language='en',
            agent_id=self.router.entity_id, extra_system_prompt='keep me unchanged')
    def fallback(self, callback=None):
        agent = EntityFallback(self.hass, callback)
        self.hass.agents[c.FALLBACK_AGENT] = agent
        return agent
    async def test_all_status_questions_local_without_fallback_or_services(self):
        with patch.object(r, 'async_get_agent', side_effect=AssertionError('No LLM lookup')):
            for phrase in r.is_status_question.__globals__['STATUS_QUESTIONS']:
                result = await self.router.async_process(self.input(phrase))
                self.assertIsNone(result.response.error)
                self.assertTrue(result.continue_conversation)
                self.assertIn('actual boiler flame is not independently monitored', result.response.speech)
                self.assertTrue(result.response.speech.endswith('Anything else I can help with?'))
        self.hass.services.async_call.assert_not_called()
        self.assertEqual(set(self.hass.states.reads), {CLIMATE,POWER,DEMAND,TEMPERATURE})
        self.assertEqual(len(self.hass.logs),17)
        for log in self.hass.logs.values():
            self.assertEqual(len(log.content),2)
            self.assertIsNone(log.content[-1].tool_calls)
            self.assertEqual(log.content[-1].agent_id,self.router.entity_id)
    async def test_last_reported_is_used_not_last_changed(self):
        result = await self.router.async_process(self.input('heating'))
        self.assertIn('recently requested heat',result.response.speech)
    async def test_fresh_matter_and_updated_cannot_freshen_old_reports(self):
        for key in [CLIMATE,POWER,DEMAND]:
            state = self.hass.states.values[key]
            state.last_reported = datetime.now(timezone.utc)-timedelta(days=1)
            state.last_updated = datetime.now(timezone.utc)
        result = await self.router.async_process(self.input('heating'))
        self.assertIn('cannot verify whether Tado',result.response.speech)
        self.assertIn('20.4 degrees', result.response.speech)
    async def test_missing_entities_safe(self):
        self.hass.states.values.clear()
        result = await self.router.async_process(self.input('heating'))
        self.assertIsNone(result.response.error)
        self.assertIn('cannot verify',result.response.speech)
    async def test_local_existing_conversation_reused(self):
        result = await self.router.async_process(self.input('heating','existing-id'))
        self.assertEqual(result.conversation_id,'existing-id')
        self.assertEqual(self.hass.counter,0)
        self.assertEqual(self.hass.session_calls,['existing-id'])
    async def test_original_input_identity_and_every_field_preserved(self):
        inp = self.input(cid='existing-id')
        before = {name:getattr(inp,name) for name in inp.__slots__}
        expected = models.ConversationResult(object(),'provider-result',True)
        async def check(received):
            self.assertIs(received,inp)
            for name,value in before.items():
                self.assertIs(getattr(received,name),value if name!='agent_id' else c.FALLBACK_AGENT)
            return expected
        agent = self.fallback(check)
        result = await self.router.async_process(inp)
        self.assertIs(result,expected)
        self.assertIs(agent.context_seen,inp.context)
        self.assertEqual(agent.state_writes,1)
        self.assertEqual(agent.calls,1)
        self.assertEqual(self.hass.session_calls,[])
        self.assertEqual(self.hass.states.reads,[])
        for name,value in before.items():
            self.assertIs(getattr(inp,name),value)
    async def test_fallback_new_session_created_only_once(self):
        agent = self.fallback()
        inp = self.input()
        result = await self.router.async_process(inp)
        self.assertEqual(self.hass.session_calls,[None])
        self.assertEqual(agent.seen[0][2],None)
        self.assertEqual(result.conversation_id,'generated-1')
        self.assertFalse(result.continue_conversation)
        self.assertIsNone(inp.conversation_id)
    async def test_fallback_existing_session_and_followup(self):
        agent = self.fallback()
        first = await self.router.async_process(self.input('heating'))
        second = await self.router.async_process(self.input('turn the light off',first.conversation_id))
        self.assertEqual(second.conversation_id,first.conversation_id)
        self.assertEqual(agent.calls,1)
        self.assertEqual(self.hass.counter,1)
    async def test_legacy_agent_passthrough(self):
        expected = models.ConversationResult(object(),'legacy',True)
        agent = LegacyFallback(expected)
        self.hass.agents[c.FALLBACK_AGENT] = agent
        inp = self.input()
        result = await self.router.async_process(inp)
        self.assertIs(result,expected)
        self.assertIs(agent.seen[0],inp)
        self.assertEqual(agent.seen[1],c.FALLBACK_AGENT)
        self.assertEqual(inp.agent_id,self.router.entity_id)
        self.assertEqual(self.hass.session_calls,[])
    async def test_fallback_exception_restores_input_no_retry(self):
        async def fail(inp):
            raise RuntimeError('provider failed after a possible tool execution')
        agent = self.fallback(fail)
        inp = self.input(cid='retain-on-error')
        with self.assertLogs(r.__name__,level='ERROR'):
            result = await self.router.async_process(inp)
        self.assertEqual(agent.calls,1)
        self.assertEqual(inp.agent_id,self.router.entity_id)
        self.assertEqual(result.conversation_id,'retain-on-error')
        self.assertFalse(result.continue_conversation)
        self.assertIsNotNone(result.response.error)
        self.assertFalse(r._ROUTING.get())
    async def test_legacy_exception_restores_input_no_retry(self):
        agent = LegacyFallback(fail=True)
        self.hass.agents[c.FALLBACK_AGENT] = agent
        inp = self.input()
        with self.assertLogs(r.__name__,level='ERROR'):
            result = await self.router.async_process(inp)
        self.assertEqual(agent.calls,1)
        self.assertEqual(inp.agent_id,self.router.entity_id)
        self.assertIsNotNone(result.response.error)
    async def test_missing_self_and_router_fallback_rejected(self):
        for agent in [None,self.router,r.EdwardHeatingRouter(entry('other'))]:
            self.hass.agents[c.FALLBACK_AGENT] = agent
            result = await self.router.async_process(self.input(cid='existing'))
            self.assertIsNotNone(result.response.error)
            self.assertEqual(result.conversation_id,'existing')
            self.assertEqual(self.router.supported_features,0)
            self.assertEqual(self.hass.session_calls,[])
    async def test_indirect_recursion_rejected_and_guard_reset(self):
        async def recurse(inp):
            return await self.router.async_process(inp)
        agent = self.fallback(recurse)
        result = await self.router.async_process(self.input())
        self.assertEqual(agent.calls,1)
        self.assertIsNotNone(result.response.error)
        self.assertFalse(r._ROUTING.get())
        local = await self.router.async_process(self.input('heating'))
        self.assertIsNone(local.response.error)
    async def test_feature_and_streaming_contract(self):
        self.fallback()
        self.assertEqual(self.router.supported_features,conversation.ConversationEntityFeature.CONTROL)
        self.assertTrue(self.router.supports_streaming)
        self.assertEqual(self.router.supported_languages,'*')
    async def test_setup_adds_exactly_one_entity(self):
        add = Mock()
        await r.async_setup_entry(self.hass,entry('setup'),add)
        self.assertEqual(add.call_count,1)
        self.assertIsInstance(add.call_args.args[0][0],r.EdwardHeatingRouter)

    async def test_configured_sources_only_even_after_arbitrary_renaming(self):
        configured = {key: entity_id.split('.')[0]+'.alternative_fixture'
                      for key, entity_id in SOURCES.items()}
        # Two sensor sources must remain distinct.
        configured[c.CONF_TEMPERATURE] = 'sensor.alternative_temperature'
        original_states = dict(self.hass.states.values)
        self.hass.states.values = {configured[key]: original_states[old_id]
                                  for key, old_id in SOURCES.items()}
        router = r.EdwardHeatingRouter(SimpleNamespace(entry_id='alternate', data=configured))
        router.hass, router.entity_id = self.hass, self.router.entity_id
        result = await router.async_process(self.input('heating'))
        self.assertIsNone(result.response.error)
        self.assertIn('25 percent',result.response.speech)
        self.assertIn('20.4 degrees',result.response.speech)
        self.assertEqual(self.hass.states.reads, [configured[c.CONF_CLIMATE],
            configured[c.CONF_POWER], configured[c.CONF_DEMAND],
            configured[c.CONF_TEMPERATURE], configured[c.CONF_CLIMATE]])
        self.assertFalse(set(SOURCES.values()) & set(self.hass.states.reads))

    async def test_source_selection_copied_from_entry(self):
        configured_entry = entry('copied')
        router = r.EdwardHeatingRouter(configured_entry)
        configured_entry.data[c.CONF_POWER] = 'sensor.later_mutation'
        self.assertEqual(router._sources[c.CONF_POWER],POWER)
