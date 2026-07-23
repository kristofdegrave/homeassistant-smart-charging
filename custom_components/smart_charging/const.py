"""Constants for the Smart Charging integration."""

from .modes._amp_step import ROUND_DOWN

DOMAIN = "smart_charging"

# Domain events (ADR-0011). Past-tense PascalCase payload, snake_case HA event type.
EVENT_ACTIVE_SOC_LIMIT_CHANGED = "smart_charging_active_soc_limit_changed"

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
MODE_CAPTAR = "Captar"

# Profile names (select.profile options; also the coordinator's active_profile values, R16).
PROFILE_MANUAL = "Manual"
PROFILE_AUTO = "Auto"

# Departure-time entity id-suffixes (time.py platform; unique_id/translation_key building
# blocks, R14). Day-of-week suffixes double as Python's own Monday-first ordering.
DAY_MON = "mon"
DAY_TUE = "tue"
DAY_WED = "wed"
DAY_THU = "thu"
DAY_FRI = "fri"
DAY_SAT = "sat"
DAY_SUN = "sun"
DEPARTURE_OVERRIDE_HOLIDAY = "holiday"
DEPARTURE_OVERRIDE_HOME_DAY = "home_day"

# Adapter role keys (the coordinator's/factory's per-role dict; RA1 extension for ROLE_EV_SOC).
ROLE_EV_SOC = "ev_soc"
ROLE_CHARGER_CURRENT = "charger_current"
ROLE_CHARGER_STATUS = "charger_status"
ROLE_NET_POWER = "net_power"
ROLE_CHARGER_POWER = "charger_power"
ROLE_GRID_VOLTAGE = "grid_voltage"
# RA1 extension (Task 2.1, R15): sensed EV battery capacity, optional at the factory level.
ROLE_EV_BATTERY_CAPACITY = "ev_battery_capacity"
# RA2 (Task 2.1, R14): external departure-deadline override, optional at the factory level.
ROLE_DEPARTURE_EXTERNAL = "departure_external"
# RA2 (Task 2.1, R9/R13): external home-day-flag source, optional at the factory level.
ROLE_HOME_DAY_EXTERNAL = "home_day_external"
# RA2 (Task 2.1, R9): next-day solar forecast, required only when CONF_SOLAR_INSTALLED.
ROLE_SOLAR_FORECAST = "solar_forecast"

# Defaults
DEFAULT_NOMINAL_VOLTAGE = 230.0
DEFAULT_CONTROL_INTERVAL_S = 10
# E5 15-minute averaging window (design doc Sec 6.4), shared by coordinator.py's own fallback
# and __init__.py's setup-time CONF_PEAK_WINDOW_SIZE derivation so the two can't drift apart.
PEAK_WINDOW_SECONDS = 900

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
CONF_CAPTAR_AVAILABLE = "captar_available"  # bool, default True -- design doc §3, R18 scoped (#215)
# optional at the factory level (NF3) -- design doc §3, R15
CONF_EV_BATTERY_CAPACITY_ENTITY = "ev_battery_capacity_entity"
# optional at the factory level (NF3) -- design doc §3, R14
CONF_DEPARTURE_EXTERNAL_ENTITY = "departure_external_entity"
# optional at the factory level (NF3) -- design doc §3, R9/R13
CONF_HOME_DAY_EXTERNAL_ENTITY = "home_day_external_entity"
# required only when CONF_SOLAR_INSTALLED (R9 needs it) -- design doc §3
CONF_SOLAR_FORECAST_ENTITY = "solar_forecast_entity"

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
CONF_PEAK_WINDOW_SIZE = "peak_window_size"  # E5 15-min window sample count, derived at setup
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
CONF_SAFETY_MARGIN_W = "safety_margin_w"  # Captar peak-protection margin (design doc §3, E5)
CONF_MAX_PEAK_KW = "max_peak_kw"  # Captar billing-protection peak limit (design doc §3, E5)
CONF_PEAK_GRACE_MIN = "peak_grace_min"  # Captar grace period before peak enforcement (design §3)
CONF_CAPTAR_COOLDOWN_MIN = "captar_cooldown_min"  # Captar mode cooldown duration (design doc §3)
CONF_POWER_RESPECT_PEAK = "power_respect_peak"  # R17 opt-out: Power mode honors the peak limit
CONF_EV_BATTERY_CAPACITY_KWH = "ev_battery_capacity_kwh"  # R15 required-current formula input
CONF_MAX_SOLAR_SOC = "max_solar_soc"  # R8 solar step-up ceiling
CONF_SOLAR_STEP_PP = "solar_step_pp"  # R8 solar step-up step size
CONF_SOLAR_STEP_THRESHOLD_PP = "solar_step_threshold_pp"  # R8 solar step-up trigger gap
CONF_SOLAR_RESERVE_SOC = "solar_reserve_soc"  # R9 overnight solar-reserve cap (runtime, R7 row 1)
CONF_SOLAR_FORECAST_THRESHOLD_KWH = "solar_forecast_threshold_kwh"  # R9 solar-reserve forecast gate

DEFAULT_GRID_SAFETY_OFFSET_A = 2.0
DEFAULT_SMOOTHING_WINDOW = 4
DEFAULT_SOLAR_START_THRESHOLD_W = 150.0
DEFAULT_SOLAR_ONLY_START_THRESHOLD_W = 1300.0
DEFAULT_SOLAR_HOLD_MIN = 5.0
DEFAULT_SOLAR_COOLDOWN_MIN = 2.0
DEFAULT_SOLAR_ONLY_STRATEGY = ROUND_DOWN
DEFAULT_SOLAR_ONLY_MIDPOINT = 0.5  # fraction 0-1 (R2 round_nearest), not a percent
DEFAULT_SOC_LIMIT = 80.0  # percent, 50-100 (R6) -- range enforced by config_flow/number entity
DEFAULT_CAPTAR_AVAILABLE = True
DEFAULT_SAFETY_MARGIN_W = 250.0
DEFAULT_MAX_PEAK_KW = 4.0
DEFAULT_PEAK_GRACE_MIN = 2.0
DEFAULT_CAPTAR_COOLDOWN_MIN = 10.0
DEFAULT_POWER_RESPECT_PEAK = True
DEFAULT_EV_BATTERY_CAPACITY_KWH = 75.0
DEFAULT_MAX_SOLAR_SOC = 100.0
DEFAULT_SOLAR_STEP_PP = 5.0
DEFAULT_SOLAR_STEP_THRESHOLD_PP = 2.0
DEFAULT_SOLAR_RESERVE_SOC = 60.0
DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH = 12.0
