"""Capability-Gate engine (E9). Pure — no HA imports.

R18's runtime available-mode set: Off and Power are always available; Solar/SolarOnly
require solar_available; Captar requires captar_available. This is the runtime
counterpart to select.py's entity-definition-time option list — both read the same
SOLAR_CAPABLE_MODES/CAPTAR_CAPABLE_MODES tuples (const.py) so the two questions can never
drift apart. This function exists so the Auto profile (E2) can ask the identical question
without a config-flow dependency.
"""

from ..const import (
    BASE_CAPABLE_MODES,
    CAPTAR_CAPABLE_MODES,
    SOLAR_CAPABLE_MODES,
)


def resolve_available_modes(solar_available: bool, captar_available: bool) -> frozenset[str]:
    """Return the set of modes available this cycle (R18)."""
    modes = set(BASE_CAPABLE_MODES)
    if solar_available:
        modes.update(SOLAR_CAPABLE_MODES)
    if captar_available:
        modes.update(CAPTAR_CAPABLE_MODES)
    return frozenset(modes)
