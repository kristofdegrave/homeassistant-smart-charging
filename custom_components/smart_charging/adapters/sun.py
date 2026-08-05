"""Sun-state adapter (ADR-0003 extension, issue #376).

Unlike every other role, `sun.sun` needs no config-flow entity mapping -- it is a core
Home Assistant entity, always present once the (auto-loaded) `sun` integration is set up.
The factory builds this adapter unconditionally, the same way it builds the four
always-required roles.
"""

from homeassistant.core import HomeAssistant

from ._read_only import _ReadOnlyAdapter

SUN_ENTITY_ID = "sun.sun"
# HA's own sun.sun states.
SUN_STATE_ABOVE_HORIZON = "above_horizon"
SUN_STATE_BELOW_HORIZON = "below_horizon"


class SunReadAdapter(_ReadOnlyAdapter):
    """Reads `sun.sun`'s raw state, or None if missing/unavailable/unknown -- the
    ADR-0007 fault signal, same as every other read adapter, though the sun role is never
    itself fault-gated (NF4-style: the coordinator's own call site treats a None reading as
    neither `sun_is_up` nor `sun_is_down` holding)."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(hass, SUN_ENTITY_ID)

    async def read(self) -> str | None:
        state = self._live_state()
        if state is None:
            return None
        return state.state
