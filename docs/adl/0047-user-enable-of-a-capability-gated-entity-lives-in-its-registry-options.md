# ADR-0047: A user's own enable of a capability-gated entity is recorded in that entity's registry options (narrows ADR-0028)

Date: 2026-09-25
Status: Accepted

## Summary

In the context of capability-gated entities that `sync_disabled_by` re-disables on every reload,
facing a user's enable that HA records as the same `None` the integration rests at, we decided on
the entity registry's per-entity `options` under this integration's domain key, with a mark the
integration's own setup leaves on each row it sees disabled, to keep that enable through every
capability change, restart and reload, accepting that it rests on who writes a row.

## Context

R18, in [`requirements.md`](../analysis/requirements.md), requires that a
[capability](../analysis/system-overview.md#ubiquitous-language) change never overrides a user's
own enable or disable; only an entity the user has left alone follows the capabilities.

[ADR-0028](0028-registry-level-disabling-for-capability-gated-entities.md) meets the disable half:
`sync_disabled_by` leaves `RegistryEntryDisabler.USER` alone. Its Decision assumes the enable
half is met the same way, through `disabled_by=USER`, and it is not. These forces, all
established from Home Assistant's source at the pinned version
([research](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/1361#issuecomment-5837259410)),
shape the answer:

- **A user's enable is `disabled_by=None`.** The registry's websocket update accepts only `None`
  or `user`. Core then reloads the config entry 30 s later, and `sync_disabled_by` sees `None`
  with the capability still absent, so it disables the entity again.
- **`disabled_by` alone cannot say who enabled a row.** At setup, "never disabled" and "the user
  just enabled it" look the same. Only this integration writes `INTEGRATION`, and
  `EVENT_ENTITY_REGISTRY_UPDATED` carries the changed fields' old values, but not who made the
  change.
- **An enable can happen while the entry is not loaded**, after a failed setup or between the
  unload and the setup of a reload. R18 still requires it to stick.
- **The record binds more than today's entities.** ADR-0028's Consequences tell every future
  capability-gated entity to reuse its helpers, and the record will persist on users'
  installations. Moving it after upgrade means a migration.
- **The `sc_runtime` label is not part of this.** It follows the capability, not the enabled
  state (R19's capability-gated-visibility criterion, ADR-0028).

## Considered options

### Option A — The entity registry's per-entity `options`, under this integration's domain key

`options[DOMAIN]` on the entity's own registry row holds `{"user_enabled": true}`. It is written
with `EntityRegistry.async_update_entity_options`, which replaces only this domain's mapping.

- Pro: The record is on the row `sync_disabled_by` already reads. It survives restarts and
  reloads with that row, and costs no new file and no new setup-order dependency.
- Pro: HA keeps a removed row's `options`, and its `disabled_by`, and restores both if the same
  unique id comes back. So the record never outlives or loses its entity, and nothing has to
  prune it.
- Con: Any websocket client can write the record (`options_domain` on the registry update). A
  forged record can only keep an entity enabled, which the user can do anyway.
- Con: HA documents registry `options` for no custom integration. Core's own `sensor.private` is
  the only precedent for integration-private data there.
- Con: The record is invisible in the UI. A user cannot see why an entity whose capability is
  absent stays on.

### Option B — The config entry's `options`, holding the set of user-enabled unique ids

- Pro: One place for the whole entry, visible in the entry's diagnostics, with no coupling to
  the registry's field semantics.
- Con: Every write to `entry.options` fires the entry's update listener, which reloads the entry
  at once ([ADR-0008](0008-reconfigure-reload-behavior.md)). So each toggle gets a reload of its
  own, on top of HA's own 30 s reload.
- Con: It is options-flow data changed outside the options flow. It is also one entry-wide blob,
  which the integration must prune itself when an entity is removed.

### Option C — An integration-owned `homeassistant.helpers.storage.Store`

- Pro: The storage belongs to the integration alone, with a documented API. Nothing can write it
  except this integration.
- Con: It is a new persisted file with its own version and migration burden. It must be loaded
  before the platforms set up, pruned when an entity is removed, and deleted when the entry is
  removed.
- Con: It takes the name of the RA3 Config/State Store (ADR-0018, ADR-0019), which is a
  different thing.

### Option D — Do nothing; R18's enable half stays unmet

- Pro: No new record and no new setup step.
- Con: A user's enable is undone 30 s later, every time, which R18 forbids. Keeping it would mean
  weakening R18.

Options A to C each still need a way to tell a user's enable from the integration's own `None`.
Options E and F are the two found.

### Option E — A registry-update listener that records the enable as it happens

Each gated platform subscribes to `EVENT_ENTITY_REGISTRY_UPDATED` after its own setup writes, so
every `disabled_by` change it sees was made by someone else, and releases it through
`entry.async_on_unload`.

- Pro: It sees each change as it happens, including a disable followed by a re-enable between
  two setups.
- Con: An enable made while the entry is not loaded reaches no listener, so the next setup
  disables the entity again, against R18.
- Con: A bus subscription per gated platform, and every test that drives a platform's setup with
  a stub entry must give it `async_on_unload`.

### Option F — A mark the integration's own setup leaves on each row it sees disabled

Setup marks every row it finds or leaves disabled by `INTEGRATION` or `USER`. The next setup reads
a marked row that is now `None` as a user's enable, however long ago and whether or not the entry
was loaded. A row created at first registration is marked just after `async_add_entities`, since
HA reserves `Entity.get_initial_entity_options` for its component base classes.

- Pro: It catches every enable, loaded or not, with no subscription. It stays in ADR-0028's
  setup-time shape.
- Con: It rests on who writes a row. HA's device and config-entry re-enables touch only rows they
  disabled themselves, so only a user's enable returns a marked row to `None`. Nothing documents
  that; it holds in HA's registry code
  ([research](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/1361#issuecomment-5844276275)).
- Con: A disable followed by a re-enable of an enabled row between two setups is not seen. The
  row ends where it started, so it is treated as left alone.

## Decision

Options A and F. A is the only storage whose record lives and dies with its entity (A's second
Pro) without a reload per toggle (B's first Con) or a file to version and prune (C's first Con),
and D fails R18. F is the only way of telling the enable apart that meets R18 while the entry is
not loaded (E's first Con). The Cons of A and F are the price.

1. **The record.** `options[DOMAIN]` on the entity's registry row holds two flags, each a named
   constant: `disabled_seen`, the mark of Option F, and `user_enabled`, the user's enable.
   `DOMAIN` is the integration domain.
2. **`sync_disabled_by` narrowed.** Before ADR-0028's flip, for an existing row:
   - `None` with `disabled_seen` is a user's enable: it sets `user_enabled` and drops the mark;
   - `USER` is a user's disable: it drops `user_enabled`.

   The flip then leaves a `None` row with `user_enabled` enabled while the capability is absent,
   and drops the mark whenever it writes `None` itself. Last, a row left `INTEGRATION` or `USER`
   gets `disabled_seen`. A capability that returns does not clear `user_enabled`: only the user's
   own disable does. The signature does not change.
3. **First registration.** A post-add step in `entity.py`, called after `async_add_entities` in
   each gated platform's setup (beside `sync_labels` where the platform has one), marks a row
   that is `INTEGRATION` and not yet marked, as Option F describes.
4. **A removed entity.** The integration does nothing. The record is part of the row, so HA
   removes it with the row, restores it with the row, and purges it with the orphaned row once
   the entry is gone.

This narrows ADR-0028 in two places, and nothing else in it changes:

- The premise in its Decision that a user forces an entity back on with `disabled_by=USER`. That
  Decision's reason for keeping the label independent still stands, with the enable recorded as
  in point 1, and the label keeps following the capability.
- The contract its Consequences give `sync_disabled_by`, which only flipped `None` and
  `INTEGRATION`. That contract gains point 2.

## Consequences

- Easier: a capability-gated entity added later gets R18's enable half from `sync_disabled_by`
  and the post-add step, with no storage and no listener of its own. Harder: `sync_disabled_by`
  now reads and writes the row's options as well as `disabled_by`, and its tests gain the mark's
  cases.
- Follow-up: the development task that implements R18's enable half builds points 1 to 3 in
  `entity.py`, `const.py`, `sensor.py` and `time.py`, with tests, and corrects the docstrings the
  Blast radius marks non-conforming. The tests cover:
  - a user's enable while the capability is absent surviving a reload and a capability change;
  - the same enable made while the entry is not loaded;
  - a user's later disable clearing the record;
  - a re-enable while the capability is present;
  - a first-registered row being marked.
- ADR-0028's ADL row gains a pointer to this record in the same change. Its Status stays
  `Accepted`.

**Blast radius.** Two searches, run from the repository root:

1. `rg -n 'sync_disabled_by|RegistryEntryDisabler\.(USER|INTEGRATION)|disabled_by=USER|force[sd]? (the entity |an entity )?back on|own choice to enable or disable|own enable( or |/)disable choice|enabled it themselves|user has enabled|chose to re-enable' custom_components/ tests/ docs/ .claude/ .github/ CLAUDE.md`
   — 75 hits outside this record. It is keyed on the helper whose contract changes, for its
   callers and descriptions; on the two disablers that helper reads and writes, for the tests
   that assert its contract on a row without naming it; and on the wordings of R18's rule and of
   the premise this record corrects found in the tree. The dot-directories are named, because a
   root sweep skips them.
2. `rg -n 'async_setup_entry\(' tests/` — 10 hits: the tests that drive a gated platform's setup
   directly, which a new setup step could break.

| Site | Today | Follow-up |
|---|---|---|
| `custom_components/smart_charging/entity.py:12` | `sync_disabled_by` reads and writes `disabled_by` only | Point 2 |
| `custom_components/smart_charging/entity.py:16` | Its docstring: flips only between `None` and `INTEGRATION` | Point 2 |
| `custom_components/smart_charging/entity.py:35` | Writes `INTEGRATION` on any `None` row while the capability is absent | Point 2 |
| `custom_components/smart_charging/entity.py:36` | Re-enables an `INTEGRATION` row without dropping a mark | Point 2 |
| `custom_components/smart_charging/entity.py:54` | `sync_labels`'s docstring gives a user's enable as `disabled_by=USER` | Correct the docstring |
| `custom_components/smart_charging/sensor.py:72` | Imports `sync_disabled_by`, not the post-add step | Point 3 |
| `custom_components/smart_charging/sensor.py:418` | Calls `sync_disabled_by`; no post-add mark | Point 3, after its `async_add_entities` call |
| `custom_components/smart_charging/time.py:43` | Imports `sync_disabled_by`, not the post-add step | Point 3 |
| `custom_components/smart_charging/time.py:77` | The departure-time docstring: a user can "force the entity back on" | Correct the docstring |
| `custom_components/smart_charging/time.py:78` | Gives that enable as `disabled_by=USER` | Correct the docstring |
| `custom_components/smart_charging/time.py:80` | Calls it the entity "the user chose to re-enable" | Correct the docstring |
| `custom_components/smart_charging/time.py:125` | Calls `sync_disabled_by`; no post-add mark | Point 3 |

57 other hits conform: `entity.py:50` (names `sync_disabled_by`'s lookup, still true);
`sensor.py:389` (a config mirror is never resynced, so a user's enable already stays); the tests
in `test_entity_labels.py`, `test_time.py`, `test_sensor.py` and `test_init.py` (ADR-0028's
contract and the user's disable still hold; the fake at `test_sensor.py:644` keeps the unchanged
signature); search 2's ten setup drivers (the post-add step finds no registered row and does
nothing, and needs nothing new of the entry); and `project-plan.md`, `system-design.md` and
`entity-catalog.md`, which state the behaviour this record delivers. Out of scope: R18
(`requirements.md:323`) and UC11 (l. 119, 127, 266) state the rule this record serves, and stay as
written. ADR-0028's seven hits (l. 151–187) are immutable; its l. 171 premise and l. 179 contract
are what this record narrows. ADR-0031's three hits and `test_sensor.py:1185` keep config mirrors
disabled by default and outside `sync_disabled_by`. ADR-0028's ADL row (`docs/adl/README.md:37`)
points here.
