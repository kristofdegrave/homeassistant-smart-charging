"""Plain-pytest tests for the Manual profile's mode-selection pass-through (E2, ADR-0017, R16)."""

import pytest

from custom_components.smart_charging.const import MODE_CAPTAR, MODE_OFF, MODE_SOLAR
from custom_components.smart_charging.profiles.manual import ManualPolicy


@pytest.mark.parametrize("mode", [MODE_OFF, MODE_SOLAR, MODE_CAPTAR])
def test_select_returns_active_mode_unchanged(mode):
    """resolution-rules.md: "Manual needs no table" -- a pure pass-through of the user's own
    selection (R16's acceptance criterion), proven across every representative mode
    (design doc §5), not just one."""
    assert ManualPolicy().select(active_mode=mode) == mode


def test_select_ignores_every_other_kwarg():
    """Manual's own contract: no automatic mode change regardless of observable conditions
    (R16's Manual criterion, requirements.md; NF1's general no-automatic-changes rule
    applies via its own parenthetical) -- proven here by passing Auto's full kwarg set
    alongside active_mode and confirming none of it changes the result."""
    result = ManualPolicy().select(
        active_mode=MODE_OFF,
        urgent=True,
        soc=10.0,
        active_soc_limit=80.0,
        available_modes=frozenset({MODE_OFF, MODE_CAPTAR}),
        solar_capability_present=True,
        sun_is_up=True,
        solar_surplus_sufficient=True,
        sun_is_down=False,
        low_tariff_active=True,
        solar_reserve_active=True,
    )
    assert result == MODE_OFF
