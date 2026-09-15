# Project profile

The facts about *this* project that a person has to know to act on the method, each with its
why. `.claude/profile.yml` is the other half: every value a script or a command reads verbatim
— repository, board and field ids, the label set, enabled work types, the changed-path map, the
review cap, dependency pins. Nothing here repeats a value the YAML holds; a section names the
key instead. Together the two files are the whole of what is project-specific in
`docs/reference/**` and `.claude/**` — the method documents state rules and route here for the
project they run in, so a method document that spells one of these facts is the defect.

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

The board is the **EMS** project (`profile.yml`'s `board`). Its Status column vocabulary and
option ids are `board.fields.status`; what the columns mean here:

- `Backlog` — filed, not started. Every issue starts here.
- `Ready` — **unused**. It exists on the board but has no defined meaning in this workflow, so
  nothing moves an item into it. If it gains one later (say, dependencies resolved and
  pickable), the contribution workflow's chain is where it gets inserted, explicitly.
- `In progress` — writing has actually started, in a worktree on the issue's branch.
- `In review` — a PR is open; it stays here through every review/fix round and the human's
  merge decision.
- `Done` — merged and cleaned up.

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
are method and which are stack is the layering the epic that introduced this file settled; the
stack skills are declared here and not part of the method.

## Flow

**Default.** This project follows the method's idea-to-product flow as written, with no stage
removed, added or reordered and no gate changed. When the flow document gains its
deviation contract, a deviation is stated here as one `###` per deviation with its why — never
as a copy of the flow.
