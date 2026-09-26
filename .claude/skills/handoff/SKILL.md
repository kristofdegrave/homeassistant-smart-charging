---
name: handoff
description: Use when the user explicitly asks to hand off, write a handoff, or compact this conversation so a fresh session/agent can continue the work. Not for ordinary summaries, status reports, stop-and-report check-ins, or PR/issue bodies — those stay in the conversation or in the artifact they belong to.
argument-hint: "What will the next session work on?"
disable-model-invocation: true
---

# Handoff

Write one Markdown document that lets a fresh agent resume this work without the scrollback.
The repo's own boundaries make this routine: the stop-and-report rule (**Rule B** of the doc
`CLAUDE.md`'s **Contribution workflow** section routes to) pauses an interactive session once
an issue's chain reaches approval or the review cap, and each task runs in its own worktree.

## Where it goes

The session scratchpad directory named in the system prompt, or the OS temp directory if none
is, named `handoff-<issue>.md` so successive handoffs don't collide. **Never inside the repo
or a worktree** — a handoff is session scrappage, and a file there lands in the diff, the
review and the merge. Report the absolute path when you're done.

## What it contains

Six sections, in this order. Keep each to what the next agent cannot reconstruct itself.

1. **Goal** — the issue being worked and what "done" looks like. If the user passed arguments,
   they describe what the next session will focus on: scope the whole document to that.
2. **State** — issue number, worktree absolute path, branch, PR URL, board Status, and where
   the contribution workflow stopped — `CLAUDE.md`'s **Contribution workflow** section routes
   to the doc that owns the steps (which step, by its name there, and which review round against the
   interactive cap that doc states).
3. **Decisions** — choices made in conversation that are not yet written down anywhere, each
   with the reason. This is the section that only the scrollback has; everything else can be
   re-read.
4. **Open questions** — unsettled points, and who has to settle them (the human partner, or a
   fact an agent can look up).
5. **Next steps** — ordered, concrete, starting from the workflow step in *State*.
6. **Suggested skills** — which skills the next agent should call the Skill tool for, and when.

## Suggested skills

Name skills, not procedures — the skill carries its own instructions.

- Artifact work: `implement`, which resolves the issue's row of `CLAUDE.md`'s **Model
  selection** table and follows the work file it names. Cite the row, don't restate the table.
- Before an issue exists: `work-idea` (an `idea` issue), `grilling` (stress-test a decision
  with the human partner), `file-task-issue` (file the issues that fall out).
- Any open question the human partner has to settle, at any step: `clarify`.
- Once an issue has a PR: record which step of the contribution workflow the work is at, and
  route there — the doc `CLAUDE.md`'s **Contribution workflow** section routes to names the
  skill each step runs through, so the note does not.

## Rules

- **Reference, don't duplicate.** Specs, plans, ADRs, issues, PRs, commits and diffs are
  already durable — give the path, number or URL and a one-line "why it matters here". A
  handoff that restates a plan goes stale against it.
- **Redact.** No tokens, API keys, passwords, or personal data — not the user's own. Say a
  credential is needed and where it comes from, never its value.
- **Write it for someone with no context**, including yourself. Expand every pronoun and
  "as discussed above".
- **Don't let writing it do the work.** A handoff records state; it never drafts the artifact,
  commits, or opens a PR on the way past.
