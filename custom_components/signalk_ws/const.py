DOMAIN = "signalk_ws"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_SSL = "ssl"
CONF_VERIFY_SSL = "verify_ssl"
CONF_CONTEXT = "context"
CONF_VESSEL_NAME = "vessel_name"
CONF_PATH = "path"
CONF_PATHS = "paths"
CONF_SUBSCRIPTIONS = "subscriptions"
CONF_PERIOD_MS = "period_ms"
CONF_FORMAT = "format"
CONF_POLICY = "policy"
CONF_MIN_PERIOD_MS = "min_period_ms"
CONF_PRESET = "preset"

DEFAULT_PORT = 3000
DEFAULT_SSL = False
DEFAULT_VERIFY_SSL = True
DEFAULT_CONTEXT = "vessels.self"
DEFAULT_PERIOD_MS = 1000
DEFAULT_VESSEL_NAME = "Vessel"
DEFAULT_FORMAT = "delta"
DEFAULT_POLICY = "ideal"
DEFAULT_MIN_PERIOD_MS = 0

PRESET_CUSTOM = "custom"
PRESET_NAVIGATION = "navigation"
PRESET_WIND = "wind"
PRESET_DEPTH = "depth"
PRESET_BATTERIES = "batteries"
PRESET_TANKS = "tanks"

PRESET_PATHS: dict[str, list[str]] = {
    PRESET_CUSTOM: [],
    PRESET_NAVIGATION: [
        "navigation.speedOverGround",
        "navigation.courseOverGroundTrue",
        "navigation.position",
    ],
    PRESET_WIND: [
        "environment.wind.speedApparent",
        "environment.wind.angleApparent",
    ],
    PRESET_DEPTH: [
        "environment.depth.belowTransducer",
    ],
    PRESET_BATTERIES: [
        "electrical.batteries.house.voltage",
    ],
    PRESET_TANKS: [
        "tanks.fuel.0.currentLevel",
        "tanks.water.0.currentLevel",
    ],
}

DEFAULT_PATHS = (
    PRESET_PATHS[PRESET_NAVIGATION]
    + PRESET_PATHS[PRESET_WIND]
    + PRESET_PATHS[PRESET_DEPTH]
    + PRESET_PATHS[PRESET_BATTERIES]
)

HEALTH_SENSOR_CONNECTION_STATE = "connection_state"
HEALTH_SENSOR_LAST_MESSAGE = "last_message"
HEALTH_SENSOR_RECONNECT_COUNT = "reconnect_count"
HEALTH_SENSOR_LAST_ERROR = "last_error"
