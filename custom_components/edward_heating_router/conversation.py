"""Supported ConversationEntity wrapper for Home Assistant Core 2026.10.4."""
from contextvars import ContextVar
import logging

from homeassistant.components import conversation
from homeassistant.components.conversation.agent_manager import async_get_agent
from homeassistant.helpers import intent

from .const import (
    CONF_CLIMATE, CONF_DEMAND, CONF_POWER, CONF_TEMPERATURE, FALLBACK_AGENT,
)
from .policy import HeatingEvidence, Reading, answer_heating_status, is_status_question

_LOGGER = logging.getLogger(__name__)
_ROUTING = ContextVar("edward_heating_router_active", default=False)
PARALLEL_UPDATES = 0

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([EdwardHeatingRouter(entry)])

class EdwardHeatingRouter(conversation.ConversationEntity):
    """Intercept only exact status questions; keep the existing agent intact."""
    _attr_name = "Edward Heating Router"
    # Fallback OpenAI uses the current shared chat log and its delta listener.
    # Local text returns normally; Core TTS uses the non-streaming response path.
    _attr_supports_streaming = True

    def __init__(self, entry):
        self._attr_unique_id = entry.entry_id
        self._sources = dict(entry.data)

    @property
    def supported_languages(self):
        return "*"  # English allowlist only; other text passes through unchanged.

    @property
    def supported_features(self):
        agent = async_get_agent(self.hass, FALLBACK_AGENT)
        if agent is None or agent is self or isinstance(agent, EdwardHeatingRouter):
            return conversation.ConversationEntityFeature(0)
        return getattr(agent, "supported_features", conversation.ConversationEntityFeature(0))

    async def async_process(self, user_input):
        if _ROUTING.get():
            return self._error(user_input, "Edward's conversation route is unavailable.")
        token = _ROUTING.set(True)
        try:
            if is_status_question(user_input.text):
                # Base method creates/reuses HA's session and chat log. Opening
                # that context only locally avoids generating a second session
                # when the fallback receives conversation_id=None.
                return await super().async_process(user_input)
            agent = async_get_agent(self.hass, FALLBACK_AGENT)
            if agent is None or agent is self or isinstance(agent, EdwardHeatingRouter):
                return self._error(user_input, "Edward's usual conversation agent is unavailable.")
            original_agent_id = user_input.agent_id
            try:
                # Original object: preserve all present/future input fields,
                # identity-bearing context, device, satellite and extra prompt.
                user_input.agent_id = FALLBACK_AGENT
                if isinstance(agent, conversation.ConversationEntity):
                    agent.async_set_context(user_input.context)
                    return await agent.internal_async_process(user_input)
                return await agent.async_process(user_input)
            finally:
                user_input.agent_id = original_agent_id
        except Exception:
            # Do not retry a provider: it may already have executed tools.
            _LOGGER.exception("Edward conversation processing failed")
            return self._error(user_input, "I'm sorry, I couldn't complete that request. Please try again.")
        finally:
            _ROUTING.reset(token)

    def _error(self, user_input, message):
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_error(intent.IntentResponseErrorCode.UNKNOWN, message)
        return conversation.ConversationResult(response=response, conversation_id=user_input.conversation_id)

    async def _async_handle_message(self, user_input, chat_log):
        def reading(entity_id, attribute=None):
            state = self.hass.states.get(entity_id)
            if state is None:
                return Reading(None, None)
            value = state.attributes.get(attribute) if attribute else state.state
            # Live State.last_reported only. Never last_updated/last_changed,
            # REST serialization, or the separate Matter temperature timestamp.
            return Reading(value, state.last_reported)
        evidence = HeatingEvidence(
            mode=reading(self._sources[CONF_CLIMATE]), power_percent=reading(self._sources[CONF_POWER]),
            demand=reading(self._sources[CONF_DEMAND]), hallway_temp_c=reading(self._sources[CONF_TEMPERATURE]),
            target_c=reading(self._sources[CONF_CLIMATE], "temperature"),
        )
        text = answer_heating_status(evidence).text + " Anything else I can help with?"
        chat_log.async_add_assistant_content_without_tools(
            conversation.AssistantContent(agent_id=self.entity_id, content=text)
        )
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(text)
        return conversation.ConversationResult(
            response=response, conversation_id=chat_log.conversation_id,
            continue_conversation=True,
        )
