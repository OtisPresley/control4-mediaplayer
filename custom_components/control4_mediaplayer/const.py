DOMAIN = "control4_mediaplayer"

CONF_ON_VOLUME = "on_volume"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_CHANNEL = "channel"
CONF_SOURCE_LIST = "source_list"

DEFAULT_PORT = 8750
DEFAULT_VOLUME = 5                 # percent
DEFAULT_SOURCE_LIST = ["1", "2", "3", "4"]
DEFAULT_UDP_TIMEOUT = 2.0

PREFIX = "v27"

def get_unique_id(host: str, channel: int, suffix: str = None) -> str:
    """Generate a consistent standardized unique ID across platforms."""
    if suffix:
        return f"{PREFIX}_{host}_ch{channel}_{suffix}"
    return f"{PREFIX}_{host}_ch{channel}"

def get_entity_name(zone_custom_name: str, name_suffix: str = None) -> str:
    """Generate a consistent standardized entity display name across platforms."""
    if name_suffix:
        return f"{zone_custom_name} {name_suffix}"
    return zone_custom_name

