# Work types `uc` and `requirement` — the completion bar

**Who reads this.** Both sides of the review, which is why it is its own file rather than a
section of either one:

- **The author**, as the self-check before requesting review — this is what
  `definition-of-done.md` means by an artifact's own completion bar, standing in for the
  builds/lints/tests checklist that doesn't apply to a document.
- **The reviewer**, as the bulk of the review criteria. Each item states the severity a miss
  carries, so the two sides judge the same document against the same bar.

It states *what must be true of a finished analysis document*. How one is written — numbering,
the template, the drafting order, the propagation procedure — is the `implement.md` beside this
file and the one in `../requirement/`. How a review is conducted — what to read first, how to
anchor findings, the output format, and the checks that are about the *change* rather than the
document — belongs with the reviewer.

**Why one file for two labels.** The `uc` and `requirement` rows share one reviewer, and that
reviewer is dispatched over one tree: `docs/analysis/**`. That tree also holds documents
belonging to neither label — `control-cycle.md`, `resolution-rules.md`, `entity-catalog.md`,
`system-overview.md` — so a per-label bar would leave those with no bar at all, and the shared
core (glossary-first, the 6Cs, requirement-ID accuracy, what-not-how, not restating mechanism)
would be written twice and drift. One file, addressed by both rows.

It sits in a **label directory** rather than a neutral one — a `work-types/analysis/` or
`_shared/` would have read better — because this tree is keyed by context label: the directory
name *is* the label, so renaming a label is a directory move, and a directory that is not a
label name breaks the invariant `ci-pipeline.md`'s **Label vocabulary sync** relies on to
enumerate what a rename touches. Given that constraint it goes in `uc/`, the larger of the two
type-specific halves, and `../requirement/done.md` routes here.

So sections 1–4 apply to **every** analysis document, and section 5's three subsections apply
to the kind of document actually changed. A document matching none of the three is judged on
sections 1–4 alone; that is not a gap.

## 1. Cross-document consistency

**(1.1) Every domain term used is defined in the glossary.** The glossary-first rule and the
glossary's home are `CLAUDE.md`'s **DDD alignment (lightweight)** section; what this item adds
is the severity. A term used in the document and not defined there is **Major**.

**(1.2) Every requirement ID referenced exists and is used correctly.** `Rnn` / `NFnn` / `Cnn`
are judged against `docs/analysis/requirements.md` — the file, never a memorised range — and
against the acceptance criteria the ID actually carries. A non-existent ID is **Major**; an ID
that exists but is cited for something it does not say is **Major**.

**(1.3) Entity ids match `docs/analysis/entity-catalog.md` exactly.** An invented or misspelled
`sc_` id is **Major**.

**(1.4) Relationships to other documents are accurate and not overclaimed.** A stated
`«include»`/`«extend»`, a "realized by <mechanism>", a "satisfies Rnn" that the other document
does not bear out is **Major**; a link or anchor that does not resolve is **Nit**.

**(1.5) Nothing it describes contradicts another analysis document.** **Major**, naming both
sides of the contradiction.

## 2. Requirement coverage and homing

**(2.1) The document satisfies every requirement it claims**, and each claim is actually
supported by its content rather than asserted in a *Requirements satisfied* line — **Major**.

**(2.2) Every requirement has exactly one home** — a use-case, a mechanism document,
`resolution-rules.md`, or the constraints table. A second home for a requirement already homed
elsewhere is **Major**; the fix is a reference, not a copy.

**(2.3) No mechanism is restated.** A document that repeats the control cycle's clamps or a
resolution rule instead of referencing `control-cycle.md` / `resolution-rules.md` is **Major** —
this is the most common form 2.2 takes.

## 3. Writing quality

**(3.1) What, not how.** No implementation detail — Python modules, HA services, timer helpers,
persistence. Entity ids that are part of the ubiquitous language are fine. **Major** for a
mechanism smuggled into a *what*; **Minor** for an incidental implementation aside.

**(3.2) The 6Cs pass.** Clarity, Concision, Completeness, Consistency, Correctness,
Concreteness, per `CLAUDE.md`'s **Requirements standard**. A miss is **Minor** unless it makes
the document wrong or unusable, which the items above already catch at their own severity.

**(3.3) No tracking refs in the body.** The rule — no PR numbers, no issue tracking statuses —
and its reason are in `CLAUDE.md`'s **Review protocol for analysis documents** section, which
also states that it reaches ADRs; what this item adds is the severity. A tracking ref in the
document body is **Minor**.

**(3.4) Markdown hygiene.** Table style consistent with its neighbours; Mermaid is valid
syntax. **Nit**, except invalid Mermaid, which renders nothing and is **Minor**.

## 4. Code backing

The analysis documents are not the last stop: a document the shipped code contradicts is not
consistent. This item is the single definition of what that means — the author's propagation
step and the reviewer's spot-check both read it here, and neither restates it.

**(4.1) What is in scope.** Only what this change *adds or alters*, read off the diff (or, where
no diff is available, off the list the caller names). Two kinds qualify:

- **An acceptance criterion or constraint row** of `requirements.md`.
- **A use-case's own behavioural assertions**: a Given/When/Then step of the main success
  scenario, an alternate flow or an exception flow; a **Trigger**; a **State model** state or
  transition; a **domain event** under *Domain events produced*. Each names something the
  running integration does — a value written through an adapter role, a condition it acts on, a
  bound it applies, a state it enters, an event it fires. A pre- or postcondition is in scope
  only where it asserts behaviour no other in-scope item in the same diff already covers.
  **Scope / level** and **Relationships** split the same way: in scope wherever they assert
  behaviour — which existing mechanism realizes the use-case, which event it subscribes to,
  whose set-point logic it never touches — and out of scope where they only navigate, an
  `«include»`/`«extend»` pointer or a renumbered sibling link being the usual case.

**Out of scope, and the change is a no-op for this item:** a use-case restating a requirement
(a requirement's home is `requirements.md`, so restating one elsewhere changes nothing), a
rewording, a link or cross-reference, a renumbering, a Mermaid diagram redrawn to match steps
already in the diff, Stakeholders prose, a glossary entry, a *Requirements satisfied* line.
Where nothing is in scope, one line saying so discharges the item.

**(4.2) The finding is stated.** For every in-scope item taken, the **PR body** says which of
two cases holds: the code already satisfies it — naming the file and the function that does —
or it does not. Behaviour the code does not implement at all is this second case, not an
exemption from it. The same applies where the code implements something measurably different:
a different default, bound, unit or ordering.

**(4.3) A gap is filed.** Where the code does not satisfy an in-scope item, a `specs` child
issue for that gap is filed as part of this PR and referenced in the body — a `specs` issue,
never a task issue, for the reason `CLAUDE.md`'s **Contribution workflow** section routes to.
A gap found and left unfiled is **Major**.

**Scope of that Major.** It is assertable only against evidence the judge actually holds. The
author always holds the PR body, so it always binds the self-check. A reviewer who was not
given the PR body cannot tell a missing filing from an unseen one, and reports **Minor** saying
the gap is Major unless such an issue has been filed; the reviewer's own checklist states this
from its side.

Both sides sample rather than sweep, and each says which items it took. The reviewer's cap is
in its own checklist; a work file may set the author's — `uc/implement.md` does, at five
items — or leave the count to the diff, and either way the lookup stays targeted per item.
Sampling is expected; a silent sweep is not.

## 5. Per-document-kind items

### 5.1 A use-case (`docs/analysis/use-cases/UCnn-*.md`)

- **Section order matches the template** in `implement.md` — **Minor**, **Major** where a
  section required for this kind of use-case is absent altogether.
- **Preconditions and postconditions are testable state**, not actions — **Minor**.
- **Main, alternate and exception flows are all present and in Given/When/Then**, with
  alternate flows numbered to the basic step they branch from (`4a`) — a missing exception flow
  on a use-case that can fail to meet its goal is **Major**; mis-numbering is **Nit**.
- **Domain events are past-tense PascalCase** and correspond to steps in the scenarios —
  **Minor**.
- **`entity-catalog.md`'s *Read by* / *Written by* columns reflect every entity it touches** —
  **Major**, because the catalog is how the binding stays discoverable.
- **A mode use-case (UC01–UC04) carries a `stateDiagram-v2` and a State model subsection**
  whose states and transitions match its Given/When/Then scenarios, and states the set-point
  rule — a missing state model is **Major**; a state model that disagrees with the scenarios is
  **Major**; a lighter model on UC08/UC10 is expected, and others may omit it.
- **Deadline escalation is referenced, not restated** — a charging use-case says it is extended
  by the deadline use-case rather than re-deriving urgency escalation (**Major**, as a form of
  2.3).

### 5.2 A requirement, constraint or glossary term

- **Format.** A requirement is `### Rnn — <short title>` with **Priority** (MoSCoW), **What**
  (one sentence) and **Acceptance criteria** as a checklist. A missing MoSCoW priority is
  **Major**; a missing or malformed heading is **Minor**.
- **Acceptance criteria are SMART** — specific, measurable, testable, each stating the
  configurable default and range in parentheses where one exists. A criterion that cannot be
  tested as written is **Major**; a missing default or range is **Minor**.
- **A criterion describes an observable *what*, not a mechanism** — **Major** (a sharper form of
  3.1, and the most common defect in this kind of change).
- **Every configurable parameter has a concrete default.** "No default specified" is **Major**.
- **A constraint (`Cnn`) is a hard rule that holds regardless of mode**, lives as one row of the
  constraints table, and is enforced as an invariant of the control cycle. A "constraint" that
  is really a mode-specific rule is **Major**.
- **A glossary term defines meaning only.** The `sc_` binding — id, unit, default — lives in
  `entity-catalog.md`, and a glossary entry restating it is **Minor**. A definition duplicated
  from elsewhere rather than linked is **Minor**.
- **Ripples are propagated** — a new or changed requirement usually touches the glossary, the
  mechanism documents and `entity-catalog.md` (new `sc_` entities, with defaults matching the
  requirement). An unpropagated ripple that leaves two documents disagreeing is **Major** under
  1.5; one that merely leaves a gap is **Minor**.

### 5.3 A flow or mechanism document

- **It follows the flow-document standard** in `CLAUDE.md`'s **Flow document standard**
  section: Purpose → Trigger → Domain events → Mermaid diagram → Steps → Edge cases →
  Requirements satisfied. A missing section is **Minor**; a missing *Domain events* or *Steps*
  section is **Major**.
- **Domain events are past-tense PascalCase and correspond to steps** — **Minor**.
- **The Mermaid type is one of the preferred three** (`flowchart TD`, `stateDiagram-v2`,
  `sequenceDiagram`) — **Nit**.
