"""Constants for the Smart Charging integration."""

from .modes._amp_step import ROUND_DOWN

DOMAIN = "smart_charging"

# Canonical charger states (ADR-0003 / glossary). Never add a fourth without a glossary change.
STATE_DISCONNECTED = "disconnected"
STATE_CONNECTED = "connected"
STATE_CHARGING = "charging"

# The canonical states in which commanding current is appropriate.
CHARGEABLE_STATES = (STATE_CONNECTED, STATE_CHARGING)

# Charging mode names (select.mode options; also the coordinator's active_mode values).
MODE_OFF = "Off"
MODE_POWER = "Power"
MODE_SOLAR = "Solar"
MODE_SOLAR_ONLY = "SolarOnly"

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
CONF_SMOOTHING_WINDOW = "smoothing_window"  # R10 rolling-window sample count
CONF_SOLAR_START_THRESHOLD_W = "solar_start_threshold_w"  # R1 (Solar)
CONF_SOLAR_ONLY_START_THRESHOLD_W = "solar_only_start_threshold_w"  # R2 (SolarOnly)
CONF_SOLAR_HOLD_MIN = "solar_hold_min"  # R1 post-surplus hold duration
CONF_SOLAR_COOLDOWN_MIN = "solar_cooldown_min"  # R1/R2 cooldown duration
CONF_SOLAR_ONLY_STRATEGY = "solar_only_strategy"  # R2: "round_up" | "round_down" | "round_nearest"
CONF_SOLAR_ONLY_MIDPOINT = "solar_only_midpoint"  # R2 round_nearest fractional threshold
# Config-flow-time default for the "Default charge limit" number entity's initial value
# (SocLimitOverrideNumber). The two are kept independently overridable (R6): this is the
# config-time default; the entity is the runtime value that solar step-up/reserve-cap (R7)
# sit on top of.
CONF_DEFAULT_SOC_LIMIT = "default_soc_limit"

DEFAULT_GRID_SAFETY_OFFSET_A = 2.0
DEFAULT_SMOOTHING_WINDOW = 4
DEFAULT_SOLAR_START_THRESHOLD_W = 150.0
DEFAULT_SOLAR_ONLY_START_THRESHOLD_W = 1300.0
DEFAULT_SOLAR_HOLD_MIN = 5.0
DEFAULT_SOLAR_COOLDOWN_MIN = 2.0
DEFAULT_SOLAR_ONLY_STRATEGY = ROUND_DOWN
DEFAULT_SOLAR_ONLY_MIDPOINT = 0.5  # fraction 0-1 (R2 round_nearest), not a percent
DEFAULT_SOC_LIMIT = 80.0  # percent, 50-100 (R6) -- range enforced by config_flow/number entity
