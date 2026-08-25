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
    ERROR_REQUIRED_WHEN_DEADLINE_AVAILABLE,
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
    STEP_NOTIFICATIONS,
    STEP_POWER,
    STEP_SOLAR,
    STEP_THRESHOLDS,
    STEP_VEHICLE,
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


# UC12's fixed nine-step order, table rows only (`core` excluded -- it is the shared entry
# point both async_step_user/async_step_reconfigure delegate into, ADR-0027 point 5, design
# "Step ids and the two tables"). Eight ids, `captar` before `solar` (ADR-0027, Consequences).
# A documentation/cross-check aid for whoever adds a row (R20 AC9's extensibility criterion),
# not a runtime dependency of the dispatcher -- CONFIG_TABLE's own order is what the dispatcher
# actually walks.
UC12_FIXED_STEP_ORDER = (
    STEP_GRID,
    STEP_EV_CHARGER,
    STEP_VEHICLE,
    STEP_POWER,
    STEP_CAPTAR,
    STEP_SOLAR,
    STEP_DEADLINE,
    STEP_NOTIFICATIONS,
)

# The config flow's own table (ADR-0027 Option C; T4 cut-over -- topic-step plan). Install and
# reconfigure share this one table (ADR-0027 point 3/5): `power`/`captar` have no mapping half
# at all, so both are gated off entirely in reconfigure mode (a per-step gate, not a stop
# condition, because both sit in the *middle* of the fixed order). `solar`/`deadline`/
# `notifications` are gated on this run's own answer from the `core` step; `grid`/`ev_charger`/
# `vehicle` are always shown.
CONFIG_TABLE: tuple[FlowStep, ...] = (
    FlowStep(step_id=STEP_GRID, gate=lambda flow: True),
    FlowStep(step_id=STEP_EV_CHARGER, gate=lambda flow: True),
    FlowStep(step_id=STEP_VEHICLE, gate=lambda flow: True),
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

# The options flow's own table (ADR-0025 point 3, untouched by T4 -- T7's concern): threshold
# halves only, no `core`/`mappings`/`vehicle_limit` rows (mapping fields never appear here --
# ADR-0005 restricts this flow to the options bucket). Gated on the *stored* capability flags
# (`self.config_entry.data`), never this run's own answers -- the options flow never re-asks a
# capability, only its thresholds. Every gate reads defensively via `.get(key, DEFAULT_*)`,
# never bracket indexing: `deadline_available` is a key this slice introduces (D-1) and is
# absent from every entry written before it, so `entry.data[CONF_DEADLINE_AVAILABLE]` would
# KeyError on the first Configure a pre-slice entry ever opens.
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

# Interim-named (topic-step plan T3): the options flow's own nine-topic-step table, not yet
# wired into `SmartChargingOptionsFlow._table` -- OPTIONS_TABLE above still is, until T7
# renames this to OPTIONS_TABLE (deleting the one above) the same way T4 renamed
# NINE_STEP_CONFIG_TABLE to CONFIG_TABLE. `core` IS a row here (unlike CONFIG_TABLE), because
# the options flow's own entry point, async_step_init, renders no form of its own. Gated on
# the *stored* capability flags, defensively (`.get(key, DEFAULT_*)`): `notifications_available`
# is a key this slice introduces and is absent from every entry written before it.
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
        # R20 AC1 / design D-1's success criterion: the four capability declarations and
        # nothing else -- every other field this fragment used to carry (the charger/grid
        # mappings, the transient vehicle-limit election) now lives on its own topic step
        # (`grid`/`ev_charger`/`vehicle`).
        # Form default True (R20 AC1's "defaulting to present"; design D-5) -- deliberately
        # diverges from DEFAULT_SOLAR_AVAILABLE (False), which stays the absent-key read
        # fallback for an entry that predates this field.
        vol.Required(CONF_SOLAR_AVAILABLE, default=True): bool,
        vol.Required(CONF_CAPTAR_AVAILABLE, default=DEFAULT_CAPTAR_AVAILABLE): bool,
        vol.Required(CONF_DEADLINE_AVAILABLE, default=DEFAULT_DEADLINE_AVAILABLE): bool,
        # New capability (D-1); form default and absent-key read fallback agree (design D-5,
        # unlike solar's split) -- R18 AC9's default-absent exception.
        vol.Required(CONF_NOTIFICATIONS_AVAILABLE, default=DEFAULT_NOTIFICATIONS_AVAILABLE): bool,
    }
)


def _solar_threshold_schema(defaults: dict | None = None) -> vol.Schema:
    """UC12 (topic-step) step 7 threshold half."""
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


def _captar_threshold_schema(defaults: dict | None = None) -> vol.Schema:
    """UC12 (topic-step) step 6 threshold half -- CapTar has no mapping half at all (design
    field-to-step table): every mapping this step used to carry (`ev_soc_entity`) now lives
    on the always-shown `vehicle` step (R20 AC4's once-only rule)."""
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
        # UC12 5c / R20 AC5's named carve-out: the one ungated field a capability-gated step
        # carries.
        vol.Optional(CONF_HOME_DAY_EXTERNAL_ENTITY): _entity(["binary_sensor", "input_boolean"]),
    }
)


def _deadline_threshold_schema(defaults: dict | None = None) -> vol.Schema:
    """UC12 (topic-step) step 8 threshold half."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_REMINDER_LEAD_H,
                default=d.get(CONF_REMINDER_LEAD_H, DEFAULT_REMINDER_LEAD_H),
            ): vol.Coerce(float),
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


# --- The nine topic steps' schema fragments (ADR-0027, Consequences: "The schema fragments
# are re-cut along topic lines"; design "Schema fragments" table). CONFIG_TABLE above walks
# these; OPTIONS_TABLE still walks the older ADR-0025 fragments above until T7 re-cuts it.


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


def _car_home_missing_error(merged: dict) -> dict[str, str] | None:
    """UC12 4a / design D-3: car_home_entity is required when EITHER a vehicle charge limit
    is mapped OR the deadline capability is declared present -- two independent triggers, two
    error codes, so the message never contradicts the form the household is looking at. The
    charge-limit trigger is checked first, so a submission that trips both reports the one
    tied to the field just filled in on this same step (`vehicle_charge_limit_entity`) rather
    than the one answered earlier (`deadline_available`, on `core`) -- `merged` is
    `{**self._answers, **user_input}` so this guard can read both. `_ev_soc_missing_error`/
    `_solar_forecast_missing_error`, this guard's former siblings, are gone: both fields they
    guarded are now plain `vol.Required` (ADR-0027 point 1)."""
    if merged.get(CONF_CAR_HOME_ENTITY):
        return None
    if merged.get(CONF_VEHICLE_CHARGE_LIMIT_ENTITY):
        return {CONF_CAR_HOME_ENTITY: ERROR_REQUIRED_WHEN_VEHICLE_LIMIT_MAPPED}
    if merged.get(CONF_DEADLINE_AVAILABLE):
        return {CONF_CAR_HOME_ENTITY: ERROR_REQUIRED_WHEN_DEADLINE_AVAILABLE}
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
        """UC12 1a / ADR-0027 point 2: reconfigure prefills a step's rendered schema from the
        stored entry -- a rendering-only concern; the accumulator itself is never seeded
        (install renders `schema` unchanged). `extra_from(entry.data)` augments the prefill
        source for the one field with no stored key of its own -- the `core` step's
        `notifications_available` prefill (design D-7)."""
        if self._mode is not FlowMode.RECONFIGURE:
            return schema
        entry = self._get_reconfigure_entry()
        source = (entry.data | extra_from(entry.data)) if extra_from else entry.data
        return self.add_suggested_values_to_schema(schema, source)

    async def async_step_core(self, user_input=None):
        """UC12 (topic-step) step 1: the four capability decisions + the smoothing-window
        threshold (design field-to-step table). D-7: on reconfigure, `notifications_available`
        is prefilled from a stored flag when present, else derived from whether a notify
        target is already mapped -- an entry that predates the key must not silently drop
        that mapping the moment `_split_data` writes a narrower data bucket."""
        schema = CORE_MAPPING_SCHEMA
        if self._mode is not FlowMode.RECONFIGURE:
            schema = schema.extend(_core_threshold_schema().schema)
        if user_input is None:
            schema = self._maybe_prefill(
                schema,
                extra_from=lambda data: {
                    CONF_NOTIFICATIONS_AVAILABLE: data.get(
                        CONF_NOTIFICATIONS_AVAILABLE,
                        bool(data.get(CONF_NOTIFICATION_TARGET_ENTITY)),
                    )
                },
            )
            return self.async_show_form(step_id=STEP_CORE, data_schema=schema)

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_CORE)

    async def async_step_grid(self, user_input=None):
        """UC12 (topic-step) step 2: the grid-connection mapping + threshold halves, always
        shown (design "Config table")."""
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
        (design D-2, R20 AC4) -- presented exactly once, whatever the capability
        declarations. Step-local guard (ADR-0027 point 1, design D-3): a missing car_home
        mapping re-shows this step with a field-local error, firing on either of UC12 4a's two
        independent triggers (`_car_home_missing_error`)."""
        schema = VEHICLE_MAPPING_SCHEMA
        if self._mode is not FlowMode.RECONFIGURE:
            schema = schema.extend(_vehicle_threshold_schema().schema)
        if user_input is None:
            return self.async_show_form(
                step_id=STEP_VEHICLE, data_schema=self._maybe_prefill(schema)
            )

        merged = {**self._answers, **user_input}
        errors = _car_home_missing_error(merged)
        if errors:
            return self.async_show_form(
                step_id=STEP_VEHICLE,
                data_schema=self.add_suggested_values_to_schema(schema, user_input),
                errors=errors,
            )

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_VEHICLE)

    async def async_step_power(self, user_input=None):
        """UC12 (topic-step) step 5: threshold-only, no mapping half (design "Schema
        fragments"). CONFIG_TABLE's own gate keeps this step out of reconfigure -- no
        `self._mode` check is needed in the method body itself."""
        schema = _power_threshold_schema()
        if user_input is None:
            return self.async_show_form(step_id=STEP_POWER, data_schema=schema)

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_POWER)

    async def async_step_captar(self, user_input=None):
        """UC12 (topic-step) step 6: threshold-only, no mapping half (design field-to-step
        table) -- gated on CapTar declared this run AND mode is not reconfigure
        (CONFIG_TABLE's own gate), so this step is unreachable during reconfigure and needs
        neither `self._mode` branching nor `_maybe_prefill` in its own body."""
        schema = _captar_threshold_schema()
        if user_input is None:
            return self.async_show_form(step_id=STEP_CAPTAR, data_schema=schema)

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_CAPTAR)

    async def async_step_solar(self, user_input=None):
        """UC12 (topic-step) step 7: the solar mapping + threshold halves, gated on solar
        declared this run (design "Config table"). `solar_forecast_entity` is `vol.Required`
        on SOLAR_MAPPING_SCHEMA (design D-2) -- the once-only `_solar_forecast_missing_error`
        guard it replaced is gone; HA's own schema validation rejects a missing value and
        re-shows this step."""
        schema = SOLAR_MAPPING_SCHEMA
        if self._mode is not FlowMode.RECONFIGURE:
            schema = schema.extend(_solar_threshold_schema().schema)
        if user_input is None:
            return self.async_show_form(step_id=STEP_SOLAR, data_schema=self._maybe_prefill(schema))

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_SOLAR)

    async def async_step_deadline(self, user_input=None):
        """UC12 (topic-step) step 8: the departure-time mapping (+ the home-day carve-out,
        R20 AC5) + reminder-lead threshold, gated on deadline declared this run (design
        "Config table"). No step-local guard: UC12 marks neither field required (R18 AC7)."""
        schema = DEADLINE_MAPPING_SCHEMA
        if self._mode is not FlowMode.RECONFIGURE:
            schema = schema.extend(_deadline_threshold_schema().schema)
        if user_input is None:
            return self.async_show_form(
                step_id=STEP_DEADLINE, data_schema=self._maybe_prefill(schema)
            )

        self._answers.update(user_input)
        return await self._async_advance(after=STEP_DEADLINE)

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

    async def _async_finish(self) -> config_entries.ConfigFlowResult:
        """UC12 step 10 (install) / 1a (reconfigure): create or update the entry. Reconfigure
        touches the data bucket only (ADR-0005) and reloads (ADR-0008); it never computes
        `options` at all -- neither `power` nor `captar` is reachable in this mode
        (CONFIG_TABLE's own gates), so no threshold answer ever entered `self._answers` to
        intersect."""
        data = _split_data(self._answers)
        if self._mode is FlowMode.RECONFIGURE:
            entry = self._get_reconfigure_entry()
            return self.async_update_reload_and_abort(entry, data=data)
        # Intersection, not direct indexing (ADR-0027, Consequences): a capability declared
        # absent this run never renders its step, so its OPTION_KEYS members are absent from
        # self._answers -- direct indexing would KeyError the moment any capability is off.
        options = {k: self._answers[k] for k in OPTION_KEYS if k in self._answers}
        options[CONF_CONTROL_INTERVAL_S] = DEFAULT_CONTROL_INTERVAL_S
        return self.async_create_entry(title="Smart Charging", data=data, options=options)

    async def async_step_reconfigure(self, user_input=None):
        """UC12 1a's reconfigure entry point (ADR-0027 point 5): delegate into the shared
        `core` step, framework-imposed name aside -- the same shared step methods and table
        install uses, with `self._mode` alone selecting each step's mapping-only render
        (`_maybe_prefill`), the `power`/`captar` rows' skip, and `_async_finish`'s terminal
        branch. No guard logic of its own: `_car_home_missing_error` is already step-local and
        runs unconditionally regardless of `self._mode`."""
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

    # --- Topic-step plan T3: the five genuinely-new topic steps' threshold-only counterparts, plus
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
