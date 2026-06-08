import logging

from homeassistant.components.number import RestoreNumber

try:
    from homeassistant.helpers.device_registry import DeviceInfo
except ImportError:
    from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, get_entity_name, get_unique_id

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

    entity = C4MaxVolumeNumber(hass, config_entry, manager, host, channel, device_info, zone_custom_name)
    hass.data[DOMAIN][config_entry.entry_id]["max_volume_entity"] = entity
    
    entities = [entity]
    if config_entry.data.get("enable_eq", False):
        entities.extend([
            C4EQNumber(
                hass, config_entry, manager, host, channel, device_info, zone_custom_name,
                name_suffix="Treble",
                unique_id_suffix="treble",
                default_val=0.0,
                config_key="treble",
                min_value=-12,
                max_value=12,
                cmd_prefix="c4.amp.trebgain",
            ),
            C4EQNumber(
                hass, config_entry, manager, host, channel, device_info, zone_custom_name,
                name_suffix="Bass",
                unique_id_suffix="bass",
                default_val=0.0,
                config_key="bass",
                min_value=-12,
                max_value=12,
                cmd_prefix="c4.amp.bassgain",
            ),
            C4EQNumber(
                hass, config_entry, manager, host, channel, device_info, zone_custom_name,
                name_suffix="Balance",
                unique_id_suffix="balance",
                default_val=0.0,
                config_key="balance",
                min_value=-10,
                max_value=10,
                cmd_prefix="c4.amp.bal",
            ),
        ])
    else:
        # Programmatically remove old EQ entities from Entity Registry so they don't stay as "unavailable"
        from homeassistant.helpers import entity_registry as er
        ent_reg = er.async_get(hass)
        
        treble_uid = get_unique_id(host, channel, "treble")
        bass_uid = get_unique_id(host, channel, "bass")
        bal_uid = get_unique_id(host, channel, "balance")
        
        for uid in (treble_uid, bass_uid, bal_uid):
            entity_id = ent_reg.async_get_entity_id("number", DOMAIN, uid)
            if entity_id:
                ent_reg.async_remove(entity_id)
                
    async_add_entities(entities)


def int_to_signed_hex(val: int) -> str:
    """Convert a signed integer to an 8-bit signed hex byte (two's complement)."""
    signed_val = int(val)
    if signed_val < 0:
        return f"{256 + signed_val:02x}"
    return f"{signed_val:02x}"


class C4NumberEntity(RestoreNumber):
    """Base class for Control4 Number entities to prevent code repetition and unify persistence using RestoreNumber."""
    _attr_has_entity_name = True

    def __init__(
        self,
        hass,
        config_entry,
        manager,
        host,
        channel,
        device_info,
        zone_custom_name,
        name_suffix,
        unique_id_suffix,
        default_val,
        config_key,
        min_value,
        max_value,
        step=1,
        cmd_prefix=None,
    ):
        self.hass = hass
        self._config_entry = config_entry
        self._manager = manager
        self._channel = channel
        self._config_key = config_key
        self._default_val = default_val
        self._cmd_prefix = cmd_prefix
        
        self._attr_name = get_entity_name(zone_custom_name, name_suffix)
        self._attr_unique_id = get_unique_id(host, channel, unique_id_suffix)
        self._attr_device_info = device_info
        
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        
        # Set initial default value
        self._attr_native_value = default_val

    async def async_added_to_hass(self):
        """Restore native value on startup."""
        await super().async_added_to_hass()
        
        # Restore the state using Home Assistant's built-in RestoreNumber helper
        last_number_data = await self.async_get_last_number_data()
        if last_number_data and last_number_data.native_value is not None:
            self._attr_native_value = float(last_number_data.native_value)
            
            # For Max Volume, we do NOT sync to hardware on startup to prevent audible volume jumps
            # if the physical amplifier is actively playing in the background.
            # It will be safely synced to the physical hardware on the next zone turn on/off or slider move.
            if self._config_key != "max_volume":
                await self._async_send_value_command(self._attr_native_value)

    async def async_set_native_value(self, value: float):
        self._attr_native_value = value
        
        # Dispatch command
        await self._async_send_value_command(value)
        self.async_write_ha_state()

    async def _async_send_value_command(self, value: float):
        """Send specific amplifier command for the value."""
        if self._cmd_prefix:
            zone_hex = f"{int(self._channel):02x}"
            val_hex = int_to_signed_hex(value)
            await self._manager.async_send_command(f"{self._cmd_prefix} {zone_hex} {val_hex}")


class C4MaxVolumeNumber(C4NumberEntity):
    """Entity representing the maximum volume limit of a zone."""
    def __init__(self, hass, config_entry, manager, host, channel, device_info, zone_custom_name):
        super().__init__(
            hass, config_entry, manager, host, channel, device_info, zone_custom_name,
            name_suffix="Max Volume",
            unique_id_suffix="max_volume",
            default_val=100.0,
            config_key="max_volume",
            min_value=0,
            max_value=100,
        )

    async def _async_send_value_command(self, value: float):
        # Software-only volume capping: cap the active play volume in HA and
        # send a chvol command if it exceeds the new maximum. No hardware
        # chvolmax command is ever sent to avoid amplifier register corruption
        # that causes audible volume blasts.
        media_player = self.hass.data[DOMAIN][self._config_entry.entry_id].get("media_player")
        if media_player:
            current_volume = media_player.volume_level  # float 0.0 to 1.0
            max_volume_float = value / 100.0
            if current_volume > max_volume_float:
                current_volume = max_volume_float
                media_player._volume = current_volume
                media_player.async_write_ha_state()
                await media_player._amp.async_set_volume(current_volume)


class C4EQNumber(C4NumberEntity):
    """Generic class representing EQ adjustments (Treble, Bass, Balance) of a zone."""
    def __init__(
        self,
        hass,
        config_entry,
        manager,
        host,
        channel,
        device_info,
        zone_custom_name,
        name_suffix,
        unique_id_suffix,
        default_val,
        config_key,
        min_value,
        max_value,
        cmd_prefix,
    ):
        super().__init__(
            hass, config_entry, manager, host, channel, device_info, zone_custom_name,
            name_suffix=name_suffix,
            unique_id_suffix=unique_id_suffix,
            default_val=default_val,
            config_key=config_key,
            min_value=min_value,
            max_value=max_value,
            cmd_prefix=cmd_prefix,
        )
