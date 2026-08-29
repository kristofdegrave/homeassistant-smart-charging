"""Low-tariff adapter: normalizes a tariff signal to a boolean (ADR-0003, RA2 extension)."""

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from ._read_only import _ReadOnlyAdapter


class LowTariffReadAdapter(_ReadOnlyAdapter):
    """Reads the tariff signal and normalizes it to the boolean low-tariff flag.

    A raw state matching HA's native on/off vocabulary is checked *first* and used
    directly (the `binary_sensor`/`input_boolean` case, unchanged from
    `BooleanReadAdapter`'s prior behaviour) -- this takes precedence over
    `low_states` even if a raw `on`/`off` value were also listed there, which is
    never an ambiguity in practice since a native on/off entity has no other raw
    state to list. Otherwise `low_states` -- the user-supplied set of raw states
    that count as low tariff, parsed from the config-entry's raw comma-separated
    string (design doc SS2 -- kept as a string end-to-end so reconfigure prefill
    round-trips correctly) -- decides membership; any other raw state resolves to
    `False`. This is a deliberate, *restrictive* default for a present-but-unmatched
    state -- distinct from the glossary's *permissive* "always active" default for a
    genuinely unmapped or unavailable signal (entity-catalog.md; SS7's own deferred-
    asymmetry note). Returns `None` only when the entity itself is
    missing/unavailable/unknown -- the ADR-0007 fault signal proper.
    """

    def __init__(self, hass: HomeAssistant, entity_id: str, low_states: str) -> None:
        super().__init__(hass, entity_id)
        self._low_states = {s.strip() for s in low_states.split(",") if s.strip()}

    async def read(self) -> bool | None:
        state = self._live_state()
        if state is None:
            return None
        if state.state == STATE_ON:
            return True
        if state.state == STATE_OFF:
            return False
        return state.state in self._low_states
