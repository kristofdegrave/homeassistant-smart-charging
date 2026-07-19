# Token efficiency in AI authoring

Reference guidance for authoring the artifacts that drive Claude runs in this repo:
skills (`.claude/skills/`), agent definitions (`.claude/agents/`), and the CI worker
prompts (`.github/workflows/_ai-*.yml`). It exists so that every new authored artifact is
lean by construction, not trimmed after the fact.

It is **reference**, not a gate: nothing here overrides the correctness, review-integrity, or
model-selection rules in `CLAUDE.md`. Where a token saving would trade away analysis quality
or write/review independence, quality wins — see [Non-negotiables](#non-negotiables).

## Where the tokens actually go

Two multipliers dominate cost in this repo, and neither is "a subagent was spawned":

1. **Cold sessions in the CI review/fix loop.** Each PR can run up to a small, fixed number of
   automatic review→fix cycles (a tunable cap in `_ai-review.yml`'s "Route by verdict" step),
   and every review and every fix is a *fresh container* with no cross-run prompt-cache reuse.
   The per-cycle cost (a review pass plus a fix pass) is paid again from cold each cycle, so
   the cycle count is the biggest single lever.
2. **Fixed context re-read on every cold session.** `claude-code-action` auto-loads
   `CLAUDE.md`, all of `.claude/skills/`, and all of `.claude/agents/` on every run,
   whether or not a given file is relevant to the task. That overhead is multiplied by the
   number of sessions in the loop above.

Everything below targets one of these two.

## Principles

- **Say what, point to where.** An authored artifact should carry the *decision procedure*
  and link to the source of truth, not restate it. `submit-pr-review` being "the single
  source of truth for the review payload" is the pattern: other artifacts reference it
  instead of duplicating the payload rules.
- **One source of truth per fact.** Duplicated instructions across skills/agents are read
  every cold session and drift over time. Deduplicate into one file and link.
- **Scope the read.** Tell a run *which* file to read for a task, so it doesn't fan out
  across the whole `docs/` tree. The review worker already does this — it selects one
  checklist per changed path rather than loading all six.
- **Keep stable files stable.** Prompt caching only pays off when the cached prefix does
  not change. Churn in `CLAUDE.md`, a skill, or an agent def invalidates the cache for
  every run that follows. Batch edits; avoid cosmetic churn.
- **Bound the loop, not the turn.** Prefer capping *how many times* a run repeats
  (cycles, retries) over shrinking a single run's turn ceiling. A too-low turn ceiling
  causes truncation and a re-run, which costs more than it saved — this is why the fix pass
  runs at 50 turns, not 20 (`.github/workflows/_ai-fix.yml`), and why any automatic
  review↔fix cap belongs on the *cycle count*, not the per-pass turns.

## Checklist — authoring a skill (`.claude/skills/`)

- [ ] The skill states a procedure and links to sources of truth; it does not restate rules
      that already live in another skill, an agent def, or `CLAUDE.md`.
- [ ] No instruction here is duplicated in another skill. If two skills need the same rule,
      it lives in one and the other links to it.
- [ ] The `description` is precise enough to trigger on the right task and *not* on
      adjacent ones — a skill that fires when it shouldn't costs a whole run's context.
- [ ] Any file the skill tells the run to read is named specifically, not "read the docs".
- [ ] Examples are the shortest that still teach the pattern; long transcripts are trimmed.

## Checklist — authoring an agent definition (`.claude/agents/`)

- [ ] The "read first" list names the minimum set of files needed to do the job, in order.
- [ ] The checklist is self-contained for its artifact type, so a review needs to load only
      *this* agent def plus the payload skill — not several agent defs.
- [ ] Shared review mechanics (payload shape, anchoring, verdict marker) are referenced from
      `submit-pr-review`, not copied.
- [ ] Tool grants are the minimum the checklist actually uses (a read-only reviewer needs no
      write/edit tools).

## Checklist — authoring a CI worker prompt/config (`.github/workflows/_ai-*.yml`)

- [ ] The prompt selects the specific checklist(s) for the changed paths rather than telling
      the run to consider all of them.
- [ ] `--allowed-tools` is the minimum the task needs; each grant has a comment saying why.
- [ ] `max_turns` is set high enough to finish in one pass (avoid truncation re-runs) and no
      higher; if a run regularly hits the ceiling, raise it — a hit ceiling means a wasted run.
- [ ] Any automatic repeat (review↔fix, retries) has an explicit cap and a terminal state
      (e.g. the loop's cycle cap + `needs-approval` escalation in `_ai-review.yml`), so it
      cannot run away.
- [ ] PR content is treated as untrusted data (this is a correctness/security rule, not a
      cost one, but the worker prompts already carry it — keep it).

## How to measure

`ai-cost-summary` (`.github/actions/ai-cost-summary`) writes per-run cost, turns, and token
usage — including `cache_read_input_tokens` and `cache_creation_input_tokens` — to the job
summary. Use it, not estimates, to decide whether a change actually helped:

- **Cycle count per PR** — *manually* count the `<!-- ai-review-verdict: remarks -->` reviews
  on the PR (`ai-cost-summary` is per-run and has no per-PR aggregate). This is the dominant
  cost driver; watch it first.
- **Cache-read ratio** — `cache_read_input_tokens` ÷ total input tokens, from the job summary.
  A drop after an edit to `CLAUDE.md`/a skill/an agent def means that edit invalidated the
  cached prefix.
- **Turns vs. ceiling** — a run at its `max_turns` ceiling was likely truncated and will be
  re-run; raise the ceiling rather than eating the re-run.

Lock in a change only when the summary shows it moved one of these numbers the right way.

## Non-negotiables

These bound every optimization here; a token saving that touches one of them is not taken:

- **Write and review stay separate sessions.** Reviewing your own draft in the same context
  reintroduces the bias the split exists to remove (`CLAUDE.md`, review protocol).
- **Model tiering is by task, not by cost.** Opus for analysis/design/ADR work, Sonnet for
  code — per `CLAUDE.md`. Do not downgrade an analysis run to save tokens.
- **No merge without the maintainer's manual approval.** Cost bounds cap *automatic* work;
  they never auto-approve or auto-merge.
