"""Constants for the Smart Charging integration."""

DOMAIN = "smart_charging"

# Canonical charger states (ADR-0003 / glossary). Never add a fourth without a glossary change.
STATE_DISCONNECTED = "disconnected"
STATE_CONNECTED = "connected"
STATE_CHARGING = "charging"

# The canonical states in which commanding current is appropriate.
CHARGEABLE_STATES = (STATE_CONNECTED, STATE_CHARGING)

# Defaults
DEFAULT_NOMINAL_VOLTAGE = 230.0
DEFAULT_CONTROL_INTERVAL_S = 10

# --- Config entry DATA — entity-role mappings + state-translation only.
#     Changed only via the reconfigure flow, because remapping which entity plays
#     which role mid-cycle is safety-relevant (ADR-0005 Decision; ADR-0003). ---
CONF_CHARGER_CURRENT_ENTITY = "charger_current_entity"
CONF_CHARGER_STATUS_ENTITY = "charger_status_entity"
CONF_CONNECTED_STATES = "connected_states"  # user input: raw states meaning "connected"
CONF_CHARGING_STATES = "charging_states"  # user input: raw states meaning "charging"
CONF_STATUS_TRANSLATION = "status_translation"  # derived {raw: canonical} stored in data
CONF_NET_POWER_ENTITY = "net_power_entity"
CONF_CHARGER_POWER_ENTITY = "charger_power_entity"
CONF_GRID_VOLTAGE_ENTITY = "grid_voltage_entity"  # optional (NF4)
CONF_EV_SOC_ENTITY = "ev_soc_entity"  # optional at the factory level (RA1 extension)
CONF_SOLAR_INSTALLED = "solar_installed"  # bool, default False -- design doc §3, R18 scoped

# --- Config entry OPTIONS — thresholds/defaults + interval. "Turn-the-dial" tuning
#     values, editable anytime via Configure without re-running setup. ADR-0005 names
#     "safety margin" (the grid-safety offset) explicitly as an options value. ---
CONF_NOMINAL_VOLTAGE = "nominal_voltage"
CONF_MIN_CURRENT = "min_current"
CONF_MAX_CURRENT = "max_current"
CONF_GRID_CEILING_A = "grid_ceiling_a"
CONF_GRID_SAFETY_OFFSET_A = "grid_safety_offset_a"  # C4 safety margin below the fuse rating
CONF_DEFAULT_TARGET_CURRENT = "default_target_current"
CONF_CONTROL_INTERVAL_S = "control_interval_s"
CONF_SMOOTHING_WINDOW = "smoothing_window"
CONF_SOLAR_START_THRESHOLD_W = "solar_start_threshold_w"
CONF_SOLAR_ONLY_START_THRESHOLD_W = "solar_only_start_threshold_w"
CONF_SOLAR_HOLD_MIN = "solar_hold_min"
CONF_SOLAR_COOLDOWN_MIN = "solar_cooldown_min"
CONF_SOLAR_ONLY_STRATEGY = "solar_only_strategy"  # "round_up" | "round_down" | "round_nearest"
CONF_SOLAR_ONLY_MIDPOINT = "solar_only_midpoint"
CONF_DEFAULT_SOC_LIMIT = "default_soc_limit"

DEFAULT_GRID_SAFETY_OFFSET_A = 2.0
DEFAULT_SMOOTHING_WINDOW = 4
DEFAULT_SOLAR_START_THRESHOLD_W = 150.0
DEFAULT_SOLAR_ONLY_START_THRESHOLD_W = 1300.0
DEFAULT_SOLAR_HOLD_MIN = 5.0
DEFAULT_SOLAR_COOLDOWN_MIN = 2.0
DEFAULT_SOLAR_ONLY_STRATEGY = "round_down"
DEFAULT_SOLAR_ONLY_MIDPOINT = 0.5
DEFAULT_SOC_LIMIT = 80.0
