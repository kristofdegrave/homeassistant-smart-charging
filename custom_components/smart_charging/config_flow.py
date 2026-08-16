"""Config and options flow for Smart Charging (ADR-0005)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CAPTAR_AVAILABLE,
    CONF_CAPTAR_COOLDOWN_MIN,
    CONF_CAR_HOME_ENTITY,
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_CHARGING_STATES,
    CONF_CONNECTED_STATES,
    CONF_CONTROL_INTERVAL_S,
    CONF_DEADLINE_AVAILABLE,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_DEPARTURE_EXTERNAL_ENTITY,
    CONF_EV_BATTERY_CAPACITY_ENTITY,
    CONF_EV_BATTERY_CAPACITY_KWH,
    CONF_EV_SOC_ENTITY,
    CONF_EVENING_PROMPT_ENABLED,
    CONF_EVENING_PROMPT_TIME,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_GRID_VOLTAGE_ENTITY,
    CONF_HOME_DAY_EXTERNAL_ENTITY,
    CONF_LOW_TARIFF_ENTITY,
    CONF_MAX_CURRENT,
    CONF_MAX_PEAK_KW,
    CONF_MAX_SOLAR_SOC,
    CONF_MIN_CURRENT,
    CONF_NET_POWER_ENTITY,
    CONF_NOMINAL_VOLTAGE,
    CONF_NOTIFICATION_TARGET_ENTITY,
    CONF_PEAK_GRACE_MIN,
    CONF_POWER_RESPECT_PEAK,
    CONF_REMINDER_LEAD_H,
    CONF_SAFETY_MARGIN_W,
    CONF_SMOOTHING_WINDOW,
    CONF_SOLAR_AVAILABLE,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_FORECAST_ENTITY,
    CONF_SOLAR_FORECAST_THRESHOLD_KWH,
    CONF_SOLAR_HOLD_MIN,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_SOLAR_ONLY_START_THRESHOLD_W,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_RESERVE_SOC,
    CONF_SOLAR_START_THRESHOLD_W,
    CONF_SOLAR_STEP_PP,
    CONF_SOLAR_STEP_THRESHOLD_PP,
    CONF_STATUS_TRANSLATION,
    CONF_VEHICLE_CHARGE_LIMIT_ENTITY,
    CONF_VEHICLE_LIMIT_MAPPED,
    DEFAULT_CAPTAR_AVAILABLE,
    DEFAULT_CAPTAR_COOLDOWN_MIN,
    DEFAULT_CONTROL_INTERVAL_S,
    DEFAULT_DEADLINE_AVAILABLE,
    DEFAULT_DEFAULT_TARGET_CURRENT,
    DEFAULT_EV_BATTERY_CAPACITY_KWH,
    DEFAULT_EVENING_PROMPT_ENABLED,
    DEFAULT_EVENING_PROMPT_TIME,
    DEFAULT_GRID_CEILING_A,
    DEFAULT_GRID_SAFETY_OFFSET_A,
    DEFAULT_MAX_CURRENT,
    DEFAULT_MAX_PEAK_KW,
    DEFAULT_MAX_SOLAR_SOC,
    DEFAULT_MIN_CURRENT,
    DEFAULT_NOMINAL_VOLTAGE,
    DEFAULT_PEAK_GRACE_MIN,
    DEFAULT_POWER_RESPECT_PEAK,
    DEFAULT_REMINDER_LEAD_H,
    DEFAULT_SAFETY_MARGIN_W,
    DEFAULT_SMOOTHING_WINDOW,
    DEFAULT_SOC_LIMIT,
    DEFAULT_SOLAR_AVAILABLE,
    DEFAULT_SOLAR_COOLDOWN_MIN,
    DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH,
    DEFAULT_SOLAR_HOLD_MIN,
    DEFAULT_SOLAR_ONLY_MIDPOINT,
    DEFAULT_SOLAR_ONLY_START_THRESHOLD_W,
    DEFAULT_SOLAR_ONLY_STRATEGY,
    DEFAULT_SOLAR_RESERVE_SOC,
    DEFAULT_SOLAR_START_THRESHOLD_W,
    DEFAULT_SOLAR_STEP_PP,
    DEFAULT_SOLAR_STEP_THRESHOLD_PP,
    DOMAIN,
    ERROR_REQUIRED_WHEN_CAPTAR_AVAILABLE,
    ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE,
    ERROR_REQUIRED_WHEN_VEHICLE_LIMIT_MAPPED,
    ROUND_DOWN,
    ROUND_NEAREST,
    ROUND_UP,
    STATE_CHARGING,
    STATE_CONNECTED,
    STEP_CAPTAR,
    STEP_DEADLINE,
    STEP_MAPPINGS,
    STEP_SOLAR,
    STEP_THRESHOLDS,
    STEP_VEHICLE_LIMIT,
)

# Threshold/default keys stored in config-entry OPTIONS (ADR-0005), not data.
OPTION_KEYS = (
    CONF_NOMINAL_VOLTAGE,
    CONF_MIN_CURRENT,
    CONF_MAX_CURRENT,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_SMOOTHING_WINDOW,
    CONF_SOLAR_START_THRESHOLD_W,
    CONF_SOLAR_ONLY_START_THRESHOLD_W,
    CONF_SOLAR_HOLD_MIN,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_SAFETY_MARGIN_W,
    CONF_MAX_PEAK_KW,
    CONF_PEAK_GRACE_MIN,
    CONF_CAPTAR_COOLDOWN_MIN,
    CONF_POWER_RESPECT_PEAK,
    CONF_EV_BATTERY_CAPACITY_KWH,
    CONF_MAX_SOLAR_SOC,
    CONF_SOLAR_STEP_PP,
    CONF_SOLAR_STEP_THRESHOLD_PP,
    CONF_SOLAR_RESERVE_SOC,
    CONF_SOLAR_FORECAST_THRESHOLD_KWH,
    CONF_EVENING_PROMPT_ENABLED,
    CONF_EVENING_PROMPT_TIME,
    CONF_REMINDER_LEAD_H,
)


def _parse_states(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


def _build_translation(connected: str, charging: str) -> dict[str, str]:
    translation = {s: STATE_CONNECTED for s in _parse_states(connected)}
    # Charging wins on overlap.
    translation.update({s: STATE_CHARGING for s in _parse_states(charging)})
    return translation


def _entity(domain: str | list[str] | None = None):
    cfg = {} if domain is None else {"domain": domain}
    return selector.EntitySelector(selector.EntitySelectorConfig(**cfg))


# DATA fields — entity-role mappings + raw state lists (folded into status_translation).
MAPPING_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CHARGER_CURRENT_ENTITY): _entity("number"),
        vol.Required(CONF_CHARGER_STATUS_ENTITY): _entity(["sensor", "binary_sensor"]),
        vol.Required(CONF_CONNECTED_STATES): str,
        vol.Required(CONF_CHARGING_STATES): str,
        vol.Required(CONF_NET_POWER_ENTITY): _entity("sensor"),
        vol.Required(CONF_CHARGER_POWER_ENTITY): _entity("sensor"),
        vol.Optional(CONF_GRID_VOLTAGE_ENTITY): _entity("sensor"),
        vol.Optional(CONF_SOLAR_AVAILABLE, default=False): bool,
        vol.Optional(CONF_CAPTAR_AVAILABLE, default=True): bool,
        vol.Optional(CONF_EV_SOC_ENTITY): _entity("sensor"),
        vol.Optional(CONF_SOLAR_FORECAST_ENTITY): _entity("sensor"),
        vol.Optional(CONF_EV_BATTERY_CAPACITY_ENTITY): _entity("sensor"),
        vol.Optional(CONF_DEPARTURE_EXTERNAL_ENTITY): _entity("sensor"),
        vol.Optional(CONF_HOME_DAY_EXTERNAL_ENTITY): _entity(["binary_sensor", "input_boolean"]),
        vol.Optional(CONF_LOW_TARIFF_ENTITY): _entity(["binary_sensor", "input_boolean"]),
        vol.Optional(CONF_VEHICLE_CHARGE_LIMIT_ENTITY): _entity("number"),
        vol.Optional(CONF_CAR_HOME_ENTITY): _entity(["device_tracker", "person", "binary_sensor"]),
        # RA4 notify-target role (notifications design doc §3/§6): must be a `notify`-domain
        # entity; EntitySelector's own domain filter rejects a mismatched entity (vol.Invalid).
        vol.Optional(CONF_NOTIFICATION_TARGET_ENTITY): _entity("notify"),
    }
)


def _threshold_schema(defaults: dict | None = None) -> vol.Schema:
    """OPTIONS fields — thresholds/defaults, prefilled from `defaults` when editing."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_NOMINAL_VOLTAGE, default=d.get(CONF_NOMINAL_VOLTAGE, DEFAULT_NOMINAL_VOLTAGE)
            ): vol.Coerce(float),
            vol.Required(
                CONF_MIN_CURRENT, default=d.get(CONF_MIN_CURRENT, DEFAULT_MIN_CURRENT)
            ): vol.Coerce(float),
            vol.Required(
                CONF_MAX_CURRENT, default=d.get(CONF_MAX_CURRENT, DEFAULT_MAX_CURRENT)
            ): vol.Coerce(float),
            vol.Required(
                CONF_GRID_CEILING_A, default=d.get(CONF_GRID_CEILING_A, DEFAULT_GRID_CEILING_A)
            ): vol.Coerce(float),
            vol.Required(
                CONF_GRID_SAFETY_OFFSET_A,
                default=d.get(CONF_GRID_SAFETY_OFFSET_A, DEFAULT_GRID_SAFETY_OFFSET_A),
            ): vol.Coerce(float),
            vol.Required(
                CONF_DEFAULT_TARGET_CURRENT,
                default=d.get(CONF_DEFAULT_TARGET_CURRENT, DEFAULT_DEFAULT_TARGET_CURRENT),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SMOOTHING_WINDOW,
                default=d.get(CONF_SMOOTHING_WINDOW, DEFAULT_SMOOTHING_WINDOW),
            ): vol.Coerce(int),
            vol.Required(
                CONF_SOLAR_START_THRESHOLD_W,
                default=d.get(CONF_SOLAR_START_THRESHOLD_W, DEFAULT_SOLAR_START_THRESHOLD_W),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_ONLY_START_THRESHOLD_W,
                default=d.get(
                    CONF_SOLAR_ONLY_START_THRESHOLD_W, DEFAULT_SOLAR_ONLY_START_THRESHOLD_W
                ),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_HOLD_MIN, default=d.get(CONF_SOLAR_HOLD_MIN, DEFAULT_SOLAR_HOLD_MIN)
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_COOLDOWN_MIN,
                default=d.get(CONF_SOLAR_COOLDOWN_MIN, DEFAULT_SOLAR_COOLDOWN_MIN),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_ONLY_STRATEGY,
                default=d.get(CONF_SOLAR_ONLY_STRATEGY, DEFAULT_SOLAR_ONLY_STRATEGY),
            ): vol.In([ROUND_UP, ROUND_DOWN, ROUND_NEAREST]),
            vol.Required(
                CONF_SOLAR_ONLY_MIDPOINT,
                default=d.get(CONF_SOLAR_ONLY_MIDPOINT, DEFAULT_SOLAR_ONLY_MIDPOINT),
            ): vol.Coerce(float),
            vol.Required(
                CONF_DEFAULT_SOC_LIMIT, default=d.get(CONF_DEFAULT_SOC_LIMIT, DEFAULT_SOC_LIMIT)
            ): vol.Coerce(float),
            vol.Required(
                CONF_SAFETY_MARGIN_W,
                default=d.get(CONF_SAFETY_MARGIN_W, DEFAULT_SAFETY_MARGIN_W),
            ): vol.Coerce(float),
            vol.Required(
                CONF_MAX_PEAK_KW, default=d.get(CONF_MAX_PEAK_KW, DEFAULT_MAX_PEAK_KW)
            ): vol.Coerce(float),
            vol.Required(
                CONF_PEAK_GRACE_MIN,
                default=d.get(CONF_PEAK_GRACE_MIN, DEFAULT_PEAK_GRACE_MIN),
            ): vol.Coerce(float),
            vol.Required(
                CONF_CAPTAR_COOLDOWN_MIN,
                default=d.get(CONF_CAPTAR_COOLDOWN_MIN, DEFAULT_CAPTAR_COOLDOWN_MIN),
            ): vol.Coerce(float),
            vol.Required(
                CONF_POWER_RESPECT_PEAK,
                default=d.get(CONF_POWER_RESPECT_PEAK, DEFAULT_POWER_RESPECT_PEAK),
            ): bool,
            vol.Required(
                CONF_EV_BATTERY_CAPACITY_KWH,
                default=d.get(CONF_EV_BATTERY_CAPACITY_KWH, DEFAULT_EV_BATTERY_CAPACITY_KWH),
            ): vol.Coerce(float),
            vol.Required(
                CONF_MAX_SOLAR_SOC,
                default=d.get(CONF_MAX_SOLAR_SOC, DEFAULT_MAX_SOLAR_SOC),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_STEP_PP,
                default=d.get(CONF_SOLAR_STEP_PP, DEFAULT_SOLAR_STEP_PP),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_STEP_THRESHOLD_PP,
                default=d.get(CONF_SOLAR_STEP_THRESHOLD_PP, DEFAULT_SOLAR_STEP_THRESHOLD_PP),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_RESERVE_SOC,
                default=d.get(CONF_SOLAR_RESERVE_SOC, DEFAULT_SOLAR_RESERVE_SOC),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_FORECAST_THRESHOLD_KWH,
                default=d.get(
                    CONF_SOLAR_FORECAST_THRESHOLD_KWH, DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH
                ),
            ): vol.Coerce(float),
            # UC08 evening home-day prompt options (notifications design doc §3). No
            # sc_prompt_timeout_h field -- deliberately not wired (design §3/§9; UC08 has no
            # separate timeout, midnight is the only answer deadline).
            vol.Required(
                CONF_EVENING_PROMPT_ENABLED,
                default=d.get(CONF_EVENING_PROMPT_ENABLED, DEFAULT_EVENING_PROMPT_ENABLED),
            ): bool,
            vol.Required(
                CONF_EVENING_PROMPT_TIME,
                default=d.get(CONF_EVENING_PROMPT_TIME, DEFAULT_EVENING_PROMPT_TIME),
            ): selector.TimeSelector(),
        }
    )


# Install form = mappings + thresholds in one screen; split into data/options on submit.
USER_SCHEMA = MAPPING_SCHEMA.extend(_threshold_schema().schema)


# --- The step-table dispatcher (guided config flow, ADR-0025 Option C). ---
# No handler class uses this yet (plan T2) -- SmartChargingConfigFlow/SmartChargingOptionsFlow
# start wiring into it from T3 onward. CONFIG_TABLE/OPTIONS_TABLE below are populated
# incrementally, one task at a time, in UC12's fixed order, as each step method lands
# (T3's mappings/thresholds rows, T4's solar row, T5's captar row, T6's deadline row, T7's
# vehicle_limit row, T10's options table) -- not all six/four rows at once here, since no
# step method exists yet for most of them and a row with no matching method would strand the
# flow the moment its gate passed (ADR-0025's stated Con). This is a deliberate scoping of the
# plan's "add the two tables exactly as the design doc specifies" instruction: the design doc
# describes the tables' final, fully-populated shape; this task adds the mechanism and the
# (initially empty) tables it operates on, per T3's own note ("keep T2's table assertions
# scoped to the rows that exist").


class FlowMode(StrEnum):
    """Which of the three flows (UC12) a `_TableWalkMixin` instance is running."""

    INSTALL = "install"
    RECONFIGURE = "reconfigure"
    OPTIONS = "options"


@dataclass(frozen=True)
class FlowStep:
    """One row of a flow's ordered, gated step table (ADR-0025, Option C)."""

    step_id: str
    gate: Callable[[Any], bool]  # takes the flow handler: a config flow or an options flow


class _TableWalkMixin:
    """Shared table-walk dispatcher for `SmartChargingConfigFlow`/`SmartChargingOptionsFlow`.

    `gate` takes the flow handler rather than a dict so one `FlowStep` signature serves both
    tables: the config-table gates read `self._answers`/`self._mode`, the options-table gates
    read `self.config_entry.data`. Deliberately not typed `Callable[[_TableWalkMixin], bool]`:
    `config_entry` lives on `OptionsFlow`, not on this mixin, so the narrower hint would make
    every options-table gate a type error.
    """

    _mode: FlowMode
    _answers: dict[str, Any] | None = None  # per-run accumulator (ADR-0025 point 2)
    _table: ClassVar[tuple[FlowStep, ...]] = ()

    async def _async_advance(self, after: str | None):
        """Show the first step after `after` whose gate passes; finish when none remain.

        `after` need not itself be a table row (e.g. the `core`/`init` entry point is not a
        `_table` member) -- scanning starts from the row *following* a matching step_id, or
        from the first row when `after` is `None` or not found in the table at all."""
        start = 0
        if after is not None:
            for index, row in enumerate(self._table):
                if row.step_id == after:
                    start = index + 1
                    break
        for row in self._table[start:]:
            if row.gate(self):
                return await getattr(self, f"async_step_{row.step_id}")()
        return await self._async_finish()

    async def _async_finish(self):
        """Terminal: create / update the entry. Implemented per handler."""
        raise NotImplementedError


# UC12 step 2's fixed order (solar -> captar -> deadline -> vehicle limit -> ungated mappings
# -> ungated thresholds), independent of how many of CONFIG_TABLE's rows exist yet -- every
# task that appends a row must keep the table a subsequence of this order (asserted by
# tests/test_config_flow.py's test_uc12_step2_config_table_is_in_uc12s_fixed_order).
UC12_FIXED_STEP_ORDER = (
    STEP_SOLAR,
    STEP_CAPTAR,
    STEP_DEADLINE,
    STEP_VEHICLE_LIMIT,
    STEP_MAPPINGS,
    STEP_THRESHOLDS,
)

# Populated incrementally -- see the module comment above. Empty until T3.
CONFIG_TABLE: tuple[FlowStep, ...] = ()

# Populated incrementally in T10 (its own table per ADR-0025 point 3 -- gated on the *stored*
# capability flags, not this run's answers). Empty until then.
OPTIONS_TABLE: tuple[FlowStep, ...] = ()


# --- Per-step schema fragments (guided config flow, ADR-0025 Option C; UC12/R20). ---
# MAPPING_SCHEMA/_threshold_schema()/USER_SCHEMA above stay in place until the flat flow's
# remaining callers are removed (T13, plan). These fragments are the guided flow's own.

CORE_MAPPING_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CHARGER_CURRENT_ENTITY): _entity("number"),
        vol.Required(CONF_CHARGER_STATUS_ENTITY): _entity(["sensor", "binary_sensor"]),
        vol.Required(CONF_CONNECTED_STATES): str,
        vol.Required(CONF_CHARGING_STATES): str,
        vol.Required(CONF_NET_POWER_ENTITY): _entity("sensor"),
        vol.Required(CONF_CHARGER_POWER_ENTITY): _entity("sensor"),
        # T3 flips this rendered default to True (design, "Decisions on two forks" §2 --
        # R20 AC1's "defaulting to present"); DEFAULT_SOLAR_AVAILABLE itself stays False,
        # used only as the absent-key read fallback. Left at the constant here, same as
        # `prompt_timeout_h` below is left off the ungated-threshold fragment until T3.
        vol.Required(CONF_SOLAR_AVAILABLE, default=DEFAULT_SOLAR_AVAILABLE): bool,
        vol.Required(CONF_CAPTAR_AVAILABLE, default=DEFAULT_CAPTAR_AVAILABLE): bool,
        vol.Required(CONF_DEADLINE_AVAILABLE, default=DEFAULT_DEADLINE_AVAILABLE): bool,
        vol.Required(CONF_VEHICLE_LIMIT_MAPPED, default=False): bool,
    }
)


def _solar_mapping_schema(include_ev_soc: bool) -> vol.Schema:
    """UC12 step 3 mapping half. `ev_soc_entity` is included only when the once-only rule
    (R20 AC4) puts it here rather than on the CapTar step -- the one field deliberately
    shared with `_captar_mapping_schema` (design, "Schema fragments")."""
    fields: dict = {}
    if include_ev_soc:
        fields[vol.Optional(CONF_EV_SOC_ENTITY)] = _entity("sensor")
    fields[vol.Optional(CONF_SOLAR_FORECAST_ENTITY)] = _entity("sensor")
    return vol.Schema(fields)


def _solar_threshold_schema(defaults: dict | None = None) -> vol.Schema:
    """UC12 step 3 threshold half."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_SOLAR_START_THRESHOLD_W,
                default=d.get(CONF_SOLAR_START_THRESHOLD_W, DEFAULT_SOLAR_START_THRESHOLD_W),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_ONLY_START_THRESHOLD_W,
                default=d.get(
                    CONF_SOLAR_ONLY_START_THRESHOLD_W, DEFAULT_SOLAR_ONLY_START_THRESHOLD_W
                ),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_ONLY_STRATEGY,
                default=d.get(CONF_SOLAR_ONLY_STRATEGY, DEFAULT_SOLAR_ONLY_STRATEGY),
            ): vol.In([ROUND_UP, ROUND_DOWN, ROUND_NEAREST]),
            vol.Required(
                CONF_SOLAR_ONLY_MIDPOINT,
                default=d.get(CONF_SOLAR_ONLY_MIDPOINT, DEFAULT_SOLAR_ONLY_MIDPOINT),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_HOLD_MIN, default=d.get(CONF_SOLAR_HOLD_MIN, DEFAULT_SOLAR_HOLD_MIN)
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_COOLDOWN_MIN,
                default=d.get(CONF_SOLAR_COOLDOWN_MIN, DEFAULT_SOLAR_COOLDOWN_MIN),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_STEP_PP,
                default=d.get(CONF_SOLAR_STEP_PP, DEFAULT_SOLAR_STEP_PP),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_STEP_THRESHOLD_PP,
                default=d.get(CONF_SOLAR_STEP_THRESHOLD_PP, DEFAULT_SOLAR_STEP_THRESHOLD_PP),
            ): vol.Coerce(float),
            vol.Required(
                CONF_MAX_SOLAR_SOC,
                default=d.get(CONF_MAX_SOLAR_SOC, DEFAULT_MAX_SOLAR_SOC),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_RESERVE_SOC,
                default=d.get(CONF_SOLAR_RESERVE_SOC, DEFAULT_SOLAR_RESERVE_SOC),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_FORECAST_THRESHOLD_KWH,
                default=d.get(
                    CONF_SOLAR_FORECAST_THRESHOLD_KWH, DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH
                ),
            ): vol.Coerce(float),
        }
    )


def _captar_mapping_schema(include_ev_soc: bool) -> vol.Schema:
    """UC12 step 4 mapping half. See `_solar_mapping_schema` for the once-only ev_soc rule."""
    fields: dict = {}
    if include_ev_soc:
        fields[vol.Optional(CONF_EV_SOC_ENTITY)] = _entity("sensor")
    return vol.Schema(fields)


def _captar_threshold_schema(defaults: dict | None = None) -> vol.Schema:
    """UC12 step 4 threshold half."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_CAPTAR_COOLDOWN_MIN,
                default=d.get(CONF_CAPTAR_COOLDOWN_MIN, DEFAULT_CAPTAR_COOLDOWN_MIN),
            ): vol.Coerce(float),
        }
    )


DEADLINE_MAPPING_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_DEPARTURE_EXTERNAL_ENTITY): _entity("sensor"),
    }
)


def _deadline_threshold_schema(defaults: dict | None = None) -> vol.Schema:
    """UC12 step 5 threshold half."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_REMINDER_LEAD_H,
                default=d.get(CONF_REMINDER_LEAD_H, DEFAULT_REMINDER_LEAD_H),
            ): vol.Coerce(float),
        }
    )


VEHICLE_LIMIT_MAPPING_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VEHICLE_CHARGE_LIMIT_ENTITY): _entity("number"),
        vol.Optional(CONF_CAR_HOME_ENTITY): _entity(["device_tracker", "person", "binary_sensor"]),
    }
)


UNGATED_MAPPING_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_GRID_VOLTAGE_ENTITY): _entity("sensor"),
        vol.Optional(CONF_LOW_TARIFF_ENTITY): _entity(["binary_sensor", "input_boolean"]),
        # RA4 notify-target role (notifications design doc §3/§6): must be a `notify`-domain
        # entity; EntitySelector's own domain filter rejects a mismatched entity (vol.Invalid).
        vol.Optional(CONF_NOTIFICATION_TARGET_ENTITY): _entity("notify"),
        vol.Optional(CONF_EV_BATTERY_CAPACITY_ENTITY): _entity("sensor"),
        vol.Optional(CONF_HOME_DAY_EXTERNAL_ENTITY): _entity(["binary_sensor", "input_boolean"]),
    }
)


def _ungated_threshold_schema(
    defaults: dict | None = None, *, include_interval: bool = False
) -> vol.Schema:
    """UC12 step 8. `include_interval` is True only for the options flow (UC12 1b) -- the
    install and reconfigure flows never ask the control interval and default it instead.

    `prompt_timeout_h` is added in T3 (design, "Decisions on two forks" §1) -- the ungated-
    threshold fragment's key set here is one field short of the design doc's fragment table
    until that task lands."""
    d = defaults or {}
    schema: dict = {
        vol.Required(
            CONF_NOMINAL_VOLTAGE, default=d.get(CONF_NOMINAL_VOLTAGE, DEFAULT_NOMINAL_VOLTAGE)
        ): vol.Coerce(float),
        vol.Required(
            CONF_MIN_CURRENT, default=d.get(CONF_MIN_CURRENT, DEFAULT_MIN_CURRENT)
        ): vol.Coerce(float),
        vol.Required(
            CONF_MAX_CURRENT, default=d.get(CONF_MAX_CURRENT, DEFAULT_MAX_CURRENT)
        ): vol.Coerce(float),
        vol.Required(
            CONF_GRID_CEILING_A, default=d.get(CONF_GRID_CEILING_A, DEFAULT_GRID_CEILING_A)
        ): vol.Coerce(float),
        vol.Required(
            CONF_GRID_SAFETY_OFFSET_A,
            default=d.get(CONF_GRID_SAFETY_OFFSET_A, DEFAULT_GRID_SAFETY_OFFSET_A),
        ): vol.Coerce(float),
        vol.Required(
            CONF_SMOOTHING_WINDOW,
            default=d.get(CONF_SMOOTHING_WINDOW, DEFAULT_SMOOTHING_WINDOW),
        ): vol.Coerce(int),
        vol.Required(
            CONF_DEFAULT_SOC_LIMIT, default=d.get(CONF_DEFAULT_SOC_LIMIT, DEFAULT_SOC_LIMIT)
        ): vol.Coerce(float),
        vol.Required(
            CONF_DEFAULT_TARGET_CURRENT,
            default=d.get(CONF_DEFAULT_TARGET_CURRENT, DEFAULT_DEFAULT_TARGET_CURRENT),
        ): vol.Coerce(float),
        vol.Required(
            CONF_SAFETY_MARGIN_W,
            default=d.get(CONF_SAFETY_MARGIN_W, DEFAULT_SAFETY_MARGIN_W),
        ): vol.Coerce(float),
        vol.Required(
            CONF_MAX_PEAK_KW, default=d.get(CONF_MAX_PEAK_KW, DEFAULT_MAX_PEAK_KW)
        ): vol.Coerce(float),
        vol.Required(
            CONF_PEAK_GRACE_MIN,
            default=d.get(CONF_PEAK_GRACE_MIN, DEFAULT_PEAK_GRACE_MIN),
        ): vol.Coerce(float),
        vol.Required(
            CONF_EV_BATTERY_CAPACITY_KWH,
            default=d.get(CONF_EV_BATTERY_CAPACITY_KWH, DEFAULT_EV_BATTERY_CAPACITY_KWH),
        ): vol.Coerce(float),
        vol.Required(
            CONF_POWER_RESPECT_PEAK,
            default=d.get(CONF_POWER_RESPECT_PEAK, DEFAULT_POWER_RESPECT_PEAK),
        ): bool,
        vol.Required(
            CONF_EVENING_PROMPT_ENABLED,
            default=d.get(CONF_EVENING_PROMPT_ENABLED, DEFAULT_EVENING_PROMPT_ENABLED),
        ): bool,
        vol.Required(
            CONF_EVENING_PROMPT_TIME,
            default=d.get(CONF_EVENING_PROMPT_TIME, DEFAULT_EVENING_PROMPT_TIME),
        ): selector.TimeSelector(),
    }
    if include_interval:
        schema[
            vol.Required(
                CONF_CONTROL_INTERVAL_S,
                default=d.get(CONF_CONTROL_INTERVAL_S, DEFAULT_CONTROL_INTERVAL_S),
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=5))
    return vol.Schema(schema)


def _ev_soc_missing_error(user_input: dict) -> dict[str, str] | None:
    """R18/design §3: Solar installed=True or CapTar available=True requires ev_soc
    mapped -- a config-time guard, not a runtime fault. Shared by the install and
    reconfigure steps so flipping either toggle through either path is rejected the
    same way. Both must be False for ev_soc to stay optional."""
    if user_input.get(CONF_SOLAR_AVAILABLE) and not user_input.get(CONF_EV_SOC_ENTITY):
        return {CONF_EV_SOC_ENTITY: ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE}
    if user_input.get(CONF_CAPTAR_AVAILABLE, DEFAULT_CAPTAR_AVAILABLE) and not user_input.get(
        CONF_EV_SOC_ENTITY
    ):
        return {CONF_EV_SOC_ENTITY: ERROR_REQUIRED_WHEN_CAPTAR_AVAILABLE}
    return None


def _solar_forecast_missing_error(user_input: dict) -> dict[str, str] | None:
    """Design doc §3: solar_forecast is required only when CONF_SOLAR_AVAILABLE is True
    (R9's precondition is inert without the solar capability) -- same
    required_when_solar_available-style guard ev_soc's own guard uses."""
    if user_input.get(CONF_SOLAR_AVAILABLE) and not user_input.get(CONF_SOLAR_FORECAST_ENTITY):
        return {CONF_SOLAR_FORECAST_ENTITY: ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE}
    return None


def _car_home_missing_error(user_input: dict) -> dict[str, str] | None:
    """UC09 C2 / design §9.1: mapping vehicle_charge_limit requires car_home -- the
    home-only write gate is not optional. Unmapped vehicle limit imposes no requirement."""
    if user_input.get(CONF_VEHICLE_CHARGE_LIMIT_ENTITY) and not user_input.get(
        CONF_CAR_HOME_ENTITY
    ):
        return {CONF_CAR_HOME_ENTITY: ERROR_REQUIRED_WHEN_VEHICLE_LIMIT_MAPPED}
    return None


def _mapping_errors(user_input: dict) -> dict[str, str] | None:
    """Combined config-time guards for the mapping step (install + reconfigure)."""
    errors = _ev_soc_missing_error(user_input) or {}
    errors.update(_solar_forecast_missing_error(user_input) or {})
    errors.update(_car_home_missing_error(user_input) or {})
    return errors or None


def _split_data(user_input: dict) -> dict:
    """Extract the DATA bucket (mappings + derived translation) from a submitted form."""
    data = {
        k: v
        for k, v in user_input.items()
        if k not in OPTION_KEYS and k not in (CONF_CONNECTED_STATES, CONF_CHARGING_STATES)
    }
    data[CONF_STATUS_TRANSLATION] = _build_translation(
        user_input[CONF_CONNECTED_STATES], user_input[CONF_CHARGING_STATES]
    )
    return data


class SmartChargingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the install-time and reconfigure flows (ADR-0005)."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

        errors = _mapping_errors(user_input)
        if errors:
            return self.async_show_form(
                step_id="user",
                data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
                errors=errors,
            )

        data = _split_data(user_input)
        # Intersection, not direct indexing: T1 (guided config flow) appends keys to
        # OPTION_KEYS that this flat USER_SCHEMA does not yet ask for (e.g. reminder_lead_h,
        # asked only on UC12 step 5) -- ADR-0025, Consequences, applied here a task early so
        # this still-active flat flow survives OPTION_KEYS growing ahead of USER_SCHEMA.
        options = {k: user_input[k] for k in OPTION_KEYS if k in user_input}
        options[CONF_CONTROL_INTERVAL_S] = DEFAULT_CONTROL_INTERVAL_S
        return self.async_create_entry(title="Smart Charging", data=data, options=options)

    async def async_step_reconfigure(self, user_input=None):
        """Edit the entity-role mappings (DATA) with re-validation; reloads on save (ADR-0005)."""
        entry = self._get_reconfigure_entry()
        if user_input is None:
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=self.add_suggested_values_to_schema(MAPPING_SCHEMA, entry.data),
            )

        errors = _mapping_errors(user_input)
        if errors:
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=self.add_suggested_values_to_schema(MAPPING_SCHEMA, user_input),
                errors=errors,
            )

        return self.async_update_reload_and_abort(entry, data=_split_data(user_input))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SmartChargingOptionsFlow()


class SmartChargingOptionsFlow(config_entries.OptionsFlow):
    """Options flow: thresholds/defaults + control interval, editable anytime (ADR-0005).

    `self.config_entry` (from `config_entries.OptionsFlow`) resolves via `self.hass`
    and the flow-manager-assigned entry id, neither of which is set yet inside
    `__init__`. This class therefore defines no `__init__` and only reads
    `self.config_entry` from step methods, which always run after initialization.
    """

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options
        schema = _threshold_schema(opts).extend(
            {
                vol.Required(
                    CONF_CONTROL_INTERVAL_S,
                    default=opts.get(CONF_CONTROL_INTERVAL_S, DEFAULT_CONTROL_INTERVAL_S),
                ): vol.All(vol.Coerce(int), vol.Range(min=5))
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
