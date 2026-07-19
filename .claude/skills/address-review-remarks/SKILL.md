---
name: address-review-remarks
description: "Use when addressing review findings on Smart Charging analysis documents (docs/analysis/**) or ADRs (docs/adl/**) — from the AI review loop (a PR comment containing `ai-review-verdict: remarks`) or from a human review. Works locally and in CI."
---

# Address review remarks

Fix the findings a review raised against analysis documents (`docs/analysis/**`) or ADRs
(`docs/adl/**`), then account
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
- If you disagree with a finding, leave the document unchanged for that finding and record why —
  it becomes a **Skipped** entry in the summary. Never half-apply a fix you think is wrong.

## 3. Fix with the author's context

Fixing is re-authoring — work with the same context the original author had:

- **For a use-case (`UCnn-*.md`): apply the `write-use-case` skill in full** — its template,
  rules (glossary-first, entity-catalog columns, reference-don't-restate, state models for
  mode UCs), and common-mistakes list define what a correct fix looks like. Those rules are
  deliberately not restated here.
- **For an ADR (`docs/adl/NNNN-*.md`): apply the `write-adr` skill in full**, with one
  overriding rule: **never edit an Accepted ADR's Context/Decision/Consequences** to
  address a finding, even if the finding says the decision itself was wrong. Determine
  "Accepted" from the **base branch**, not the working tree — run
  `git show <base-sha-or-ref>:<path>` for the file; if it doesn't exist there, or its
  Status there isn't already `Accepted`, this PR is still drafting the ADR and normal
  fixes apply. Only a Status that already read `Accepted` on the base branch is immutable.
  If a finding argues the *decision* on an already-Accepted ADR is wrong (not just its
  write-up), that is a **Skipped** entry in the summary — record it as a candidate for a
  new, superseding ADR and say so, rather than rewriting history. Findings about the ADR's
  *write-up* (a missing Con, a Decision that doesn't reference its options, a Consequence
  that doesn't follow) are fixed normally.
- For other analysis docs: follow the flow document standard and review protocol in CLAUDE.md.
- Run the skill's 6Cs self-check on the sections you changed before writing the summary
  (ADRs are exempt — see `write-adr`'s Self-check, which replaces the 6Cs pass for ADRs).

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

