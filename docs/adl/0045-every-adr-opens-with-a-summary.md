# ADR-0045: Every ADR opens with a Y-statement Summary (narrows ADR-0001)

Date: 2026-09-22
Status: Accepted

## Summary

In the context of ADRs that have grown too long to read for their decision, facing readers who
must get through the whole Context first, we decided that every new ADR opens with a Summary
of at most five lines in the Y-statement shape, to put the decision on the first screen,
accepting one more section to keep consistent with the Decision.

## Context

[ADR-0001](0001-use-architecture-decision-records.md) fixed the template as Status / Context /
Considered options / Decision / Consequences, chosen to keep records "as lightweight as the
rest of the project's documentation".

The records have drifted from that. ADR-0001 to ADR-0012 run about 500–1,500 words; ADR-0024
to ADR-0044 run about 3,000–4,700. The decision sits in the fourth section, so a reader looking
for *what* was decided has to read through the forces and every option first.

Forces:

- **Findability.** The most common question put to the log is "what did we decide about X?",
  and the template makes it the slowest one to answer.
- **Drift.** A summary is a second statement of the decision, so it can contradict the first.
  Whatever is added must be checkable against the Decision.
- **Weight.** ADR-0001's reason for its template still holds: every section added is a tax on
  every future record.
- **Length is a symptom.** Most of the growth is a Context that retells how the problem was
  found. Bounding Context is a drafting rule for the ADR work type to state, not a template
  decision, so this record does not try to solve it.

## Considered options

### Option A — Do nothing; rely on the Context bound

- Pro: No template change; nothing new to keep consistent.
- Con: A Context bounded to forces is shorter, but the decision is still in the fourth section.

### Option B — A Summary section first, in the Y-statement shape

*In the context of <situation>, facing <concern>, we decided <option> to achieve <quality>,
accepting <downside>*: the established one-sentence ADR form.

- Pro: The decision is on the first screen of every record, in a fixed shape a reviewer can
  check field by field against Considered options and Decision.
- Con: A sixth section, and a second statement of the decision that has to be held to the
  first.

### Option C — Move the Decision to the top

- Pro: No new section; nothing to drift.
- Con: The Decision references trade-offs stated in Considered options (the bar's item 4), so
  at the top it would point forward at options not yet read, or have to restate them.

### Option D — A "decided" column in the ADL index

- Pro: No template change; the whole log is scannable from one page.
- Con: A reader opening the record itself still gets no summary, and the index row is a copy
  that drifts with nothing checking it.

## Decision

Option B. It is the only option that puts the decision at the top of the record (unlike A and
D) without breaking the Decision's references to its options (unlike C). Its Con, drift, is
contained by the fixed shape: the Summary names the chosen option as Considered options names
it and accepts one of that option's stated Cons, so a mismatch can be checked rather than
judged.

This narrows ADR-0001: its template stands, with one section added before Context. It is not a
supersession. The rule is forward-binding: it governs ADRs written from here on, this one
first.

## Consequences

- Easier: finding what a record decided. Harder: every new ADR carries one more section, and
  the review checks it against the Decision.
- Follow-up: the template, the ADR bar's template-conformance item, and the ADR work file's
  drafting guidance gain the Summary section. The bar also gains the check that it matches the
  record, at Major, since a summary contradicting its record misleads worse than none.

**Blast radius.** Two searches, run from the repository root:

1. `rg -n 'Status[ ,/]+Context' docs/ .claude/ .github/ CLAUDE.md` — every place that states
   the template's section list. Keyed on the first two sections, not on a single name, because
   every such statement starts there. The dot-directories are named, since a root sweep skips
   them.
2. `rg -l '^## Context\r?$' docs/adl/` — every record and the template (45 hits; `\r?` because
   the tree has CRLF files).

| Site | Today | Verdict |
|---|---|---|
| `docs/adl/template.md` (search 2) | No Summary section | Does not conform: follow-up above |
| `docs/reference/work-types/adr/done.md:22` | Item 2 lists five sections | Does not conform: follow-up above |
| `docs/reference/work-types/adr/implement.md:32` | Drafting step lists five sections | Does not conform: follow-up above |
| `docs/reference/work-types/adr/review.md:20` | Describes the template by five sections | Does not conform: follow-up above |

Out of scope:

- **ADR-0001 to ADR-0044** (the other 44 hits of search 2) keep their five sections: the rule
  is forward-binding. Whether a Summary may be backfilled into an Accepted record is left to the
  width of the ADR immutability rule, which is being settled separately.
- **`docs/adl/0001-use-architecture-decision-records.md:26, 54, 63`** (search 1): the decision
  this record narrows, and the history of the template families; it keeps its text.
- **`.github/test-check-authoring-rules.sh:87`** (search 1): a fixture string for the link
  check, not a statement of the template; it keeps testing that check.
