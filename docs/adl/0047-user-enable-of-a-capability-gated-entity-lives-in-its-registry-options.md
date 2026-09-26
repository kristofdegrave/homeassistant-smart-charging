# ADR-0047: A user's own enable of a capability-gated entity is recorded in that entity's registry options (narrows ADR-0028)

Date: 2026-09-25
Status: Accepted

## Summary

In the context of capability-gated entities that `sync_disabled_by` re-disables on every reload,
facing a user's enable that Home Assistant records as the same `disabled_by=None` the integration
uses for its own resting state, we decided on the entity registry's per-entity `options` under
this integration's domain key, to keep an enable made while the entry is loaded through every
capability change, restart and reload, accepting that any websocket client can write the record.

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
- **The row alone cannot say who enabled it.** At setup, "never disabled" and "the user just
  enabled it" look the same. So the enable has to be noticed when it happens, by a listener on
  `EVENT_ENTITY_REGISTRY_UPDATED`. That event carries the changed fields' old values, but not
  who made the change.
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

- Pro: No new record and no listener.
- Con: A user's enable is undone 30 s later, every time, which R18 forbids. Keeping it would mean
  weakening R18.

## Decision

Option A. It is the only option whose record lives and dies with its entity (A's second Pro)
without a reload per toggle (B's first Con) or a file to version and prune (C's first Con).
D fails R18. A's Cons are the price.

1. **The record.** `options[DOMAIN]["user_enabled"] = True` on the entity's registry row. The key
   is a named constant, and `DOMAIN` is the integration domain.
2. **The listener.** It lives in `entity.py`, beside `sync_disabled_by`. Each gated platform's
   `async_setup_entry` registers it after its own `sync_disabled_by` calls and
   `async_add_entities`, for the unique ids that platform gates, and releases it through
   `entry.async_on_unload`. It subscribes with
   `hass.bus.async_listen(EVENT_ENTITY_REGISTRY_UPDATED, …)`, filtered to `update` events whose changes carry `disabled_by`. It matches rows by `platform`
   and `unique_id` rather than by `entity_id`, so renaming an entity does not lose it. Registering
   it after the integration's own setup writes means every `disabled_by` change it sees was made
   by someone else.
3. **Setting and clearing.** A change from `INTEGRATION` or `USER` to `None` is a user's enable,
   and writes the record. It does so whether or not the capability is present, since R18 lets
   only an entity the user has left alone follow the capabilities. A change to `USER` is a
   user's disable, and removes the `user_enabled` key. Any other disabler (`DEVICE`,
   `CONFIG_ENTRY`) leaves the record as it is.
4. **`sync_disabled_by` narrowed.** While the capability is absent, a row with `disabled_by=None`
   and the record is left enabled. Otherwise the helper behaves as ADR-0028 has it, and its
   signature does not change. A capability that returns does not clear the record: only the
   user's own disable does.
5. **A removed entity.** The integration does nothing. The record is part of the row, so HA
   removes it with the row, restores it with the row, and purges it with the orphaned row once
   the entry is gone.

This narrows ADR-0028 in two places, and nothing else in it changes:

- The premise in its Decision that a user forces an entity back on with `disabled_by=USER`. That
  Decision's reason for keeping the label independent still stands, with the enable recorded as
  in point 1.
- The contract its Consequences give `sync_disabled_by`, which only flipped `None` and
  `INTEGRATION`. That contract gains point 4.

## Consequences

- Easier: a capability-gated entity added later gets R18's enable half from `sync_disabled_by`
  and the listener beside it, with no storage of its own. Harder: a gated platform's setup has
  one more step, registering the listener, and the tests of the helpers gain the record's cases.
- Foreclosed: an enable made while the entry is not loaded — its setup failed, or a reload is
  between unload and setup — reaches no listener, so the next setup disables the entity again.
  Every listener-based option shares this window; the user enables the entity again once the
  entry is loaded.
- Follow-up: the development task that implements R18's enable half builds points 1 to 4 in
  `entity.py`, `const.py`, `sensor.py` and `time.py`, with tests, and corrects the two
  docstrings and the `test_sensor.py` stub the Blast radius marks non-conforming. Those tests cover a user's
  enable while the capability is absent surviving a reload and a capability change, a user's
  later disable clearing the record, and a re-enable while the capability is present.
- ADR-0028's ADL row gains a pointer to this record in the same change. Its Status stays
  `Accepted`.

**Blast radius.** `rg -n 'sync_disabled_by|RegistryEntryDisabler\.(USER|INTEGRATION)|disabled_by=USER|force[sd]? (the entity |an entity )?back on|own choice to enable or disable|own enable( or |/)disable choice|enabled it themselves' custom_components/ tests/ docs/ .claude/ .github/ CLAUDE.md`
— 72 hits outside this record, run from the repository root. It is keyed three ways. On the
helper whose contract changes, for its callers and descriptions. On the two disablers that helper
reads and writes, for the tests that assert its contract on a registry row without naming it.
And on R18's rule and the premise this record corrects, in each spelling the tree uses: a user's
enable as `USER`, "force … back on", "own choice to enable or disable", "own enable/disable
choice", "enabled it themselves". The dot-directories are named, because a root sweep skips
them.

| Site | Today | Follow-up |
|---|---|---|
| `custom_components/smart_charging/entity.py:12` | `sync_disabled_by` writes `INTEGRATION` over a user's enable | Point 4 |
| `custom_components/smart_charging/entity.py:16` | Its docstring: flips only between `None` and `INTEGRATION` | Point 4 |
| `custom_components/smart_charging/entity.py:35` | Writes `INTEGRATION` on any `None` row while the capability is absent | Point 4 |
| `custom_components/smart_charging/entity.py:54` | `sync_labels`'s docstring gives a user's enable as `disabled_by=USER` | Correct the docstring |
| `custom_components/smart_charging/sensor.py:72` | Imports `sync_disabled_by`, not the listener | Point 2 |
| `custom_components/smart_charging/sensor.py:418` | Calls `sync_disabled_by`; no listener registered | Point 2 |
| `custom_components/smart_charging/time.py:43` | Imports `sync_disabled_by`, not the listener | Point 2 |
| `custom_components/smart_charging/time.py:77` | The departure-time docstring: a user can "force the entity back on" | Correct the docstring |
| `custom_components/smart_charging/time.py:78` | Gives that enable as `disabled_by=USER` | Correct the docstring |
| `custom_components/smart_charging/time.py:125` | Calls `sync_disabled_by`; no listener registered | Point 2 |
| `tests/test_sensor.py:635` | Its test drives `sensor.async_setup_entry` with a stub entry that has no `async_on_unload` | Point 2: give the stub `async_on_unload` |
| `tests/test_sensor.py:644` | Fakes `sync_disabled_by` in that test | Point 2: as above |
| `tests/test_sensor.py:648` | Patches the fake in; the stub entry still lacks `async_on_unload` | Point 2: as above |

45 other hits conform: `entity.py:36` (re-enables an `INTEGRATION` row once the capability
returns, unchanged by point 4); `entity.py:50` (names `sync_disabled_by`'s lookup, still true);
`sensor.py:389` (a config mirror is never resynced, so a user's enable already stays); the other
tests in `test_entity_labels.py`, `test_time.py`, `test_sensor.py` and `test_init.py` (ADR-0028's
contract and the user's disable, which still hold); and `project-plan.md`, `system-design.md` and
`entity-catalog.md`, which state the behaviour this record delivers. Out of scope: R18
(`requirements.md:323`) and UC11 (l. 266) state the rule this record serves, and stay as written.
ADR-0028's seven hits (l. 151–187) are immutable; its l. 171 premise and l. 179 contract are what
this record narrows. ADR-0031's three hits and `test_sensor.py:1185` keep config mirrors disabled
by default and outside `sync_disabled_by`. ADR-0028's ADL row (`docs/adl/README.md:37`) points
here.
