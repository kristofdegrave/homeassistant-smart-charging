# Work type: `adr` — the completion bar

**Who reads this.** Both sides of the review, which is why it is its own file rather than a
section of either one:

- **The author**, as the self-check before requesting review — this is what
  `definition-of-done.md` means by an artifact's own completion bar, standing in for the
  builds/lints/tests checklist that doesn't apply to a document.
- **The reviewer**, as the bulk of the review criteria. Each item states the severity a miss
  carries, so the two sides judge the same ADR against the same bar.

It states *what must be true of a finished ADR*. How the ADR is written — numbering, the
template, the drafting order, supersession mechanics — is `implement.md`. How a review is
conducted — what to read first, how to anchor findings, the output format, and the checks that
are about the *change* rather than the record — belongs with the reviewer.

There is no 6Cs pass here. That check is for behavioural requirements and use-cases; an ADR's
correctness is judged by whether its options and trade-offs are real, not by
Clarity/Concision/etc.

## The bar

**(1) It should be an ADR at all.** The decision meets the worthiness test in `CLAUDE.md`'s
**Architecture Decision Records (ADRs)** section — the architectural-decision definition, its
calibration test for borderline cases, and its two carve-outs (test/CI/dev-tooling choices;
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
