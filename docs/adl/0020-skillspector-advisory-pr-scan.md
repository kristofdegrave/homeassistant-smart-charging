# ADR-0020: Advisory SkillSpector scan feeding the workflow-reviewer AI review

Date: 2026-08-09
Status: Accepted

## Context

`.claude/skills/` and `.claude/agents/` are executable instructions, not documentation — they
run with the AI pipeline's write-scoped credentials (`ANTHROPIC_API_KEY`, `WORKFLOW_PAT`) against
untrusted issue/PR content. CLAUDE.md's "Authoring AI artifacts" section and the
`workflow-reviewer` agent (`.claude/agents/workflow-reviewer.md`) already treat this tree as
security-sensitive: every change to it goes through a fresh Opus review
(`.github/workflows/_ai-review.yml`) checking prompt-injection containment, least privilege,
fork-PR trust boundaries, and a token-efficiency checklist.

NVIDIA's [SkillSpector](https://github.com/NVIDIA/SkillSpector) is a purpose-built static scanner
for this exact artifact class: it flags prompt injection patterns, data-exfiltration shapes,
privilege-escalation patterns, unpinned `npx`/`uvx` invocations, and missing tool-permission
scoping in a `SKILL.md`/agent definition and the scripts it references. It runs as a mechanical
substring/pattern pass (`--no-llm`), which is fast and cheap but noisy: a skill that *documents*
a security concern (e.g. `workflow-reviewer.md`'s own injection-containment checklist) trips the
same rule as a skill that *contains* one. An unverified field report shared outside this project
described roughly 3 in 4 findings as false positives on their skill set — we have no independent
measurement yet, but the qualitative failure mode (substring matching can't distinguish
discussing a pattern from executing one) holds regardless of the exact ratio.

The question this ADR answers: do we adopt SkillSpector at all, and if so, does its output
become a blocking CI check or evidence handed to the existing judged review — given that a noisy
blocking gate risks training reviewers to click past findings, including real ones.

## Considered options

### Option A — Do nothing (status quo)

Rely solely on `workflow-reviewer`'s existing checklist; no new scanner, no new workflow surface.

- Pro: No new external dependency, no new CI job to maintain, no added run time or token cost.
- Con: `workflow-reviewer`'s checklist is a manually maintained set of instructions applied by an
  LLM under time/turn pressure — it has no dedicated mechanical pass for patterns a static scanner
  checks deterministically (e.g. every `npx`/`uvx` invocation across a diff is version-pinned).
  An oversight there is silent: nothing flags that the check was skipped.

### Option B — Blocking gate

Run SkillSpector as a required status check; a score above threshold fails the PR.

- Pro: A hard stop that cannot be forgotten or skipped by an inattentive reviewer or a rushed
  turn budget.
- Con: Given the high false-positive rate inherent to substring-based static analysis (see
  Context), a blocking gate degrades signal over time — it directly contradicts the severity-graded, human/AI-judged review
  model this project already uses everywhere else (`code-reviewer`, `workflow-reviewer`, and the
  rest report Critical/Major/Minor/Nit for a human or the fix cycle to weigh, never a blunt
  pass/fail). A red gate that's wrong 3 times out of 4 trains people to override it, including on
  the 1-in-4 that's real.

### Option C — Advisory scan feeding the AI review as evidence

Run SkillSpector as a `continue-on-error` (job-level) scan whenever a PR touches a skill/agent
root; hand its report to the existing `workflow-reviewer`-driven review step as material to
verify (confirm/dismiss per finding, cite `file:line`), not as a second gate. The scan itself
never blocks merge — only a `workflow-reviewer`-confirmed finding can, via the pipeline's
existing verdict-marker/label flow (`needs-work` / `needs-approval`).

- Pro: Reuses the review model and label plumbing (`_ai-review.yml`'s verdict marker) already in
  place instead of adding a second, parallel pass/fail signal; the mechanical detection SkillSpector
  is good at (unpinned installs, pattern matches) gets a dedicated pass without asking an LLM to
  emulate static analysis under a turn budget; raw scanner noise never reaches a human directly —
  only the reviewer's judged CONFIRMED findings do, which keeps the PR's visible signal meaningful.
- Con: Adds an external tool dependency (SkillSpector itself, a third-party project) and a new job
  to the AI pipeline — one that must itself pass `workflow-reviewer`'s own checklist before merge
  (the reviewer must review the addition to its own review pipeline), and that carries ongoing
  upkeep the other options don't: a pinned-version install to track and re-bump over time, and a
  risk-score threshold to keep calibrated as this project's own skills/agents change (see
  Consequences for the specific obligations this creates).

## Decision

Option C. This project already treats blunt pass/fail gates as the wrong tool for judgment calls
under uncertainty — every existing reviewer agent reports by severity for a human or the fix cycle
to weigh, never a red X (Option B's failure mode is exactly the false-positive erosion this
pattern exists to avoid). Option A leaves a mechanical, deterministic check (install pinning,
pattern matches) to an LLM's turn-budgeted attention instead of a purpose-built tool, which is a
capability gap worth closing given `.claude/skills/`/`.claude/agents/` already carry write-scoped
credentials. Option C's added maintenance cost (pinning, threshold calibration, one more job in
the review pipeline) is accepted as the price of closing that gap without abandoning the
judged-review model.

## Consequences

- A follow-up issue must be opened to add the scan job and wire its report into `_ai-review.yml`'s
  existing review step (or a companion workflow it calls) — this ADR settles the decision and its
  constraints, not the exact YAML. This is a workflow-authoring change, not one backed by a
  `docs/plans/` TDD plan, so it does not take the `development`/`testing` context label or a
  `Plan:` anchor line; it goes straight to implementation under `workflow-reviewer`'s cycle.
- The implementation issue must require: (a) the SkillSpector install pinned to an exact tag or
  commit SHA, never a tracked branch; (b) `continue-on-error` at job level, not step level, so a
  failing `uses:` step cannot redden the PR; (c) the risk-score threshold calibrated against a
  local `skillspector scan --no-llm` run over this project's current `.claude/skills/` and
  `.claude/agents/` before being enabled, not copied from an external default; (d) the scanner's
  raw output never echoed to stdout/logs directly (workflow-command injection risk from PR-authored
  content) and passed to the review step via `env`, not inlined into a prompt string.
- That implementation change is itself a change under `.github/workflows/` and must go through the
  full `workflow-reviewer` cycle (fresh Opus review) before merge, same as any other pipeline change.
- `docs/reference/ai-authoring-token-efficiency.md`'s CI-worker checklist may need a new bullet
  once the concrete job exists, covering how scanner-report evidence is passed to a review prompt
  without becoming untrusted instructions itself (same containment discipline the prompt-injection
  checklist already requires of PR diff content).
- Forecloses treating any future static-analysis tool over this tree as a blocking status check by
  default — the same advisory-evidence pattern applies unless a later ADR explicitly supersedes
  this one for a documented reason.
