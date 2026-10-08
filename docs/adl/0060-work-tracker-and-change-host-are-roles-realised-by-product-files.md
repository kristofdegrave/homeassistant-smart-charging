# ADR-0060: Work tracking and change review are two roles, defined by a concept document and realised by per-product files

Date: 2026-10-08
Status: Accepted

## Summary

In the context of a method whose steps drive GitHub directly, facing a project that tracks in
Jira and reviews on GitHub, we decided on Options A3, B2, C2, D2 and E2 — two roles, product
files that say only how, concepts Jira fits, closing and gates in step skills, a guard that
fails closed — to keep one method across products, accepting that an MCP server update stops
work until the host file classifies its new tools.

## Context

- **The method speaks GitHub.** Step skills, `contribution-workflow.md` and the git guard spell
  `gh` commands, label names, board columns and the `Closes #N` keyword into their rules;
  `tracker-mechanics.md` holds most, but not all, of the commands.
- **The first second target pairs two products**: GitHub reviews changes, Jira tracks work. The
  exit labels already mean one thing on a pull request and another on an issue.
- **Jira differs in shape, not only in commands**
  ([research](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/1517#issuecomment-6062585228)):
  fixed hierarchy levels, more only on paid tiers; statuses configured per site within three
  categories; labels, components and custom fields whose ids differ per site; nothing transitions
  on merge unless an automation is configured; reached through Atlassian's MCP server, `acli` or
  REST.
- **MCP exists only inside a session.** CI check scripts and the `PreToolUse` guard run outside
  one, so they need a CLI or REST route to any product they read.
- **The merge rule is enforced by a hook** (ADR-0052) that can only refuse a merge it
  recognises; today it matches `gh pr merge`.
- **The method travels between repositories** as its own layer; a rule copied into each
  product's text drifts between the copies.

## Considered options

### A — Where the product boundary sits

**A1 — Keep the method on GitHub** (status quo).
- Pro: nothing to change; every rule stays next to its command.
- Con: a Jira project rewrites the method, not a file.

**A2 — One "forge" role** covering tracking and review together.
- Pro: one product file per project.
- Con: GitHub + Jira needs a third, mixed file, and every pairing another.

**A3 — Two roles, work tracker and change host**, each realised by its own product file and
selected separately in the profile.
- Pro: any tracker pairs with any host; the pairing the first target needs is a profile line.
- Con: two files to keep complete per product, and a concept on the seam (closing on merge)
  needs an owner on each side.

### B — What a product file holds

**B1 — A product variant of the method**: each product file restates the steps it touches.
- Pro: a reader sees one product's whole flow in one place.
- Con: the rule lives in as many copies as there are products, and they drift.

**B2 — How, never whether or when.** A method concept document has one `##` heading per
concept, stated semantically ("awaiting human approval", not "a label") and marked required or
optional. Each product file carries the same headings with its commands, conventions and
fallback, an access section (channel, tools, fallback), and setup sections a project opts into
(the GitHub board, CI wiring). The profile carries an instance's mapping — status names, field
ids. The method check fails a product file that neither covers nor declares absent a heading.
- Pro: each rule has one copy; the headings are a contract a check can test.
- Con: a reader follows a step through two files, and every concept must be named before a
  product file can say how.

### C — The concepts' shape

**C1 — GitHub's shapes, renamed**: one label vocabulary for context, free nesting, a mandatory
board.
- Pro: the GitHub product file is a rename.
- Con: Jira's fixed levels, per-site fields and optional estimation do not fit, so the first
  Jira file reopens the concepts.

**C2 — Shapes Jira also fits**: context is three concepts — work type (the Model selection
row), level (idea, epic, task), kind (bug, enhancement) — each mapped per product; exactly two
levels, epic → task, a strand too large for one epic becoming sibling epics; the board (Size,
Estimate, Status, Priority) is an optional tracker capability the profile declares.
- Pro: maps onto GitHub sub-issues and Jira Epic → Story without a paid tier.
- Con: no nested epics, and every board rule applies only where the profile declares the board.

### D — Closing on merge, and CI

**D1 — The host closes the item** through a reference keyword, and gates that live only in CI
stay there.
- Pro: today's mechanism, unchanged on GitHub.
- Con: Jira closes nothing on merge by default, and a gate held only by one CI product is lost
  on another.

**D2 — The method holds both.** `cleanup` reads the item's state after the merge and closes it
if open; the tracker file owns the reference syntax, the host file where it goes. CI is not a
role: "are this change's checks green" is a host concept, the method's checks are portable
scripts wired into a CI product by a setup section, and every CI-only gate also gets a home in
a step skill.
- Pro: closing and gating work on any pairing.
- Con: outside a session, a gate holds only where the project wired it into its CI.

### E — The merge guard

**E1 — One guard per host**, matching that host's merge commands.
- Pro: simple, and today's shape.
- Con: the destructive-git half is copied per host, and an MCP merge tool the list omits
  passes.

**E2 — Split, failing closed.** The method half keeps the destructive-git refusals and states
the merge rule as product-neutral conditions; the host file names which commands and MCP tools
merge and how each condition is read; the profile selects the host. Every tool of the host's
MCP server is classified merge or not merge, and an unclassified tool, or an unknown host, is
refused.
- Pro: a new merge path is refused until classified, not let through.
- Con: an MCP server update stops work until the host file classifies its new tools.

## Decision

**Options A3, B2, C2, D2 and E2**, each for the Cons its rivals carry above; each chosen
option's Con is accepted.

One record, not five: A3 creates the product files, B2 says what may go in them, C2 is what
makes B2's headings hold for Jira, and D2 and E2 are the two places where a rule today held by
GitHub itself — its close keyword, its CI, its command name — would otherwise leave the method
with the product. This record does not decide what a milestone means; ADR-0052 still does.

## Consequences

- **Follow-up**: the concept document; a GitHub work-tracker file, with the board as an
  opt-in setup section; a GitHub change-host file, with CI wiring and release setup; the profile
  selecting a product per role, and the method check's coverage rule; the contribution workflow,
  step skills, filing and decomposition, and the autopilot rewritten against concepts; `cleanup`
  closing the item and taking the close guard's rule; the guard split.
- **`tracker-mechanics.md` becomes the GitHub product files' content.** "Never `gh issue
  close`" leaves the method.
- **The autopilot's settings allow-list each product's MCP tools**, under ADR-0054's model.
- **Easier**: a second product is one file per role and a profile mapping. **Harder**: every new
  method rule that touches a product names its concept first, and a project without CI wiring
  has no gate outside a session.
- **`docs/design/system-design.md` §8.3** gains a process row when it reconciles the records
  after ADR-0051.

**Blast radius.** One search, run from the repository root:

```sh
rg -n --hidden --glob '!.git/' --glob '!docs/adl/**' --glob '!docs/postmortems/**' \
  --glob '!docs/archive/**' --glob '!CHANGELOG.md' \
  -e '\bgh [a-z]+\b|gh-as-bot|Closes #' .
```

Wide enough because the repository reaches its own tracker and host in three ways only — the
`gh` CLI, the bot wrapper around it, and GitHub's close keyword — and no MCP server is
configured; `.github/check-upstream-drift.py` calls GitHub's REST API directly, but for
upstream dependencies' releases, which no role covers. Concept
vocabulary (label and column names) is the concept document's inventory, not a product call.
It returns **686** hits on `origin/main`.

| Site | Today | Follow-up |
|---|---|---|
| `.claude/hooks/block-destructive-git.sh` (131) and `.claude/hooks/test-block-destructive-git.sh` (318) | One guard matches `gh` merge and approval commands beside the destructive-git refusals | Split into the method half and the GitHub host half, failing closed |
| `docs/reference/method/contribution-workflow.md:210`, `:220`, `:221`, `:245`, `:321` | State `Closes #N`, "never `gh issue close`" and `gh pr merge` as method rules | Restated as concepts; the syntax moves to the product files |
| `CLAUDE.md:20`, `:25` | Name `gh pr merge` and gh refusals in a method rule | Name the merge concept |
| `.github/workflows/close-guard.yml:41`, `:56`, `:71` | Hold the docs-only close rule in CI alone | The rule moves into `cleanup`; the workflow may stay as its GitHub wiring |
| `.github/check-source-lines.py:23`, `:102`, `:106`; `.github/test-check-source-lines.sh:163` | A method check fetches the issue through `gh api` | Reaches the tracker through its product file's CLI/REST route |
| `docs/reference/work-types/adr/implement.md:21` | Reserves the number with `gh api` | Names the host's branch-creation concept |
| `.claude/skills/fix/SKILL.md:30`, `:35`; `research/SKILL.md:3`, `:16`, `:44`; `file-task-issue/SKILL.md:9`; `autopilot/SKILL.md:9`; `resolving-merge-conflicts/SKILL.md:62`; `submit-pr-review/SKILL.md:63` | Step skills spell `gh` commands or `Closes #` | Rewritten against concepts, the commands moving to the product files |

213 hits conform: `tracker-mechanics.md` (87), the bot wrapper and its test (23) and its CI
step (1), `setup-labels.sh` (8), `upstream-drift.yml` (8) and `release.yml` (2) are GitHub-side
content or wiring; `profile.md` (10), `profile.yml` (2) and `.claude/settings.json` (69) are the
instance and harness side; `ai-authoring.md:281` states this rule's principle;
`CLAUDE.md:63` and `workflow/review.md:23` name a path. The excluded trees keep their dated
text; this record and its ADL row fall in that exclusion.
