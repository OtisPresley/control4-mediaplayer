import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    prefix = "v27"

    # Registry cleanup logic remains exactly as is
    entities_to_remove = [
        entity.entity_id for entity in ent_reg.entities.values() 
        if entity.platform == DOMAIN and not str(entity.unique_id).startswith(prefix)
    ]
    for entity_id in entities_to_remove:
        ent_reg.async_remove(entity_id)

    devices_to_remove = [
        device.id for device in dev_reg.devices.values() 
        if any(identifier[0] == DOMAIN and not str(identifier[1]).startswith(prefix) 
               for identifier in device.identifiers)
    ]
    for device_id in devices_to_remove:
        dev_reg.async_remove_device(device_id)

    # ADDED: Listen for option updates
    entry.async_on_unload(entry.add_update_listener(update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, ["media_player"])
    return True

# ADDED: The listener that triggers the reload
async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload entry."""
    return await hass.config_entries.async_unload_platforms(entry, ["media_player"])