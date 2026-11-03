"""Single-instance setup with privately stored source selections."""
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .const import DOMAIN, SOURCE_DOMAINS


class EdwardHeatingRouterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors = {}
        if user_input is not None:
            for key, domain in SOURCE_DOMAINS.items():
                value = user_input.get(key)
                if (not isinstance(value, str)
                        or not value.startswith(domain + ".")
                        or self.hass.states.get(value) is None):
                    errors[key] = "invalid_entity"
            if not errors:
                # Keep only declared settings. No credentials or home-specific
                # identifiers are embedded in the distributable source.
                return self.async_create_entry(
                    title="Edward Heating Router",
                    data={key: user_input[key] for key in SOURCE_DOMAINS},
                )
        schema = vol.Schema({
            vol.Required(key): EntitySelector(EntitySelectorConfig(domain=domain))
            for key, domain in SOURCE_DOMAINS.items()
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
