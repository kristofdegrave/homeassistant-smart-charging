# ADR-0050: The method keeps no description of CI's lifecycle (narrows ADR-0048)

Date: 2026-09-26
Status: Accepted

## Summary

In the context of a retired AI label pipeline whose shape the method still describes in the
abstract, facing a description no one will use that restates rules another document owns, we
decided to drop it, to keep each rule in one place, accepting that adopting CI again starts from
git history and the local rules alone.

## Context

- **What stands.** [ADR-0048](0048-retire-the-ai-label-pipeline.md) retired the pipeline and
  chose its Option C: keep a short, implementation-free description of how the lifecycle would
  run as CI jobs. It rejected Option D, which kept no description at all.
- **C's case rested on portability.** The method travels between repositories, so a project
  adopting it with CI might start from the description.
- **That case does not hold here.** The human partner does not plan to use the method in a
  repository that runs its lifecycle in CI. If CI returns here, it will be rebuilt.
- **The description restates rules it does not own.** The chain, **Rule A**, **Rounds and the
  cap** and **Exit labels** are `contribution-workflow.md`'s. The description repeats them as
  they would apply to jobs.
- **Nothing tests it.** No check reads it, and every `workflow` change has to keep it consistent
  with the rules it repeats.
- **One reason lives only in it.** ADR-0048 also held that the description explains why each
  step does one task and why the review loop has a cap. The first is **Rule A**'s author/reviewer
  separation, which `contribution-workflow.md` states. The second, that a loop no one watches
  needs a bound, is written only in the description, although **Rule B** runs the local chain
  unattended too.

## Considered options

### Option A — Keep the description (status quo, ADR-0048's Option C)

- Pro: nothing to change, and a project that later adopts the method with CI finds a shape to
  start from.
- Con: about 500 words that no one here will use, repeating rules another document owns, kept in
  step by every `workflow` review.

### Option B — Keep one sentence in its place

State only that the lifecycle's steps are separable, one task each, and point at
`contribution-workflow.md`.

- Pro: keeps the portability hint at almost no cost.
- Con: it still describes a CI that does not exist, and it is still a copy that has to stay true
  to its owner.

### Option C — Drop it (ADR-0048's Option D)

- Pro: each rule lives in one place, and `workflow` reviews stop checking a description of
  something that is not built.
- Con: adopting CI again starts from git history and the local rules alone, with no shape
  written down.
- Con: the one written reason for a review cap goes with the description unless it is moved.

## Decision

**Option C.** A's Con is the cost this record removes, and A's Pro serves a project this
repository does not plan to be. B keeps a smaller copy of the same kind: it still describes a CI
that does not exist. C's first Con is accepted because a rebuild would start from the deleted
workflows in history and from rules that are already written, not from a summary of them. Its
second is met by moving the reason, not by keeping the description.

This narrows ADR-0048 in one place: of its Option C, the retirement stands and the kept
description goes. ADR-0048's Status is unchanged.

## Consequences

- **`ci-pipeline.md` loses the section The lifecycle as CI jobs** and its intro's first half. It
  keeps **Label vocabulary sync**, **The docs-only close guard** and **The upstream-pin drift
  check**, whose headings the files that point into them depend on. Whether the file keeps its
  name is left to the change that removes the section.
- **The cap's reason moves** to `contribution-workflow.md`'s **Rounds and the cap**: the chain
  runs unattended, so the loop needs a bound.
- **Every route to the description goes:** `CLAUDE.md`'s **Contribution workflow** routing cell
  keeps only its regular-CI half, and `contribution-workflow.md`'s intro sentence goes.
- **A kept section loses its trigger-label reasoning:** the upstream-pin drift check's reason for
  applying `workflow` alone, in `ci-pipeline.md` and in `upstream-drift.yml`, no longer argues
  from a label that starts work.
- **`docs/design/system-design.md` §8.3**, which accounts for every ADR after 0019, gives this
  record a process row and notes ADR-0048's row as narrowed by it.
- **Easier:** a `workflow` change is checked against the rules, not also against a description
  of them. **Harder:** nothing records how the lifecycle would split into CI jobs.

**Blast radius.** One search, run from the repository root:

```sh
rg -n -i --hidden --glob '!.git/' \
  --glob '!docs/adl/**' --glob '!docs/postmortems/**' --glob '!docs/archive/**' \
  --glob '!docs/plans/**' --glob '!CHANGELOG.md' \
  -e 'ci-pipeline\.md|as CI jobs|into CI jobs|lifecycle as jobs|is the actor' \
  -e 'starts? (the )?(job|work)' .
```

Wide enough because the description lives in one file: a route to it names `ci-pipeline.md`, or
reaches it through `CLAUDE.md`'s routing cell, which is a hit. The description names itself by
its role (jobs, CI as the actor), and its reasoning survives elsewhere as a label or job that
*starts* work. Keying on the section heading alone would miss the intro, the routing cell and
that reasoning. `--hidden` keeps `.claude/` and `.github/` in. It returns **28** hits on
`origin/main`.

| Site | Today | Follow-up |
|---|---|---|
| `docs/reference/method/ci-pipeline.md:1`, `:4` | The title and intro name the lifecycle as jobs, and CI as the actor | Reworded to the regular-CI checks alone |
| `docs/reference/method/ci-pipeline.md:9`, `:15`, `:16`, `:17` | Head the section The lifecycle as CI jobs and list the labels that start each job | The section is removed, its cap reason moved |
| `docs/reference/method/ci-pipeline.md:252` | Justifies the drift check's `workflow`-only label by a label that would start work | Reworded without a starting label |
| `.github/workflows/upstream-drift.yml:15` | The same invariant, "least of all one that starts work" | Reworded the same way |
| `docs/reference/method/contribution-workflow.md:9`, `:10` | Say how the lifecycle would split into CI jobs is described in `ci-pipeline.md` | The sentence is removed |
| `CLAUDE.md:112` | The **Contribution workflow** cell routes to `ci-pipeline.md` for how the lifecycle would run as CI jobs | Keeps only "the repository's own CI checks" |

14 hits conform: 13 point at `ci-pipeline.md`'s regular-CI sections, which stay, and
`.claude/skills/implement/SKILL.md:12` quotes a user's "start work on #N". Out of scope:
the 3 hits in `.github/test-check-authoring-rules.sh` are synthetic link fixtures that test a
pattern, not the description, and keep doing so. The excluded trees keep their dated text, and
this record and its ADL row fall in that exclusion.
