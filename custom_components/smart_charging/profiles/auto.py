"""Auto profile mode-selection (E2). Pure -- no HA imports, no cross-engine calls.

`Manual` needs no module here (resolution-rules.md: "`Manual` needs no table"); the
coordinator already reads `select.smart_charging_mode` directly for that case.
"""

from ..const import MODE_CAPTAR, MODE_OFF, MODE_POWER, MODE_SOLAR


def select_mode(
    soc: float,
    active_soc_limit: float,
    available_modes: frozenset[str],
    urgent: bool,
    solar_capability_present: bool,
    sun_is_up: bool,
    solar_surplus_sufficient: bool,
    sun_is_down: bool,
    low_tariff_active: bool,
    solar_reserve_active: bool,
) -> str:
    """resolution-rules.md's Auto mode-selection table, rows 1-5, first match wins.

    1. soc >= active_soc_limit -> Off
    2. urgent -> Captar if MODE_CAPTAR in available_modes else Power
    3. solar_capability_present and sun_is_up and solar_surplus_sufficient -> Solar
    4. sun_is_down and low_tariff_active and not solar_reserve_active -> Captar
       (only reachable when MODE_CAPTAR in available_modes -- R18: absent CapTar,
       row 4 simply never matches, falling through to row 5, NOT a Power fallback)
    5. otherwise -> Off
    """
    if soc >= active_soc_limit:
        return MODE_OFF

    if urgent:
        return MODE_CAPTAR if MODE_CAPTAR in available_modes else MODE_POWER

    if solar_capability_present and sun_is_up and solar_surplus_sufficient:
        return MODE_SOLAR

    if (
        sun_is_down
        and low_tariff_active
        and not solar_reserve_active
        and MODE_CAPTAR in available_modes
    ):
        return MODE_CAPTAR

    return MODE_OFF
