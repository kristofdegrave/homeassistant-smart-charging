# Post-mortem: four live-behaviour defects that a 38,000-line process did not catch

Date: 2026-09-11
Defects: #1005, #1006, #1007, #1008/#1009
Tracked by: epic #1011

This is a dated snapshot of reasoning about a shipped failure, not a normative rule and not a
source of truth for behaviour. See `CLAUDE.md`'s Document structure section for what
`docs/postmortems/` is and is not.

---

## Context

Four defects reached a running installation and were all found by a human looking at the
dashboard, despite a heavyweight documented process: analysis-first (`docs/analysis/`),
volatility-based design (`docs/design/`), ADRs (`docs/adl/`), implementation specs with TDD
plans (`docs/plans/`), an Opus reviewer agent on every artifact, a CI AI review loop, and a
two-harness test taxonomy (ADR-0009, ADR-0037).

**Scope of evidence.** `docs/` is 38,513 lines against 7,432 lines of product code
(`docs/plans/` alone is 24,409). ~1,002 merged PRs and 1,009 issues for one Home Assistant
integration. Every claim below is anchored to a file, commit, issue, or PR comment in this
repo, at the date it was read.

---

## 1. Where each defect had its chance

### #1005 — deadline never rolls over

The best-documented defect in the repo. It was *found four separate times before it shipped*,
and each time the process converted the finding into a document.

| Moment | What happened | Looked, or didn't? |
|---|---|---|
| **T1.4 authoring** (PR #350, 2026-07-23) | The plan's own section 6 contained a contradiction: prose said "no next-day rollover", while its worked example was `NOW = 22:00` / `DEADLINE = 06:00` commented *"next-day 06:00 — 8 hours remaining"*. The author noticed, reasoned it through in 20 lines of module docstring, and picked the prose. | **Looked, reasoned, wrong conclusion** |
| **T5.2 code review** (PR #373, 2026-07-23) | `code-reviewer` caught it once the engine was wired live and filed **#375**, which states the live symptom exactly: *"plug in at 22:00, departure deadline 06:00 … resolves `remaining_hours` as negative … fires `DeadlineUnreachableNotified` every cycle overnight."* | **Looked, correct conclusion** |
| **Epic #306 closed** (2026-07-27) | Epic closed COMPLETED while **#375, an open `development`-labelled child of it, was still open.** | **No one looked** |
| **PR #452 code review** (2026-08-02) | Found again, independently, filed as **#453**. | **Looked, correct conclusion** |
| **PR #510** (2026-08-04) | Changed **8 files, all under `docs/analysis/`**. Its own body: *"The **code fix** in `engines/deadline.py`'s `resolve_required_current` is a separate development task, blocked on this PR merging."* Its `analysis-reviewer` review repeats it verbatim in the Recommendation. Then: `Closes #453` / `Closes #375`. Both closed COMPLETED. | **Looked, said the right thing, then closed the tracking issues anyway** |
| **After merge** | No `development` issue was ever filed. Every issue created between 2026-08-04 and 2026-09-11 was searched for rollover / next-occurrence / deadline — nothing. The next mention is #1005, filed by the human who looked at the dashboard, 38 days later. | **No one looked** |

The commit message of `bd02976` contains a complete, accurate prose description of defect #1005,
written five weeks before it was reported:

> *"Under the previous same-day-only wording the time remaining went negative once the departure
> time-of-day passed, saturating the required current and making every ordinary weekday
> afternoon look maximally urgent."*

This is emphatically not "no one looked". Four reviewers looked and three of them were right.
The process has no step that converts "correct review finding about code" into "code changes".

### #1006 — missed-deadline hold

Added to `requirements.md` R5 by the *second commit* of the same PR #510, in response to a
review comment on UC05. `grep -rn "missed_deadline\|deadline_hold" custom_components/` returns
nothing. It is a precondition in two resolution tables (`resolution-rules.md:34`, `:327`) that
are evaluated today as if a hold can never exist.

**Chance to catch: none, structurally.** It entered through an `analysis-reviewer` pass whose
checklist is entirely document-to-document:

> *"Every domain term used is defined in the `system-overview.md` glossary… Every requirement ID
> referenced exists in `requirements.md`… Entity ids match `entity-catalog.md` exactly"*

`analysis-reviewer` never reads `custom_components/`. Its "What to read first" list contains six
paths, all under `docs/analysis/`. **No one looked, by design.**

### #1007 — kW/W mismatch on the power roles

| Moment | What happened |
|---|---|
| **ADR-0030 review** (PR #877) | `adr-reviewer` raised the hazard: *"No unit/availability contract stated for the external reading (kW assumed) — worth naming as a constraint for the implementation spec."* Scoped to the one new role. |
| **ADR-0030 Consequences** | *"a unit contract for the reading — DSO/smart-meter peak sensors commonly report in W, so the adapter … must normalize"*. One role. |
| **Impl spec D-1** (`docs/plans/2026-09-03-external-monthly-peak-mapping-design.md:92-95`) | The author looked *directly at the sibling roles* and dismissed them: **"`NumericReadAdapter` does `float(state.state)` with no unit handling at all; the existing roles that use it rest on a documented unit convention. ADR-0030 records that DSO/smart-meter peak sensors 'commonly report in W', so that convention cannot be relied on *here*."** The "documented unit convention" is `entity-catalog.md`'s W column — a document the source entity's author has never read. |
| **Same spec, Deliberate deferrals** | *"**Device-class filtering on the entity selector** — the codebase's selectors filter by domain only, with no `device_class` precedent anywhere… adding a selector-level filter is a flow-wide convention change, not this slice's to make."* The second line of defence, also declined, also on scope-hygiene grounds. |
| **PR #951 review** | Two comments on `PowerKilowattReadAdapter`: class ordering, and a duplicated float-parse block. Nothing about siblings. |

The purest **looked and reasoned to the wrong conclusion** of the four — twice, in writing, in
the same document. And the reasoning was *good process reasoning*: don't widen a slice. That is
the problem.

**Test tier:** could not have caught it. ADR-0009's mandated adapter coverage is *"present,
absent, unavailable, and — for enum roles — an unmapped raw state."* There is no unit case.
`tests/adapters/test_numeric.py::test_reads_native_float` seeds a state with **no unit attribute
at all** — an adapter that ignores units passes the full mandated set by construction.

### #1008 / #1009 — precision, unit, tile names

**No one looked, and there was nothing to look at.** R19's six acceptance criteria are entirely
about *which entities appear and are settable*:

> *"Every entity classified as runtime configuration in `entity-catalog.md` … is both visible and
> settable from the dashboard."*

Not one word about legibility, precision, rounding, or units. A requirement standard built on
"SMART, testable statements" produced a dashboard requirement with no criterion a human eye can
fail.

`tests/test_dashboard.py` mirrors this exactly — 20 tests, all structural
(`test_charging_status_section_has_the_seven_documented_tiles`,
`test_power_flow_section_omits_the_solar_surplus_tile_when_solar_is_unavailable`). Nothing
renders.

There *is* a catalog-conformance test, `tests/test_init.py::test_every_owned_entity_id_matches_entity_catalog`
— and it checks **the id column only**. `entity-catalog.md:185` specifies `%` for
`active_soc_limit`; `sensor.py:227`'s `ActiveSocLimitSensor` sets no unit, no device class, no
state class. The conformance test that exists covers one of the catalog's eight columns.

The one rule that would have caught both is `docs/reference/definition-of-done.md`:
*"**Runtime-verified, not just test-verified**, for anything with observable runtime behavior —
drive it, don't claim it works on unit tests alone."* It was added 2026-08-29; the dashboard
shipped 2026-08-11. It is an author self-check with no artifact, no reviewer check, and no CI
gate — nothing in `code-reviewer.md` or `_ai-review.yml` asks whether it happened.

---

## 2. What connects a merged requirement to the code that must change

**Nothing. Plainly.**

`write-requirement`'s propagation step names exactly four targets, all documents:

> *"**Propagate**, before step 3's review — a new/changed requirement usually ripples: update the
> glossary, the mechanism docs (`control-cycle.md` / `resolution-rules.md`), and
> `entity-catalog.md`… so the whole **analysis layer** stays consistent."*

Its "Common mistakes" section reinforces the boundary: *"Leaving ripples unpropagated
(requirement added but no `entity-catalog.md` row…)"*. The word "code" does not appear in the
skill.

`analysis-reviewer` reads only `docs/analysis/`. `_ai-review.yml` routes a docs-only diff to that
checklist and no other. So a requirement change is reviewed by an agent that is structurally
incapable of noticing the code now contradicts it.

The repo *does* have the right rule — for the wrong artifact. `contribution-workflow.md:64`:

> ***"A merged `specs` issue produces task issues, not code.** Its approved plan doesn't implement
> itself — file the `development`/`testing` task issues… Filing them is part of finishing the
> spec issue."*

That exists for `specs` and nothing else. There is no equivalent for `requirement`. And nothing
prevents what actually happened: **a docs-only PR closing a `development`-labelled issue (#375)
as COMPLETED**, or an epic (#306) being closed COMPLETED with that same child still open.

---

## 3. Escalating rather than documenting a plan/code conflict

**Is there a rule?** Yes, and it was followed. `develop-task/SKILL.md`:

> *"**Plan inconsistency → truthful, task-scoped implementation, surfaced.** …don't silently
> follow the literal text or paper over it. Implement the minimal truthful version scoped to this
> task, record which later task owns the deferred piece, and flag the deviation instead of
> deciding silently."*

(Codified 2026-08-29 in `d18bff9`; the test docstring from 2026-07-23 already invokes it as "per
project convention" — the rule was retro-codified from this very practice.)

The test docstring does exactly what the rule asks — names the contradiction, resolves it
task-scoped, records it:

> *"Both tests cannot pass together under one same-day, no-rollover rule — **a plan
> inconsistency, not a bug in this test file.** Resolved here (per project convention: implement
> the truthful, task-scoped contract and record the deviation)…"*

The rule is not missing. What is missing is a **sufficiency test on the resolution**. Three
things would have had to be true for escalation instead:

1. **The rule would have to distinguish an inconsistency between the plan's *words* and the
   plan's *numbers* from an inconsistency of scope.** The rule is written for the
   ordering/dependency case ("advertising a capability a later task hasn't built"), where
   task-scoped truncation is genuinely right. Here the two halves of section 6 encoded two
   *different behaviours*, and one had to be wrong. The author's own docstring says "Both tests
   cannot pass together" — that is a semantics conflict, and no one can resolve it task-scoped.
2. **The rule would have to say that "record the deviation" is not discharged by a docstring.**
   Here it was, twice over — the module docstring *and* the engine docstring both encode the
   wrong contract in prose confident enough that `code-reviewer` and `test-reviewer` read them as
   a decision rather than a defect.
3. **`test-reviewer` would have to be told that a test rewritten to avoid a plan's own worked
   example is a red flag.** Its honesty checklist is *"Fixtures don't silently pin values that
   make the assertion trivially true."* The author replaced `NOW=22:00 / DEADLINE=06:00` with
   `FORMULA_NOW=06:00 / FORMULA_DEADLINE=14:00` **"to avoid the cross-midnight ambiguity noted
   above"** — a fixture chosen to dodge the disputed case, which is a near-miss of the existing
   rule but not a hit.

A footnote that sharpens the point: the same avoidance recurred in
`tests/test_deadline_soc_management_end_to_end.py`, whose `_setup` docstring instructs
contributors to **"freeze time on a weekend date (Sat/Sun's own default is None)"** so the
weekday 06:00 default never resolves. Every deadline end-to-end test freezes at 12:00 and then
seeds `_seed_today_deadline(hours_from_now=4)`. The suite navigates around the bug in a
documented helper.

---

## 4. Does an ADR bind anything beyond its own PR?

**No. An ADR binds the PR that introduces it, plus whatever a future author happens to
remember.**

Two propagation mechanisms exist, and neither does this:

- **`code-reviewer`'s reading list**: *"The accepted ADRs the change **touches**."* Touches, not
  governs. A PR that doesn't touch `PowerKilowattReadAdapter` never surfaces ADR-0030.
- **`code-reviewer`'s checklist section 2**, "Structural ADR compliance (the ones this project
  cannot regress)" — a hand-curated list of ADRs 0002-0010. It is the closest thing to a standing
  invariant set, and it is **frozen at ADR-0010**. Twenty-seven ADRs have landed since; none has
  been added, because the list is copied by hand.

Every ADR since then propagates by human memory. ADR-0037 is unusually candid that it knows this
— its Consequences open with *"CLAUDE.md's test/CI/dev-tooling carve-out **has to be amended**…
That amendment is a separate `workflow` change, not part of this ADR — this decision creates it
as an obligation, tracked and settled on its own."* That obligation was honoured (commit
`41d5199`). But it was honoured because the ADR author wrote it down as a bullet and someone read
it — the same mechanism that failed for #1005's follow-up issue.

The concrete gap for #1007: nothing in the ADR template, the `write-adr` skill, or `adr-reviewer`
asks **"where else does this decision apply today?"** ADR-0030 is an ADR about a *hazard class*
(untrusted units at the adapter boundary) written as if it were an ADR about a *role*.

---

## 5. What the test taxonomy asserts, and what it cannot

**ADR-0009 tier 1 (plain pytest, `engines/`/`modes/`/`profiles/`):** asserts that a pure function
reproduces the plan's worked examples. Its oracle *is the plan document*. When the plan is wrong
(#1005) or silent (#1006), tier 1 is a faithful transcription of the error. It cannot see a
clock, a unit, or a unit-of-measurement attribute.

**Tier 2 (HA harness):** asserts wiring, entity ids, registry state, config-flow shape, and
per-cycle commanded current. Its mandated adapter coverage is present / absent / unavailable /
unmapped-enum — four states of *presence*, zero states of *meaning*. Its readings are **seeded by
the test author**, so the author's assumption about units is the test's assumption about units.

**Tier 3 (ADR-0037, scenario/timeline):** every engine live and binding, many cycles, readings
*derived* by a plant simulator with lag, judged by invariants that must not be *"computed by the
same code path that produced the value"*. Genuinely the strongest oracle here — and it does not
exist yet.

**The structural blind spot, stated precisely:** all three tiers assert **the system against its
own documents**. None asserts the system against **an external reality it does not control** — an
entity whose `unit_of_measurement` says something other than what the catalog assumed, a wall
clock that keeps running past a configured time, a Lovelace card rendered at a real width. Every
one of the four defects lives in that gap. The oracle for all four was a human looking at a
dashboard, which is the only oracle in this project that reads the world instead of the docs.

### Would a scenario test have caught #1005?

**As specified today: no. As the epic is scoped: probably yes, and by accident.**

- #998 (the harness slice) explicitly **pins the Manual profile** — *"`ManualPolicy` is a
  pass-through of the user's selection (R16), so mode selection is a fixed variable"*. #1005 is a
  mode-selection defect. It cannot surface there.
- The Auto paths are a separate epic, #1004, which depends on #998 existing first, files "One
  issue per path, filed one at a time", and states *"**Each path needs the maintainer's input
  before it is written.**"* Not one path issue is filed.
- Its first candidate path is *"A full day: sun up → surplus sufficient → Solar, surplus fading →
  Off, sun down + low tariff → CapTar."* Here is the accident: `time.py:47` is
  `WEEKDAY_DEFAULT = time(6, 0)` and `const.py:337` is `DEFAULT_DEADLINE_AVAILABLE = True`. A
  full-day Auto scenario on any weekday starting after 06:00 resolves `urgent=True` on cycle one,
  `profiles/auto.py`'s row 2 fires, and the scenario gets `Captar` where it scripted `Solar` —
  before any invariant runs.
- But #1004 warns about exactly the failure mode that would make it *pass*: *"a path can silently
  take a different branch than its author intended and still pass: the scenario asserts on the
  commanded current, not on which row fired."* Whether it catches #1005 depends on whether the
  author asserts the mode or only the amps.
- #1006 and #1007 it would not catch at all: the hold has no observable it can assert against
  production behaviour that does not exist, and the simulator generates its own readings, so it
  can never disagree with itself about units.

---

## 6. Is the cost proportionate?

**No, and the evidence is specific rather than rhetorical.**

The honest positive first: the ADRs are genuinely excellent. ADR-0037's invariant-oracle rule,
its Option D rejection (*"an oracle the fix pipeline can regenerate is not an oracle under
`_ai-fix.yml`"*), and its self-report that it sits outside CLAUDE.md's own carve-out, are better
reasoning than most funded teams produce. The reviewer agents find real things — #375 and #453
are both `code-reviewer` catches. This process is not theatre.

But look at what it optimises. **Every artifact in the loop has a document as its oracle**:

| Reviewer | Judges against |
|---|---|
| `analysis-reviewer` | analysis docs |
| `adr-reviewer` | ADRs + analysis docs |
| `impl-spec-reviewer` | ADRs + analysis docs |
| `code-reviewer` | the plan, analysis docs, and the ADRs it *touches* |
| `test-reviewer` | ADR-0009 + analysis docs |
| CI `_ai-review.yml` | dispatches to those same five checklists by changed path |
| CI `ci.yml` | ruff, pytest, hassfest, HACS |

Nothing in that list reads a real entity's `unit_of_measurement`, advances a real clock past a
configured time, or renders a page. The single step that points at reality is one bullet in
`definition-of-done.md`, which has no artifact, no reviewer, and no gate.

The arithmetic: 5.2 lines of documentation per line of product code; ~1,000 PRs for a 7.4k-line
integration. Two of the four defects (#1005, #1006) are cases where **the documentation was
right, extensively reviewed, and the code simply did something else** — the investment bought a
correct specification of behaviour the system does not have. #1007 is a case where **an ADR
correctly identified a hazard and slice-hygiene discipline actively prevented fixing it at its
siblings**. #1008/#1009 are a case where **the requirements standard's own "SMART/testable" rule
produced criteria that no human eye can fail**.

**Verdict:** this process reliably produces a consistent, well-argued specification and reliably
prevents structural regressions. It does not, at any point, ask whether the running thing matches
it. That is not a small gap at the edge — it is the gap where all four defects live.

---

## Recommendations

Ranked by expected defects caught per unit of effort. Three changes, plus removals to pay for
them. Each is tracked as a child of epic #1011.

### R1 — A requirement change must name its code consequence (#1013)

**Cost:** ~15 lines across `write-requirement/SKILL.md`, `analysis-reviewer.md`,
`contribution-workflow.md`, `ai-pipeline.yml`. One session.

1. Extend `write-requirement`'s Propagate step past the doc layer: grep `custom_components/` for
   the behaviour this requirement constrains; state in the PR body whether the code satisfies it;
   if not, file the `development` issue **in this PR**. This generalises the rule
   `contribution-workflow.md:64` already states for `specs`.
2. Give `analysis-reviewer` one code-facing question, scoped to criteria the diff actually
   alters: locate the code implementing each; if none exists or it does something else, report
   Major.
3. Refuse a PR whose diff is entirely under `docs/` and whose body `Closes` a
   `development`/`testing` issue. ~10 lines in `ai-pipeline.yml`.

**Would have caught:** #1005 and #1006, at three points each.
**Would NOT have caught:** #1007 (drift was ADR-to-code), #1008/#1009 (no requirement existed).

### R2 — Make "runtime-verified" produce an artifact (#1014)

**Cost:** ~10 lines of process text; 5-15 minutes per behaviour-visible PR thereafter.

A PR that changes observable runtime behaviour includes a **Runtime check** section stating what
was driven and what was observed — pasted entity state including its unit, or a screenshot.
`code-reviewer` reports Major when the diff touches an entity's state/unit/precision/classes, the
dashboard, a notification, or the commanded current, and no such section exists. Deliberately not
a CI gate: a mechanical presence-check is satisfied by an empty section.

**Would have caught:** #1008 and #1009 outright (`168.142101632559` is unmissable in a pasted
state); likely #1007 — issue #1007's own "To confirm on the affected install" section *is* this
check, performed after the fact.
**Would NOT have caught:** #1005, #1006 — neither is visible in a single cycle's state.

### R3 — Distrust units at the boundary; give ADRs a blast radius (#1015)

**Cost:** the process half is ~3 lines plus a template row; the code half is #1007 itself.

1. Add "unit present and expected" to ADR-0009's mandated adapter coverage, in `write-tests`,
   `test-reviewer` and `code-reviewer`. `PowerKilowattReadAdapter`'s own tests are already the
   model; this makes that the rule rather than one role's good luck.
2. Add a **Blast radius** line to `docs/adl/template.md`'s Consequences — every site in the
   codebase this decision governs today, and whether each conforms — and one `adr-reviewer` check
   that the enumeration is complete. For ADR-0030 that is a `grep` for `NumericReadAdapter`,
   returning three power roles with one being fixed.

**Would have caught:** #1007, twice over.
**Would NOT have caught:** #1005, #1006, #1008/#1009.

### Not recommended (yet)

**Do not build the scenario tier as the answer to these four.** ADR-0037 is well-reasoned and
worth keeping, but be clear about what it buys: as specified it catches **none of the four**, and
even fully built it catches at most #1005, conditionally. It is the right tool for the temporal
`baseline_w` class it was designed around (#990/#992). Sequencing it ahead of R1-R3 spends the
largest engineering budget on the smallest slice of this failure set — and ADR-0037's own Con is
that *"a wrong simulator produces confident failures against correct product code."*

---

## What to remove or cheapen to pay for this (#1016)

**1. Cheapen `docs/plans/`.** 24,409 lines — 63% of all documentation, 3.3x the product code. The
largest artifact class and the weakest oracle: #1005 originates in a plan that contradicted
itself between prose and worked example, and #1007's escape is a decision recorded in a plan that
nobody revisits after the slice merges. Cap the impl-spec design doc at the `D-n` decisions and
the TDD task list; drop the restated formulas, ADR rationale and per-task narrative.
`develop-task` already sends the author to the ADR and analysis docs directly, so the plan's
copies are a third version to keep in sync and a second place to be wrong. **This one change pays
for R1, R2 and R3 several times over.**

**2. Cut the interactive review loop from 3 rounds to 2.** CI already caps at 2. The third round
is overwhelmingly nits — PR #951's two review comments were class ordering and a duplicated
try/except, on the PR that shipped #1007's sibling gap. None of the four defects would have been
caught by a third pass.

**3. Extend or stop trusting `test_every_owned_entity_id_matches_entity_catalog`** (#1017). It
checks one of eight catalog columns and gives false confidence that the catalog is enforced —
`active_soc_limit`'s missing `%` sits one column to the right of what it checks.

---

## Loose ends surfaced during the investigation

- **#1018** — `_apply_peak_clamp` runs unconditionally while R3 AC1 says *"When it is absent, no
  peak-protection clamp ever engages"*. A fifth instance of the same spec/code drift pattern,
  already recorded in `docs/plans/2026-09-03-external-monthly-peak-mapping-design.md:420` with no
  owner, where it then rotted unnoticed. Not a safety hazard — it makes a non-CapTar install
  charge *more* conservatively than specified, not less.
- **#697** — while the deadline capability defaults to present
  (`const.py:337`, `DEFAULT_DEADLINE_AVAILABLE = True`), #1005 bites every install on every
  weekday afternoon. That default is why a human found it.
