# Offline tests

Run with Python 3.12+ from the repository root:

    python -m venv .venv
    .venv/bin/python -m pip install -r tests/requirements.txt
    .venv/bin/python -m unittest discover -s tests -v
    .venv/bin/python -m compileall -q custom_components tests

45 tests passed with Python 3.12.14 and voluptuous 0.16.0.
Tests use synthetic entity IDs and do not access
Home Assistant, devices, network services or an LLM.

The harness executes the vendored upstream `models.py` and `entity.py` unchanged
and extracts the upstream `AssistantContent` dataclass. HA dependencies are
stubbed: intents, entity state writes, agent lookup, state registry, session and
chat-log context managers, configuration-flow plumbing and entity selectors.
Config-flow schema checks use real voluptuous. Single-instance tests verify the
component calls the expected unique-ID guard; they do not test the HA registry.

Coverage retains all original 32 cases: all 17 expected status phrases; commands
passed through; 600/601-second boundary; missing/naive/old/future timestamps;
contradictory readings; invalid/unavailable/NaN/infinite values; independent
Matter freshness; unverified boiler flame; no local device or fallback calls;
original input identity/fields; ID restoration; modern and legacy fallback;
recursion; no retries; continuation, conversation IDs and one-time sessions.

13 additional cases verify arbitrary configured source IDs, exact source reads,
entry-data copying, required selectors and domains, missing/wrong-domain/absent
entities, non-string values, declared-field filtering, single-instance guard,
unavailable-but-existing entities, and no embedded source entity-ID constants.

These tests do not establish live installation/startup compatibility or actual
HA chat-log/streaming integration, provider tools, satellite or spoken TTS
behavior. Deployment smoke tests are still required.
