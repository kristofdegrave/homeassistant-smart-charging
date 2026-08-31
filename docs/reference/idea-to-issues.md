# From idea to issues (epic decomposition)

Entry point is an in-conversation idea or an existing `idea`-labeled issue (`work-idea` runs
the brainstorm dialogue either way). Once scoped enough to act on:

1. **Single-artifact idea** — file that one issue directly (`file-task-issue`); no epic needed.
2. **Multi-artifact strand** (ADR + spec + implementation, or similar) — file a **new epic
   issue** first, Size only, unchecked checklist placeholder. If the idea started as an issue,
   link it in the epic body ("Split from #NNN") and close the idea issue once it's fully
   captured — the epic is a separate issue that stays open; don't relabel/reuse the idea issue
   as the epic, since an epic must stay open tracking children long after the idea itself is
   "decomposed."
3. **File what's already decidable now**, each appended to the epic's checklist as created:
   ADR issue if a structural decision surfaced; spec issue (`specs`) — needed for nearly every
   multi-artifact strand, skip only when the epic is pure non-code doc work; any other
   already-scoped issue (`uc`, `requirement`, `workflow`).
4. **Don't file `development`/`testing` task issues yet.** They require an approved plan's
   anchored `Plan:` line (`write-impl-spec`'s output), which doesn't exist until step 3's spec
   issue is drafted and reviewed. File them once that plan lands, one per task in the plan's
   build order, each appended to the epic checklist as filed.
5. **Keep the epic current.** Anything that surfaces later and belongs to this strand — a bug
   found mid-implementation, a follow-up task — gets appended to the epic's checklist too
   (`bug`/`enhancement` labels are fine; a child doesn't need a drafter context label to belong
   to an epic).
6. **Size + Estimate on every issue** except the epic itself (Size only — see
   [contribution-workflow.md](contribution-workflow.md)'s **Issue conventions**).
7. **Milestone / priority**: not yet standardized — `[TBD]`. Note urgency in the epic body
   until this is resolved rather than inventing a scheme ad hoc.

Once an issue is filed, it follows the normal lifecycle in
[contribution-workflow.md](contribution-workflow.md) (issue → worktree → PR → review → merge).
