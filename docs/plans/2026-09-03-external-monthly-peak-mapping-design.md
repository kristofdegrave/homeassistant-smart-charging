# Design: external monthly-peak sensor — role, merge, and the `captar` step's mapping half (#922)

Derives from three Accepted ADRs, in the order they constrain the build:
[ADR-0030](../adl/0030-external-monthly-peak-sensor.md) (the optional adapter role),
[ADR-0032](../adl/0032-external-monthly-peak-precedence.md) (the `max()` merge feeding
`resolve_effective_peak_limit`), and
[ADR-0033](../adl/0033-captar-step-gains-a-mapping-half.md) (the mapping's config-flow home, which
partially supersedes [ADR-0027](../adl/0027-config-flow-topic-step-structure.md) point 3's
enumeration but not its rule). Behaviour is owned by
[`requirements.md`](../analysis/requirements.md) R3 AC8/AC9 and R18 AC5,
[`resolution-rules.md`](../analysis/resolution-rules.md) row 2,
[`UC12`](../analysis/use-cases/UC12-configure-installation-through-guided-flow.md) step 6 / 6a, and
[`entity-catalog.md`](../analysis/entity-catalog.md)'s `monthly_peak_external` row and
Captar-dependent-rows note. This document adds only sequence, concrete files and signatures, and
tests. It introduces no service and no call direction `system-design.md` does not already have.

## Scope — the whole strand, not just the config-flow half

Issue #922 is worded around ADR-0033's config-flow rework, and that is the largest part of the
work. It is not a sufficient slice on its own, and this document deliberately widens to the whole
strand for two checkable reasons rather than by preference:

1. **The config-flow half has nothing to write into.** Direct inspection of `main` finds no
   `ROLE_MONTHLY_PEAK_EXTERNAL`, no `CONF_MONTHLY_PEAK_EXTERNAL_ENTITY`, and no occurrence of
   `monthly_peak_external` anywhere under `custom_components/` or `tests/`. A config-flow-only
   slice would collect a key that no factory branch reads and no engine consumes — exactly the
   inert outcome ADR-0033's own Decision rejects Option A for.
2. **ADR-0032 delegates two named decisions to "the implementation spec."** Its Consequences leave
   the merge's "exact call-site placement and signature change" and the question of whether
   `sensor.smart_charging_monthly_peak_kw` needs "a rename, a second entity, or no change beyond
   documentation" to this document. ADR-0030 likewise names the reading's unit contract as "an
   implementation-spec obligation this ADR surfaces but does not itself resolve." No other spec
   issue in epic #873 exists to own them.

Slices touched, per `project-plan.md`: **RA2** (policy-input read adapters), **E5**
(Billing-Protection Engine), **M1** (the Coordinator's per-cycle read), **C4** (the config/options
flow). No slice's **service** is widened — no new service, no new call direction. RA2's role
**enumeration** does grow, and that is stated rather than glossed: `project-plan.md` lists RA2's
roles as a closed five (`solar_forecast`, `low_tariff`, `car_home`, `departure_external`,
`home_day_external`) and its integration checkpoint counts "all thirteen non-vehicle-limit roles",
so a fourteenth role extends both. `ROLE_SOLAR_POWER` set the precedent for treating that as a
slice extension rather than a new slice. No test pins either number, so nothing breaks — but this
document holds ADR-0027 to the distinction between an enumeration and the rule behind it, and owes
`project-plan.md` the same.

**Out of scope**, and named rather than left silent:

- ADR-0030's Option D (recorder / long-term-statistics backfill) — explicitly left open there as
  complementary follow-up.
- Surfacing the *merged* operand as its own entity — ADR-0032 leaves this open; D-6 below decides
  against it for now and says why.
- **R18 AC5's own wording.** Its list of the fields the CapTar-gated step presents is still a
  closed five-item enumeration that does not name this mapping. ADR-0033's Consequences name that
  amendment as owed analysis work, and it is an analysis-doc change under its own review protocol,
  not a task in this plan. UC12, `resolution-rules.md`, `entity-catalog.md` and
  `system-overview.md` have all already been amended and are used here as anchors as they stand.

## A factual correction this document records

ADR-0033's Context states, in its Option A description, that "the `ROLE_MONTHLY_PEAK_EXTERNAL` key
exists in `const.py`". It does not — ADR-0030 named it as a Consequence that has not yet been
built. Nothing in ADR-0033's Decision or Consequences turns on it (its subject is the mapping's
config-flow home, which is unaffected), so this is recorded here as a spec-level correction rather
than escalated into a superseding ADR. The practical effect is that T1 below creates the role key
this build assumes, instead of merely referencing it.

## Success criteria

- With the mapping unset, every observable behaviour is bit-for-bit what it is today: the role is
  absent from the factory's dict, `resolve_monthly_peak_operand` returns the internally-tracked
  value unchanged, and `sensor.smart_charging_effective_peak_limit` resolves exactly as before
  (R3 AC9).
- With the mapping set and the entity reporting a usable power value, the effective peak limit's
  monthly-peak-demand operand never resolves below that reading, and the existing
  `min(..., max_peak_kw)` step still bounds the result (R3 AC8, `resolution-rules.md` row 2).
- A reading in **W** yields the same operand as the identical reading in **kW** — the unit contract
  ADR-0030 obliges this spec to resolve (D-1).
- The `captar` step renders the mapping field on install (beside its six threshold values) and
  alone on reconfigure, only while CapTar is declared present this run; `power` is still absent
  from reconfigure unconditionally (ADR-0033; ADR-0027 point 3's rule, unamended).
- A reconfigure form whose mapping is prefilled and resubmitted unchanged leaves `entry.data`'s
  mapping intact — the issue-#499 silent-drop class, given its own regression test (D-7).
- Declaring CapTar absent on reconfigure drops the mapping from the data bucket while the six
  options-bucket values lie dormant (`entity-catalog.md`'s Captar-dependent-rows note).
- `ruff check .` / `ruff format --check .` clean; full suite green at every task boundary.

## Concrete decisions this document makes

**D-1 — Unit normalisation lives in a new adapter class, and an unusable unit reads as absent.**
`NumericReadAdapter` (`adapters/numeric.py`) does `float(state.state)` with no unit handling at
all; the existing roles that use it rest on a documented unit convention. ADR-0030 records that
DSO/smart-meter peak sensors "commonly report in W", so that convention cannot be relied on here.
A new `PowerKilowattReadAdapter` in the same module reads the state's own
`unit_of_measurement` attribute and converts to `UnitOfPower.KILO_WATT` via Home Assistant's
`homeassistant.util.unit_conversion.PowerConverter` — the constant, not a `"kW"` literal.

The important half of this decision is the fallback. When the state is missing, `unavailable`,
`unknown` or non-numeric — or when the unit attribute is **absent or not a member of
`PowerConverter.VALID_UNITS`** — the adapter returns `None`. That is not the same state as
factory-level role absence (T1 pins the difference deliberately: an unmapped key leaves the role
out of the dict entirely), but the two are **equivalent at the merge**, which is what matters here:
`resolve_monthly_peak_operand` receives `None` either way, and R3 AC9 then governs. It deliberately does **not** fall back
to assuming kW, because the two mistakes are not symmetric: a W reading misread as kW (4090 →
4090 kW) drives the operand straight to `max_peak_kw`, which *widens* the clamp and removes the
protection R3 exists to give, whereas the reverse mistake resolves to a tiny value the peak floor
absorbs harmlessly. Silently unmapped is the safe failure; silently unclamped is not.

**D-2 — The merge is a separate pure function, not a new parameter on
`resolve_effective_peak_limit`.** ADR-0032 leaves the placement to this document. Adding a
parameter to `resolve_effective_peak_limit` forces a choice between a default (which a call site
can silently omit — and there are two) and a required argument (which rewrites ten existing
positional calls in `tests/engines/test_billing_protection.py` for no behavioural gain). Instead,
`engines/billing_protection.py` gains a sibling:

```python
def resolve_monthly_peak_operand(internal_kw: float, external_kw: float | None) -> float
```

returning `internal_kw` when `external_kw` is `None`, else `max(internal_kw, external_kw)`. It is
pure, so it is plain-pytest-testable in isolation (ADR-0009), and it names the rule as its own
unit rather than burying it in the coordinator. `resolve_effective_peak_limit`'s signature,
docstring and existing tests are untouched.

**D-3 — The merge is computed once per cycle, at the tracker's own call site.** `coordinator.py`
already computes `monthly_peak_kw` once (~line 418) and feeds it to *both*
`resolve_effective_peak_limit` calls (~line 422, the provisional pre-`ctx` value used only for the
`ev_soc`-fault early return, and ~line 621, the final one). The external read and the merge slot in
directly beneath that single assignment, and both call sites then take the merged local. There is
no second copy for the two to drift apart — the same lockstep reasoning the comment at the final
call site already records for `ctx.effective_peak_limit_kw`.

**D-4 — The read uses `_read_role`, so the ADR-0021 diagnostic wiring is automatic.**
`await self._read_role(ROLE_MONTHLY_PEAK_EXTERNAL)` is the codebase's one guarded optional-role
read: it returns `None` when the role is unwired and otherwise mirrors the value into
`_role_readings`, which `_current_adapter_readings` filters into
`sensor.smart_charging_adapter_readings`. The role is **not** added to
`ROLES_ADAPTER_READINGS_EXCLUDED` (five members today) — it is read by `_run_cycle` itself, unlike
the three roles excluded because another Manager rather than `_run_cycle` reads them
(`ROLE_CAR_HOME`, `ROLE_VEHICLE_CHARGE_LIMIT`, `ROLE_HOME_DAY_EXTERNAL`) and the two excluded for
being write-only — so ADR-0030's "surfaces by the existing default" holds structurally, with no
sensor-side change at all.

**D-5 — No CapTar capability gate on the merge, because the mapping cannot outlive the
capability.** R3's clamp does not run when CapTar is absent, so a merged operand would be inert
there anyway. It is also unreachable: the mapping is a data-bucket field collected only on the
CapTar-gated step, and reconfigure rewrites the data bucket wholesale (D-8), so withdrawing CapTar
removes the key, which removes the factory branch, which leaves `external_kw` at `None`. Adding an
explicit `captar_available` guard to the merge would be a second, redundant expression of a fact
the buckets already enforce.

**D-6 — `sensor.smart_charging_monthly_peak_kw` keeps its meaning; no rename, no second entity.**
ADR-0032 leaves this open. The sensor documents "the integration's own tracked peak", and that is
still exactly what `CycleResult.monthly_peak_kw` carries after this change — the merge happens
downstream of it, in a separate local. A rename would break a `RestoreSensor` whose stored state
seeds the tracker across restarts, for a naming nicety. A second entity is unwarranted because the
merged value is already observable three times over: `sensor.smart_charging_effective_peak_limit`
shows the resolved value that actually drives the clamp, `sensor.smart_charging_peak_headroom_a` is
derived from that same operand and so tracks it automatically (`coordinator.py` ~639), and the
external operand's raw reading shows on the adapter-readings sensor (D-4). What remains is a
documentation obligation, and
`entity-catalog.md` already discharges it — its `effective_peak_limit` row states the merged
formula in full.

**D-7 — The reconfigure prefill is a first-class requirement, not a courtesy.** ADR-0033 names the
silent-drop class explicitly. The repo already carries its named regression test,
`tests/test_config_flow.py::test_reconfigure_form_prefills_existing_mappings` (issue #499: "any
optional mapping the user doesn't retype is silently dropped on save"), and a stronger sibling,
`test_reconfigure_grid_step_prefills_low_tariff_states`, which asserts the resubmitted value
survives into `entry.data`. The new field gets coverage of the second, stronger shape — render,
read the suggested value, resubmit unchanged, assert `entry.data[CONF_MONTHLY_PEAK_EXTERNAL_ENTITY]`
still holds it — because rendering a suggestion is not the property that matters; surviving the
save is.

**D-8 — Clearing the mapping and withdrawing CapTar both already work; they need tests, not code.**
`_async_finish` computes `data = _split_data(self._answers)` and, in reconfigure mode, calls
`async_update_reload_and_abort(entry, data=data)` — a wholesale replacement of the data bucket, not
a merge. So an emptied optional selector is simply absent from `self._answers` and therefore absent
from the new data (UC12 6a: "leaving the mapping unset or clearing it is equivalent either way"),
and a withdrawn CapTar capability skips the step entirely, dropping the key with it
(`entity-catalog.md`: "withdrawing CapTar on reconfigure drops it from the data bucket … it does
not resume dormant"). Both are emergent properties of a mechanism that predates this change; both
are load-bearing for this field and currently unasserted for it.

## Structure

### The mapping's chain, end to end

| Piece | File | Shape |
| --- | --- | --- |
| Data key | `const.py` (DATA block, ~185-224) | `CONF_MONTHLY_PEAK_EXTERNAL_ENTITY = "monthly_peak_external_entity"`; never a member of `OPTION_KEYS` |
| Role key | `const.py` (roles block, ~120-156) | `ROLE_MONTHLY_PEAK_EXTERNAL = "monthly_peak_external"` — matching `entity-catalog.md`'s row id |
| Adapter | `adapters/numeric.py` | `PowerKilowattReadAdapter(_ReadOnlyAdapter)` (D-1) |
| Factory branch | `adapters/factory.py` | `if data.get(CONF_MONTHLY_PEAK_EXTERNAL_ENTITY): adapters[ROLE_MONTHLY_PEAK_EXTERNAL] = PowerKilowattReadAdapter(hass, data[CONF_MONTHLY_PEAK_EXTERNAL_ENTITY])` — the truthiness-`.get` idiom `ROLE_HOME_DAY_EXTERNAL` and `ROLE_LOW_TARIFF` already use, so an unmapped key leaves the role out of the dict |
| Merge | `engines/billing_protection.py` | `resolve_monthly_peak_operand` (D-2) |
| Per-cycle read + merge | `coordinator.py` (~418-427) | `_read_role` then the merge, feeding both `resolve_effective_peak_limit` call sites (D-3, D-4) |
| Schema fragment | `config_flow.py` | `CAPTAR_MAPPING_SCHEMA` (below) |
| Table gate | `config_flow.py` `CONFIG_TABLE` | plain capability gate (below) |
| Step method | `config_flow.py` `async_step_captar` | the `async_step_solar` idiom (below) |
| Strings | `strings.json`, `translations/en.json`, `translations/nl.json` | `config.step.captar` only (below) |

### The schema fragment's name

It is `CAPTAR_MAPPING_SCHEMA`, a module-level constant:

```python
CAPTAR_MAPPING_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_MONTHLY_PEAK_EXTERNAL_ENTITY): _entity("sensor"),
    }
)
```

Two constraints converge on that name and shape. The shipped convention is that mapping halves are
module-level `*_MAPPING_SCHEMA` constants (`GRID_`, `SOLAR_`, `DEADLINE_`, `NOTIFICATIONS_`) while
only threshold halves are `_x_threshold_schema(defaults)` functions, because only they take stored
defaults — a mapping half carrying one optional entity selector takes none. Independently,
`tests/test_config_flow.py::test_flat_flow_schema_surface_is_deleted` asserts
`_captar_mapping_schema` is permanently absent as a module symbol; the new constant is a different
symbol under the convention that applies to it, so that assertion needs no change and must not be
weakened. The field is `vol.Optional` per UC12 6a ("left unmapped by default"), and the selector is
domain-restricted to `sensor`, matching `CONF_DEPARTURE_EXTERNAL_ENTITY` and
`CONF_SOLAR_FORECAST_ENTITY`.

### The table row and its comment

`CONFIG_TABLE`'s `STEP_CAPTAR` row drops its second conjunct and becomes the same plain capability
gate `solar`/`deadline`/`notifications` carry:

```python
FlowStep(step_id=STEP_CAPTAR, gate=lambda flow: bool(flow._answers.get(CONF_CAPTAR_AVAILABLE))),
```

`STEP_POWER`'s row is untouched and becomes the sole place the flow-mode half of ADR-0027 point 3's
rule does any work. The comment block above `CONFIG_TABLE` currently reads "`power`/`captar` have
no mapping half at all, so both are gated off entirely in reconfigure mode" and cites point 3
inline; ADR-0033's Consequences make re-pointing that comment part of this work, not a cosmetic
tidy — a reader who arrives at point 3 through this comment rather than through the ADL index has
no other pointer to the narrowing. It must name `power` alone, say that `captar` is now a plain
capability gate because it has acquired a mapping half, and cite ADR-0033 beside ADR-0027.

### `async_step_captar`

It takes the four-line idiom `async_step_solar` already uses — mapping half always, threshold half
extended on only when the mode is not reconfigure, `_maybe_prefill` on the rendered schema:

```python
schema = CAPTAR_MAPPING_SCHEMA
if self._mode is not FlowMode.RECONFIGURE:
    schema = schema.extend(_captar_threshold_schema().schema)
if user_input is None:
    return self.async_show_form(step_id=STEP_CAPTAR, data_schema=self._maybe_prefill(schema))
self._answers.update(user_input)
return await self._async_advance(after=STEP_CAPTAR)
```

Its docstring today asserts the step "needs neither `self._mode` branching nor `_maybe_prefill` in
its own body" and must be rewritten with it. A fourth docstring goes stale one task earlier, the
moment the fragment itself lands: `_captar_threshold_schema`'s (~454-456) opens "UC12 (topic-step)
step 6 threshold half -- CapTar has no mapping half at all". ADR-0033 names three and warns the
count is a floor, not a total; this is the one the floor misses, and it is also the one a
`power`-and-`captar` prose sweep cannot find, since it names `captar` alone. Two further docstrings
go stale at the same moment as `async_step_captar`'s without their logic changing, and ADR-0033
names both: `_async_finish`'s, which reasons that
"neither `power` nor `captar` is reachable in this mode, so no threshold answer ever entered
`self._answers`" — the terminal split is bucket-driven, so the code stays correct while that
reasoning does not (`captar` is now reachable, but contributes no `OPTION_KEYS` member in
reconfigure, since its threshold half is not rendered) — and `async_step_reconfigure`'s, which
restates the two-row skip directly.

The **options** flow is untouched. `OPTIONS_TABLE`'s `captar` row and its step method keep
rendering the threshold half alone: the new field is data-bucket (ADR-0005) and the options flow
writes options only (ADR-0027 point 4). ADR-0033 flags this as the one place an implementer could
plausibly over-apply the decision, so T6 asserts it rather than leaving it to inference.

### Translations

Only `config.step.captar` changes, in all three files:

- `description` — "Tune CapTar's peak-shaving thresholds." is written for a threshold-only screen
  and is wrong above a single-mapping reconfigure form. It becomes a both-contexts sentence on the
  model `solar` already uses ("Map the entities Solar mode reads and tune its thresholds.").
- `data.monthly_peak_external_entity` and `data_description.monthly_peak_external_entity` — a label
  and a description. The label must carry no `"required if"` / `"required when"` qualifier;
  `tests/test_config_flow_translations.py::test_no_field_label_carries_a_conditional_qualifier`
  enforces that. `"(optional)"` is fine — `solar_power_entity` sets the precedent.
- `options.step.captar` is **unchanged** (its own orphaned-field check is per section, and the
  options step stays threshold-only).

`title` ("CapTar") already reads correctly in both contexts and does not change.

### The two fixtures that fail quietly

ADR-0033 warns that the dangerous failure here is not a red assertion but a roster that must
*grow*. There are two, in two different files:

- `tests/test_config_flow.py::_ALL_MAPPING_FRAGMENTS` (~line 2132) — a seven-tuple today, because
  `power` and `captar` have no mapping half. Four invariants walk it
  (`test_r20_ac4_no_field_belongs_to_two_fragments` ~2154,
  `test_adr0005_no_option_key_appears_in_a_mapping_fragment` ~2175,
  `test_uc12_1b_control_interval_is_only_in_the_core_threshold_fragment_when_requested` ~2182,
  and — the one that matters most here, ~1718 —
  `test_uc12_1b_options_never_presents_a_mapping_or_a_capability_declaration`, which derives the
  set of forbidden options-flow fields from this very roster). Omitting `CAPTAR_MAPPING_SCHEMA`
  fails nothing at all; the invariants simply stop covering the new field. Adding it, conversely,
  buys the options-flow guarantee of D's `async_step_captar` section for free and structurally:
  the new key becomes a field the options flow is *proven* never to render, rather than one a
  hand-written assertion happens to check. It is inserted between `VEHICLE_MAPPING_SCHEMA` and
  `SOLAR_MAPPING_SCHEMA`, keeping table order.
- `tests/test_config_flow_translations.py::CONFIG_STEP_FIELDS` (~line 91) — `cf.STEP_CAPTAR:
  _keys(cf._captar_threshold_schema())` becomes `_keys(cf.CAPTAR_MAPPING_SCHEMA) |
  _keys(cf._captar_threshold_schema())`, matching the `solar`/`deadline` idiom. This one *does*
  fail loudly, but in the opposite direction from the one an implementer expects: adding the label
  without updating the roster trips the **orphaned-label** check, not a missing-label check. Its
  neighbouring anti-vacuity guards (`assert set(CONFIG_STEP_FIELDS) == CONFIG_STEP_IDS`) are keyed
  on step ids and are not implicated — this change adds a field to an existing step, not a step.
  `OPTIONS_STEP_FIELDS`'s `captar` entry stays threshold-only.

### The tests that fail loudly

Five encode the superseded enumeration. All are rewritten, none deleted — the `power` half of what
they protect is now the *only* coverage of the flow-mode half of point 3's rule, so losing it would
leave that rule untested.

| Test | Today | Becomes |
| --- | --- | --- |
| `test_uc12_1a_reconfigure_never_shows_power_or_captar` (~1083) | asserts both absent from the reconfigure walk with CapTar present | `power`-only, renamed; a second test asserts `captar` **is** visited on that same walk |
| `test_adr0027_point3_power_and_captar_rows_are_gated_off_in_reconfigure` (~2401) | both gates evaluate `False` in reconfigure | `power`-only, renamed; plus an assertion that `STEP_CAPTAR`'s gate is now mode-independent — `True` in both modes when CapTar is on, `False` in both when off |
| `test_r20_ac2_reconfigure_traverses_exactly_uc12s_mapping_halves` (~1426, 16 parametrisations decorated at ~1425) | expected sequence never appends `STEP_CAPTAR`; fails 8 of 16 | appends `STEP_CAPTAR` after `STEP_VEHICLE` whenever `captar` is true, before `STEP_SOLAR` |
| `test_uc12_1a_reconfigure_shows_mapping_halves_only` (~1107) | asserts `vehicle` is followed directly by `solar` | inserts the `captar` step, asserting its rendered keys equal `_keys(CAPTAR_MAPPING_SCHEMA)` exactly |
| `test_uc12_captar_step_is_threshold_only_no_ev_soc` (~903) | **install**-side; asserts rendered keys equal the threshold schema's exactly | renamed off "threshold_only"; asserts the keys equal mapping ∪ threshold, and keeps its `CONF_EV_SOC_ENTITY not in` assertion, which is still true and still worth pinning |

Two comments restate the enumeration in prose and move with them: `_run_reconfigure_flow`'s
docstring (`tests/test_config_flow.py` ~262-266), and the section header above the
`power`/`captar` cases (~line 888, "The `power`/`captar` steps: threshold-only, gated off in
reconfigure").

## Mapping to `system-design.md` services

| Piece | Service | Slice |
| --- | --- | --- |
| `PowerKilowattReadAdapter`, factory branch, role key | Resource Access (adapter roles, ADR-0003) | RA2 |
| `resolve_monthly_peak_operand` | Billing-Protection Engine (pure, ADR-0010) | E5 |
| `_read_role` call + merge at the two resolve call sites | Coordinator / control cycle (ADR-0006) | M1 |
| `CAPTAR_MAPPING_SCHEMA`, table gate, step method, strings | Config-flow client | C4 |

No new service, no new call direction, no engine reaching HA: `PowerConverter` is imported by the
adapter (Resource Access, HA-coupled by definition), never by `engines/billing_protection.py`,
which stays pure and HA-import-free per ADR-0010.

## Testing approach (ADR-0009)

- **Plain pytest** — `resolve_monthly_peak_operand` (pure logic, `tests/engines/test_billing_protection.py`);
  the `CONFIG_TABLE` gate-evaluation test (a lambda against a stub flow, as the existing one
  already is); the translation-file content tests (`tests/test_config_flow_translations.py`,
  `tests/test_translations.py`).
- **HA harness** — the adapter (entity states, units, `unavailable`/`unknown`); the factory; the
  coordinator's per-cycle merge; every config-flow traversal, prefill and terminal-split test.

Mandated edge cases, each owed an explicit assertion: role unmapped; mapped but `unavailable`;
mapped but `unknown`; mapped with a non-numeric state; mapped with **no** unit attribute; mapped
with a non-power unit; mapped in W; mapped in kW; external below internal (internal wins); external
above internal (external wins); external above `max_peak_kw` (the existing `min()` still bounds it);
external above internal but below `peak_floor_kw` (the floor still wins — the other half of
`resolution-rules.md` row 2's nesting, and the symmetric case to the `max_peak_kw` one above);
CapTar declared absent with the mapping still stored (the merge is unguarded by design, so D-5 is
pinned rather than left as an invitation to add a `captar_available` guard nothing would object to);
the tracked peak surviving a cycle after the external reading disappears (D-6's no-overwrite half);
mapping cleared on reconfigure; CapTar withdrawn on reconfigure.

## Packaging and migration

No config-entry migration and no `VERSION` bump (ADR-0033's own Consequences). The change adds one
optional data-bucket key; an entry created earlier simply lacks it, which is the same state as a
mapped-then-cleared entry, and the factory's truthiness `.get` handles both identically. No
existing key changes name, type or bucket. No new HA dependency —
`homeassistant.util.unit_conversion` ships with core.

## Deliberate deferrals

- **Recorder backfill** (ADR-0030 Option D) — open, complementary follow-up.
- **A dedicated entity for the merged operand** — see D-6; reversible if a household ever needs to
  see it separately from `effective_peak_limit`.
- **R18 AC5's amendment** — analysis work under its own review protocol, tracked in epic #873.
  Nothing in this plan depends on it landing first; the mapping's CapTar gating is already stated
  by UC12 step 6 and `entity-catalog.md`, both of which are current.
- **Device-class filtering on the entity selector** — the codebase's selectors filter by domain
  only, with no `device_class` precedent anywhere. D-1's unit check catches the mismatch that
  matters at read time and fails safe; adding a selector-level filter is a flow-wide convention
  change, not this slice's to make.
