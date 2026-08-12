"""HA-harness tests for SmartChargingEntity's label-application mechanism (C5, #601).

`tests/test_entity.py` stays plain pytest (no `hass`) -- it only exercises the pure
`_object_id_suffix`/`unique_id` derivation. Label application needs the entity registry and a
real `async_added_to_hass` call, so it lives here instead.
"""

from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.restore_state import RestoreEntity
from pytest_homeassistant_custom_component.common import (
    MockEntityPlatform,
    mock_restore_cache_with_extra_data,
)

from custom_components.smart_charging.const import LABEL_SC_RUNTIME
from custom_components.smart_charging.entity import SmartChargingEntity

_OTHER_LABEL = "some_other_label"


class _LabelledEntity(SmartChargingEntity):
    _object_id_suffix = "labelled"
    _owned_labels = frozenset({LABEL_SC_RUNTIME})


class _UnlabelledEntity(SmartChargingEntity):
    _object_id_suffix = "unlabelled"


class _RestoringLabelledEntity(SmartChargingEntity, RestoreEntity):
    """Mirrors the real shape of every restore-capable owned entity: `SmartChargingEntity`
    first in the MRO, `RestoreEntity` after it -- the exact ordering issue #1 of the
    impl-spec-reviewer's Critical findings was about."""

    _object_id_suffix = "restoring_labelled"
    _owned_labels = frozenset({LABEL_SC_RUNTIME})

    def __init__(self, entry_id: str) -> None:
        super().__init__(entry_id)
        self.restored_state = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.restored_state = await self.async_get_last_state()


async def test_owned_labels_applied_on_add(hass):
    entity = _LabelledEntity(entry_id="entry1")
    platform = MockEntityPlatform(hass, domain="sensor")
    await platform.async_add_entities([entity])

    registry = er.async_get(hass)
    entry = registry.async_get(entity.entity_id)
    assert entry is not None
    assert entry.labels == {LABEL_SC_RUNTIME}


async def test_default_owned_labels_is_empty(hass):
    entity = _UnlabelledEntity(entry_id="entry1")
    platform = MockEntityPlatform(hass, domain="sensor")
    await platform.async_add_entities([entity])

    registry = er.async_get(hass)
    entry = registry.async_get(entity.entity_id)
    assert entry is not None
    assert entry.labels == set()


async def test_owned_labels_merge_with_a_users_own_label(hass):
    """`async_update_entity`'s `labels` parameter replaces the stored set -- a bare assignment
    would silently erase a label the user attached themselves on the next reload."""
    registry = er.async_get(hass)
    entity = _LabelledEntity(entry_id="entry1")
    platform = MockEntityPlatform(hass, domain="sensor")
    await platform.async_add_entities([entity])
    registry.async_update_entity(entity.entity_id, labels={_OTHER_LABEL})

    # Re-fire the mechanism directly (simulating a second add on reload).
    await entity.async_added_to_hass()

    entry = registry.async_get(entity.entity_id)
    assert entry.labels == {LABEL_SC_RUNTIME, _OTHER_LABEL}


async def test_async_added_to_hass_still_delegates_restore_state(hass):
    """Regression guard: a non-delegating `async_added_to_hass` override would silently break
    every existing RestoreEntity-mixing owned entity's restore-on-restart behavior."""
    entity_id = "sensor.smart_charging_restoring_labelled"
    mock_restore_cache_with_extra_data(hass, ((State(entity_id, "restored"), {}),))

    entity = _RestoringLabelledEntity(entry_id="entry1")
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="sensor")
    await platform.async_add_entities([entity])

    assert entity.restored_state is not None
    assert entity.restored_state.state == "restored"
