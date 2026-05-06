import logging
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
)
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN
from .control4Amp import control4AmpChannel

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    host = config_entry.data.get("host")
    port = config_entry.data.get("port")
    channel = config_entry.data.get("channel")
    name = config_entry.data.get("zone_custom_name")
    async_add_entities([C4MediaPlayer(host, port, channel, name, config_entry)], update_before_add=True)

class C4MediaPlayer(MediaPlayerEntity):
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET | MediaPlayerEntityFeature.VOLUME_STEP |
        MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF |
        MediaPlayerEntityFeature.SELECT_SOURCE | MediaPlayerEntityFeature.VOLUME_MUTE
    )

    def __init__(self, host, port, channel, zone_custom_name, config_entry):
        self._amp = control4AmpChannel(host, port, channel)
        self._host, self._port, self._channel = host, port, channel
        self._config_entry = config_entry 
        
        amp_label = config_entry.data.get("name", "Matrix Amp")
        
        self._state, self._volume, self._muted, self._source = STATE_OFF, 0.5, False, None

        self._attr_has_entity_name = True
        
        # Pull latest values from config_entry
        self._attr_name = config_entry.data.get("zone_custom_name", zone_custom_name)
        self._attr_unique_id = f"v27_{host}_ch{channel}"
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"v27_{host}_main_amp")},
            name=amp_label,
            manufacturer="Control4",
            model="Matrix Amplifier",
        )
        
        # Pull latest source list from config_entry
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

    async def async_turn_on(self):
        await self.hass.async_add_executor_job(self._amp.turn_on)
        
        # Read the power on volume you set in the Options menu
        on_vol_percent = self._config_entry.data.get("on_volume", 50)
        self._volume = on_vol_percent / 100.0
        
        # Tell the amp to move to that volume
        await self.hass.async_add_executor_job(setattr, self._amp, "volume", self._volume)
        
        self._state = STATE_ON
        self.async_write_ha_state()

    async def async_turn_off(self):
        await self.hass.async_add_executor_job(self._amp.turn_off)
        self._state = STATE_OFF
        self.async_write_ha_state()

    async def async_set_volume_level(self, volume):
        await self.hass.async_add_executor_job(setattr, self._amp, "volume", volume)
        self._volume = volume
        self.async_write_ha_state()

    async def async_mute_volume(self, mute):
        target_vol = 0 if mute else self._volume
        await self.hass.async_add_executor_job(setattr, self._amp, "volume", target_vol)
        self._muted = mute
        self.async_write_ha_state()

    async def async_select_source(self, source):
        if source in self._source_list:
            idx = self._source_list.index(source) + 1
            await self.hass.async_add_executor_job(setattr, self._amp, "source", idx)
            self._source = source
            self.async_write_ha_state()