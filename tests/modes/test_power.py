"""Plain-pytest tests for the Power charging mode (E1 slice)."""

from custom_components.smart_charging.const import (
    STATE_CHARGING,
    STATE_CONNECTED,
    STATE_DISCONNECTED,
)
from custom_components.smart_charging.modes.power import desired_current


def test_power_commands_target_when_charging():
    assert desired_current(target_current=10.0, status=STATE_CHARGING) == 10.0


def test_power_commands_target_when_connected():
    assert desired_current(target_current=8.0, status=STATE_CONNECTED) == 8.0


def test_power_commands_zero_when_disconnected():
    assert desired_current(target_current=10.0, status=STATE_DISCONNECTED) == 0.0
