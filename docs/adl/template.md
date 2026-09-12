# ADR-NNNN: <Short noun phrase naming the decision>

Date: YYYY-MM-DD <!-- the date this ADR was created; never changes, even if Status later does -->
Status: Proposed | Accepted | Deprecated | Superseded by ADR-NNNN

## Context

What is the issue we're seeing that motivates this decision? State the forces at
play (technical, project, stakeholder) without prescribing the answer yet.

## Considered options

List every option seriously evaluated, including the one rejected. Two options
(do X / don't do X) is fine — the point is to make the trade-off explicit, not to
pad the record.

### Option A — <name>

- Pro: ...
- Con: ...

### Option B — <name>

- Pro: ...
- Con: ...

## Decision

Which option was chosen, and why — referencing the pros/cons above rather than
restating them.

## Consequences

What becomes easier or harder as a result? Include follow-up work this decision
creates (new issues to open, docs to update) and anything it forecloses.

**Blast radius** — required. Every site this decision governs *today*, and whether each
conforms. Bound it like this, so it stays decidable instead of becoming an open-ended audit:

1. State the **one search** that enumerates the candidate sites — a literal `grep`/`glob`
   command a reader can re-run — and why its pattern is wide enough. A pattern keyed on the
   narrowest name silently drops subclasses, aliases and re-exports the decision also
   governs; if that risk exists, say how the pattern covers them.
2. Give **one row per hit**: the site, what it does today, and conforms / does not conform.
   Rows sharing a verdict may be grouped, as long as every hit is accounted for.
3. Name the hits this ADR puts **out of scope** and what they keep doing instead. Silence is
   not out-of-scope.

The enumeration is complete when every hit of the stated search appears either in the table or
in the out-of-scope list — not when the codebase has been audited. A decision that governs no
existing site (greenfield, or a process decision) says so, with the search that shows it.
Non-conforming sites are follow-up work; list them as such.
`0038-unit-contract-at-the-power-read-adapter-boundary.md` is the worked example.
