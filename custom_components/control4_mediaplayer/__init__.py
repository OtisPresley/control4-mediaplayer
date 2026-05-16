import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .manager import Control4Manager

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

    # Initialize Control4Manager
    host = entry.data.get("host")
    port = entry.data.get("port", 8750)
    amp_label = entry.data.get("name", "Matrix Amp")
    
    hass.data.setdefault(DOMAIN, {})
    manager = Control4Manager(host, port)
    hass.data[DOMAIN][entry.entry_id] = {
        "manager": manager
    }

    # Force device name to match user-set name from config entry
    device = dev_reg.async_get_device(identifiers={(DOMAIN, f"v27_{host}_main_amp")})
    if device and device.name != amp_label:
        _LOGGER.info("Updating device name to %s", amp_label)
        dev_reg.async_update_device(device.id, name=amp_label)

    # Apply input gains from config entry (only do it once for Channel 1)
    if entry.data.get("channel") == 1:
        input_gains_str = entry.data.get("input_gains", "")
        if input_gains_str:
            _LOGGER.info("Applying input gains for %s", amp_label)
            gains = input_gains_str.split("\n")
            for i, gain in enumerate(gains):
                if gain.strip():
                    try:
                        gain_val = float(gain.strip())
                        await manager.async_set_input_gain(i + 1, gain_val)
                    except ValueError:
                        _LOGGER.warning("Invalid input gain value in config: %s", gain)



    if not hass.services.has_service(DOMAIN, "party_mode"):
        async def handle_party_mode(call):
            source = call.data.get("source")
            volume = call.data.get("volume", 50)
            for current_entry in hass.config_entries.async_entries(DOMAIN):
                if current_entry.entry_id in hass.data.get(DOMAIN, {}):
                    manager = hass.data[DOMAIN][current_entry.entry_id]["manager"]
                    channel = current_entry.data.get("channel")
                    source_list = current_entry.data.get("source_list", "").split("\n")
                    sources = [s.strip() for s in source_list if s.strip()]
                    if source in sources:
                        idx = sources.index(source) + 1
                        await manager.async_send_command("c4.amp.psave 00 00")
                        await manager.async_send_command(f"c4.amp.out {channel:02x} {idx:02x}")
                        vol_hex = f"{int(volume + 155):02x}"
                        await manager.async_send_command(f"c4.amp.chvol {channel:02x} {vol_hex}")

        hass.services.async_register(DOMAIN, "party_mode", handle_party_mode)

    if not hass.services.has_service(DOMAIN, "send_raw_command"):
        async def handle_send_raw_command(call):
            command = call.data.get("command")
            entity_ids = call.data.get("entity_id", [])
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]
            
            for entity_id in entity_ids:
                entity = ent_reg.async_get(entity_id)
                if entity and entity.config_entry_id in hass.data.get(DOMAIN, {}):
                    manager = hass.data[DOMAIN][entity.config_entry_id]["manager"]
                    await manager.async_send_command(command)

        hass.services.async_register(DOMAIN, "send_raw_command", handle_send_raw_command)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    await hass.config_entries.async_forward_entry_setups(
        entry, ["media_player", "number"]
    )
    return True

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, ["media_player", "number"]
    )
    if unload_ok and entry.entry_id in hass.data.get(DOMAIN, {}):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok