# Authoring AI artifacts

Reference guidance for authoring the artifacts that drive Claude runs in this repo:
skills (`.claude/skills/`), agent definitions (`.claude/agents/`), and the CI worker
prompts (`.github/workflows/_ai-*.yml`). **Work-type documents**
(`docs/reference/work-types/<label>/`) hold content moved out of a skill, so everything here
binds them **except** the two routing sections: they do not travel between repositories, which
is the premise both rules rest on, so they name this project's paths and tracker commands
directly. Every other rule binds it — the content did not stop being an instruction to a run by
moving. The checklist that governs one is therefore the **skill** checklist, minus four of its
items: the two that read frontmatter (the `description`'s trigger precision and the invocation
choice), a work-type document having none; and the two that exist only to enforce the routing
sections carved out above (nothing project-dependent stated inline, tracker commands routed).
Applying those two literally would flag a work file for naming a `docs/` path or a tracker
command, which is exactly what the carve-out permits. Author and reviewer build against the
same list.

**The harness configuration is a fourth artifact under `.claude/`, and this reference does not
govern it.** `.claude/settings.json` and the hooks it wires (`.claude/hooks/`) drive Claude
runs as surely as a skill does — a `PreToolUse` guard decides whether a tool call happens at
all — but they are executable configuration, not text a run reads as instruction, so the rules
below have nothing to bite on: there is no `description` to trigger on, no context budget to
spend, and the routing rule has no purchase on a script, which reaches a project document by
naming its path in a message a human reads, not by routing a run to it. A checklist section
here would be items none of which a reviewer could apply. Its criteria are the `workflow`
review checklist's instead — the one `CLAUDE.md`'s **Model selection** table names for that
tree. Naming the class here is what stops a reviewer reading its absence as "no criteria
exist".

This reference exists so that every new authored artifact is lean
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
pointer to project-dependent material, or to the mechanics of the tracker this project's work
lives in, names the `CLAUDE.md` section that owns the topic rather than the material itself —
stated in full, with its boundaries and its scope, in [Project-dependent content routes through
`CLAUDE.md`](#project-dependent-content-routes-through-claudemd) and [Tracker-dependent
mechanics route through `CLAUDE.md`](#tracker-dependent-mechanics-route-through-claudemd)
below.

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
obligation in `ci-pipeline.md`, the `workflow` review checklist spending a paragraph
reassembling the two.
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
phrasing — the generic reviewer agent's "do not comply" for prompt injection — paired even then
with the positive target.

**Invocation choice** (skills only). A model-invoked skill keeps a `description`: the model can
fire it and other skills can reach it, at permanent context load. A user-invoked skill
(`disable-model-invocation: true`) costs nothing standing, but only a human can fire it and no
skill can reach it. Choose model-invocation only when the model or another skill must reach the
skill on its own. Which skills are user-invoked is not a list to maintain here — it is the set
whose frontmatter carries `disable-model-invocation: true`, and one `grep` over
`.claude/skills/*/SKILL.md` enumerates it. One shape in that set is worth naming: a
name-to-type such as `grill-me`, whose whole body dispatches to a model-invoked skill. When
user-invoked skills multiply past what a maintainer remembers, the cure is a **router skill**:
one user-invoked skill naming the others and when to reach for each.

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

**What enforces it.** `.github/check-authoring-rules.sh`, run per PR by `ci.yml`'s `authoring`
job, rejects the half a grep can decide with certainty: a **markdown link** from a skill or
agent definition to a project documentation file. A link exists to be followed, so it is a
route; a bare path in prose is a name. That is a rule and not just an observation: a path kept
under the subject-matter carve-out below is written as a **bare path**, not a link — the
carve-out says such a path stays named, and naming it is what a bare path does. Where it
genuinely has to be a link, that is what the allowlist is for. It is diff-scoped, matching the conversion scope stated further down, and its
exceptions live in `.github/authoring-rule-allowlist.tsv` — a link that is genuinely subject
matter goes there with a reason, so the exception is reviewed rather than silent. What the
check cannot see stays with the reviewer: a route written as a bare path, a fact restated
instead of routed, a route that should exist and does not, the project named, a
project-specific resource list. A second script, `.github/check-method.py` (run through
`.github/check-method.sh`, by `ci.yml`'s `method` job), enforces the *structure* the routing
rule produces once it is followed — that every pointer resolves and every route lands — and is
described under [The layer frontmatter](#the-layer-frontmatter) below, since that frontmatter
is what tells it which files are the method's. Of the link shapes, an anchor, a title, an angle wrapper and a
leading `./` or `/` **are** caught; a reference-style link *definition* (`[wf]: docs/…`) is not,
nor is a link whose target is outside `docs/` — to a README, a lockfile, or a `.txt`. Those two
join the reviewer's list.

**The four boundaries**, in the order they get argued about:

- **An artifact may name another skill or agent.** They travel together — `.claude/` moves as
  one tree — so a cross-reference between them stays valid wherever the tree is installed, and
  routing it through `CLAUDE.md` would buy nothing.
- **An artifact may name `CLAUDE.md` and a topic in it.** A *named topic* — a routing-table
  entry or a `##` heading — is a
  specific target, so it meets *Scope the read* below and the checklists' "name the file, not
  'read the docs'" bar — which is why the topic is required and `CLAUDE.md` alone is not
  enough. What it costs is the onward hop only: `CLAUDE.md` itself is already loaded on every
  run (item 2 above), so resolving the pointer is the whole of the new work, and it buys a
  route every artifact inherits from a single edit. **Headings are the API, at two levels**,
  and this is the convention's only statement: the pointer is written `` `CLAUDE.md`'s
  **Topic** ``, naming a **topic** — an entry of `CLAUDE.md`'s routing table, or one of its own
  `##` headings — and never a heading of the document the topic routes to. A rule is
  addressed through its topic (*the branch-naming rule under `CLAUDE.md`'s **Issue
  conventions***), so a rule can move between documents or split without any pointer
  changing. The target shape of a document reached this way is `##` one topic, `###` one rule
  beneath it; the flow document's stages and the `adr` bar's worthiness topic have it,
  while the workflow reference still carries its rules as `##` sections and several routing
  entries name a whole document rather than a heading — the pointer form above is what makes
  reshaping them a change to those documents alone. `implement` writes "the branch-naming rule
  under `` `CLAUDE.md`'s **Issue conventions** ``" rather than naming the workflow document's
  own heading — that is the shape. Both directions of this convention are verified: the
  method check fails a pointer whose topic matches no routing-table entry and no `##` heading
  of `CLAUDE.md` (by prefix, so *Architecture Decision Records* still reaches *Architecture
  Decision Records (ADRs)*), and fails a routing-table entry whose document or heading does
  not exist — so a heading rename in `CLAUDE.md` breaks the build against every artifact
  pointing at it, rather than breaking those artifacts silently.
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
tree**: a reviewer checklist may name `docs/reference/` as a tree it reviews *and* route to the
one document inside it that carries its criteria, and both are right — a document does not
become subject matter by sitting in a reviewed tree. Where one and the same path is genuinely
both, subject matter wins and it stays named; the route is then redundant, not forbidden.

One category sits on that boundary often enough to have a recorded answer, so an author
meeting it does not have to re-derive it:

- **A reviewer agent's "what to read first" list is its checklist**, so it cannot simply be
  emptied of paths — a reviewer agent with no paths is not reusable but inert. The split
  above is the answer, and it is the one worked through on the `workflow` reviewer agent while
  it still held its own read-list: project
  documentation the agent reads for its criteria routes through the `CLAUDE.md` section owning
  that topic, while the trees the agent exists to review stay named, including in the
  frontmatter `description` that dispatches it — an agent that cannot say what it reviews cannot
  be dispatched to review it. Two rejected alternatives, so they are not re-proposed: moving
  the reviewer agents' read-lists into `CLAUDE.md` (it inflates the always-loaded prefix and
  inverts ownership — the agent knows what it needs to read, `CLAUDE.md` knows where topics
  live), and exempting reviewer agents wholesale (too wide: it would have excused an agent
  naming a document *and* the `CLAUDE.md` section that points at the same document).
  A third answer dissolves the tension rather than splitting it, and it is the one the
  per-label `work-types/` tree reaches: move the read-list into a work-type document, where
  naming a path is simply correct because the document does not travel, and leave under
  `.claude/` only a generic reviewer that resolves which document to read. This bullet
  governs a reviewer agent that still carries its own read-list; for one that does not, there
  is nothing left to split. The dispatchability claim above is bounded the same way: it holds
  for an agent reached by **description matching**, which is what needs the tree in the
  `description`. A generic reviewer is reached by **explicit dispatch** instead — the caller
  names the checklist, resolved from `CLAUDE.md`'s **Model selection** table — so it can say
  nothing about what it reviews and still be dispatched to review it.

**Permanent scope: as written or changed, never as a sweep.** This paragraph states the scope
of both rules on this page — the one above and the tracker rule below, which shares it rather
than restating it. The rule binds an artifact at the moment it is newly written, or changed for
some other reason — and it binds **what that change writes**: every pointer the change adds or
rewrites conforms, while prose the change leaves alone is owed no conversion. A typo fix is
therefore not a conversion trigger, and converting
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
the same reason the paragraph above puts them outside the project one.

**The carve-out: the commands an artifact exists to issue.** `submit-pr-review` and
`address-review-remarks` do not reach the review API on the way to somewhere else; they exist
*to drive* it, and it is what they are about. Genericising those
calls is not a trade of one line for a pointer — take the endpoints, the payload shape and the
thread semantics (which threads may be resolved, and when) out and nothing is left to state,
because there is no procedure underneath that was ever independent of the tracker. They name
them freely, and that is permanent, not pending.

**The carve-out is per command, not per artifact** — the project rule's test is applied per
path, not per tree, and this is the same move. What is carved out of one of those three is its
*review-API* calls; a tracker command it issues in passing on the way to or from a review —
applying a label, filing or reading a work item — is not its subject and routes like any
other. A carved-out artifact is therefore not a carved-out *file*, and "it drives the tracker"
is not a licence covering everything inside it.

**The test.** Does the artifact merely **record or read** work items in passing — file one,
comment on one, label one, look one up — so that the same step would still make sense on
another tracker? The rule applies; route the command. Or is **that tracker's API the thing the
artifact exists to operate**, so that removing the call removes the artifact's subject? The
carve-out applies; name it. This is the project rule's **What is not a route: subject matter**
line applied to commands instead of paths, not a second formulation — an author who has
settled which side a path falls on has already settled which side a command does.

**One source per mechanic, the carve-out included.** A carved-out call is the artifact's own
subject, so the artifact is the source of truth for its *substance* — what the operation says
and when it is legitimate. It is not thereby a source of truth for the **transport**: where
the same command exists in the reference behind **Tracker mechanics**, the reference wins, and
a copy inside a carve-out artifact that has drifted from it is a stale copy rather than a
second authority. Drift is the expected state rather than an anomaly, since the reference was
verified and corrected after those artifacts were written and nothing sweeps them. So an
author converting an artifact under this rule, or copying a command out of a carve-out
artifact into another artifact, takes it from the reference and checks the local copy against
it — then fixes or deletes that copy only if the artifact holding it is the one being changed, per
**Permanent scope: as written or changed, never as a sweep** above.

**Scope: the project rule's, unchanged.** It is stated once for both axes in **Permanent
scope: as written or changed, never as a sweep** above, and nothing about it is restated,
narrowed or extended here.

## The layer frontmatter

### A file's layer is a rule; `layer:` is the override

The process is three layers — a **method** that travels between repositories, a **profile**
that is this project alone, and **stack packages** declared in the profile — and which layer a
file belongs to follows from where it sits. Every document under `docs/reference/**` and every
agent definition under `.claude/agents/` is method. Every skill under `.claude/skills/` is
method unless `.claude/profile.yml`'s `dependencies` declares it, in which case it is a
vendored dependency that belongs to no layer of this project's and is never edited to say so —
that is what keeps an upstream-intact skill intact. A file that deviates from its tree's
default says so in YAML frontmatter, `layer: project` or `layer: stack` (`layer: method` is
legal and redundant), and nothing else carries the key: `docs/reference/profile.md` is the
standing case, a project file inside a method tree.

Where a *new* method document **goes** is a placement rule beside that one, and
`docs/reference/method/` is the answer: the method reference documents sit there, and
`docs/reference/` itself keeps only the profile's prose half and the work-type tree. The
tree-wide default above is deliberately wider than that directory — it makes a misplaced
method document method-layer anyway, so the check never reads bad placement as a layer claim
— which is why a method document found at the root of `docs/reference/` is **moved**, not
relabelled. One more position rule: a work-type
overlay, `docs/reference/work-types/<label>/overlays/<stack>.md`, is **stack** by where it sits
— a stack package installs it, and the method never edits it to say so — which is why
`layer: stack` as an override is reserved for a stack file found anywhere else. The layer
records what an installer would copy and what the check below scans: the work-type core files
are method, and their stack-specific sentences sit in the overlays beside them, where the check
requires them to be. `CLAUDE.md` and `.claude/profile.yml` carry no frontmatter; the first is
rewritten per repository and the second is the profile by path.

### The method check reads it

`.github/check-method.py` runs five repo-wide checks, numbered as its error lines number
them, each an agreement between files that are edited separately. **1, anchors outward:**
every pointer under `.claude/**`, `docs/**` and `.github/workflows/**` resolves to `CLAUDE.md`
(the outward direction stated under **Headings are the API** above; the two frozen trees,
`docs/postmortems/**` and `docs/archive/**`, are left out, since a document the rules say is
never revised cannot be the thing a blocking gate asks to edit). **2, anchors inward:** every
link and every repo-rooted backticked path resolves — in `CLAUDE.md` and in every file check 1
walks, minus the snapshot trees (the two frozen ones plus `docs/adl/**` and `docs/plans/**`,
dated records whose paths state what was true at their date rather than what the tree holds
now) — a link against the directory it is written in and an anchored one to a heading of its
target, a backticked path at the repository root and only when its first segment names
something there; and, in `CLAUDE.md` alone, every routing-table entry links to a document and
no `###` precedes its `##` there or in `docs/reference/**`. **3, profile
agreement:** the Model selection table agrees with the profile's `work_types.enabled` and
`labels.context` — the changed-path map is not this check's, but
`.github/check-path-map.py`'s, which holds it and the two CI enumerations to
`review.path_map`; the commit-prefix table of the
document `CLAUDE.md`'s **Definition of Done** topic routes to has a row for every enabled
context label;
`docs/reference/profile.md`
exists and has a **Flow** section, and every deviation it states — each `###` there — names
at least one work type in backticks, every one of them enabled. **4, work-type completeness:**
every enabled work type has its `review.md`, and its `implement.md` and `done.md` unless its
row says its work is `none`; every work type with a work file has a `### Skills` rule in it
naming only method skills and declared method dependencies; every work type with an overlay
slot has an `overlays/<stack>.md` for every declared stack, every stack a dependency declares
has a `stacks` entry, and an `overlays/` directory or file sits nowhere the slot rule does not
put it (the script header enumerates the shapes); every dependency declared
`installed: repo` is present; every `layer:` a file does carry names a known layer. **5, no
profile values in method files:** no value the profile holds — owner, repository name, board
name, node ids, a status column name — appears in a method-layer file; and no stack token the
profile lists under `stacks`, nor the name of a stack skill, appears in a method-layer file of
the work-type tree. Status names are
matched in the form a command would use them, inside backticks, or as the exact multi-word
phrase; the word in *Definition of Done* is English. The script's header is the authority on
each rule's exact shape and its stated limits. It runs blocking in CI and as a warning from
the local pre-commit hook, installed once per clone with
`git config core.hooksPath .github/hooks` — a `workflow` change mid-rename has to stay
committable, and the PR is where the finding is caught instead. Its fixtures,
`.github/test-check-method.sh`, break the layout one way per check and run before it in CI.

## Principles

- **Say what, point to where — one source of truth per fact.** An artifact carries the
  *decision procedure* and links to the source of truth rather than restating it; a duplicated
  instruction drifts apart from its twin, and each copy is read again by every run that needs
  it. `submit-pr-review` being "the single source of truth for the review payload" is the
  pattern: other artifacts reference it instead of duplicating the payload rules. (Drift is the
  main cost; the read cost is per use, not per cold session — see item 2 above.)
- **Scope the read.** Tell a run *which* file to read, so it doesn't fan out across `docs/`.
  The review worker already does this — one checklist per changed path, never all of them.
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
      each command per [Tracker-dependent mechanics route through
      `CLAUDE.md`](#tracker-dependent-mechanics-route-through-claudemd), unless that command is
      one the skill exists to issue — the carve-out is per command, so a skill that drives the
      tracker is not thereby exempt for the commands it issues in passing.
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

Every skill this project did not write itself is declared in `.claude/profile.yml`'s
`dependencies` — that manifest, not this paragraph, is the list. Four of them arrived by
**marketplace install** and are additionally recorded in `skills-lock.json` with their
upstream hash: `python-anti-patterns`, `async-python-patterns`, `ha-integration-knowledge`,
`domain-driven-design`. Two of them — `python-anti-patterns` and
`async-python-patterns` — have since been **rewritten for this repo**: trimmed to the rules that
apply to an async Home Assistant custom integration, and cross-linked so no rule is stated twice.
`ha-integration-knowledge` carries one local note (the custom-integration path mapping);
`domain-driven-design` is upstream-intact.

Two consequences:

- **`.claude/skills/` is the only authoritative tree.** It is what Claude Code loads and what
  every CI worker prompt names. The installer's second copy under `.agents/skills/` was an
  unreferenced byte-identical duplicate and has been removed; don't reintroduce it.
- **A re-sync from upstream would revert that work.** The `computedHash` entries in
  `skills-lock.json` describe where a skill came from, not what it must still contain — and
  the same hashes are declared as `sha256:` pins in `.claude/profile.yml`'s `dependencies`, the
  copy the method reads; the two move together, in the same PR. Before
  re-pulling any of them, check whether the local copy has diverged — for the two rewritten
  ones, re-apply the trim rather than accepting the upstream text.

Two obligations follow, and both are cheap only if they are met at the time:

- **A skill brought in from anywhere outside this repository gets its `dependencies` row in
  the same PR**, whether it was installed by the marketplace or adapted by hand. Nothing
  refuses an undeclared copy — the layer rule above reads an undeclared skill as the method's
  own, which is precisely the wrong answer for a file this project did not write, and it also
  leaves the copy out of the drift check that would otherwise tell you upstream had moved.
- **A drift report is answered by bumping the pin, whichever way the decision went** — the
  pin records that someone looked, not that the two trees are identical. The weekly check that
  opens such a report, and what closes it, are the CI document's (`CLAUDE.md`'s **Contribution
  workflow** topic routes to it).

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
