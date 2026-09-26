# Model selection — why the table is shaped as it is

`CLAUDE.md`'s **Model selection** section holds the table and the routing rule a run applies
to it: which files a row resolves to, and how a review's checklists are selected from the
changed paths and the linked issue's label. This document holds the reasoning behind that
shape, and it is reached from the table's own heading for a reader who wants the *why*. Every
rule a **review dispatch** applies — which files a row resolves to, which checklists a change
gets, how each is scoped — is stated in that section and only there; nothing here adds to or
narrows it, and nothing here is a step in resolving a file. What this document does carry
beyond reasoning is the handful of obligations on whoever **edits** the table — keeping the
review model in step, what a label rename touches — which a dispatch never applies. Every `##`
below is a topic and every `###` one rule, so a pointer reaches any of them through that
section.

## Reviewers and their model

### Reviewers always run on Opus

**Reviewers always run on Opus**, regardless of the artifact type being reviewed — which is
why the review-model column reads opus in every row today. The column exists anyway: it makes
a row self-contained, and a row that ever deviates has to argue for it here. Two places must
keep matching: this column and every reviewer agent definition's frontmatter `model: opus`.

## The cell grammar

### A cell that names more than one file labels each role

**A cell that names more than one file labels each role**, in either column. Three roles exist:
the **work file** holds how the artifact is written; the **completion bar** holds what must be
true of the finished artifact; the **checklist** holds what only a reviewer can check — how to
read the change, and the checks about the change rather than the artifact.

### No row names an entry point

**No row names an entry point.** How a run reaches the work file is the same for every work
type, so it is not a per-row fact — `CLAUDE.md`'s **Contribution workflow** topic routes to
the step that takes the work, and that step resolves the row itself. That
leaves the row self-contained in the only sense that matters: it says what to follow, and is
read by whatever followed it there.

### No row branches in the *How the work is done* column

**No row branches in the *How the work is done* column.** A work type whose work splits between
two artifacts names one work file and one completion bar like every other row, and those files
route onward inside `docs/reference/work-types/` — `documentation` is the case. What a row may
still split by is a **tree**, in the review column, where the split is what the union routing
in `CLAUDE.md`'s **Model selection** section is for and so cannot move into a file —
`development` is the case, and each tree is its own sentence, so `;` never has to mean two
things in one cell. A sentence may also state a
named file's scope, as `development`'s work column does for its bar. (`work-types/README.md`
describes that tree's shape. Nothing in this table resolves through it: a row names its files
literally, and this pointer is for a reader wanting the shape, never a step in reaching a file.)

### The checklist is a file; the reviewer is generic

**The checklist is a file; the reviewer is generic — `.claude/agents/reviewer.md`.** That agent
holds nothing type-specific — only the untrusted-data rule, how to resolve a checklist and a bar from
this table, what to do when one cannot be read, and the output and anchoring contract every
review shares. So a row names a `docs/reference/work-types/<label>/review.md` and the generic
agent is spawned against it. The column names the file, and whoever dispatches follows what
it says rather than a reviewer they know of from elsewhere.

### A row is self-contained

**A row is self-contained.** Nothing outside the row and the change's own files is needed to
know what to delegate to — a row names its files outright, and where a work type splits further
that is settled inside those files rather than by anything a run has to resolve here. Reviewer
dispatch additionally resolves the linked issue's label, per the union rule in `CLAUDE.md`'s
**Model selection** section — that is the one input outside the row, and it only ever adds a
reviewer.

## Bars and checklists

### The completion bar is one file named in both columns

**The completion bar is one file named in both columns, and that is deliberate.** It is the
only per-type fact with two readers: the author self-checks against it before requesting
review, and the reviewer applies it as criteria. Naming it twice duplicates a *route*, not a
rule — the alternative is the author and the reviewer each holding their own wording of the
same bar, which is the drift this split exists to remove. A row whose type has no separate bar
simply names none, and its work file carries what "done" means.

### Two rows may share one bar

**Two rows may share one bar.** `uc` and `requirement` do: they share a reviewer, and that
reviewer is dispatched over one tree that also holds documents belonging to neither label, so a
bar per label would leave those with none. Each row still names a path in its own label's
directory, so the row stays self-contained and label-keyed; the `requirement` one routes to the
shared file rather than restating it. A shared reviewer alone does not earn this: the argument
is that the reviewed tree is wider than either label, so splitting the bar would leave part of
it unjudged. The converse — one work type needing more than one bar, because its artifacts are
judged on disjoint criteria — is settled inside its own completion bar and never in the row:
`documentation`'s bar routes to one per document.

## Label and path routing — the reasoning

The rule itself — the union, the tree qualifier, how the two halves are scoped, and what a
tree's own reviewer rule may and may not do — is stated in `CLAUDE.md`'s **Model selection**
section, where a review dispatch applies it. What follows is why it is shaped that way.

### Label and path answer different questions

They answer different questions: the label says what kind of work this is, the changed paths
say what it actually touched, and they come apart whenever a change is *about* one artifact
type but *lives* in another's tree — common for `workflow` work, which edits whichever file
holds the rule.

### Why a tree's own rule never subtracts a reviewer

Adding a file must never subtract a reviewer, which a whole-change suppression would let it do.

### Why path routing is the half that cannot be skipped

Path routing is the half `CLAUDE.md`'s section never lets a run skip because it is what
guarantees no changed tree goes unreviewed, and it is also the half that cannot be steered: the label is resolved from the
PR body, which whoever opened the PR wrote, so the worst a crafted body can do is add a
reviewer, never remove one. The label
row is the addition: it brings the checklist written for this kind of work even when the change
landed somewhere else. A `documentation` PR editing `docs/design/**` therefore gets the
`documentation` checklist for the file and its label's checklist for the subject, and a `development` PR
that also edits a workflow file gets the `workflow` checklist on that file rather than nothing.

## Two rows that differ from the rest

### The `development` and `testing` rows lean on their stack overlays

**The `development` and `testing` rows lean on their stack overlays** more than any other row:
the platform reference and the language checklists their work rests on are stack skills, and
a method row never names one. Every work type with a slot applies its overlays the same way
(the shape is `docs/reference/work-types/README.md`'s **Stack overlays**); what sets these two
rows apart is that their overlays carry the skills the work cannot be done without, and say
when each is read. They are not a fourth column: the overlay is part of the same work file,
bar and checklist the row already names, so the dispatch does not change and nothing here
repeats a rule those files own.

### The `workflow` row has no work file on purpose

**The `workflow` row has no work file on purpose.** A `workflow` change rewrites the files that
instruct every future run — the skills, the agents, the method and the profile — so its drafting
is directed by the human partner rather than taken from an issue by a work file. Its review is
still automated, and its
checklist is the one file in its `docs/reference/work-types/workflow/` directory: with no bar
beside it, that file carries the whole of the criteria rather than only what a bar cannot.
What a `workflow` author reads instead is in `CLAUDE.md`'s **Authoring AI artifacts** topic.

## The no-label row's path map

### The path map is one list, in one place

The row's arrow list in `CLAUDE.md` is the one enumeration of the changed-path set, so adding
or moving a tree means editing that list alone.

`docs/analysis/**` names the `uc` checklist because that tree is wider than either label
sharing it — `requirement`'s file points at the same one.

### Adding or renaming a context label

Adding or renaming a context label means updating `CLAUDE.md`'s table too — see
[ci-pipeline.md](ci-pipeline.md)'s **Label vocabulary sync** for every other
place the same vocabulary is baked in.
