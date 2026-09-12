# ADR-0040: A fifth mandated adapter case — a numeric role's expected unit set and its behaviour on a foreign or absent unit (extends ADR-0009)

Date: 2026-09-12
Status: Accepted

## Context

[ADR-0009](0009-testing-strategy.md) mandates, in its Decision and again in its Consequences, the
per-role coverage every adapter must have before it is considered done: entity **present**,
**absent**, **unavailable**, and — for enum roles — an **unmapped raw state**. That set is
restated in `.claude/skills/write-tests/SKILL.md`, `.claude/agents/test-reviewer.md` and
`.claude/agents/code-reviewer.md`, so it is what a test author writes to and what a reviewer
demands.

Four of those cases are states of **presence**: is there a reading at all. Only the fifth, and
only for enum roles, is a state of **meaning**: does the reading say what the code thinks it
says. For a numeric role there is no meaning case, and the consequence is mechanical rather than
subtle.

`tests/adapters/test_numeric.py::test_reads_native_float` seeds a state with **no unit attribute
at all**:

```python
hass.states.async_set("sensor.net_power", "2300.0")
```

An adapter that ignores `unit_of_measurement` entirely therefore satisfies the *whole* mandated
set by construction — not by luck, but because nothing in the set can distinguish it from one
that honours units. `NumericReadAdapter` did exactly that for `net_power` and `charger_power`,
returning `float(state.state)` with no unit inspection, and a live installation whose grid meter
reported kW while its charger reported W ran with a `baseline_w` collapsed to roughly
`-charger_w`. The full suite was green throughout. The defect was found by a human questioning an
implausible solar-surplus number on a dashboard.

[ADR-0038](0038-unit-contract-at-the-power-read-adapter-boundary.md) has since settled the
*runtime* contract for the four power-valued roles, and it closes with the boundary this record
picks up: "it makes no claim about *test* coverage for the contract. That the mandated adapter
cases (ADR-0009) test four states of presence and none of meaning is a separate gap, tracked
separately — and it must be settled by its own ADR extending ADR-0009, not inferred from this
one. A conforming adapter under this record could still ship with no unit test at all."

Three forces bear on what to do about that.

**The model already exists, for one role, by accident of authoring order.**
`PowerKilowattReadAdapter` was written under ADR-0030's deferred unit obligation and its tests
already cover both halves of the meaning case:
`tests/adapters/test_numeric.py::test_power_kilowatt_adapter_missing_unit_returns_none` (absent
unit) and `::test_power_kilowatt_adapter_non_power_unit_returns_none` (foreign unit). Nothing made
the author write them; nothing made the authors of the three sibling W roles write theirs. That
asymmetry — one role's good luck — is the gap, and the fix is to make the existing good practice
the rule rather than to invent a new practice.

**The gap is wider than the power roles.** Ten adapter roles read a numeric value
(`adapters/factory.py`). Four are power-valued and now governed by ADR-0038. The other six —
`grid_voltage` (V), `ev_soc` (%), `ev_battery_capacity` (kWh), `solar_forecast` (kWh) via
`NumericReadAdapter`, and `charger_current` (A), `vehicle_charge_limit` (%) via
`NumericReadWriteAdapter` — carry the same class of hazard, have no unit contract at runtime, and
have no unit case in their tests. ADR-0038 names deciding their unit sets as follow-up. A
coverage rule written to bind only where a runtime contract already exists would bind exactly the
four roles that are already safe.

**Coverage is what this record can settle; behaviour is not.** Whether `grid_voltage` should
reject a millivolt reading or accept it is a domain decision about that role, and under CLAUDE.md's
domain/business-rules carve-out it belongs to `entity-catalog.md` or to a role-specific ADR, not
here. What ADR-0009 owns, and what this record extends, is what a passing adapter suite is allowed
to mean — which CLAUDE.md's test/CI carve-out names explicitly as staying ADR-worthy: *"the
test-tier taxonomy — which tier a test belongs in, what a passing suite is allowed to mean, and
where a contributor is expected to put a new test (see ADR-0009 and ADR-0037)."* A mandated
per-role case is that second clause. Unlike ADR-0037, which had to argue the carve-out should say
this, this record can cite it.

## Considered options

### Option A — Add a fifth mandated case: state the role's expected unit set and pin its behaviour on a foreign and on an absent unit

Extend ADR-0009's mandated per-role coverage with a fifth case, scoped to numeric roles carrying a
unit. The case obliges the test suite to *state* the role's expected unit set and to *pin* what
happens on a unit outside it and on no unit at all — whatever that behaviour currently is,
including "used as-is".

- Pro: kills the by-construction pass wherever a role's behaviour is decided — a unit-blind adapter
  can no longer satisfy the mandated set, because two of the cases now seed units it must have an
  answer for. Where the behaviour is *not* decided the claim is weaker and worth stating as such:
  a unit-blind adapter still passes clauses 2 and 3 when both assert "used as-is", and what the
  rule buys there is that the undecided contract becomes visible in the suite rather than absent
  from it. It is grounded rather than aspirational — the two `PowerKilowattReadAdapter` tests
  above already are the rule, so adopting it costs that role nothing and names an existing
  standard rather than an imagined one.
- Pro: it binds the six uncontracted roles *without* pre-deciding their behaviour. A test that
  pins "a `mV` reading on `grid_voltage` is used as the number it is" is a true and useful test:
  it makes an undecided contract visible in the suite and in review, where today it is invisible
  in both. The rule creates the question; ADR-0038's follow-up answers it.
- Con: a test that pins today's behaviour can read as blessing it. A reviewer who sees a passing
  foreign-unit case may take it as evidence the role is safe when it records only that the role is
  *consistent*. This is a real cost and the Decision below carries a mitigation rather than a
  denial.
- Con: a fifth case is a fifth thing to remember, and its trigger is conditional ("numeric roles
  carrying a unit") where the other four are unconditional. Conditional rules are the ones that
  get applied wrongly at the edges.

### Option B — Do nothing; rely on ADR-0038's runtime contract plus review

Leave ADR-0009's four cases alone. The power roles now convert or reject by contract, and a future
role's unit handling gets caught at code review.

- Pro: no new rule, no new edge to get wrong, and the defect that motivated all of this is already
  fixed at the boundary where it mattered. Review is not a straw man here: `adr-reviewer` did raise
  the unit hazard on ADR-0030's own PR.
- Con: it raised the hazard and the answer scoped it to the one new role — the sibling question was
  never asked, because nothing asks it. ADR-0038 itself says a conforming adapter under it could
  still ship with no unit test at all, so the runtime contract and the coverage obligation are
  genuinely independent. And the six non-power numeric roles stay both uncontracted and untested,
  which is precisely the state `net_power` was in.

### Option C — Supersede ADR-0009 with a restated mandated set

Write a record that replaces ADR-0009 wholesale, carrying its two-tier taxonomy forward alongside a
five-case adapter set.

- Pro: one document holds the whole testing strategy, so a contributor reads one file instead of
  chasing ADR-0009 → ADR-0035 → ADR-0037 → this record.
- Con: supersession under `docs/adl/template.md` is for a decision that no longer holds, and every
  part of ADR-0009 still holds — the harness split, the traceability naming, the four presence
  cases. Superseding would discard a live decision to add to it, and would orphan the three records
  that already narrow or extend ADR-0009 by pointing at a Superseded parent.

### Option D — Put the fifth case only in the skills and agents, with no ADR

Edit `write-tests/SKILL.md`, `test-reviewer.md` and `code-reviewer.md` to demand the unit case, and
skip the record.

- Pro: cheapest, and it lands directly in the three files an author and a reviewer actually read —
  an ADR reaches them only through those files anyway.
- Con: the four cases are ADR-0009's, and three copies restating them is exactly why they hold. A
  skill that adds a fifth case it did not get from an ADR puts the derived copy above its source:
  the next reader of ADR-0009 sees four cases and has no way to learn there are five, and the first
  drift between the three copies has no authority to settle it. This option is not rejected as
  work — it is the required propagation of whichever rule is decided, and is tracked as its own
  `workflow` change.

### Option E — Mandate a unit case for every adapter role, numeric or not

Drop the conditional trigger: every role gets a unit case, so there is no boundary to misjudge.

- Pro: removes Option A's second Con entirely. No author has to decide whether their role is in
  scope, and no reviewer has to adjudicate it.
- Con: `unit_of_measurement` is meaningless on the seven non-numeric roles — `charger_status`,
  `low_tariff`, `car_home`, `home_day_external`, `departure_external`, `notification_target` and
  `sun`. Their meaning case is the unmapped-raw-state case ADR-0009 already mandates. Requiring a
  ritual assertion on roles where the attribute carries no information trains reviewers to wave
  the case through, which erodes it on the roles where it is load-bearing.

### Option F — Enforce it mechanically: one parametrised conformance test over the factory's role table

Rather than a per-role obligation, a single table-driven test that walks every wired numeric role
and asserts its declared unit set and out-of-set behaviour.

- Pro: cannot be forgotten, and a new role is covered the moment it is wired — the blast-radius
  problem solved by construction rather than by remembering.
- Con: it needs a machine-readable per-role unit set, which does not exist: `entity-catalog.md`'s
  unit column is prose in a markdown table, and the adapters encode their target unit only in
  `_PowerReadAdapter._target_unit`, on four roles. A single generic assertion also cannot express
  the three different behaviours already in play (convert, assume-and-warn, reject), so it would
  either encode them as per-role exceptions — a lookup table by another name — or flatten them and
  assert something weaker than each role's real contract.

## Decision

**Option A**, as an **extension** of ADR-0009 rather than a supersession — the same relationship
ADR-0037 has to ADR-0009's tier taxonomy. ADR-0035 stands in the third of these relationships,
narrowing ADR-0009's unmapped-raw-state case rather than extending it; what all three share, and
what matters here, is that none of them is a supersession. ADR-0009's four cases, its harness
split and its requirement-traceability naming are untouched and remain authoritative; this record
adds a fifth case to the mandated coverage set and nothing else. Option C is rejected on its Con:
superseding a decision that still holds in every part would orphan the records already pointing
at it.

**The fifth mandated case.** For every adapter role whose reading is **numeric** and whose
`entity-catalog.md` unit column **names a unit**, the role's tests must:

1. **State the expected unit set** — which source units the role's mapped entity is expected to
   report, named in the test or its docstring, not left to be inferred from the adapter's code.
   (Note this is an expectation about the *source*, not a promise about handling: a role whose
   behaviour is "used as-is" still has an expected set, and clauses 2 and 3 are exactly what
   record that a reading outside it is used anyway.)
2. **Cover a foreign unit** — a reading whose `unit_of_measurement` is present and outside that
   set, asserting the role's actual behaviour.
3. **Cover an absent unit** — a reading with no `unit_of_measurement` attribute, asserting the
   role's actual behaviour.

**The obligation is discharged per adapter class, not per role.** Unit handling lives on the
adapter, and several roles share one: `net_power`, `charger_power` and `solar_power` are all
`PowerWattReadAdapter`; `grid_voltage`, `ev_soc`, `ev_battery_capacity` and `solar_forecast` are
all `NumericReadAdapter`; `charger_current` and `vehicle_charge_limit` are both
`NumericReadWriteAdapter`; `monthly_peak_external` alone is `PowerKilowattReadAdapter`. Two cases
per role would mean twenty near-identical assertions against four classes, which is ritual rather
than coverage. So clauses 2 and 3 are satisfied for a role by cases on **the class through which
that role reads**, and a role is conforming when its class has them.

**And a subclass that does not override `read` inherits its base class's clauses 2 and 3.**
`NumericReadWriteAdapter` subclasses `NumericReadAdapter` and adds only `write`; its read path is
the inherited method, so cases on it would assert the code the base class's cases already assert.
Demanding them anyway would be the same ritual this rule just rejected, one level down. The
obligation attaches to the class that *defines* the read, and the follow-up below is counted
accordingly.

Clause 1 stays per role: the expected unit set is a property of the role, and two roles on one
class may legitimately have different ones — at which point the shared class no longer expresses
both, and the divergence is itself the finding. A reviewer's question is therefore "which class
defines this role's read, does that class have the two cases, and does this role state its unit
set", and the follow-up below is counted in classes for cases 2-3 and in roles for clause 1.

Cases 2 and 3 are separate because the two are treated differently wherever the question has been
decided: ADR-0038's whole carve-out turns on the absent case specifically, and a single combined
"bad unit" test would hide that distinction for every role that inherits it.

**The behaviour asserted is the role's own, and this record does not prescribe it.** A role may
convert, assume-and-warn, reject, or use the value as-is; the obligation is that the suite says
which, in a test that fails if it changes. Deciding which is right for a given role is a
domain/business rule under CLAUDE.md's second carve-out — `entity-catalog.md`'s business, or that
role's own ADR, as ADR-0038 was for the power four. **Absent a role-specific decision, the
expected unit set is the catalogued unit alone** — `entity-catalog.md`'s unit column names what the
source entity is expected to report, and nothing has yet widened that to a set. Clause 1 is then
discharged by naming it, and clauses 2 and 3 pin today's behaviour against it. This is what stops
clause 1 blocking on a decision that has not been made: a role is never waiting on its unit set to
be *decided* before its tests can be written, only on the catalog stating one. Option A's first
Con is accepted with a mitigation rather than denied: a test pinning "used as-is" **must say in
its docstring that it records an undecided contract, not a safe one**, so the passing case reads
as a marker rather than as a clearance. That is the whole difference between this rule making the
gap visible and it papering over the gap.

**Grounded, not aspirational.** Two tests in the suite today already satisfy clauses 2 and 3 for
`PowerKilowattReadAdapter`, and they are the model the rule is generalised from:

| Clause | Existing test |
|---|---|
| Absent unit | `tests/adapters/test_numeric.py::test_power_kilowatt_adapter_missing_unit_returns_none` |
| Foreign unit | `tests/adapters/test_numeric.py::test_power_kilowatt_adapter_non_power_unit_returns_none` |

`PowerWattReadAdapter`'s `::test_power_watt_adapter_absent_unit_assumes_watts` and
`::test_power_watt_adapter_present_non_power_unit_is_rejected` are the same pair for the
assume-and-warn behaviour, written under ADR-0038. Between them those two classes carry all four
power roles, so — the obligation being per class — adopting this rule costs those roles no new
*cases*. Clause 1 is a separate matter even there: none of those four tests names an accepted
source-unit set outright, and ADR-0038 is the role-specific decision that supplies it, so what
those roles owe is a sentence in a docstring rather than a test. The cases themselves are the
expensive half, and their entire cost falls on `NumericReadAdapter`, which defines the read for
the other six roles and has no such tests.

**The in/out boundary, stated so a test author cannot reasonably get it wrong.** The phrase
"carrying no unit at all" has two readings and they land on opposite sides:

- **A source entity that reports no `unit_of_measurement` — IN, and mandatory.** This is clause 3
  above, not an exemption from it. A role does not escape the case because the entity a test happens
  to seed is unitless; that reading *is* the case. `test_reads_native_float` seeding a bare number
  is the situation this record exists to stop being the only unit-shaped coverage a role has.
- **A role whose catalogued unit column is `—` — OUT.** A numeric role that is genuinely
  dimensionless (a bare count or ratio, with `—` in `entity-catalog.md`'s unit column) has no
  expected unit set to state, so clauses 1–3 have no content. No such role exists today; the
  exemption is written down because the first one to be added will otherwise be argued about. It is
  conditional on the catalog: a role whose unit column is blank because nobody filled it in is **in
  scope**, and the correct response is to fill in the catalog, not to claim the exemption.

`%` is **in scope** — `ev_soc` and `vehicle_charge_limit`. The trigger is that the catalog names a
unit the source entity is expected to report, not that the quantity has a physical dimension. A
state-of-charge sensor reporting `kWh` is the same class of positive evidence of a mis-mapping as a
grid meter reporting `°C`, and nothing is gained by excluding it on a dimensional-analysis argument
a test author would have to relitigate. This is deliberately broader than a "physical unit"
trigger, which would leave the two percent-valued roles uncovered on a dimensional technicality.

**What the rule does not reach.**

- **Non-numeric roles** — `charger_status` (enum), `low_tariff`, `car_home`, `home_day_external`
  (bool), `departure_external` (time), `notification_target`, `sun`. Their mandated set stays at
  four cases, the fourth being the unmapped-raw-state case where it applies. Option E is rejected
  for wanting to extend it here anyway.
- **The write half of a read/write role.** `charger_current` and `vehicle_charge_limit` are covered
  by this rule on the value they *read*. What unit a written value is in, and whether the target
  entity's own unit should be checked before writing, is a distinct question this record leaves
  open — ADR-0038 already names it as follow-up for those two roles.
- **Entities this integration publishes.** A missing `unit_of_measurement` on an owned sensor is an
  entity-conformance defect, not an adapter-coverage one, and is tracked on its own. The rule binds
  the read boundary only.
- **The coordinator, end-to-end and scenario tiers.** Those tests seed their own readings, so the
  author's unit assumption is the test's unit assumption and no coverage rule can break that
  circularity. Only a test that drives a real adapter against a real `unit_of_measurement`
  attribute can, which is why the case is mandated at the adapter tier and nowhere else.
- **Runtime behaviour.** Nothing here obliges any adapter to change what it does, and a role whose
  tests pin "used as-is" is conforming under this record while remaining a live hazard under
  ADR-0038's follow-up.

Option F is rejected on its Con for now rather than on its merits — the table it needs does not
exist — and is recorded below as the shape to revisit if a machine-readable per-role unit set ever
lands. Option B is rejected because the runtime contract and the coverage obligation are
independent by ADR-0038's own statement, and the status quo's cost has already been paid once, in
production. Option D is not rejected at all: it is the required propagation of this decision, and
is tracked as its own `workflow` change.

## Consequences

- **One adapter class, carrying six numeric roles, is non-conforming the moment this is
  accepted** — `NumericReadAdapter`, which reads for `grid_voltage`, `ev_soc`,
  `ev_battery_capacity` and `solar_forecast` directly, and for `charger_current` and
  `vehicle_charge_limit` through `NumericReadWriteAdapter`'s inherited `read`.
  This is deliberate and is the point: the rule's value is that it names them. A `testing` issue
  to add clauses 2 and 3 to `NumericReadAdapter` — which defines the read both share — and
  clause 1's unit-set statement for each of the six roles, is follow-up this decision creates:
  **two new cases, not twelve**, plus six docstring sentences. That read path is unitless today,
  so both cases will pin "used as-is" and must carry the docstring the Decision requires.
- **The rule must be propagated to the three derived copies** before it binds anyone in practice:
  `.claude/skills/write-tests/SKILL.md`, `.claude/agents/test-reviewer.md` and
  `.claude/agents/code-reviewer.md` all restate the mandated set as four cases. That is a separate
  `workflow` change, filed and reviewed on its own — an ADR the derived copies do not reflect binds
  nothing, so until it lands this record is a statement of intent rather than an operating rule.
- **The ADL index gains a back-pointer on ADR-0009's row**, alongside the ones ADR-0035 and
  ADR-0037 already carry — per ADR-0037's stated convention that an extending record is reachable
  from its parent's row rather than only by reading to the end of the log.
- **ADR-0038's deferred question now has a test-side obligation attached.** Deciding the six
  non-power roles' unit sets was already follow-up there; after this record, a role whose unit set
  is decided gets its behaviour pinned by tests that already exist, so the decision lands as an
  assertion change rather than as new coverage.
- **Option F stays open as a later strengthening.** If a machine-readable per-role unit set ever
  exists — a declared `_expected_units` on each adapter, or a generated table from
  `entity-catalog.md` — a table-driven conformance test would subsume this obligation, make it
  unforgettable, and restore the per-role granularity this record trades away in making the
  obligation per class. Adopting it would *narrow* this record, not contradict it, and would need
  its own ADR to settle what the generic assertion is allowed to mean.
- **What becomes harder:** adding a numeric adapter role now requires stating its expected unit
  set — the catalogued unit, absent a role-specific decision widening it — and, if it introduces a
  new adapter class, giving that class the two cases. Previously a role could be wired, tested and
  merged without the question being asked at all. That is the intended cost, and it is the same
  cost ADR-0038 accepted at runtime.
- **What becomes easier:** a reviewer has a mechanical question to ask of any adapter diff —
  "which class defines this role's read, does that class have its two unit cases, and does this
  role state its expected unit set" — that does not require knowing the role's domain. The failure
  mode that shipped a kW-as-W read behind a green suite is no longer reachable without a
  reviewer actively accepting it.
- **Accepted before that class conforms**, on the same basis as ADR-0009 and ADR-0037: a
  coverage rule has to be settled before the work it governs is scheduled, and leaving it
  Proposed would make the propagation change and the test additions provisional.
