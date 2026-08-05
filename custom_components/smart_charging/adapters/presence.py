"""Presence (car_home) read adapter: maps a presence entity's state to a bool (ADR-0003)."""

from homeassistant.const import STATE_HOME, STATE_ON

from ._read_only import _ReadOnlyAdapter

_HOME_STATES = (STATE_HOME, STATE_ON)


class PresenceReadAdapter(_ReadOnlyAdapter):
    """Reads a presence/device_tracker/binary_sensor entity as car-at-home (True/False).

    None when the entity is missing/unavailable/unknown -- for this role that is not the
    ADR-0007 fault path (M2 is outside the control cycle); the Manager treats None as
    "cannot confirm presence" and suppresses a System write (design §9.1 alternative).

    Any other state (e.g. a `person` entity's named zone, or a garbage state) reads as
    False -- deliberately, unlike `BooleanReadAdapter`'s None-for-unrecognized-state: a
    zone that isn't "home" is still "not at home" for the C2 gate this role backs.
    """

    async def read(self) -> bool | None:
        state = self._live_state()
        if state is None:
            return None
        return state.state in _HOME_STATES
