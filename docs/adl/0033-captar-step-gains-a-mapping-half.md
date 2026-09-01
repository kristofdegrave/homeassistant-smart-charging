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
inert: ADR-0030's Consequences say as much when they leave the placement "to the guided-config-flow
use case to resolve, not decided here".

The natural home for the mapping is the `captar` step. That is where every other input to the same
clamp already lives: [ADR-0027](0027-config-flow-topic-step-structure.md)'s nine-step topic-grouped
model puts the four peak-protection thresholds and the `Power`-mode peak-protection switch on
`captar` (UC12 5b), gated on `CONF_CAPTAR_AVAILABLE`, on the reasoning that gating a clamp's
thresholds but not its on/off switch would split one topic across two steps. The external
monthly-peak reading is an operand of that same clamp and, like the thresholds, has no effect
whatever while the CapTar capability is absent — R3's clamp does not run at all in that case, so
the reading has no consumer.

Placing it there collides with a specific sentence in ADR-0027, which is **Accepted, shipped and
test-pinned**. Its point 3 reads:

> `power` and `captar` are threshold-only and must be skipped in reconfigure mode, while every
> other step has a mapping half and must be shown (subject to its capability gate). Each such row
> therefore carries a gate conjoining its capability condition with "this flow mode renders a half
> this step has".

Two of ADR-0027's Consequences restate the same enumeration — the schema-fragment consequence
("with `power` and `captar` threshold-only and no step mapping-only") and the test-obligation
consequence ("cover the reconfigure subset explicitly (that `power` and `captar` never appear)").
`custom_components/smart_charging/config_flow.py` implements it: `CONFIG_TABLE`'s `STEP_CAPTAR` row
conjoins `flow._mode is not FlowMode.RECONFIGURE` into its gate alongside the capability test, and
two tests assert it by name —
`tests/test_config_flow.py::test_uc12_1a_reconfigure_never_shows_power_or_captar` and
`::test_adr0027_point3_power_and_captar_rows_are_gated_off_in_reconfigure`.

The collision is narrower than it first looks, and the distinction matters for what this ADR has to
change. Point 3 states two things: an abstract **rule** (each row's gate conjoins its capability
condition with "this flow mode renders a half this step has") and a concrete **enumeration** of
which steps that rule currently resolves to nothing for in reconfigure mode (`power` and `captar`).
The rule is a function of a step's schema halves; the enumeration is a snapshot of what those halves
happened to contain in August 2026. Give `captar` a mapping field and the rule keeps working
untouched — reconfigure renders mapping halves, `captar` now has one, so its gate reduces to its
plain capability test — while the enumeration becomes false. `power` is unaffected either way: it
still has no mapping half and still never appears in reconfigure.

[ADR-0001](0001-use-architecture-decision-records.md)'s immutability rule forbids editing an
Accepted ADR's Context/Decision/Consequences to reflect a change of fact, so correcting ADR-0027's
sentence in place is not available. The question this ADR answers is therefore: **where does the
external monthly-peak mapping live in the nine-step flow, and what does ADR-0027 point 3 owe as a
result?**

The forces are otherwise those ADR-0027 already recorded and are not re-derived: the fixed step
order and complete traversal, the data/options split at a single terminal call
([ADR-0005](0005-config-entry-structure-and-interval.md) — mappings are data-bucket, thresholds are
options-bucket), the one-table-per-flow structure with a shared dispatcher, and UC12's
postconditions that no field of an absent capability is ever presented and that a new capability is
appended without touching another step.

## Considered options

### Option A — Leave the mapping out of the guided flow entirely

Keep ADR-0027 point 3 exactly as written by not giving the role a config-flow home at all: the
`ROLE_MONTHLY_PEAK_EXTERNAL` key exists in `const.py`, but nothing in the flow ever maps it.

- Pro: Zero change to any shipped decision, table row, schema fragment, translation string or test —
  the baseline every other option pays its cost against. It also defers a placement question that a
  later, larger config-flow rework might answer more cheaply.
- Con: It makes ADR-0030's role permanently unreachable. The flow is this integration's only
  entity-mapping mechanism ([ADR-0003](0003-hardware-abstraction-adapters.md)); there is no YAML or
  service path a household could use instead, so an unmapped role means the reported under-clamping
  failure mode ADR-0030 and ADR-0032 exist to close stays open for every install. It leaves two
  Accepted ADRs describing a feature no user can switch on, which is worse documentation debt than
  the sentence this ADR would otherwise narrow.

### Option B — Put the mapping on an existing ungated step (`grid`)

Add the field to the always-shown `grid` step, whose other fields are the net-power, grid-voltage
and low-tariff mappings — the closest topic match among the five ungated steps, and literally the
"place reachable regardless of `CONF_CAPTAR_AVAILABLE`" ADR-0030 floated.

- Pro: Point 3's enumeration stays true verbatim, so no supersede, no table-row change, and neither
  named test moves. The field is reachable on every install path, so a household that declares
  CapTar absent today and turns it on at a later reconfigure already has the mapping in place
  instead of having to supply it in the same sitting.
- Con: It presents, on every single install, a field that provably does nothing for the majority of
  them — the clamp it feeds does not run without CapTar (R3, R18) — which is exactly the outcome
  UC12's postcondition ("no field of an absent capability is ever presented") and R18 AC5 exist to
  prevent, and which UC12 5b changed the previous step model specifically to stop doing for the
  peak-protection fields. It splits the peak-protection topic across two steps, the same defect
  ADR-0027 cited when it refused to leave `power_respect_peak` on the `power` step. And it forces a
  carve-out in `entity-catalog.md`'s CapTar-dependent-rows note, which would then have to say this
  one CapTar-dependent field is presented ungated while its five siblings are not.

### Option C — A new ungated single-field step

Append (or insert) a tenth step whose only content is the external monthly-peak mapping, ungated so
every install reaches it.

- Pro: Uses the extensibility affordance ADR-0027's Option C was chosen for — one table row plus one
  step method, no existing step touched — and keeps `captar` threshold-only, so point 3's
  enumeration survives untouched. It also gives the mapping a screen whose title can explain the
  DSO-sensor concept at length without crowding another step.
- Con: A step whose membership rule is "this one optional field" is not a topic, which is precisely
  the shape ADR-0027 abolished when it deleted the `mappings`/`thresholds` catch-alls and required
  every step's membership rule to be stateable. Being ungated it inherits Option B's real defect in
  full — every non-CapTar install gets a whole screen it cannot use — while adding a screen to a
  flow that is already nine deep, and growing the sixteen-capability traversal matrix by another
  position for no gating benefit. Making it *gated* instead would collapse it into Option E with an
  extra step id for one field.

### Option D — Put the mapping on `captar`, but keep the step out of reconfigure

Add the field to the `captar` step's schema for the install flow only, leaving `CONFIG_TABLE`'s
`STEP_CAPTAR` gate and both named tests exactly as they are, so the mapping is asked once at install
and never shown again.

- Pro: The field lands on the right topic step under the right capability gate, and the shipped gate
  row, its two tests and point 3's enumeration all stay literally correct — the smallest diff of any
  option that actually makes the role mappable.
- Con: It would be the only mapping in the entire flow a user could never repair. Re-pointing a
  mapping after a DSO integration renames or replaces its peak entity is the exact job UC12 1a's
  reconfigure flow exists for, and an external sensor owned by a third-party integration is *more*
  likely to churn than most, not less. Preserving the enumeration would also make the gate arbitrary
  rather than derived: point 3's rule says a step is skipped in reconfigure because it has no half
  to render, and under this option `captar` would be skipped despite having one — the rule and the
  code would disagree, which is a worse record than narrowing the enumeration honestly.

### Option E — Put the mapping on `captar` and let the step gain a mapping half

Add the field to the `captar` step under the existing `CONF_CAPTAR_AVAILABLE` gate, accept that
`captar` now has a mapping half, and drop the reconfigure conjunct from its table row so it appears
in the reconfigure flow whenever CapTar is present — showing that one field, since none of its
thresholds belong to a mapping half. Point 3's *enumeration* is superseded; its rule is not.

- Pro: The field sits with every other input to the same clamp, under the same gate, so the
  peak-protection topic stays whole and no non-CapTar install is ever offered a field that does
  nothing (UC12's postcondition, R18 AC5). It is repairable at reconfigure like every other mapping.
  Crucially, it needs no new mechanism: point 3's own gate rule already yields the right answer once
  `captar` has a mapping half, so the change is to one row's evaluated conditions and one new schema
  fragment, not to how gating works.
- Con: It falsifies a sentence in an Accepted, shipped ADR, which costs a superseding record, a
  `CONFIG_TABLE` change, a new `_captar_mapping_schema`, re-worded `captar` translation strings that
  must now read correctly in a reconfigure context as well as an install one, and the rewrite of two
  tests named after the very claim being narrowed. It also removes a property a reader could
  previously rely on — that a step's mapping-half status is fixed by its topic — since a step can
  now *acquire* a mapping half, meaning any future field addition has to re-ask the reconfigure
  question rather than assume the answer.

## Decision

**Option E.** The external monthly-peak mapping is presented on the CapTar-gated `captar` step, and
`captar` thereby has a mapping half: it appears in the reconfigure flow whenever
`CONF_CAPTAR_AVAILABLE` is set, rendering that single field.

Option A is rejected because the cost it avoids is a sentence in a record, while the cost it accepts
is a shipped role no household can ever use — it would leave ADR-0030 and ADR-0032 describing an
inert feature. Options B and C both buy point 3's literal survival with the defect UC12 5b
explicitly changed the step model to remove: presenting a CapTar-only field to installs that have no
CapTar. C pays that price twice over, since a single-field step is also the un-stateable membership
rule ADR-0027 abolished the catch-alls to be rid of, and a *gated* version of C is Option E with a
gratuitous extra step id. Option D is the closest call — it lands the field in the right place for
the smallest diff — but its own Con is decisive on both counts: it makes the flow's only
unrepairable mapping out of the one most likely to need repair, and it would preserve the
enumeration only by putting the code in contradiction with the rule the same point states.

What makes E cheap is the distinction drawn in the Context. **This ADR supersedes ADR-0027 point 3's
enumeration, not its rule.** The rule — each row's gate conjoins its capability condition with
"this flow mode renders a half this step has" — is correct as written and already generalizes to
this case without amendment: reconfigure renders mapping halves, `captar` now has one, so its gate
reduces to its plain capability test, and `power`, which still has none, still evaluates false in
reconfigure exactly as before. Only the concrete claim that `power` **and** `captar` are the
threshold-only pair is narrowed, to `power` alone. Two Consequences of ADR-0027 restate that same
enumeration — the schema-fragment line and the test-obligation line — and are narrowed by the same
act, in the same way, for the same reason. Everything else in ADR-0027 stands unchanged: the
table-driven linear structure, points 1, 2, 4 and 5, and the whole of its remaining Consequences.

Because the correction is confined to one clause, **ADR-0027's Status stays `Accepted`** and its
body is not touched (ADR-0001's immutability rule). A full `Superseded by` status would be actively
misleading — it would retire a decision whose mechanism this ADR relies on and re-affirms, and would
oblige a fresh record to restate the nine-step structure verbatim for no gain. The ADL index row for
ADR-0027 is annotated instead, since `docs/adl/README.md` is a navigational index rather than an
ADR body and is not covered by the immutability rule; ADR-0025's row was likewise updated when it
was superseded.

This also answers **ADR-0030's explicitly deferred question**. Of the two homes it named, neither is
chosen: the answer is a *gated* placement on the existing `captar` step rather than "a new ungated
step" or "a place reachable regardless of `CONF_CAPTAR_AVAILABLE`". The consequence ADR-0030 was
guarding against — the role being unmappable for a non-CapTar install — is accepted deliberately,
because R3's clamp does not run without the CapTar capability, so on such an install the role has no
consumer and a mapping for it would be inert. UC12 6a is the analysis-side counterpart of this
decision and describes the resulting user-visible behaviour; this ADR settles the structural half.

## Consequences

- **ADR-0027 point 3's enumeration is narrowed; its rule and Status are untouched.** ADR-0027 keeps
  Status `Accepted` and its body is not edited. From here, "`power` and `captar` are threshold-only"
  reads as "`power` is threshold-only", and the two Consequences restating it — the schema-fragment
  line ("with `power` and `captar` threshold-only and no step mapping-only") and the test-obligation
  line ("that `power` and `captar` never appear") — are read the same narrowed way. `power` remains
  the flow's only threshold-only step and still never appears in reconfigure. `docs/adl/README.md`
  gains a row for this ADR and annotates ADR-0027's row to point at it, in this same change, so a
  reader arriving at ADR-0027 finds the narrowing before reading point 3.
- **`power` becomes the only row with a conjoined gate.** `CONFIG_TABLE`'s `STEP_CAPTAR` row drops
  its `and flow._mode is not FlowMode.RECONFIGURE` conjunct and reduces to
  `bool(flow._answers.get(CONF_CAPTAR_AVAILABLE))`, joining `solar`/`deadline`/`notifications` as a
  plain capability gate; the comment block above `CONFIG_TABLE` that spells out the old pairing must
  be re-worded with it. `STEP_POWER`'s row is unchanged and is now the sole place where the
  flow-mode half of point 3's rule does any work.
- **A `captar` mapping fragment reappears, with different contents.** ADR-0027 dissolved
  `_captar_mapping_schema` when the EV state-of-charge field moved to `vehicle`; a fragment of the
  same name returns carrying exactly one optional entity selector for the external monthly-peak
  sensor. Its unit contract and unavailable/unknown handling are ADR-0030's obligations and are not
  re-decided here.
- **Withdrawing CapTar treats the mapping and the thresholds differently, and that needs no new
  rule.** The mapping is a data-bucket field and the five peak-protection thresholds are
  options-bucket fields (ADR-0005), so declaring CapTar absent at a later reconfigure drops the
  mapping from the data bucket under UC12 1a's existing rule for any withdrawn capability's mapping
  fields, while the thresholds simply lie dormant and resume on exactly their stored values if the
  capability returns. Re-declaring CapTar present therefore requires re-mapping the sensor. This
  asymmetry falls out of the buckets the two field kinds already live in; this ADR neither invents
  nor needs a special case for it. `entity-catalog.md`'s CapTar-dependent-rows note is where that
  asymmetry is documented.
- **The two named tests must be rewritten, not deleted, and the coverage they hold must grow.**
  `test_uc12_1a_reconfigure_never_shows_power_or_captar` and
  `test_adr0027_point3_power_and_captar_rows_are_gated_off_in_reconfigure` both assert the
  superseded enumeration in their names, docstrings and bodies. The `power` half of what they
  protect is still required — nothing here weakens it, and it is now the *only* case that exercises
  the flow-mode half of point 3's rule, so losing it would leave that rule untested. Each becomes a
  `power`-only test under a name that no longer claims `captar`, plus new positive coverage that
  `captar` is walked in reconfigure with CapTar present (rendering only the mapping field) and
  skipped with CapTar absent. Per [ADR-0009](0009-testing-strategy.md) the traversal case is an
  HA-harness test and the gate case is plain pytest, matching how the two existing tests are already
  split. Naming and writing them is the implementation spec's job, not this ADR's.
- **`captar`'s translation block must read correctly in two contexts.** ADR-0027 requires each
  step's shared `config.step.*` block to work for both install and reconfigure. `captar`'s title and
  description are written today for a threshold-only screen and would be wrong above a
  single-mapping reconfigure form, so `strings.json`, `translations/en.json` and
  `translations/nl.json` need re-wording plus a label and description for the new field.
- **No config-entry migration and no `VERSION` bump.** The change adds one optional data-bucket key
  that entries created earlier will not have; ADR-0030's role is absent at the factory level when
  unmapped, which is exactly the state such an entry is already in. No existing key changes name,
  type or bucket.
- **ADR-0030's deferred placement question is closed** — gated, on the `captar` step. The remaining
  open work in that strand is the requirement and use-case text (UC12 6a) and then the
  implementation spec, which owns the table row, the fragment, the translations and the test rewrite
  named above.
- **What becomes harder.** A reader can no longer infer a step's reconfigure behaviour from whether
  it is capability-gated: `captar` is capability-gated *and* present in reconfigure, while `power`
  has no capability gate at all *and* is absent from it — the two properties are now visibly
  independent. Point 3's rule is the only reliable way to answer the question, and it must
  actually be applied rather than pattern-matched. Relatedly, mapping-half status is now
  demonstrably a property a step can acquire, so any future field added to a threshold-only step has
  to re-ask whether that step now belongs in the reconfigure walk.
- **What this forecloses — and what it does not.** It does not establish that every optional mapping
  belongs on a capability-gated step. The reason this one does is specific and checkable: its sole
  consumer is a clamp that does not run when the capability is absent, so the field is inert without
  it. A future optional mapping whose consumer runs regardless belongs on an ungated step, and
  Option B's reasoning — not this decision — is the one that would apply to it.
