"""Plain-pytest tests for the Auto profile's mode-selection (E2, R16)."""

from custom_components.smart_charging.const import MODE_CAPTAR, MODE_OFF, MODE_POWER, MODE_SOLAR
from custom_components.smart_charging.profiles.auto import select_mode

BASE = dict(
    soc=50.0,
    active_soc_limit=80.0,
    urgent=False,
    solar_capability_present=True,
    sun_is_up=False,
    solar_surplus_sufficient=False,
    sun_is_down=True,
    low_tariff_active=True,
    solar_reserve_active=False,
)


def test_row1_soc_at_limit_selects_off():
    modes = frozenset({MODE_OFF, MODE_POWER})
    assert select_mode(**{**BASE, "soc": 80.0}, available_modes=modes) == MODE_OFF


def test_row2_urgent_escalates_to_captar_when_available():
    modes = frozenset({MODE_OFF, MODE_POWER, MODE_CAPTAR})
    assert select_mode(**{**BASE, "urgent": True}, available_modes=modes) == MODE_CAPTAR


def test_row2_urgent_falls_back_to_power_when_captar_unavailable():
    modes = frozenset({MODE_OFF, MODE_POWER})
    assert select_mode(**{**BASE, "urgent": True}, available_modes=modes) == MODE_POWER


def test_row3_solar_surplus_selects_solar():
    modes = frozenset({MODE_OFF, MODE_POWER, MODE_SOLAR})
    kwargs = {**BASE, "sun_is_up": True, "solar_surplus_sufficient": True, "sun_is_down": False}
    assert select_mode(**kwargs, available_modes=modes) == MODE_SOLAR


def test_row4_overnight_top_up_selects_captar():
    modes = frozenset({MODE_OFF, MODE_POWER, MODE_CAPTAR})
    assert select_mode(**BASE, available_modes=modes) == MODE_CAPTAR


def test_row4_withheld_when_captar_unavailable_falls_to_off():
    # R18: absent CapTar, row 4 never matches -- falls through to row 5 (Off), NOT Power.
    modes = frozenset({MODE_OFF, MODE_POWER})
    assert select_mode(**BASE, available_modes=modes) == MODE_OFF


def test_row4_withheld_when_solar_reserve_active():
    modes = frozenset({MODE_OFF, MODE_POWER, MODE_CAPTAR})
    assert select_mode(**{**BASE, "solar_reserve_active": True}, available_modes=modes) == MODE_OFF


def test_row4_withheld_when_low_tariff_inactive():
    modes = frozenset({MODE_OFF, MODE_POWER, MODE_CAPTAR})
    assert select_mode(**{**BASE, "low_tariff_active": False}, available_modes=modes) == MODE_OFF


def test_row5_otherwise_off():
    modes = frozenset({MODE_OFF, MODE_POWER})
    kwargs = {**BASE, "sun_is_down": False, "low_tariff_active": False}
    assert select_mode(**kwargs, available_modes=modes) == MODE_OFF


def test_row3_never_selects_solar_without_the_capability():
    # available_modes already excludes Solar when the capability is absent (E9), but this
    # also asserts the row's own solar_capability_present guard independently.
    modes = frozenset({MODE_OFF, MODE_POWER})
    kwargs = {
        **BASE,
        "solar_capability_present": False,
        "sun_is_up": True,
        "solar_surplus_sufficient": True,
        "sun_is_down": False,
    }
    assert select_mode(**kwargs, available_modes=modes) != MODE_SOLAR


def test_row1_wins_over_row2_even_when_urgent():
    # First-match-wins (resolution-rules.md/design doc §8): a full battery (row 1)
    # still selects Off even if the deadline is simultaneously urgent (row 2) --
    # a full battery does not charge just because a deadline is close.
    modes = frozenset({MODE_OFF, MODE_POWER, MODE_CAPTAR})
    kwargs = {**BASE, "soc": 80.0, "urgent": True}
    assert select_mode(**kwargs, available_modes=modes) == MODE_OFF


def test_row2_wins_over_row3_even_during_a_solar_eligible_window():
    # First-match-wins: an urgent deadline (row 2) escalates to Captar/Power even
    # when row 3's solar-surplus condition also holds -- it never falls through to Solar.
    modes = frozenset({MODE_OFF, MODE_POWER, MODE_CAPTAR, MODE_SOLAR})
    kwargs = {
        **BASE,
        "urgent": True,
        "sun_is_up": True,
        "solar_surplus_sufficient": True,
        "sun_is_down": False,
    }
    assert select_mode(**kwargs, available_modes=modes) == MODE_CAPTAR
