import logging

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
)
from homeassistant.const import STATE_OFF, STATE_ON

try:
    from homeassistant.helpers.device_registry import DeviceInfo
except ImportError:
    from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, get_entity_name, get_unique_id
from .control4Amp import control4AmpChannel

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    host = config_entry.data.get("host")
    port = config_entry.data.get("port")
    channel = config_entry.data.get("channel")
    name = config_entry.data.get("zone_custom_name")
    
    # Retrieve the manager initialized in __init__.py
    manager = hass.data[DOMAIN][config_entry.entry_id]["manager"]
    
    entity = C4MediaPlayer(host, port, channel, name, config_entry, manager)
    hass.data[DOMAIN][config_entry.entry_id]["media_player"] = entity
    async_add_entities([entity], update_before_add=True)

class C4MediaPlayer(MediaPlayerEntity, RestoreEntity):
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET | MediaPlayerEntityFeature.VOLUME_STEP |
        MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF |
        MediaPlayerEntityFeature.SELECT_SOURCE | MediaPlayerEntityFeature.VOLUME_MUTE
    )

    def __init__(self, host, port, channel, zone_custom_name, config_entry, manager):
        self._amp = control4AmpChannel(manager, channel)
        self._host, self._port, self._channel = host, port, channel
        self._config_entry = config_entry 
        
        amp_label = config_entry.data.get("name", "Matrix Amp")
        
        self._state, self._volume, self._muted, self._source = STATE_OFF, 0.5, False, None

        self._attr_has_entity_name = True
        
        self._attr_name = get_entity_name(config_entry.data.get("zone_custom_name", zone_custom_name))
        
        # Maintaining the v27_ prefix as explicitly requested by the user
        self._attr_unique_id = get_unique_id(host, channel)
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"v27_{host}_main_amp")},
            name=amp_label,
            manufacturer="Control4",
            model="Matrix Amplifier",
        )
        
        raw_sources = config_entry.data.get("source_list", "")
        self._source_list = [s.strip() for s in raw_sources.split("\n") if s.strip()]

    @property
    def state(self): return self._state
    @property
    def volume_level(self): return self._volume
    @property
    def is_volume_muted(self): return self._muted
    @property
    def source_list(self): return self._source_list
    @property
    def source(self): return self._source

    @property
    def max_volume(self) -> float:
        """Return the current maximum volume level as a float (0.0 to 1.0)."""
        max_vol_entity = self.hass.data[DOMAIN][self._config_entry.entry_id].get("max_volume_entity")
        if max_vol_entity and max_vol_entity.native_value is not None:
            return float(max_vol_entity.native_value) / 100.0
        return 1.0

    async def async_turn_on(self):
        # 1. Calculate and cap the play volume
        on_vol_percent = self._config_entry.data.get("on_volume", 50)
        self._volume = on_vol_percent / 100.0
        max_vol = self.max_volume
        if self._volume > max_vol:
            self._volume = max_vol

        # 2. Pre-load the correct play volume into the amp BEFORE waking it from
        #    power save. This ensures the register is already at the right level
        #    the instant the amp resumes routing, preventing any volume blast.
        await self._amp.async_set_volume(self._volume)

        # 3. Wake the system out of power save (amp now resumes at the correct volume)
        await self._amp._manager.async_set_power_save(False)

        # 4. Route the input to start playing
        if self._source in self._source_list:
            idx = self._source_list.index(self._source) + 1
        else:
            idx = 1
        self._amp._source = idx
        await self._amp.async_set_source(idx)

        self._state = STATE_ON
        self.async_write_ha_state()

    async def async_turn_off(self):
        await self._amp.async_turn_off()
        self._state = STATE_OFF
        self.async_write_ha_state()

    async def async_set_volume_level(self, volume):
        max_vol = self.max_volume
        if volume > max_vol:
            volume = max_vol
        await self._amp.async_set_volume(volume)
        self._volume = volume
        self.async_write_ha_state()

    async def async_mute_volume(self, mute):
        await self._amp.async_mute_volume(mute)
        self._muted = mute
        self.async_write_ha_state()

    async def async_select_source(self, source):
        if source in self._source_list:
            idx = self._source_list.index(source) + 1
            await self._amp.async_set_source(idx)
            self._source = source
            self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Restore state on startup."""
        await super().async_added_to_hass()
        
        last_state = await self.async_get_last_state()
        if last_state:
            self._state = last_state.state
            
            # Restore volume
            if "volume_level" in last_state.attributes:
                self._volume = float(last_state.attributes["volume_level"])
            
            # Restore muted
            if "is_volume_muted" in last_state.attributes:
                self._muted = bool(last_state.attributes["is_volume_muted"])
            elif "muted" in last_state.attributes:
                self._muted = bool(last_state.attributes["muted"])
                
            # Restore source
            if "source" in last_state.attributes:
                self._source = last_state.attributes["source"]
                if self._source in self._source_list:
                    idx = self._source_list.index(self._source) + 1
                    self._amp._source = idx
                    
        # Software cap the restored volume on load (completely silent/passive)
        max_vol = self.max_volume
        if self._volume > max_vol:
            self._volume = max_vol