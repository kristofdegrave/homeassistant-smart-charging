# Work type: `adr` — how the work is done

How an Architecture Decision Record under `docs/adl/` is written — and nothing else. It is the
`adr` row's work file in `CLAUDE.md`'s **Model selection** table.
- Why ADRs exist and why the template looks as it does:
  [ADR-0001](../../../adl/0001-use-architecture-decision-records.md).
- What the finished record must satisfy: `done.md`, the completion bar. Most of what a review
  will say is already there — open it before drafting, not after.
- Whether the decision should be an ADR at all is settled when the issue is filed and re-checked
  against the bar's item 1, *It should be an ADR at all* — not while drafting.

## Before the branch exists

- **Number: one above the highest held.** Several ADRs may be in flight at once, and an open
  `adr/NNNN` branch reserves its number. Re-run the count, never remember it, just before the
  branch is cut:
  1. `git fetch --prune origin`;
  2. take the highest `NNNN` in `git ls-tree --name-only origin/main docs/adl/` and
     `git branch -r --list 'origin/adr/[0-9][0-9][0-9][0-9]'`;
  3. add one;
  4. reserve it at once, before drafting: create the remote branch at `origin/main` with
     `gh api repos/<owner>/<repo>/git/refs -f ref=refs/heads/adr/NNNN -f sha=<origin/main sha>`,
     then fetch it and cut the worktree from it. The call refuses (HTTP 422) a name that
     already exists, so a refusal means another session took the number: re-count. A plain
     push is no reservation: it goes out only after the draft, and it fast-forwards over a
     same-named branch cut from an older `main`.

  A merged ADR's leftover branch never exceeds `main`'s highest, so it changes nothing. Never
  reuse or renumber: a superseded or abandoned ADR keeps its number. The bar's item 2,
  *Template conformance*, judges the result.
- **Branch `adr/<adr-number>`**, zero-padded — not the issue number. The contribution workflow
  lets a work file override the number segment when it states the exception and why; this is
  that statement: the record's own number is its identity, and the branch is what reserves it.
  Its reservation is step 4 of the count; never clobber a branch of that name.

## Drafting

1. **Cross-check existing ADRs and design docs first** — does this contradict an Accepted ADR?
   The bar's item 8, *It doesn't contradict an Accepted ADR without superseding it*, judges the
   result. Cheap before the Decision is written, expensive after;
   the step most often skipped.
2. **Draft against `docs/adl/template.md`**, section by section — the Summary last, though it
   sits first:
   - **Context — the forces, not the derivation.** The bar's item 3, *Context states the
     forces — not the answer, and not the derivation*, judges it. Write what was found, not
     how: one sentence naming the site beats four paragraphs proving it.
   - **Considered options** — every option seriously evaluated, each with a real Pro and Con
     (the bar's item 4, *The considered options are real*). Reached this section with only the
     chosen option? Stop and name what else was on the table, even "do nothing".
   - **Decision** — name the option and point at its trade-offs; don't restate them (the bar's
     item 4 again).
   - **Consequences** — follow-up work, what gets easier or harder (the bar's item 5,
     *Consequences follow from the Decision*), and the Blast radius per the template (the bar's
     item 6, *The Blast radius is complete, and closes the record*).
   - **Summary** — written once the Decision is settled, from the Decision and the chosen
     option's Cons, never from memory of the argument (the bar's item 12, *The Summary matches
     the record*).
   - **Links** — only the targets the bar's item 11, *Links point only at targets that outlive
     the record*, allows; name everything else in prose.
     For example, the use-case is cited as `UC12`, never linked by its file.

## Rules

- **Form** — per *Write rules as items, with the shortest example that teaches them*, in
  [`ai-authoring.md`'s Principles](../../method/ai-authoring.md#principles).
- **Reference, don't restate.** Anywhere in the record, cite a requirement or use-case (`R7`,
  `UC03`) rather than re-deriving it.
- **One problem, one decision per ADR** — the bar's item 7, *One problem, one decision*. A
  design doc bundling several architectural choices yields several ADRs.
- **One PR per ADR** — no second ADR, no unrelated non-ADR work, however close. The ADL row
  (the bar's item 2) and any supersession Status-line edit (item 8) belong in that same PR. A
  genuine follow-up on the same ADR uses the workflow's multi-PR convention for its issue.
- **Status `Accepted` from the first draft** — the bar's item 10, *Status is `Accepted` before
  `needs-approval`*, is the rule's only home.
- **Merge in number order**, so `main` never holds a number above one still open. An
  `Abandoned` ADR merges like any other, so a higher one waits for it too.
  - **Who checks, and when:** the session that ran the review step, straight after a clean
    pass's exit. It fetches, lists the `adr/NNNN` branches as the count does, and looks for a
    lower number whose record is not on `origin/main`.
  - **One found:** a blocking reason found after the exit, so the PR goes on hold per
    [contribution-workflow.md's *Exit labels*](../../method/contribution-workflow.md#exit-labels).
  - **How the hold ends:** once the lower ADR merges, the human partner grants a round. Its fix
    merges `origin/main` in, where a conflict on the ADL row is expected, and the next pass
    reads the complete log.
- **Abandoned, not deleted.** An ADR the human partner drops before it merges keeps its number
  and its full draft: it merges with `Status: Abandoned — <why, in one sentence>`, and its ADL
  row reads `Abandoned`, without the reason. Deleted, it would leave a gap in the log, and the count could hand its
  number out again.
- **Fix a finding by rewriting, not appending.** Revise the passage the finding names so it
  reads as if written right the first time. A clarifying paragraph added beside the flawed one
  is not a fix; it is how a record grows longer every round without getting clearer.
- **Immutable once merged.** An ADR that exists on the base is edited in exactly three ways,
  whatever its Status there — `Superseded`, `Deprecated` and `Abandoned` records included —
  and this list is the rule's only home, for author, fixer and reviewer alike:
  - its Status line, to record a supersession (`Superseded by ADR-NNNN`) or a deprecation, or
    to correct one merged as anything but `Accepted` or `Abandoned` — the bar's item 10 — to
    `Accepted`;
  - a typo fix that changes no meaning;
  - a repair of something that directs the reader to act and is **actually broken**:
    - a link that no longer resolves: re-point it at the same content's new path; where that
      content is gone, keep its name in prose and drop the link;
    - an instruction against a file that no longer exists: strike it.

    Nothing is restated or added in place of either. A link that still resolves is not broken,
    however it could break later, and a path mentioned in prose is not an instruction.

  Nothing else is changed in that record. A change of mind is a new ADR that supersedes it;
  a better write-up, a Summary, a sturdier link are left as the record stands. Two guards:
  - **Read existence from the base, not the working tree:** `git show <base>:<path>`, `<base>`
    the PR's base commit — a bare branch name may not resolve in a fresh checkout. The Status
    line decides nothing: under the bar's item 10 every draft reads `Accepted` in the working
    tree, and a record that is on the base was merged, whichever Status it carries now.
    - Not on the base → a draft; fix normally.
    - Base cannot be read (no ref fetched, command unavailable) → don't fall back to the working
      tree. Treat the record as merged and say in the summary that the base read failed. A
      wrong Skipped entry is one a human reads and reverses; a wrong edit rewrites a merged
      record unseen.
  - **A finding whose fix would be an edit outside the list is Skipped, not fixed.** One that
    the decision is wrong is recorded as a candidate for a superseding ADR; any other is recorded
    as declined under this rule.

### Skills

`research` for the facts an ADR's Context rests on, cited from the record by linking the issue
comment; `receiving-code-review` in the review step. This work type names no stack skill.

## Common mistakes

- Skipping the issue-first step for a decision nobody has discussed yet.
- Writing the investigation into Context instead of the forces.
- Editing an old ADR's Decision instead of writing one that supersedes it.
- Bundling two ADRs, or an ADR plus unrelated work, into one PR.
- Drafting against this file alone and never opening `done.md`.
