"""Tests for SmartChargingEntity's object_id pin (ADR-0013)."""

from custom_components.smart_charging.entity import SmartChargingEntity


def test_suggested_object_id_falls_back_when_unset():
    """Undecorated entities keep HA's default (translated-name-derived) behavior. This
    passes already — Entity.suggested_object_id gracefully returns None for an entity with
    no platform/name set — and is here to lock in that pre-existing fallback behavior."""
    entity = SmartChargingEntity(entry_id="test_entry")
    assert entity.suggested_object_id is None


def test_suggested_object_id_returns_pinned_suffix_when_set():
    """ADR-0013: a subclass pinning `_object_id_suffix` overrides the translated-name
    default, decoupling the registered object_id from the display name. This is the one
    that actually fails until the override is implemented."""
    entity = SmartChargingEntity(entry_id="test_entry")
    entity._object_id_suffix = "soc_limit_override"
    assert entity.suggested_object_id == "soc_limit_override"
