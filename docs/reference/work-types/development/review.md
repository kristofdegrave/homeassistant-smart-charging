# Work type: `development` — the review checklist

**Who reads this.** The reviewer only — a fresh, read-only Opus agent, never the session that
wrote the code. It holds what only a reviewer can check: what to read first, and the checks
that are about the **change** rather than the finished code. What must be true of finished code
is [`done.md`](done.md) beside this file, and how it is written is
[`implement.md`](implement.md); neither is restated here.

The output format, the severity grouping, the anchoring rules and the untrusted-data rule are
not here either. They are the same for every review and live with whoever applies this
checklist — the generic `reviewer` agent definition locally, the review workflow's own prompt
in CI, which has no agent to spawn and self-applies instead. Both reach this file the same
way, through `CLAUDE.md`'s **Model selection** table.

**This checklist covers `custom_components/smart_charging/` and nothing else.** A `development`
change produces two artifacts in two trees, and the criteria belong to the artifact rather than
to the label that dispatched the review — which is why the `development` row names the
`testing` row's checklist and bar for its `tests/**` half, and why a code-only change resolves
this file alone. So a test defect is reported against the item the `testing` bar names for it,
never against an item here.

## What to read first

Always read:

- The changed files under `custom_components/smart_charging/` and their mirrored tests under
  `tests/` — from the diff the caller gives you, or the files whole.
- The implementation-plan task the change realizes — the change's spec. The `specs` row of
  `CLAUDE.md`'s **Model selection** table names the artifact and the tree it lives in.
- The behaviour the change implements, in this project's analysis documents — the
  authoritative "what". `CLAUDE.md`'s **Document structure** section names them and says which
  holds what.
- The accepted ADRs the change touches. Locate them per `CLAUDE.md`'s **Architecture Decision
  Records (ADRs)** section.
- The **PR description**, which [`done.md`](done.md)'s item 6, *Runtime check*, is judged
  against. Take it from the caller where the caller supplies it; fetch it yourself where your
  tool grant reaches the tracker — `CLAUDE.md`'s **Tracker mechanics** section names the
  reference carrying the command. Only where you have no body and no way to reach one, say so
  and say that the item could not be judged; never report a missing section you were never
  handed, and never treat the two cases that item excludes as findings.

Read conditionally:

- The `ha-integration-knowledge` skill — where the diff touches HA platform surface (entity
  classes, config flow, `manifest.json`, services).

Then [`done.md`](done.md), the completion bar, before you start scoring rather than while you
write up. It names further material at the item that needs it — two Python skills at its
item 5. Read each when its item applies; don't fan out across the tree ahead of that.

## The checks that are yours alone

[`done.md`](done.md) is the bulk of the checklist: apply every item in it as a review
criterion, at the severity that item states. One check is not in it, because it is about how
this **review** is conducted rather than about the finished code, and an author checking their
own draft cannot make it. Everything else — including the scope each bar item states for
itself — comes from the bar, not from here.

**(A) You read the change's tests even where you were dispatched for the code tree.** A row's
tree qualifier says which checklist a changed tree is *guaranteed*, not what a reviewer may
read — and a code change's wiring is often only visible in the tests that exercise it. Reading
them applies no second standard to them: where the change also touches `tests/**` you already
hold the `testing` checklist and bar for those files, and where it does not, what the tests
show you is evidence about the code. Where a second reviewer was dispatched over the same
files, expect overlap: a finding raised twice is the accepted cost, a finding raised by neither
is not.

This is also what makes [`done.md`](done.md)'s overlap paragraph — the one after its item 6 —
decidable, and decidable here rather than anywhere else: it binds the review that holds both
bars, and a review holding both is a review that read the tests. Apply it as that paragraph
states it; nothing about it is restated here.
