# Work type: `adr` — the completion bar

What must be true of a finished ADR: the author self-checks against it, the reviewer scores it.
How an ADR is written is `implement.md`; checks about the *change* belong with the reviewer. No
6Cs pass — an ADR is judged on whether its options and trade-offs are real.

**Scope: the bar scores a record the change adds.** On a record that already exists on the base,
only review check (A) applies, and whether a permitted edit is itself correct — a finding the
fixer may not act on is not raised. An `Abandoned` record is scored on item 2's filename and
ADL-row bullets, item 10, and the presence of a Summary: one sentence is enough, none →
**Major**.

## The bar

**(1) It should be an ADR at all.** The decision meets the worthiness test in the
**Architecture Decision Records (ADRs)** topic below.
- Fails it → **Major**. Name the definition clause or carve-out it fails, and where it belongs
  instead (a PR description, `docs/analysis/requirements.md`,
  `docs/analysis/resolution-rules.md`).

**(2) Template conformance.**
- Status / Summary / Context / Considered options / Decision / Consequences, in that order,
  under those exact names, per `docs/adl/template.md`. Summary is required from ADR-0045 on; a
  record before it conforms with the other five. A section missing, renamed or out of order →
  **Major**.
- Filename `NNNN-kebab-case-title.md`, `NNNN` above `main`'s highest `docs/adl/NNNN-*` with
  every number between held by a remote `adr/NNNN` branch (`implement.md`'s *Number*).
  Otherwise → **Major**.
- `docs/adl/README.md` (the ADL) has a row for it whose title and Status match the record; an
  `Abandoned` row omits the reason.
  Missing or mismatched → **Major**: the row is how the log stays readable.

**(3) Context states the forces — not the answer, and not the derivation.** Forces are what a
reader needs to judge the options: the problem, the constraints, the requirement or record at
stake.
- A Context that only makes the case for the chosen option → **Minor** (item 4 usually fails
  too).
- A passage that retells *how the problem was found* → **Minor**: code traces, a step-by-step
  proof that an older record is wrong, quoted passages of a record the ADR only needs to cite,
  the history of noticing. State the finding in a sentence, naming the site; the proof lives
  in the issue or PR, which `git log` reaches from the record.

  | Force (keep) | Derivation (move out) |
  |---|---|
  | "R5 requires a cycle without state of charge to end no occasion; ADR-0024's edge check fires the clear on such a cycle." | Quoting ADR-0024's table row, then tracing each `_run_cycle` early return to show which ones reach the edge check. |

**(4) The considered options are real.**
- Every option has at least one genuine Pro **and** one genuine Con. No real Con → **Major**:
  the option was not seriously considered, or a Con is being hidden.
- At least one **rejected** option. Only the chosen one → **Major**. "Do nothing" / "keep the
  status quo" counts when it was genuinely on the table.
- The Decision **references** the options' trade-offs rather than restating them, and adds no
  argument the Considered options section doesn't ground. New ungrounded argument →
  **Major**; mere restatement → **Minor**.

**(5) Consequences follow from the Decision.** They add new information — concrete follow-up
(issues to open, docs to update), what gets easier or harder. Restating the decision →
**Minor**.

**(6) The Blast radius is complete, and closes the record.** Consequences end with the Blast
radius `docs/adl/template.md` specifies. Run the search exactly as written; one that needs
translating first fails the width test below. **Major** in each case, naming the sites missed:
- the section is absent;
- the search fails the template's width test, dropping something the decision also governs;
- a hit is not accounted for — not a non-conforming row, counted as conforming, or in an
  out-of-scope group — or the count differs from the conforming hits.

An empty result fails the width test when the ADR's table lists hits, or when the ADR does not
claim the template's no-hits case: the search is then defective, not the blast radius empty.
**Minor**: a row missing what the site does today or its follow-up; an out-of-scope group not
saying what it keeps doing; anything after the Blast radius.

**(7) One problem, one decision.** An ADR bundling two or more independent structural choices
→ **Major**; split it.

**(8) It doesn't contradict an Accepted ADR without superseding it.** Where it contradicts one,
it says so, and the old ADR's **Status line only** reads `Superseded by ADR-NNNN`. A
contradiction with no supersession → **Critical**.

**(9) Terminology matches** the glossary in `docs/analysis/system-overview.md` and the usage in
other ADRs. A term that departs from them → **Minor**.

**(10) Status is `Accepted` before `needs-approval`.** The only home of this convention: **an
ADR carries `Status: Accepted` from its first draft, in its own PR**, and keeps it — or
`Abandoned — <why>` once dropped (`implement.md`'s *Abandoned, not deleted*). A round that left
it otherwise is corrected once the pass is clean. Handed over with any other Status → **Major**:
the ADL row (item 2) would record a decision the log says was never taken.

**(11) Links point only at targets that outlive the record.** A merged record's link is touched
only once it has actually broken, so every link that can break is a future edit to an immutable
record — a defect when written. A markdown link to a target the table does not mark linkable →
**Major**:

| Target | Rule |
|---|---|
| Another ADR | Always linkable, whole-file — supersession and narrowing must be navigable. |
| `docs/analysis/system-overview.md`, `requirements.md`, `entity-catalog.md`, `resolution-rules.md`; `docs/design/system-design.md` | Linkable, whole-file, with the item cited by identifier in prose (`R5`). No anchor to an item's own heading (`### R5 — <title>`): its anchor contains the title, so a retitle breaks it, as with a use-case file. A section heading such as `#ubiquitous-language` is fine. |
| A use-case | Cited by identifier (`UC12`), never linked: the filename embeds the title, so a retitle breaks the link. |
| The issue comment recording a `research` finding the Context rests on | Linkable — the comment is the record of how the finding was established, per the `research` skill. |
| An external URL | Only when the decision is *about* the external thing (a template's source, a dependency adopted), with its identity legible in prose so a dead link still leaves a name. |
| Any other issue or PR | Neither linked nor cited by number: state the fact itself; `git log` reaches the PR from the record (the tracking-refs rule below). |
| Anything else — code paths, `.claude/**`, `.github/**`, any tree that can be retired | Named in prose, not linked. |

Links only, not mentions: a path written in prose doesn't break. A link already in a merged
record is out of scope: it stays until it actually breaks, and is then repaired under
`implement.md`'s *Immutable once merged*.

**(12) The Summary matches the record.**
- It names the chosen option as Considered options names it and accepts one of that option's
  stated Cons. A mismatch → **Major**: a summary that contradicts its record misleads worse
  than none.
- In the shape and within the length `docs/adl/template.md` specifies. Longer, or another
  shape → **Minor**.

**(13) No clutter**, as the *Clutter* entry in
[`ai-authoring.md`'s Vocabulary](../../method/ai-authoring.md#vocabulary) defines it, at its
severities and in its scope. Item 3's derivation Minor is that test applied to
Context.

## Architecture Decision Records (ADRs)

### Every architectural decision is captured before the work that depends on it

**Every architectural decision must be captured as an ADR before the work that depends on it is committed.** Rationale and template choice: `docs/adl/0001-use-architecture-decision-records.md`.

### What an architectural decision is

A choice about structure that is expensive to reverse or materially constrains future options.
- **Is:** how entities map to hardware; where a boundary or abstraction layer sits; a
  configuration schema's shape; a library or protocol the product depends on; the control-loop
  structure.
- **Is not:** a variable name, a log message, a one-off implementation detail with no lasting
  structural consequence.
- **In doubt:** would a future contributor benefit from knowing *why*, not just *what*?

### The calibration test and the two carve-outs

Borderline case: would reversing or swapping this choice touch more than one module, or a
contract other code depends on? This supplements the categories above, never overrides them —
a *product-code* choice listed there stays architectural even when well encapsulated. Only the
carve-outs below narrow that. Serious deliberation is not proof either way: weigh it against the
reach test and the *why* question.

- **Test, CI or dev-tooling choices** — which tool or library a script calls (a benchmarking
  library, a measurement helper, a lint tool). Not architectural unless product code takes a
  structural dependency on it; it goes in the PR description. The carve-out does **not**
  reach the *structure* of the apparatus, which stays ADR-worthy. Exactly two things sit on
  that side:
  - the **CI/automation pipeline's own structure** — trust boundaries, job topology,
    review-loop caps;
  - the **test-tier taxonomy** — which tier a test belongs in, what a passing suite may mean,
    where a new test goes (ADR-0009, ADR-0037).

  The line is **who is bound by the choice**, not which directory holds the code: a taxonomy
  binds every future test and reviewer, a library only the files importing it. So a test
  fixture's or simulator's internals are on the library side however elaborate; its tier is on
  the taxonomy side.
- **Domain/business rules** — a formula, a precedence order, which values are surfaced — even
  when seriously debated. They go in `docs/analysis/requirements.md` or
  `docs/analysis/resolution-rules.md`. Surfacing, renaming or mirroring an existing config
  value or computed reading as an entity is not, on its own, a boundary change, and stays in
  this carve-out.

### The bar applies to new decisions; supersede, never re-decide in place

- The bar does not make an Accepted ADR non-architectural retroactively. A past decision that
  no longer holds is superseded (per `docs/adl/template.md`), never edited away.
- An Accepted ADR whose Consequences set a forward-looking bar in a category a carve-out now
  excludes: the carve-out governs from here on, and that ADR is superseded to say so rather
  than left in implicit conflict.

### How an ADR moves through the contribution workflow

- It follows `CLAUDE.md`'s **Contribution workflow** topic; the `adr` row of its **Model
  selection** table names this bar and the work file.
- No tracking refs (PR numbers, issue status) in the ADR body — `CLAUDE.md`'s **Review
  protocol for analysis documents** topic; the rule applies equally here.
