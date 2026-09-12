# Authoring AI artifacts

Reference guidance for authoring the artifacts that drive Claude runs in this repo:
skills (`.claude/skills/`), agent definitions (`.claude/agents/`), and the CI worker
prompts (`.github/workflows/_ai-*.yml`). It exists so that every new authored artifact is lean
*and* predictable by construction: the [Vocabulary](#vocabulary) names the failure modes,
[Project-dependent content routes through
`CLAUDE.md`](#project-dependent-content-routes-through-claudemd) and [Tracker-dependent
mechanics route through
`CLAUDE.md`](#tracker-dependent-mechanics-route-through-claudemd) fix where anything
repository-specific and anything tracker-specific live, and the per-artifact checklists test
the ones a reviewer can decide mechanically.

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
2. **Fixed context re-read on every cold session.** `claude-code-action` loads `CLAUDE.md`
   in full on every run, plus the frontmatter `name` and `description` of each file under
   `.claude/skills/` (and of `.claude/agents/` wherever subagent dispatch is available) —
   the action's documented behaviour; what a worker receives under a restricted tool grant is
   not independently verified here. A skill or agent **body** is not loaded until the skill is
   invoked or the file is read — the CI prompts point the worker at a path and grant `Read`
   precisely because of this. So the fixed overhead is `CLAUDE.md` plus a description index,
   multiplied by the number of sessions in the loop above; the bodies are a per-use cost, paid
   only by the run that needs them.

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
it, leading word first. `ha-integration-knowledge`'s (vendored) description — "Everything you
need to know … If you're looking at an integration, you must use this as your primary reference"
— names one branch so broad it always fires. **Project rule, overriding the upstream advice:** a
pointer to project-dependent material names the `CLAUDE.md` section that owns the topic rather
than the material itself — stated in full, with its boundaries and its scope, in
[Project-dependent content routes through
`CLAUDE.md`](#project-dependent-content-routes-through-claudemd) below.

**The two loads.** **Context load** is what always-loaded material costs every turn — the fixed
context re-read above. **Cognitive load** is what it costs the maintainer to know a document
exists and when to reach for it. Only the first is minimised here; the second is the price of the
split, not a cost to drive to zero. `grill-me` spends cognitive load to buy zero context load;
`grilling` pays a three-sentence description every turn to stay model-reachable.

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

## Project-dependent content routes through `CLAUDE.md`

**The rule.** A skill or agent definition states the **generic procedure**; everything
project-dependent in it is resolved through `CLAUDE.md`. Project-dependent means the project's
name, its documentation paths, its list of sources, its entity or module names — anything that
would simply be *wrong* in another repository. The reason is reusability: the artifact is what
travels between repositories, and `CLAUDE.md` is the one file that is rewritten per repository,
so an artifact that reaches every project-dependent fact through a `CLAUDE.md` section lands in
the next repository working, while one that names the facts lands in it lying. A CI worker
prompt (`.github/workflows/_ai-*.yml`) is outside the rule: it does not travel — it *is* this
repository's pipeline.

**The four boundaries**, in the order they get argued about:

- **An artifact may name another skill or agent.** They travel together — `.claude/` moves as
  one tree — so a cross-reference between them stays valid wherever the tree is installed, and
  routing it through `CLAUDE.md` would buy nothing.
- **An artifact may name `CLAUDE.md` and a section heading in it.** A *named section* is a
  specific target, so it meets *Scope the read* below and the checklists' "name the file, not
  'read the docs'" bar — which is why the heading is required and `CLAUDE.md` alone is not
  enough. What it costs is the onward hop only: `CLAUDE.md` itself is already loaded on every
  run (item 2 above), so resolving the pointer is the whole of the new work, and it buys a
  route every artifact inherits from a single edit.
- **An artifact may not name a `docs/**` path, the project by name, or a project-specific
  resource list** — with the one exception of its own subject matter, defined after this
  list. Write "this project" where a name is tempting; route the path and the list.
- **Where no `CLAUDE.md` section owns the topic, add the route there — never the fact.** One
  line naming the topic and the document that owns it, and no more — *Keep stable files stable*
  below says what a fact parked in the always-loaded prefix costs every run, and its churn every
  warm one. If what you are about to add to `CLAUDE.md` is longer than a route, it belongs in
  the document the route points at.

**What is not a route: subject matter.** This exception is about paths only — the project's
name and its resource lists are never subject matter. Among paths, the rule binds the project
*documentation* an artifact reads to learn how to operate. The repo paths an artifact exists to
*act on* — the trees a reviewer's diff lands in, the workflow file a checklist is about, the
tree a skill writes into — are the subject matter of its own criteria, not a route to
documentation, and stay named. The test is which of the two a path is: *tells the artifact how
to operate* → route it; *is what the artifact operates on* → name it. A checklist about the
router workflow cannot route to the router workflow. The test is applied **per path, not per
tree**: `workflow-reviewer` names `docs/reference/` as a tree it reviews *and* routes to the
one document inside it that carries its criteria, and both are right — a document does not
become subject matter by sitting in a reviewed tree. Where one and the same path is genuinely
both, subject matter wins and it stays named; the route is then redundant, not forbidden.

Some categories sit on that boundary often enough to have a recorded answer, so an author
meeting one does not have to re-derive it:

- **A reviewer agent's "what to read first" list is its checklist**, so it cannot simply be
  emptied of paths — an `analysis-reviewer` with no paths is not reusable but inert. The split
  above is the answer, and it is the one worked through on `workflow-reviewer`: project
  documentation the agent reads for its criteria routes through the `CLAUDE.md` section owning
  that topic, while the trees the agent exists to review stay named, including in the
  frontmatter `description` that dispatches it — an agent that cannot say what it reviews cannot
  be dispatched to review it. Two rejected alternatives, so they are not re-proposed: moving
  the reviewer agents' read-lists into `CLAUDE.md` (it inflates the always-loaded prefix and
  inverts ownership — the agent knows what it needs to read, `CLAUDE.md` knows where topics
  live), and exempting reviewer agents wholesale (too wide: it would have excused an agent
  naming a document *and* the `CLAUDE.md` section that points at the same document).
- **A skill whose whole purpose is one artifact type this project defines** — the `write-*`
  family, each written for a document type that exists only because this project defines it,
  and `develop-task`, written for a task as this project's implementation plans define one —
  does not gain reusability by being genericised, and the rule does not ask it to be. A
  `write-use-case` skill has nothing to be in a repository with no use-case documents. So the
  artifact type it produces, the tree it writes into, and the template it drafts against are
  its subject matter and stay named. What still routes is everything it reads to know *how the
  project works around that artifact* — the review protocol, the lifecycle, the model tiering,
  the reference docs it is not itself about. The rule is near-vacuous for these skills, which is
  the decision, not an oversight.

**Permanent scope: as written or changed, never as a sweep.** This paragraph states the scope
of both rules on this page — the one above and the tracker rule below, which shares it rather
than restating it. The rule binds an artifact at the moment it is newly written, or changed
for some other reason — and it binds **what that change writes**: every pointer the change
adds or rewrites conforms, while prose the change leaves
alone is owed no conversion. A typo fix is therefore not a conversion trigger, and converting
the rest of a file you are rewriting anyway is welcome but never required. An artifact nobody
has a reason to touch is never opened to satisfy this rule, and there is no retroactive
conversion pass: artifacts predating the rule are conformant by age, not on borrowed time. This
is the rule's standing scope, not a grace period that expires. A reviewer therefore applies it
to what the diff writes, and not to an unconverted file that diff happens to read, sit beside,
or resemble; a finding raised against untouched material is out of scope by construction.

## Tracker-dependent mechanics route through `CLAUDE.md`

**The rule.** A skill or agent definition states the **generic procedure** — *file a work
item*, *record the finding against the work item that needed it*, *reply to the finding and
close it out* — and reaches the commands that drive one particular tracker through
`CLAUDE.md`'s **Tracker mechanics** section. Tracker-dependent means the `gh` invocations
themselves and everything that exists only because this project's work lives in GitHub issues,
pull requests, review threads, labels and a project board: endpoint paths, field and option
ids, flag spellings, and the failure mode and read-back each command needs. The reason is the
[project-dependent](#project-dependent-content-routes-through-claudemd) one a turn further
out: the procedure is what travels and the tracker is what gets swapped, so an artifact whose
steps are procedures lands in a repository on another tracker needing one `CLAUDE.md` section
rewritten, while one that spells `gh api …/pulls/<n>/reviews` into a step lands there needing
itself rewritten. CI worker prompts (`.github/workflows/_ai-*.yml`) are outside this rule for
the same reason they are outside the other: they do not travel — they *are* this repository's
pipeline, wired to this tracker's events.

**The carve-out: an artifact whose subject is one tracker's API.** `submit-pr-review`,
`finalize-pr-review` and `address-review-remarks` do not merely touch the tracker on the way
to somewhere else; they exist *to drive* its review API, and the review API is what they are
about. Genericising them is not a trade of one line for a pointer — take the endpoints, the
payload shape and the thread mechanics out of them and nothing is left to state, because there
is no procedure underneath that was ever independent of the tracker. They name it freely, and
that is permanent, not pending.

**The test**, for an artifact that is neither obviously one: does it merely **record or read**
work items in passing — file one, comment on one, label one, look one up — so that the same
step would still make sense on another tracker? The rule applies; route the commands. Or is
**one tracker's API the artifact's actual subject**, the thing it was written to operate? The
carve-out applies; name it. This is the project rule's **What is not a route: subject matter**
line applied to commands instead of paths, not a second formulation — an author who has
settled which side a path falls on has already settled which side a command does.

**One source per mechanic, the carve-out included.** A carve-out artifact is the source of
truth for what it owns — what a review *says*: payload shape, severity grouping, the verdict
marker, which threads may be resolved. It is not thereby a source of truth for the mechanics
it happens to spell out. Where the same command exists in the reference behind **Tracker
mechanics**, the reference wins; a copy inside a carve-out artifact that has drifted from it is
a stale copy, not a second authority. Drift is the expected state rather than an anomaly,
since the reference was verified and corrected after those artifacts were written and nothing
sweeps them. So an author converting an artifact under this rule, or copying a command out of
a carve-out artifact into one, takes the command from the reference and checks the local copy
against it — and fixes or deletes the local copy only if that artifact is the one being
changed, which the scope below decides.

**Scope: identical to the project rule's.** It binds an artifact as it is newly written or
changed, binds only what that change writes, mandates no sweep, and bounds a reviewer's
findings the same way. That is stated once, for both axes, in **Permanent scope: as written or
changed, never as a sweep** above; it is not restated here.

## Principles

- **Say what, point to where — one source of truth per fact.** An artifact carries the
  *decision procedure* and links to the source of truth rather than restating it; a duplicated
  instruction drifts apart from its twin, and each copy is read again by every run that needs
  it. `submit-pr-review` being "the single source of truth for the review payload" is the
  pattern: other artifacts reference it instead of duplicating the payload rules. (Drift is the
  main cost; the read cost is per use, not per cold session — see item 2 above.)
- **Scope the read.** Tell a run *which* file to read, so it doesn't fan out across `docs/`.
  The review worker already does this — one checklist per changed path, not all six.
- **Keep stable files stable.** Prompt caching only pays off when the cached prefix does
  not change. What sits in that prefix is `CLAUDE.md` and the description index — so churn in
  `CLAUDE.md`, or in a skill's or agent's *frontmatter*, invalidates it; editing a skill
  **body** does not, since the body was never in the prefix. Batch edits; avoid cosmetic
  churn. Note this is a **local-session lever, not a CI one**: each CI worker is a fresh
  container with no cross-run cache reuse (see *Cold sessions* above), so CI pays the prefix
  from cold every run whether or not anything changed. There is no CI payoff here to optimise
  for.
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
- [ ] Any file the skill tells the run to read is named specifically, not "read the docs".
- [ ] Nothing project-dependent is stated in the skill; each such fact is routed per
      [Project-dependent content routes through
      `CLAUDE.md`](#project-dependent-content-routes-through-claudemd) — its boundaries, its
      subject-matter exception for the tree the skill writes into, and its scope included.
- [ ] The skill states the generic procedure for anything it does to the tracker and routes
      the commands per [Tracker-dependent mechanics route through
      `CLAUDE.md`](#tracker-dependent-mechanics-route-through-claudemd), unless one tracker's
      API is the skill's own subject.
- [ ] Every step ends on a completion criterion a run can decide, not a judgement word.
- [ ] The invocation choice is justified: model-invoked only where the model or another skill
      must reach it, otherwise `disable-model-invocation: true`.
- [ ] Examples are the shortest that still teach the pattern; long transcripts are trimmed.

## Checklist — authoring an agent definition (`.claude/agents/`)

- [ ] The "read first" list names the minimum set of files needed to do the job, in order.
- [ ] Nothing project-dependent is stated in the definition; each such fact is routed per
      [Project-dependent content routes through
      `CLAUDE.md`](#project-dependent-content-routes-through-claudemd), including its
      subject-matter boundary for the trees the agent reviews.
- [ ] Any tracker command the definition would state is routed instead, per
      [Tracker-dependent mechanics route through
      `CLAUDE.md`](#tracker-dependent-mechanics-route-through-claudemd).
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
  A drop after an edit to `CLAUDE.md`, or to a skill's or agent's *frontmatter*, means that
  edit invalidated the cached prefix. Editing a **body** cannot move this number: the body was
  never in the prefix. And the comparison is only meaningful *between local sessions sharing
  a warm cache* — across CI runs there is no cross-run reuse to lose (see *Cold sessions*
  above), so a difference between two CI runs' ratios is not evidence about an edit.
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
