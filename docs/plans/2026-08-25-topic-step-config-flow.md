# C4 — Topic-grouped nine-step config flow: Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan
> task-by-task.

**Goal:** Re-cut `custom_components/smart_charging/config_flow.py` from ADR-0025's seven
capability-grouped steps onto the nine **topic-grouped** steps
[UC12](../analysis/use-cases/UC12-configure-installation-through-guided-flow.md) and
[R20](../analysis/requirements.md#r20--guided-installation-configuration) settle, keeping the
table-driven linear `async_step_*` mechanism
[ADR-0027](../adl/0027-config-flow-topic-step-structure.md) re-affirms (Option C). Closes issue #821
of epic #760; slice **C4** of [`docs/design/project-plan.md`](../design/project-plan.md).

**ADR gate:** none outstanding — ADR-0027 is **Accepted** (#820, merged). ADR-0025 is superseded;
no task here may cite it as live authority (T12 is the re-citation pass).

**Architecture:** unchanged in mechanism — one ordered, gated step table per flow, one shared
dispatcher, one `async_step_*` method per UC12 step, one per-run accumulator consumed once at the
terminal step, where `_split_data` (unchanged) and an intersection-based `OPTION_KEYS` consumption
perform the ADR-0005 bucket split. What changes is the *content*: nine topic steps, four
capabilities, per-topic schema fragments, two conjoined reconfigure gates. Full design:
[`2026-08-25-topic-step-config-flow-design.md`](2026-08-25-topic-step-config-flow-design.md) — read
it first; this plan does not restate its tables.

**Scope guard — this plan touches only these six files:**
`custom_components/smart_charging/config_flow.py`, `custom_components/smart_charging/const.py`,
`custom_components/smart_charging/strings.json`,
`custom_components/smart_charging/translations/{en,nl}.json`,
`tests/test_config_flow.py`, `tests/test_config_flow_translations.py`.
No other module changes. In particular **no `adapters/factory.py` change**: `CONF_SOLAR_POWER_ENTITY`
is captured but its role is not built here (design, Deferrals).

`tests/test_translations.py` is **not** in the list and must stay green untouched — the previous
slice already removed its config-flow import and its flat-block parity test. If a task makes it fail,
that is a regression to fix, not collateral to accept.

**Tech Stack:** Python ≥3.12, Home Assistant, `pytest-homeassistant-custom-component` (HA harness —
the config flow is HA-coupled, so per ADR-0009 and project-plan C4's own "Testable on its own" line
every behavioural task here is HA-harness), `ruff`.

**Model:** Per CLAUDE.md, this is development work — execute on **Sonnet**.

**No fork is left open.** The design's "Forks" section records that every candidate fork
(config-entry migration/`VERSION`, the capability set, the step order, each field's bucket) is
answered by a cited source. If a task uncovers a genuine new fork, **stop and report it** rather than
guessing — do not resolve it inside a task.

---

## Conventions used throughout

- **Named constants, no magic strings** (CLAUDE.md) — step ids are `STEP_*` constants in `const.py`;
  field keys are `CONF_*`; error codes `ERROR_*`. Never a bare `"grid"` or `"ev_soc_entity"` literal
  in `config_flow.py` or the tests.
- **Cite, don't restate.** Every test docstring names its criterion (`R20 AC4`, `UC12 4a`,
  `ADR-0027 point 3`). If a test and UC12 disagree, **UC12 wins and the task stops**.
- **Never cite ADR-0025 as live authority.** New and edited docstrings name **ADR-0027**.
- **`git commit --author="Claude <noreply@anthropic.com>"`** with the trailer
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Re-check `git branch --show-current` before every commit (shared checkout).
- **After every task, run the full suite** (`pytest tests/ -q`). `tests/test_init.py`,
  `tests/test_coordinator*.py` and the end-to-end tests build their entries from
  `tests/helpers.py`'s `entry_data_base`/`entry_options_base`, not through the flow, so they should be
  unaffected — any failure there is a regression to fix before committing.
- `ruff check .` **and** `ruff format --check .` both clean before each commit.
- **Genuine red before green** — each task states the failure its first test produces.
- **The flow stays runnable at every commit.** T1–T3 add structure alongside the live flow without
  changing any user-visible path. **T4 is the single atomic cut-over** — the old catch-all steps
  (`mappings`, `thresholds`, `vehicle_limit`) cannot be retired one field at a time without an
  install path that silently stops asking for something, so they are retired in one commit together
  with the nine live steps that replace them. Every commit from T4 onward leaves all three flows
  working end to end, including their validation.

**Landing-order check (design D-4), do this before T1.** Run
`grep -n "CONF_LOW_TARIFF_STATES" custom_components/smart_charging/const.py`:

- **Hit** → issue #746 landed first. `GRID_MAPPING_SCHEMA` (T2) carries `CONF_LOW_TARIFF_ENTITY` with
  its widened `sensor`/`select`/`input_select` domains **and** `CONF_LOW_TARIFF_STATES`, and T4 moves
  their labels from the `mappings` block to the `grid` block.
- **No hit** → this slice lands first. `GRID_MAPPING_SCHEMA` carries `CONF_LOW_TARIFF_ENTITY` exactly
  as it is today, and nothing else. Say so in T2's commit message so #746's own plan can re-point its
  `UNGATED_MAPPING_SCHEMA` step at `GRID_MAPPING_SCHEMA`/`STEP_GRID`.

---

## Task T1: Constants — the four capabilities, the five new keys, the nine step ids

**Realizes:** UC12 step 1, 5, 7, 9; R18 AC9, AC11. **ADR honored:** ADR-0027 (Consequences — "The
step constants and the fixed-order constant change"; "A `notifications` capability flag and its
default … must be added"), ADR-0005 (bucket assignment), CLAUDE.md (no magic strings).
**Test boundary:** plain assertions inside the HA-harness module `tests/test_config_flow.py` (no
`hass` fixture needed; they live there for cohesion with the flow they describe).

**Files:** edit `custom_components/smart_charging/const.py`, `tests/test_config_flow.py`.

**Step 1 — failing tests.**

```python
def test_d1_new_config_keys_match_the_entity_catalog():
    """Design D-1: key strings and defaults come from entity-catalog.md, not invented.
    notifications_available defaults False -- R18 AC9's named default-ABSENT exception,
    the one capability whose form default and read fallback agree (design D-5)."""

def test_d1_new_threshold_keys_are_option_keys_members():
    """ADR-0005: power_cooldown_min, deadline_notice_enabled and plug_in_reminder_enabled
    are config-entry OPTIONS, so they must be in OPTION_KEYS or the terminal split routes
    them to data."""

def test_adr0027_step_ids_are_uc12s_nine():
    """ADR-0027, Consequences: STEP_GRID/EV_CHARGER/VEHICLE/POWER/NOTIFICATIONS added."""
```

The first two fail with `ImportError`/`AttributeError` on the new constants; the third likewise.

**Step 2 — implement.** In `const.py`, add exactly the design D-1 table's ten constants
(`CONF_NOTIFICATIONS_AVAILABLE`/`DEFAULT_NOTIFICATIONS_AVAILABLE`, `CONF_POWER_COOLDOWN_MIN`/
`DEFAULT_POWER_COOLDOWN_MIN`, `CONF_DEADLINE_NOTICE_ENABLED`/`DEFAULT_DEADLINE_NOTICE_ENABLED`,
`CONF_PLUG_IN_REMINDER_ENABLED`/`DEFAULT_PLUG_IN_REMINDER_ENABLED`, `CONF_SOLAR_POWER_ENTITY`,
`ERROR_REQUIRED_WHEN_DEADLINE_AVAILABLE`) plus `STEP_GRID`, `STEP_EV_CHARGER`, `STEP_VEHICLE`,
`STEP_POWER`, `STEP_NOTIFICATIONS`. Append the three new option keys to `OPTION_KEYS` in
`config_flow.py`. Each constant carries a one-line comment naming its catalog row and requirement.

**Do not delete anything yet** — `STEP_VEHICLE_LIMIT`/`STEP_MAPPINGS`/`STEP_THRESHOLDS`,
`CONF_VEHICLE_LIMIT_MAPPED` and the two retiring `ERROR_*` codes are still live until T4.

`ERROR_REQUIRED_WHEN_DEADLINE_AVAILABLE` needs its `config.error` entry in `strings.json`,
`translations/en.json` and `translations/nl.json` **in this same commit** —
`tests/test_config_flow_translations.py` discovers `ERROR_*` constants dynamically and fails the
moment the constant exists without a translation.

**Verify + commit.**

---

## Task T2: The nine per-step schema fragments

**Realizes:** UC12 steps 1–9 (their field lists); R20 AC1, AC3, AC4, AC5. **ADR honored:** ADR-0027
(Consequences — "The schema fragments are re-cut along topic lines"), ADR-0005 (mapping half → data,
threshold half → options). **Test boundary:** HA harness module `tests/test_config_flow.py`; these
particular assertions need no `hass` fixture (design, Testing approach).

**Files:** edit `config_flow.py`, `tests/test_config_flow.py`.

**Step 1 — failing tests.** One key-set test per step, spelling the expected field set out from
`CONF_*` constants (an independent oracle — never `_keys(fragment) == _keys(fragment)`):

```python
def test_uc12_step1_core_threshold_fragment_has_exactly_uc12s_fields():
    """The core *mapping* half (the four capability declarations) is asserted in T4, which
    is where CORE_MAPPING_SCHEMA is re-cut -- it renders live until then."""
def test_uc12_step2_grid_fragments_have_exactly_uc12s_fields()
def test_uc12_step3_ev_charger_fragments_have_exactly_uc12s_fields()
def test_uc12_step4_vehicle_fragments_have_exactly_uc12s_fields()
def test_uc12_step5_power_threshold_fragment_has_exactly_uc12s_fields()
def test_uc12_5b_captar_threshold_fragment_carries_the_peak_protection_fields():
    """UC12 5b / R18 AC5: power_respect_peak, safety_margin_w, max_peak_kw, peak_floor_kw
    and peak_grace_min now live on the CapTar-gated step and nowhere else."""
def test_uc12_step7_solar_fragments_have_exactly_uc12s_fields():
    """Includes the new solar_power_entity mapping (design D-1) and both hold durations
    plus the restart debounce, which epic #760's list omits and UC12 names."""
def test_uc12_5c_deadline_mapping_carries_the_home_day_external_carve_out():
    """UC12 5c / R20 AC5: the single ungated field the flow places on a gated step."""
def test_uc12_step9_notifications_fragments_have_exactly_uc12s_fields():
    """R18 AC11: all three per-notification enable toggles, each defaulting on, plus the
    target mapping and the evening-prompt time."""

def test_r20_ac4_no_field_belongs_to_two_fragments():
    """R20 AC4 / ADR-0027 Context: ev_soc_entity moved to the ungated `vehicle` step, so the
    include_ev_soc carve-out the seven-step model needed is gone -- fragments are now
    strictly disjoint, with no exemption list."""
def test_adr0005_every_option_key_appears_in_exactly_one_threshold_fragment()
def test_adr0005_no_option_key_appears_in_a_mapping_fragment()
def test_uc12_1b_control_interval_is_only_in_the_core_threshold_fragment_when_requested():
    """UC12 1b: _core_threshold_schema(include_interval=True) is the options flow's only
    door to the control interval."""
```

All fail with `AttributeError` on the new fragment names.

The last four run over an explicit tuple of the **new** fragments only — the retiring
`UNGATED_MAPPING_SCHEMA`/`_ungated_threshold_schema` still exist until T4 and would overlap with
them. The tuple is the same one `tests/test_config_flow_translations.py`'s `CONFIG_STEP_FIELDS` is
built from after T4, so the assertion keeps its meaning once the old fragments are gone.

**Step 2 — implement.** Add the fragments named in the design's "Schema fragments" table, alongside
the existing ones (nothing is deleted or rewired yet, so every current test stays green).
`CORE_MAPPING_SCHEMA` is the one fragment **not** touched here: `async_step_core` renders it live
today, so re-cutting it to the four capability declarations belongs to T4's cut-over. Everything else
is new: `_core_threshold_schema`, `GRID_MAPPING_SCHEMA`, `_grid_threshold_schema`,
`EV_CHARGER_MAPPING_SCHEMA`, `_ev_charger_threshold_schema`, `VEHICLE_MAPPING_SCHEMA`,
`_vehicle_threshold_schema`, `_power_threshold_schema`, `SOLAR_MAPPING_SCHEMA`,
`NOTIFICATIONS_MAPPING_SCHEMA`, `_notifications_threshold_schema`; extend `_captar_threshold_schema`
with the five peak-protection fields and `DEADLINE_MAPPING_SCHEMA` with
`CONF_HOME_DAY_EXTERNAL_ENTITY`.

Requiredness per design D-2: `vol.Required` for `ev_soc_entity` (on `VEHICLE_MAPPING_SCHEMA`),
`solar_forecast_entity`, and every field already required today; `vol.Optional` for
`solar_power_entity`, `notification_target_entity`, `car_home_entity`,
`vehicle_charge_limit_entity`, `ev_battery_capacity_entity`, `grid_voltage_entity`,
`low_tariff_entity`, `departure_external_entity`, `home_day_external_entity`.

**Note on the two extended fragments:** `_captar_threshold_schema` and `DEADLINE_MAPPING_SCHEMA` are
rendered live today, so extending them here changes what the *current* captar/deadline steps ask.
That is intended and harmless — the fields are the same ones the live `thresholds`/`mappings` steps
also ask for until T4 retires them, and T4's tests assert the post-cut-over field sets. Adjust the
existing `tests/test_config_flow_translations.py` `CONFIG_STEP_FIELDS` map and add the corresponding
labels to the three translation files in this same commit so the parity test stays green.

**Verify + commit.**

---

## Task T3: The two new tables and the nine step methods (defined, not yet wired)

**Realizes:** UC12's fixed order and gating; R20 AC2, AC7, AC9. **ADR honored:** ADR-0027 Decision
(Option C, unchanged in mechanism), point 3 (reconfigure's subset is a per-step gate, not a stop
condition), point 4 (the options flow keeps its own table). **Test boundary:** HA harness module;
the table-shape assertions need no `hass` fixture.

**Files:** edit `config_flow.py`, `tests/test_config_flow.py`.

**Step 1 — failing tests.**

```python
def test_uc12_config_table_is_uc12s_fixed_order_minus_the_core_entry_point():
    """UC12 step table / ADR-0027 point 5: nine steps, captar BEFORE solar; `core` is the
    shared entry point (ADR-0027 point 5) and deliberately not a row. The expected order is
    spelled out here from const.py's STEP_* constants, not read back from the table."""
def test_uc12_1b_options_table_is_all_nine_steps_including_core()
def test_adr0027_every_config_table_step_has_a_step_method():
    """Renamed from test_adr0025_... (T12 does the rest of the re-citation pass). The named
    discharge of Option C's stated Con: a row with no method is silently unreachable."""
def test_adr0027_every_options_table_step_has_a_step_method()
def test_adr0027_point3_power_and_captar_rows_are_gated_off_in_reconfigure():
    """UC12 1a: neither has a mapping half, so both must be absent from the reconfigure walk
    -- expressed as each row's own conjoined gate, not as a stop condition."""
def test_uc12_1b_options_gates_read_stored_flags_defensively():
    """ADR-0027 point 4 + design 'Step ids': every options gate is .get(key, DEFAULT_*), so an
    entry predating notifications_available opens Configure without KeyError."""
```

They fail with `AttributeError` on the new table/method names.

**Step 2 — implement.** Define the nine `async_step_*` methods on `SmartChargingConfigFlow` and the
nine on `SmartChargingOptionsFlow`, each rendering its own fragment(s) via the existing
`_maybe_prefill`/`defaults` mechanisms and ending in `await self._async_advance(after=<its own id>)`.
Define the two new tables. **Leave `_table` pointing at the current tables** and leave
`async_step_user`/`async_step_reconfigure`/`async_step_init` untouched — nothing is wired yet, so the
live flow is unchanged and every existing behavioural test still passes.

For the gate assertions, test the gate callables directly against a small stub exposing `_answers`,
`_mode` and `config_entry` — no `hass` needed.

**Verify + commit.**

---

## Task T4: Cut-over — the install flow walks the nine steps

**Realizes:** UC12 steps 1–10, 4a, 4b, 5a, 5b, 5c; R20 AC1, AC3, AC4, AC5; R18 AC5, AC9, AC10, AC11.
**ADR honored:** ADR-0027 Decision + point 1 (validation is step-local, one guard becomes
field-local) + Consequences (two guard helpers dissolve; the catch-alls disappear), ADR-0005 (the
bucket split), CLAUDE.md (no magic strings). **Test boundary:** HA harness.

**This is the atomic task.** The three catch-all steps cannot be retired field by field without an
install path that silently stops asking for something, so they are retired in one commit together
with the nine live steps that replace them.

**Files:** edit `config_flow.py`, `const.py`, `strings.json`, `translations/en.json`,
`translations/nl.json`, `tests/test_config_flow.py`, `tests/test_config_flow_translations.py`.

**Step 1 — failing tests.**

```python
async def test_uc12_install_all_capabilities_walks_all_nine_steps_in_order(hass)
async def test_uc12_install_default_capabilities_skips_notifications(hass):
    """R18 AC9 / UC12 5a: a household accepting the defaults is offered steps 6-8 but NOT
    step 9 -- the one capability that is opted into rather than out of."""
async def test_r20_ac4_ev_soc_is_asked_on_vehicle_with_no_capabilities_declared(hass):
    """R20 AC4 / UC12 postconditions: presented exactly once, on the always-shown `vehicle`
    step, even when neither solar nor CapTar is declared -- the case the seven-step model
    could not present at all."""
async def test_adr0005_install_splits_buckets_over_the_nine_step_answers(hass):
    """ADR-0005 / UC12 step 10: mappings + the four capability flags + the derived status
    translation in data; thresholds, defaults and seed values in options; control_interval_s
    defaulted, never asked (UC12 1b)."""
async def test_r20_ac3_captar_absent_install_stores_no_peak_protection_keys(hass):
    """UC12 5b / R18 AC5: all five peak-protection values are now behind the CapTar gate."""
async def test_r20_ac3_notifications_absent_install_stores_no_notification_keys(hass):
    """R18 AC10: no target mapping, no enable toggle, no evening-prompt time."""
async def test_uc12_5c_home_day_external_is_absent_when_deadlines_are_unmanaged(hass)
async def test_r18_ac11_notification_toggles_default_on_and_land_in_options(hass)
```

The first fails at the second form: the live flow shows `solar`, not `grid`.

**Step 2 — implement.**

1. Re-cut `CORE_MAPPING_SCHEMA` to the four capability declarations (solar `default=True` per design
   D-5; captar/deadline `default=DEFAULT_*`; notifications `default=DEFAULT_NOTIFICATIONS_AVAILABLE`,
   i.e. `False`) and render `core` with `_core_threshold_schema()` extended in for install.
2. Point `SmartChargingConfigFlow._table` at the new config table; `async_step_user` and
   `async_step_reconfigure` keep delegating into `async_step_core`.
3. Move `ev_soc_entity` (`vol.Required`) and `car_home_entity` onto the `vehicle` step; make
   `solar_forecast_entity` a plain `vol.Required` on `solar` (ADR-0027 point 1).
4. **Delete:** `UNGATED_MAPPING_SCHEMA`, `_ungated_threshold_schema`, `VEHICLE_LIMIT_MAPPING_SCHEMA`,
   `_solar_mapping_schema`, `_captar_mapping_schema`, `_ev_soc_missing_error`,
   `_solar_forecast_missing_error`, `async_step_mappings`, `async_step_thresholds`,
   `async_step_vehicle_limit`, the old tables, `_maybe_prefill`'s now-unused `extra_from` parameter,
   `self._answers.pop(CONF_VEHICLE_LIMIT_MAPPED, None)`, and from `const.py`
   `CONF_VEHICLE_LIMIT_MAPPED`, `STEP_VEHICLE_LIMIT`, `STEP_MAPPINGS`, `STEP_THRESHOLDS`,
   `ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE`, `ERROR_REQUIRED_WHEN_CAPTAR_AVAILABLE` — plus the last
   two codes' `config.error` entries in all three translation files (design, "Guards and required
   fields").
5. Update `UC12_FIXED_STEP_ORDER` to the nine ids.
6. `strings.json`/`en.json`/`nl.json`: remove the `config.step.vehicle_limit`/`mappings`/`thresholds`
   blocks, add `grid`, `ev_charger`, `vehicle`, `power`, `notifications`, and re-home every field
   label to the block of the step that now presents it. Titles and descriptions must read correctly
   in **both** a first-install and an edit-my-mappings context (ADR-0027, Consequences: install and
   reconfigure share `config.step.*`), and the parenthetical "(required if …)" qualifiers stay
   dropped — a field now appears only when it is required.
7. Rebuild `tests/test_config_flow_translations.py`'s `CONFIG_STEP_FIELDS` map from the new
   fragments; its module-level `assert set(CONFIG_STEP_FIELDS) == CONFIG_STEP_IDS` self-check must
   still hold.

The options flow is untouched by this task and keeps walking its old table — it is re-cut in T7.
Because `_ungated_threshold_schema` is deleted here, `SmartChargingOptionsFlow.async_step_thresholds`
must be pointed at the new per-topic threshold fragments in this same commit as a **mechanical**
change (same fields, same defaults, several forms instead of one) so the options flow keeps asking
everything it asks today; T7 then gives it its proper table.

**Expect a wide rewrite of `tests/test_config_flow.py`** (≈2 500 lines): every test that drives the
install path through `core → mappings → thresholds` is re-driven through the nine steps. Keep the
existing helper shape — a `_run_install_flow(hass, *, capabilities, per_step_input)` driver — and
extend `capabilities` to four flags.

**Verify + commit.**

---

## Task T5: Traversal matrix — sixteen capability combinations, install

**Realizes:** R20 AC2, AC3; UC12 5a. **ADR honored:** ADR-0027 Consequences ("every capability
combination — now sixteen, since `notifications` is a fourth independent flag — must be shown to
traverse exactly the steps UC12 prescribes, in order"). **Test boundary:** HA harness.

**Files:** edit `tests/test_config_flow.py`.

**Step 1 — failing test.** One parametrized test over all `2**4` combinations asserting the **exact
sequence** of `step_id`s the install flow shows:

```python
@pytest.mark.parametrize("solar,captar,deadline,notifications", ALL_SIXTEEN)
async def test_r20_ac2_install_traverses_exactly_uc12s_steps_in_order(hass, ...):
    """R20 AC2 / UC12 5a: the five ungated steps always, plus exactly one step per declared
    capability, in UC12's fixed order (captar BEFORE solar). Expected sequence is computed
    here from the four flags, not read back from CONFIG_TABLE."""
```

Add the ungated-step invariant explicitly, since it is the design's named safety caveat:

```python
@pytest.mark.parametrize("solar,captar,deadline,notifications", ALL_SIXTEEN)
async def test_r20_ac5_grid_and_charger_bounds_are_asked_on_every_install_path(hass, ...):
    """Design, Safety caveat: grid_ceiling_a / grid_safety_offset_a / nominal_voltage (grid)
    and min_current / max_current (ev_charger) sit on ungated steps and can never be skipped
    by a capability gate."""
```

**Step 2 — implement.** Expect this to pass on T4's implementation. If any combination diverges,
the bug is in T4's gates — fix it here rather than weakening the expectation.

**Verify + commit.**

---

## Task T6: The reconfigure flow (UC12 1a)

**Realizes:** UC12 1a; R20 AC2, AC7. **ADR honored:** ADR-0027 point 2 (prefill is rendering-only;
the accumulator is never seeded), point 3 (reconfigure's subset is a per-step gate), ADR-0008
(reload). **Test boundary:** HA harness.

**Files:** edit `config_flow.py` (only if a gate proves wrong), `tests/test_config_flow.py`.

**Step 1 — failing tests.**

```python
async def test_uc12_1a_reconfigure_never_shows_power_or_captar(hass):
    """ADR-0027 point 3: neither step has a mapping half, so both are absent from the
    reconfigure walk -- asserted with the CapTar capability PRESENT, so the only reason
    `captar` is skipped is the conjoined flow-mode half of its gate."""
async def test_uc12_1a_reconfigure_shows_mapping_halves_only(hass)
async def test_uc12_1a_reconfigure_shows_core_grid_ev_charger_vehicle_unconditionally(hass):
    """UC12 1a: the `vehicle` mapping half appears even with every capability absent."""
async def test_r20_ac7_reconfigure_leaves_the_options_bucket_untouched(hass)
async def test_r20_ac7_withdrawing_a_capability_drops_its_mapping_fields_only(hass):
    """UC12 1a / 5b: the withdrawn capability's mapping fields leave the data bucket (the
    accumulator was never seeded from the entry, ADR-0027 point 2), while its thresholds
    stay in options untouched."""
async def test_adr0008_reconfigure_reloads_the_entry(hass)
```

**Step 2 — implement.** Expect these to pass on T4's implementation; fix gates or `_maybe_prefill`
call sites if not.

**Verify + commit.**

---

## Task T7: The options flow's own nine-row table (UC12 1b)

**Realizes:** UC12 1b; R20 AC7; R18 AC11. **ADR honored:** ADR-0027 point 4 (the options flow keeps
its own table, gated on stored flags, threshold halves only, and is the only flow presenting the
control interval), ADR-0005, ADR-0008. **Test boundary:** HA harness.

**Files:** edit `config_flow.py`, `strings.json`, `translations/{en,nl}.json`,
`tests/test_config_flow.py`, `tests/test_config_flow_translations.py`.

**Step 1 — failing tests.**

```python
async def test_uc12_1b_options_walks_all_five_ungated_steps_plus_declared_gated_ones(hass)
async def test_uc12_1b_control_interval_is_presented_on_the_options_core_step_only(hass):
    """UC12 1b: install defaults it, reconfigure touches no options -- the options flow is
    the only path that presents it. Assert its absence on both other flows too."""
async def test_uc12_1b_options_never_presents_a_mapping_or_a_capability_declaration(hass)
@pytest.mark.parametrize("solar,captar,deadline,notifications", ALL_SIXTEEN)
async def test_r20_ac2_options_traverses_exactly_the_stored_capabilities_steps(hass, ...)
async def test_uc12_1b_options_gate_on_an_entry_predating_notifications_available(hass):
    """Design 'Step ids': a MockConfigEntry whose data has no notifications_available key
    opens Configure without KeyError and skips step 9."""
async def test_r20_ac7_options_merges_into_stored_options_never_replaces_them(hass):
    """A capability withdrawn through reconfigure leaves its thresholds in options; the next
    Configure+Save must not delete them."""
async def test_r18_ac11_options_can_toggle_one_notification_off_without_touching_the_others(hass)
```

**Step 2 — implement.** Point `SmartChargingOptionsFlow._table` at the new options table; give it
`async_step_core` (with `include_interval=True`), `grid`, `ev_charger`, `vehicle`, `power`,
`captar`, `solar`, `deadline`, `notifications`, each rendering only its threshold fragment with
`self.config_entry.options` as `defaults`. Delete `async_step_thresholds` and the old options table.
Add the five new `options.step.*` blocks (and remove the retired ones) in all three translation
files, and rebuild `OPTIONS_STEP_FIELDS` in the parity test module.

**Verify + commit.**

---

## Task T8: The car-at-home field-level rule (UC12 4a)

**Realizes:** UC12 4a; R20 AC3, AC6. **ADR honored:** ADR-0027 point 1 ("`_car_home_missing_error`
survives on the `vehicle` step but must now fire on the deadline capability as well as on a
filled-in charge-limit mapping … reading the former from the accumulator") and its "What this
forecloses" note. **Test boundary:** HA harness.

**Files:** edit `config_flow.py`, `const.py` (nothing new — `ERROR_REQUIRED_WHEN_DEADLINE_AVAILABLE`
landed in T1), `tests/test_config_flow.py`.

**Step 1 — failing tests — this is UC12 4a's whole truth table.**

```python
async def test_uc12_4a_car_home_required_when_a_charge_limit_is_mapped(hass):
    """errors == {CONF_CAR_HOME_ENTITY: ERROR_REQUIRED_WHEN_VEHICLE_LIMIT_MAPPED}; the
    `vehicle` step is re-shown and the flow has NOT advanced."""
async def test_uc12_4a_car_home_required_when_the_deadline_capability_is_present(hass):
    """The cross-step half: the trigger was answered on step 1, the error is reported on the
    `vehicle` step (design D-3 -> ERROR_REQUIRED_WHEN_DEADLINE_AVAILABLE), never at the end
    of the flow."""
async def test_uc12_4a_car_home_optional_when_neither_trigger_holds(hass):
    """No charge limit mapped AND deadlines unmanaged -> the step submits blank and advances."""
async def test_uc12_4a_charge_limit_trigger_wins_when_both_hold(hass):
    """Design D-3: the message names the field the user just filled in."""
```

**Step 2 — implement.** `_car_home_missing_error(merged)` reads
`{**self._answers, **user_input}`: charge-limit trigger first, deadline-capability trigger second,
each returning its own code. Re-show the `vehicle` step with the field-local error; never advance.

**Verify + commit.**

---

## Task T9: Exception flows — domain mismatch, blank required field, abandonment

**Realizes:** UC12 Exception flows; R20 AC6, AC8. **ADR honored:** ADR-0027 point 1 (validation is
step-local). **Test boundary:** HA harness.

**Files:** edit `tests/test_config_flow.py`.

**Step 1 — failing tests.**

```python
async def test_r20_ac6_wrong_domain_entity_is_rejected_on_the_step_that_presents_it(hass):
    """UC12 exception flow 1: e.g. a `sensor` where charger_current requires a `number` --
    the same step is re-shown, the flow does not advance, no later step is ever reached with
    an invalid earlier mapping in place."""
async def test_r20_ac6_blank_required_ev_soc_is_reported_on_the_vehicle_step(hass):
    """ADR-0027 point 1: now a plain vol.Required on an always-shown step -- surfaces as
    InvalidData from the flow manager, not as an end-of-flow error."""
async def test_r20_ac6_blank_required_solar_forecast_is_reported_on_the_solar_step(hass)
async def test_r20_ac8_abandoning_install_creates_no_entry(hass)
async def test_r20_ac8_abandoning_reconfigure_leaves_the_entry_exactly_as_it_was(hass)
async def test_r20_ac8_abandoning_options_leaves_the_options_bucket_exactly_as_it_was(hass)
```

**Step 2 — implement.** Expect these to pass on T4/T7's implementation; any failure is a real gap to
close in `config_flow.py`.

**Verify + commit.**

---

## Task T10: Extensibility guard (R20 AC9)

**Realizes:** R20 AC9; UC12 postconditions. **ADR honored:** ADR-0027 Decision ("a new capability is
one table row plus one step method, appended after the existing gated rows, with no existing step
touched" — the decisive point over Option B). **Test boundary:** HA harness.

**Files:** edit `tests/test_config_flow.py`.

**Step 1 — failing test.** The capability set is closed this release (R18 AC13), so this criterion is
only reachable by construction:

```python
async def test_r20_ac9_a_tenth_gated_row_appended_changes_no_existing_step(hass, monkeypatch):
    """R20 AC9: monkeypatch a synthetic tenth row (gated on a fake flag) onto the END of
    CONFIG_TABLE with its own step method; assert (a) it is reached when its flag is set,
    (b) skipped when it is not, and (c) the nine existing steps' order and field sets are
    byte-identical either way."""
```

**Step 2 — implement.** Test-only; if the dispatcher needs a change to make it pass, that is a real
finding — report it rather than special-casing the test.

**Verify + commit.**

---

## Task T11: `nl.json` parity and step-block wording

**Realizes:** R20 AC1–AC7's user-facing surface. **ADR honored:** ADR-0027 Consequences
("Translations are re-cut, and grow … each step's title and description must still read correctly in
both a first-install and an edit-my-mappings context"). **Test boundary:** plain pytest
(`tests/test_config_flow_translations.py`, `tests/test_translations.py` — data-file checks, ADR-0009).

**Files:** edit `strings.json`, `translations/en.json`, `translations/nl.json`.

**Step 1 — failing checks.** `tests/test_translations.py`'s
`test_strings_json_and_en_json_are_identical` and `test_nl_json_has_the_same_keys_as_en_json` are the
red here if T4/T7 left any drift; `test_no_orphaned_step_block_or_field_label` catches a label left
behind on a retired block.

**Step 2 — implement.** Reconcile all three files; write real Dutch for the five new step blocks and
every re-homed label (never an English string in `nl.json`). Re-read each of the nine
titles/descriptions once in the reconfigure voice as well as the install voice.

**Verify + commit.**

---

## Task T12: The ADR re-citation pass

**Realizes:** documentation integrity. **ADR honored:** ADR-0027 Consequences, which names this
explicitly: "roughly fifty docstring and comment references to 'ADR-0025' live in `config_flow.py`,
`const.py`, `tests/test_config_flow.py` and `tests/test_config_flow_translations.py`, including a
test named `test_adr0025_every_config_table_step_has_a_step_method`, and all of them must come to
name ADR-0027 instead." **Test boundary:** n/a (comment/docstring change); the full suite is the
regression guard.

**Files:** `config_flow.py`, `const.py`, `tests/test_config_flow.py`,
`tests/test_config_flow_translations.py`.

**Steps.** `grep -rn "ADR-0025\|adr0025" custom_components tests` and re-point every hit at ADR-0027,
adjusting the surrounding sentence where the old ADR's *reasoning* is cited rather than its number
(e.g. "ADR-0025 point 3" → "ADR-0027 point 3", whose content differs). Delete any comment that
describes the seven-step model as current — in particular `config_flow.py`'s historical note about
`_mapping_errors` and the incremental table build-out, and `const.py`'s `STEP_*` block comment. Two
kinds of reference **stay**: a deliberate historical note that says ADR-0025 was superseded, and the
design-doc references, which must now point at
`2026-08-25-topic-step-config-flow-design.md` rather than `2026-08-13-guided-config-flow-design.md`.

**Verify + commit.**

---

## Completion check

Before the final commit, verify each of the following and record the result in the PR body:

1. `pytest tests/ -q` fully green; `ruff check .` and `ruff format --check .` both clean.
2. **Both key sets narrow safely** (design, Packaging):
   `grep -rn "entry\.data\[\|\.options\[\|opts\[" custom_components/smart_charging/` returns no
   config-key indexing — every consumer reads `.get(<key>)` / `.get(<key>, DEFAULT_...)`. This is
   project-plan C4's integration checkpoint ("the entry C4 writes drives RA1's factory and the
   Store's data/options reads on setup") verified by construction.
3. **No orphaned constant:** `grep -rn "STEP_VEHICLE_LIMIT\|STEP_MAPPINGS\|STEP_THRESHOLDS\|
   CONF_VEHICLE_LIMIT_MAPPED\|ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE\|
   ERROR_REQUIRED_WHEN_CAPTAR_AVAILABLE" custom_components tests` returns nothing.
4. **No ADR-0025 citation as live authority** (T12).
5. `SmartChargingConfigFlow.VERSION` is still `1` and no `async_migrate_entry` was added
   (ADR-0027, Consequences; design, Forks).
6. Every one of the design's eleven success criteria has at least one named test.
7. `manifest.json` untouched; no file outside the six-file scope guard changed.

---

## Follow-up (not this plan)

Each is a deferral the design names, with its owner; none blocks this slice:

- Building the `solar_power` adapter role from `CONF_SOLAR_POWER_ENTITY` (RA1) — the key is captured
  here contract-first, the role is not.
- Wiring `power_cooldown_min` (R11), `deadline_notice_enabled`/`plug_in_reminder_enabled`
  (R5/R12/R18 AC11), and `notifications_available`'s own delivery gate (R18 AC10).
- Issue #746's `CONF_LOW_TARIFF_STATES` field, if it did not land before this slice (D-4).
- `docs/design/project-plan.md`'s C4 entry, whose "ADR gate: none new" line is accurate again now
  that ADR-0027 is Accepted — no edit needed, recorded here so the next reader does not re-open it.
