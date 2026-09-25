# ADR-NNNN: <Short noun phrase naming the decision>

Date: YYYY-MM-DD <!-- the date this ADR was created; never changes, even if Status later does -->
Status: Proposed | Accepted | Deprecated | Superseded by ADR-NNNN

## Summary

At most five lines, in the Y-statement shape (ADR-0045): *In the context of <situation>,
facing <concern>, we decided <option> to achieve <quality>, accepting <downside>*. Name the
chosen option as Considered options names it, and accept one of its stated Cons.

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

**Blast radius** — required, and the last part of the record: nothing follows it. Every site
this decision governs *today*, bounded so it stays decidable instead of becoming an open-ended
audit:

1. State the **search** that enumerates the candidate sites — one ripgrep pattern with a
   repo-rooted path, or a short explicitly listed set of them, runnable as written by a reader
   holding nothing but `Grep`/`Glob` — and why its pattern is wide enough: a pattern keyed on
   the narrowest name silently drops subclasses, aliases and re-exports the decision also
   governs.
2. **One row per hit that does not conform**: the site, what it does today, its follow-up.
3. **One line counting the hits that conform**, not a row each.
4. **Out of scope, one line per group**: which hits, and what they keep doing instead. Silence
   is not out-of-scope.

It is complete when every hit is a row, in the count or in an out-of-scope group — not when the
codebase has been audited. A search that genuinely returns no hits means the decision governs
no existing site; say so, and give the search. A process decision is not automatically that
case: it usually governs a tree of its own.

```markdown
**Blast radius.** `rg -n 'unit_of_measurement' custom_components/ tests/` — 12 hits, wide
enough because every power read passes through that attribute.

| Site | Today | Follow-up |
|---|---|---|
| `custom_components/smart_charging/adapters/peak.py:41` | Reads the value without a unit check | Convert per this decision |

8 other hits conform. Out of scope: the 3 hits in `tests/fixtures/` keep asserting raw values.
```
