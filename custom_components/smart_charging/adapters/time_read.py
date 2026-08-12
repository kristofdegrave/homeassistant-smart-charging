"""Time-of-day read adapter (ADR-0003 extension, RA2)."""

from datetime import time

from homeassistant.util import dt as dt_util

from ._read_only import _ReadOnlyAdapter


class TimeReadAdapter(_ReadOnlyAdapter):
    """Reads a time-of-day entity's native value.

    Added for the `departure_external` role (design doc §4 note): its mapped entity's
    native value is a `datetime.time`, not a float (`NumericReadAdapter`) or a
    user-translated canonical string (`StatusReadAdapter`). Neither existing class fits
    without being reshaped, so this is a new, minimal adapter class of the same shape
    ADR-0003 already establishes ("one class per role"), rather than repurposing
    either.

    Returns None when the entity is missing/unavailable/unknown OR its native state can't
    be parsed as a time (e.g. a source sensor currently reporting a non-time value like
    "no deadline") -- the ADR-0007 fault signal, same as every other read adapter, and
    also R14's own "external sensor currently reports no deadline" case.
    """

    async def read(self) -> time | None:
        state = self._live_state()
        if state is None:
            return None
        return dt_util.parse_time(state.state)
