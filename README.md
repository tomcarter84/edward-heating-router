# Edward Heating Router

A small Home Assistant conversation agent for conservative, deterministic Tado
heating-status answers. It handles an explicit English phrase list locally and
passes every other request to an existing `conversation.openai_conversation`
agent, preserving the conversation ID, context, device, satellite and extra prompt.

## Scope and safety

- The local status path reads the four source entities selected during setup.
  Household entity IDs and credentials are not included in this repository.
- Recent Tado mode, heat-request percentage and heating demand must all be valid
  and no more than 600 seconds old. Conflicting or stale sources are reported
  as unverified. A fresh separate thermometer cannot freshen old demand data.
- Freshness uses the live Home Assistant `State.last_reported` timestamp.
- Heat request is not proof of a burning boiler. Replies always state that the
  actual boiler flame is not independently monitored.
- The local status path does not call device services or an AI model. Unmatched
  requests use the existing agent and its existing permissions. This router is
  not an independent action-authorization gateway.
- Matched replies retain the conversation ID and invite a follow-up question.

Examples include “Is the heating on?”, “Is the heating on or off?”, “Is the boiler
firing?” and “What is the heating status?”. See `policy.py` for the complete exact
phrase list. Optional “Edward” prefixes and normal terminal punctuation are
accepted. Command or mixed-command phrasing is not intercepted.

This version is deliberately designed for one Tado heating zone and a separate
hallway thermometer in Celsius. It is not a general-purpose climate controller.
The source configuration is selectable; reply wording still refers to Tado and
the hallway.

## Compatibility

Developed and offline-tested against Home Assistant Core **2026.10.4**.
Version 0.1.1 adds private source selection to the initial implementation.
Actual HA startup, provider streaming and physical voice behavior need live
acceptance testing on the target installation; offline checks are not a claim
of end-to-end compatibility with every Home Assistant release.

## Installation with HACS

1. Add this repository as a custom **Integration** repository in HACS.
2. Download **Edward Heating Router**.
3. Check your Home Assistant configuration and restart Home Assistant.
4. In **Settings → Devices & services**, add **Edward Heating Router**.
5. Select the climate entity, its Tado heat-request percentage sensor, its
   heating-demand binary sensor, and the separate Celsius temperature sensor.
   Verify the percentage and Celsius units when selecting the sensors. Setup
   validates the entity domains and existence, not the manufacturer or units.
   The selected IDs are stored in your local Home Assistant configuration.
6. Test the new conversation agent with read-only text questions before selecting
   it in a production voice assistant. Keep a record of the previous agent.

For manual installation, copy only `custom_components/edward_heating_router`
into your configuration's existing `custom_components` directory, then follow
steps 3–6. Do not replace the entire `custom_components` directory.

The integration does not change pipelines or dashboards automatically. To use it
for voice, select its conversation agent in the intended assistant while leaving
speech-to-text, voice, language and wake-word settings unchanged. If a custom
text UI directly names an agent, update that target separately. Verify the
registered entity ID rather than assuming it.

Do not send real thermostat commands as negative tests. The automated tests cover
command routing. Use status questions and harmless read-only follow-ups for live
acceptance, including a heating-status question after another conversation turn.

## Rollback

Restore the original conversation agent in each assistant or custom text UI that
you changed. Refresh cached custom frontend assets if needed. Verify normal
conversation, then disable or remove only the Edward Heating Router integration.
Its files can remain in place while disabled. If you later remove the files,
restart Home Assistant normally. Do not remove your original conversation agent.

## Why a conversation agent?

In Core 2026.10.4, agent-requested follow-up turns skip sentence-trigger handling.
A wrapper at the selected conversation-agent boundary can handle those turns
without enabling broad local control intents.

Reviewed upstream interfaces:
- [Conversation entity](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/conversation/entity.py)
- [Conversation models](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/conversation/models.py)
- [Agent manager](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/conversation/agent_manager.py)
- [Assist pipeline](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/assist_pipeline/default_pipeline.py)

## Tests

Run `python -m unittest discover -s tests -v` and
`python -m compileall -q custom_components tests` from the repository root.
The harness uses lightweight HA dependencies and three unmodified upstream
fixtures. Their Apache-2.0 license and provenance are in `upstream/`.

See `tests/README.md` for dependencies, coverage and limits.
