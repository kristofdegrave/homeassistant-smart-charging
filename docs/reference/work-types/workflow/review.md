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
not here. They are the same for every review and live with whoever applies this checklist — the
generic `reviewer` agent definition locally, the review workflow's own prompt in CI, which has
no agent to spawn and self-applies instead. Both reach this file the same way, through
`CLAUDE.md`'s **Model selection** table. Your own handling of untrusted material is stated
there and once; check **(1)** below is about containment in the artifact under review, which is
a different question with the same subject.

## What this label covers

A change to this project's AI pipeline itself and the process docs it is driven by — a skill
(`.claude/skills/`), an agent definition (`.claude/agents/`), a CI workflow
(`.github/workflows/`), the project profile and the two scripts that read it
(`.claude/profile.yml`; `.github/setup-labels.sh`, which writes its `labels` to the
repository; `.github/profile-env.sh`, which prints its tracker values for the reference's
recipes), an issue form
(`.github/ISSUE_TEMPLATE/`), or the canonical process reference (`docs/reference/`,
`CLAUDE.md`). The workflow, skill and agent files run with write-scoped credentials
(`ANTHROPIC_API_KEY`, a write-scoped `GITHUB_TOKEN`/PAT) against untrusted issue and PR content,
so this checklist weighs security at least as heavily as quality. An issue form carries no
credentials itself but can still point at load-bearing process semantics (e.g. `adr.yml`
linking to the ADR worthiness test) that must stay in sync with what it references.

## What to read first

Always read:

- The changed files.
- `docs/reference/method/ai-authoring.md`, which `CLAUDE.md`'s **Authoring AI artifacts** section
  routes to — the shared vocabulary, the checklist for each artifact type (skill / agent /
  CI worker prompt), and its non-negotiables. A work-type document under
  `docs/reference/work-types/<label>/` is one of these artifacts even though it is not a skill;
  that reference's own opening says how far it binds one and which checklist to apply, and its
  scope is the label directories — not this tree's own `README.md`, which that file says is an
  ordinary reference document outside the rule's subject matter.
- If a changed file is a CI workflow: `.github/workflows/ai-pipeline.yml` (the router — label
  guards, fork-PR handling, permissions-per-job) for context on how the changed file fits.
- If a changed file is a CI workflow, a skill (`.claude/skills/`), or an agent definition
  (`.claude/agents/`): `docs/reference/method/ci-pipeline.md`, for each job's stated scope
  (draft/review/fix are one task each) and the `needs-*` label contract.
- If a changed file is under `.github/ISSUE_TEMPLATE/`: `.claude/profile.yml`'s `labels` (the
  set `.github/setup-labels.sh` writes), plus
  `docs/reference/method/contribution-workflow.md`'s **Issue conventions** — the canonical
  context-label vocabulary, to check the form's `labels:` value against it — and
  `docs/reference/method/ci-pipeline.md`'s **Label vocabulary sync**, to check the CI-side files stay
  in step; and, for `adr.yml`, the document `CLAUDE.md`'s **Architecture Decision Records
  (ADRs)** topic routes to, since the form links to it.

## Review checklist

**(1) Prompt-injection containment in the reviewed artifact (Critical if missing)**
- Any worker prompt that feeds issue/PR/commit content to Claude explicitly labels that
  content as untrusted data, not instructions, and states what to do if it tries to redirect
  behavior (record as a finding / attempted injection, never comply).
- Any drafter-style job (writes files from untrusted input) constrains what it can actually
  commit via an allow-list mechanism (e.g. `add-paths` scoped to the artifact type's own
  tree) — not solely a prompt-level instruction. A prompt-only constraint is not defense in
  depth; flag its absence as Critical.
- No change widens an existing containment boundary (an `add-paths` scope, an `--allowed-tools`
  grant, a fork-PR guard) without the PR explaining why the wider blast radius is safe.

**(2) Least privilege**
- `--allowed-tools` / tool grants are the minimum the task needs, each with a comment saying
  why (the authoring checklist's CI-worker section).
- Job `permissions:` blocks grant only what that job's steps use; a reviewer/drafter job that
  only needs to comment does not get `contents: write`.
- Secrets stay behind the `ai` environment; no new step reads a secret into a log-visible
  context (`echo`, unquoted interpolation into a shell command that could be echoed).

**(3) Fork-PR / trust boundary**
- A job that can spend `ANTHROPIC_API_KEY` or push commits keeps (or, if this change touches
  that logic, correctly preserves) the existing guards: `pull_request` not
  `pull_request_target`, the sender-is-maintainer check, and — for jobs with `contents: write`
  — the `head.repo.full_name == github.repository` fork exclusion.
- If the change extends a path filter (`ai-pipeline.yml`'s `on.pull_request.paths` or
  similar), confirm the newly in-scope paths don't let a fork PR trigger a privileged job it
  couldn't reach before.

**(4) Authoring checklist (per artifact type)**
- Apply the matching checklist section (skill / agent / CI worker prompt) of
  `docs/reference/method/ai-authoring.md` to the changed file(s) — or, for a work-type document, the
  skill checklist as that reference scopes it.
- One source of truth per fact: a rule duplicated across skills/agents/prompts instead of
  linked from one is a Minor finding (Major if the duplicate has already drifted).
- A work-type core file (any `.md` under `docs/reference/work-types/`, branch files included,
  outside an `overlays/` directory) names no stack skill and
  spells no stack token — the method check refuses both, and `work-types/README.md`'s **Stack
  overlays** says where such material goes. An overlay that restates a method rule rather than
  extending one is the one-source-of-truth finding above, hidden in a file the method cannot
  see; a core file that reads *the stack overlay names it* with no overlay entry that does is
  a broken route — Major, since the rule then has no home.
- The context-label vocabulary's values are
  `docs/reference/method/contribution-workflow.md`'s and the CI-side sync obligation — every pipeline
  place that vocabulary is baked into and must move together — is
  `docs/reference/method/ci-pipeline.md`'s. A change to one place that doesn't update the rest is a
  Major finding (silent drift in the vocabulary the whole label-driven pipeline trusts).
- If a changed file is under `.github/ISSUE_TEMPLATE/`: its frontmatter `labels:` value is a
  label `.claude/profile.yml`'s `labels` defines — one of the canonical context labels above, or the
  pre-triage `idea` label for `idea.yml` (a form advertising a label that doesn't exist yet is a
  Major finding); and any process claim the form's body makes (e.g. `adr.yml` linking to the
  document `CLAUDE.md`'s **Architecture Decision Records (ADRs)** topic routes to) still
  matches what that reference currently says.
- The issue-to-merge lifecycle is the document `CLAUDE.md`'s **Contribution workflow** topic
  routes to; `CLAUDE.md` and every skill's "Follows this project's contribution workflow" line
  only point to it, never restate its steps. When any of the docs `CLAUDE.md` links there change,
  cross-check their claims about `_ai-draft.yml`/`_ai-review.yml`/`_ai-fix.yml` behavior
  (commit-prefix mapping, branch scheme, loop caps) against those files' actual current
  behavior — a plausible-sounding claim that drifted from what the workflow doc actually does
  is a Major finding.
- Every pointer a changed skill or agent definition writes to project material is in the
  `` `CLAUDE.md`'s **Topic** `` form, and the topic resolves — to an entry of `CLAUDE.md`'s
  routing table or one of its `##` headings. A pointer naming the owning document's heading
  directly, or a topic that resolves to nothing, is a Minor finding — Major where it is the
  only route to something the artifact must read. The heading shape of the routed documents is
  not this item's to score: the convention, and where that shape is and is not yet reached, is
  stated once in `docs/reference/method/ai-authoring.md`; this item checks the pointer, not the
  target.
- The same rule read the other way, and one of the shapes `docs/reference/ai-authoring.md`
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
- If a changed skill (`.claude/skills/`) or agent definition (`.claude/agents/`) runs in an
  interactive session, it must never instruct adding `needs-draft`/`needs-review`/`needs-work`
  itself — per `docs/reference/method/ci-pipeline.md`, those are CI-only triggers; an interactive
  session does review/fix locally instead. Flag as Major (silently hands work to CI the human
  didn't ask for, and can collide with CI's own loop-cap accounting).

**(5) Non-negotiables unaffected**
- Write and review still happen in separate sessions/agents (a skill or workflow must never
  have the same run draft and review its own output).
- Model tiering by task is preserved (Opus for analysis/design/ADR/this-review-itself; Sonnet
  for code), not downgraded for cost.
- No change removes or weakens the maintainer manual-approval-before-merge gate.
