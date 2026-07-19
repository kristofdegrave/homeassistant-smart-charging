"""Plain-pytest tests for the Grid-Safety engine (E6)."""

from custom_components.smart_charging.engines.grid_safety import clamp_to_ceiling


def test_c4_no_clamp_when_headroom_exceeds_request():
    # Ceiling 25 A @230 V, offset 2 A; household baseline = net 2300 W - charger 0 W = 10 A.
    # Headroom = (25 - 2) - 10 = 13 A; a 10 A request is untouched.
    assert clamp_to_ceiling(
        desired_current=10.0, net_w=2300.0, charger_w=0.0, voltage=230.0,
        ceiling_a=25.0, offset_a=2.0,
    ) == 10.0


def test_c4_clamps_request_to_headroom_below_ceiling_minus_offset():
    # Charger already drawing 3680 W (16 A); net 5980 W. Baseline = 5980 - 3680 = 2300 W = 10 A.
    # Headroom = (ceiling 25 - offset 2) - 10 = 13 A. A 20 A request clamps to 13 A.
    result = clamp_to_ceiling(
        desired_current=20.0, net_w=5980.0, charger_w=3680.0, voltage=230.0,
        ceiling_a=25.0, offset_a=2.0,
    )
    assert result == 13.0


def test_c4_headroom_floored_to_whole_ampere():
    # Baseline 3000 W / 230 V = 13.043 A. Headroom = 23 - 13.043 = 9.956 A -> floored to 9 A,
    # so an EVSE that rounds the setpoint up cannot overshoot the C4 safety headroom (MVP-added
    # conservative rounding; no requirement mandates a whole-ampere C4 command).
    result = clamp_to_ceiling(
        desired_current=20.0, net_w=3000.0, charger_w=0.0, voltage=230.0,
        ceiling_a=25.0, offset_a=2.0,
    )
    assert result == 9.0


def test_c4_negative_headroom_when_baseline_exceeds_ceiling():
    # Household already over the ceiling with no charger draw: headroom is negative.
    # The engine returns the (negative) headroom; the cycle-invariant stage turns it into a stop.
    result = clamp_to_ceiling(
        desired_current=10.0, net_w=6900.0, charger_w=0.0, voltage=230.0,
        ceiling_a=25.0, offset_a=2.0,
    )
    assert result <= 0.0


def test_c4_net_export_increases_headroom_beyond_ceiling():
    # Household exporting 2000 W (net negative), no charger draw: baseline = -2000 W = -8.69 A.
    # Headroom = (25 - 2) - (-8.69) = 31.69 A -> floored to 31 A; well above the request.
    result = clamp_to_ceiling(
        desired_current=16.0, net_w=-2000.0, charger_w=0.0, voltage=230.0,
        ceiling_a=25.0, offset_a=2.0,
    )
    assert result == 16.0
