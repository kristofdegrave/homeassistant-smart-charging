# ADR-0033: External monthly-peak mapping on the CapTar-gated step — `captar` gains a mapping half

Date: 2026-09-01
Status: Proposed

## Context

[ADR-0030](0030-external-monthly-peak-sensor.md) added an optional adapter role,
`ROLE_MONTHLY_PEAK_EXTERNAL`, for a smart-meter/DSO capacity-tariff peak sensor, and
[ADR-0032](0032-external-monthly-peak-precedence.md) settled how that reading combines with the
internally tracked monthly peak demand. ADR-0030 deliberately left one question open and named it:
the config-flow home for the mapping — "a new ungated step, or a place reachable regardless of
`CONF_CAPTAR_AVAILABLE`" — was deferred to the guided-config-flow use case
([UC12](../analysis/use-cases/UC12-configure-installation-through-guided-flow.md)) to resolve.
Until that question is answered the role has no way to be mapped at all, so the whole strand is
inert: ADR-0030's Consequences say as much when they leave the placement "to the
guided-config-flow use case to resolve, not decided here".

The natural home for the mapping is the `captar` step. That is where every other input to the same
clamp already lives: [ADR-0027](0027-config-flow-topic-step-structure.md)'s nine-step
topic-grouped model puts the four peak-protection thresholds and the `Power`-mode peak-protection
switch on `captar` (UC12 5b) — beside the `Captar`-mode cooldown, which is the step's one field
that tunes the mode rather than the clamp — all gated on `CONF_CAPTAR_AVAILABLE`, on the reasoning
that gating a clamp's thresholds but not its on/off switch would split one topic across two steps.
The external monthly-peak reading is an operand of that same clamp and, like the thresholds, has
no effect whatever while the CapTar capability is absent — R3's clamp does not run at all in that
case, so the reading has no consumer.

Placing it there collides with a specific sentence in ADR-0027, which is **Accepted, shipped and
test-pinned**. Its point 3 reads:

> `power` and `captar` are threshold-only and must be skipped in reconfigure mode, while every
> other step has a mapping half and must be shown (subject to its capability gate). Each such row
> therefore carries a gate conjoining its capability condition with "this flow mode renders a half
> this step has".

Two of ADR-0027's Consequences restate the same enumeration — the schema-fragment consequence
("with `power` and `captar` threshold-only and no step mapping-only") and the test-obligation
consequence ("cover the reconfigure subset explicitly (that `power` and `captar` never appear)").
`custom_components/smart_charging/config_flow.py` implements it: `CONFIG_TABLE`'s `STEP_CAPTAR`
row conjoins `flow._mode is not FlowMode.RECONFIGURE` into its gate alongside the capability test.
Two tests assert the enumeration by name —
`tests/test_config_flow.py::test_uc12_1a_reconfigure_never_shows_power_or_captar` and
`::test_adr0027_point3_power_and_captar_rows_are_gated_off_in_reconfigure` — and two more encode
it structurally without naming it, including the sixteen-combination reconfigure traversal matrix
(`::test_r20_ac2_reconfigure_traverses_exactly_uc12s_mapping_halves`) that discharges ADR-0027's
own "every capability combination traverses exactly the steps UC12 prescribes" obligation. Two
more sit outside the reconfigure walk altogether — one install-side, one asserting the mapping
fragment's absence as a module symbol. The Consequences below enumerate them, as a floor rather
than a closed list.

The collision is narrower than it first looks, and the distinction matters for what this ADR has
to change. Point 3 states two things: an abstract **rule** (each row's gate conjoins its
capability condition with "this flow mode renders a half this step has") and a concrete
**enumeration** of which steps that rule currently resolves to nothing for in reconfigure mode
(`power` and `captar`). The rule is a function of a step's schema halves; the enumeration is a
snapshot of what those halves happened to contain in August 2026. Give `captar` a mapping field
and the rule keeps working untouched — reconfigure renders mapping halves, `captar` now has one,
so its gate reduces to its plain capability test — while the enumeration becomes false. `power` is
unaffected either way: it still has no mapping half and still never appears in reconfigure.

[ADR-0001](0001-use-architecture-decision-records.md)'s immutability rule forbids editing an
Accepted ADR's Context/Decision/Consequences to reflect a change of fact, so correcting ADR-0027's
sentence in place is not available.

That leaves two recording shapes, and which one applies is a force here rather than an open choice
— the same framing ADR-0027 itself used when it set out why replacing ADR-0025 had to be a
supersede rather than an edit. ADR-0001 knows only the full form: a new ADR replaces an old one
whole, and the old one's Status becomes `Superseded by ADR-NNNN`. That form fits when the
successor can stand alone in the predecessor's place — as ADR-0027 could, because ADR-0025's
reasoning was written in terms of step identities that had ceased to exist. It does not fit here.
This ADR does not replace ADR-0027; it *depends* on it, and specifically on the very point it
corrects — point 3's rule is the mechanism that makes the new placement work, and points 1, 2, 4
and 5 are untouched. Retiring ADR-0027 whole would therefore either leave the nine-step structure
recorded nowhere current, or oblige this record to restate it verbatim for no gain, and would mark
as historical a decision the shipped code still implements. So the applicable form is a **partial
supersede**: the enumeration is replaced, the record that contains it stays Accepted and current.
That shape is not in ADR-0001's vocabulary, and adopting it is a consequence this ADR owns rather
than a mechanism it can cite.

The question this ADR answers is therefore: **where does the external monthly-peak mapping live in
the nine-step flow, and what does ADR-0027 point 3 owe as a result?**

The forces are otherwise those ADR-0027 already recorded and are not re-derived: the fixed step
order and complete traversal, the data/options split at a single terminal call
([ADR-0005](0005-config-entry-structure-and-interval.md) — mappings are data-bucket, thresholds
are options-bucket), the one-table-per-flow structure with a shared dispatcher, and UC12's
postconditions that no field of an absent capability is ever presented and that a new capability
is appended without touching another step.

## Considered options

### Option A — Leave the mapping out of the guided flow entirely

Keep ADR-0027 point 3 exactly as written by not giving the role a config-flow home at all: the
`ROLE_MONTHLY_PEAK_EXTERNAL` key exists in `const.py`, but nothing in the flow ever maps it.

- Pro: Zero change to any shipped decision, table row, schema fragment, translation string or
  test — the baseline every other option pays its cost against. It also defers a placement
  question that a later, larger config-flow rework might answer more cheaply.
- Con: It makes ADR-0030's role permanently unreachable. The flow is this integration's only
  entity-mapping mechanism ([ADR-0003](0003-hardware-abstraction-adapters.md)); there is no YAML
  or service path a household could use instead, so an unmapped role means the reported
  under-clamping failure mode ADR-0030 and ADR-0032 exist to close stays open for every install.
  It leaves two Accepted ADRs describing a feature no user can switch on, which is worse
  documentation debt than the sentence this ADR would otherwise narrow.

### Option B — Put the mapping on an existing ungated step (`grid`)

Add the field to the always-shown `grid` step, whose other fields are the net-power, grid-voltage
and low-tariff mappings — the closest topic match among the five ungated steps, and literally the
"place reachable regardless of `CONF_CAPTAR_AVAILABLE`" ADR-0030 floated.

- Pro: Point 3's enumeration stays true verbatim, so no supersede, no table-row change, and
  neither named test moves. The field is reachable on every install path, so a household that
  declares CapTar absent today and turns it on at a later reconfigure already has the mapping in
  place instead of having to supply it in the same sitting.
- Con: It presents, on every single install, a field that provably does nothing for the majority
  of them — the clamp it feeds does not run without CapTar (R3, R18) — which is exactly the
  outcome UC12's postcondition ("no field of an absent capability is ever presented"), R20 AC3 and
  R18 AC5 exist to prevent, and which UC12 5b changed the previous step model specifically to stop
  doing for the peak-protection fields. It splits the peak-protection topic across two steps, the
  same defect ADR-0027 cited when it refused to leave `power_respect_peak` on the `power` step.
  And it forces a carve-out in `entity-catalog.md`'s CapTar-dependent-rows note, which would then
  have to say this one CapTar-dependent field is presented ungated while its six siblings on that
  step are not.

### Option C — A new ungated single-field step

Append (or insert) a tenth step whose only content is the external monthly-peak mapping, ungated
so every install reaches it.

- Pro: Uses the extensibility affordance ADR-0027's Option C was chosen for — one table row plus
  one step method, no existing step touched — and keeps `captar` threshold-only, so point 3's
  enumeration survives untouched. It also gives the mapping a screen whose title can explain the
  DSO-sensor concept at length without crowding another step.
- Con: A step whose membership rule is "this one optional field" is not a topic, which is
  precisely the shape ADR-0027 abolished when it deleted the `mappings`/`thresholds` catch-alls
  and required every step's membership rule to be stateable. Being ungated it inherits Option B's
  real defect in full — every non-CapTar install gets a whole screen it cannot use — while adding
  a screen to a flow that is already nine deep, and growing the sixteen-capability traversal
  matrix by another position for no gating benefit. Making it *gated* instead would collapse it
  into Option E with an extra step id for one field.

### Option D — Put the mapping on `captar`, but keep the step out of reconfigure

Add the field to the `captar` step's schema for the install flow only, leaving `CONFIG_TABLE`'s
`STEP_CAPTAR` gate and both named tests exactly as they are, so the mapping is asked once at
install and never shown again.

- Pro: The field lands on the right topic step under the right capability gate, and the shipped
  gate row, its two tests and point 3's enumeration all stay literally correct — the smallest diff
  of any option that actually makes the role mappable.
- Con: It would be the only mapping in the entire flow a user could never repair. Re-pointing a
  mapping after a DSO integration renames or replaces its peak entity is the exact job UC12 1a's
  reconfigure flow exists for, and an external sensor owned by a third-party integration is *more*
  likely to churn than most, not less. Preserving the enumeration would also make the gate
  arbitrary rather than derived: point 3's rule says a step is skipped in reconfigure because it
  has no half to render, and under this option `captar` would be skipped despite having one — the
  rule and the code would disagree, which is a worse record than narrowing the enumeration
  honestly.

### Option E — Put the mapping on `captar` and let the step gain a mapping half

Add the field to the `captar` step under the existing `CONF_CAPTAR_AVAILABLE` gate, accept that
`captar` now has a mapping half, and drop the reconfigure conjunct from its table row so it
appears in the reconfigure flow whenever CapTar is present — showing that one field, since none of
its thresholds belong to a mapping half. Point 3's *enumeration* is superseded; its rule is not.

- Pro: The field sits with every other input to the same clamp, under the same gate, so the
  peak-protection topic stays whole and no non-CapTar install is ever offered a field that does
  nothing (R20 AC3 states the rule directly; R18 AC5 and UC12's postcondition apply it to this
  step). It is repairable at reconfigure like every other mapping. Crucially, it needs no new
  mechanism: point 3's own gate rule already yields the right answer once `captar` has a mapping
  half, so the change is to one row's evaluated conditions and one new schema fragment, not to how
  gating works.
- Con: It falsifies a sentence in an Accepted, shipped ADR, which costs a superseding record —
  and one of a shape ADR-0001's vocabulary does not currently have, per Context — plus a
  `CONFIG_TABLE` change, a new `CAPTAR_MAPPING_SCHEMA`, mode branching and prefill in
  `async_step_captar`, re-worded `captar` translation strings that must now read correctly in a
  reconfigure context as well as an install one and a translation-parity fixture updated to match,
  and the rewrite of every test that spells the enumeration out — two named after it, the
  sixteen-combination reconfigure traversal matrix, the mapping-halves walk-through and an
  install-side schema-equality test — plus a mapping-fragment roster that has to grow without any
  test going red to say so.
  It also removes a property a reader could previously rely on — that a step's mapping-half status
  is fixed by its topic — since a step can now *acquire* a mapping half, meaning any future field
  addition has to re-ask the reconfigure question rather than assume the answer.

## Decision

**Option E.** The external monthly-peak mapping is presented on the CapTar-gated `captar` step,
and `captar` thereby has a mapping half: it appears in the reconfigure flow whenever
`CONF_CAPTAR_AVAILABLE` is set, rendering that single field.

Option A is rejected because the cost it avoids is a sentence in a record, while the cost it
accepts is a shipped role no household can ever use — it would leave ADR-0030 and ADR-0032
describing an inert feature. Options B and C both buy point 3's literal survival with the defect
UC12 5b explicitly changed the step model to remove: presenting a CapTar-only field to installs
that have no CapTar. C pays that price twice over, since a single-field step is also the
un-stateable membership rule ADR-0027 abolished the catch-alls to be rid of, and a *gated* version
of C is Option E with a gratuitous extra step id. Option D is the closest call — it lands the
field in the right place for the smallest diff — but its own Con is decisive on both counts: it
makes the flow's only unrepairable mapping out of the one most likely to need repair, and it would
preserve the enumeration only by putting the code in contradiction with the rule the same point
states.

What keeps E's cost confined — not small, but confined to one clause of the record and to the code
and tests that spell that clause out — is the distinction drawn in the Context. **This ADR
supersedes ADR-0027 point 3's enumeration, not its rule.** The rule — each row's gate conjoins its
capability condition with "this flow mode renders a half this step has" — is correct as written
and already generalizes to this case without amendment: reconfigure renders mapping halves,
`captar` now has one, so its gate reduces to its plain capability test, and `power`, which still
has none, still evaluates false in reconfigure exactly as before. Only the concrete claim that
`power` **and** `captar` are the threshold-only pair is narrowed, to `power` alone. Two
Consequences of ADR-0027 restate that same enumeration — the schema-fragment line and the
test-obligation line — and are narrowed by the same act, in the same way, for the same reason.
Everything else in ADR-0027 stands unchanged: the table-driven linear structure, points 1, 2, 4
and 5, and the whole of its remaining Consequences.

The recording shape follows from the force stated in Context, and what remains to decide is only
where the pointer to this record goes. It goes in the ADL index, in the *title* cell of ADR-0027's
row, leaving that row's Status cell verbatim `Accepted` — so no row ever carries a status the
ADR's own header does not. `docs/adl/README.md` is a navigational index rather than an ADR body
and is not covered by the immutability rule, but it is not a place to invent status vocabulary
either.

This also answers **ADR-0030's explicitly deferred question**. Of the two homes it named, neither
is chosen: the answer is a *gated* placement on the existing `captar` step rather than "a new
ungated step" or "a place reachable regardless of `CONF_CAPTAR_AVAILABLE`". The consequence
ADR-0030 was guarding against — the role being unmappable for a non-CapTar install — is accepted
deliberately, because R3's clamp does not run without the CapTar capability, so on such an install
the role has no consumer and a mapping for it would be inert. This ADR settles the structural half
only; the resulting user-visible behaviour belongs in UC12, which owes a new alternate flow for it
(6a) as part of the analysis work named in the Consequences.

## Consequences

- **ADR-0027 point 3's enumeration is narrowed; its rule and Status are untouched.** ADR-0027
  keeps Status `Accepted` and its body is not edited. From here, "`power` and `captar` are
  threshold-only" reads as "`power` is threshold-only", and the two Consequences restating it —
  the schema-fragment line ("with `power` and `captar` threshold-only and no step mapping-only")
  and the test-obligation line ("that `power` and `captar` never appear") — are read the same
  narrowed way. `power` remains the flow's only threshold-only step and still never appears in
  reconfigure. `docs/adl/README.md` gains a row for this ADR and annotates the *title* cell of
  ADR-0027's row to point at it, in this same change, leaving that row's Status cell verbatim
  `Accepted`. That pointer only reaches a reader who arrives via the index, and two paths bypass
  it: `config_flow.py`'s own `CONFIG_TABLE` comment cites point 3 inline, and ADR-0030 links
  straight to ADR-0027's file. Only the first is compensated — re-pointing that comment block is
  part of the work named in the next Consequence, not a cosmetic tidy. The second is an accepted
  residual cost: a reader arriving from ADR-0030, or from the design and plan documents that cite
  ADR-0027, lands on an unmarked point 3, and nothing short of editing ADR-0027 itself would
  change that.
- **No table row carries a conjoined gate any more, and `power` alone carries a flow-mode one.**
  `CONFIG_TABLE`'s `STEP_CAPTAR` row drops its `and flow._mode is not FlowMode.RECONFIGURE`
  conjunct and reduces to `bool(flow._answers.get(CONF_CAPTAR_AVAILABLE))`, joining
  `solar`/`deadline`/`notifications` as a plain capability gate; the comment block above
  `CONFIG_TABLE` that spells out the old pairing must be re-worded with it. `STEP_POWER`'s row is
  unchanged — it was never a conjunction, since `power` has no capability gate to conjoin with —
  and it is now the sole place where the flow-mode half of point 3's rule does any work. Point 3's
  rule is a conjunction in the general case; after this decision no row is a case where both
  halves are non-trivial at once.
- **`async_step_captar` gains mode branching and prefill.** Its docstring today states it needs
  neither `self._mode` branching nor `_maybe_prefill` in its own body, and its body has neither —
  correct while the step was install-only, wrong from here. It must acquire both, exactly as every
  other step with a mapping half already has. The prefill half is not cosmetic: an optional
  mapping rendered without suggested values on a reconfigure form is silently dropped on save, a
  bug class this repo already carries a named regression test for. Two docstrings go stale at the
  same moment without their logic changing: `_async_finish`'s, which asserts neither `power` nor
  `captar` is reachable in reconfigure mode — the terminal split is bucket-driven, so the code
  stays correct while the reasoning it records does not — and `async_step_reconfigure`'s, which
  restates the two-row skip directly.
- **The options flow is unaffected and must stay that way.** The new field is data-bucket
  (ADR-0005) and the options flow writes options only (ADR-0027 point 4), so `OPTIONS_TABLE`'s
  `captar` row keeps rendering the threshold half alone. Point 3's rule already delivers this —
  the options flow renders no mapping halves for any step — but it is the one place an implementer
  could plausibly over-apply this decision, so it is stated rather than left to inference.
- **A `captar` mapping fragment reappears, under a different name and with different contents.**
  ADR-0027 only removed `_captar_mapping_schema`'s `include_ev_soc` parameter; the implementation
  went further and dissolved the fragment outright once the EV state-of-charge field moved to
  `vehicle`, leaving it with nothing to carry, and a test now pins its absence. What returns is
  not that symbol: the shipped convention is that mapping halves are module-level
  `*_MAPPING_SCHEMA` constants (`GRID_MAPPING_SCHEMA`, `SOLAR_MAPPING_SCHEMA`,
  `DEADLINE_MAPPING_SCHEMA`) while only threshold halves are `_x_threshold_schema(defaults)`
  functions, because only they take stored defaults. A mapping half carrying one optional entity
  selector takes none, so this is `CAPTAR_MAPPING_SCHEMA`, a constant. That is also why the test
  pinning the old symbol's absence needs no change: it asserts `_captar_mapping_schema` is gone,
  and it stays gone. The new fragment is a different symbol under the convention that applies to
  it, not a reversion. Its unit contract and unavailable/unknown handling are ADR-0030's
  obligations and are not re-decided here.
- **Withdrawing CapTar treats the mapping and the thresholds differently, and that needs no new
  rule.** The mapping is a data-bucket field and the step's six existing values — the four
  peak-protection thresholds, the `Power`-mode peak-protection switch, and the `Captar`-mode
  cooldown — are options-bucket fields (ADR-0005), so declaring CapTar absent at a later
  reconfigure drops the mapping from the data bucket under UC12 1a's existing rule for any
  withdrawn capability's mapping fields, while the thresholds simply lie dormant and resume on
  exactly their stored values if the capability returns. Re-declaring CapTar present therefore
  requires re-mapping the sensor. This asymmetry falls out of the buckets the two field kinds
  already live in; this ADR neither invents nor needs a special case for it. `entity-catalog.md`'s
  CapTar-dependent-rows note is where that asymmetry belongs — it covers only the options-bucket
  values today, and extending it is one of the analysis edits named below, on the model of the
  deadline note's existing carve-out for the external home-day mapping.
- **At least five tests encode the superseded enumeration; all are rewritten, none deleted.** Two
  assert it by name — `test_uc12_1a_reconfigure_never_shows_power_or_captar` and
  `test_adr0027_point3_power_and_captar_rows_are_gated_off_in_reconfigure` — in their names,
  docstrings and bodies. Two more encode it structurally in the *reconfigure* walk: the
  sixteen-combination reconfigure matrix
  `test_r20_ac2_reconfigure_traverses_exactly_uc12s_mapping_halves`, whose expected-step list
  never appends `STEP_CAPTAR` and so fails eight of its sixteen parametrisations, and
  `test_uc12_1a_reconfigure_shows_mapping_halves_only`, which walks every capability present and
  asserts `vehicle` is followed directly by `solar`. One sits outside the reconfigure walk
  entirely and is easy to miss for that reason:
  `test_uc12_captar_step_is_threshold_only_no_ev_soc` asserts on the **install** flow that the
  step's rendered keys equal the threshold schema's exactly, which fails as soon as the step
  renders a mapping field too — every other step extends its mapping half with its threshold half
  on install — and takes the test's own name with it. The reconfigure walk helper's docstring and
  the section-header comment above the `power`/`captar` cases restate the enumeration as well.
  The count is a floor, not a total, and the sweep it starts must look for two different failure
  shapes. The loud one is an assertion that goes red: any test fixing `captar`'s exact schema keys
  or an exact step sequence. The quiet one is a roster that must *grow* — `_ALL_MAPPING_FRAGMENTS`
  enumerates every mapping half the flow has, and omitting the new constant there fails nothing at
  all; the invariants driven off that roster simply stop covering the new field. Given that this
  decision turns on a step *acquiring* a mapping half, a fixture that silently under-covers the
  acquired one is the more dangerous of the two. Of these, the reconfigure matrix is the
  substantive test — it discharges the reconfigure third of ADR-0027's "every capability
  combination traverses exactly the steps UC12 prescribes" obligation (install and options have
  their own matrices). The `power` half of what the named pair protects is
  still required — nothing here weakens it, and it is now the *only* coverage of the flow-mode
  half of point 3's rule, so losing it would leave that rule untested. Each of the two becomes a
  `power`-only test under a name that no longer claims `captar`; the matrix and the walk-through
  gain `captar` in their expected reconfigure sequence whenever CapTar is present, rendering the
  mapping field alone. New coverage is owed for the reconfigure prefill of that field, since an
  unprefilled optional mapping is the silent-drop bug class named above. Per
  [ADR-0009](0009-testing-strategy.md) the traversal cases are HA-harness tests and the gate case
  is plain pytest, matching how the existing tests are already split. Naming and writing them is
  the implementation spec's job, not this ADR's.
- **`captar`'s translation block must read correctly in two contexts.** ADR-0027 requires each
  step's shared `config.step.*` block to work for both install and reconfigure. `captar`'s title
  and description are written today for a threshold-only screen and would be wrong above a
  single-mapping reconfigure form, so `strings.json`, `translations/en.json` and
  `translations/nl.json` need re-wording plus a label and description for the new field. The
  translation-parity fixture must move with them: it hard-codes the `captar` step's config-flow
  field set as the threshold schema's keys alone, so adding the label without updating that entry
  fails the orphaned-field parity check. The fixture's own anti-vacuity guards are keyed on step
  ids and are not implicated: this decision adds a field to an existing step, not a step. The
  fixture's options-side entry for `captar` correctly stays threshold-only, which is the same
  invariant as the options-flow Consequence above, seen from the fixture side.
- **No config-entry migration and no `VERSION` bump.** The change adds one optional data-bucket
  key that entries created earlier will not have; ADR-0030's role is absent at the factory level
  when unmapped, which is exactly the state such an entry is already in. No existing key changes
  name, type or bucket.
- **ADR-0030's deferred placement question is closed** — gated, on the `captar` step. The
  remaining open work in that strand is the analysis text and then the implementation spec, which
  owns the table row, the fragment, the step method, the translations and the test rewrite named
  above. Two analysis edits are specifically owed because each currently asserts the superseded
  enumeration as present fact: UC12 states that `captar` and `power` are both absent from the
  reconfigure flow, in its flow narrative, its diagram note and its Requirements-satisfied section,
  and must instead describe `captar`'s mapping half; and R18 AC5's list of fields the CapTar-gated
  step
  presents is a closed enumeration that does not yet include this mapping. A third is owed for
  completeness rather than correction: `entity-catalog.md`'s CapTar-dependent-rows note must gain
  the data-bucket mapping beside the options-bucket values it already covers, and with it the
  withdrawal asymmetry described above.
- **What becomes harder.** A reader can no longer infer a step's reconfigure behaviour from
  whether it is capability-gated: `captar` is capability-gated *and* present in reconfigure, while
  `power` has no capability gate at all *and* is absent from it — the two properties are now
  visibly independent. Point 3's rule is the only reliable way to answer the question, and it must
  actually be applied rather than pattern-matched. Relatedly, mapping-half status is now
  demonstrably a property a step can acquire, so any future field added to a threshold-only step
  has to re-ask whether that step now belongs in the reconfigure walk.
- **A partial supersede is a shape ADR-0001 does not have, and this record does not legislate
  one.** ADR-0001's vocabulary has only the whole-record form, and this is the first ADR to
  replace one clause of a still-current decision. What was done here is described rather than
  prescribed, so a future ADR facing the same force has a worked example to follow: the narrowing
  ADR states plainly which clause it replaces and which reasoning survives, the narrowed ADR keeps
  its Status and its body untouched, and the ADL index carries the pointer in the narrowed row's
  title cell rather than its status cell. Turning that into a project-wide convention — amending
  ADR-0001's status vocabulary, and binding future contributors to it — is a separate structural
  decision that this ADR neither makes nor should: it belongs in its own ADR against ADR-0001, and
  is named here as available follow-up rather than settled. What can be said without deciding
  anything is the boundary: a decision whose *reasoning* no longer holds is a full supersede, as
  ADR-0025 was, not a narrowing.
- **What this forecloses — and what it does not.** It does not establish that every optional
  mapping belongs on a capability-gated step. The reason this one does is specific and checkable:
  its sole consumer is a clamp that does not run when the capability is absent, so the field is
  inert without it. A future optional mapping whose consumer runs regardless belongs on an ungated
  step, and Option B's reasoning — not this decision — is the one that would apply to it.
