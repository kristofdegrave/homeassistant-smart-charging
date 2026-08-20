"""SmartChargingConfig: one frozen dataclass built once at setup (`__init__.py`) from the
config entry's data/options (issue #570). Before this, `__init__.py` resolved every option
with `opts.get(CONF_X, DEFAULT_X)` into a plain dict, and coordinator.py/coordinator_cycle.py
then resolved many of the SAME ~28 keys a second time (`self._config.get(CONF_X, DEFAULT_X)`),
mixed with direct indexing (`self._config[CONF_X]`) elsewhere -- which keys were guaranteed
present was unknowable without cross-reading both files.

Every field here is fully resolved (default applied, if any) by the time `__init__.py`
constructs it. coordinator.py/coordinator_cycle.py read it as a plain typed attribute and never
re-default or re-index it themselves -- a missing/misspelled field is now a construction-time
`TypeError`, not a silent `KeyError`/stale-default deep in a control cycle.

Deliberately NOT a `Mapping`/dict: `NotificationManager` (M3) is out of this issue's scope and
keeps its own small `Mapping[str, Any]` (built in `__init__.py` from this same object's fields,
so the two never drift apart) -- only coordinator.py/coordinator_cycle.py take this dataclass
directly.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class SmartChargingConfig:
    """Every config-entry option coordinator.py/coordinator_cycle.py read during a control
    cycle, resolved exactly once (field name is the CONF_* constant's suffix, lowercased) --
    except `evening_prompt_enabled`/`evening_prompt_time`, which neither module reads: they
    exist only so `__init__.py` can derive `NotificationManager`'s (M3, out of this issue's
    scope) own small config `Mapping` from this same, already-resolved object instead of a
    second `opts.get(CONF_X, DEFAULT_X)` resolution.

    `kw_only=True`: with 28 same-shaped fields (several adjacently confusable, e.g.
    `solar_start_threshold_w`/`solar_only_start_threshold_w`), positional construction would
    be a silent-transposition hazard for no benefit -- every construction site already uses
    keywords.
    """

    solar_available: bool
    captar_available: bool
    min_current: float
    max_current: float
    grid_ceiling_a: float
    grid_safety_offset_a: float
    nominal_voltage: float
    smoothing_window: int
    peak_window_size: int
    solar_start_threshold_w: float
    solar_only_start_threshold_w: float
    solar_hold_min: float
    solar_only_hold_min: float
    solar_cooldown_min: float
    solar_only_strategy: str
    solar_only_midpoint: float
    safety_margin_w: float
    max_peak_kw: float
    peak_grace_min: float
    captar_cooldown_min: float
    power_respect_peak: bool
    ev_battery_capacity_kwh: float
    max_solar_soc: float
    solar_step_pp: float
    solar_step_threshold_pp: float
    solar_reserve_soc: float
    solar_forecast_threshold_kwh: float
    evening_prompt_enabled: bool
    evening_prompt_time: str
