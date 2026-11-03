"""Pure deterministic policy. No clients, services, tools or network access."""
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
import re

STATUS_QUESTIONS = frozenset({
    "is the heating on", "is the heating on right now",
    "is the heating on or off", "is the heating on or off right now",
    "is the downstairs heating on or off", "is the downstairs heating actually on",
    "is the heating currently running or off", "is the heating actively calling for heat now",
    "is the heating actually running", "is the heating running",
    "is the boiler firing", "is the boiler firing right now",
    "what is the current heating status", "what is the heating status", "heating",
    "how does the tado heating look", "is the heating calling for heat",
})

def normalize(text):
    if not isinstance(text, str):
        return ""
    # Only harmless speech punctuation is accepted. Do not erase arbitrary
    # syntax, accented words, numbers or command fragments to manufacture a match.
    text = " ".join(text.lower().strip().split())
    text = re.sub(r"^edward[, ]+", "", text)
    return text.rstrip("?!. ").strip()

def is_status_question(text):
    return normalize(text) in STATUS_QUESTIONS

@dataclass(frozen=True)
class Reading:
    value: object
    reported_at: object

@dataclass(frozen=True)
class HeatingEvidence:
    mode: Reading
    power_percent: Reading
    demand: Reading
    hallway_temp_c: Reading
    target_c: Reading

@dataclass(frozen=True)
class Answer:
    text: str
    confidence: str
    heating_now_verified: bool = False

def _seconds_old(reading, now):
    stamp = reading.reported_at
    if not isinstance(stamp, datetime) or stamp.tzinfo is None:
        return None
    try:
        if stamp.utcoffset() is None:
            return None
        age = (now - stamp).total_seconds()
    except (TypeError, ValueError, OverflowError):
        return None
    return age if isfinite(age) and age >= 0 else None

def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if isfinite(value) else None

def answer_heating_status(e, *, now=None):
    at = now or datetime.now(timezone.utc)
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    ages = [_seconds_old(r, at) for r in (e.mode, e.power_percent, e.demand)]
    mode, power, demand = e.mode.value, _number(e.power_percent.value), e.demand.value
    valid = mode in ("auto", "heat", "off") and power is not None and 0 <= power <= 100 and demand in ("on", "off")
    fresh = valid and all(age is not None and age <= 600 for age in ages)
    recent_mode = ages[0] is not None and ages[0] <= 600 and mode in ("auto", "heat", "off")
    recent_power = ages[1] is not None and ages[1] <= 600 and power is not None and 0 <= power <= 100
    recent_demand = ages[2] is not None and ages[2] <= 600 and demand in ("on", "off")
    conflict = (recent_power and recent_demand and (power > 0) != (demand == "on")) or (recent_mode and mode == "off" and ((recent_power and power > 0) or (recent_demand and demand == "on")))
    if conflict:
        text, confidence = "The recent thermostat readings disagree, so I cannot verify current heat demand.", "conflicting"
    elif fresh:
        state = "requested heat" if power > 0 else "did not request heat"
        # A fractional percentage must not round positive demand to zero.
        text = f"Tado recently {state}, with a {power:g} percent heat request."
        confidence = "recent"
    else:
        text = "I cannot verify whether Tado is requesting heat now; its demand readings are missing, invalid or more than ten minutes old."
        if power is not None and 0 <= power <= 100 and ages[1] is not None:
            minutes = int(ages[1] // 60)
            unit = "minute" if minutes == 1 else "minutes"
            text += f" Its last reported heat request was {power:g} percent, {minutes} {unit} ago."
        confidence = "unverified"
    if recent_mode:
        text += f" The thermostat recently reported {mode} mode."
        target = _number(e.target_c.value)
        target_age = _seconds_old(e.target_c, at)
        if target is not None and target_age is not None and target_age <= 600:
            text += f" Its target is {target:g} degrees."
    temp, temp_age = _number(e.hallway_temp_c.value), _seconds_old(e.hallway_temp_c, at)
    if temp is not None and temp_age is not None and temp_age <= 600:
        text += f" A separate hallway thermometer recently reported {temp:.1f} degrees."
    else:
        text += " The current hallway temperature is not verified."
    return Answer(text + " The actual boiler flame is not independently monitored.", confidence)

def respond_to_status_only(utterance, evidence, *, now=None):
    return answer_heating_status(evidence, now=now) if is_status_question(utterance) else None
