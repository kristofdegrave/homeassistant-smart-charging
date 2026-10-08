# ADR-0060: Work tracker and change host are two roles, defined by a concept document and realised by per-product files (narrows ADR-0054)

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
- **The next target pairs two products**: GitHub reviews changes, Jira tracks work. The
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
nesting levels, epic → task, a strand too large for one epic becoming sibling epics; the board
(Size, Estimate, Status, Priority) is an optional tracker capability the profile declares.
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

- **Follow-up**: the concept document; a GitHub work-tracker file, the board an opt-in setup
  section; a GitHub change-host file, with CI wiring and release setup; the profile selecting a
  product per role, and the method check's coverage rule; the rewrites the Blast radius rows
  list.
- **`tracker-mechanics.md` splits**: its commands become the GitHub product files' content, its
  rules move into the method. `contribution-workflow.md`'s "never `gh issue close`" leaves the
  method.
- **ADR-0054 is narrowed**, not superseded: A3's one author test moves from beside the tracker
  recipe into the method, the product file keeping how the write-access association is read.
  The autopilot's settings allow-list each product's MCP tools under its model.
- **ADR-0052 is not narrowed**: E2 keeps its B2 merge conditions, their C2 guard and its
  accident-guard Con, moving only which commands and tools merge, and how each condition is
  read, into the host file.
- **Easier**: a second product is one file per role and a profile mapping. **Harder**: every new
  method rule that touches a product names its concept first, and a project without CI wiring
  has no gate outside a session.
- **`docs/design/system-design.md` §8.3** gains a process row when it reconciles the records
  after ADR-0051.

**Blast radius.** One search, run from the repository root:

```sh
rg -n --hidden \
  -e '\bgh\b|GitHub|GraphQL|\bREST\b' \
  -e '(?i:\bclos(e[sd]?|ing)\b)|Part of\b' \
  -e '(?i:\blabel)|needs-approval|needs-decision' \
  -e '(?i:\bboard\b|backlog|\bin (review|progress)\b|sub-issue)|\*done\*|\bSize\b|\bEstimate\b' \
  CLAUDE.md .claude/ .github/ docs/reference/
```

Wide enough because each pattern covers one thing the decision moves, prose words in any case
and names as spelt: how the method reaches a product — `gh` however spelt, its bot wrapper,
GitHub and its APIs (A3, B2, E2); closing in every form and the reference keywords (D2); the
labels its gates and routing key on (C2); the board by field and column (board-Status lines
all lie in hit files), and C2's nesting. Issue, PR and epic are concept names the concept document
may keep. No MCP server is configured. Outside the four paths the patterns find no site: code,
tests, analysis, design and README use the words in a plain, Home Assistant or domain sense or
recount a past record, as §8.3's ADR-0048 row does; `CHANGELOG.md`, `docs/postmortems/` and
`docs/adl/`, this record included, are dated text. It returns **1907** hits on `origin/main`.

| Site | Today | Follow-up |
|---|---|---|
| `.claude/hooks/block-destructive-git.sh` (272) and its test (420) | One guard matches `gh` merge, approval and label commands beside the destructive-git refusals | Split into the method half and the GitHub host half, failing closed |
| `docs/reference/method/tracker-mechanics.md` (162) | GitHub commands, with method rules among them — the author test | Commands into the GitHub product files, rules into the method |
| `docs/reference/method/`: `contribution-workflow.md` (105), `ci-pipeline.md` (71), `idea-to-product.md` (45), `model-selection.md` (21), `ai-authoring.md` (16), `definition-of-done.md` (6), `source-lines.md` (4) | State labels, board fields and columns, sub-issue nesting, the close keywords and rules, and `gh` commands as method rules | Restated as concepts; label, field and syntax move to the product files |
| `CLAUDE.md` (24) | Keys Model selection by context label; names `gh pr merge`, `gh` refusals and board fields in method rules | Keyed by work type; names the concepts |
| `docs/reference/work-types/` (152, in 24 files), and its overlay path in `profile.md` and `profile.yml` (2) | Keys its directories and rules by context label; `decompose` parks with `needs-approval`, sub-issue edges and Size | Keyed by work type; gates and edges named as concepts |
| `.claude/skills/` and `.claude/agents/` (149, in 15 files) | Step skills spell `gh` commands, `Closes #`, labels, board moves and who closes an item | Rewritten against concepts, the commands moving to the product files; `cleanup` closes the item |
| `.github/workflows/close-guard.yml` (28) | Holds the docs-only close rule in CI alone | The rule moves into `cleanup`; the workflow may stay as its GitHub wiring |
| `.github/check-source-lines.py` (8) and its test (8) | A method check fetches the issue through `gh api` | Reaches the tracker through its product file's CLI/REST route |
| `.github/check-method.py` (67) and its test (24) | Checks the profile's context labels against the Model selection rows | Checks work types, and gains the product-file coverage rule |
| `.github/workflows/upstream-drift.yml` (17), `check-upstream-drift.py` (7) and its test (1) | Files and updates its report issue outside a session via `gh issue` and the `workflow` label; the report expects a closing PR and GitHub's body format | Reaches the tracker through its product file's CLI/REST route, the label mapped to the work type; its upstream commit reads are no role's |

269 hits conform: the bot wrapper, its test and its CI step (34), `setup-labels.sh` (38), the
issue forms (34), `release.yml` (3), `release-please.yml`, `dependabot.yml` and `SECURITY.md` (1
each) are GitHub-side content or wiring; `profile.md` (57), `profile.yml` (25), `profile-env.sh`
(6) and `.claude/settings.json` (69) are the instance and harness side. Out of scope: 29 hits
keep a non-tracker sense — the `domain-driven-design` skill (9), `.claude/vendor/` (4), two
badge labels in `ci.yml` and `coverage.yml`, the flow's closing step and a closed set in
`decomposition-checklist.md` (10) and `decompose/review.md` (1), a fail-closed gate in
`check-authoring-rules.sh` (1), and a close in `async-python-patterns` and
`python-anti-patterns` (1 each).
