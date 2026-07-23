"""Capability-Gate engine (E9). Pure — no HA imports.

R18's runtime available-mode set: Off and Power are always available; Solar/SolarOnly
require solar_available; Captar requires captar_available. This is the runtime
counterpart to select.py's entity-definition-time option list (built directly from the
same two config booleans) — it exists so the Auto profile (E2) can ask the identical
question without a config-flow dependency.
"""

from custom_components.smart_charging.const import (
    MODE_CAPTAR,
    MODE_OFF,
    MODE_POWER,
    MODE_SOLAR,
    MODE_SOLAR_ONLY,
)


def resolve_available_modes(solar_available: bool, captar_available: bool) -> frozenset[str]:
    """Return the set of modes available this cycle (R18)."""
    modes = {MODE_OFF, MODE_POWER}
    if solar_available:
        modes |= {MODE_SOLAR, MODE_SOLAR_ONLY}
    if captar_available:
        modes.add(MODE_CAPTAR)
    return frozenset(modes)
