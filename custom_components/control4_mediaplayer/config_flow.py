import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DOMAIN, DEFAULT_UDP_TIMEOUT


def int_to_little_endian_hex(val: int) -> str:
    """Convert an integer to a little-endian hex string for Control4."""
    if val > 65535 or val < 0:
        val = max(0, min(val, 65535))
    hex_str = f"{val:04x}"
    if val <= 255:
        return f"{val:02x}"
    return f"{hex_str[2:4]} {hex_str[0:2]}"


class Control4ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Control4 Media Player."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Register the standalone options flow handler."""
        return OptionsFlowHandler(config_entry)

    def __init__(self):
        """Initialize the config flow."""
        self.init_info = {}

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self.init_info = user_input
            return await self.async_step_zones()

        default_sources = "\n".join([f"Input {i}" for i in range(1, 9)])

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=8750): int,
                    vol.Optional(CONF_NAME, default="Matrix Amp"): str,
                    vol.Required("amp_size", default="8"): vol.In({"4": "4-Zone", "8": "8-Zone"}),
                    vol.Required("source_list", default=default_sources): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                    vol.Optional("udp_timeout", default=DEFAULT_UDP_TIMEOUT): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.25, max=2.0, step=0.25, mode=selector.NumberSelectorMode.SLIDER)
                    ),
                }
            ),
        )

    async def async_step_zones(self, user_input=None):
        """Zone naming step."""
        if user_input is not None:
            for key, zone_name in user_input.items():
                if zone_name.strip():
                    await self.hass.config_entries.flow.async_init(
                        DOMAIN,
                        context={"source": config_entries.SOURCE_IMPORT},
                        data={**self.init_info, "channel": int(key.replace("zone", "")), "zone_custom_name": zone_name},
                    )
            return self.async_abort(reason="bulk_add_success")

        fields = {
            vol.Optional(f"zone{i}", default=f"Zone {i}"): str
            for i in range(1, int(self.init_info.get("amp_size", 8)) + 1)
        }
        return self.async_show_form(step_id="zones", data_schema=vol.Schema(fields))

    async def async_step_import(self, data):
        """Create entry with v27 prefix to ensure clean registration."""
        await self.async_set_unique_id(f"v27_{data[CONF_HOST]}_ch{data['channel']}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=data["zone_custom_name"], data=data)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Standalone options flow handler with bulk copy functionality."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize with a private entry reference."""
        self._entry = config_entry
        self._preset_data = {}

    async def async_step_init(self, user_input=None):
        """Manage the settings menu."""
        return await self.async_step_zone_settings(user_input)

    async def async_step_zone_settings(self, user_input=None):
        if user_input is not None:
            if user_input.pop("return_to_main", False):
                return await self.async_step_init()

            sync_all = user_input.pop("copy_to_all", False)
            sync_timeout = user_input.pop("copy_timeout_to_all", False)
            new_data = {**self._entry.data, **user_input}
            self.hass.config_entries.async_update_entry(self._entry, data=new_data)

            if sync_all or sync_timeout:
                current_entries = self.hass.config_entries.async_entries(DOMAIN)
                for entry in current_entries:
                    if entry.entry_id != self._entry.entry_id:
                        updated_data = {**entry.data}
                        if sync_all:
                            updated_data["source_list"] = user_input.get("source_list")
                            updated_data["input_gains"] = user_input.get("input_gains", "")
                        if sync_timeout:
                            updated_data["udp_timeout"] = user_input.get("udp_timeout", DEFAULT_UDP_TIMEOUT)
                        self.hass.config_entries.async_update_entry(entry, data=updated_data)

            return self.async_create_entry(title="", data=None)

        return self.async_show_form(
            step_id="zone_settings",
            data_schema=vol.Schema(
                {
                    vol.Required("zone_custom_name", default=self._entry.data.get("zone_custom_name", "")): str,
                    vol.Required("on_volume", default=self._entry.data.get("on_volume", 50)): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=100)
                    ),
                    vol.Required("source_list", default=self._entry.data.get("source_list", "")): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                    vol.Optional(
                        "input_gains",
                        default=self._entry.data.get("input_gains") or "0\n0\n0\n0\n0\n0\n0\n0"
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                    vol.Optional("udp_timeout", default=self._entry.data.get("udp_timeout", DEFAULT_UDP_TIMEOUT)): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.25, max=2.0, step=0.25, mode=selector.NumberSelectorMode.SLIDER)
                    ),
                    vol.Optional("copy_to_all", default=False): bool,
                    vol.Optional("copy_timeout_to_all", default=False): bool,
                    vol.Optional("return_to_main", default=False): bool,
                }
            ),
        )
