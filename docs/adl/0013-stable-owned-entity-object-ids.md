# ADR-0013: Stable, locale-independent object_ids for owned entities

Date: 2026-07-27
Status: Accepted

## Context

ADR-0004 establishes that `smart_charging` creates and fully owns a set of control and
diagnostic entities (`select.smart_charging_profile`,
`number.smart_charging_soc_limit_override`, `time.smart_charging_departure_*`, etc.),
grouped under one HA device. `docs/analysis/entity-catalog.md` and `README.md` both
document these as literal `entity_id`s, on the expectation that a user can reference
`number.smart_charging_soc_limit_override` directly in an automation or dashboard.

`entity.py`'s `SmartChargingEntity` base class sets `_attr_has_entity_name = True` and
relies on each platform entity's `_attr_translation_key` for its display name, with no
`_attr_suggested_object_id`. Under `has_entity_name = True`, Home Assistant derives a
newly-registered owned entity's `object_id` (the part of the `entity_id` after the
domain) from the **device name + the entity's translated name** — i.e. the
`entity.<platform>.<translation_key>.name` string in `strings.json` — not from the
`translation_key` itself. Concretely, `soc_limit_override`'s strings.json name "Default
charge limit" yields `number.smart_charging_default_charge_limit`, not the catalog's
`number.smart_charging_soc_limit_override`; several other owned entities have the same
mismatch (at least `monthly_peak_kw`, `departure_mon`…`departure_sun`,
`departure_holiday`, `departure_home_day`, `active_soc_limit`).

This also means the generated `object_id` is not stable across HA locales: the same
entity registers under a different `entity_id` on a Dutch install than an English one,
because the name string it derives from is translated but the `translation_key` is not.
`tests/test_init.py:149` already documents the current (English-locale) behavior by
asserting `number.smart_charging_default_charge_limit`, confirming this is what actually
ships today, not a test bug.

This decision only concerns **owned** entities (ADR-0004's second population); mapped
hardware entities are referenced by the user's own pre-existing `entity_id` and are
unaffected.

## Considered options

### Option A — Pin an explicit, locale-independent `object_id` for every owned entity

Give each owned entity an explicit, locale-independent object_id suffix equal to its
catalog id's suffix (e.g. `soc_limit_override`, `monthly_peak_kw`), decoupling the
registered `entity_id` from the translated display name. The display name shown in the
UI still comes from `translation_key` and remains fully localized; only the `entity_id`
is pinned. (`_attr_suggested_object_id` is a no-op in the HA version this integration
targets; the mechanism is an override of the `suggested_object_id` property on the
shared `SmartChargingEntity` base — see the implementation follow-up for the verified
detail.)

- Pro: `entity_id` matches `entity-catalog.md`/`README.md` exactly, in every HA locale,
  which is what those documents already promise users for automations and dashboards —
  no further doc rewrite needed.
- Con: Every owned entity now carries two related-but-distinct identifiers to keep in
  sync (`translation_key` for display, explicit object_id suffix for the wire name);
  a contributor adding a new owned entity must remember to set both, and nothing besides
  code review enforces that they match the catalog's expected suffix.

### Option B — Accept HA's locale-derived naming; correct the docs instead

Leave `entity.py`/platform files as they are, and rewrite `entity-catalog.md`, ADR-0004,
and `README.md` to describe each owned entity by its **display name** (the
`translation_key`'s English string) rather than promising a specific `entity_id`,
noting that the actual `entity_id` is locale-dependent and the user should confirm it
via the entity picker.

- Pro: No code change; this is standard, unremarkable `has_entity_name` behavior used by
  the vast majority of HA integrations, and avoids the redundant id Option A introduces.
- Con: Breaks the concrete commitment `entity-catalog.md`/`README.md` already make
  today — every automation/dashboard example in the README written against a literal
  `smart_charging_*` id becomes locale-fragile, and a non-English user following the
  README's literal ids finds nothing at that `entity_id`. It also reopens
  `entity-catalog.md`/ADR-0004/README for a documentation rewrite of every owned-entity
  row, larger than the follow-up ADR-0004 already tracks.

## Decision

Option A. `entity-catalog.md`, `README.md`, and ADR-0004 already commit to specific,
literal `entity_id`s for every owned entity, for direct use in user automations and
dashboards — that commitment predates this ADR, and the current translated-name-derived
ids are a bug against it rather than a documentation gap. Option B's Con is exactly that
regression: it would convert an already-documented, already-relied-upon contract into a
locale-dependent one. Option A's Con (two identifiers to keep in sync) is a one-time,
per-entity cost paid once when an owned entity is added, caught by test coverage (each
owned entity's `entity_id` is asserted in `tests/test_init.py`-equivalent tests) rather
than by convention alone.

Each owned entity's explicit object_id suffix equals the suffix already used in
`entity-catalog.md`'s existing rows (e.g. `soc_limit_override`, not
`default_charge_limit`), so no catalog renumbering is needed — only the entities whose
generated `entity_id` currently diverges from the catalog change, to match the catalog
value they were always documented to have.

## Consequences

- Every owned entity in `select.py`, `number.py`, `sensor.py`, `switch.py`, `time.py`
  needs an explicit, locale-independent object_id pinned alongside its
  `_attr_translation_key`, matching `entity-catalog.md`'s existing suffix for that
  entity. This includes entities whose translation-key-derived name happens to already
  coincide with the catalog suffix today (e.g. `select.smart_charging_profile`) — those
  need the same explicit pin so a future wording change to `strings.json` can't silently
  drift their `entity_id` the way it has for the entities this ADR's Context lists.
- `tests/test_init.py:149` (and any sibling assertions on other owned entities) must be
  updated to assert the catalog's documented `entity_id`s, not the currently-generated
  locale-derived ones.
- Follow-up: open an implementation task (via `write-impl-spec`, scoped to whichever
  in-flight slice owns `entity.py`/the platform files, or a standalone slice if none is
  open) to make the code change and update the affected tests; this ADR records the
  naming decision, not the code.
- Follow-up: no further `entity-catalog.md`/README rewrite is needed as a result of this
  ADR — the existing documented ids become correct once the code change lands.
- Any future owned entity added to the catalog must pin its object_id the same way from
  the start, rather than relying on the translated name.
