"""Plain-pytest tests for the Capability-Gate Engine (E9, R18)."""

from custom_components.smart_charging.const import (
    MODE_CAPTAR,
    MODE_OFF,
    MODE_POWER,
    MODE_SOLAR,
    MODE_SOLAR_ONLY,
)
from custom_components.smart_charging.engines.capability_gate import resolve_available_modes


def test_neither_capability_only_off_and_power():
    modes = resolve_available_modes(solar_available=False, captar_available=False)
    assert modes == {MODE_OFF, MODE_POWER}


def test_solar_only_adds_both_solar_modes():
    modes = resolve_available_modes(solar_available=True, captar_available=False)
    assert modes == {MODE_OFF, MODE_POWER, MODE_SOLAR, MODE_SOLAR_ONLY}


def test_captar_only_adds_captar():
    modes = resolve_available_modes(solar_available=False, captar_available=True)
    assert modes == {MODE_OFF, MODE_POWER, MODE_CAPTAR}


def test_both_capabilities_present_offers_everything():
    modes = resolve_available_modes(solar_available=True, captar_available=True)
    assert modes == {MODE_OFF, MODE_POWER, MODE_SOLAR, MODE_SOLAR_ONLY, MODE_CAPTAR}
