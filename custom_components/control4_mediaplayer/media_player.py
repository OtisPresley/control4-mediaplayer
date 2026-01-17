"""Control4 Media Player platform (config entry + YAML import)."""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import timedelta
from time import monotonic

import voluptuous as vol

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    PLATFORM_SCHEMA,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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


@dataclass(frozen=True)
class _PolledOutStatus:
    """Parsed output/source status for a channel."""

    is_on: bool
    source_index: int | None  # 1-based


_RE_OUT = re.compile(r"\bc4\.amp\.out\b\s+0?\d+\s+([0-9A-Fa-f]{2})\b")


def _parse_c4_amp_out(resp: str) -> _PolledOutStatus | None:
    """Parse `c4.amp.out` response.

    Expected to contain: `c4.amp.out 0<channel> <byte>`.
    Some devices append extra tokens (e.g. `OK`), so we locate the byte via regex.
    """
    m = _RE_OUT.search(resp)
    if not m:
        return None

    token = m.group(1).strip()
    # Off is typically 00
    if token in ("00", "0", "000"):
        return _PolledOutStatus(is_on=False, source_index=None)

    # Source is typically numeric (decimal) or hex byte.
    try:
        src_i = int(token, 16)
    except ValueError:
        return None

    if src_i <= 0:
        return _PolledOutStatus(is_on=False, source_index=None)

    return _PolledOutStatus(is_on=True, source_index=src_i)

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
    poll_external = bool(
        opts.get(CONF_POLL_EXTERNAL, data.get(CONF_POLL_EXTERNAL, DEFAULT_POLL_EXTERNAL))
    )
    poll_interval = int(
        opts.get(CONF_POLL_INTERVAL, data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))
    )
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
        coordinator=(
            _Control4OutCoordinator(
                hass=hass,
                host=host,
                port=port,
                channel=channel,
                interval_seconds=poll_interval,
            )
            if poll_external
            else None
        ),
    )

    # If external polling is enabled, start the coordinator so state can reflect
    # changes coming from a Control4 Controller/keypads.
    if entity.coordinator is not None:
        await entity.coordinator.async_config_entry_first_refresh()

    async_add_entities([entity])


class _Control4OutCoordinator(DataUpdateCoordinator[_PolledOutStatus | None]):
    """Coordinator that polls `c4.amp.out` for a single channel."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        channel: int,
        interval_seconds: int,
    ) -> None:
        self._host = host
        self._port = port
        self._channel = channel
        self._interval = max(1, min(int(interval_seconds), 300))

        super().__init__(
            hass,
            _LOGGER,
            name=f"control4_mediaplayer_out_{host}_{port}_ch{channel}",
            update_interval=timedelta(seconds=self._interval),
        )

    async def _async_update_data(self) -> _PolledOutStatus | None:
        """Fetch latest output/source byte from the amp."""

        def _query() -> _PolledOutStatus | None:
            # The current send_udp_command implementation uses a non-blocking socket,
            # so an immediate recv can miss the reply. Retry once with a short delay.
            cmd = f"c4.amp.out 0{self._channel}"
            for attempt in (0, 1):
                try:
                    resp = send_udp_command(cmd, self._host, self._port)
                except Exception:
                    resp = None

                if resp is not None:
                    resp_s = str(resp).strip()
                    parsed = _parse_c4_amp_out(resp_s) if resp_s else None
                    if parsed is not None:
                        return parsed

                if attempt == 0:
                    time.sleep(0.05)

            return None

        try:
            return await self.hass.async_add_executor_job(_query)
        except Exception as err:
            raise UpdateFailed(str(err)) from err


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
        coordinator: _Control4OutCoordinator | None,
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
        self._coordinator = coordinator
        self._unsub_coordinator = None

        self._amp = control4AmpChannel(host, port, channel)
        self._channel = channel

        # When polling is enabled, avoid immediately overriding optimistic state right after
        # a local on/off command (some controllers report the previous state for a moment).
        self._last_command_ts = 0.0

        # ---- Stable unique ID per zone ----
        self._attr_unique_id = unique_id

        # Group zones per amp (device)
        self._device_identifier = f"{host}:{port}"

    @property
    def coordinator(self) -> _Control4OutCoordinator | None:
        return self._coordinator

    def _apply_polled_status(self, status: _PolledOutStatus) -> None:
        # Grace period after local commands (seconds)
        if monotonic() - getattr(self, "_last_command_ts", 0.0) < 1.5:
            return

        if not status.is_on:
            self._state = STATE_OFF
            return

        self._state = STATE_ON
        if status.source_index and 1 <= status.source_index <= len(self._source_list):
            self._source = self._source_list[status.source_index - 1]


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
        """Subscribe to coordinator updates (optional)."""
        await super().async_added_to_hass()

        if self._coordinator is None:
            return

        # Push initial coordinator data (if any) into entity state.
        if self._coordinator.data is not None:
            self._apply_polled_status(self._coordinator.data)

        def _handle_update() -> None:
            if self._coordinator and self._coordinator.data is not None:
                self._apply_polled_status(self._coordinator.data)
                self.async_write_ha_state()

        self._unsub_coordinator = self._coordinator.async_add_listener(_handle_update)

    async def async_will_remove_from_hass(self) -> None:
        """Clean up coordinator subscription."""
        if self._unsub_coordinator:
            self._unsub_coordinator()
            self._unsub_coordinator = None
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
