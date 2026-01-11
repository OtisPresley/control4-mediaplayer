"""Control4 Media Player platform (config entry + YAML import)."""
from __future__ import annotations

import logging
from datetime import timedelta
import re
from time import monotonic

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.media_player import (
    PLATFORM_SCHEMA,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_CHANNEL,
    CONF_HOST,
    CONF_ON_VOLUME,
    CONF_POLL_EXTERNAL,
    CONF_POLL_INTERVAL,
    CONF_PORT,
    CONF_SOURCE_LIST,
    DEFAULT_POLL_EXTERNAL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SOURCE_LIST,
    DEFAULT_VOLUME,
    DOMAIN,
)
from .control4Amp import control4AmpChannel, send_udp_command

_LOGGER = logging.getLogger(__name__)

SUPPORT_C4 = (
    MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.VOLUME_MUTE
)

# ----------------- optional legacy YAML import -----------------
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required("name"): cv.string,
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Required(CONF_CHANNEL): cv.positive_int,
        vol.Optional(CONF_ON_VOLUME, default=DEFAULT_VOLUME): cv.positive_int,
        vol.Optional(CONF_SOURCE_LIST, default=DEFAULT_SOURCE_LIST): cv.ensure_list,
    }
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Import YAML to a config entry once, then manage via UI."""
    data = {
        "name": config.get("name"),
        CONF_HOST: config.get(CONF_HOST),
        CONF_PORT: config.get(CONF_PORT, DEFAULT_PORT),
        CONF_CHANNEL: config.get(CONF_CHANNEL),
        CONF_ON_VOLUME: config.get(CONF_ON_VOLUME, DEFAULT_VOLUME),
        CONF_POLL_EXTERNAL: config.get(CONF_POLL_EXTERNAL, DEFAULT_POLL_EXTERNAL),
        CONF_POLL_INTERVAL: config.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
        CONF_SOURCE_LIST: config.get(CONF_SOURCE_LIST, DEFAULT_SOURCE_LIST),
    }
    unique = f'{data[CONF_HOST]}:{data[CONF_PORT]}:ch{data[CONF_CHANNEL]}'
    if any(e.unique_id == unique for e in hass.config_entries.async_entries(DOMAIN)):
        _LOGGER.info("YAML import skipped; config entry already exists for %s", unique)
        return

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "import"}, data=data
        )
    )
# ----------------- end YAML import -----------------


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    data = entry.data
    opts = entry.options or {}

    name = data["name"]
    host = data[CONF_HOST]
    port = data.get(CONF_PORT, DEFAULT_PORT)
    channel = data[CONF_CHANNEL]
    on_volume = int(opts.get(CONF_ON_VOLUME, data.get(CONF_ON_VOLUME, DEFAULT_VOLUME)))
    poll_external = bool(opts.get(CONF_POLL_EXTERNAL, data.get(CONF_POLL_EXTERNAL, DEFAULT_POLL_EXTERNAL)))
    poll_interval = int(opts.get(CONF_POLL_INTERVAL, data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)))
    poll_interval = max(1, min(poll_interval, 300))
    src = opts.get(CONF_SOURCE_LIST, data.get(CONF_SOURCE_LIST, DEFAULT_SOURCE_LIST))
    if isinstance(src, str):
        source_list = [s.strip() for s in src.split(",") if s.strip()]
    else:
        source_list = list(src)

    entity = Control4MediaPlayer(
        name=name,
        host=host,
        port=port,
        channel=channel,
        on_volume=on_volume,
        poll_external=poll_external,
        poll_interval=poll_interval,
        source_list=source_list,
        unique_id=entry.unique_id or f"{host}:{port}:ch{channel}",
    )
    async_add_entities([entity])


class Control4MediaPlayer(MediaPlayerEntity):
    _attr_should_poll = False
    _attr_icon = "mdi:speaker"
    _attr_supported_features = SUPPORT_C4
    _attr_has_entity_name = False  # we pass a full name

    def __init__(
        self,
        name: str,
        host: str,
        port: int,
        channel: int,
        on_volume: int,
        poll_external: bool,
        poll_interval: int,
        source_list: list[str],
        unique_id: str,
    ):
        self._name = name
        self._state = STATE_OFF
        self._muted = False

        self._source_list = source_list or DEFAULT_SOURCE_LIST
        self._source = self._source_list[0]

        self._on_volume = max(0.0, min(1.0, float(on_volume) / 100.0))
        self._mute_volume = self._on_volume

        self._poll_external = bool(poll_external)
        self._poll_interval = max(1, min(int(poll_interval), 300))
        self._poll_unsub = None

        self._amp = control4AmpChannel(host, port, channel)
        self._channel = channel

        # When polling is enabled, avoid immediately overriding optimistic state right after
        # a local on/off command (some controllers report the previous state for a moment).
        self._last_command_ts = 0.0

        # ---- Stable unique ID per zone ----
        self._attr_unique_id = unique_id

        # Group zones per amp (device)
        self._device_identifier = f"{host}:{port}"

    
    async def async_update(self):
        """Poll Control4 for the channel output so HA reflects external on/off changes.

        Note: Some Control4 controllers may briefly report the previous output right after
        an on/off command. We keep the optimistic HA state for a short grace period to
        avoid flipping back immediately.
        """
        if not self._poll_external:
            return

        # Grace period after local commands (seconds)
        if monotonic() - getattr(self, "_last_command_ts", 0.0) < 1.5:
            return

        try:
            resp = send_udp_command(
                f"c4.amp.out 0{self._channel}",
                self._amp.host,
                self._amp.port,
            )
        except Exception as err:  # keep entity available even if polling fails
            _LOGGER.debug("Control4 poll failed for %s: %s", self._name, err)
            return

        if resp is None:
            return

        resp_s = str(resp).strip()
        if not resp_s:
            return

                # Extract the channel output byte from the response. Some controllers
        # append extra tokens (e.g. 'OK'), so we can't rely on the last token.
        m = re.search(r"\bc4\.amp\.out\b\s+0?\d+\s+([0-9A-Fa-f]{2})\b", resp_s)
        if not m:
            return
        src = m.group(1).strip()


        # Off is typically "00"
        if src in ("00", "0", "000"):
            self._state = STATE_OFF
            return

        self._state = STATE_ON

        # Best-effort: map numeric source back to the configured source_list
        try:
            src_i = int(src, 16) if src.lower().startswith("0x") else int(src)
        except ValueError:
            try:
                src_i = int(src, 16)
            except ValueError:
                return

        if src_i > 0 and src_i <= len(self._source_list):
            self._source = self._source_list[src_i - 1]


# ---- Device registry card ----
    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_identifier)},
            "manufacturer": "Control4",
            "name": f"Control4 Matrix Amp ({self._device_identifier})",
            "model": "Matrix Amplifier",
        }
    async def async_added_to_hass(self) -> None:
        """Set up periodic polling (optional)."""
        await super().async_added_to_hass()
        if not self._poll_external:
            return

        async def _poll(_now) -> None:
            # Run async_update() then write state
            await self.async_update_ha_state(True)

        self._poll_unsub = async_track_time_interval(
            self.hass, _poll, timedelta(seconds=self._poll_interval)
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up polling subscription."""
        if self._poll_unsub:
            self._poll_unsub()
            self._poll_unsub = None
        await super().async_will_remove_from_hass()

    # ---- Entity properties ----
    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def source(self):
        return self._source

    @property
    def source_list(self):
        return self._source_list

    @property
    def is_volume_muted(self):
        return self._muted

    @property
    def volume_level(self):
        # control4AmpChannel should expose current 0..1 level
        return self._amp.volume

    # ---- Commands ----
    async def async_turn_on(self):
        self._amp.volume = self._on_volume
        self._amp.turn_on()
        self._last_command_ts = monotonic()
        self._state = STATE_ON
        self.async_write_ha_state()

    async def async_turn_off(self):
        self._amp.volume = self._on_volume
        self._amp.turn_off()
        self._last_command_ts = monotonic()
        self._state = STATE_OFF
        self.async_write_ha_state()

    async def async_mute_volume(self, mute: bool) -> None:
        if mute and not self._muted:
            self._muted = True
            self._mute_volume = self._amp.volume
            self._amp.volume = 0
        elif not mute and self._muted:
            self._muted = False
            self._amp.volume = self._mute_volume
        self.async_write_ha_state()

    async def async_set_volume_level(self, volume: float):
        self._amp.volume = max(0.0, min(1.0, volume))
        self.async_write_ha_state()

    async def async_volume_up(self):
        self._amp.volume = min(self._amp.volume + 0.01, 1.0)
        self.async_write_ha_state()

    async def async_volume_down(self):
        self._amp.volume = max(self._amp.volume - 0.01, 0.0)
        self.async_write_ha_state()

    async def async_select_source(self, source: str):
        if source not in self._source_list:
            return
        self._source = source
        # Control4 amps typically use 1-based source indices
        self._amp.source = self._source_list.index(source) + 1
        self.async_write_ha_state()
