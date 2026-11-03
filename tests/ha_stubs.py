"""Offline HA harness. Executes vendored models.py and entity.py unchanged.

Only dependencies are stubbed: storage, intents, restore state, chat contexts.
This verifies router call contracts, not a real HA installation or streaming TTS.
"""
import ast
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntFlag
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]

def module(name, **attrs):
    m = ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m

class IntentResponse:
    def __init__(self, language):
        self.language, self.speech, self.error = language, None, None
    def async_set_speech(self, speech):
        self.speech = speech
    def async_set_error(self, code, message):
        self.error = (code, message)

class RestoreEntity:
    def async_set_context(self, context):
        self.context_seen = context
    def async_write_ha_state(self):
        self.state_writes = getattr(self, 'state_writes', 0) + 1

class Feature(IntFlag):
    CONTROL = 1

@contextmanager
def session(hass, conversation_id):
    hass.session_calls.append(conversation_id)
    if conversation_id is None:
        hass.counter += 1
        conversation_id = f'generated-{hass.counter}'
    yield SimpleNamespace(conversation_id=conversation_id)

class ChatLog:
    def __init__(self, conversation_id):
        self.conversation_id, self.content = conversation_id, []
    def async_add_assistant_content_without_tools(self, content):
        if content.tool_calls:
            raise AssertionError('Local status must not call tools')
        self.content.append(content)

@contextmanager
def chat_log(hass, session, user_input):
    log = hass.logs.setdefault(session.conversation_id, ChatLog(session.conversation_id))
    log.content.append(SimpleNamespace(role='user', content=user_input.text))
    yield log

module('homeassistant')
module('homeassistant.components')
module('homeassistant.helpers')
module('homeassistant.core', Context=object)
module('homeassistant.const', STATE_UNAVAILABLE='unavailable', STATE_UNKNOWN='unknown')
intent = module('homeassistant.helpers.intent', IntentResponse=IntentResponse,
                IntentResponseErrorCode=SimpleNamespace(UNKNOWN='unknown'))
module('homeassistant.helpers.llm', LLMContext=object)
module('homeassistant.helpers.restore_state', RestoreEntity=RestoreEntity)
module('homeassistant.helpers.chat_session', async_get_chat_session=session)
module('homeassistant.util')
module('homeassistant.util.dt', utcnow=lambda: datetime.now(timezone.utc))
conversation = module('homeassistant.components.conversation')
module('homeassistant.components.conversation.const', DOMAIN='conversation', ConversationEntityFeature=Feature)
module('homeassistant.components.conversation.chat_log', ChatLog=ChatLog, async_get_chat_log=chat_log)
module('homeassistant.components.conversation.agent_manager', async_get_agent=lambda hass, name: hass.agents.get(name))
models = load('homeassistant.components.conversation.models', ROOT/'upstream/models.py')
entity = load('homeassistant.components.conversation.entity', ROOT/'upstream/entity.py')
conversation.ConversationEntity = entity.ConversationEntity
conversation.ConversationEntityFeature = Feature
conversation.ConversationResult = models.ConversationResult
# Execute the exact upstream AssistantContent dataclass with its annotations.
tree = ast.parse((ROOT/'upstream/chat_log.py').read_text())
node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AssistantContent')
ns = dict(dataclass=dataclass, field=field, Literal=Literal, Any=Any, datetime=datetime,
          utcnow=lambda: datetime.now(timezone.utc), llm=SimpleNamespace(ToolInput=object))
exec(compile(ast.Module(body=[node], type_ignores=[]), 'upstream/chat_log.py', 'exec'), ns)
conversation.AssistantContent = ns['AssistantContent']
# Do not execute integration setup: only the conversation/policy modules are in scope.
module('custom_components')
package = module('custom_components.edward_heating_router')
package.__path__ = [str(ROOT/'custom_components/edward_heating_router')]
const = load('custom_components.edward_heating_router.const', ROOT/'custom_components/edward_heating_router/const.py')
policy = load('custom_components.edward_heating_router.policy', ROOT/'custom_components/edward_heating_router/policy.py')
router_module = load('custom_components.edward_heating_router.conversation', ROOT/'custom_components/edward_heating_router/conversation.py')

class AbortFlow(Exception):
    """Stub matching the observable configured-unique-ID abort contract."""

class ConfigFlow:
    def __init_subclass__(cls, *, domain, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.domain = domain
    async def async_set_unique_id(self, value):
        self.unique_id = value
    def _abort_if_unique_id_configured(self):
        if self.unique_id in self.hass.configured_unique_ids:
            raise AbortFlow('already_configured')
    def async_create_entry(self, *, title, data):
        return {'type':'create_entry', 'title':title, 'data':data}
    def async_show_form(self, *, step_id, data_schema, errors):
        return {'type':'form', 'step_id':step_id, 'data_schema':data_schema, 'errors':errors}

class EntitySelector:
    def __init__(self, config):
        self.config = config
    def __call__(self, value):
        # HA selector internals are outside this offline harness. The component
        # validates domain/existence itself; tests assert selector config too.
        if not isinstance(value, str):
            raise ValueError('entity_id must be a string')
        return value

module('homeassistant.config_entries', ConfigFlow=ConfigFlow)
module('homeassistant.helpers.selector', EntitySelector=EntitySelector, EntitySelectorConfig=dict)
