import logging

from homeassistant.components.number import NumberEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    host = config_entry.data.get("host")
    channel = config_entry.data.get("channel")
    manager = hass.data[DOMAIN][config_entry.entry_id]["manager"]
    amp_label = config_entry.data.get("name", "Matrix Amp")
    
    # Get the custom name assigned to this zone
    zone_custom_name = config_entry.data.get("zone_custom_name", f"Zone {channel}")

    device_info = DeviceInfo(
        identifiers={(DOMAIN, f"v27_{host}_main_amp")},
        name=amp_label,
        manufacturer="Control4",
        model="Matrix Amplifier",
    )

    async_add_entities([
        C4MaxVolumeNumber(manager, host, channel, device_info, zone_custom_name),
    ])

class C4MaxVolumeNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1

    def __init__(self, manager, host, channel, device_info, zone_custom_name):
        self._manager = manager
        self._channel = channel
        self._attr_name = f"{zone_custom_name} Max Volume"
        self._attr_unique_id = f"v27_{host}_ch{channel}_max_volume"
        self._attr_device_info = device_info
        self._attr_native_value = 100

    async def async_set_native_value(self, value: float):
        self._attr_native_value = value
        await self._manager.async_set_max_volume(self._channel, value)
        self.async_write_ha_state()
