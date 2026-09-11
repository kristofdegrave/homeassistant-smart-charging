# Authoring AI artifacts

Reference guidance for authoring the artifacts that drive Claude runs in this repo:
skills (`.claude/skills/`), agent definitions (`.claude/agents/`), and the CI worker
prompts (`.github/workflows/_ai-*.yml`). It exists so that every new authored artifact is lean
*and* predictable by construction: the [Vocabulary](#vocabulary) names the failure modes, the
per-artifact checklists test for them.

It is **reference**, not a gate: nothing here overrides the correctness, review-integrity, or
model-selection rules in `CLAUDE.md`. Where a token saving would trade away analysis quality
or write/review independence, quality wins — see [Non-negotiables](#non-negotiables).

## Where the tokens actually go

Two multipliers dominate cost in this repo, and neither is "a subagent was spawned":

1. **Cold sessions in the CI review/fix loop.** Each PR can run up to a small, fixed number of
   automatic review→fix cycles (a tunable cap in `_ai-review.yml`'s "Route by verdict" step),
   and every review and every fix is a *fresh container* with no cross-run prompt-cache reuse.
   The per-cycle cost is paid again from cold each cycle, so the cycle count is the biggest
   single lever.
2. **Fixed context re-read on every cold session.** `claude-code-action` auto-loads
   `CLAUDE.md`, all of `.claude/skills/`, and all of `.claude/agents/` on every run,
   whether or not a given file is relevant to the task. That overhead is multiplied by the
   number of sessions in the loop above.

Everything below targets one of these two.

## Vocabulary

Names for the failure modes the checklists below test for, after [mattpocock/skills
`writing-for-agents`](https://github.com/mattpocock/skills/tree/main/skills/productivity/writing-for-agents).
A term is here only because an artifact in this repo exhibits it, cited as the worked example.

**Context pointer.** A reference held in context naming out-of-context material and the condition
for reaching it: a skill `description`, a `CLAUDE.md` line naming a doc, an agent def's "read
first" entry. Its *wording*, not its target, decides whether a run reaches the material, so a
must-have target behind a vague pointer is a **variance bug** — sharpen the pointer before
inlining the material, naming what it is and the distinct branches that should trigger reaching
it, leading word first. `ha-integration-knowledge`'s description ("Everything you need to know …
If you're looking at an integration, you must use this as your primary reference") names no
branch and triggers on a mood, for material the repo calls its primary reference. **Project rule,
overriding the upstream advice:** a skill never names a `docs/reference/*.md` path directly — it
points at the `CLAUDE.md` section owning the topic, which routes onward, keeping the route a
one-place edit every skill inherits (`work-idea` and `handoff` predate this; fix when touched).

**The two loads.** **Context load** is what always-loaded material costs every turn — the fixed
context re-read above. **Cognitive load** is what it costs the maintainer to know a document
exists and when to reach for it. Only the first is minimised here; the second is the price of the
split, not a cost to drive to zero. `grill-me` spends cognitive load to buy zero context load;
`grilling` pays a 60-word description every turn to stay model-reachable.

**Information hierarchy.** Three rungs, by how immediately a run needs the material: in-file
step, in-file reference, reference disclosed behind a pointer. **Progressive disclosure** is the
move down that ladder — inline what every branch needs, disclose what only some reach; the
per-label `work-types/` tree in `docs/plans/2026-09-11-lifecycle-skills-design.md` is that move
applied to the seven reviewer agents. **Co-location** decides what sits beside a piece once it
lands: a concept's definition, rules and caveats under one heading. The context-label
vocabulary is the counter-example — values canonical in `contribution-workflow.md`, CI-side sync
obligation in `ci-pipeline.md`, `workflow-reviewer` spending a paragraph reassembling the two.
**Sprawl** is length itself, even where every line is live and unique: `domain-driven-design` is
194 upstream-intact lines in a tree every cold run loads.

**Completion criteria.** Every step ends on a condition telling the run it is done. *Clarity*:
can it tell done from not-done? A fuzzy bound invites **premature completion** — stopping early
because the steps still visible ahead pull attention towards being done. *Demand*: how much the
bound asks: "every changed path has its checklist applied" forces legwork where "review the PR"
does not, and it binds flat reference ("every rule applied") as much as a sequence. `grilling`
shows both — a fuzzy opening bound ("until you reach a shared understanding") rescued by a
checkable terminal gate (the user confirms) and a high-demand round format. Sharpen the bound
first; hiding later steps needs a context boundary (a subagent, a hand-off).

**Negation.** Steering by prohibition drags the forbidden behaviour into context and makes it
*more* available, not less. Prompt the positive: `async-python-patterns` heads its first rule
"Never block the event loop" though the positive target sits in the body ("push blocking work to
HA's own executor"). A prohibition earns its place only as a hard guardrail with no positive
phrasing — `workflow-reviewer`'s "do NOT comply" for prompt injection — paired even then with the
positive target.

**Invocation choice** (skills only). A model-invoked skill keeps a `description`: the model can
fire it and other skills can reach it, at permanent context load. A user-invoked skill
(`disable-model-invocation: true`) costs nothing standing, but only a human can fire it and no
skill can reach it. Choose model-invocation only when the model or another skill must reach the
skill on its own. The repo's two user-invoked skills are `handoff` and `grill-me`, the latter a
name-to-type whose whole body dispatches to the model-invoked `grilling`. When user-invoked
skills multiply past what a maintainer remembers, the cure is a **router skill**: one user-invoked
skill naming the others and when to reach for each.

## Principles

- **Say what, point to where — one source of truth per fact.** An artifact carries the
  *decision procedure* and links to the source of truth rather than restating it; an
  instruction duplicated across skills/agents is read every cold session and drifts.
  `submit-pr-review` being "the single source of truth for the review payload" is the
  pattern: other artifacts reference it instead of duplicating the payload rules.
- **Scope the read.** Tell a run *which* file to read, so it doesn't fan out across `docs/`.
  The review worker already does this — one checklist per changed path, not all six.
- **Keep stable files stable.** Prompt caching only pays off when the cached prefix does
  not change. Churn in `CLAUDE.md`, a skill, or an agent def invalidates the cache for
  every run that follows. Batch edits; avoid cosmetic churn.
- **Bound the loop, not the turn.** Prefer capping *how many times* a run repeats
  (cycles, retries) over shrinking a single run's turn ceiling. A too-low turn ceiling
  causes truncation and a re-run, which costs more than it saved — this is why the fix pass's
  derived ceiling (`.github/workflows/_ai-fix.yml`) starts well above the 20-turn ceiling that
  was once hit mid-work, and why any automatic review↔fix cap belongs on the *cycle count*, not
  the per-pass turns.

## Checklist — authoring a skill (`.claude/skills/`)

- [ ] The skill states a procedure and links to sources of truth; it does not restate rules
      that already live in another skill, an agent def, or `CLAUDE.md`.
- [ ] No instruction here is duplicated in another skill. If two skills need the same rule,
      it lives in one and the other links to it.
- [ ] The `description` is precise enough to trigger on the right task and *not* on
      adjacent ones — a skill that fires when it shouldn't costs a whole run's context. It
      names the branches that should trigger it, not a mood (see [Vocabulary](#vocabulary)).
- [ ] Any file the skill tells the run to read is named specifically, not "read the docs" —
      and a `docs/reference/*.md` target is reached through the `CLAUDE.md` section that owns
      it, never named directly.
- [ ] Every step ends on a completion criterion a run can decide, not a judgement word.
- [ ] The invocation choice is justified: model-invoked only where the model or another skill
      must reach it, otherwise `disable-model-invocation: true`.
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
      (`_ai-draft.yml`, `_ai-review.yml`, and `_ai-fix.yml` all derive this per run from a
      workload shape — the issue's context label for the drafter, the changed paths for
      review/fix — plus the linked issue's project-board Size field, rather than a flat
      constant — board hygiene is load-bearing for these paths; see each file's "Resolve
      max_turns from context/workload + Size" step.)
- [ ] Any automatic repeat (review↔fix, retries) has an explicit cap and a terminal state
      (e.g. the loop's cycle cap + `needs-approval` escalation in `_ai-review.yml`), so it
      cannot run away.
- [ ] PR content is treated as untrusted data (this is a correctness/security rule, not a
      cost one, but the worker prompts already carry it — keep it).
- [ ] A third-party static-analysis report handed to a reviewer as evidence (e.g. the
      SkillSpector report `_ai-review.yml`'s `skill-scan` job produces, per ADR-0020) is written
      to a file and read with a tool the run already has, never inlined into the prompt string
      or echoed to a step's own stdout — the untrusted-content containment above applies to it
      exactly as it does to PR diff content.

## Vendored skills are forked on purpose

Four skills came from external sources via a marketplace install and are recorded in
`skills-lock.json` with their upstream hash: `python-anti-patterns`, `async-python-patterns`,
`ha-integration-knowledge`, `domain-driven-design`. Two of them — `python-anti-patterns` and
`async-python-patterns` — have since been **rewritten for this repo**: trimmed to the rules that
apply to an async Home Assistant custom integration, and cross-linked so no rule is stated twice.
`ha-integration-knowledge` carries one local note (the custom-integration path mapping);
`domain-driven-design` is upstream-intact.

Two consequences:

- **`.claude/skills/` is the only authoritative tree.** It is what Claude Code loads and what
  every CI worker prompt names. The installer's second copy under `.agents/skills/` was an
  unreferenced byte-identical duplicate and has been removed; don't reintroduce it.
- **A re-sync from upstream would revert that work.** The `computedHash` entries in
  `skills-lock.json` describe where a skill came from, not what it must still contain. Before
  re-pulling any of the four, check whether the local copy has diverged — for the two rewritten
  ones, re-apply the trim rather than accepting the upstream text.

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
