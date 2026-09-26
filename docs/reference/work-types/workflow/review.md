# Work type: `workflow` — the review checklist

**Who reads this.** The reviewer only — a fresh, read-only Opus agent, never the session that
wrote the change. This directory holds **only** this file: `workflow` has no work file and no
completion bar, because its work is never drafted from an issue and a human authors it by hand.
The document that `CLAUDE.md`'s **Model selection** section routes to argues why, and
`work-types/README.md` records the asymmetry as deliberate. The consequence for you is that
there is no bar to fall back on: this file is the whole of the criteria for a `workflow`
review, which is why it carries a full checklist where other labels' review documents carry
only what their bar cannot.

The output format, the severity grouping, the anchoring rules and the untrusted-data rule are
not here. They are the same for every review and live with the generic `reviewer` agent
definition, which reaches this file through `CLAUDE.md`'s **Model selection** table. Your own
handling of untrusted material is stated there and once; check **(1)** below is about containment in the artifact under review, which is
a different question with the same subject.

## What this label covers

A change to this project's process and to the files that drive its runs — a skill
(`.claude/skills/`), an agent definition (`.claude/agents/`), a CI workflow
(`.github/workflows/`), the project profile and the two scripts that read it
(`.claude/profile.yml`; `.github/setup-labels.sh`, which writes its `labels` to the
repository; `.github/profile-env.sh`, which prints its tracker values for the reference's
recipes), an issue form
(`.github/ISSUE_TEMPLATE/`), the harness configuration that decides what a run may do
(`.claude/settings.json` and the hooks it wires, `.claude/hooks/`) — which is why the committed
settings file is the restricted one and `settings.local.json` is the ignored one, as
`.gitignore` says at the line — or the canonical process reference (`docs/reference/`,
`CLAUDE.md`). A workflow runs with repository secrets
and a write-scoped `GITHUB_TOKEN`, and a skill or agent steers a run that reads untrusted issue
and PR content with write access to the repository, so this checklist weighs security at least
as heavily as quality. An issue form carries no
credentials itself but can still point at load-bearing process semantics (e.g. `adr.yml`
linking to the ADR worthiness test) that must stay in sync with what it references.

## What to read first

Always read:

- The changed files.
- `docs/reference/method/ai-authoring.md`, which `CLAUDE.md`'s **Authoring AI artifacts** section
  routes to — the shared vocabulary, the checklist for each artifact type (skill / agent), and
  its non-negotiables. A work-type document under
  `docs/reference/work-types/<label>/` is one of these artifacts even though it is not a skill;
  that reference's own opening says how far it binds one and which checklist to apply, and its
  scope is the label directories — not this tree's own `README.md`, which that file says is an
  ordinary reference document outside the rule's subject matter.
- If a changed file is `.claude/settings.json` or under `.claude/hooks/`: the other half of
  the pair — the wiring names the script, the script is what the wiring runs, and a review of
  one that never opened the other cannot tell whether the guard still fires — together with
  its test suite, and the rule it mechanizes, which is
  `docs/reference/method/contribution-workflow.md`'s **Commit & push authorization**.
- If a changed file is under `.github/ISSUE_TEMPLATE/`: `.claude/profile.yml`'s `labels` (the
  set `.github/setup-labels.sh` writes), plus
  `docs/reference/method/contribution-workflow.md`'s **Issue conventions** — the canonical
  context-label vocabulary, to check the form's `labels:` value against it — and
  `docs/reference/method/ci-pipeline.md`'s **Label vocabulary sync**, to check the other places
  the vocabulary is baked into stay in step; and, for `adr.yml`, the document `CLAUDE.md`'s
  **Architecture Decision Records (ADRs)** topic routes to, since the form links to it.

## Review checklist

**(1) Prompt-injection containment in the reviewed artifact (Critical if missing)**
- Any skill, agent or workflow step that feeds issue/PR/commit content to a model explicitly
  labels that content as untrusted data, not instructions, and states what to do if it tries
  to redirect behavior (record as a finding / attempted injection, never comply).
- Any job that writes files or commits from untrusted input constrains what it can actually
  commit by a mechanism (a path allow-list, a token scoped to what the job may write) — not
  solely a prompt-level instruction. A prompt-only constraint is not defense in depth; flag
  its absence as Critical.
- No change widens an existing containment boundary (a path allow-list, a tool grant, a
  fork-PR guard) without the PR explaining why the wider blast radius is safe.

**(2) Least privilege**
- Tool grants — an agent definition's `tools`, a `permissions.allow` entry, a workflow step's
  own grant — are the minimum the task needs.
- Job `permissions:` blocks grant only what that job's steps use; a job that only needs to
  comment does not get `contents: write`.
- A secret is read only by the step that uses it; no new step reads one into a log-visible
  context (`echo`, unquoted interpolation into a shell command that could be echoed).

**(3) Fork-PR / trust boundary**
- A job that holds a secret or can push commits keeps (or, if this change touches that logic,
  correctly preserves) the guards that keep a fork PR out of it: `pull_request` not
  `pull_request_target`, and any sender or head-repository check the job carries.
- If the change widens a trigger (a new event, a wider path filter), confirm the newly
  in-scope events don't let a fork PR reach a job holding a secret or write access it
  couldn't reach before.

**(4) Authoring checklist (per artifact type)**
- Apply the matching checklist section (skill / agent) of
  `docs/reference/method/ai-authoring.md` to the changed file(s) — or, for a work-type document, the
  skill checklist as that reference scopes it.
- The harness configuration has no section there, deliberately — that reference says why, and
  routes its criteria here. So judge a change to `.claude/settings.json` or `.claude/hooks/`
  on these instead. **Every fall-through to "permit" is argued where it happens.** The guard
  this project ships is an accident guard and not a sandbox — it says so in its own header,
  and it fails *open* on an input it cannot parse, with the reasoning written at the line it
  happens. That is a decision, not a defect, and this item does not reopen it: what it scores
  is a fall-through that is **undocumented at the line it happens, taken without saying so on
  input the guard could not parse, or newly introduced by the diff** — Critical, since a guard
  that quietly permits what it did not understand reads as enforcing a rule it is not. A
  permit the guard reached on input it *did* parse — an unlisted subcommand of a family it
  watches — is in scope by its header, not a silent fall-through. Widening an existing one is
  checked as a widening, below.
  **The change is carried by the guard's own test suite**, extended in the same diff that adds
  or narrows a refusal — a behaviour change with no test is Major, since nothing else
  exercises the script.
  **The wiring and the tree still match**: every command `settings.json` names resolves to a
  file that exists, and every script under `.claude/hooks/` that is meant to run as a hook is
  wired — which is not every file there, a `test-*` harness being a suite run by hand from the
  repo, not a hook. A hook silently unwired is Critical; the rule it enforces reads as enforced and
  is not.
  **Nothing widens what a run may do without asking** — a new `permissions.allow` entry, a
  matcher narrowed so fewer calls reach the guard — without the PR explaining why, per
  **(1)**'s last bullet, which governs this file as much as a workflow's.
- One source of truth per fact: a rule duplicated across skills/agents/prompts instead of
  linked from one is a Minor finding (Major if the duplicate has already drifted).
- *Clutter*, the Vocabulary entry in `docs/reference/method/ai-authoring.md`: its narrative and
  oversized-example forms are judged by that entry, at its severities. Its restatement form is
  not scored here: the item above, or the item below that begins *The same rule read the other
  way*, governs it — whichever covers the owner — at that item's severities.
- A work-type core file (any `.md` under `docs/reference/work-types/`, branch files included,
  outside an `overlays/` directory) names no stack skill and
  spells no stack token — the method check refuses both, and `work-types/README.md`'s **Stack
  overlays** says where such material goes. An overlay that restates a method rule rather than
  extending one is the one-source-of-truth finding above, hidden in a file the method cannot
  see; a core file that reads *the stack overlay names it* with no overlay entry that does is
  a broken route — Major, since the rule then has no home.
- The context-label vocabulary's values are
  `docs/reference/method/contribution-workflow.md`'s and the sync obligation — every place that
  vocabulary is baked into and must move together — is
  `docs/reference/method/ci-pipeline.md`'s. A change to one place that doesn't update the rest is a
  Major finding (silent drift in the vocabulary the label-keyed routing trusts).
- If a changed file is under `.github/ISSUE_TEMPLATE/`: its frontmatter `labels:` value is a
  label `.claude/profile.yml`'s `labels` defines — one of the canonical context labels above, or the
  pre-triage `idea` label for `idea.yml` (a form advertising a label that doesn't exist yet is a
  Major finding); and any process claim the form's body makes (e.g. `adr.yml` linking to the
  document `CLAUDE.md`'s **Architecture Decision Records (ADRs)** topic routes to) still
  matches what that reference currently says.
- The issue-to-merge lifecycle is the document `CLAUDE.md`'s **Contribution workflow** topic
  routes to; `CLAUDE.md` and every skill's "Follows this project's contribution workflow" line
  only point to it, never restate its steps. When any of the docs `CLAUDE.md` links there change,
  cross-check their claims about a skill's, hook's or script's behavior (commit-prefix mapping,
  branch scheme, the review cap) against that file's actual current behavior — a
  plausible-sounding claim that drifted from what the file actually does is a Major finding.
- Every pointer a changed skill or agent definition writes to project material is in the
  `` `CLAUDE.md`'s **Topic** `` form, and the topic resolves — to an entry of `CLAUDE.md`'s
  routing table or one of its `##` headings. A pointer naming the owning document's heading
  directly, or a topic that resolves to nothing, is a Minor finding — Major where it is the
  only route to something the artifact must read. The heading shape of the routed documents is
  not this item's to score: the convention, and where that shape is and is not yet reached, is
  stated once in `docs/reference/method/ai-authoring.md`; this item checks the pointer, not the
  target.
- The same rule read the other way, and one of the shapes `docs/reference/method/ai-authoring.md`
  names as the residue its check cannot decide: a rule or path the diff **states** where
  another file owns it, with no pointer written at all — so there is no link to catch and no
  pointer to fail. Where that owner is another skill, agent or prompt, the one-source-of-truth
  item above governs and its severities are the ones to apply; this item is for the owners it
  does not name — a reference document, `CLAUDE.md` itself, the profile — and for work-type
  documents, which it does not name either. Read what the diff adds and ask: is this prose
  restating something whose home is elsewhere, in place of a `` `CLAUDE.md`'s **Topic** ``
  pointer to it? Where no topic owns the material yet, the fix is the routing line added to
  `CLAUDE.md`, never the fact inlined here — an author who found no topic and wrote the fact
  instead is the case this item exists for. Minor where a pointer to the owner is already
  there and the inlined copy is redundant beside it; Major where it is the artifact's only
  statement of the rule, since it then has no owner to be checked against and drifts unseen.
  Scoped to what the diff writes, per that reference's **Permanent scope: as written or
  changed, never as a sweep** — a finding raised against untouched prose is out of scope.

**(5) Non-negotiables unaffected**
- Write and review still happen in separate sessions/agents (a skill or workflow must never
  have the same run draft and review its own output).
- Model tiering by task is preserved (Opus for analysis/design/ADR/this-review-itself; Sonnet
  for code), not downgraded for cost.
- No change removes or weakens the maintainer manual-approval-before-merge gate.
