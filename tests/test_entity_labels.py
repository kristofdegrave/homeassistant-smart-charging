"""HA-harness tests for SmartChargingEntity's registry-sync mechanisms (C5, #601; ADR-0028).

`tests/test_entity.py` stays plain pytest (no `hass`) -- it only exercises the pure
`_object_id_suffix`/`unique_id` derivation. Registry-state sync (labels, and per ADR-0028,
`disabled_by`) needs the entity registry, so it lives here instead. `sync_disabled_by` and
`sync_labels` are the two setup-time registry helpers ADR-0028 introduces to replace the
label-only mechanism this file used to test exclusively via a real `async_added_to_hass` call.
"""

from homeassistant.const import Platform
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.restore_state import RestoreEntity
from pytest_homeassistant_custom_component.common import (
    MockEntityPlatform,
    mock_restore_cache_with_extra_data,
)

from custom_components.smart_charging.const import DOMAIN, LABEL_SC_RUNTIME
from custom_components.smart_charging.entity import (
    SmartChargingEntity,
    sync_disabled_by,
    sync_labels,
)

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


async def test_sync_labels_applies_owned_labels(hass):
    """ADR-0028: sync_labels writes owned_labels onto a registered entity's row."""
    entity = _UnlabelledEntity(entry_id="entry1")
    platform = MockEntityPlatform(hass, domain=Platform.SENSOR, platform_name=DOMAIN)
    await platform.async_add_entities([entity])
    registry = er.async_get(hass)

    sync_labels(
        registry, Platform.SENSOR, entity.unique_id, owned_labels=frozenset({LABEL_SC_RUNTIME})
    )

    entry = registry.async_get(entity.entity_id)
    assert entry.labels == {LABEL_SC_RUNTIME}


async def test_sync_labels_noop_with_no_owned_or_manageable_labels(hass):
    """ADR-0028: a class with no owned_labels at all (e.g. SolarSurplusSensor) gets no
    registry write at all -- not a call that happens to leave the labels empty, a genuine
    no-op, checked via entry identity (registry entries are replaced, not mutated, on any real
    update, so an unchanged identity proves no write happened)."""
    entity = _UnlabelledEntity(entry_id="entry1")
    platform = MockEntityPlatform(hass, domain=Platform.SENSOR, platform_name=DOMAIN)
    await platform.async_add_entities([entity])
    registry = er.async_get(hass)
    before = registry.async_get(entity.entity_id)

    sync_labels(registry, Platform.SENSOR, entity.unique_id, owned_labels=frozenset())

    assert registry.async_get(entity.entity_id) is before


async def test_sync_labels_merges_with_a_users_own_label(hass):
    """`async_update_entity`'s `labels` parameter replaces the stored set -- a bare assignment
    would silently erase a label the user attached themselves on the next reload. Calls with
    only `owned_labels` set, relying on `manageable_labels`'s default (falls back to
    `owned_labels` itself) -- the case ADR-0028's own review caught as under-specified."""
    entity = _LabelledEntity(entry_id="entry1")
    platform = MockEntityPlatform(hass, domain=Platform.SENSOR, platform_name=DOMAIN)
    await platform.async_add_entities([entity])
    registry = er.async_get(hass)
    registry.async_update_entity(entity.entity_id, labels={_OTHER_LABEL})

    sync_labels(
        registry, Platform.SENSOR, entity.unique_id, owned_labels=frozenset({LABEL_SC_RUNTIME})
    )

    entry = registry.async_get(entity.entity_id)
    assert entry.labels == {LABEL_SC_RUNTIME, _OTHER_LABEL}


async def test_sync_labels_removes_label_when_owned_labels_drops_it(hass):
    """ADR-0028: a capability turning off (owned_labels no longer containing the label) must
    remove it, not just leave it stuck from a previous reload -- `manageable_labels` is the
    superset that makes removal possible, since `owned_labels` alone could only ever grow the
    stored set (#674). Uses an _UnlabelledEntity and sets the precondition label explicitly
    (rather than relying on _LabelledEntity's inherited async_added_to_hass hook, which T3.4
    deleted -- this test must still prove removal with that hook gone). Also carries an
    unrelated _OTHER_LABEL through the precondition and asserts it survives removal -- the
    combination (existing - manageable) | owned dropping only the managed label while a
    fresh-install/additive-only test (test_sync_labels_merges_with_a_users_own_label) never
    exercises removal at all -- flagged during T3.4's review as a coverage gap left by
    deleting the equivalent pre-ADR-0028 test_time.py case."""
    entity = _UnlabelledEntity(entry_id="entry1")
    platform = MockEntityPlatform(hass, domain=Platform.SENSOR, platform_name=DOMAIN)
    await platform.async_add_entities([entity])
    registry = er.async_get(hass)
    registry.async_update_entity(entity.entity_id, labels={LABEL_SC_RUNTIME, _OTHER_LABEL})
    assert registry.async_get(entity.entity_id).labels == {LABEL_SC_RUNTIME, _OTHER_LABEL}

    sync_labels(
        registry,
        Platform.SENSOR,
        entity.unique_id,
        owned_labels=frozenset(),
        manageable_labels=frozenset({LABEL_SC_RUNTIME}),
    )

    entry = registry.async_get(entity.entity_id)
    assert entry.labels == {_OTHER_LABEL}


async def test_sync_labels_keys_on_unique_id_not_entity_id(hass):
    """ADR-0028: sync_labels must resolve the entity purely from (domain, DOMAIN, unique_id) --
    it works on a registry row that was never added to hass at all (no live entity instance,
    no entity_id ever assigned on one), which is exactly the disabled-entity case its docstring
    exists for."""
    registry = er.async_get(hass)
    entry = registry.async_get_or_create(Platform.SENSOR, DOMAIN, "entry1_never_added")

    sync_labels(
        registry,
        Platform.SENSOR,
        "entry1_never_added",
        owned_labels=frozenset({LABEL_SC_RUNTIME}),
    )

    assert registry.async_get(entry.entity_id).labels == {LABEL_SC_RUNTIME}


async def test_sync_labels_noop_when_not_yet_registered(hass):
    """ADR-0028: a unique_id with no registry row yet must not raise -- mirrors
    sync_disabled_by's equivalent case."""
    registry = er.async_get(hass)
    unique_id = "entry1_never_registered"
    entity_count_before = len(registry.entities)

    sync_labels(registry, Platform.SENSOR, unique_id, owned_labels=frozenset({LABEL_SC_RUNTIME}))

    assert registry.async_get_entity_id(Platform.SENSOR, DOMAIN, unique_id) is None
    assert len(registry.entities) == entity_count_before


async def test_async_added_to_hass_still_delegates_restore_state(hass):
    """Regression guard: `SmartChargingEntity` carries no `async_added_to_hass` override of its
    own (T3.4 deleted the label-sync one it used to have), so this pins the MRO shape --
    `_RestoringLabelledEntity`'s own override's `super()` call must keep landing on
    `RestoreEntity`. A future non-delegating override reintroduced on `SmartChargingEntity`
    would silently break every existing RestoreEntity-mixing owned entity's restore-on-restart
    behavior."""
    entity_id = "sensor.smart_charging_restoring_labelled"
    mock_restore_cache_with_extra_data(hass, ((State(entity_id, "restored"), {}),))

    entity = _RestoringLabelledEntity(entry_id="entry1")
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain=Platform.SENSOR)
    await platform.async_add_entities([entity])

    assert entity.restored_state is not None
    assert entity.restored_state.state == "restored"


async def test_sync_disabled_by_disables_when_capability_absent(hass):
    """ADR-0028: capability_met=False on a currently-enabled entity sets disabled_by."""
    entity = _UnlabelledEntity(entry_id="entry1")
    platform = MockEntityPlatform(hass, domain=Platform.SENSOR, platform_name=DOMAIN)
    await platform.async_add_entities([entity])
    registry = er.async_get(hass)

    sync_disabled_by(registry, Platform.SENSOR, entity.unique_id, capability_met=False)

    entry = registry.async_get(entity.entity_id)
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_sync_disabled_by_reenables_when_capability_returns(hass):
    """ADR-0028: capability_met=True clears a disabled_by=INTEGRATION set by this mechanism."""
    entity = _UnlabelledEntity(entry_id="entry1")
    platform = MockEntityPlatform(hass, domain=Platform.SENSOR, platform_name=DOMAIN)
    await platform.async_add_entities([entity])
    registry = er.async_get(hass)
    registry.async_update_entity(entity.entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION)

    sync_disabled_by(registry, Platform.SENSOR, entity.unique_id, capability_met=True)

    entry = registry.async_get(entity.entity_id)
    assert entry.disabled_by is None


async def test_sync_disabled_by_never_overrides_user_disable(hass):
    """ADR-0028: a user's own disabled_by=USER must survive a capability change in either
    direction -- this mechanism only ever flips its own None<->INTEGRATION pair."""
    entity = _UnlabelledEntity(entry_id="entry1")
    platform = MockEntityPlatform(hass, domain=Platform.SENSOR, platform_name=DOMAIN)
    await platform.async_add_entities([entity])
    registry = er.async_get(hass)
    registry.async_update_entity(entity.entity_id, disabled_by=er.RegistryEntryDisabler.USER)

    sync_disabled_by(registry, Platform.SENSOR, entity.unique_id, capability_met=True)
    assert registry.async_get(entity.entity_id).disabled_by is er.RegistryEntryDisabler.USER

    sync_disabled_by(registry, Platform.SENSOR, entity.unique_id, capability_met=False)
    assert registry.async_get(entity.entity_id).disabled_by is er.RegistryEntryDisabler.USER


async def test_sync_disabled_by_is_idempotent(hass):
    """ADR-0028: calling with the same capability_met twice in a row is a no-op the second time
    -- every reload re-runs this sync, so it must not toggle or error on repetition."""
    entity = _UnlabelledEntity(entry_id="entry1")
    platform = MockEntityPlatform(hass, domain=Platform.SENSOR, platform_name=DOMAIN)
    await platform.async_add_entities([entity])
    registry = er.async_get(hass)

    sync_disabled_by(registry, Platform.SENSOR, entity.unique_id, capability_met=False)
    first = registry.async_get(entity.entity_id).disabled_by
    sync_disabled_by(registry, Platform.SENSOR, entity.unique_id, capability_met=False)
    second = registry.async_get(entity.entity_id).disabled_by

    assert first is er.RegistryEntryDisabler.INTEGRATION
    assert second is er.RegistryEntryDisabler.INTEGRATION


async def test_sync_disabled_by_noop_when_not_yet_registered(hass):
    """ADR-0028: a unique_id with no registry row yet (first-ever setup, before
    async_add_entities creates one) must not raise -- entity_registry_enabled_default handles
    that case instead."""
    registry = er.async_get(hass)
    unique_id = "entry1_never_registered"
    entity_count_before = len(registry.entities)

    sync_disabled_by(registry, Platform.SENSOR, unique_id, capability_met=False)

    assert registry.async_get_entity_id(Platform.SENSOR, DOMAIN, unique_id) is None
    assert len(registry.entities) == entity_count_before
