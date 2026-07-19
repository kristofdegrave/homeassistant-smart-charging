"""Plain-pytest tests for the Signal-Conditioning engine (E7, voltage slice)."""

from custom_components.smart_charging.engines.signal_conditioning import resolve_voltage


def test_uses_measured_voltage_when_healthy():
    assert resolve_voltage(measured=235.0, nominal=230.0) == 235.0


def test_falls_back_to_nominal_when_missing():
    assert resolve_voltage(measured=None, nominal=230.0) == 230.0


def test_falls_back_to_nominal_when_non_positive():
    assert resolve_voltage(measured=0.0, nominal=230.0) == 230.0
    assert resolve_voltage(measured=-5.0, nominal=230.0) == 230.0
