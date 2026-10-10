# ADR-0061: A milestone is a release scope, and priority is its own optional concept (narrows ADR-0052)

Date: 2026-10-10
Status: Accepted

## Summary

In the context of a picker ordering work by milestone, facing a flow that ships per release and
trackers that keep release and priority apart, we decided on Option C — a milestone is a release
scope, priority an optional concept, the picker taking the earliest open release, then priority,
else the oldest unblocked issue — to give each concept one meaning on every tracker, accepting
that a project without the board ranks within a release by age alone.

## Context

- **A milestone is the method's priority today**
  ([ADR-0052](0052-autopilot-gates-auto-merge-by-tree-milestones-as-priority.md), Option D2):
  ranked by a numeric title prefix, unprefixed milestones tying and the tie going to the human
  through `clarify`, a roadmap session prefixing them. No open milestone carries a prefix, so
  every pick across milestones is such a tie.
- **The flow is gaining a Ship stage** that cuts a release per milestone, so a milestone has to
  say what ships together; how Ship runs is a record of its own.
- **Trackers keep release and priority apart**: Jira has Fix Version beside priority and rank.
  [ADR-0060](0060-work-tracker-and-change-host-are-roles-realised-by-product-files.md) makes
  the board, with a Priority field, an optional tracker capability and leaves what a milestone
  means to ADR-0052.
- **GitHub orders milestones only by due date**; none of the open ones has one.

## Considered options

### Option A — Keep milestones as ordered priority (ADR-0052's D2)

- Pro: nothing changes; the rule and the filing skills already carry it.
- Con: one field means both "ships together" and "goes first", and Jira's Fix Version means
  only the first.
- Con: the order rests on a hand-held prefix and a roadmap session that has not been held.

### Option B — A milestone is a release scope, and release order is the only order

- Pro: one concept, mapping onto Fix Version, with no board needed.
- Con: within a release nothing outranks age, so putting one issue first takes a release of
  its own.

### Option C — A milestone is a release scope; priority is a separate, optional concept

A milestone is what ships together. Priority is an optional tracker concept: on GitHub the
board's Priority field, on Jira priority or rank. The picker takes the earliest open release
first, by the tracker's release order — on GitHub the due date, an undated release ranking
after every dated one and undated releases as one; within it, by priority where the tracker
carries it, else, and among equals, the oldest unblocked issue. The prefix, the tie sent to
the human and the roadmap session go.

- Pro: each concept is one native field on each tracker, and the method runs without the board.
- Con: a project without the board ranks within a release by age alone.
- Con: until the human dates the open milestones, they rank as one release.

## Decision

**Option C**: A's double meaning has no Jira counterpart, and B leaves no way to put one issue
first short of a release for it. Both of C's Cons are accepted.

## Consequences

- **ADR-0052 is narrowed**: its Option D2 and its consequence making milestones the method's
  priority are superseded; A2, B2 and C2 stand. **ADR-0060 is not narrowed**: its optional
  board already carries Priority, and the milestone meaning it deferred is decided here.
  **ADR-0054 is not narrowed**: its candidates and parks are untouched, and only the order its
  picker reads changes.
- **Unchanged**: every issue routed to work carries a milestone, an epic's is copied to its
  children, and an unmilestoned one is picked last.
- **Follow-up**: the milestone rule under **Issue conventions** and the autopilot's *Order*
  rewritten per the rows below; the board gains an optional Priority field in the profile; the
  GitHub work-tracker file says how release order and priority are read; the human dates the
  open milestones as releases.
- **Easier**: a pick never waits on the human for order. **Harder**: an issue that must go
  first needs the board, or a release of its own.

**Blast radius.** One search, run from the repository root:

```sh
rg -n --hidden \
  -e '(?i:milestone|roadmap|priorit|\brank|unprefixed|title prefix|due date)' \
  -e '(?i:\bpick(er|s|ed|ing)?\b|lowest-numbered|oldest|next issue)' \
  -e '(?i:\breleas)' \
  CLAUDE.md .claude/ .github/ docs/reference/
```

Wide enough because the decision moves what a milestone means, how a pick is ordered and the
release a milestone becomes: the first pattern names a milestone and every ranking word the
rule uses, the second every way the picker and its tie-break are written, the third the release
side, each in any case. Outside the four paths the patterns find priority in the MoSCoW or
domain sense, packaging releases, and dated records — `CHANGELOG.md`, `docs/postmortems/` and
`docs/adl/`, this record included. It returns **143** hits.

| Site | Today | Follow-up |
|---|---|---|
| `docs/reference/method/contribution-workflow.md:322`–`:329` | Milestone is priority: prefix ranking, never a due date, an unprefixed tie to `clarify`, the roadmap session | Release scope and the picker order above |
| `docs/reference/method/idea-to-product.md:207`, `:208` | Milestones carry priority | Milestones carry release scope; priority is the tracker's optional concept |
| `docs/reference/method/idea-to-product.md:214` | Cites ADR-0052 for the milestone rules | Cites this record |
| `.claude/skills/autopilot/SKILL.md:111` | A tie goes to the human; nothing is picked that tick | The tie clause goes |

47 hits conform: the milestone commands in `tracker-mechanics.md` (15), placement and copying
in `file-task-issue` (11), `idea-to-product.md` (5), `work-idea` and `diagnosing-bugs` (2 each),
the autopilot's filing and pick steps (3), the routing entry, a permission and its profile
line (3), and the epic exclusion, Rule B's next-issue stop and the unmilestoned-last rule (6).
Out of scope: 8 hits keep MoSCoW or domain priority; 29 a release in another sense — the
release workflows (21), which cut releases, `SECURITY.md` (4), `dependabot.yml` (2) and two
skills; 30 pick, rank, oldest or next issue in another sense, `cherry-pick` included; 17 the
vendored and `domain-driven-design` texts.
