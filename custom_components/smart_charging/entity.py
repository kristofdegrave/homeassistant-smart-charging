"""Base class for Smart Charging owned entities (ADR-0002/0004)."""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


class SmartChargingEntity(Entity):
    """Common device grouping for owned entities; subclasses set their own unique_id."""

    _attr_has_entity_name = True
    _object_id_suffix: str | None = None  # locale-independent object_id suffix (ADR-0013)
    _owned_labels: frozenset[str] = frozenset()  # C5 (#601): e.g. LABEL_SC_RUNTIME
    # The labels this class may add OR remove -- a superset of every value `_owned_labels` can
    # take across this class's lifetime, class-level and constant even when `_owned_labels`
    # itself is set per-instance and conditionally (#674). Left empty for the common case where
    # `_owned_labels` never changes: `async_added_to_hass` then falls back to `_owned_labels`
    # itself, so subtracting and re-adding the same constant set is a no-op and existing
    # subclasses need no change.
    _manageable_labels: frozenset[str] = frozenset()

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Smart Charging",
        )
        # ADR-0013's only listed Con is keeping this and `_object_id_suffix` in sync by
        # hand at each call site; deriving unique_id from the same suffix here removes
        # that risk structurally. Subclasses that set `_object_id_suffix`
        # as an instance attribute (e.g. `SmartChargingDepartureTime`) must do so before
        # calling `super().__init__()`.
        if self._object_id_suffix is not None:
            self._attr_unique_id = f"{entry_id}_{self._object_id_suffix}"

    @property
    def suggested_object_id(self) -> str | None:
        # ADR-0013: pin the object_id to a fixed, locale-independent suffix so the
        # registered entity_id matches entity-catalog.md in every HA locale, decoupled
        # from the translated display name (which still comes from translation_key). The
        # returned suffix is device-name-prefixed by HA because has_entity_name is True,
        # yielding e.g. number.smart_charging_soc_limit_override.
        return self._object_id_suffix or super().suggested_object_id

    async def async_added_to_hass(self) -> None:
        # `SmartChargingEntity` is first in every subclass's MRO (RestoreEntity/CoordinatorEntity
        # come after it) -- delegating first is required, not optional, or every existing
        # subclass's restore-on-restart / coordinator-push registration would silently break.
        await super().async_added_to_hass()
        manageable = self._manageable_labels or self._owned_labels
        if not manageable:
            return
        registry = er.async_get(self.hass)
        existing = registry.async_get(self.entity_id)
        if existing is None:
            # Every `_owned_labels`-carrying class also sets `_object_id_suffix`, so
            # `unique_id` is always set and the entity is always already registered by this
            # point -- unreachable in practice, but async_update_entity raises KeyError on an
            # unregistered entity_id, so guard rather than let that surprise a future caller.
            return
        # C5 (#601): merge, never assign the bare set -- `async_update_entity`'s `labels`
        # parameter replaces the stored set, so a bare assignment would silently erase any
        # label the user attached themselves on the very next reload. Subtract `manageable`
        # before re-adding `_owned_labels` (#674): for a class whose `_owned_labels` never
        # changes this is a no-op (the same constant set is removed then re-added), but for one
        # whose `_owned_labels` is conditional, this is what lets a label be *removed* on a
        # later reload, not just added -- a bare union could only ever grow the stored set.
        registry.async_update_entity(
            self.entity_id, labels=(existing.labels - manageable) | self._owned_labels
        )
