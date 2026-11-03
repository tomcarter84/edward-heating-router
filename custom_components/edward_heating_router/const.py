"""Routing defaults and private configuration keys."""
DOMAIN = "edward_heating_router"
FALLBACK_AGENT = "conversation.openai_conversation"
CONF_CLIMATE = "climate_entity"
CONF_POWER = "power_entity"
CONF_DEMAND = "demand_entity"
CONF_TEMPERATURE = "temperature_entity"
SOURCE_DOMAINS = {
    CONF_CLIMATE: "climate",
    CONF_POWER: "sensor",
    CONF_DEMAND: "binary_sensor",
    CONF_TEMPERATURE: "sensor",
}
