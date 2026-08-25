"""Config and options flow for Smart Charging (ADR-0005)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
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
    CONF_DEADLINE_NOTICE_ENABLED,
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
    CONF_NOTIFICATIONS_AVAILABLE,
    CONF_PEAK_FLOOR_KW,
    CONF_PEAK_GRACE_MIN,
    CONF_PLUG_IN_REMINDER_ENABLED,
    CONF_POWER_COOLDOWN_MIN,
    CONF_POWER_RESPECT_PEAK,
    CONF_REMINDER_LEAD_H,
    CONF_SAFETY_MARGIN_W,
    CONF_SMOOTHING_WINDOW,
    CONF_SOLAR_AVAILABLE,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_FORECAST_ENTITY,
    CONF_SOLAR_FORECAST_THRESHOLD_KWH,
    CONF_SOLAR_HOLD_MIN,
    CONF_SOLAR_ONLY_HOLD_MIN,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_SOLAR_ONLY_START_THRESHOLD_W,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_POWER_ENTITY,
    CONF_SOLAR_RESERVE_SOC,
    CONF_SOLAR_RESTART_DEBOUNCE_MIN,
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
    DEFAULT_DEADLINE_NOTICE_ENABLED,
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
    DEFAULT_NOTIFICATIONS_AVAILABLE,
    DEFAULT_PEAK_FLOOR_KW,
    DEFAULT_PEAK_GRACE_MIN,
    DEFAULT_PLUG_IN_REMINDER_ENABLED,
    DEFAULT_POWER_COOLDOWN_MIN,
    DEFAULT_POWER_RESPECT_PEAK,
    DEFAULT_REMINDER_LEAD_H,
    DEFAULT_SAFETY_MARGIN_W,
    DEFAULT_SMOOTHING_WINDOW,
    DEFAULT_SOC_LIMIT,
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
    STEP_EV_CHARGER,
    STEP_GRID,
    STEP_MAPPINGS,
    STEP_NOTIFICATIONS,
    STEP_POWER,
    STEP_SOLAR,
    STEP_THRESHOLDS,
    STEP_VEHICLE,
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
    CONF_SOLAR_ONLY_HOLD_MIN,
    CONF_SOLAR_RESTART_DEBOUNCE_MIN,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_SAFETY_MARGIN_W,
    CONF_MAX_PEAK_KW,
    CONF_PEAK_FLOOR_KW,
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
    # CONF_REMINDER_LEAD_H lives on the deadline step's threshold half. T10 gave the options
    # flow its own table with a merge-not-replace terminal step (design, "The terminal step
    # and the bucket split"), so it round-trips through Configure+Save correctly.
    CONF_REMINDER_LEAD_H,
    # T2 (topic-step config-flow design D-1): three new keys, deferred from T1 until a
    # fragment actually carries each of them (_power_threshold_schema,
    # _notifications_threshold_schema below).
    CONF_POWER_COOLDOWN_MIN,
    CONF_DEADLINE_NOTICE_ENABLED,
    CONF_PLUG_IN_REMINDER_ENABLED,
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


# --- The step-table dispatcher (guided config flow, ADR-0025 Option C). ---
# SmartChargingConfigFlow's own table is CONFIG_TABLE, SmartChargingOptionsFlow's is
# OPTIONS_TABLE (both below); both are now complete, with a step method for every row (T3-T13).
#
# Historical note on the guard consolidation this replaced: the flat flow's `_mapping_errors`
# combined three guards (solar's/captar's shared ev_soc_entity requirement and vehicle_limit's
# car_home_entity requirement) at a single thresholds-step safety net, because none of those
# three had a step of its own to answer on. T5 gave solar/captar that step-local home for
# ev_soc_entity; T7 gave vehicle_limit the same for car_home_entity via `_car_home_missing_error`
# -- with all three guards step-local, the thresholds-step combiner and `_mapping_errors` itself
# were deleted outright (ADR-0025, Consequences: the combiner has no *guided-flow step* left that
# needs all three). T9 migrated `async_step_reconfigure` onto this same table (ADR-0025 point 4):
# it now delegates into the shared `core` step instead of running its own flat form, so every
# guard above already covers reconfigure too -- there is no longer a separate three-guard combine
# to keep in sync with the guided flow's own.


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
# CONFIG_TABLE carries all six rows as of T7; T8's traversal matrix is the exact-sequence
# assertion this comment used to ask for on the config side (its own task, not duplicated
# here). OPTIONS_TABLE carries all four of its own rows as of T10, asserted directly as
# equality by that table's own order test (unlike CONFIG_TABLE, OPTIONS_TABLE landed complete
# in one task, so there was no incremental build-out state to tolerate with a subsequence
# check).
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
# `solar`, gated on this run's own CONF_SOLAR_AVAILABLE answer. T5 added `captar`, gated the
# same way on CONF_CAPTAR_AVAILABLE, placed after `solar` -- UC12's fixed order is what makes
# `async_step_captar`'s `include_ev_soc` expression correct (see its docstring). T6 added
# `deadline`, gated the same way on CONF_DEADLINE_AVAILABLE -- unlike solar/captar it carries
# no step-local guard (UC12 marks neither of its fields required, R18 AC7). T7 adds
# `vehicle_limit`, gated on the transient CONF_VEHICLE_LIMIT_MAPPED election (design D-2; popped
# in `_async_finish`, never stored). All four gates read a value that's always present in
# self._answers by the time any gate runs (CORE_MAPPING_SCHEMA marks each vol.Required). The
# table is now complete for the install flow.
# `thresholds` is additionally gated off for reconfigure (UC12 1a, design "Step ids" table row
# 6): T9 wires async_step_reconfigure into this same table, so this gate is what makes step 8
# skip itself in that mode -- no second table, no reconfigure-specific branch in the walk.
CONFIG_TABLE: tuple[FlowStep, ...] = (
    FlowStep(step_id=STEP_SOLAR, gate=lambda flow: bool(flow._answers.get(CONF_SOLAR_AVAILABLE))),
    FlowStep(step_id=STEP_CAPTAR, gate=lambda flow: bool(flow._answers.get(CONF_CAPTAR_AVAILABLE))),
    FlowStep(
        step_id=STEP_DEADLINE, gate=lambda flow: bool(flow._answers.get(CONF_DEADLINE_AVAILABLE))
    ),
    FlowStep(
        step_id=STEP_VEHICLE_LIMIT,
        gate=lambda flow: bool(flow._answers.get(CONF_VEHICLE_LIMIT_MAPPED)),
    ),
    FlowStep(step_id=STEP_MAPPINGS, gate=lambda flow: True),
    FlowStep(step_id=STEP_THRESHOLDS, gate=lambda flow: flow._mode is not FlowMode.RECONFIGURE),
)

# The options flow's own table (ADR-0025 point 3): threshold halves only, no `core`/
# `mappings`/`vehicle_limit` rows (mapping fields never appear here -- ADR-0005 restricts this
# flow to the options bucket). Gated on the *stored* capability flags (`self.config_entry.data`),
# never this run's own answers -- the options flow never re-asks a capability, only its
# thresholds. Every gate reads defensively via `.get(key, DEFAULT_*)`, never bracket indexing:
# `deadline_available` is a key this slice introduces (D-1) and is absent from every entry
# written before it, so `entry.data[CONF_DEADLINE_AVAILABLE]` would KeyError on the first
# Configure a pre-slice entry ever opens.
OPTIONS_TABLE: tuple[FlowStep, ...] = (
    FlowStep(
        step_id=STEP_SOLAR,
        gate=lambda flow: bool(
            flow.config_entry.data.get(CONF_SOLAR_AVAILABLE, DEFAULT_SOLAR_AVAILABLE)
        ),
    ),
    FlowStep(
        step_id=STEP_CAPTAR,
        gate=lambda flow: bool(
            flow.config_entry.data.get(CONF_CAPTAR_AVAILABLE, DEFAULT_CAPTAR_AVAILABLE)
        ),
    ),
    FlowStep(
        step_id=STEP_DEADLINE,
        gate=lambda flow: bool(
            flow.config_entry.data.get(CONF_DEADLINE_AVAILABLE, DEFAULT_DEADLINE_AVAILABLE)
        ),
    ),
    FlowStep(step_id=STEP_THRESHOLDS, gate=lambda flow: True),
)


# --- T3: the two new (interim-named) tables for the nine topic steps (ADR-0027 Decision,
# Option C unchanged in mechanism). Named NINE_STEP_CONFIG_TABLE/NINE_STEP_OPTIONS_TABLE so
# they can coexist with the still-live CONFIG_TABLE/OPTIONS_TABLE above -- T4 renames the
# first to CONFIG_TABLE and T7 the second to OPTIONS_TABLE, each deleting the table it
# replaces in the same commit (plan T3). Neither table is wired into `_table`/the framework
# entry points yet, so the live flow is unchanged.
#
# `core` is deliberately not a NINE_STEP_CONFIG_TABLE row: it is the shared install/
# reconfigure entry point both async_step_user and async_step_reconfigure delegate into
# (ADR-0027 point 5, design "Step ids and the two tables"). It IS a NINE_STEP_OPTIONS_TABLE
# row, because the options flow's own entry point, async_step_init, renders no form of its
# own.
NINE_STEP_CONFIG_TABLE: tuple[FlowStep, ...] = (
    FlowStep(step_id=STEP_GRID, gate=lambda flow: True),
    FlowStep(step_id=STEP_EV_CHARGER, gate=lambda flow: True),
    FlowStep(step_id=STEP_VEHICLE, gate=lambda flow: True),
    # Neither `power` nor `captar` has a mapping half, so both must be absent from the
    # reconfigure walk (UC12 1a, ADR-0027 point 3): reconfigure's subset is a per-step gate,
    # not a stop condition, because both sit in the *middle* of the fixed order rather than
    # at its end.
    FlowStep(step_id=STEP_POWER, gate=lambda flow: flow._mode is not FlowMode.RECONFIGURE),
    FlowStep(
        step_id=STEP_CAPTAR,
        gate=lambda flow: (
            bool(flow._answers.get(CONF_CAPTAR_AVAILABLE))
            and flow._mode is not FlowMode.RECONFIGURE
        ),
    ),
    FlowStep(step_id=STEP_SOLAR, gate=lambda flow: bool(flow._answers.get(CONF_SOLAR_AVAILABLE))),
    FlowStep(
        step_id=STEP_DEADLINE, gate=lambda flow: bool(flow._answers.get(CONF_DEADLINE_AVAILABLE))
    ),
    FlowStep(
        step_id=STEP_NOTIFICATIONS,
        gate=lambda flow: bool(flow._answers.get(CONF_NOTIFICATIONS_AVAILABLE)),
    ),
)

# Gated on the *stored* capability flags (`flow.config_entry.data`), never this run's own
# answers -- the options flow never re-asks a capability, only its thresholds (ADR-0027
# point 4). Every gate reads defensively via `.get(key, DEFAULT_*)`, never bracket indexing:
# `notifications_available` is a key this slice introduces and is absent from every entry
# written before it, so `entry.data[CONF_NOTIFICATIONS_AVAILABLE]` would KeyError the first
# time an upgraded installation opens Configure.
NINE_STEP_OPTIONS_TABLE: tuple[FlowStep, ...] = (
    FlowStep(step_id=STEP_CORE, gate=lambda flow: True),
    FlowStep(step_id=STEP_GRID, gate=lambda flow: True),
    FlowStep(step_id=STEP_EV_CHARGER, gate=lambda flow: True),
    FlowStep(step_id=STEP_VEHICLE, gate=lambda flow: True),
    FlowStep(step_id=STEP_POWER, gate=lambda flow: True),
    FlowStep(
        step_id=STEP_CAPTAR,
        gate=lambda flow: bool(
            flow.config_entry.data.get(CONF_CAPTAR_AVAILABLE, DEFAULT_CAPTAR_AVAILABLE)
        ),
    ),
    FlowStep(
        step_id=STEP_SOLAR,
        gate=lambda flow: bool(
            flow.config_entry.data.get(CONF_SOLAR_AVAILABLE, DEFAULT_SOLAR_AVAILABLE)
        ),
    ),
    FlowStep(
        step_id=STEP_DEADLINE,
        gate=lambda flow: bool(
            flow.config_entry.data.get(CONF_DEADLINE_AVAILABLE, DEFAULT_DEADLINE_AVAILABLE)
        ),
    ),
    FlowStep(
        step_id=STEP_NOTIFICATIONS,
        gate=lambda flow: bool(
            flow.config_entry.data.get(
                CONF_NOTIFICATIONS_AVAILABLE, DEFAULT_NOTIFICATIONS_AVAILABLE
            )
        ),
    ),
)


# --- Per-step schema fragments (guided config flow, ADR-0025 Option C; UC12/R20). ---
# The flat flow's own MAPPING_SCHEMA/_threshold_schema()/USER_SCHEMA (and _mapping_errors,
# gone since T7) are deleted as of T13 -- every path now runs through CONFIG_TABLE/OPTIONS_TABLE
# above. These fragments are the guided flow's own.

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
                CONF_SOLAR_ONLY_HOLD_MIN,
                default=d.get(CONF_SOLAR_ONLY_HOLD_MIN, DEFAULT_SOLAR_ONLY_HOLD_MIN),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_RESTART_DEBOUNCE_MIN,
                default=d.get(CONF_SOLAR_RESTART_DEBOUNCE_MIN, DEFAULT_SOLAR_RESTART_DEBOUNCE_MIN),
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
    """UC12 step 4 threshold half (the seven-step model, live today) / topic-step step 6's
    CapTar-gated threshold half (ADR-0027, T3/T4). Extended here (T2) with the five
    peak-protection fields (UC12 5b, R18 AC5) -- they now sit in this fragment AND
    `_ungated_threshold_schema` at once, which is intentional until T4 retires the latter
    (design, "Schema fragments"; plan T2's own re-pointing note)."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_CAPTAR_COOLDOWN_MIN,
                default=d.get(CONF_CAPTAR_COOLDOWN_MIN, DEFAULT_CAPTAR_COOLDOWN_MIN),
            ): vol.Coerce(float),
            vol.Required(
                CONF_POWER_RESPECT_PEAK,
                default=d.get(CONF_POWER_RESPECT_PEAK, DEFAULT_POWER_RESPECT_PEAK),
            ): bool,
            vol.Required(
                CONF_SAFETY_MARGIN_W,
                default=d.get(CONF_SAFETY_MARGIN_W, DEFAULT_SAFETY_MARGIN_W),
            ): vol.Coerce(float),
            vol.Required(
                CONF_MAX_PEAK_KW, default=d.get(CONF_MAX_PEAK_KW, DEFAULT_MAX_PEAK_KW)
            ): vol.Coerce(float),
            vol.Required(
                CONF_PEAK_FLOOR_KW, default=d.get(CONF_PEAK_FLOOR_KW, DEFAULT_PEAK_FLOOR_KW)
            ): vol.Coerce(float),
            vol.Required(
                CONF_PEAK_GRACE_MIN,
                default=d.get(CONF_PEAK_GRACE_MIN, DEFAULT_PEAK_GRACE_MIN),
            ): vol.Coerce(float),
        }
    )


DEADLINE_MAPPING_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_DEPARTURE_EXTERNAL_ENTITY): _entity("sensor"),
        # T2 (topic-step config-flow design, field-to-step table): the one ungated field a
        # gated step carries (UC12 5c / R20 AC5's named carve-out). Sits in this fragment AND
        # UNGATED_MAPPING_SCHEMA at once until T4 retires the latter.
        vol.Optional(CONF_HOME_DAY_EXTERNAL_ENTITY): _entity(["binary_sensor", "input_boolean"]),
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
            CONF_PEAK_FLOOR_KW, default=d.get(CONF_PEAK_FLOOR_KW, DEFAULT_PEAK_FLOOR_KW)
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
        # No prompt-timeout field is presented here -- midnight is the only answer deadline
        # (notifications-design.md §3/§9); a later slice briefly presented one anyway, since
        # reverted (#813/#818).
    }
    if include_interval:
        schema[
            vol.Required(
                CONF_CONTROL_INTERVAL_S,
                default=d.get(CONF_CONTROL_INTERVAL_S, DEFAULT_CONTROL_INTERVAL_S),
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=5))
    return vol.Schema(schema)


# --- T2: the nine steps' schema fragments (ADR-0027, Consequences: "The schema fragments
# are re-cut along topic lines"; design "Schema fragments" table). Added alongside the
# ADR-0025 fragments above, which still render the live flow until T4's cut-over -- nothing
# below is wired into CONFIG_TABLE/OPTIONS_TABLE yet (T3/T4/T7). CORE_MAPPING_SCHEMA is the
# one step whose mapping half is not re-cut here (still the four ADR-0025 core mappings + the
# capability decisions); its topic-step form is T4's concern, so only its threshold half is
# added here. Every docstring below cites "UC12 (topic-step) step N" -- the ADR-0027/design
# step numbering, which differs from the ADR-0025 fragments' own "UC12 step N" citations
# above for the same step id until T4 retires the latter.


def _core_threshold_schema(
    defaults: dict | None = None, *, include_interval: bool = False
) -> vol.Schema:
    """UC12 (topic-step) step 1 threshold half: the smoothing window, plus the control
    interval on the options flow only (UC12 1b; design, "Schema fragments").
    `include_interval` migrates here from `_ungated_threshold_schema` (design, "Schema
    fragments")."""
    d = defaults or {}
    schema: dict = {
        vol.Required(
            CONF_SMOOTHING_WINDOW,
            default=d.get(CONF_SMOOTHING_WINDOW, DEFAULT_SMOOTHING_WINDOW),
        ): vol.Coerce(int),
    }
    if include_interval:
        schema[
            vol.Required(
                CONF_CONTROL_INTERVAL_S,
                default=d.get(CONF_CONTROL_INTERVAL_S, DEFAULT_CONTROL_INTERVAL_S),
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=5))
    return vol.Schema(schema)


GRID_MAPPING_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NET_POWER_ENTITY): _entity("sensor"),
        vol.Optional(CONF_GRID_VOLTAGE_ENTITY): _entity("sensor"),
        # Landing-order check (design D-4): #746 (CONF_LOW_TARIFF_STATES) had not landed on
        # origin/main when this task ran, so this slice lands first -- this fragment carries
        # CONF_LOW_TARIFF_ENTITY exactly as it exists today and nothing else. #746's own plan
        # re-points its "add the field to UNGATED_MAPPING_SCHEMA" step at
        # GRID_MAPPING_SCHEMA/STEP_GRID.
        vol.Optional(CONF_LOW_TARIFF_ENTITY): _entity(["binary_sensor", "input_boolean"]),
    }
)


def _grid_threshold_schema(defaults: dict | None = None) -> vol.Schema:
    """UC12 (topic-step) step 2 threshold half."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_NOMINAL_VOLTAGE,
                default=d.get(CONF_NOMINAL_VOLTAGE, DEFAULT_NOMINAL_VOLTAGE),
            ): vol.Coerce(float),
            vol.Required(
                CONF_GRID_CEILING_A,
                default=d.get(CONF_GRID_CEILING_A, DEFAULT_GRID_CEILING_A),
            ): vol.Coerce(float),
            vol.Required(
                CONF_GRID_SAFETY_OFFSET_A,
                default=d.get(CONF_GRID_SAFETY_OFFSET_A, DEFAULT_GRID_SAFETY_OFFSET_A),
            ): vol.Coerce(float),
        }
    )


EV_CHARGER_MAPPING_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CHARGER_CURRENT_ENTITY): _entity("number"),
        vol.Required(CONF_CHARGER_STATUS_ENTITY): _entity(["sensor", "binary_sensor"]),
        vol.Required(CONF_CONNECTED_STATES): str,
        vol.Required(CONF_CHARGING_STATES): str,
        vol.Required(CONF_CHARGER_POWER_ENTITY): _entity("sensor"),
    }
)


def _ev_charger_threshold_schema(defaults: dict | None = None) -> vol.Schema:
    """UC12 (topic-step) step 3 threshold half."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_MIN_CURRENT, default=d.get(CONF_MIN_CURRENT, DEFAULT_MIN_CURRENT)
            ): vol.Coerce(float),
            vol.Required(
                CONF_MAX_CURRENT, default=d.get(CONF_MAX_CURRENT, DEFAULT_MAX_CURRENT)
            ): vol.Coerce(float),
        }
    )


VEHICLE_MAPPING_SCHEMA = vol.Schema(
    {
        # Required (design D-2, "Guards and required fields"): ADR-0027 point 1 makes this an
        # unconditional vol.Required on the always-shown `vehicle` step -- the once-only
        # cross-step guard (_ev_soc_missing_error) it replaces is deleted at T4.
        vol.Required(CONF_EV_SOC_ENTITY): _entity("sensor"),
        vol.Optional(CONF_EV_BATTERY_CAPACITY_ENTITY): _entity("sensor"),
        vol.Optional(CONF_VEHICLE_CHARGE_LIMIT_ENTITY): _entity("number"),
        # Optional here too (design D-2): the field-level car-at-home rule
        # (_car_home_missing_error, UC12 4a) still fires on a filled-in charge limit or a
        # present deadline capability -- that guard is wired to this step in T8.
        vol.Optional(CONF_CAR_HOME_ENTITY): _entity(["device_tracker", "person", "binary_sensor"]),
    }
)


def _vehicle_threshold_schema(defaults: dict | None = None) -> vol.Schema:
    """UC12 (topic-step) step 4 threshold half."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_EV_BATTERY_CAPACITY_KWH,
                default=d.get(CONF_EV_BATTERY_CAPACITY_KWH, DEFAULT_EV_BATTERY_CAPACITY_KWH),
            ): vol.Coerce(float),
            vol.Required(
                CONF_DEFAULT_SOC_LIMIT,
                default=d.get(CONF_DEFAULT_SOC_LIMIT, DEFAULT_SOC_LIMIT),
            ): vol.Coerce(float),
        }
    )


def _power_threshold_schema(defaults: dict | None = None) -> vol.Schema:
    """UC12 (topic-step) step 5 threshold half -- threshold-only, no mapping half (design
    "Schema fragments")."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_DEFAULT_TARGET_CURRENT,
                default=d.get(CONF_DEFAULT_TARGET_CURRENT, DEFAULT_DEFAULT_TARGET_CURRENT),
            ): vol.Coerce(float),
            vol.Required(
                CONF_POWER_COOLDOWN_MIN,
                default=d.get(CONF_POWER_COOLDOWN_MIN, DEFAULT_POWER_COOLDOWN_MIN),
            ): vol.Coerce(float),
        }
    )


SOLAR_MAPPING_SCHEMA = vol.Schema(
    {
        # New key (design D-1/D-2), optional -- nothing reads it yet (RA1's role construction
        # is deferred, design Deferrals).
        vol.Optional(CONF_SOLAR_POWER_ENTITY): _entity("sensor"),
        # Required (design D-2, "Guards and required fields"): ADR-0027 point 1 makes this a
        # plain vol.Required on the capability-gated `solar` step -- `_solar_forecast_missing_
        # error` is deleted at T4.
        vol.Required(CONF_SOLAR_FORECAST_ENTITY): _entity("sensor"),
    }
)


NOTIFICATIONS_MAPPING_SCHEMA = vol.Schema(
    {
        # RA4 notify-target role (notifications design doc §3/§6): must be a `notify`-domain
        # entity; EntitySelector's own domain filter rejects a mismatched entity (vol.Invalid).
        vol.Optional(CONF_NOTIFICATION_TARGET_ENTITY): _entity("notify"),
    }
)


def _notifications_threshold_schema(defaults: dict | None = None) -> vol.Schema:
    """UC12 (topic-step) step 9 threshold half: the three per-notification enable toggles
    (R18 AC11), each defaulting on, plus the evening home-day prompt's own time-of-day
    threshold."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_DEADLINE_NOTICE_ENABLED,
                default=d.get(CONF_DEADLINE_NOTICE_ENABLED, DEFAULT_DEADLINE_NOTICE_ENABLED),
            ): bool,
            vol.Required(
                CONF_PLUG_IN_REMINDER_ENABLED,
                default=d.get(CONF_PLUG_IN_REMINDER_ENABLED, DEFAULT_PLUG_IN_REMINDER_ENABLED),
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
    )


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

    def _maybe_prefill(
        self,
        schema: vol.Schema,
        *,
        extra_from: Callable[[Mapping[str, Any]], dict[str, Any]] | None = None,
    ) -> vol.Schema:
        """UC12 1a / ADR-0025 point 2: reconfigure prefills a step's rendered schema from the
        stored entry -- a rendering-only concern; the accumulator itself is never seeded
        (install renders `schema` unchanged). `extra_from(entry.data)` augments the prefill
        source for the one field with no stored key of its own -- the core step's transient
        vehicle-limit election (design D-2)."""
        if self._mode is not FlowMode.RECONFIGURE:
            return schema
        entry = self._get_reconfigure_entry()
        source = (entry.data | extra_from(entry.data)) if extra_from else entry.data
        return self.add_suggested_values_to_schema(schema, source)

    async def async_step_core(self, user_input=None):
        """UC12 step 1: the core mappings + the three capability decisions + the
        vehicle-limit election (design, "Schema fragments")."""
        if user_input is None:
            schema = self._maybe_prefill(
                CORE_MAPPING_SCHEMA,
                extra_from=lambda data: {
                    CONF_VEHICLE_LIMIT_MAPPED: bool(data.get(CONF_VEHICLE_CHARGE_LIMIT_ENTITY))
                },
            )
            return self.async_show_form(step_id=STEP_CORE, data_schema=schema)

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_CORE)

    async def async_step_solar(self, user_input=None):
        """UC12 step 3: the solar mapping + threshold halves, gated on solar declared this
        run (design, "Schema fragments"). Step-local guard (ADR-0025 point 1): a missing
        ev_soc/solar_forecast mapping re-shows this step with a field-local error -- the
        `_mapping_errors` end-of-form safety net this replaced is gone entirely since T7."""
        include_ev_soc = CONF_EV_SOC_ENTITY not in self._answers
        schema = _solar_mapping_schema(include_ev_soc)
        if self._mode is not FlowMode.RECONFIGURE:
            schema = schema.extend(_solar_threshold_schema().schema)
        if user_input is None:
            return self.async_show_form(step_id=STEP_SOLAR, data_schema=self._maybe_prefill(schema))

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
            return self.async_show_form(
                step_id=STEP_CAPTAR, data_schema=self._maybe_prefill(schema)
            )

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

    async def async_step_deadline(self, user_input=None):
        """UC12 step 5: the departure-time mapping + reminder-lead threshold, gated on
        deadline declared this run (design, "Schema fragments"). No step-local guard: UC12
        marks neither field required (R18 AC7) -- unlike the solar/captar steps, a submission
        here always advances."""
        schema = DEADLINE_MAPPING_SCHEMA
        if self._mode is not FlowMode.RECONFIGURE:
            schema = schema.extend(_deadline_threshold_schema().schema)
        if user_input is None:
            return self.async_show_form(
                step_id=STEP_DEADLINE, data_schema=self._maybe_prefill(schema)
            )

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_DEADLINE)

    # --- T3: the five genuinely-new topic-step methods (ADR-0027 Consequences; plan T3).
    # None of these is reachable from CONFIG_TABLE yet -- `_table` still points at the live
    # seven-step table above, so the flow this integration ships today is unchanged. T4's
    # cut-over is what points `_table` at NINE_STEP_CONFIG_TABLE and makes these reachable.

    async def async_step_grid(self, user_input=None):
        """UC12 (topic-step) step 2: the grid-connection mapping + threshold halves, always
        shown (design "Config table"). No step-local guard here -- validation guards belong
        to T4/T8, which is where this step becomes reachable."""
        schema = GRID_MAPPING_SCHEMA
        if self._mode is not FlowMode.RECONFIGURE:
            schema = schema.extend(_grid_threshold_schema().schema)
        if user_input is None:
            return self.async_show_form(step_id=STEP_GRID, data_schema=self._maybe_prefill(schema))

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_GRID)

    async def async_step_ev_charger(self, user_input=None):
        """UC12 (topic-step) step 3: the charger mapping + threshold halves, always shown
        (design "Config table")."""
        schema = EV_CHARGER_MAPPING_SCHEMA
        if self._mode is not FlowMode.RECONFIGURE:
            schema = schema.extend(_ev_charger_threshold_schema().schema)
        if user_input is None:
            return self.async_show_form(
                step_id=STEP_EV_CHARGER, data_schema=self._maybe_prefill(schema)
            )

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_EV_CHARGER)

    async def async_step_vehicle(self, user_input=None):
        """UC12 (topic-step) step 4: the vehicle mapping + threshold halves, always shown
        (design "Config table"). `ev_soc_entity` is `vol.Required` on VEHICLE_MAPPING_SCHEMA
        (design D-2) -- the once-only cross-step guard it replaces is deleted at T4. The
        field-level car-at-home rule (UC12 4a) is wired to this step in T8."""
        schema = VEHICLE_MAPPING_SCHEMA
        if self._mode is not FlowMode.RECONFIGURE:
            schema = schema.extend(_vehicle_threshold_schema().schema)
        if user_input is None:
            return self.async_show_form(
                step_id=STEP_VEHICLE, data_schema=self._maybe_prefill(schema)
            )

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_VEHICLE)

    async def async_step_power(self, user_input=None):
        """UC12 (topic-step) step 5: threshold-only, no mapping half (design "Schema
        fragments"). NINE_STEP_CONFIG_TABLE's own gate keeps this step out of reconfigure
        once wired (T4) -- no `self._mode` check is needed in the method body itself."""
        schema = _power_threshold_schema()
        if user_input is None:
            return self.async_show_form(step_id=STEP_POWER, data_schema=schema)

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_POWER)

    async def async_step_notifications(self, user_input=None):
        """UC12 (topic-step) step 9: the notify-target mapping + the three per-notification
        enable toggles (R18 AC11), gated on notifications declared this run (design "Config
        table")."""
        schema = NOTIFICATIONS_MAPPING_SCHEMA
        if self._mode is not FlowMode.RECONFIGURE:
            schema = schema.extend(_notifications_threshold_schema().schema)
        if user_input is None:
            return self.async_show_form(
                step_id=STEP_NOTIFICATIONS, data_schema=self._maybe_prefill(schema)
            )

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_NOTIFICATIONS)

    async def async_step_vehicle_limit(self, user_input=None):
        """UC12 step 6: the vehicle charge-limit mapping + its paired car-home presence
        mapping, gated on the transient election made on the core step (design D-2). UC12
        step 6: "the two are always asked together". Step-local guard (ADR-0025 point 1,
        design D-3): a missing car_home mapping re-shows this step with a field-local error,
        the last of the three guards `_mapping_errors` used to combine to move step-local.

        Unlike the solar/captar guards, this one reads `user_input` alone, never
        `self._answers` -- both fields it checks are answered on this step, not carried over:
        `vehicle_charge_limit_entity` is `vol.Required`, so the flow manager guarantees it is
        in `user_input` before this method ever runs; `car_home_entity` appears on no other
        guided step."""
        if user_input is None:
            return self.async_show_form(
                step_id=STEP_VEHICLE_LIMIT,
                data_schema=self._maybe_prefill(VEHICLE_LIMIT_MAPPING_SCHEMA),
            )

        errors = _car_home_missing_error(user_input)
        if errors:
            return self.async_show_form(
                step_id=STEP_VEHICLE_LIMIT,
                data_schema=self.add_suggested_values_to_schema(
                    VEHICLE_LIMIT_MAPPING_SCHEMA, user_input
                ),
                errors=errors,
            )

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_VEHICLE_LIMIT)

    async def async_step_mappings(self, user_input=None):
        """UC12 step 7: the ungated entity-role mappings (design, "Schema fragments")."""
        if user_input is None:
            return self.async_show_form(
                step_id=STEP_MAPPINGS, data_schema=self._maybe_prefill(UNGATED_MAPPING_SCHEMA)
            )

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_MAPPINGS)

    async def async_step_thresholds(self, user_input=None):
        """UC12 step 8: the ungated thresholds/defaults -- the install/reconfigure flows
        never ask the control interval (design, "Schema fragments").

        No mapping guard here: T3 kept a temporary `_mapping_errors` safety net on this step
        (today's flat flow's end-of-form behaviour, preserved verbatim) until T4-T7 each moved
        one guard to its own gated step. T7 moved the last one (`_car_home_missing_error`, to
        the vehicle_limit step) and deleted both that call and `_mapping_errors` itself --
        this step never had a mapping guard of its own to begin with (UC12 assigns none to the
        ungated thresholds step). Render skips `_maybe_prefill` too -- unlike every other step
        method, this one is unreachable in reconfigure at all (CONFIG_TABLE's own gate), so
        there is never a reconfigure render to prefill."""
        schema = _ungated_threshold_schema(include_interval=False)
        if user_input is None:
            return self.async_show_form(step_id=STEP_THRESHOLDS, data_schema=schema)

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_THRESHOLDS)

    async def _async_finish(self) -> config_entries.ConfigFlowResult:
        """UC12 step 9 (install) / 1a (reconfigure): create or update the entry. Reconfigure
        touches the data bucket only (ADR-0005) and reloads (ADR-0008); it never computes
        `options` at all -- the `thresholds` row's own gate skips step 8 entirely in this
        mode, so no threshold answer ever entered `self._answers` to intersect."""
        self._answers.pop(CONF_VEHICLE_LIMIT_MAPPED, None)  # design D-2: transient, not stored
        data = _split_data(self._answers)
        if self._mode is FlowMode.RECONFIGURE:
            entry = self._get_reconfigure_entry()
            return self.async_update_reload_and_abort(entry, data=data)
        # Intersection, not direct indexing (ADR-0025, Consequences): a capability declared
        # absent this run never renders its step, so its OPTION_KEYS members are absent from
        # self._answers -- direct indexing would KeyError the moment any capability is off.
        options = {k: self._answers[k] for k in OPTION_KEYS if k in self._answers}
        options[CONF_CONTROL_INTERVAL_S] = DEFAULT_CONTROL_INTERVAL_S
        return self.async_create_entry(title="Smart Charging", data=data, options=options)

    async def async_step_reconfigure(self, user_input=None):
        """UC12 1a's reconfigure entry point (ADR-0025 point 4): delegate into the shared
        `core` step, framework-imposed name aside -- the same shared step methods and table
        install uses, with `self._mode` alone selecting each step's mapping-only render
        (`_maybe_prefill`), the `thresholds` row's skip, and `_async_finish`'s terminal
        branch. No guard logic of its own: every guard (`_ev_soc_missing_error`,
        `_solar_forecast_missing_error`, `_car_home_missing_error`) is already step-local
        (T4/T5/T7) and runs unconditionally regardless of `self._mode`."""
        self._mode = FlowMode.RECONFIGURE
        self._answers = {}
        return await self.async_step_core()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SmartChargingOptionsFlow()


class SmartChargingOptionsFlow(_TableWalkMixin, config_entries.OptionsFlow):
    """Options flow: thresholds/defaults + control interval, editable anytime (ADR-0005).

    Walks its own table (ADR-0025 point 3) -- threshold halves only, built from the same
    fragments the config flow uses, gated on the stored capability flags rather than any
    answer of this run's own.

    `self.config_entry` (from `config_entries.OptionsFlow`) resolves via `self.hass`
    and the flow-manager-assigned entry id, neither of which is set yet inside
    `__init__`. This class therefore defines no `__init__` and only reads
    `self.config_entry` from step methods, which always run after initialization --
    `_answers` (declared on the mixin) is likewise only ever assigned from `async_step_init`.
    """

    _table = OPTIONS_TABLE

    async def async_step_init(self, user_input=None):
        """UC12 1b's entry point (ADR-0025 point 4): renders no form of its own, walks
        straight into the table."""
        self._mode = FlowMode.OPTIONS
        self._answers = {}
        return await self._async_advance(after=None)

    async def async_step_solar(self, user_input=None):
        """UC12 step 3, threshold half only -- no mapping fields, and no once-only ev_soc
        rule to evaluate (that's a config-flow-only concern). Design D-4: `defaults` prefills
        from the stored options directly, unlike the config flow's `add_suggested_values_to_schema`
        prefill -- this preserves the flat options flow's existing re-submission behaviour."""
        schema = _solar_threshold_schema(self.config_entry.options)
        if user_input is None:
            return self.async_show_form(step_id=STEP_SOLAR, data_schema=schema)
        self._answers.update(user_input)
        return await self._async_advance(after=STEP_SOLAR)

    async def async_step_captar(self, user_input=None):
        """UC12 step 4, threshold half only."""
        schema = _captar_threshold_schema(self.config_entry.options)
        if user_input is None:
            return self.async_show_form(step_id=STEP_CAPTAR, data_schema=schema)
        self._answers.update(user_input)
        return await self._async_advance(after=STEP_CAPTAR)

    async def async_step_deadline(self, user_input=None):
        """UC12 step 5, threshold half only."""
        schema = _deadline_threshold_schema(self.config_entry.options)
        if user_input is None:
            return self.async_show_form(step_id=STEP_DEADLINE, data_schema=schema)
        self._answers.update(user_input)
        return await self._async_advance(after=STEP_DEADLINE)

    async def async_step_thresholds(self, user_input=None):
        """UC12 step 8 -- always shown (ungated), and the one step that also asks the
        control interval (UC12 1b's own carve-out: install/reconfigure never ask it)."""
        schema = _ungated_threshold_schema(self.config_entry.options, include_interval=True)
        if user_input is None:
            return self.async_show_form(step_id=STEP_THRESHOLDS, data_schema=schema)
        self._answers.update(user_input)
        return await self._async_advance(after=STEP_THRESHOLDS)

    # --- T3: the five genuinely-new topic steps' threshold-only counterparts, plus
    # `async_step_core` (design "Options table": `core` IS a NINE_STEP_OPTIONS_TABLE row,
    # unlike the config table -- the options flow's own entry point, async_step_init,
    # renders no form of its own, so this method must exist for that table's own
    # reachability obligation, plan T3). None of these six is reachable from OPTIONS_TABLE
    # yet -- `_table` still points at the live table above; T7's cut-over is what points
    # `_table` at NINE_STEP_OPTIONS_TABLE and makes them reachable.

    async def async_step_core(self, user_input=None):
        """UC12 (topic-step) 1b, options-table row 1: the smoothing window + the control
        interval (UC12 1b's own carve-out -- install/reconfigure never ask it; design
        "Options table")."""
        schema = _core_threshold_schema(self.config_entry.options, include_interval=True)
        if user_input is None:
            return self.async_show_form(step_id=STEP_CORE, data_schema=schema)
        self._answers.update(user_input)
        return await self._async_advance(after=STEP_CORE)

    async def async_step_grid(self, user_input=None):
        """UC12 (topic-step) step 2, threshold half only -- always shown."""
        schema = _grid_threshold_schema(self.config_entry.options)
        if user_input is None:
            return self.async_show_form(step_id=STEP_GRID, data_schema=schema)
        self._answers.update(user_input)
        return await self._async_advance(after=STEP_GRID)

    async def async_step_ev_charger(self, user_input=None):
        """UC12 (topic-step) step 3, threshold half only -- always shown."""
        schema = _ev_charger_threshold_schema(self.config_entry.options)
        if user_input is None:
            return self.async_show_form(step_id=STEP_EV_CHARGER, data_schema=schema)
        self._answers.update(user_input)
        return await self._async_advance(after=STEP_EV_CHARGER)

    async def async_step_vehicle(self, user_input=None):
        """UC12 (topic-step) step 4, threshold half only -- always shown."""
        schema = _vehicle_threshold_schema(self.config_entry.options)
        if user_input is None:
            return self.async_show_form(step_id=STEP_VEHICLE, data_schema=schema)
        self._answers.update(user_input)
        return await self._async_advance(after=STEP_VEHICLE)

    async def async_step_power(self, user_input=None):
        """UC12 (topic-step) step 5, threshold half only -- always shown (unlike the config
        flow's own `power` step, the options flow never gates it on flow mode)."""
        schema = _power_threshold_schema(self.config_entry.options)
        if user_input is None:
            return self.async_show_form(step_id=STEP_POWER, data_schema=schema)
        self._answers.update(user_input)
        return await self._async_advance(after=STEP_POWER)

    async def async_step_notifications(self, user_input=None):
        """UC12 (topic-step) step 9, threshold half only -- gated on the *stored*
        notifications capability (design "Options table")."""
        schema = _notifications_threshold_schema(self.config_entry.options)
        if user_input is None:
            return self.async_show_form(step_id=STEP_NOTIFICATIONS, data_schema=schema)
        self._answers.update(user_input)
        return await self._async_advance(after=STEP_NOTIFICATIONS)

    async def _async_finish(self) -> config_entries.ConfigFlowResult:
        """UC12 1b: merge this run's answers into the stored options, never replace them
        wholesale (design, "The terminal step and the bucket split"). `OptionsFlow.
        async_create_entry` replaces `entry.options` outright, and this run's accumulator is
        deliberately narrower than the stored bucket whenever a capability is gated off --
        replacing rather than merging would silently delete that capability's thresholds the
        first time Configure is opened after withdrawing it through reconfigure (R20 AC7)."""
        intersection = {k: self._answers[k] for k in OPTION_KEYS if k in self._answers}
        # Not OPTION_KEYS-intersected like every other key above: control_interval_s is
        # deliberately not an OPTION_KEYS member (design, "The terminal step and the bucket
        # split"). Membership-guarded rather than direct indexing anyway, matching every
        # other key's defensive style here, even though the unconditional `thresholds` gate
        # makes the key's absence unreachable today.
        if CONF_CONTROL_INTERVAL_S in self._answers:
            intersection[CONF_CONTROL_INTERVAL_S] = self._answers[CONF_CONTROL_INTERVAL_S]
        return self.async_create_entry(title="", data={**self.config_entry.options, **intersection})
