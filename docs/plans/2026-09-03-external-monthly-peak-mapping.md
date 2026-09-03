# TDD plan: external monthly-peak sensor — role, merge, and the `captar` mapping half (#922)

Derived from `docs/plans/2026-09-03-external-monthly-peak-mapping-design.md`; decisions referenced
as **D-1**…**D-8** are that document's. Branch `development/<issue>` per task, filed against this
plan once it lands. Test boundary per task, per ADR-0009: `engines/` logic is plain pytest,
adapters/factory/coordinator/config-flow are HA harness, translation-file content is plain pytest.

**Why this order.** The chain is built consumer-last, so nothing is ever wired to a value that
cannot exist: keys and adapter (T1) → the pure merge rule (T2) → the coordinator that calls both
(T3) → the flow that populates the key (T4–T6) → the regressions that pin the emergent
save-path behaviour (T7). Every task leaves the full suite green. Three couplings force
adjacent pieces into a single commit and are called out where they bite: the label/roster pair in
T4, and the gate/step pair split across T5–T6.

## T1 — Const keys, the unit-normalising adapter, and the factory branch

Test boundary: **HA harness** (`tests/adapters/test_numeric.py` for the adapter, beside
`NumericReadAdapter`'s own cases; `tests/adapters/test_factory.py` for the factory branch, beside
`ROLE_HOME_DAY_EXTERNAL`'s).

- Failing test — the adapter (parametrised over one state per case): a
  `PowerKilowattReadAdapter` over a `sensor` entity returns `4.09` for state `"4090"` with
  `unit_of_measurement: "W"`, `4.09` for state `"4.09"` with `"kW"` (D-1's equivalence success
  criterion, asserted as one parametrised pair, not two unrelated cases), and `None` for each of:
  entity missing, state `unavailable`, state `unknown`, state `"not a number"`, **unit attribute
  absent**, unit `"°C"`. The last two are the load-bearing ones — D-1 chooses "reads as absent"
  over "assume kW" precisely because a W value misread as kW widens the clamp rather than
  narrowing it.
- Failing test — the factory: an entry whose `data` carries
  `monthly_peak_external_entity` builds `ROLE_MONTHLY_PEAK_EXTERNAL` as a
  `PowerKilowattReadAdapter`; an entry without the key (and one with it set to `""`/`None`) leaves
  the role **absent from `adapters`** — not present-and-returning-`None`, since ADR-0030's
  optional-role contract is factory-level absence.
- Failing test — `ROLE_MONTHLY_PEAK_EXTERNAL not in ROLES_ADAPTER_READINGS_EXCLUDED` (D-4: the
  role is read by `_run_cycle`, so ADR-0021's diagnostic sensor must pick it up by the existing
  default, and that must be pinned rather than left to inference).
- Add to `const.py`: `CONF_MONTHLY_PEAK_EXTERNAL_ENTITY = "monthly_peak_external_entity"` in the
  DATA-key block (**not** in `OPTION_KEYS`) and `ROLE_MONTHLY_PEAK_EXTERNAL = "monthly_peak_external"`
  in the roles block — the id `entity-catalog.md` already uses.
- Add `PowerKilowattReadAdapter(_ReadOnlyAdapter)` to `adapters/numeric.py`, converting via
  `homeassistant.util.unit_conversion.PowerConverter` and guarding on
  `PowerConverter.VALID_UNITS`. The conversion target is `UnitOfPower.KILO_WATT` from
  `homeassistant.const`, never a `"kW"` literal (no-magic-strings).
- Add the factory branch in `adapters/factory.py`, using the truthiness-`.get` idiom
  `ROLE_HOME_DAY_EXTERNAL`/`ROLE_LOW_TARIFF` already use.
- Green, commit: `feat: add the external monthly-peak adapter role (ADR-0030, #922)`.

## T2 — The merge rule as a pure function

Test boundary: **plain pytest** (`tests/engines/test_billing_protection.py`).

- Failing test: `resolve_monthly_peak_operand(2.0, None) == 2.0` (R3 AC9 — unmapped rests on the
  internal value alone); `(2.0, 4.09) == 4.09` (external above internal wins, R3 AC8);
  `(5.0, 4.09) == 5.0` (internal above external wins — the merge raises, never lowers);
  `(2.0, 0.0) == 2.0` (a genuine `0.0` reading is a value, not a stand-in for "absent" — the
  distinction `None` carries, and the one case where a truthiness test instead of an `is None`
  test would be wrong).
- Failing test — **both ends of the existing nesting**, since `resolve_effective_peak_limit` is
  `min(max(operand, peak_floor_kw), max_peak_kw)` and the merge only changes the operand: an
  external reading above `max_peak_kw`, run through `resolve_monthly_peak_operand` and then
  `resolve_effective_peak_limit`, still resolves to `max_peak_kw`; and an external reading that
  beats the internal value but still sits below `peak_floor_kw` resolves to the floor. Both halves
  of `resolution-rules.md` row 2's nesting stay intact — the merge raises the operand, it does not
  escape the clamp at either end.
- Add `resolve_monthly_peak_operand(internal_kw: float, external_kw: float | None) -> float` to
  `engines/billing_protection.py` (D-2). Do **not** change `resolve_effective_peak_limit`'s
  signature, docstring or existing tests. The module keeps its no-HA-imports property (ADR-0010),
  and that is already enforced rather than merely intended: `tests/test_engine_purity.py` covers
  the new function for free the moment it lands in this module.
- Green, commit: `feat: add the monthly-peak operand merge rule (ADR-0032, #922)`.

## T3 — The coordinator reads the role and merges once per cycle

Test boundary: **HA harness** (`tests/test_coordinator.py`).

- Failing test: with the role mapped and reporting a value **above** the tracked peak, one cycle's
  `CycleResult.effective_peak_limit_kw` resolves from the external reading; with it mapped
  **below**, from the tracked one; with it unmapped, exactly as today (the pinned no-op case).
- Failing test — **two cycles, not one**: `CycleResult.monthly_peak_kw` still carries the
  **internally-tracked** value even when the external reading is higher (D-6 — the sensor's
  documented meaning is unchanged), and it is *still* the tracked value on a second cycle from
  which the external reading has gone. The second cycle is the load-bearing half.
  `resolution-rules.md` row 2's note claims two things — the merge is recomputed fresh each cycle,
  **and** it "never overwrites the internally-tracked monthly peak demand, so a live spike this
  integration observes between external-sensor refreshes is not discarded". A single-cycle
  assertion only reaches the first. Because `monthly_peak_kw` is produced by
  `self._peak_demand.update(...)` *before* the merge, a refactor that wrote the merged value back
  into the tracker — `seed_monthly_peak` / `PeakDemandState.seed()` is a real, reachable boundary
  (`coordinator.py` ~1001-1007) — would pass a one-cycle test and only surface on the next cycle,
  by which time the contaminated value is indistinguishable from a genuine spike.
- Failing test: the mapped role's raw reading appears in `CycleResult.adapter_readings` under
  `monthly_peak_external` (D-4, via `_read_role`'s own cache write).
- Failing test — **D-5, pinned rather than assumed**: with the role mapped and reading high but
  `captar_available` **off**, the merge still runs unguarded and the cycle behaves exactly as the
  CapTar-absent path does today (R3's clamp does not apply there, so the merged operand is inert).
  Without this, nothing objects to a later contributor adding a `captar_available` guard to the
  merge — a second, redundant expression of what the buckets already enforce, and the one place
  D-5's reasoning could be silently undone.
- Failing test — both call sites, not just the final one: on a cycle that takes the `ev_soc`-fault
  early return (the path fed by the provisional `resolve_effective_peak_limit(urgent=False)` call
  at ~line 422), the resolved limit also reflects the external reading. This is the specific
  failure D-3 exists to prevent: updating the final call site alone leaves the provisional one on
  the unmerged value, and no existing test would notice.
- In `coordinator.py`, directly beneath the single `monthly_peak_kw = self._peak_demand.update(...)`
  assignment (~line 418): `external_peak_kw = await self._read_role(ROLE_MONTHLY_PEAK_EXTERNAL)`,
  then `peak_operand_kw = resolve_monthly_peak_operand(monthly_peak_kw, external_peak_kw)`. Pass
  `peak_operand_kw` at **both** `resolve_effective_peak_limit` call sites (~422, ~621). No CapTar
  gate on the merge (D-5).
- Green, commit: `feat: merge the external monthly-peak reading into the peak operand (ADR-0032, #922)`.

The feature is now fully functional for any entry whose data carries the key. T4 onward is the only
way a household can put it there.

## T4 — The mapping fragment, the install render, and its labels

Test boundary: **HA harness** for the flow; **plain pytest** for the translation files.

The label roster and the string files are two-way coupled and must land in one commit: adding
`monthly_peak_external_entity` to `strings.json` without updating `CONFIG_STEP_FIELDS` trips the
orphaned-label check, and updating the roster without the label trips the missing-label check
(`tests/test_config_flow_translations.py`, D's "two fixtures that fail quietly").

- Failing test: `CAPTAR_MAPPING_SCHEMA` exists as a module-level constant whose keys are exactly
  `{CONF_MONTHLY_PEAK_EXTERNAL_ENTITY}`, and the key is `vol.Optional` (UC12 6a — unmapped by
  default). Leave `test_flat_flow_schema_surface_is_deleted` (~2033) **untouched**: it pins
  `_captar_mapping_schema`'s absence, which stays true and must not be weakened.
- **Rewrite** `test_uc12_captar_step_is_threshold_only_no_ev_soc` (~903) — it goes red on this
  task's implementation, since it asserts the install step's rendered keys equal the threshold
  schema's exactly. Rename it off "threshold_only"; assert the keys equal
  `_keys(CAPTAR_MAPPING_SCHEMA) | _keys(_captar_threshold_schema())`, and keep its
  `CONF_EV_SOC_ENTITY not in` assertion unchanged — still true, still worth pinning.
- Add `CAPTAR_MAPPING_SCHEMA` to `config_flow.py` (D's "schema fragment" section) and extend it
  with the threshold half in `async_step_captar` for the install render.
- Rewrite `_captar_threshold_schema`'s own docstring (`config_flow.py` ~454-456). It reads "UC12
  (topic-step) step 6 threshold half -- **CapTar has no mapping half at all** (design
  field-to-step table)", and this task is the moment that becomes false. It is the fourth stale
  docstring, and the one ADR-0033's "a floor, not a total" caveat catches: unlike the three T5
  rewrites, it names `captar` **alone**, so T8's `power`-paired-with-`captar` sweep would miss it.
  It should say the step now carries a mapping half of its own, while keeping its still-true point
  that `ev_soc_entity` lives on the always-shown `vehicle` step (R20 AC4's once-only rule).
- Add `CAPTAR_MAPPING_SCHEMA` to `tests/test_config_flow.py::_ALL_MAPPING_FRAGMENTS` (~2132),
  between `VEHICLE_MAPPING_SCHEMA` and `SOLAR_MAPPING_SCHEMA` to keep table order. This is the
  silent under-coverage ADR-0033 warns about: omitting it fails nothing, it just stops four
  invariants from covering the new field — including
  `test_uc12_1b_options_never_presents_a_mapping_or_a_capability_declaration` (~1718), which
  derives its forbidden-field set from this roster and so extends the options-flow guarantee to
  the new key automatically, the moment the roster grows.
- Update `tests/test_config_flow_translations.py::CONFIG_STEP_FIELDS`'s `captar` entry to
  `_keys(cf.CAPTAR_MAPPING_SCHEMA) | _keys(cf._captar_threshold_schema())`. Leave
  `OPTIONS_STEP_FIELDS`'s `captar` entry threshold-only.
- Update `strings.json`, `translations/en.json`, `translations/nl.json`: reword
  `config.step.captar.description` to cover both contexts (D's Translations section), and add the
  new field's `data` label and `data_description`. No `"required if"`/`"required when"` in the
  label. `config.step.captar.title` and the whole `options.step.captar` block are unchanged.
- Green, commit: `feat: present the external monthly-peak mapping on the captar step (ADR-0033, #922)`.

## T5 — `async_step_captar` gains mode branching and prefill

Test boundary: **HA harness** (`tests/test_config_flow.py`).

Landed **before** the gate flip on purpose: while `STEP_CAPTAR` is still gated off in reconfigure
the new branch is unreachable, `_maybe_prefill` is a documented no-op outside reconfigure mode, and
the install render is byte-identical — so this commit changes no observable behaviour and no
existing test, which is what lets T6 be a pure gate-and-tests commit.

- Failing test: the install flow's `captar` step still renders mapping ∪ threshold keys and still
  stores both halves into the right buckets on finish — a pinned no-op, since this task's whole
  claim is that install is unaffected.
- Rewrite `async_step_captar` to the `async_step_solar` idiom (D's `async_step_captar` section):
  `CAPTAR_MAPPING_SCHEMA`, extended with `_captar_threshold_schema()` only when
  `self._mode is not FlowMode.RECONFIGURE`, rendered through `self._maybe_prefill(schema)`.
- Rewrite its docstring — it currently asserts the step needs "neither `self._mode` branching nor
  `_maybe_prefill` in its own body".
- Rewrite the two docstrings that go stale without their logic changing, both named by ADR-0033:
  `_async_finish`'s ("neither `power` nor `captar` is reachable in this mode") — the terminal split
  is bucket-driven, so state why the code stays correct: `captar` is now reachable in reconfigure
  but contributes no `OPTION_KEYS` member, because its threshold half is not rendered there — and
  `async_step_reconfigure`'s, which restates the two-row skip directly.
- Green, commit: `refactor: give async_step_captar mode branching and prefill (ADR-0033, #922)`.

## T6 — The gate flip, and the five tests that spell out the superseded enumeration

Test boundary: **plain pytest** for the gate-evaluation test (a lambda against a stub flow, as the
existing one already is); **HA harness** for every traversal test.

- **Rewrite** `test_adr0027_point3_power_and_captar_rows_are_gated_off_in_reconfigure` (~2401) into
  a `power`-only test under a name that no longer claims `captar`. Keep the `power` assertion
  exactly as strong: it is now the *only* coverage of the flow-mode half of ADR-0027 point 3's
  rule, which this change does not weaken. Add a sibling asserting `STEP_CAPTAR`'s gate is
  mode-**independent** — `True` in install and reconfigure alike when `captar_available` is set,
  `False` in both when it is not.
- **Rewrite** `test_uc12_1a_reconfigure_never_shows_power_or_captar` (~1083) into a `power`-only
  test, renamed; add a companion asserting `captar` **is** visited on the same reconfigure walk
  when CapTar is present.
- **Rewrite** `test_r20_ac2_reconfigure_traverses_exactly_uc12s_mapping_halves` (~1426): the
  expected sequence appends `STEP_CAPTAR` after `STEP_VEHICLE` whenever the parametrisation's
  `captar` flag is true. This is the substantive one — it discharges the reconfigure third of
  ADR-0027's "every capability combination … must traverse exactly the steps UC12 prescribes, in
  order", and it currently fails 8 of its 16 parametrisations.
- **Rewrite** `test_uc12_1a_reconfigure_shows_mapping_halves_only` (~1107): insert the `captar`
  step between `vehicle` and `solar`, asserting its rendered keys equal
  `_keys(CAPTAR_MAPPING_SCHEMA)` **exactly** — the mapping half alone, no threshold key leaking in.
- Failing test: `OPTIONS_TABLE`'s `captar` step still renders `_keys(_captar_threshold_schema())`
  exactly, and `CONF_MONTHLY_PEAK_EXTERNAL_ENTITY` never reaches `entry.options` after an options
  run. ADR-0033 names the options flow as the one place this decision could plausibly be
  over-applied, so it is asserted rather than inferred. The *rendering* half is already covered
  structurally once T4 grows the roster (above) — this bullet adds the stored-bucket half, which
  the roster invariant does not reach.
- Change `CONFIG_TABLE`'s `STEP_CAPTAR` gate to
  `lambda flow: bool(flow._answers.get(CONF_CAPTAR_AVAILABLE))`. `STEP_POWER`'s row is untouched.
- Reword the comment block above `CONFIG_TABLE` (it currently reads "`power`/`captar` have no
  mapping half at all, so both are gated off entirely in reconfigure mode" and cites point 3
  inline): name `power` alone, say `captar` is now a plain capability gate because it has acquired
  a mapping half, and cite ADR-0033 beside ADR-0027. ADR-0033 makes this pointer part of the work,
  not a tidy — it is one of only two paths by which a reader reaches point 3 without seeing the
  narrowing.
- Reword the two prose restatements that move with the tests: `_run_reconfigure_flow`'s docstring
  (`tests/test_config_flow.py` ~262-266, "`power`/`captar` are gated off entirely in this mode
  (UC12 1a)"), and the section header above the `power`/`captar` cases (~888, "The `power`/`captar`
  steps: threshold-only, gated off in reconfigure").
- Green, commit: `feat: show the captar step in the reconfigure flow (ADR-0033, #922)`.

## T7 — Prefill, clear, and withdrawal: the three save-path regressions

Test boundary: **HA harness** (`tests/test_config_flow.py`). Test-only — D-8's two behaviours are
emergent properties of `_async_finish`'s wholesale data-bucket replacement, so this task should
need no production change. If any assertion here needs one, that is a genuine finding, not a
licence to weaken the test.

- Failing test — **the silent-drop class** (D-7, the bug ADR-0033 names): reconfigure an entry that
  already has the mapping stored; assert the `captar` form's rendered `suggested_value` for
  `CONF_MONTHLY_PEAK_EXTERNAL_ENTITY` is the stored entity id; **resubmit the prefilled form
  unchanged**; assert `entry.data[CONF_MONTHLY_PEAK_EXTERNAL_ENTITY]` still holds it. Model it on
  `test_reconfigure_grid_step_prefills_low_tariff_states` (~395), not on
  `test_reconfigure_form_prefills_existing_mappings` (~1204) — rendering a suggestion is not the
  property that matters; surviving the save is.
- Failing test — **clearing** (UC12 6a: "leaving the mapping unset or clearing it is equivalent
  either way"): reconfigure the same entry, submit the `captar` step with the field omitted, and
  assert the key is absent from `entry.data` afterwards and the role is absent from the rebuilt
  adapter set.
- Failing test — **withdrawal** (`entity-catalog.md`'s Captar-dependent-rows note): reconfigure an
  entry that has the mapping stored, declare `captar_available` **off** on the `core` step, finish,
  and assert (a) `CONF_MONTHLY_PEAK_EXTERNAL_ENTITY` is gone from `entry.data`, and (b) the six
  options-bucket CapTar values — the four thresholds, `power_respect_peak`, `captar_cooldown_min` —
  are **unchanged** in `entry.options`, lying dormant. The asymmetry is the point of the test;
  asserting only half of it would pass while the note's claim was broken.
- Green, commit: `test: pin the captar mapping's prefill, clear and withdrawal behaviour (#922)`.

## T8 — Integration checkpoint

- Full suite green: `pytest tests/` (HA harness) and the plain-pytest engine tests.
- `ruff check .` and `ruff format --check .` clean.
- Manual read-through of the three translation files' `captar` blocks in both an install and a
  reconfigure framing — the one property no test can assert is whether the reworded description
  actually reads correctly above a single-field form.
- End-to-end: install with CapTar on and the mapping set, confirm
  `sensor.smart_charging_adapter_readings` carries `monthly_peak_external` and
  `sensor.smart_charging_effective_peak_limit` reflects the merged operand; reconfigure, confirm
  the `captar` step appears showing that field alone, prefilled.
- Grep for stale prose one last time, on **two** patterns, because the two failure shapes differ:
  no comment or docstring under `custom_components/` or `tests/` should still pair `power` with
  `captar` as the threshold-only steps, **and** none should still say `captar` has "no mapping
  half" / is "threshold-only" on its own. The second pattern is the one that catches a `captar`-only
  restatement like `_captar_threshold_schema`'s; ADR-0033 warns the enumerated count is a floor,
  not a total, so this sweep is the backstop rather than a formality.
- This closes #922's build tasks and, with them, epic #873.

## Follow-up (not this plan)

- **R18 AC5's amendment** — its list of CapTar-gated fields is still a closed five-item
  enumeration that omits this mapping. Analysis work under its own review protocol; nothing here
  depends on it.
- **Recorder / long-term-statistics backfill** — ADR-0030 Option D, left open there as
  complementary rather than rejected.
- **A dedicated entity for the merged operand** — D-6 decides against it for now, on the grounds
  that `effective_peak_limit` and the adapter-readings sensor already make it observable.
