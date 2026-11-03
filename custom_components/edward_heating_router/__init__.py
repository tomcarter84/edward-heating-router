"""Edward's local, read-only heating status conversation router."""
from homeassistant.const import Platform

PLATFORMS = [Platform.CONVERSATION]

async def async_setup_entry(hass, entry):
    """Load only our conversation entity; do not alter a pipeline."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass, entry):
    """Unload only our entity."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
