---
layer: project
---

# Project profile

The facts about *this* project that a person has to know to act on the method, each with its
why. `.claude/profile.yml` is the other half: every value a script or a command reads verbatim
— repository, board and field ids, the label set, enabled work types, the changed-path map, the
review cap, dependency pins. Nothing here repeats a value the YAML holds; a section names the
key instead. Between them the two files own these facts: the repository and tracker, the
board and its ids, the label set, the enabled work types, the changed-path map, the review cap,
the dependency pins, the research sources, git identity, merge strategy and flow deviations. A
method document that spells one of *those* facts is the defect — it states the rule and routes
here. Stack-specific content (Home Assistant, Python) is a different axis and is not this
file's: it lives in the stack skills and in the per-stack overlays of the work-type files
(`docs/reference/work-types/<label>/overlays/<stack>.md`). What the profile holds about a stack
is `profile.yml`'s `stacks`: the declared stacks, each with the tokens the method check keeps
out of the core work-type files.

## Repository and git identity

Claude commits, comments, and opens PRs as the developer's own GitHub account — there is no
separate bot account for the interactive session. The CI pipeline acts as
`github-actions[bot]` instead ([ci-pipeline.md](ci-pipeline.md)). **Why it matters:** a human
item and the session's own footprint are posted under the same login, so
[contribution-workflow.md](contribution-workflow.md)'s **Rounds and the cap** tells them apart
by the session's markers, never by author.

The repository is `profile.yml`'s `repo`; the tracker is GitHub issues, pull requests, review
threads and labels on it, driven with the recipes in
[tracker-mechanics.md](tracker-mechanics.md).

## Merge strategy

Every PR is **squash-merged, manually**, by the maintainer — `CODEOWNERS` covers every tree and
branch protection on `main` requires that approval, so neither the interactive session nor CI
can merge. **Why the squash matters:** it rewrites the merged branch into one commit, which
orphans any branch stacked on it. That is the reason
[contribution-workflow.md](contribution-workflow.md)'s **Base `main` and stacking** has every
PR base `main` directly, however the work was branched locally.

## Project board

The board is `profile.yml`'s `board` (its name, number and node id are there). Its Status
column vocabulary and option ids are `board.fields.status`. The contribution workflow's chain
names columns by **role** only — *backlog*, *in progress*, *in review*, *done* — and this list
is what maps each role to a column here; a method document that spelled a column name would
be stating a profile value, which the method check refuses:

- `Backlog` — the *backlog* role: filed, not started. Every issue starts here.
- `Ready` — **plays no role**. It exists on the board but has no defined meaning in this
  workflow, so nothing moves an item into it. If it gains one later (say, dependencies resolved
  and pickable), the contribution workflow's chain is where it gets inserted, explicitly.
- `In progress` — the *in progress* role: writing has actually started, in a worktree on the
  issue's branch.
- `In review` — the *in review* role: a PR is open; it stays here through every review/fix
  round and the human's merge decision.
- `Done` — the *done* role: merged and cleaned up.

**Size** (`board.fields.size`) is a five-tier T-shirt estimate of reading-plus-writing effort;
**Estimate** (`board.fields.estimate`) is story points in a plain number field. Both are board
fields, not labels, so filing an issue is always two steps
([tracker-mechanics.md](tracker-mechanics.md)'s **Filing a work item**). The rules for setting
them — sizing sweeps up a tier, epics carrying Size only — are
[contribution-workflow.md](contribution-workflow.md)'s **Issue conventions**.

## Labels

The label set — names, colours, descriptions — is `profile.yml`'s `labels`, in four groups
(pre-triage, action, context, kind), and `.github/setup-labels.sh` writes exactly that set to
the repository. What a group means and when an issue carries a label from it is
[contribution-workflow.md](contribution-workflow.md)'s **Issue conventions**; the CI-side places
the context vocabulary is also baked into are [ci-pipeline.md](ci-pipeline.md)'s **Label
vocabulary sync**. The enabled context labels are also the enabled work types
(`work_types.enabled`) — one directory each under `docs/reference/work-types/` and one row each
in `CLAUDE.md`'s **Model selection** table.

## Research sources

When an external fact blocks a decision — what Home Assistant does in some case, how a
dependency behaves, what a device's API returns — these are this project's primary sources,
highest trust first. The `research` skill carries the generic procedure and reaches this list
through `CLAUDE.md`'s **Research sources** section.

1. **Home Assistant** — `developers.home-assistant.io` for the documented contract, and the
   `homeassistant` package source at the version pinned in `requirements-test.txt` for what
   the code actually does.
2. **Library source** — a dependency's published source at the version the file that pins it
   names (`requirements-test.txt` for test and dev dependencies; the integration manifest's
   `requirements` array for anything the shipped integration depends on), not its README. A
   changelog entry counts only as a pointer to the commit that made the change.
3. **Device / vendor API docs** — the manufacturer's own specification for a charger,
   inverter, meter or tariff provider this project integrates with (the hardware is listed in
   `docs/analysis/system-overview.md`); a captured response from the real device outranks the
   specification.

## Dependencies

The method skills this project's work files name, the skills ported into `.claude/skills/`,
and the two stack packages (Home Assistant, Python) are declared in `profile.yml`'s
`dependencies`, each with its upstream source and the pin it was last reconciled with. That
section is the provenance manifest: a pin moves only by a decision recorded in the PR that
moves it, because several of these skills are deliberate adaptations of their upstream
([ai-authoring.md](ai-authoring.md)'s **Vendored skills are forked on purpose**). Which of them
are method and which are stack follows the three-layer split this file exists for — method
(travels everywhere), profile (this project), stack packages (Home Assistant, Python) — so the
stack skills are declared here and are not part of the method.

## Flow

The method's default idea-to-product flow is [idea-to-product.md](idea-to-product.md), and
its first rule is to apply what this section states over the stages it names. This section is
the **deviation contract**, and it has exactly two shapes. Either it says **Default** — the
flow as written, no stage removed, added or reordered, no gate changed — and carries no `###`
at all. Or it carries one `###` per deviation, each heading naming, in backticks, the context
label of the work type whose stage it changes — ``### The `specs` stage is skipped on the bug
track``, say — with the why beneath it, and never a copy of the flow, which would drift from
the method's. **Every backticked span in a deviation heading is read as a work type**, so
nothing else in the heading is backticked: a kind label, a file or a status goes in plain
words, or in the why beneath. The method check refuses a deviation heading that names no work
type, or one this project does not enable — a stage whose work type is not enabled is skipped
by the flow's own rule and needs no deviation to say so — and it refuses a profile document
with no `## Flow` section, or no profile document at all, since either has stated neither
shape.

**Default.** This project follows the flow as written.
