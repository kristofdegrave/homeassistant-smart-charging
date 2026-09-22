# ADR-0045: Every new ADR opens with a Y-statement Summary (narrows ADR-0001)

Date: 2026-09-22
Status: Accepted

## Summary

In the context of ADRs whose decision sits in their fourth section, facing readers who must get
through the whole Context to learn what was decided, we decided on a Summary section first, in
the Y-statement shape, to put the decision on the first screen, accepting a sixth section, and a
second statement of the decision that has to be held to the first.

## Context

[ADR-0001](0001-use-architecture-decision-records.md)'s Decision fixed the template as Status /
Context / Considered options / Decision / Consequences, chosen to keep records "as lightweight
as the rest of the project's documentation".

The records have drifted from that: ADR-0001 to ADR-0012 have a median of about 1,100 words,
ADR-0024 to ADR-0044 about 3,000. The decision sits in the fourth section, so a reader looking
for *what* was decided reads through the forces and every option first.

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

### Option A — Do nothing; leave it to a drafting rule bounding Context

- Pro: No template change; nothing new to keep consistent.
- Con: A Context bounded to forces is shorter, but the decision is still in the fourth section.

### Option B — A Summary section first, in the Y-statement shape

At most five lines, before Context: *In the context of <situation>, facing <concern>, we
decided <option> to achieve <quality>, accepting <downside>* — the established one-sentence ADR
form without its "and neglected <other options>" clause, which Considered options carries.

- Pro: The decision is on the first screen of every record, in a fixed shape a reviewer can
  check field by field against Considered options and Decision.
- Con: A sixth section, and a second statement of the decision that has to be held to the
  first.

### Option C — Move the Decision to the top

- Pro: No new section; nothing to drift.
- Con: The Decision references trade-offs stated in Considered options, so at the top it would
  point forward at options not yet read, or have to restate them.

### Option D — A "decided" column in the ADL index

- Pro: No template change; the whole log is scannable from one page.
- Con: A reader opening the record itself still gets no summary, and the index row is a copy
  that drifts with nothing checking it.

## Decision

Option B: every new ADR opens with a Summary of at most five lines, in the Y-statement shape,
directly before Context. It is the only option that puts the decision at the top of the record
(unlike A and D) without breaking the Decision's references to its options (unlike C).

Its Con, drift, is contained by the fixed shape, which is Option B's Pro. The Summary names the
chosen option as Considered options names it and accepts one of that option's stated Cons, so a
mismatch is checked, not judged. A mismatch is therefore a defect of the record, not of style.
Being a statement of the decision, the Summary is immutable with it once the record is
Accepted.

This narrows ADR-0001 the way ADR-0033 narrows a record without superseding it. What is narrowed
is one clause: the section list in ADR-0001's Decision gains a Summary before Context. What
stands is everything else: the reasoning of ADR-0001's Option C, the numbering, immutability and supersession.
The rule is forward-binding: it governs ADRs written from here on, this one first.

## Consequences

- Easier: finding what a record decided. Harder: every new ADR carries one more section, and
  the review checks it against the Decision.
- ADR-0001's ADL row gains a pointer to this record in the same change; its Status stays
  `Accepted`.
- Follow-up: the template, the ADR bar's template-conformance item, the ADR work file's
  drafting guidance, the ADR review checklist's description of the template, and the method's
  description of the template gain the Summary section. The bar gains the check that the
  Summary matches the record, at Major. The immutability rule's section lists gain the Summary.
  Search 1 does not reach those two lists, which name only the immutable sections; they are
  listed below by hand.

**Blast radius.** Two searches, run from the repository root:

1. `rg -n 'Status[ ,/]+Context|ADR template|adl/template' docs/ .claude/ .github/ CLAUDE.md`
   — every place that describes the template. It is keyed on the section list and on the
   template's names, because a description can do either: list the sections, or name the
   template and say what it is made of. The dot-directories are named, since a root sweep
   skips them.
2. `rg -l '^## Context\r?$' docs/adl/` — every record and the template (46 hits; `\r?` because
   the tree has CRLF files).

| Site | Today | Verdict |
|---|---|---|
| `docs/adl/template.md` (search 2) | No Summary section | Does not conform: follow-up |
| `docs/reference/work-types/adr/done.md:22`, `implement.md:32`, `review.md:20` | List the template's five sections | Do not conform: follow-up |
| `docs/reference/method/idea-to-product.md:511` | "ADR template (Nygard + Considered options)" | Does not conform: follow-up |
| `docs/reference/work-types/adr/implement.md:54`, `review.md:44` (named by hand) | Name Context / Decision / Consequences as the sections an Accepted record may not change | Do not conform: follow-up |
| `docs/reference/work-types/adr/done.md:23, 47, 143` | Point at the template without listing its sections | Conform |
| `.github/check-authoring-rules.sh:8`, `.github/workflows/_ai-review.yml:374` | Name the template as a path | Conform |

Out of scope:

- **ADR-0001 to ADR-0044** (44 hits of search 2, and the search-1 hits in ADR-0001, ADR-0040 and
  ADR-0041) keep their five sections and their text: the rule is forward-binding. Whether a
  Summary may be backfilled into an Accepted record is not decided here.
- **This record** (search 2, and its own lines naming the template) states the decision and
  follows it.
- **`.github/test-check-authoring-rules.sh:76-77, 87`** (search 1): fixture strings for the link
  check, not descriptions of the template; they keep testing that check.
- **`docs/postmortems/2026-09-11-four-live-behaviour-defects.md:227, 381`** (search 1): a dated
  snapshot of reasoning, never edited to follow later rules.
