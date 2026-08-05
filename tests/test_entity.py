"""Tests for SmartChargingEntity's object_id pin (ADR-0013)."""

from custom_components.smart_charging.entity import SmartChargingEntity


class _PinnedEntity(SmartChargingEntity):
    """A subclass pinning `_object_id_suffix`, matching how owned entities use it (a class
    attribute), rather than reaching into instance internals."""

    _object_id_suffix = "soc_limit_override"


def test_suggested_object_id_falls_back_when_unset():
    """Undecorated entities keep HA's default (translated-name-derived) behavior — the
    delegation half of the `or` in `suggested_object_id`. `_attr_name` is set so
    `Entity.suggested_object_id` returns a non-None value, distinguishing this from a
    weaker implementation that always returns `_object_id_suffix` verbatim."""
    entity = SmartChargingEntity(entry_id="test_entry")
    entity._attr_name = "Fallback Name"
    assert entity.suggested_object_id == "Fallback Name"


def test_suggested_object_id_returns_pinned_suffix_when_set():
    """ADR-0013: a subclass pinning `_object_id_suffix` overrides the translated-name
    default, decoupling the registered object_id from the display name. This is the one
    that actually fails until the override is implemented."""
    entity = _PinnedEntity(entry_id="test_entry")
    assert entity.suggested_object_id == "soc_limit_override"


def test_unique_id_derived_from_object_id_suffix():
    """Issue #507: unique_id is derived once from `_object_id_suffix` instead of every
    subclass hand-building `f"{entry_id}_{suffix}"` -- ADR-0013's only listed Con was
    keeping those two in sync by hand."""
    entity = _PinnedEntity(entry_id="test_entry")
    assert entity.unique_id == "test_entry_soc_limit_override"


def test_unique_id_is_none_when_no_object_id_suffix_is_set():
    """An entity that never pins `_object_id_suffix` gets no derived unique_id (it must
    set `_attr_unique_id` itself) rather than a nonsensical `"<entry_id>_None"`."""
    entity = SmartChargingEntity(entry_id="test_entry")
    assert entity.unique_id is None
