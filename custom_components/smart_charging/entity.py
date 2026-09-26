"""Base class for Smart Charging owned entities (ADR-0002/0004)."""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, OPTION_DISABLED_SEEN, OPTION_USER_ENABLED


def sync_disabled_by(
    registry: er.EntityRegistry, domain: str, unique_id: str, *, capability_met: bool
) -> None:
    """Pre-add registry sync (ADR-0028, narrowed by ADR-0047): flips disabled_by between None
    and RegistryEntryDisabler.INTEGRATION as capability_met changes, for an entity that already
    has a registry row -- except a row the user has enabled themselves while the capability is
    absent, which this call now recognizes and leaves alone (R18's enable half, ADR-0047).
    No-ops if the entity isn't registered yet (a brand-new entity's initial disabled state is
    set by _attr_entity_registry_enabled_default at add time instead -- there is no row for
    this call to act on before that) or if the row is somehow missing despite a matching
    entity_id. Still never writes any other `disabled_by` value in either direction (notably
    USER): what ADR-0047 adds is entirely in the row's `options[DOMAIN]` (`const.py`'s
    `OPTION_DISABLED_SEEN`/`OPTION_USER_ENABLED`) -- this call now also marks `disabled_seen`
    on a row it leaves disabled, and clears a stale `user_enabled` when it sees the user's own
    `disabled_by=USER` (only the user's own disable does, per that ADR's Decision).

    `domain` is the entity's platform domain (e.g. "sensor", "time") -- the same first
    positional argument `registry.async_get_entity_id(domain, platform, unique_id)` itself
    takes, where `platform` there means the *integration* domain (`DOMAIN`). Named `domain`
    here, not `platform`, to avoid exactly that ambiguity.
    """
    entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
    if entity_id is None:
        return
    existing = registry.async_get(entity_id)
    if existing is None:
        return

    options = existing.options.get(DOMAIN, {})
    seen = options.get(OPTION_DISABLED_SEEN, False)
    user_enabled = options.get(OPTION_USER_ENABLED, False)
    disabled_by = existing.disabled_by

    # ADR-0047 point 2, before the flip: tell a user's enable and a user's disable apart from
    # this call's own resting state.
    if disabled_by is None and seen:
        user_enabled = True
        seen = False
    elif disabled_by is er.RegistryEntryDisabler.USER:
        user_enabled = False

    # ADR-0028's flip, now skipping the disable half for a row the user has enabled.
    if not capability_met and disabled_by is None and not user_enabled:
        registry.async_update_entity(entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION)
        disabled_by = er.RegistryEntryDisabler.INTEGRATION
    elif capability_met and disabled_by is er.RegistryEntryDisabler.INTEGRATION:
        registry.async_update_entity(entity_id, disabled_by=None)
        disabled_by = None
        seen = False  # this call's own write of None is never a user's enable.

    # ADR-0047 point 2, last: a row left disabled (by either disabler) is marked, so the next
    # external flip to None is recognized.
    if disabled_by in (er.RegistryEntryDisabler.INTEGRATION, er.RegistryEntryDisabler.USER):
        seen = True

    new_options: dict[str, bool] = {}
    if seen:
        new_options[OPTION_DISABLED_SEEN] = True
    if user_enabled:
        new_options[OPTION_USER_ENABLED] = True
    if new_options != dict(options):
        registry.async_update_entity_options(entity_id, DOMAIN, new_options or None)


def mark_disabled_seen(registry: er.EntityRegistry, domain: str, unique_id: str) -> None:
    """Post-add registry sync (ADR-0047's Option F, point 3): marks a freshly first-registered
    row that entity_platform.py itself created disabled (disabled_by=INTEGRATION, from
    _attr_entity_registry_enabled_default=False) with disabled_seen, so a later user enable is
    recognized even if it happens while the config entry isn't loaded at all. Called after
    async_add_entities, beside sync_labels where the platform has one -- HA reserves
    Entity.get_initial_entity_options for its own component base classes, so there is no hook
    to do this at creation time itself. No-ops for a row registered enabled (nothing to tell
    apart yet) or already marked (a later reload's sync_disabled_by owns the mark from here)."""
    entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
    if entity_id is None:
        return
    existing = registry.async_get(entity_id)
    if existing is None:
        return
    if existing.disabled_by is not er.RegistryEntryDisabler.INTEGRATION:
        return
    if existing.options.get(DOMAIN, {}).get(OPTION_DISABLED_SEEN, False):
        return
    registry.async_update_entity_options(entity_id, DOMAIN, {OPTION_DISABLED_SEEN: True})


def sync_labels(
    registry: er.EntityRegistry,
    domain: str,
    unique_id: str,
    *,
    owned_labels: frozenset[str],
    manageable_labels: frozenset[str] = frozenset(),
) -> None:
    """Post-add registry sync (ADR-0028): replaces the removed async_added_to_hass-based label
    sync with the identical merge semantics. Keyed on unique_id (via the same
    registry.async_get_entity_id lookup as sync_disabled_by), NOT the entity instance's own
    entity_id attribute -- a registry-disabled entity never gets added to hass, so its instance
    may have no reliable entity_id to read; the registry lookup works regardless of whether the
    entity was added live this reload (ADR-0028's Decision requires the label to stay correct
    even for a capability-absent entity a user has enabled themselves -- disabled_by=None with
    the ADR-0047 record recognizing it as theirs, not disabled_by=USER)."""
    manageable = manageable_labels or owned_labels
    if not manageable:
        return
    entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
    if entity_id is None:
        return
    existing = registry.async_get(entity_id)
    if existing is None:
        return
    registry.async_update_entity(entity_id, labels=(existing.labels - manageable) | owned_labels)


class SmartChargingEntity(Entity):
    """Common device grouping for owned entities; subclasses set their own unique_id."""

    _attr_has_entity_name = True
    _object_id_suffix: str | None = None  # locale-independent object_id suffix (ADR-0013)
    _owned_labels: frozenset[str] = frozenset()  # C5 (#601): e.g. LABEL_SC_RUNTIME
    # The labels this class may add OR remove -- a superset of every value `_owned_labels` can
    # take across this class's lifetime, class-level and constant even when `_owned_labels`
    # itself is set per-instance and conditionally (#674). Left empty for the common case where
    # `_owned_labels` never changes: each platform's setup-time `sync_labels` call (ADR-0028)
    # then falls back to `_owned_labels` itself, so subtracting and re-adding the same constant
    # set is a no-op and existing subclasses need no change.
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
