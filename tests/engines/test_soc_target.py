"""Plain-pytest tests for the SOC-Target engine (E3, row-3-only slice)."""

from custom_components.smart_charging.engines.soc_target import resolve_active_soc_limit


def test_resolves_to_the_configured_override():
    assert resolve_active_soc_limit(soc_limit_override=80.0) == 80.0


def test_tracks_a_changed_override():
    assert resolve_active_soc_limit(soc_limit_override=65.0) == 65.0
