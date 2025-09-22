from __future__ import annotations

from typing import Any, Set
import voluptuous as vol
import yaml  # for Advanced Editor YAML/JSON parsing

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector  # numeric + text selectors

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_CHANNEL,
    CONF_ON_VOLUME,
    CONF_SOURCE_LIST,
    DEFAULT_PORT,
    DEFAULT_VOLUME,
    DEFAULT_SOURCE_LIST,
)

# Human-facing labels used in this flow (no translations)
F_NAME = "Name"
F_HOST = "Host"
F_PORT = "Port"
F_AMP_SIZE = "Amplifier Size"
F_CHANNEL = "Channel"
F_ON_VOLUME = "On Volume"
F_SOURCE_LIST = "Source List (comma or newline separated)"
F_BULK_ADD = "Add Zones in Bulk"
F_NAME_PREFIX = "Zone Prefix (bulk)"
F_ZONE_COUNT = "Zone Count (bulk)"

# Options flow labels
F_ADVANCED_EDITOR = "Use Advanced Editor"
F_APPLY_TO_ALL = "Apply to All Zones on This Device"
F_SOURCE_LIST_YAML = "Source List (YAML/JSON)"

AMP_SIZE_CHOICES = [4, 8]


# ----------------------- helpers -----------------------
def _normalize_sources(src) -> list[str]:
    """Turn comma/newline separated string or list into a clean list of sources."""
    if src is None:
        return list(DEFAULT_SOURCE_LIST)
    if isinstance(src, (list, tuple)):
        return [str(s).strip() for s in src if str(s).strip()]
    if isinstance(src, str):
        parts: list[str] = []
        blob = src.replace("\r", "\n")
        for line in blob.split("\n"):
            for piece in line.split(","):
                p = piece.strip()
                if p:
                    parts.append(p)
        return parts or list(DEFAULT_SOURCE_LIST)
    return list(DEFAULT_SOURCE_LIST)


def _parse_sources_advanced(text: str) -> list[str]:
    """
    Accept YAML/JSON from the advanced textarea.
    - Prefer yaml.safe_load (also parses JSON).
    - Accept string -> fallback to normal splitter.
    - Ensure list[str] result.
    """
    try:
        data = yaml.safe_load(text) if text is not None else None
    except Exception:
        # raise to caller to show a friendly error and keep the textarea
        raise

    if data is None:
        return []

    if isinstance(data, list):
        return [str(x).strip() for x in data if str(x).strip()]

    if isinstance(data, str):
        return _normalize_sources(data)

    # Unexpected type (e.g., dict/int) → treat as parse error
    raise ValueError("YAML/JSON must be a list of strings or a string.")


def _dump_sources_as_yaml_list(sources: list[str]) -> str:
    """Display default in advanced editor as a clean YAML list (no quotes, one per line)."""
    if not sources:
        return "- "
    return "\n".join(f"- {s}" for s in sources)


def _existing_channels(flow: config_entries.ConfigFlow, host: str, port: int) -> Set[int]:
    """All configured channels for the given amp (Host+Port)."""
    return {
        int(e.data.get(CONF_CHANNEL))
        for e in flow._async_current_entries()  # type: ignore[attr-defined]
        if e.data.get(CONF_HOST) == host and int(e.data.get(CONF_PORT, DEFAULT_PORT)) == port
    }


def _next_available(existing: Set[int], amp_size: int) -> int | None:
    for ch in range(1, amp_size + 1):
        if ch not in existing:
            return ch
    return None


def _default_sources_for_size(size: int, inherit: list[str] | None) -> list[str]:
    """Use inherited list if present; otherwise 1..N based on amp size."""
    if inherit:
        return inherit
    n = max(1, int(size))
    return [str(i) for i in range(1, n + 1)]


class Control4ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        # Small UI state to enable "soft refresh" of the same step.
        self._pending: dict[str, Any] = {}

    # ---- reactive schema (plain Voluptuous; selectors only for numeric pickers) ----
    def _base_user_schema(
        self,
        *,
        defaults: dict[str, Any],
        amp_max: int,
        show_bulk: bool,
        zone_max: int | None = None,
    ) -> vol.Schema:
        amp_max = max(1, int(amp_max))
        zone_max = amp_max if zone_max is None else max(1, int(zone_max))

        ch_default = min(max(int(defaults.get(F_CHANNEL, 1)), 1), amp_max)
        cnt_default = min(max(int(defaults.get(F_ZONE_COUNT, 1)), 1), zone_max)

        fields: dict[Any, Any] = {
            vol.Required(F_NAME, default=str(defaults.get(F_NAME, ""))): str,
            vol.Required(F_HOST, default=str(defaults.get(F_HOST, ""))): str,
            vol.Optional(F_PORT, default=int(defaults.get(F_PORT, DEFAULT_PORT))): vol.All(
                int, vol.Range(min=1, max=65535)
            ),
            vol.Optional(F_AMP_SIZE, default=int(defaults.get(F_AMP_SIZE, 8))): vol.In(AMP_SIZE_CHOICES),
            # Required channel selector bounded by amp size
            vol.Required(F_CHANNEL, default=ch_default): selector.selector(
                {"number": {"min": 1, "max": amp_max, "mode": "box"}}
            ),
            vol.Optional(F_ON_VOLUME, default=int(defaults.get(F_ON_VOLUME, DEFAULT_VOLUME))): vol.All(
                int, vol.Range(min=0, max=100)
            ),
            vol.Optional(F_SOURCE_LIST, default=str(defaults.get(F_SOURCE_LIST, ",".join(DEFAULT_SOURCE_LIST)))): str,
            vol.Optional(F_BULK_ADD, default=bool(defaults.get(F_BULK_ADD, False))): bool,
        }

        if show_bulk:
            fields[vol.Optional(F_NAME_PREFIX, default=str(defaults.get(F_NAME_PREFIX, "")))] = str
            # Zone Count selector bounded by remaining capacity (zone_max)
            fields[vol.Optional(F_ZONE_COUNT, default=cnt_default)] = selector.selector(
                {"number": {"min": 1, "max": zone_max, "mode": "box"}}
            )

        return vol.Schema(fields)

    # ------------------------------ steps ------------------------------
    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        # Initial render: assume 8-zone, bulk OFF.
        if user_input is None:
            amp_max = 8
            self._pending["_amp_max"] = amp_max
            self._pending["_show_bulk"] = False
            src_default = ",".join(_default_sources_for_size(amp_max, None))
            return self.async_show_form(
                step_id="user",
                data_schema=self._base_user_schema(
                    defaults={
                        F_PORT: DEFAULT_PORT,
                        F_AMP_SIZE: amp_max,
                        F_ON_VOLUME: DEFAULT_VOLUME,
                        F_SOURCE_LIST: src_default,
                        F_CHANNEL: 1,
                        F_ZONE_COUNT: 1,
                        F_BULK_ADD: False,
                    },
                    amp_max=amp_max,
                    show_bulk=False,
                    zone_max=amp_max,
                ),
            )

        # Read inputs
        name = str(user_input.get(F_NAME, "")).strip()
        host = str(user_input.get(F_HOST, "")).strip()
        port = int(user_input.get(F_PORT, DEFAULT_PORT))
        amp_size = int(user_input.get(F_AMP_SIZE, 8))
        channel = int(user_input.get(F_CHANNEL, 1))
        on_volume = int(user_input.get(F_ON_VOLUME, DEFAULT_VOLUME))
        bulk = bool(user_input.get(F_BULK_ADD, False))
        prefix = str(user_input.get(F_NAME_PREFIX, "")).strip()

        # Inherit sources from sibling (same Host/Port) if present
        inherited = None
        for e in self._async_current_entries():
            if e.data.get(CONF_HOST) == host and int(e.data.get(CONF_PORT, DEFAULT_PORT)) == port:
                inherited = _normalize_sources(
                    e.options.get(CONF_SOURCE_LIST, e.data.get(CONF_SOURCE_LIST, DEFAULT_SOURCE_LIST))
                )
                break

        # Auto sources to amp size unless user typed something
        auto_sources = _default_sources_for_size(amp_size, inherited)
        source_list = _normalize_sources(user_input.get(F_SOURCE_LIST, ",".join(auto_sources)))

        # Compute existing & zone_max (remaining free channels from selected start channel)
        if host and port:
            existing = _existing_channels(self, host, port)
        else:
            existing = set()

        start_ch = min(max(channel, 1), amp_size)
        if host and port:
            remaining_from_start = [ch for ch in range(start_ch, amp_size + 1) if ch not in existing]
            zone_max = max(1, len(remaining_from_start)) if bulk else amp_size
        else:
            zone_max = amp_size

        # If user turned on Bulk and all zones are already configured → abort now (no re-render)
        next_avail = _next_available(existing, amp_size)
        if bulk and host and port and next_avail is None:
            return self.async_abort(reason=f"All zones are already configured for {host}:{port}.")

        # --- Soft refresh ONLY when amp size or bulk toggle changed ---
        last_amp = int(self._pending.get("_amp_max", 8))
        last_bulk = bool(self._pending.get("_show_bulk", False))
        if (last_amp != amp_size) or (last_bulk != bulk):
            self._pending["_amp_max"] = amp_size
            self._pending["_show_bulk"] = bulk

            # On re-render, set Channel to the first available channel (if known for this host:port)
            render_ch = next_avail if (host and port and next_avail is not None) else start_ch
            if host and port:
                remaining_from_render = [ch for ch in range(render_ch, amp_size + 1) if ch not in existing]
                render_zone_max = max(1, len(remaining_from_render)) if bulk else amp_size
            else:
                render_zone_max = amp_size

            return self.async_show_form(
                step_id="user",
                data_schema=self._base_user_schema(
                    defaults={
                        F_NAME: name,
                        F_HOST: host,
                        F_PORT: port,
                        F_AMP_SIZE: amp_size,
                        F_CHANNEL: render_ch,  # <-- jump to first available on re-render
                        F_ON_VOLUME: on_volume,
                        F_SOURCE_LIST: ",".join(auto_sources),
                        F_BULK_ADD: bulk,
                        F_NAME_PREFIX: prefix,
                        F_ZONE_COUNT: min(max(int(user_input.get(F_ZONE_COUNT, 1)), 1), render_zone_max),
                    },
                    amp_max=amp_size,
                    show_bulk=bulk,
                    zone_max=render_zone_max,
                ),
                errors={"base": f"Form updated for a {amp_size}-zone amplifier."} if last_amp != amp_size else None,
            )

        # Trim source list to amp size (just in case)
        if len(source_list) > amp_size:
            source_list = source_list[:amp_size]

        # Availability (recompute if empty host/port was provided before)
        existing = _existing_channels(self, host, port) if host and port else set()

        # Channel range validation against amp size
        if channel < 1 or channel > amp_size:
            clamped = min(max(channel, 1), amp_size)
            rem = [ch for ch in range(clamped, amp_size + 1) if ch not in existing]
            zmax = max(1, len(rem)) if bulk else amp_size
            return self.async_show_form(
                step_id="user",
                data_schema=self._base_user_schema(
                    defaults={
                        F_NAME: name,
                        F_HOST: host,
                        F_PORT: port,
                        F_AMP_SIZE: amp_size,
                        F_CHANNEL: clamped,
                        F_ON_VOLUME: on_volume,
                        F_SOURCE_LIST: ",".join(source_list),
                        F_BULK_ADD: bulk,
                        F_NAME_PREFIX: prefix,
                        F_ZONE_COUNT: min(max(int(user_input.get(F_ZONE_COUNT, 1)), 1), zmax),
                    },
                    amp_max=amp_size,
                    show_bulk=bulk,
                    zone_max=zmax,
                ),
                errors={"base": f"Channel must be between 1 and {amp_size}."},
            )

        # All configured → simple popup (include host:port if available)
        if next_avail is None:
            where = f"{host}:{port}" if host and port else "this amplifier"
            return self.async_abort(reason=f"All zones are already configured for {where}.")

        # Chosen channel already used → keep form with suggestion (now includes host:port)
        if channel in existing:
            remaining = [ch for ch in range(next_avail, amp_size + 1) if ch not in existing]
            zmax = max(1, len(remaining)) if bulk else amp_size
            where = f"{host}:{port}" if host and port else "this amplifier"
            return self.async_show_form(
                step_id="user",
                data_schema=self._base_user_schema(
                    defaults={
                        F_NAME: name,
                        F_HOST: host,
                        F_PORT: port,
                        F_AMP_SIZE: amp_size,
                        F_CHANNEL: next_avail,  # suggest first available
                        F_ON_VOLUME: on_volume,
                        F_SOURCE_LIST: ",".join(source_list),
                        F_BULK_ADD: bulk,
                        F_NAME_PREFIX: prefix,
                        F_ZONE_COUNT: min(max(len(remaining), 1), zmax),
                    },
                    amp_max=amp_size,
                    show_bulk=bulk,
                    zone_max=zmax,
                ),
                errors={"base": f"Channel {channel} is already configured on {where}. Next available is {next_avail}."},
            )

        # Bulk path → go directly to per-channel names
        if bulk:
            remaining = [ch for ch in range(channel, amp_size + 1) if ch not in existing]
            max_count = len(remaining)
            count_req = int(user_input.get(F_ZONE_COUNT, max_count))
            count = max(1, min(count_req, max_count))
            targets = remaining[:count]

            self._pending = {
                "targets": targets,
                "names_prefix": prefix,
                CONF_HOST: host,
                CONF_PORT: port,
                CONF_ON_VOLUME: on_volume,
                CONF_SOURCE_LIST: source_list,
            }
            return await self.async_step_user_bulk_names()

        # Single-zone creation
        unique = f"{host}:{port}:ch{channel}"
        await self.async_set_unique_id(unique)

        data = {
            "name": name,
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_CHANNEL: channel,
            CONF_ON_VOLUME: on_volume,
            CONF_SOURCE_LIST: source_list,
        }
        title = f"{name} ({host}:{port} ch{channel})"
        return self.async_create_entry(title=title, data=data)

    async def async_step_user_bulk_names(self, user_input=None):
        """One screen for per-channel names (after Add form)."""
        host = self._pending[CONF_HOST]
        port = int(self._pending.get(CONF_PORT, DEFAULT_PORT))
        on_volume = int(self._pending.get(CONF_ON_VOLUME, DEFAULT_VOLUME))
        source_list = _normalize_sources(self._pending.get(CONF_SOURCE_LIST, DEFAULT_SOURCE_LIST))
        channels: list[int] = list(self._pending["targets"])
        prefix = str(self._pending.get("names_prefix", "")).strip()

        def _field_key(ch: int) -> str:
            return f"Name (ch {ch})"

        if user_input is None:
            schema_dict: dict[Any, Any] = {}
            for ch in channels:
                default_name = f"{prefix} {ch}".strip() if prefix else f"Zone {ch}"
                schema_dict[vol.Required(_field_key(ch), default=default_name)] = str
            return self.async_show_form(step_id="user_bulk_names", data_schema=vol.Schema(schema_dict))

        names: dict[int, str] = {}
        for ch in channels:
            nm = str(user_input.get(_field_key(ch), "")).strip() or f"Zone {ch}"
            names[ch] = nm

        # Spawn flows for the rest
        for ch in channels[1:]:
            entry_data = {
                "name": names[ch],
                CONF_HOST: host,
                CONF_PORT: port,
                CONF_CHANNEL: ch,
                CONF_ON_VOLUME: on_volume,
                CONF_SOURCE_LIST: source_list,
            }
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"}, data=entry_data)
            )

        # Create first in this flow
        first_ch = channels[0]
        unique = f"{host}:{port}:ch{first_ch}"
        await self.async_set_unique_id(unique)

        first_data = {
            "name": names[first_ch],
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_CHANNEL: first_ch,
            CONF_ON_VOLUME: on_volume,
            CONF_SOURCE_LIST: source_list,
        }
        title = f"{names[first_ch]} ({host}:{port} ch{first_ch})"
        return self.async_create_entry(title=title, data=first_data)

    async def async_step_import(self, user_input: dict[str, Any]):
        """Import a single zone from configuration.yaml into a config entry."""
        # Map YAML keys (CONF_*) to the same structure used by entries/options
        name = str(user_input.get("name", "")).strip()
        host = str(user_input.get(CONF_HOST, "")).strip()
        port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
        channel = int(user_input.get(CONF_CHANNEL, 1))
        on_volume = int(user_input.get(CONF_ON_VOLUME, DEFAULT_VOLUME))
        source_list = _normalize_sources(user_input.get(CONF_SOURCE_LIST, DEFAULT_SOURCE_LIST))
    
        # Infer a reasonable amp size bound (keep it simple: cap by common sizes)
        # If an explicit amp size was provided in YAML, respect it; otherwise assume 8.
        amp_size_yaml = user_input.get("amp_size") or user_input.get(F_AMP_SIZE)
        try:
            amp_size = int(amp_size_yaml) if amp_size_yaml is not None else 8
        except Exception:
            amp_size = 8
        amp_size = amp_size if amp_size in AMP_SIZE_CHOICES else 8
    
        # Clamp/validate channel against amp size
        if channel < 1 or channel > amp_size:
            channel = max(1, min(channel, amp_size))
    
        # Prevent duplicates on the same amp/channel
        existing = _existing_channels(self, host, port) if host and port else set()
        if channel in existing:
            return self.async_abort(reason="already_configured")
    
        # Unique ID: host:port:chN
        unique = f"{host}:{port}:ch{channel}"
        await self.async_set_unique_id(unique)
        # Abort if this exact unique_id already exists
        self._abort_if_unique_id_configured()
    
        # Finalize entry payload
        if not name:
            name = f"Zone {channel}"
    
        data = {
            "name": name,
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_CHANNEL: channel,
            CONF_ON_VOLUME: on_volume,
            CONF_SOURCE_LIST: source_list,
        }
        title = f"{name} ({host}:{port} ch{channel})"
        return self.async_create_entry(title=title, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return Control4OptionsFlow(config_entry)


class Control4OptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry
        self._pending: dict[str, Any] = {}

    async def async_step_init(self, user_input=None):
        data = self.entry.options or self.entry.data

        if user_input is not None:
            if user_input.get(F_ADVANCED_EDITOR):
                # Stash simple fields; Source List is handled in advanced step
                self._pending[F_ON_VOLUME] = int(user_input.get(F_ON_VOLUME, data.get(CONF_ON_VOLUME, DEFAULT_VOLUME)))
                self._pending[F_APPLY_TO_ALL] = bool(user_input.get(F_APPLY_TO_ALL, True))
                return await self.async_step_advanced()

            on_volume = int(user_input.get(F_ON_VOLUME, data.get(CONF_ON_VOLUME, DEFAULT_VOLUME)))
            source_list = _normalize_sources(user_input.get(F_SOURCE_LIST, data.get(CONF_SOURCE_LIST, DEFAULT_SOURCE_LIST)))
            apply_to_all = bool(user_input.get(F_APPLY_TO_ALL, True))
            return await self._save_and_broadcast(on_volume, source_list, apply_to_all)

        schema = vol.Schema(
            {
                vol.Required(F_ON_VOLUME, default=data.get(CONF_ON_VOLUME, DEFAULT_VOLUME)): vol.All(
                    int, vol.Range(min=0, max=100)
                ),
                vol.Optional(
                    F_SOURCE_LIST, default=",".join(_normalize_sources(data.get(CONF_SOURCE_LIST, DEFAULT_SOURCE_LIST)))
                ): str,
                vol.Optional(F_ADVANCED_EDITOR, default=False): bool,
                vol.Optional(F_APPLY_TO_ALL, default=True): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_advanced(self, user_input=None):
        data = self.entry.options or self.entry.data

        if user_input is not None:
            raw_text = user_input.get(
                F_SOURCE_LIST_YAML,
                _dump_sources_as_yaml_list(_normalize_sources(data.get(CONF_SOURCE_LIST, DEFAULT_SOURCE_LIST))),
            )
            try:
                source_list = _parse_sources_advanced(raw_text)
            except Exception:
                # Re-render the advanced editor with a friendly parse error
                example = "- HC800-1\n- HC800-2\n- Server"
                schema = vol.Schema(
                    {
                        vol.Required(
                            F_SOURCE_LIST_YAML,
                            default=str(raw_text) if raw_text is not None else example,
                        ): selector.selector({"text": {"multiline": True}})
                    }
                )
                return self.async_show_form(
                    step_id="advanced",
                    data_schema=schema,
                    errors={"base": "Could not parse YAML/JSON. Please enter a list, e.g.\n" + example},
                )

            on_volume = int(self._pending.get(F_ON_VOLUME, data.get(CONF_ON_VOLUME, DEFAULT_VOLUME)))
            apply_to_all = bool(user_input.get(F_APPLY_TO_ALL, self._pending.get(F_APPLY_TO_ALL, True)))
            return await self._save_and_broadcast(on_volume, source_list, apply_to_all)

        # Initial render of advanced editor: show current list as YAML
        current_sources = _normalize_sources(data.get(CONF_SOURCE_LIST, DEFAULT_SOURCE_LIST))
        default_yaml = _dump_sources_as_yaml_list(current_sources)
        schema = vol.Schema(
            {
                vol.Required(F_SOURCE_LIST_YAML, default=default_yaml): selector.selector({"text": {"multiline": True}}),
                vol.Optional(F_APPLY_TO_ALL, default=self._pending.get(F_APPLY_TO_ALL, True)): bool,
            }
        )
        return self.async_show_form(step_id="advanced", data_schema=schema)

    async def _save_and_broadcast(self, on_volume: int, source_list: list[str], apply_to_all: bool):
        new_options = {CONF_ON_VOLUME: int(on_volume), CONF_SOURCE_LIST: list(source_list)}

        if apply_to_all:
            host = self.entry.data.get(CONF_HOST)
            port = int(self.entry.data.get(CONF_PORT, DEFAULT_PORT))
            for e in self.hass.config_entries.async_entries(DOMAIN):
                if e.entry_id == self.entry.entry_id:
                    continue
                if e.data.get(CONF_HOST) == host and int(e.data.get(CONF_PORT, DEFAULT_PORT)) == port:
                    opts = dict(e.options) if e.options else {}
                    opts[CONF_SOURCE_LIST] = list(source_list)
                    self.hass.config_entries.async_update_entry(e, options=opts)

        return self.async_create_entry(title="", data=new_options)
