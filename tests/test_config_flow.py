"""Config-flow validation with real voluptuous and stubbed HA flow plumbing."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
import voluptuous as vol
from ha_stubs import load, ROOT, const as c, AbortFlow

flow_module = load('custom_components.edward_heating_router.config_flow',
                   ROOT/'custom_components/edward_heating_router/config_flow.py')

SOURCES = {
    c.CONF_CLIMATE:'climate.fixture_zone',
    c.CONF_POWER:'sensor.fixture_power',
    c.CONF_DEMAND:'binary_sensor.fixture_demand',
    c.CONF_TEMPERATURE:'sensor.fixture_temperature',
}

class ConfigFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.entities = {name:object() for name in SOURCES.values()}
        self.flow = flow_module.EdwardHeatingRouterConfigFlow()
        self.flow.hass = SimpleNamespace(states=SimpleNamespace(get=self.entities.get),
                                         configured_unique_ids=set())
    async def test_form_has_exact_required_fields_and_correct_domain_selectors(self):
        result = await self.flow.async_step_user()
        self.assertEqual(result['type'],'form')
        self.assertEqual(result['step_id'],'user')
        self.assertEqual(result['errors'],{})
        schema = result['data_schema']
        self.assertEqual({key.schema for key in schema.schema},set(c.SOURCE_DOMAINS))
        for key, selector in schema.schema.items():
            self.assertIsInstance(key,vol.Required)
            self.assertEqual(selector.config,{'domain':c.SOURCE_DOMAINS[key.schema]})
        with self.assertRaises(vol.MultipleInvalid):
            schema({})
        self.assertEqual(schema(SOURCES),SOURCES)
    async def test_valid_configuration_creates_expected_entry(self):
        result = await self.flow.async_step_user(dict(SOURCES))
        self.assertEqual(result,{'type':'create_entry','title':'Edward Heating Router','data':SOURCES})
        self.assertEqual(self.flow.unique_id,c.DOMAIN)
        self.assertEqual(self.flow.VERSION,1)
    async def test_each_missing_required_entity_rejected(self):
        for key in SOURCES:
            with self.subTest(key=key):
                values = dict(SOURCES)
                del values[key]
                result = await self.flow.async_step_user(values)
                self.assertEqual(result['type'],'form')
                self.assertEqual(result['errors'],{key:'invalid_entity'})
    async def test_empty_submission_reports_all_missing_entities(self):
        result = await self.flow.async_step_user({})
        self.assertEqual(result['errors'],{key:'invalid_entity' for key in SOURCES})
    async def test_each_wrong_domain_rejected_even_when_entity_exists(self):
        for key in SOURCES:
            with self.subTest(key=key):
                values = dict(SOURCES)
                values[key] = 'light.fixture_wrong_domain'
                self.entities[values[key]] = object()
                result = await self.flow.async_step_user(values)
                self.assertEqual(result['errors'],{key:'invalid_entity'})
    async def test_each_absent_entity_rejected_even_with_correct_domain(self):
        for key, domain in c.SOURCE_DOMAINS.items():
            with self.subTest(key=key):
                values = dict(SOURCES)
                values[key] = domain+'.does_not_exist'
                result = await self.flow.async_step_user(values)
                self.assertEqual(result['errors'],{key:'invalid_entity'})
    async def test_non_string_and_empty_values_rejected(self):
        for key in SOURCES:
            for invalid in [None,False,42,[],{},'']:
                with self.subTest(key=key,value=invalid):
                    result = await self.flow.async_step_user({**SOURCES,key:invalid})
                    self.assertEqual(result['errors'],{key:'invalid_entity'})
    async def test_only_declared_fields_are_saved(self):
        result = await self.flow.async_step_user({**SOURCES,'unexpected':'drop-me',
            'fallback_agent':'conversation.other','arbitrary_metadata':{'example':True}})
        self.assertEqual(result['data'],SOURCES)
    async def test_single_instance_aborts_before_form_or_entry(self):
        self.flow.hass.configured_unique_ids.add(c.DOMAIN)
        for values in [None,SOURCES]:
            with self.subTest(values=values):
                with self.assertRaisesRegex(AbortFlow,'already_configured'):
                    await self.flow.async_step_user(values)
    async def test_unavailable_but_existing_entity_allowed_for_fail_closed_runtime(self):
        for name in self.entities:
            self.entities[name] = SimpleNamespace(state='unavailable')
        self.assertEqual((await self.flow.async_step_user(SOURCES))['type'],'create_entry')
    async def test_component_has_no_embedded_source_entity_identifiers(self):
        forbidden_prefixes = ('climate.','sensor.','binary_sensor.')
        for path in (ROOT/'custom_components/edward_heating_router').glob('*.py'):
            with self.subTest(file=path.name):
                strings = [node.value for node in ast.walk(ast.parse(path.read_text()))
                           if isinstance(node,ast.Constant) and isinstance(node.value,str)]
                self.assertFalse([value for value in strings if value.startswith(forbidden_prefixes)])
        self.assertEqual(c.FALLBACK_AGENT,'conversation.openai_conversation')
