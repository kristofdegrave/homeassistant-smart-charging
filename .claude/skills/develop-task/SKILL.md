---
name: develop-task
description: Use when implementing one task from a Smart Charging implementation plan (docs/plans/*.md) — writing the code and tests for that task test-first, following the project's ADR conventions, on Sonnet. Covers a single bite-sized task through to a reviewed, committed change.
---

# Develop one implementation-plan task (TDD)

Turn one task from an approved implementation plan (`docs/plans/<slice>.md`) into working,
test-covered code under `custom_components/smart_charging/`, test-first. The plan owns *what* to
build and *in what order*; this skill is *how* one task gets built and verified. **Development work
runs on Sonnet** (per CLAUDE.md's model-selection rule).

## Before you start

- The task must come from an **approved** implementation plan produced by `write-impl-spec` — never
  write `custom_components/` code without that plan in place.
- Work the tasks in the plan's order; a task can be built only once every task it depends on exists
  or is stubbed (the plan states its `Depends on`).

## The cycle (do every step, in order)

0. **Take the task and its issue.** Ensure you are on the slice's feature branch (per CLAUDE.md's
   branch-naming). Re-check `git branch --show-current` before any commit — the checkout is shared.
1. **Read the task's plan section**, the **ADR it cites**, and the **analysis behavior** it realizes
   (`control-cycle.md`, `resolution-rules.md`, `requirements.md`, the relevant use-case). The plan's
   formulas/thresholds are **test anchors** attributed to those docs — reproduce them, don't reinvent.
2. **TDD, one behavior at a time** (use the `test-driven-development` skill):
   - Write the failing test in the **correct harness** (ADR-0009): plain pytest for `modes/`/
     `engines/`; HA harness (`pytest-homeassistant-custom-component` + `MockConfigEntry`) for
     adapters, coordinator, entities, config flow. Name it for the requirement/UC/ADR criterion.
   - Run it; confirm it **fails for the right reason** (red).
   - Write the **minimal** implementation to pass (green). Match the surrounding code's idioms.
   - Refactor while green. Commit.
3. **Honor the structural ADRs** as you code:
   - Engine purity: nothing under `modes/`/`engines/` imports `homeassistant.*` or calls another
     engine; stateful engines take state as a parameter.
   - Adapters isolate all HA I/O (ADR-0003); a role returning `None` is the fault signal.
   - Two distinct clamp call sites, no shared opt-out (ADR-0006); fault → force 0 A + `Fault`, grid
     voltage `None` → nominal, not a fault (ADR-0007).
   - Native entity naming (ADR-0004); config data/options split (ADR-0005); package layout
     (ADR-0002/0010).
4. **Verify** (use `verification-before-completion`): `ruff check .` and `pytest` green. For a change
   with runtime behavior, drive it — don't claim it works on tests alone.
5. **Review** — launch the `code-reviewer` agent (fresh, separate Opus) on the diff. Post its
   findings to the PR via the `submit-pr-review` skill in **local mode** (receive them with the
   `receiving-code-review` skill — verify, don't perform).
6. **Address** the review feedback.
7. **Manual review** — present the change to the human partner for explicit approval before merge
   (no PR is auto-merged; CODEOWNERS + branch protection enforce it).
8. **Commit / open the PR** referencing the issue (`Closes #N`), and **stop and report** status.

## Rules

- **Test-first, always.** No implementation line before a failing test that demands it.
- **Minimal + DRY + YAGNI.** Build only what the task needs; reuse existing helpers; match
  surrounding style.
- **Cite behavior, don't restate it.** The analysis docs own the rules; reproduce them as test
  anchors attributed to their source.
- **Never regress a safety invariant.** Clamps, floor/cap, and the fault path stay intact and
  un-merged.
- **Frequent commits**, one behavior each, with the `--author="Claude <noreply@anthropic.com>"`
  identity.

## Common mistakes

- Writing implementation before the red test (or a test that passes without the code).
- Importing `homeassistant.*` into a `modes/`/`engines/` module.
- Merging the two clamp call sites into one conditional (ADR-0006).
- A fault path that guesses/holds a value instead of forcing 0 A (ADR-0007).
- Testing pure logic through the HA harness, or an HA-coupled unit with plain pytest (ADR-0009).
- Claiming "done" without running `ruff`/`pytest` and driving the runtime behavior.
