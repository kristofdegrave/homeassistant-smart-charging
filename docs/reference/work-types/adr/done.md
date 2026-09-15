# Work type: `adr` — the completion bar

This file states *what must be true of a finished ADR*. How the ADR is written — numbering, the
template, the drafting order, supersession mechanics — is `implement.md`. How a review is
conducted — what to read first, how to anchor findings, the output format, and the checks that
are about the *change* rather than the record — belongs with the reviewer.

There is no 6Cs pass here. That check is for behavioural requirements and use-cases; an ADR's
correctness is judged by whether its options and trade-offs are real, not by
Clarity/Concision/etc.

## The bar

**(1) It should be an ADR at all.** The decision meets the worthiness test in the
**Architecture Decision Records (ADRs)** topic below — the architectural-decision definition,
its calibration test for borderline cases, and its two carve-outs (test/CI/dev-tooling choices;
domain/business rules). A decision that fails that bar is **Major**: name which carve-out or
definition clause it fails, and where it belongs instead (a PR description,
`docs/analysis/requirements.md`, `docs/analysis/resolution-rules.md`). This applies to the ADR
being added, never retroactively to an already-Accepted one.

**(2) Template conformance.** Status / Context / Considered options / Decision / Consequences
all present, in that order, under those exact section names, per `docs/adl/template.md`. The
filename is `NNNN-kebab-case-title.md` and `NNNN` is the next sequential 4-digit integer after
the highest existing `docs/adl/NNNN-*`. `docs/adl/README.md` (the ADL) carries a row for this
ADR whose title and Status match the record. A missing or mismatched ADL row is **Major** — it
is how the log stays readable.

**(3) Context states the forces without presupposing the answer.** A Context that only makes
the case for the chosen option is **Minor**, and usually the reason item 4 also fails.

**(4) The considered options are real.**
- Every option carries at least one genuine Pro **and** one genuine Con. An option with no real
  Con was not seriously considered, or a real Con is being hidden — **Major**.
- At least one **rejected** option is present. An ADR whose only "considered option" is the one
  chosen is not using the template — **Major**. "Do nothing" / "keep the status quo" counts,
  when it was genuinely on the table.
- The Decision **references** the options' stated trade-offs rather than restating them, and
  introduces no argument that isn't grounded in the Considered-options section — **Major** for
  a new ungrounded argument, **Minor** for a Decision that merely restates.

**(5) Consequences follow from the Decision.** They add genuine new information — concrete
follow-up (issues to open, docs to update), what becomes easier or harder — rather than
restating the decision (**Minor**).

**(6) The Blast radius enumeration is complete.** Consequences carry the enumeration
`docs/adl/template.md` specifies: a re-runnable search, a conforms/does-not-conform verdict per
hit, and an explicit out-of-scope list. Run the stated search exactly as written; the template
requires it in the dialect you hold, so a pattern needing translation before it runs is itself
the finding below. Each of these is **Major**; name the sites missed in every case:
- the section is absent;
- the search fails the template's own width test, so it drops something the decision also
  governs;
- a hit appears in neither the table nor the out-of-scope list.

An empty result counts under that width test whenever the ADR's own table lists hits, or the
ADR does not itself claim the template's no-hits case — there, emptiness is a defect in the
stated search, not an empty blast radius. **Minor**: a row carrying a verdict but not what the
site does today; a non-conforming row with no matching follow-up entry; an out-of-scope entry
not saying what it keeps doing.

This item applies to an ADR the change **adds**. One it only *modifies* is out of scope —
adding the section to an existing record would be the immutability violation the reviewer
treats as Critical.

**(7) One problem, one decision.** The ADR addresses exactly one problem and records exactly
one decision. An ADR bundling two or more independent structural choices should be split —
**Major**.

**(8) It doesn't contradict an Accepted ADR without superseding it.** Where it does contradict
one, it says so explicitly and the old ADR's **Status line only** reads
`Superseded by ADR-NNNN`. A contradiction with no supersession is **Critical**.

**(9) Terminology matches.** Domain terms match the glossary in
`docs/analysis/system-overview.md` and the usage in other ADRs — **Minor**.

**(10) Status is `Accepted` before `needs-approval`.** This is the only home for the drafting
convention it rests on: **an ADR carries `Status: Accepted` from its first draft, in its own
PR**, and stays that way. If a review round left it at anything else, the Status line is set to
`Accepted` once the pass is clean and before the PR is labelled `needs-approval`. A PR handed to the human partner with a non-`Accepted` Status is **Major** —
the ADL row (item 2) would then be recording a decision the log says was never taken.

## Architecture Decision Records (ADRs)

When a decision is an ADR at all — the test the bar's item 1 applies. It is reached from
`CLAUDE.md`'s routing table under this heading, so an issue form, a reviewer or a skill that
asks "is this architectural?" lands here.

### Every architectural decision is captured before the work that depends on it

**Every architectural decision must be captured as an ADR before the work that depends on it is committed.** See `docs/adl/0001-use-architecture-decision-records.md` for the rationale and template choice.

### What an architectural decision is

An **architectural decision** is a choice about structure that would be expensive to
reverse or that materially constrains future options — e.g. how integration entities
map to hardware, where a boundary/abstraction layer sits, the shape of a config-entry
schema, which library or protocol to depend on, a change to the coordinator/control-loop
structure. It is **not** an ADR-worthy decision to pick a variable name, a log message,
or a one-off implementation detail with no lasting structural consequence — when in
doubt, ask whether a future contributor would benefit from knowing *why*, not just
*what*.

### The calibration test and the two carve-outs

For a borderline case, a calibration test: would reversing or swapping this choice touch
more than one module, or a contract other code depends on? It supplements, not
overrides, the categories above — a *product-code* choice there (e.g. a library the
shipped integration depends on, a config-entry schema shape) stays architectural even
when well encapsulated; the two carve-outs below narrow that for their own categories.
Serious deliberation alone isn't proof either way — weigh it against the reach test and
the *why*-a-future-contributor-benefits question. Two recurring categories:

- **Test, CI, or dev-tooling choices** (a benchmarking library, a measurement helper, a
  lint tool) are not architectural unless the *product* code itself takes a structural
  dependency on them — a library used only inside `tests/` belongs in a PR description,
  not an ADR. What this carve-out excludes is **which tool or library a script happens to
  call**. It does not extend to the *structure* of the test and automation apparatus
  itself, which stays ADR-worthy even though no product code depends on it. Exactly two
  things sit on that side, and nothing else does:
  - the **CI/automation pipeline's own structure** — trust boundaries, job topology,
    review-loop caps;
  - the **test-tier taxonomy** — which tier a test belongs in, what a passing suite is
    allowed to mean, and where a contributor is expected to put a new test (see ADR-0009
    and ADR-0037).

  The line between the two halves is **who is bound by the choice**, not which directory
  the code implementing it sits in: a taxonomy binds every future test and every future
  reviewer, while a measurement library binds nothing beyond the files that import it.
  So a test-only fixture or simulator's *internals* fall on the library side of that line
  however elaborate they get, while the tier it belongs to falls on the taxonomy side.
- **Domain/business rules** (a formula, a precedence order, which values are surfaced) —
  even when seriously debated — are not architectural; they belong in
  `docs/analysis/requirements.md` or `docs/analysis/resolution-rules.md`, not an ADR.
  Surfacing, renaming, or mirroring an existing config value or computed reading as an
  entity is not, on its own, a structural boundary change and doesn't escape this
  carve-out.

### The bar applies to new decisions; supersede, never edit in place

This tightened bar applies to new decisions; it does not retroactively make an existing
Accepted ADR non-architectural — supersede it instead if a past decision no longer holds
(per `docs/adl/template.md`), never edit it in place to remove it. If an Accepted ADR's
Consequences state a forward-looking bar for future decisions in a category one of the
carve-outs above now excludes, this carve-out governs going forward and that ADR should
be superseded to say so, rather than the conflict being left implicit.

### How an ADR moves through the contribution workflow

An ADR follows the contribution workflow (`CLAUDE.md`'s **Contribution workflow** topic), with
these artifact-specific additions:

- **The implement step's draft** and **the review step's review**: the `adr` row of
  `CLAUDE.md`'s **Model selection** table names the files, and they are their only home —
  don't restate them here. The work file carries how an ADR is written (the template, the
  numbering and never-renumber rules, the immutability rule); the completion bar carries what
  must be true of the finished record, and both the author's self-check and the reviewer's
  criteria are that one file. The worthiness test is the topic above, reached from the bar's
  item 1 rather than repeated in it.
- No tracking refs (PR numbers, issue status) in the ADR body — see `CLAUDE.md`'s **Review
  protocol for analysis documents** topic; the rule applies equally here.
