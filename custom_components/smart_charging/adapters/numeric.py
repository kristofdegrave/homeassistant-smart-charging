"""Numeric read and read/write adapters (ADR-0003)."""

import logging

from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.const import ATTR_ENTITY_ID, ATTR_UNIT_OF_MEASUREMENT, Platform, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.util.unit_conversion import PowerConverter

from ._read_only import _ReadOnlyAdapter

_LOGGER = logging.getLogger(__name__)

# Distinct units one entity may be warned about before the adapter goes quiet (see
# `_PowerReadAdapter._warn_once`). Small: a correctly-mapped entity reports one unit
# forever, so reaching this at all means something is already badly wrong.
_MAX_WARNED_UNITS = 8


class NumericReadAdapter(_ReadOnlyAdapter):
    """Reads a numeric entity's native value; None if missing/unavailable/non-numeric.

    Carries no unit contract -- the value is whatever the entity reports. ADR-0038 covers
    only the power-valued roles; the remaining roles on this adapter (`grid_voltage` V,
    `ev_soc` %, `ev_battery_capacity` kWh, `solar_forecast` kWh, and via the read/write
    subclass below `charger_current` A and `vehicle_charge_limit` %) carry the same class of
    hazard and are named there as follow-up, each needing its own unit set decided.
    """

    async def read(self) -> float | None:
        state = self._live_state()
        if state is None:
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None


class _PowerReadAdapter(_ReadOnlyAdapter):
    """Shared implementation of ADR-0038's unit contract at the power-read boundary.

    Three cases, per that record:

    - a recognised power unit is converted to `_target_unit`;
    - an absent unit is either assumed to be `_target_unit` (with an *assumption* warning) or
      rejected (with a *rejection* warning), per `_assume_target_when_absent`;
    - a unit that is present but cannot be converted is always rejected, with a rejection
      warning -- unlike an absent unit, it is positive evidence of a mis-mapping.

    Warnings are emitted once per observed unit rather than once per read: the control cycle
    reads every role every cycle, so a per-read warning would be log spam that trains the user
    to ignore exactly the signal this contract exists to provide. Keying on the observed unit
    rather than the adapter's lifetime means an entity that starts reporting a *different*
    wrong unit still says so -- that is a new fact, not a repeat. The cost of that choice is a
    flapping unit, which `_MAX_WARNED_UNITS` bounds.
    """

    _target_unit: str
    _assume_target_when_absent: bool

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        super().__init__(hass, entity_id)
        self._warned_units: set[str | None] = set()

    def _warn_once(self, unit: str | None, message: str, *args: object) -> None:
        if unit in self._warned_units:
            return
        # Bounded: a template entity whose `unit_of_measurement` is itself templated can flap,
        # and keying on the unit would otherwise both grow this set without limit and warn
        # afresh each time. Past the cap the adapter stays silent rather than becoming the spam
        # the cadence rule exists to prevent -- by then the user has had several distinct
        # warnings naming this entity.
        if len(self._warned_units) >= _MAX_WARNED_UNITS:
            return
        self._warned_units.add(unit)
        _LOGGER.warning(message, *args)

    async def read(self) -> float | None:
        state = self._live_state()
        if state is None:
            return None
        try:
            value = float(state.state)
        except (ValueError, TypeError):
            return None

        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        # `unit is None` is tested FIRST, before the converter's own set: ADR-0038's carve-out
        # turns on the absent case specifically, and `PowerConverter.VALID_UNITS` is typed
        # `set[str | None]` -- some HA converters do include None in theirs. Power's does not
        # today, so the order is currently unobservable; testing it explicitly keeps the
        # contract resting on this module rather than on an HA-internal set's contents.
        if unit is None:
            if self._assume_target_when_absent:
                self._warn_once(
                    unit,
                    "%s reports no unit of measurement; assuming %s. Set a unit on that entity"
                    " if it is not in %s -- a wrong assumption here is silent.",
                    self._entity_id,
                    self._target_unit,
                    self._target_unit,
                )
                return value
            self._warn_once(
                unit,
                "%s reports no unit of measurement; reading discarded. This role is expected in"
                " %s and cannot be assumed, so it is treated as absent until the entity reports"
                " a unit.",
                self._entity_id,
                self._target_unit,
            )
            return None

        if unit in PowerConverter.VALID_UNITS:
            return PowerConverter.convert(value, unit, self._target_unit)

        # `PowerConverter.VALID_UNITS` is currently exactly `set(UnitOfPower)` -- every power
        # unit HA knows converts, including BTU/h -- so anything reaching here really is not a
        # power unit as HA spells them. The message still says "cannot be converted to" rather
        # than "is not a power unit" because it is the more actionable half: the common cause is
        # a near-miss spelling ("Watt", "w") on an otherwise-correct sensor, where "not a power
        # unit" reads as a wrong-entity diagnosis and sends the user looking in the wrong place.
        self._warn_once(
            unit,
            "%s reports unit %r, which cannot be converted to %s; reading discarded. Check the"
            " entity mapping, and check the unit string itself -- a near-miss spelling reads the"
            " same as a wrong quantity here.",
            self._entity_id,
            unit,
            self._target_unit,
        )
        return None


class PowerWattReadAdapter(_PowerReadAdapter):
    """Reads a power entity's value, normalised to W (ADR-0038).

    Used by `net_power`, `charger_power` and `solar_power`, whose documented unit is W. An
    absent unit is assumed to be W: a bare number is common and usually correct, and the two
    required roles here would fault under ADR-0007 if it were rejected, stopping charging on
    installations that are correct today.
    """

    _target_unit = UnitOfPower.WATT
    _assume_target_when_absent = True


class PowerKilowattReadAdapter(_PowerReadAdapter):
    """Reads a power entity's value, normalised to kW (ADR-0030; ADR-0038's carve-out).

    An absent unit reads as None rather than being assumed kW. This is the one role where the
    documented unit is *less* likely than the alternative when none is reported: ADR-0030
    records that DSO/smart-meter peak sensors commonly report in W, and a W value read as kW
    would produce a peak operand three orders of magnitude too large, pinning the effective
    peak limit at `max_peak_kw` via ADR-0032's `max(internal, external)` merge. The rejection
    is warned rather than silent, so the role does not vanish indistinguishably from unmapped.
    """

    _target_unit = UnitOfPower.KILO_WATT
    _assume_target_when_absent = False


class NumericReadWriteAdapter(NumericReadAdapter):
    """A numeric role that can also be written, via the number.set_value service."""

    async def write(self, value: float) -> None:
        await self._hass.services.async_call(
            Platform.NUMBER,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: self._entity_id, ATTR_VALUE: value},
            blocking=True,
        )
