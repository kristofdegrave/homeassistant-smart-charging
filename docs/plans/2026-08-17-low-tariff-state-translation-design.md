# Low-tariff adapter role state-translation — design

**Date:** 2026-08-17
**Status:** draft (issue #746, analysis: #743 / PR #745, epic n/a)
**Type:** implementation design (a slice of RA2 / C4 in `docs/design/project-plan.md` — not a new
architectural decision)

This document derives the concrete config-flow fields, adapter class, and TDD build order for the
`low_tariff` adapter role widening merged into the analysis layer in PR #745
(`docs/analysis/entity-catalog.md`'s `low_tariff` row, `docs/analysis/system-overview.md`'s
`low-tariff flag` glossary term, and `docs/analysis/use-cases/UC12-configure-installation-through-guided-flow.md`
steps 7 and 9): the `low_tariff` role must accept a tariff signal whose raw state is not already
`on`/`off`, translated to a boolean via a user-supplied list of raw states that count as low
tariff — any other raw state resolving to not-low-tariff.

---

## 1. Why this slice

Today `low_tariff` is read by `BooleanReadAdapter` (`adapters/boolean.py`), which only recognises
the entity's native `on`/`off` state and returns `None` for anything else.
`config_flow.py`'s `CONF_LOW_TARIFF_ENTITY` selector (`UNGATED_MAPPING_SCHEMA`) restricts the
picker to `binary_sensor`/`input_boolean` domains, so a real-world tariff signal exposed as a
`sensor` with a textual state (e.g. `low`/`high`) cannot be mapped at all.

**Why a `None` reading is the wrong shape for an unmatched raw state here (not an ADR-0007
argument).** `low_tariff` is an *optional* role. `coordinator.py`'s `_resolve_deadline_and_reserve`
(`coordinator.py:303-309`) already defines what a `None` reading means for it: `ctx.low_tariff_active`
defaults to `True` before the read, and is only overwritten `if low_tariff_reading is not None` —
so `None` here is never a fault: ADR-0007's Decision scopes the fault *rule* to *required* roles;
its Consequences note more broadly that "an unmapped or unavailable entity is [a fault], unlike
grid voltage" (NF4's own named exception) — but that broader framing describes what happens when
nothing *consumes* an optional `None` specially, not a blanket rule. `low_tariff` is exactly such a
consumer: `_read_role`'s guarded optional-role read already returns `None` for both "role not
wired" and "adapter read failed", and `_resolve_deadline_and_reserve` (the sole reader) treats
both identically as "stay at the always-active default". So `None` here collapses to the glossary's
single-tariff "always active" default, identical to the role being unmapped at all — not a fault,
and not the ADR-0007 signal ADR-0003's `charger_status` translation relies on to trigger a fault
cycle. If `LowTariffReadAdapter` reused `StatusReadAdapter`'s shape (unmatched
raw state → `None`), an actively-mapped, non-boolean tariff signal currently reporting an unlisted
(e.g. high-tariff) state would silently resolve to **always low tariff** — the opposite of what the
installation configured, and indistinguishable from never having mapped the entity at all. Returning
`False` instead is not a stylistic choice: it is the only reading that lets a mapped, currently
high-tariff signal actually suppress opportunistic overnight `Captar` (`resolution-rules.md`, Auto
mode-selection row 4). This is also exactly what the entity-catalog's own wording says ("every other
raw state resolving to not-low-tariff", PR #745) — the analysis doc already settled this; this
section only explains *why* that's the behaviorally correct choice, not a new decision.

This is a genuinely different unmatched-state contract from `charger_status`'s existing translation
(`StatusReadAdapter`, `CONF_CONNECTED_STATES`/`CONF_CHARGING_STATES` → derived
`CONF_STATUS_TRANSLATION`): `charger_status` is a *required* role, its translation is exhaustive
across three canonical values, and an unmatched raw state genuinely is the ADR-0007 fault signal
there (`status.py`'s own docstring). `low_tariff`'s translation is optional, one-directional (only
"which raw states count as low"), and — per the reasoning above — an unmatched raw state must be a
defined boolean value, not `None`. Reusing `StatusReadAdapter` would therefore not just be a stylistic
mismatch but would produce the wrong runtime behavior; a new adapter class is the correct fit — the
same "one class per role" shape ADR-0003 already establishes, and the same reasoning
`adapters/boolean.py`'s own docstring gives for why `BooleanReadAdapter` itself is a distinct class
from `StatusReadAdapter`. No ADR amendment is needed: ADR-0003 sets the adapter *shape* (one class
per role, `read()`/`write()`), not a single translation-table contract every role must share, and
per-role unmatched-state semantics are exactly the kind of role-specific detail ADR-0003 leaves to
each adapter class.

**Back-compat.** No config-entry migration is needed. Every existing config entry lacks
`CONF_LOW_TARIFF_STATES` entirely; `build_adapters` reads it via `data.get(CONF_LOW_TARIFF_STATES, "")`
(§3), so an existing `binary_sensor`/`input_boolean` mapping is completely unaffected in practice —
its native `on`/`off` state is checked by `LowTariffReadAdapter`'s first branch before the
(empty) translation table is ever consulted (§3), and a `binary_sensor`/`input_boolean` entity's
own state machine only ever reports `on`, `off`, `unavailable`, or `unknown` — never a third raw
value that could reach the translation-table branch at all.

| Analysis requirement (PR #745) | This slice |
| --- | --- |
| `low_tariff` accepts an entity whose state is not already on/off | Widen `CONF_LOW_TARIFF_ENTITY`'s selector domains (§2) |
| A user-supplied table lists which raw states count as low tariff | New `CONF_LOW_TARIFF_STATES` config field, parsed at adapter-construction time (§2, §3) |
| Every other raw state resolves to not-low-tariff (not a fault) | New `LowTariffReadAdapter` (§3) |
| UC12 step 7: low-tariff mapping shown with its own state-translation table | Field added to the existing ungated-mappings step (§2) — no new step, no new gate |

**Out of scope:** widening `home_day_external`/`car_home` the same way — the analysis change is
scoped to `low_tariff` only (PR #745 touches no other adapter role); `BooleanReadAdapter` is
untouched and keeps serving those two roles.

---

## 2. Config-flow surface

`custom_components/smart_charging/config_flow.py`, `UNGATED_MAPPING_SCHEMA` (currently only
`CONF_LOW_TARIFF_ENTITY: _entity(["binary_sensor", "input_boolean"])`):

```python
vol.Optional(CONF_LOW_TARIFF_ENTITY): _entity(
    ["binary_sensor", "input_boolean", "sensor", "select", "input_select"]
),
vol.Optional(CONF_LOW_TARIFF_STATES): str,  # comma-separated raw states, same shape as
                                             # CONF_CONNECTED_STATES/CONF_CHARGING_STATES
```

`select` is added alongside `input_select` — a tariff-period value is just as plausibly exposed by
an integration-provided `select` entity as by a manually-configured helper, and admitting one
without the other would be an unjustified asymmetry. `input_number`/`number` are deliberately left
out (§7): a numeric price entity needs threshold comparison, a different capability that string
state-matching cannot express. `switch` is also left out: it is normally a *command* entity
representing something the user or another automation controls, not a read-only signal from the
tariff provider, and admitting it would let a config author map a control surface that this role
never writes to — a future issue can add it if a real switch-backed tariff signal turns up.

`const.py` gains one new key, next to `CONF_LOW_TARIFF_ENTITY`:

```python
CONF_LOW_TARIFF_STATES = "low_tariff_states"  # raw states meaning "low tariff", comma-separated
```

**Stored as the raw string, not a parsed list — deliberately diverging from
`CONF_CONNECTED_STATES`/`CONF_CHARGING_STATES` → derived `CONF_STATUS_TRANSLATION`.** Those two
fields are `vol.Required` on the `core` step; reconfigure already accepts (as a documented, known
gap — `tests/test_config_flow.py:533-536,545-546`) that they have no stored raw value to prefill,
because a blank *required* field forces the user to retype it before the step can even submit.
`CONF_LOW_TARIFF_STATES` is `vol.Optional`: if it were parsed into a `list[str]` and stored under
its own key the same way, `async_step_mappings`'s reconfigure prefill
(`self._maybe_prefill(UNGATED_MAPPING_SCHEMA)` → `add_suggested_values_to_schema(schema, entry.data)`,
`config_flow.py:619-634`) would try to suggest a `list` into a `str`-typed form field — and because
nothing forces a retype on an optional field, a user who leaves it untouched on reconfigure would
silently submit a blank string, erasing a previously-configured translation table. That is exactly
the data-loss class issue #499 fixed for every other optional mapping
(`tests/test_config_flow.py:533-536`, "any optional mapping the user doesn't retype is silently
dropped on save").

Keeping `CONF_LOW_TARIFF_STATES` as the raw comma-separated string end-to-end avoids the problem by
construction: the schema field type (`str`) and the stored `data` value (`str`) always match, so
`add_suggested_values_to_schema` prefills it correctly on reconfigure exactly like every other
already-working optional string mapping (e.g. `CONF_GRID_VOLTAGE_ENTITY`,
`CONF_NOTIFICATION_TARGET_ENTITY`) — no special-casing needed in `_split_data` at all, and no new
exclude/derive pair to add. Parsing into a `list[str]` happens once, at adapter-construction time,
inside `LowTariffReadAdapter.__init__` (§3) — `adapters/` reuses the same
`[s.strip() for s in raw.split(",") if s.strip()]` shape `config_flow.py`'s `_parse_states()`
already uses, duplicated locally rather than imported, since `adapters/` has no existing dependency
on `config_flow.py` and this one-line helper isn't worth introducing one for.

No new step, no new gate: `low_tariff` stays on the existing ungated `mappings` step
(`STEP_MAPPINGS`, `CONFIG_TABLE`) — UC12 step 7 already presents it unconditionally, and PR #745's
UC12 edit only added a parenthetical to that same field, not a new step.

`OPTIONS_TABLE`/`OPTIONS_FLOW` are untouched: per ADR-0005, an entity mapping (and its
translation) is config-entry **data**, set at install/reconfigure time only, exactly like
`CONF_CONNECTED_STATES`/`CONF_CHARGING_STATES` today.

---

## 3. New adapter

`custom_components/smart_charging/adapters/tariff.py` (new file, one class per role per ADR-0003):

```python
"""Low-tariff adapter: normalizes a tariff signal to a boolean (ADR-0003, RA2 extension)."""

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from ._read_only import _ReadOnlyAdapter


class LowTariffReadAdapter(_ReadOnlyAdapter):
    """Reads the tariff signal and normalizes it to the boolean low-tariff flag.

    A raw state matching HA's native on/off vocabulary is checked *first* and used
    directly (the `binary_sensor`/`input_boolean` case, unchanged from
    `BooleanReadAdapter`'s prior behaviour) -- this takes precedence over
    `low_states` even if a raw `on`/`off` value were also listed there, which is
    never an ambiguity in practice since a native on/off entity has no other raw
    state to list. Otherwise `low_states` -- the user-supplied set of raw states
    that count as low tariff, parsed from the config-entry's raw comma-separated
    string (design doc SS2 -- kept as a string end-to-end so reconfigure prefill
    round-trips correctly) -- decides membership; any other raw state resolves to
    `False`. This is a deliberate, *restrictive* default for a present-but-unmatched
    state -- distinct from the glossary's *permissive* "always active" default for a
    genuinely unmapped or unavailable signal (entity-catalog.md; SS7's own deferred-
    asymmetry note). Returns `None` only when the entity itself is
    missing/unavailable/unknown -- the ADR-0007 fault signal proper.
    """

    def __init__(self, hass: HomeAssistant, entity_id: str, low_states: str) -> None:
        super().__init__(hass, entity_id)
        self._low_states = {s.strip() for s in low_states.split(",") if s.strip()}

    async def read(self) -> bool | None:
        state = self._live_state()
        if state is None:
            return None
        if state.state == STATE_ON:
            return True
        if state.state == STATE_OFF:
            return False
        return state.state in self._low_states
```

`adapters/factory.py`'s `build_adapters` (currently `if data.get(CONF_LOW_TARIFF_ENTITY):
adapters[ROLE_LOW_TARIFF] = BooleanReadAdapter(hass, data[CONF_LOW_TARIFF_ENTITY])`) switches to:

```python
if data.get(CONF_LOW_TARIFF_ENTITY):
    adapters[ROLE_LOW_TARIFF] = LowTariffReadAdapter(
        hass, data[CONF_LOW_TARIFF_ENTITY], data.get(CONF_LOW_TARIFF_STATES, "")
    )
```

`BooleanReadAdapter` is otherwise untouched and keeps building `home_day_external`.

---

## 4. Success criteria

"Works" means: **every existing test passes unchanged, plus new tests proving the widened
selector, the state-translation table's round-trip through the config flow, and the new
adapter's three-way behaviour (native on/off, listed raw state, unlisted raw state).**

1. `CONF_LOW_TARIFF_ENTITY` accepts a `sensor`, `select`, or `input_select` entity in the config
   flow, not only `binary_sensor`/`input_boolean`.
2. A submitted `CONF_LOW_TARIFF_STATES` comma-separated string is stored in config-entry **data**
   **as-is** (raw string, unparsed) — deliberately unlike `CONF_CONNECTED_STATES`/
   `CONF_CHARGING_STATES`, which are parsed into a derived `CONF_STATUS_TRANSLATION` key at submit
   time (§2 explains why: an optional field must round-trip through reconfigure prefill without a
   type mismatch).
3. Reconfigure on the `mappings` step prefills `CONF_LOW_TARIFF_STATES` with its previously-stored
   raw string, and re-submitting the prefilled form unchanged preserves it — the issue #499 class
   of silent data loss does not apply to this field.
4. `LowTariffReadAdapter.read()`:
   - returns `True`/`False` directly when the entity's raw state is `on`/`off` (unchanged from
     `BooleanReadAdapter`'s existing behaviour for `binary_sensor`/`input_boolean` mappings — no
     regression for installations that never adopt the new field);
   - returns `True` when the raw state is a member of the parsed `low_states` set;
   - returns `False` for any other raw state, including when `low_states` is empty (the
     entity-catalog's stated default);
   - returns `None` when the entity is missing/unavailable/unknown (ADR-0007 fault signal,
     unchanged).
5. `low_tariff_entity` left unmapped still builds no adapter (`resolution-rules.md`'s "always
   active" fallback is a **resolution-rules** concern — the flag defaults to active only because
   nothing reads a wired role, not because this adapter returns a default itself — unchanged from
   today).
6. `CONF_LOW_TARIFF_STATES` left unmapped while `CONF_LOW_TARIFF_ENTITY` **is** mapped defaults to
   an empty string, parsed to an empty set (criterion 4's third case) — a non-boolean entity with
   no configured translation always resolves to not-low-tariff, never a fault.
7. **Integration checkpoint** (mirroring `project-plan.md`'s C4 checkpoint shape, "the entry C4
   writes drives RA1's factory"): a config entry produced by actually submitting the `mappings`
   step with a `sensor`-domain entity and a `CONF_LOW_TARIFF_STATES` value, fed through
   `build_adapters`, yields a `LowTariffReadAdapter` whose parsed `_low_states` matches what was
   typed — proving the config-flow output and the factory's input actually agree, not just each
   half in isolation (T3's test, §5).

---

## 5. Testing (ADR-0009 harness split)

- `LowTariffReadAdapter` is HA-coupled (reads live entity state via `_ReadOnlyAdapter`), so per
  ADR-0009 its tests are **HA harness**, in a new `tests/adapters/test_tariff.py` (mirroring
  `tests/adapters/test_status.py`'s existing shape for `StatusReadAdapter`): on/off passthrough,
  listed-state membership, unlisted-state default, missing-entity fault.
- `adapters/factory.py`'s `build_adapters` change is covered by extending its existing HA-harness
  test file's `low_tariff` case (whichever file today asserts `ROLE_LOW_TARIFF` resolves to a
  `BooleanReadAdapter` — Task 2 locates and updates it to assert `LowTariffReadAdapter` instead,
  plus a new case passing `CONF_LOW_TARIFF_STATES`).
- `config_flow.py`'s widened selector and the `CONF_LOW_TARIFF_STATES` round-trip (install
  submission *and* reconfigure prefill/re-submission, criteria 2-3) are HA harness (ADR-0009 —
  config flow is HA-coupled), extending `tests/test_config_flow.py`'s existing ungated `mappings`
  step coverage.
- **Integration checkpoint** (criterion 7): one test drives the config flow to produce a real entry
  and feeds its `data` into `build_adapters`, asserting the resulting `LowTariffReadAdapter`'s
  `_low_states` matches what was submitted — not just each half tested against hand-built fixtures.

**Regression**: the full existing suite must pass unchanged, in particular every existing
`low_tariff`/`home_day_external` adapter-factory test and every existing `mappings`-step
config-flow test — `BooleanReadAdapter` and `home_day_external`'s config-flow field are untouched.

---

## 6. Packaging

```text
custom_components/smart_charging/
  adapters/
    tariff.py       # NEW — LowTariffReadAdapter
    factory.py       # low_tariff branch switches from BooleanReadAdapter to LowTariffReadAdapter
  config_flow.py      # CONF_LOW_TARIFF_ENTITY selector widened; + CONF_LOW_TARIFF_STATES field
                       #   (stored as-is, no _split_data change -- SS2)
  const.py             # + CONF_LOW_TARIFF_STATES
  strings.json          # + low_tariff_states label (STEP_MAPPINGS)
  translations/
    en.json              # + low_tariff_states label
    nl.json              # + low_tariff_states label
tests/
  adapters/
    test_tariff.py    # NEW
  (existing adapter-factory and config-flow test files gain low_tariff cases)
```

---

## 7. Deliberately deferred

- **Widening `home_day_external`/`car_home` the same way.** Not requested by the merged analysis
  change (PR #745 scopes `low_tariff` only); `BooleanReadAdapter` stays exactly as it is for those
  two roles. A future analysis change would need its own issue if either signal turns out to need
  a translation table too.
- **Rejecting an empty `CONF_LOW_TARIFF_STATES` at config-flow validation time.** The entity-catalog
  wording treats "no list" and "empty list" as the same not-low-tariff default (§4, criterion 5),
  so there is nothing to reject — an empty/absent table is valid, expected input for an
  installation that maps a non-boolean signal but (for whatever reason) currently has no known
  "low" states to list.
- **A dedicated glossary/const name distinguishing the raw input field from a derived value**, the
  shape `CONF_CONNECTED_STATES`/`CONF_CHARGING_STATES` → `CONF_STATUS_TRANSLATION` uses.
  Deliberately *not* used here (§2): that split works for `charger_status` only because both
  source fields are `vol.Required`, so reconfigure never needs to prefill them from a stored
  derived value in the first place. Introducing the same split for `CONF_LOW_TARIFF_STATES` (an
  optional field) would silently break reconfigure prefill instead (§2's reconciliation) — the one
  key stays a plain string round-tripped as-is, parsed only where it's consumed (§3).
- **Changing the unmapped-role default.** `coordinator.py:303-309` treats an unmapped `low_tariff`
  role (adapter absent, no `CONF_LOW_TARIFF_ENTITY`) and a mapped-but-`None`-reading role
  identically — both default `ctx.low_tariff_active` to `True` (the glossary's single-tariff
  "always active" fallback). That is pre-existing, coordinator-level behaviour, untouched by this
  slice: `LowTariffReadAdapter` only changes what a *present, non-fault* raw state resolves to
  (§1); it does not and should not change what a genuinely missing/unavailable/unmapped signal
  resolves to. The two are opposite-looking outcomes from adjacent inputs (no signal → active;
  signal present but unmatched → not active) and are deliberately not unified — flagged here so a
  future reader doesn't mistake the asymmetry for an oversight.

---

## 8. Next step

This design feeds the `writing-plans` skill to produce the ordered, test-driven implementation
plan (`2026-08-17-low-tariff-state-translation.md`). Build order: `LowTariffReadAdapter` (new,
standalone, plain-file HA harness test) → `adapters/factory.py` wiring → `config_flow.py` selector
widening + `CONF_LOW_TARIFF_STATES` field + `_split_data` parsing → full regression pass. No
`custom_components/` code is written until the paired plan exists and is approved.
