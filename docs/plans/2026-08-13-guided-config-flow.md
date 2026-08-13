# C4 — Guided config flow / options flow: Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan
> task-by-task.

**Goal:** Restructure `custom_components/smart_charging/config_flow.py` from three flat single-screen
forms into the capability-gated step sequence
[UC12](../analysis/use-cases/UC12-configure-installation-through-guided-flow.md) and
[R20](../analysis/requirements.md#r20--guided-installation-configuration) settled, using the
table-driven linear `async_step_*` mechanism
[ADR-0025](../adl/0025-config-flow-branching-structure.md) chose (Option C). Closes issue #677 of
epic #656; slice **C4** of [`docs/design/project-plan.md`](../design/project-plan.md).

**Architecture:** one ordered, gated step table per flow plus one shared dispatcher; one
`async_step_*` method per UC12 step; per-step schema fragments replacing `MAPPING_SCHEMA` /
`_threshold_schema()` / `USER_SCHEMA`; a per-run accumulator dict on the flow instance consumed once
at the terminal step, where the existing `_split_data` (unchanged) and an **intersection-based**
`OPTION_KEYS` consumption perform the ADR-0005 bucket split. Full design:
[`2026-08-13-guided-config-flow-design.md`](2026-08-13-guided-config-flow-design.md) — read it first;
this plan does not restate its tables.

**Scope guard — this plan touches only:**
`custom_components/smart_charging/config_flow.py`, `custom_components/smart_charging/const.py`
(new constants only, per design D-1/D-5), `custom_components/smart_charging/strings.json`,
`custom_components/smart_charging/translations/{en,nl}.json`,
`tests/test_config_flow.py`, `tests/test_config_flow_translations.py`.
No other module changes. No behaviour is added to any consumer of the keys this flow writes — wiring
`deadline_available` and `reminder_lead_h` to runtime behaviour is explicitly out of this slice (design,
Deferrals).

**Tech Stack:** Python ≥3.12, Home Assistant, `pytest-homeassistant-custom-component` (HA harness —
the config flow is HA-coupled, so **every** task here is HA-harness per ADR-0009 and project-plan
C4's own "Testable on its own" line), `ruff`.

**Model:** Per CLAUDE.md, this is development work — execute on **Sonnet**.

**Two open questions from the design doc must be answered before the task that depends on them
(T3):** OQ-1 (present `prompt_timeout_h` or defer it) and OQ-2 (step 1's solar default). Both are
one-task changes; T1 and T2 can proceed without either answer. Do not guess — ask.

---

## Conventions used throughout

- **Named constants, no magic strings** (CLAUDE.md) — step ids are `STEP_*` constants in `const.py`;
  field keys are the existing `CONF_*`; error codes the existing `ERROR_*`. Never a bare `"solar"`
  or `"ev_soc_entity"` literal in `config_flow.py` or the tests.
- **Cite, don't restate.** Every test docstring names its criterion (`R20 AC4`, `UC12 step 3`,
  `ADR-0025 point 2`). If a test and UC12 disagree, UC12 wins and the task stops.
- **`git commit --author="Claude <noreply@anthropic.com>"`** with the trailer
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Re-check `git branch --show-current` before every commit (shared checkout).
- **After every task, run the full suite** (`pytest tests/ -q`). Files outside the scope guard must
  keep passing unchanged; `tests/test_init.py`, `tests/test_coordinator*.py` and the end-to-end tests
  build their entries from `tests/helpers.py`'s `entry_data_base`/`entry_options_base`, not through
  the flow, so they should be unaffected — any failure there is a regression to fix before
  committing.
- `ruff check .` and `ruff format --check .` both clean before each commit.
- **Genuine red before green** — each task states the failure its first test produces.
- **The flow stays runnable at every commit.** T1–T2 add structure alongside the flat flow; T3 is the
  first task that replaces a user-visible path, and from T3 onward every commit leaves all three
  flows working end to end.

---

## Task T1: Per-step schema fragments

**Realizes:** UC12 steps 1, 3–8; R20 AC1, AC3, AC5. **ADR honored:** ADR-0025 (Consequences —
`MAPPING_SCHEMA`/`_threshold_schema()` broken into per-step fragments), ADR-0005 (no key changes
bucket). **Test boundary:** HA harness module `tests/test_config_flow.py`; these particular
assertions need no `hass` fixture (design, Testing approach).

**Files:** edit `custom_components/smart_charging/const.py`,
`custom_components/smart_charging/config_flow.py`, `tests/test_config_flow.py`.

**Step 1 — failing tests.** One test per fragment asserting its **exact** key set against the design
doc's fragment table (which is itself UC12's step text). Use
`set(schema.schema)`-style comparison via the voluptuous marker's `.schema` attribute so a missing
*or* extra key fails:

```python
def _keys(schema) -> set[str]:
    return {str(marker) for marker in schema.schema}


def test_uc12_step1_core_fragment_has_exactly_the_core_mappings_and_decisions():
    """UC12 step 1 / R20 AC1: four core mappings + two state lists + four enablement decisions --
    and nothing else (grid voltage moves to the ungated-mappings step, UC12 step 7)."""
```

Cover: `test_uc12_step3_solar_fragments_*` (mapping half with and without `include_ev_soc`; threshold
half), `test_uc12_step4_captar_fragments_*`, `test_uc12_step5_deadline_fragments_*`,
`test_uc12_step6_vehicle_limit_fragment_*`, `test_uc12_step7_ungated_mapping_fragment_*`,
`test_uc12_step8_ungated_threshold_fragment_*` (with `include_interval` False **and** True — UC12 1b).
Plus two whole-surface tests that make an omission impossible to miss:

```python
def test_every_option_key_appears_in_exactly_one_threshold_fragment():
    """ADR-0005: every OPTION_KEYS member has exactly one step that presents it -- no key
    orphaned by the split, none asked twice."""


def test_no_field_appears_in_two_fragments():
    """UC12 postcondition 3 generalised: a field belongs to exactly one step."""
```

**Red:** `ImportError` / `AttributeError` — no fragment exists.

**Step 2 — implement.** In `const.py`, add per design D-1: `CONF_DEADLINE_AVAILABLE`,
`DEFAULT_DEADLINE_AVAILABLE`, `CONF_REMINDER_LEAD_H`, `DEFAULT_REMINDER_LEAD_H`,
`CONF_VEHICLE_LIMIT_MAPPED`, and per D-5 the `STEP_*` step-id constants. `CONF_REMINDER_LEAD_H` is
appended to `OPTION_KEYS` in `config_flow.py`. (`CONF_PROMPT_TIMEOUT_H` waits on OQ-1 — T3.)

In `config_flow.py`, split `MAPPING_SCHEMA` and `_threshold_schema()` into the fragments named in the
design doc's fragment table. `MAPPING_SCHEMA`, `_threshold_schema()` and `USER_SCHEMA` stay in place
for now (the flat flow still uses them) — they are deleted in T13.

**Do not** move any field between steps beyond what the design table says; it is UC12's placement,
not a judgement call.

**Verify:** new tests green; full suite green; ruff clean. Commit.

---

## Task T2: The step table and the shared dispatcher

**Realizes:** UC12 step 2 (fixed order, complete traversal); R20 AC2, AC9. **ADR honored:** ADR-0025
(Decision — Option C; the test obligation on the table). **Test boundary:** HA harness,
`tests/test_config_flow.py`.

**Files:** edit `custom_components/smart_charging/config_flow.py`, `tests/test_config_flow.py`.

**Step 1 — failing tests.** These are the named discharge of Option C's stated Con (a step method
absent from its table is silently unreachable):

```python
def test_adr0025_every_config_table_step_has_a_step_method():
    """ADR-0025 test obligation: a table row with no async_step_<id> strands the flow."""


def test_adr0025_every_config_step_method_is_in_the_table():
    """The converse: a step method absent from the table is unreachable and nothing raises."""
```

(the same pair for `SmartChargingOptionsFlow`, excluding the framework entry points
`async_step_user` / `async_step_reconfigure` / `async_step_init`), plus:

```python
def test_uc12_step2_config_table_is_in_uc12s_fixed_order():
    """UC12 step 2 / R20 AC2: solar -> captar -> deadline -> vehicle limit -> ungated mappings
    -> ungated thresholds. The order is the table's, and it is asserted literally."""
```

and a dispatcher unit test driving `_async_advance` over a **synthetic** two-row table with a failing
gate, asserting it lands on the next passing row and calls `_async_finish` when exhausted.

**Red:** `ImportError` — no `FlowStep`, no table, no `_TableWalkMixin`.

**Step 2 — implement.** Add `FlowMode`, `FlowStep`, `_TableWalkMixin` (`_answers`, `_mode`,
`_async_advance`, abstract `_async_finish`) and the two tables exactly as the design doc specifies.
`gate` takes the flow handler so one signature serves both tables. No handler class uses them yet.

**Verify + commit.**

---

## Task T3: Install happy path — `core` → `mappings` → `thresholds` → create entry

**Realizes:** UC12 steps 1, 7, 8, 9; R20 AC1, AC5. **ADR honored:** ADR-0025 points 2 and 4
(accumulator; `async_step_user` delegates into the shared step-1 implementation), ADR-0005 (bucket
split unchanged). **Test boundary:** HA harness, `tests/test_config_flow.py`.

**Blocked on OQ-1 and OQ-2** — both land in this task's fragments/schema. Get the answers first.

**Files:** edit `custom_components/smart_charging/config_flow.py`, `tests/test_config_flow.py`
(and `const.py` + `OPTION_KEYS` if OQ-1 resolves to (a)).

**Step 1 — failing tests.** Replace `_run_user_flow`/`_create_entry` with a step-walking driver:

```python
async def _run_install_flow(hass, *, capabilities=None, per_step=None):
    """Drive the install flow step by step, submitting per_step[<step id>] at each form.
    Returns the final flow result. Asserts each intermediate result is a FORM."""
```

Then:

```python
async def test_r20_ac1_first_step_presents_only_core_mappings_and_decisions(hass):
    """R20 AC1 / UC12 step 1: the first form's schema is exactly CORE_MAPPING_SCHEMA --
    in particular it no longer carries a single threshold (the flat USER_SCHEMA did)."""


async def test_adr0005_all_capabilities_off_install_splits_buckets(hass):
    """UC12 step 9 / ADR-0005: solar/captar/deadline all declared absent and no vehicle limit
    elected -> core, mappings, thresholds only; DATA carries the mappings, the capability flags
    and the derived status_translation; OPTIONS carries only the ungated thresholds plus the
    defaulted control interval."""


async def test_adr0025_option_keys_consumption_is_intersection_based(hass):
    """ADR-0025 Consequences: a skipped step leaves its OPTION_KEYS members absent from the
    accumulator; the terminal step must intersect, not index. Direct indexing raises KeyError
    here -- this test is the one that fails against the flat comprehension."""
```

**Red:** the flow stops at the flat single form; the multi-step driver's second `async_configure`
returns `CREATE_ENTRY` instead of a `FORM`.

**Step 2 — implement.** `async_step_user` sets `self._mode = FlowMode.INSTALL`, `self._answers = {}`
and delegates to `async_step_core` (ADR-0025 point 4). `async_step_core`, `async_step_mappings` and
`async_step_thresholds` each render their fragment, merge validated input into `self._answers`, and
end with `await self._async_advance(after=<own step id>)`. `_async_finish` pops the transient
`CONF_VEHICLE_LIMIT_MAPPED` (design D-2), then:

```python
data = _split_data(self._answers)                                    # unchanged (ADR-0025)
options = {k: self._answers[k] for k in OPTION_KEYS if k in self._answers}
options[CONF_CONTROL_INTERVAL_S] = DEFAULT_CONTROL_INTERVAL_S
```

Apply OQ-1's answer (add or omit `CONF_PROMPT_TIMEOUT_H` on the ungated threshold fragment and in
`OPTION_KEYS`) and OQ-2's (step 1's solar decision default). If OQ-2 resolves as recommended, add the
comment naming the divergence between the *form* default (`True`, R20 AC1) and
`DEFAULT_SOLAR_AVAILABLE` (`False`, the absent-key read fallback), so the next reader sees it.

The three gated steps do not exist yet, so their table rows must not be reachable — gate them on the
capability flags, which this task already collects on step 1; with all three answered absent, the
walk skips them. Do **not** stub the step methods: T2's reachability test would then pass vacuously.
Add the three rows in T4–T6 together with their methods instead, and keep T2's table assertions
scoped to the rows that exist.

`async_step_reconfigure` and `async_step_init` still run the flat path — replaced in T9/T10.

**Verify + commit.**

---

## Task T4: The solar step

**Realizes:** UC12 step 3, 2a; R20 AC2, AC3, AC6. **ADR honored:** ADR-0025 point 1 (step-local
validation). **Test boundary:** HA harness, `tests/test_config_flow.py`.

**Files:** edit `config_flow.py`, `tests/test_config_flow.py`.

**Step 1 — failing tests.**

```python
async def test_uc12_step3_solar_declared_shows_solar_step_with_its_own_thresholds(hass)
async def test_uc12_2a_solar_absent_skips_the_solar_step(hass)
async def test_r20_ac3_solar_absent_install_stores_no_solar_threshold_keys(hass)
async def test_r20_ac6_missing_ev_soc_is_reported_on_the_solar_step(hass):
    """R20 AC6 / UC12 exception flow 2 / ADR-0025 point 1: the error is field-local
    (errors == {CONF_EV_SOC_ENTITY: ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE}), the same step is
    re-shown, and the flow has NOT advanced -- replacing the end-of-form _mapping_errors case."""
async def test_r20_ac6_missing_solar_forecast_is_reported_on_the_solar_step(hass)
```

Assert non-advancement explicitly: the returned result is a `FORM` whose `step_id` is still the solar
step.

**Step 2 — implement.** `async_step_solar` renders
`_solar_mapping_schema(include_ev_soc=CONF_EV_SOC_ENTITY not in self._answers)` extended with
`_solar_threshold_schema()` when `self._mode is not FlowMode.RECONFIGURE`; runs the step-local
`_ev_soc_missing_error` / `_solar_forecast_missing_error` (design D-3), re-showing the same step with
the field-local error on failure; merges and advances on success. Add its table row.

**Verify + commit.**

---

## Task T5: The CapTar step, and the once-only EV state-of-charge mapping

**Realizes:** UC12 step 4, postcondition 3; R20 AC4. **ADR honored:** ADR-0025 (Consequences —
`_ev_soc_missing_error` "needs particular care"). **Test boundary:** HA harness.

**Files:** edit `config_flow.py`, `tests/test_config_flow.py`.

**Step 1 — failing tests.** This is R20 AC4's whole truth table:

```python
async def test_r20_ac4_ev_soc_asked_on_solar_step_only_when_both_capabilities_declared(hass):
    """R20 AC4 / UC12 postcondition 3: solar and CapTar both present -> the EV state-of-charge
    mapping appears on the solar step and NOT again on the CapTar step."""


async def test_r20_ac4_ev_soc_asked_on_captar_step_when_only_captar_declared(hass)
async def test_r20_ac4_ev_soc_never_asked_when_neither_capability_declared(hass)
async def test_r20_ac6_missing_ev_soc_is_reported_on_the_captar_step(hass):
    """... with ERROR_REQUIRED_WHEN_CAPTAR_AVAILABLE, not the solar code."""
async def test_uc12_step4_captar_step_presents_the_captar_cooldown(hass)
async def test_uc12_2a_captar_absent_skips_the_captar_step(hass)
```

**Step 2 — implement.** `async_step_captar`, mirroring T4 with `include_ev_soc=CONF_EV_SOC_ENTITY not
in self._answers` — which is already false when the solar step ran, because that step merged the
mapping into the accumulator. Add its table row **after** the solar row (UC12's fixed order is what
makes this expression correct).

**Verify + commit.**

---

## Task T6: The deadline step

**Realizes:** UC12 step 5, 2a; R18 AC7 (the departure-time inputs and the reminder lead time are
neither offered nor required when the deadline capability is absent); R20 AC3. **Test boundary:** HA
harness.

**Files:** edit `config_flow.py`, `tests/test_config_flow.py`.

**Step 1 — failing tests.**

```python
async def test_uc12_step5_deadline_step_presents_departure_mapping_and_reminder_lead(hass)
async def test_r18_ac7_deadline_absent_offers_no_departure_or_reminder_field(hass):
    """R18 AC7 / R20 AC3: the deadline step is skipped entirely, and the stored entry carries
    neither departure_external_entity nor reminder_lead_h."""
async def test_uc12_step5_departure_mapping_is_optional(hass):
    """UC12 step 5 calls it 'the optional external departure-time mapping' -- submitting the
    step without it advances."""
```

**Step 2 — implement.** `async_step_deadline` + its table row after the CapTar row. No step-local
guard: UC12 marks neither field required.

**Verify + commit.**

---

## Task T7: The vehicle-charge-limit step

**Realizes:** UC12 step 6, 2a; R20 AC3, AC6. **ADR honored:** ADR-0025 point 1. **Test boundary:** HA
harness.

**Files:** edit `config_flow.py`, `tests/test_config_flow.py`.

**Step 1 — failing tests.**

```python
async def test_uc12_step6_elected_vehicle_limit_asks_the_limit_and_car_home_together(hass):
    """UC12 step 6: 'the two are always asked together'."""
async def test_uc12_2a_declined_vehicle_limit_asks_neither_field(hass)
async def test_r20_ac6_missing_car_home_is_reported_on_the_vehicle_limit_step(hass):
    """errors == {CONF_CAR_HOME_ENTITY: ERROR_REQUIRED_WHEN_VEHICLE_LIMIT_MAPPED}, same step
    re-shown, flow not advanced."""
async def test_d2_vehicle_limit_election_is_not_persisted(hass):
    """Design D-2: the election is a transient form key -- entity-catalog.md has no row for it,
    so CONF_VEHICLE_LIMIT_MAPPED must not appear in the stored data bucket."""
```

**Step 2 — implement.** `async_step_vehicle_limit` + its table row after the deadline row, gated on
the transient election. `vehicle_charge_limit_entity` is `vol.Required`; `car_home_entity` is guarded
by the step-local `_car_home_missing_error` (design D-3). The pop of the transient key in
`_async_finish` already exists from T3 — this task is where it starts mattering.

**Verify + commit.**

---

## Task T8: Traversal matrix — every enablement combination, in UC12's order

**Realizes:** UC12 step 2 / 2a; R20 AC2, AC3. **ADR honored:** ADR-0025 (Consequences — "every
enablement combination traversing exactly the steps UC12 prescribes in the prescribed order").
**Test boundary:** HA harness.

**Files:** edit `tests/test_config_flow.py` only. If a combination fails, the fix belongs to the step
task that owns it — this task adds no production code.

**Step 1 — failing test.** One parameterised test over all **16** combinations of
(solar, captar, deadline, vehicle-limit elected), each with its expected step-id sequence computed
from UC12's rules, driving the flow and recording the `step_id` of every form shown:

```python
@pytest.mark.parametrize("solar,captar,deadline,vehicle", list(itertools.product([True, False], repeat=4)))
async def test_uc12_step2_traversal_visits_exactly_the_prescribed_steps_in_order(
    hass, solar, captar, deadline, vehicle
):
    """UC12 step 2 + 2a / R20 AC2 + AC3: the visited step ids are exactly
    [core] + [solar if solar] + [captar if captar] + [deadline if deadline]
    + [vehicle_limit if vehicle] + [mappings, thresholds] -- order included."""
```

Assert the sequence **equals** the expectation (not "contains"), so both a skipped and an extra step
fail. Also assert, in every combination, that the ungated grid-safety thresholds are present in the
resulting options bucket (design, Safety caveat — an ungated step can never be gated away).

**Verify + commit.**

---

## Task T9: The reconfigure flow

**Realizes:** UC12 1a; R20 AC7. **ADR honored:** ADR-0025 points 2 (prefill is rendering-only, the
accumulator is never seeded) and 4 (`async_step_reconfigure` delegates into the shared step 1),
ADR-0008 (reload on save), ADR-0005 (data bucket only). **Test boundary:** HA harness.

**Files:** edit `config_flow.py`, `tests/test_config_flow.py`.

**Step 1 — failing tests.**

```python
async def test_uc12_1a_reconfigure_shows_mapping_fields_only(hass):
    """UC12 1a: the per-capability steps are 'restricted to their mapping fields only ...
    never a threshold', and step 8 is skipped entirely."""


async def test_uc12_1a_reconfigure_prefills_step_one_from_the_existing_entry(hass):
    """ADR-0025 point 2: prefill is rendering-only, via add_suggested_values_to_schema."""


async def test_r20_ac7_withdrawing_a_capability_drops_its_mapping_fields(hass):
    """R20 AC7 / ADR-0025 point 2: solar answered 'no' where it was 'yes' -> the solar step is
    never shown, so solar_forecast_entity never enters the accumulator and is absent from the
    saved data bucket."""


async def test_r20_ac7_reconfigure_leaves_the_options_bucket_untouched(hass):
    """UC12 1a: 'any of its thresholds already stored in the options bucket are left untouched'
    -- byte-for-byte equal before and after, including the withdrawn capability's thresholds."""


async def test_adr0008_reconfigure_reloads_the_entry(hass)
async def test_uc12_1a_reconfigure_prefills_the_vehicle_limit_election_from_the_stored_mapping(hass):
    """Design D-2: no stored election key exists, so the answer is derived from whether
    vehicle_charge_limit_entity is mapped."""
```

**Step 2 — implement.** `async_step_reconfigure` sets `self._mode = FlowMode.RECONFIGURE`,
`self._answers = {}`, and delegates to `async_step_core` (same shared method and step id as install —
ADR-0025 point 4). Each step's render path consults `self._mode` to pick the mapping-only half, and
renders through `self.add_suggested_values_to_schema(<fragment>, entry.data)`. The `thresholds` row's
gate (`mode is not RECONFIGURE`) makes step 8 skip itself. `_async_finish` branches to
`async_update_reload_and_abort(entry, data=_split_data(self._answers))`.

**Verify + commit.**

---

## Task T10: The options flow's own table

**Realizes:** UC12 1b; R20 AC7. **ADR honored:** ADR-0025 point 3 (separate table, gated on the
*stored* capability flags, threshold fields only, no vehicle-limit step) and point 4
(`async_step_init` begins the walk), ADR-0005 (options bucket only), ADR-0008. **Test boundary:** HA
harness.

**Files:** edit `config_flow.py`, `tests/test_config_flow.py`.

**Step 1 — failing tests.**

```python
async def test_uc12_1b_options_gates_on_the_stored_capability_flags(hass):
    """ADR-0025 point 3: an entry with solar stored present shows the solar threshold step;
    one with solar absent does not -- nothing in this flow re-asks the capability."""


async def test_uc12_1b_options_shows_no_mapping_field_on_any_step(hass):
    """UC12 1b: 'none of steps 1-7's fields are thresholds' -- and the converse here."""


async def test_uc12_1b_options_has_no_vehicle_limit_step(hass):
    """ADR-0025 point 3: that step has no threshold fields of its own."""


async def test_uc12_1b_options_asks_the_control_interval(hass):
    """UC12 1b: 'a field the install and reconfigure flows never ask, defaulting it instead'."""


async def test_r20_ac7_options_leaves_the_data_bucket_untouched(hass)
async def test_d4_untouched_threshold_resubmits_its_stored_value(hass):
    """Design D-4: threshold fragments keep their `defaults` parameter, so re-submitting a step
    without changing a field preserves the stored value rather than resetting it to the
    module default -- the flat options flow's behaviour, kept."""
async def test_adr0008_options_change_reloads_the_entry(hass)
```

**Step 2 — implement.** `SmartChargingOptionsFlow` gains `_TableWalkMixin`, `OPTIONS_STEP_TABLE`, its
own `async_step_solar` / `async_step_captar` / `async_step_deadline` / `async_step_thresholds`
(threshold halves only, built from the **same** fragments as the config flow — ADR-0025 point 3), and
`async_step_init` which sets `self._mode = FlowMode.OPTIONS`, `self._answers = {}` and calls
`self._async_advance(after=None)` without rendering a form of its own. Gates read
`self.config_entry.data`. `_async_finish` returns
`async_create_entry(title="", data=<intersection incl. control_interval_s>)`. Keep the class's
existing no-`__init__` rule (its docstring explains why) — `_answers` is a class attribute assigned
in `async_step_init`.

**Verify + commit.**

---

## Task T11: Abandonment writes nothing

**Realizes:** UC12 exception flow 3; R20 AC8. **ADR honored:** ADR-0025 point 2 (the accumulator's
lifetime is one flow run). **Test boundary:** HA harness.

**Files:** edit `tests/test_config_flow.py` only — no production code is expected. If a test fails,
something is persisting mid-flow, which is the bug this task exists to catch.

**Step 1 — failing/confirming tests.**

```python
async def test_r20_ac8_abandoned_install_creates_no_entry(hass):
    """UC12 exception flow 3: abort the flow after the core step -> no config entry exists."""
async def test_r20_ac8_abandoned_reconfigure_leaves_the_entry_unchanged(hass):
    """... data and options both byte-for-byte identical to before the flow started."""
async def test_r20_ac8_abandoned_options_flow_leaves_the_options_unchanged(hass)
async def test_adr0025_accumulator_starts_empty_on_a_second_run(hass):
    """ADR-0025 point 2: per-run state. An abandoned run's answers must not leak into the next
    flow started on the same handler class."""
```

Abandon via `hass.config_entries.flow.async_abort(flow_id)` (and the options-flow equivalent).

**Verify + commit.**

---

## Task T12: `strings.json` and translations — one block per step id

**Realizes:** UC12 (every step is user-facing); R20 AC6 (error messages stay field-local).
**ADR honored:** ADR-0025 (Consequences — one block per step id in both the `config` and `options`
sections; install and reconfigure share `config.step.*`). **Test boundary:** HA harness module
`tests/test_config_flow_translations.py` (JSON parity assertions; no `hass` fixture needed).

**Files:** edit `custom_components/smart_charging/strings.json`,
`custom_components/smart_charging/translations/en.json`,
`custom_components/smart_charging/translations/nl.json`,
`tests/test_config_flow_translations.py`.

**Step 1 — failing tests.** Extend the existing error-code parity file with **step and field**
parity, discovered dynamically from the tables and fragments (the same anti-hardcoding discipline
issue #508 established):

```python
def test_every_config_step_has_a_strings_block():
    """ADR-0025 Consequences: one config.step.<id> block per step id the config flow can show,
    including the shared `core` block both install and reconfigure render."""


def test_every_options_step_has_a_strings_block()
def test_every_field_a_step_presents_has_a_label_in_that_steps_block():
    """A field moved between steps without moving its label renders as a raw key."""


def test_no_orphaned_step_block_or_field_label():
    """The converse -- catches the flat flow's leftovers."""


def test_no_field_label_carries_a_conditional_qualifier():
    """ADR-0025 Consequences: '(required if Solar installed)'-style qualifiers are redundant
    once a field only appears when it is required, and must not contradict the new structure."""
```

Check `strings.json` and `translations/en.json`; keep the existing file-level rationale for not
requiring `nl.json` completeness (HA falls back to `en`).

**Step 2 — implement.** Replace `config.step.user` / `config.step.reconfigure` / `options.step.init`
with one block per step id under each section. Redistribute the existing labels; drop the
conditional qualifiers. Write each shared `config.step.*` title/description to read correctly in
**both** a first-install and an edit-my-mappings context — ADR-0025 names this as the accepted
editorial cost of sharing the table. Add labels for the new fields (`deadline_available`,
`vehicle_limit_mapped`, `reminder_lead_h`, and `prompt_timeout_h` if OQ-1 resolved to (a)) in
`strings.json`, `en.json` and `nl.json`.

**Verify + commit.**

---

## Task T13: Extensibility guard, and removal of the flat flow's remains

**Realizes:** R20 AC9; UC12 postcondition 5. **ADR honored:** ADR-0025 (Decision — C is chosen over B
specifically for this property). **Test boundary:** HA harness.

**Files:** edit `custom_components/smart_charging/config_flow.py`, `tests/test_config_flow.py`.

**Step 1 — failing test.** R18 closes the capability set this release, so no real scenario can walk
AC9 (UC12 says so explicitly). Pin it structurally instead, by adding a synthetic capability at test
time and asserting that nothing else changed:

```python
async def test_r20_ac9_a_new_capability_is_one_table_row_and_one_step_method(hass, monkeypatch):
    """R20 AC9 / UC12 postcondition 5: insert a synthetic gated row after the deadline row and
    before the vehicle-limit row, with a step method of its own, and assert (a) it is visited
    exactly where it was inserted when its gate passes, (b) it is skipped when it does not, and
    (c) every other step's field set and relative order is byte-for-byte what it was before the
    insertion -- i.e. no existing step was edited to accommodate it."""
```

Build the "before" expectation from the real table so the test cannot drift.

**Step 2 — implement / clean up.** With every path now running through the tables, delete the flat
flow's remains: `USER_SCHEMA`, `MAPPING_SCHEMA`, `_threshold_schema()`, `_mapping_errors`. Keep
`_split_data` (unchanged), `OPTION_KEYS`, `_parse_states`, `_build_translation`, `_entity`, and the
three step-local guard helpers with their `if capability` prefixes now removed (design D-3).

**Verify + commit.**

---

## Completion check

Before the final push, confirm each of the following and record it in the PR body:

1. `pytest tests/ -q` green; `ruff check .` and `ruff format --check .` clean.
2. Every success criterion in the design doc has at least one named test; every R20 acceptance
   criterion AC1–AC9 is cited by at least one test docstring.
3. `grep -n "USER_SCHEMA\|_mapping_errors\|MAPPING_SCHEMA\|_threshold_schema" custom_components/`
   returns nothing (T13's deletions landed).
4. `grep -rn "options\[" custom_components/` and a scan of every consumer of an `OPTION_KEYS` member
   confirm they all read `opts.get(<key>, DEFAULT_...)`, never direct indexing — the design's
   packaging note depends on this and the narrowed key set makes it load-bearing.
5. `SmartChargingConfigFlow.VERSION` is still `1`, and no migration was added (ADR-0025,
   Consequences).
6. `git diff --stat origin/main` touches only the six files in the scope guard.
7. Both open questions (OQ-1, OQ-2) are answered in the PR thread and the answer is reflected in the
   code and in the design doc, rather than left implicit.

---

## Follow-up (not this plan)

- Wiring `deadline_available` to the runtime capability gating (R18) and `reminder_lead_h` to the
  plug-in reminder (R12/UC10) — the keys are captured here; nothing reads them yet.
- Aligning `DEFAULT_SOLAR_AVAILABLE` with R18 AC1's "defaulting to present", if OQ-2 is resolved as
  recommended (the constant is left as the absent-key read fallback here).
- `entity-catalog.md`'s `solar_power` adapter role and `power_cooldown_min` option — UC12's own
  postcondition names both as pre-existing gaps out of scope to close here.
