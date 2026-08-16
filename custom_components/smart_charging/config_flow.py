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
    CONF_PROMPT_TIMEOUT_H,
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
    DEFAULT_PROMPT_TIMEOUT_H,
    DEFAULT_REMINDER_LEAD_H,
    DEFAULT_SAFETY_MARGIN_W,
    DEFAULT_SMOOTHING_WINDOW,
    DEFAULT_SOC_LIMIT,
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
    STEP_CORE,
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
    # CONF_PROMPT_TIMEOUT_H and CONF_REMINDER_LEAD_H: like every OPTION_KEYS member, the
    # guided install flow writes these -- but the still-flat SmartChargingOptionsFlow
    # (async_step_init) replaces entry.options wholesale from `_threshold_schema()`, which
    # asks about neither. The first Configure+Save after install silently drops both, until
    # T10 gives the options flow its own table with a merge-not-replace terminal step
    # (design, "The terminal step and the bucket split"). Harmless today: nothing reads
    # either key yet.
    CONF_PROMPT_TIMEOUT_H,
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
            # sc_prompt_timeout_h field here -- this flat schema backs only the still-flat
            # options flow (async_step_init) until T10 builds its own table; the guided
            # flow's _ungated_threshold_schema fragment presents/stores prompt_timeout_h from
            # T3 onward (design, "Decisions on two forks" §1), superseding
            # notifications-design.md §3/§9's earlier "deliberately NOT wired" call. No
            # component reads it yet.
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
# SmartChargingConfigFlow starts wiring into this from T3 onward (SmartChargingOptionsFlow
# from T10). CONFIG_TABLE/OPTIONS_TABLE below are populated incrementally, one task at a time
# (T3/T4/T5/T6/T7/T10 -- see the plan), rather than fully per the design doc's end-state
# Structure section: no step method exists yet for most rows, and a row with no matching
# method would strand the flow the moment its gate passed (ADR-0025's stated Con) --
# concretely, a full CONFIG_TABLE at T3 would AttributeError on every default install, since
# DEFAULT_CAPTAR_AVAILABLE is True and the walk would reach the captar row before
# async_step_captar exists (T5). Comment sweep of this scaffolding is part of T13's cleanup.
#
# T3's known temporary gap (a default-accepting install rejected at the thresholds step for a
# missing ev_soc_entity mapping with no step to answer it on) is fully closed as of this task.
# T4 gave ev_soc_entity a place to be answered whenever solar is declared (its form default is
# True); T5 does the same for captar (also True by default): whichever of the two capabilities
# is declared, its own step now asks for ev_soc_entity and re-shows itself with a field-local
# error on a missing mapping, rather than falling through to the thresholds-step safety net
# with no field left to answer it on. That safety net (`_mapping_errors` at the thresholds
# step) now only remains load-bearing for the still-unsplit vehicle-limit guard (T7).


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
    _table: ClassVar[tuple[FlowStep, ...]]  # no default -- a handler that forgets to set
    # this must AttributeError, not silently walk an empty table and finish early.

    async def _async_advance(self, after: str | None) -> config_entries.ConfigFlowResult:
        """Show the first step after `after` whose gate passes; finish when none remain.

        `after` need not itself be a table row: the shared `core` entry point and the
        framework-mandated `init` entry point (ADR-0025 point 4) are both legitimately not
        `_table` members. Scanning starts from the row *following* a matching step_id, or
        from the first row when `after` is `None` or not found in the table at all -- the
        same "start from row 0" behaviour serves both of those entry points correctly. Any
        other, genuinely unrecognised `after` would silently do the same (restart the walk)
        rather than raise; the mixin's only two legitimate non-member callers are `core` and
        `init`, so this is accepted as part of the design rather than additionally guarded
        here."""
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

    async def _async_finish(self) -> config_entries.ConfigFlowResult:
        """Terminal: create / update the entry. Implemented per handler."""
        raise NotImplementedError


# UC12 step 2's fixed order (solar -> captar -> deadline -> vehicle limit -> ungated mappings
# -> ungated thresholds), independent of how many of CONFIG_TABLE's rows exist yet -- every
# task that appends a row must keep the table a subsequence of this order (asserted by
# tests/test_config_flow.py's test_uc12_step2_config_table_is_in_uc12s_fixed_order, which
# spells the expected order out itself from UC12/const.py's STEP_* constants rather than
# importing this constant, so the test stays an independent oracle rather than checking the
# production table against itself). This constant is a documentation/cross-check aid for
# whoever adds a row, not a runtime dependency of the dispatcher.
#
# TODO(T7, T10): once CONFIG_TABLE carries all six rows (T7) and OPTIONS_TABLE all four
# (T10), add a completeness assertion (`[row.step_id for row in CONFIG_TABLE] ==
# list(UC12_FIXED_STEP_ORDER)`, and similarly for OPTIONS_TABLE minus vehicle_limit) -- the
# subsequence check here only guards relative order, not that every row has actually landed.
UC12_FIXED_STEP_ORDER = (
    STEP_SOLAR,
    STEP_CAPTAR,
    STEP_DEADLINE,
    STEP_VEHICLE_LIMIT,
    STEP_MAPPINGS,
    STEP_THRESHOLDS,
)

# Populated incrementally -- see the module comment above. T3 added the two ungated rows
# (`mappings`/`thresholds`, UC12 steps 7/8), needing no capability to be reached. T4 added
# `solar`, gated on this run's own CONF_SOLAR_AVAILABLE answer. T5 adds `captar`, gated the
# same way on CONF_CAPTAR_AVAILABLE, placed after `solar` -- UC12's fixed order is what makes
# `async_step_captar`'s `include_ev_soc` expression correct (see its docstring). Both
# capability flags are always present in self._answers by the time any gate runs
# (CORE_MAPPING_SCHEMA marks both vol.Required). `deadline`/`vehicle_limit` (T6-T7) still
# have no method, so their rows wait.
# `thresholds` is additionally gated off for reconfigure (UC12 1a, design "Step ids" table row
# 6) -- moot until T9 wires async_step_reconfigure into this table, but correct now.
CONFIG_TABLE: tuple[FlowStep, ...] = (
    FlowStep(step_id=STEP_SOLAR, gate=lambda flow: bool(flow._answers.get(CONF_SOLAR_AVAILABLE))),
    FlowStep(step_id=STEP_CAPTAR, gate=lambda flow: bool(flow._answers.get(CONF_CAPTAR_AVAILABLE))),
    FlowStep(step_id=STEP_MAPPINGS, gate=lambda flow: True),
    FlowStep(step_id=STEP_THRESHOLDS, gate=lambda flow: flow._mode is not FlowMode.RECONFIGURE),
)

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
        # Form default True (R20 AC1's "defaulting to present"; design, "Decisions on two
        # forks" §2) -- deliberately diverges from DEFAULT_SOLAR_AVAILABLE (False), which
        # stays the absent-key read fallback for an entry that predates this field.
        vol.Required(CONF_SOLAR_AVAILABLE, default=True): bool,
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
    install and reconfigure flows never ask the control interval and default it instead."""
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
        vol.Required(
            CONF_PROMPT_TIMEOUT_H,
            default=d.get(CONF_PROMPT_TIMEOUT_H, DEFAULT_PROMPT_TIMEOUT_H),
        ): vol.Coerce(float),
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


class SmartChargingConfigFlow(_TableWalkMixin, config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the install-time and reconfigure flows (ADR-0005, ADR-0025)."""

    VERSION = 1
    _table = CONFIG_TABLE

    async def async_step_user(self, user_input=None):
        """UC12's install entry point (ADR-0025 point 4): delegate into the shared `core`
        step, framework-imposed name aside."""
        self._mode = FlowMode.INSTALL
        self._answers = {}
        return await self.async_step_core()

    async def async_step_core(self, user_input=None):
        """UC12 step 1: the core mappings + the three capability decisions + the
        vehicle-limit election (design, "Schema fragments")."""
        if user_input is None:
            return self.async_show_form(step_id=STEP_CORE, data_schema=CORE_MAPPING_SCHEMA)

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_CORE)

    async def async_step_solar(self, user_input=None):
        """UC12 step 3: the solar mapping + threshold halves, gated on solar declared this
        run (design, "Schema fragments"). Step-local guard (ADR-0025 point 1): a missing
        ev_soc/solar_forecast mapping re-shows this step with a field-local error instead of
        the end-of-form safety net T3 still runs for the not-yet-split vehicle-limit guard."""
        include_ev_soc = CONF_EV_SOC_ENTITY not in self._answers
        schema = _solar_mapping_schema(include_ev_soc)
        if self._mode is not FlowMode.RECONFIGURE:
            schema = schema.extend(_solar_threshold_schema().schema)
        if user_input is None:
            return self.async_show_form(step_id=STEP_SOLAR, data_schema=schema)

        merged = {**self._answers, **user_input}
        errors = _ev_soc_missing_error(merged) or {}
        errors.update(_solar_forecast_missing_error(merged) or {})
        if errors:
            return self.async_show_form(
                step_id=STEP_SOLAR,
                data_schema=self.add_suggested_values_to_schema(schema, user_input),
                errors=errors,
            )

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_SOLAR)

    async def async_step_captar(self, user_input=None):
        """UC12 step 4: the CapTar mapping + threshold halves, gated on CapTar declared this
        run (design, "Schema fragments"). `include_ev_soc` mirrors the solar step's own
        expression; it is already False here whenever the solar step ran and collected the
        mapping (R20 AC4's once-only rule), because UC12's fixed order places `solar` before
        `captar` in CONFIG_TABLE and the solar step only advances after merging into
        self._answers. Step-local guard (ADR-0025 point 1, "needs particular care" per the
        design's Consequences): a missing ev_soc mapping re-shows this step with a
        field-local error keyed off CapTar, not solar -- `_ev_soc_missing_error` checks the
        solar branch first, which is inert here since solar_available is either False or
        already satisfied by the time this step can be reached."""
        include_ev_soc = CONF_EV_SOC_ENTITY not in self._answers
        schema = _captar_mapping_schema(include_ev_soc)
        if self._mode is not FlowMode.RECONFIGURE:
            schema = schema.extend(_captar_threshold_schema().schema)
        if user_input is None:
            return self.async_show_form(step_id=STEP_CAPTAR, data_schema=schema)

        merged = {**self._answers, **user_input}
        errors = _ev_soc_missing_error(merged) or {}
        if errors:
            return self.async_show_form(
                step_id=STEP_CAPTAR,
                data_schema=self.add_suggested_values_to_schema(schema, user_input),
                errors=errors,
            )

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_CAPTAR)

    async def async_step_mappings(self, user_input=None):
        """UC12 step 7: the ungated entity-role mappings (design, "Schema fragments")."""
        if user_input is None:
            return self.async_show_form(step_id=STEP_MAPPINGS, data_schema=UNGATED_MAPPING_SCHEMA)

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_MAPPINGS)

    async def async_step_thresholds(self, user_input=None):
        """UC12 step 8: the ungated thresholds/defaults -- the install/reconfigure flows
        never ask the control interval (design, "Schema fragments").

        `_mapping_errors` is called here, on the last install-path form, as the temporary
        safety net the plan's Conventions section describes: today's flat flow's end-of-form
        behaviour, preserved verbatim until T4-T7 each move one guard to its own gated step
        and T7 deletes both this call and `_mapping_errors` itself. T4/T5 already give ev_soc/
        solar_forecast (solar step) and ev_soc (captar step) their own step-local guards, so
        of the three `_mapping_errors` guards, only `_car_home_missing_error` is retained for
        T7's benefit -- and it cannot actually fire yet: it keys off
        `vehicle_charge_limit_entity`, which no guided step collects until T7 adds the
        vehicle_limit step, so this call is currently unreachable on the install path (see
        `test_thresholds_error_preserves_previously_entered_values`'s deferral comment). It
        reads `self._answers` alone, not `self._answers | user_input`: none of the three
        guards' fields (`solar_available`, `captar_available`, `ev_soc_entity`,
        `solar_forecast_entity`, `vehicle_charge_limit_entity`, `car_home_entity`) is asked on
        this step, so a merge with this step's own submission could never change the
        verdict."""
        schema = _ungated_threshold_schema(include_interval=False)
        if user_input is None:
            return self.async_show_form(step_id=STEP_THRESHOLDS, data_schema=schema)

        errors = _mapping_errors(self._answers)
        if errors:
            return self.async_show_form(
                step_id=STEP_THRESHOLDS,
                data_schema=self.add_suggested_values_to_schema(schema, user_input),
                errors=errors,
            )

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_THRESHOLDS)

    async def _async_finish(self) -> config_entries.ConfigFlowResult:
        """UC12 step 9: create the entry (install only -- T9 wires reconfigure's own
        terminal behaviour into this same mixin method)."""
        self._answers.pop(CONF_VEHICLE_LIMIT_MAPPED, None)  # design D-2: transient, not stored
        data = _split_data(self._answers)
        # Intersection, not direct indexing (ADR-0025, Consequences): a capability declared
        # absent this run never renders its step, so its OPTION_KEYS members are absent from
        # self._answers -- direct indexing would KeyError the moment any capability is off.
        options = {k: self._answers[k] for k in OPTION_KEYS if k in self._answers}
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
