"""HA-free `SmartChargingConfig` test factory (issue #570 follow-up).

Before this, `tests/test_coordinator.py`, `tests/test_coordinator_cycle.py`, and
`tests/benchmarks/test_coordinator_perf.py` each carried their own near-identical ~28-field
`_config(**overrides)` factory -- exactly the kind of "the same fact resolved in more than one
place" duplication issue #570 removed from the production code, just relocated into three test
files instead of two production ones. `make_test_config` is the one place the full field list
(and its default value) is declared; each suite's own thin `_config(**overrides)` wrapper layers
only the handful of baseline values IT specifically needs different from these shared defaults.

Deliberately NOT in `tests/helpers.py`: that module imports `homeassistant.util.dt`, which would
make `tests/test_coordinator_cycle.py` -- a plain-pytest suite deliberately kept HA-import-free
(ADR-0009) -- transitively require Home Assistant at collection time. This module only imports
`custom_components.smart_charging.config`/`.const`, both already HA-free.
"""

from custom_components.smart_charging.config import SmartChargingConfig
from custom_components.smart_charging.const import (
    DEFAULT_CAPTAR_AVAILABLE,
    DEFAULT_CAPTAR_COOLDOWN_MIN,
    DEFAULT_EV_BATTERY_CAPACITY_KWH,
    DEFAULT_EVENING_PROMPT_ENABLED,
    DEFAULT_EVENING_PROMPT_TIME,
    DEFAULT_MAX_SOLAR_SOC,
    DEFAULT_PEAK_FLOOR_KW,
    DEFAULT_PEAK_GRACE_MIN,
    DEFAULT_SAFETY_MARGIN_W,
    DEFAULT_SMOOTHING_WINDOW,
    DEFAULT_SOLAR_AVAILABLE,
    DEFAULT_SOLAR_COOLDOWN_MIN,
    DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH,
    DEFAULT_SOLAR_HOLD_MIN,
    DEFAULT_SOLAR_ONLY_HOLD_MIN,
    DEFAULT_SOLAR_ONLY_MIDPOINT,
    DEFAULT_SOLAR_ONLY_START_THRESHOLD_W,
    DEFAULT_SOLAR_ONLY_STRATEGY,
    DEFAULT_SOLAR_RESERVE_SOC,
    DEFAULT_SOLAR_RESTART_DEBOUNCE_MIN,
    DEFAULT_SOLAR_START_THRESHOLD_W,
    DEFAULT_SOLAR_STEP_PP,
    DEFAULT_SOLAR_STEP_THRESHOLD_PP,
)


def make_test_config(**overrides) -> SmartChargingConfig:
    """A `SmartChargingConfig` seeded from production DEFAULT_* values, plus a handful of
    test-only baseline current/voltage/ceiling numbers no DEFAULT_* exists for (a real config
    entry always supplies these, so `const.py` has no fallback to borrow). `**overrides` takes
    the dataclass's own field names."""
    defaults = dict(
        solar_available=DEFAULT_SOLAR_AVAILABLE,
        captar_available=DEFAULT_CAPTAR_AVAILABLE,
        min_current=6.0,
        max_current=16.0,
        grid_ceiling_a=25.0,
        grid_safety_offset_a=2.0,
        nominal_voltage=230.0,
        smoothing_window=DEFAULT_SMOOTHING_WINDOW,
        peak_window_size=1,
        solar_start_threshold_w=DEFAULT_SOLAR_START_THRESHOLD_W,
        solar_only_start_threshold_w=DEFAULT_SOLAR_ONLY_START_THRESHOLD_W,
        solar_hold_min=DEFAULT_SOLAR_HOLD_MIN,
        solar_only_hold_min=DEFAULT_SOLAR_ONLY_HOLD_MIN,
        solar_restart_debounce_min=DEFAULT_SOLAR_RESTART_DEBOUNCE_MIN,
        solar_cooldown_min=DEFAULT_SOLAR_COOLDOWN_MIN,
        solar_only_strategy=DEFAULT_SOLAR_ONLY_STRATEGY,
        solar_only_midpoint=DEFAULT_SOLAR_ONLY_MIDPOINT,
        safety_margin_w=DEFAULT_SAFETY_MARGIN_W,
        max_peak_kw=100.0,  # ample headroom by default -- most tests don't exercise R3
        peak_floor_kw=DEFAULT_PEAK_FLOOR_KW,
        peak_grace_min=DEFAULT_PEAK_GRACE_MIN,
        captar_cooldown_min=DEFAULT_CAPTAR_COOLDOWN_MIN,
        power_respect_peak=True,
        ev_battery_capacity_kwh=DEFAULT_EV_BATTERY_CAPACITY_KWH,
        max_solar_soc=DEFAULT_MAX_SOLAR_SOC,
        solar_step_pp=DEFAULT_SOLAR_STEP_PP,
        solar_step_threshold_pp=DEFAULT_SOLAR_STEP_THRESHOLD_PP,
        solar_reserve_soc=DEFAULT_SOLAR_RESERVE_SOC,
        solar_forecast_threshold_kwh=DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH,
        evening_prompt_enabled=DEFAULT_EVENING_PROMPT_ENABLED,
        evening_prompt_time=DEFAULT_EVENING_PROMPT_TIME,
    )
    defaults.update(overrides)
    return SmartChargingConfig(**defaults)
