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

- **Number.** The bar's item 2, *Template conformance*, defines it and judges it. Resolve it
  against a fetched `origin/main` before the branch exists, since the branch is named after
  it. Never reuse or renumber: a superseded ADR keeps its number, so counting from the highest
  existing one is the only safe count.
- **Branch `adr/<adr-number>`**, zero-padded — not the issue number. The contribution workflow
  lets a work file override the number segment when it states the exception and why; this is
  that statement: the record's own number is its identity. Because that number comes from
  `main`, it can collide: **only one ADR may be in flight (drafted, not merged) at a time.** CI
  resolves it the same way in `_ai-draft.yml` right after checkout, and refuses (clears
  `needs-draft`, comments why) rather than clobbering a branch that already exists upstream.

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
     item 6, *The Blast radius enumeration is complete*).
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
- **Fix a finding by rewriting, not appending.** Revise the passage the finding names so it
  reads as if written right the first time. A clarifying paragraph added beside the flawed one
  is not a fix; it is how a record grows longer every round without getting clearer.
- **Immutable once Accepted.** An ADR that is `Accepted` on the base is edited in exactly three
  ways — this list is the rule's only home, and review check (A) scores against it:
  - its Status line, to record a supersession (`Superseded by ADR-NNNN`);
  - a typo fix that changes no meaning;
  - a repair of something a reader could still act on that is **actually broken**: a link that no
    longer resolves, or an instruction against a file that no longer exists. The repair is the
    smallest that makes it work again. A link that still resolves is not broken, however it
    could break later, and a path mentioned in prose is not an instruction.

  Anything else is not an edit to that record. A change of mind is a new ADR that supersedes it;
  a better write-up, a Summary, a sturdier link are left as the record stands. This file is the
  only home for the **author and fix side**; a fix run reaches it through the `adr` row. Two
  guards:
  - **Read "Accepted" from the base, not the working tree:** `git show <base>:<path>`, `<base>`
    the base commit the caller gives (CI's prompt supplies it; locally, the PR's base) — a bare
    branch name may not resolve in a fresh checkout. Under the bar's item 10 every draft reads
    `Accepted` in the working tree.
    - Not on the base, or not `Accepted` there → a draft; fix normally.
    - Base cannot be read (no ref fetched, command unavailable) → don't fall back to the working
      tree. Treat the record as Accepted and say in the summary that the base read failed. A
      wrong Skipped entry is one a human reads and reverses; a wrong edit rewrites an accepted
      record unseen.
  - **A finding outside the list is Skipped, not fixed.** On a record Accepted on the base, a
    finding that the decision is wrong is recorded as a candidate for a superseding ADR; any
    other is recorded as declined under this rule.

### Skills

`research` for the facts an ADR's Context rests on, cited from the record by linking the issue
comment; `receiving-code-review` in the review step. This work type names no stack skill.

## Common mistakes

- Skipping the issue-first step for a decision nobody has discussed yet.
- Writing the investigation into Context instead of the forces.
- Editing an old ADR's Decision instead of writing one that supersedes it.
- Bundling two ADRs, or an ADR plus unrelated work, into one PR.
- Drafting against this file alone and never opening `done.md`.
