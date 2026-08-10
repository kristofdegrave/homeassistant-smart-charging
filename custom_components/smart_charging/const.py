"""Constants for the Smart Charging integration."""

DOMAIN = "smart_charging"

# hass.data[DOMAIN][entry_id] dict keys (__init__.py's setup-time payload). DATA_COORDINATOR/
# DATA_NOTIFICATION_MANAGER are the two bare-string-shaped keys in that dict; every sibling
# key is a CONF_* constant (issue #508) -- named here so both __init__.py's writer and every
# reader (sensor.py, tests) stay in lockstep.
DATA_COORDINATOR = "coordinator"
DATA_NOTIFICATION_MANAGER = "notification_manager"
# None when CONF_VEHICLE_CHARGE_LIMIT_ENTITY is unmapped -- M2 stays uninstantiated (Task 5.1).
DATA_VEHICLE_LIMIT_MANAGER = "vehicle_limit_manager"

# Amp-step rounding strategies (R1/R2), shared by `modes/_amp_step.py`'s `round_amp_step`
# and the config flow's `vol.In(...)` validator (Task 3.2). Plain strings, not an Enum:
# `strategy` round-trips through HA config-entry storage, which needs bare str values.
# Live here (a leaf module) rather than in `modes/_amp_step.py` so that other modules --
# including `const.py` itself, for DEFAULT_SOLAR_ONLY_STRATEGY below -- can reference them
# without importing a private submodule of `modes` (issue #502).
ROUND_UP = "round_up"
ROUND_DOWN = "round_down"
ROUND_NEAREST = "round_nearest"

# Domain events (ADR-0011). Past-tense PascalCase payload, snake_case HA event type.
EVENT_ACTIVE_SOC_LIMIT_CHANGED = "smart_charging_active_soc_limit_changed"
ATTR_ACTIVE_SOC_LIMIT = "active_soc_limit"  # ActiveSocLimitChanged payload key
# R5/ADR-0011: fires every cycle resolve_required_current's `unreachable` is True (Task 5.2),
# not only on the Normal/Urgent -> Unreachable transition edge (UC05's domain-events section).
EVENT_DEADLINE_UNREACHABLE_NOTIFIED = "smart_charging_deadline_unreachable_notified"
ATTR_REQUIRED_CURRENT_A = "required_current_a"  # DeadlineUnreachableNotified payload key

# Domain events M2 fires on the HA event bus (UC09 "Domain events produced"; DDD->HA mapping). Not
# consumed by any other Manager (ADR-0011) -- observability/automation only.
EVENT_VEHICLE_CHARGE_LIMIT_SYNCED = "smart_charging_vehicle_charge_limit_synced"
EVENT_MANUAL_CHARGE_LIMIT_ADOPTED = "smart_charging_manual_charge_limit_adopted"
EVENT_VEHICLE_CHARGE_LIMIT_RESET = "smart_charging_vehicle_charge_limit_reset"
ATTR_ENTRY_ID = "entry_id"  # shared entry-scoping key across all three M2 event payloads
ATTR_LIMIT = "limit"  # M2 event payload key -- the SOC-limit value carried by the event

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

# R18: which modes each capability offers/makes available. Single source of truth for
# select.py's option-list construction and capability_gate.py's runtime R18 gate -- a mode
# gated by an existing capability is added in one place, not duplicated across both.
# BASE_CAPABLE_MODES needs no capability at all -- always available regardless of R18.
BASE_CAPABLE_MODES = (MODE_OFF, MODE_POWER)
SOLAR_CAPABLE_MODES = (MODE_SOLAR, MODE_SOLAR_ONLY)
CAPTAR_CAPABLE_MODES = (MODE_CAPTAR,)

# Profile names (select.profile options; also the coordinator's active_profile values, R16).
PROFILE_MANUAL = "Manual"
PROFILE_AUTO = "Auto"

# Charging-status sensor values (ADR-0007): Fault when the last cycle faulted, else OK.
STATUS_FAULT = "Fault"
STATUS_OK = "OK"

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

# Owned control-entity unique_id suffixes (RA3 Store, ADR-0018/0019) -- shared between each
# entity module's _attr_unique_id and store.py's read() calls, so the two sides can't drift.
OWNED_SUFFIX_MODE = "mode"
OWNED_SUFFIX_PROFILE = "profile"
OWNED_SUFFIX_TARGET_CURRENT = "target_current"
OWNED_SUFFIX_SOC_LIMIT_OVERRIDE = "soc_limit_override"
OWNED_SUFFIX_HOME_DAY = "home_day"
OWNED_SUFFIX_DEPARTURE_HOLIDAY = f"departure_{DEPARTURE_OVERRIDE_HOLIDAY}"
OWNED_SUFFIX_DEPARTURE_HOME_DAY = f"departure_{DEPARTURE_OVERRIDE_HOME_DAY}"
# Diagnostic sensor unique_id suffix (E3/M1, ADR-0011) -- not owned/writable, but resolved
# through the same Store registry lookup so a locale/rename (ADR-0013) can't silently break
# the Vehicle-Limit Manager's listener the way a hardcoded entity_id would.
OWNED_SUFFIX_ACTIVE_SOC_LIMIT = "active_soc_limit"
OWNED_SUFFIX_SOLAR_SURPLUS_W = "solar_surplus_w"
OWNED_SUFFIX_TIME_TO_FULL = "time_to_full"
OWNED_SUFFIX_PEAK_HEADROOM_A = "peak_headroom_a"
OWNED_SUFFIX_ADAPTER_READINGS = "adapter_readings"
# Monday=0 .. Sunday=6 (Python's date.weekday()), matching time.py's DAY_OF_WEEK_DEFAULTS order.
OWNED_SUFFIX_DEPARTURE_DOW = [
    f"departure_{d}" for d in (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI, DAY_SAT, DAY_SUN)
]

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
# issue #376: built unconditionally by the factory, no config_flow entry -- sun.sun is a
# core Home Assistant entity, always present once the (auto-loaded) sun integration is set up.
ROLE_SUN = "sun"
# issue #376: optional at the factory level (NF3), like the other RA2 roles -- unmapped or a
# None reading keeps the glossary's single-tariff "always active" default.
ROLE_LOW_TARIFF = "low_tariff"
# RA4 (notifications design doc §3): message dispatch + simulated action response.
# Optional at the factory level (NF3), like the other RA-role extensions above -- present
# only when the notification target is mapped.
ROLE_NOTIFICATION_TARGET = "notification_target"
# Actionable home-day prompt action ids (UC08; notifications design doc §5/§6). The values
# round-trip verbatim through HA's mobile_app_notification_action payload -- do not rename them
# independently of the design doc.
ACTION_HOMEDAY_YES = "HOMEDAY_YES"
ACTION_HOMEDAY_NO = "HOMEDAY_NO"
# RA1-VL + car_home (RA2 role, built early -- M2 is their first consumer).
ROLE_VEHICLE_CHARGE_LIMIT = "vehicle_charge_limit"
ROLE_CAR_HOME = "car_home"

# ADR-0021: adapter_readings mirrors every currently-wired *read* role's most recently read
# value; a role the coordinator (M1's own _run_cycle) never reads has no value to mirror.
# Explicit set, not a `read()` duck-type check -- ROLE_NOTIFICATION_TARGET's adapter also
# exposes read(), and ROLE_VEHICLE_CHARGE_LIMIT is read/write.
ROLES_ADAPTER_READINGS_EXCLUDED = frozenset(
    {
        ROLE_NOTIFICATION_TARGET,  # write-only: nothing reads it to display (ADR-0021's own
        # example)
        ROLE_CHARGER_CURRENT,  # write-only from M1's perspective -- _run_cycle only ever
        # .write()s it, never .read()s it
        ROLE_CAR_HOME,  # read only by VehicleLimitManager (M2), not M1's _run_cycle -- feeding
        # cross-manager reads into this cache is out of #602's scope
        ROLE_VEHICLE_CHARGE_LIMIT,  # ditto (M2)
        ROLE_HOME_DAY_EXTERNAL,  # read only by NotificationManager, not M1's _run_cycle -- ditto
    }
)

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
# optional at the factory level (NF3) -- issue #376, Auto mode-selection row 4 (R16)
CONF_LOW_TARIFF_ENTITY = "low_tariff_entity"
# RA4 role mapping (notifications design doc §3) -- required for M3 to deliver at all, though
# the factory-level role built from it stays optional (NF3) like its siblings above.
CONF_NOTIFICATION_TARGET_ENTITY = "notification_target_entity"
CONF_VEHICLE_CHARGE_LIMIT_ENTITY = "vehicle_charge_limit_entity"  # optional (UC09 precondition)
# required when vehicle_charge_limit is mapped (design §9.1)
CONF_CAR_HOME_ENTITY = "car_home_entity"

# Config-flow error codes (config_flow.py's mapping-step guards). Values must match
# strings.json/translations/en.json's config.error keys exactly (issue #508) --
# tests/test_config_flow_translations.py walks every one of these against that section.
ERROR_REQUIRED_WHEN_SOLAR_INSTALLED = "required_when_solar_installed"
ERROR_REQUIRED_WHEN_CAPTAR_AVAILABLE = "required_when_captar_available"
ERROR_REQUIRED_WHEN_VEHICLE_LIMIT_MAPPED = "required_when_vehicle_limit_mapped"

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
CONF_SOLAR_ONLY_STRATEGY = "solar_only_strategy"  # R2: ROUND_UP | ROUND_DOWN | ROUND_NEAREST
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
# UC08 evening home-day prompt options (notifications design doc §3). sc_prompt_timeout_h is
# deliberately NOT wired here -- UC08's own state model has no separate configurable timeout;
# midnight is the only answer deadline (design doc §3/§9).
CONF_EVENING_PROMPT_ENABLED = "evening_prompt_enabled"  # input_boolean.sc_evening_prompt_enabled
CONF_EVENING_PROMPT_TIME = "evening_prompt_time"  # input_datetime.sc_evening_prompt_time

DEFAULT_GRID_SAFETY_OFFSET_A = 2.0
DEFAULT_SMOOTHING_WINDOW = 4
DEFAULT_SOLAR_START_THRESHOLD_W = 150.0
DEFAULT_SOLAR_ONLY_START_THRESHOLD_W = 1300.0
DEFAULT_SOLAR_HOLD_MIN = 5.0
DEFAULT_SOLAR_COOLDOWN_MIN = 2.0
DEFAULT_SOLAR_ONLY_STRATEGY = ROUND_DOWN
DEFAULT_SOLAR_ONLY_MIDPOINT = 0.5  # fraction 0-1 (R2 round_nearest), not a percent
DEFAULT_SOC_LIMIT = 80.0  # percent, 50-100 (R6) -- range enforced by `SocLimitOverrideNumber`
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
DEFAULT_EVENING_PROMPT_ENABLED = True
DEFAULT_EVENING_PROMPT_TIME = "18:00:00"

SOC_LIMIT_OVERRIDE_MIN = 50.0  # percent (R6) -- shared by number.py's own bounds and the
SOC_LIMIT_OVERRIDE_MAX = 100.0  # coordinator's set_soc_limit_override clamp (single source)
