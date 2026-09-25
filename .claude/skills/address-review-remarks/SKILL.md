---
name: address-review-remarks
description: "Use when addressing review findings on a pull request — from the AI review loop (a PR comment containing `ai-review-verdict: remarks`) or from a human review. CI's entry for the fix step; an interactive session reaches it through the `fix` skill rather than directly."
---

# Address review remarks

Fix the findings a review raised against a change, then account
for every finding in a summary. The fix policy and the summary contract below are the single
source of truth — the CI workflow (`_ai-fix.yml`) and local runs both follow them.

## 1. Locate the findings

Findings come from two sources — always gather **both**:

- **AI review** — the reviewer submits a native PR *review* (not an issue comment), with the
  summary in the review body and per-line findings as inline comments. Run
  `gh api "repos/<owner>/<repo>/pulls/<pr>/reviews" --paginate` and take the **most recent**
  review by a bot author (login ends in `[bot]`) whose body contains `ai-review-verdict: remarks`
  (there may be none). That review's `body` is the grouped summary; note its `id`. Then run
  `gh api "repos/<owner>/<repo>/pulls/<pr>/comments" --paginate` and take the inline comments
  whose `pull_request_review_id` equals that `id` — those are the AI's per-line findings.
  **Scope strictly to that one review id**: inline comments from earlier review cycles were
  already addressed — do not re-fix them. If the latest bot review's verdict is `clean`, there
  are no AI findings (human comments below may still exist). Older reviews are context only.
- **Human review comments** — run
  `gh api "repos/<owner>/<repo>/pulls/<pr>/comments" --paginate` and keep every comment that
  is authored by a human (login does not end in `[bot]`) **and** has no reply in its thread
  (a comment whose `in_reply_to_id` points to it) containing `ai-fix-ack` — such a reply means
  an earlier run already handled it. Also check
  `gh api "repos/<owner>/<repo>/pulls/<pr>/reviews"` for non-empty human review bodies not yet
  acknowledged in a summary. Treat every human comment as a finding of at least **Major**
  severity — human input is never skipped silently.

If neither source yields an unaddressed finding, post the summary (section 5) saying so and
stop — do not invent work.

## 2. Fix policy

- Fix every **Critical** and **Major** finding.
- Also fix **Minor**/**Nit** findings when the change is trivial and local.
- Fix by the first that works: **reword** the text the finding names; else **delete** it, or
  replace it with a pointer to its owner; only then **add** text.
- If you disagree with a finding, leave the document unchanged for that finding and record why —
  it becomes a **Skipped** entry in the summary. Never half-apply a fix you think is wrong.
- A finding whose request is outside the PR's scope is not fixed in this PR. Locally the fix
  step files it as an issue and answers the thread with that issue (the contribution
  workflow's **Thread discipline**, routed from `CLAUDE.md`'s **Contribution workflow**
  section); in CI, reply that it is out of scope and leave the thread open for the human to
  file — the fix worker's outputs are the PR's alone, whatever its tool grant could reach, so
  it must not file. Either way it is a **Skipped** entry in the summary.

## 3. Fix with the author's context

Fixing is re-authoring — work with the same context the original author had:

- **Apply the work file in full.** Take the context label from the PR's **linked issue** —
  not the PR itself, which carries none — and look its row up in `CLAUDE.md`'s **Model
  selection** table. Apply **every** file its *How the work is done* column names — how the
  artifact is written, and the completion bar the finished artifact has to meet. Their
  template, rules, bar items and common-mistakes list are what define a correct fix, and none
  of that is restated here. The bar is also what the review applied, so a fix that satisfies
  the finding but leaves a bar item failing is not finished.
- **Apply each changed tree's work file too, to that tree's files.** The review routes by
  changed path as well as by label — the no-label row's path map, in the same section — so the
  fix does too. For every tree the PR changes that the path map sends to a checklist, apply the
  *How the work is done* files of the row whose work-type directory holds that checklist, and
  of any row whose own checklist file points at it — each to the changed files of its own kind
  under that tree. A row already applied is not applied twice, and a row naming none adds
  nothing.
  The case this exists for: a PR of another label that edits a record under `docs/adl/**` is
  still bound by the `adr` work file's rule on changing a merged record.
- **Where neither the label nor a changed tree yields a work file** — no linked issue, no
  context label, or rows that name none — there is nothing to re-author with. Fix what the
  finding states, keep section 2's fix policy, and say in the summary that no work
  file governed the change.
- **A work file's rule about changing an already-merged artifact overrides the finding**,
  including the conditions that file attaches to when the rule applies. Such a finding becomes
  a **Skipped** entry in the summary, recorded with why, rather than an edit.
- **Self-checks are the work-type files' own**, including whether a general one this project
  applies to its documents is replaced by a type-specific one.

## 4. Acknowledge every human comment in its thread

For each inline human review comment you processed, reply in its thread:

```
gh api -X POST "repos/<owner>/<repo>/pulls/<pr>/comments/<comment_id>/replies" -f body="<markdown>"
```

- Start the body with `<!-- ai-fix-ack -->`, then one or two sentences: what changed (with
  file references) or why you disagree.
- This marker is how future fix runs and the reviewer know the comment is handled — never
  omit it, and never put it in any comment that is not a direct answer to a human comment.
- A human review body (not an inline comment) has no thread — account for it in the summary
  instead, mentioning the reviewer by `@login`.

## 5. Summary (one per run, finding-by-finding)

Post exactly **one** PR comment via `gh pr comment <pr> --body "<markdown>"`:

- Start the body with `<!-- ai-fix-summary -->`.
- One bullet or table row per finding — AI findings **and** human comments alike: **Fixed**
  (what changed, with file references), **Skipped** (and why you disagree), or **Partially
  fixed**. Keep it short.
- The run's **net lines added**, from `git diff --shortstat` against the head the run started
  from; a file the run created counts in full, named. If positive: which findings grew it, and
  why rewording or deleting could not fix them.
- **CRITICAL: the comment must NOT contain the text "ai-review-verdict" anywhere — not even
  quoted.** The workflows route and count fix cycles by searching comment bodies for that
  marker; a summary containing it would be miscounted as a review and break the cycle limit.
  This applies to locally posted summaries too — they land in the same comment stream the
  workflow counts.
- If there is no PR (reviewing an uncommitted local draft), report the same summary inline
  instead of commenting.

## 6. Commit — depends on where you run

- **In CI**: do NOT commit or push — the workflow commits and hands back to review.
- **Locally**: commit with `docs: address review remarks (#<pr>)` and push to the PR branch.
  No separate pre-commit approval is needed — the human partner's explicit approval gates the
  **PR merge**, not each commit or push.

