"""Shared base for read-only adapter roles (ADR-0003).

Every read-only role shares two things: the "missing/unavailable/unknown -> None"
state guard (the ADR-0007 fault signal) and a `write()` that always raises
`NotImplementedError` -- only the read-side mapping differs per role. This base
class removes both repeated pieces; subclasses only implement `read()` (typically
via `self._live_state()`).
"""

from __future__ import annotations

from datetime import time

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State


class _ReadOnlyAdapter:
    """Base for adapter roles that never accept a `write()`.

    `SunReadAdapter` has no config-flow-mapped entity id -- it passes its fixed
    `sun.sun` id through to `__init__` like any other role, so `_live_state()`
    stays a single shared implementation.
    """

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self._entity_id = entity_id

    def _live_state(self) -> State | None:
        """The entity's current state, or None if missing/unavailable/unknown --
        the ADR-0007 fault signal shared by every read adapter."""
        state = self._hass.states.get(self._entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        return state

    async def write(self, value: float | str | bool | time) -> None:
        raise NotImplementedError(f"{type(self).__name__} is read-only")
