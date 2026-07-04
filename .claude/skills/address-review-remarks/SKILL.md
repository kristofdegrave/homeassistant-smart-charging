---
name: address-review-remarks
description: "Use when addressing review findings on Smart Charging analysis documents (docs/analysis/**) — from the AI review loop (a PR comment containing `ai-review-verdict: remarks`) or from a human review. Works locally and in CI."
---

# Address review remarks

Fix the findings a review raised against analysis documents (`docs/analysis/**`), then account
for every finding in a summary. The fix policy and the summary contract below are the single
source of truth — the CI workflow (`fix-review.yml`) and local runs both follow them.

## 1. Locate the findings

How you gather findings depends on what you're working against:

- **Findings already in hand** — if the caller handed you review text or a findings list
  directly (e.g. piped from `/code-review`, pasted, or a prior `analysis-reviewer` report),
  use it as-is. Skip the GitHub lookups below entirely.
- **A PR exists** — gather **both** of the following:
  - **AI review** — if the caller did not hand you the review text: run
    `gh pr view <pr> --comments` and take the **most recent** comment containing
    `ai-review-verdict: remarks` (there may be none). Older review comments are context only.
  - **Human review comments** — run
    `gh api "repos/<owner>/<repo>/pulls/<pr>/comments" --paginate` and keep every comment that
    is authored by a human (login does not end in `[bot]`) **and** has no reply in its thread
    (a comment whose `in_reply_to_id` points to it) containing `ai-fix-ack` — such a reply means
    an earlier run already handled it. Also check
    `gh api "repos/<owner>/<repo>/pulls/<pr>/reviews"` for non-empty human review bodies not yet
    acknowledged in a summary. Treat every human comment as a finding of at least **Major**
    severity — human input is never skipped silently.
- **No PR** (reviewing an uncommitted local draft) — there's no review thread to read, so
  produce the findings yourself: run the `analysis-reviewer` agent against the draft, per the
  fresh-agent review step in CLAUDE.md's review protocol. Its report is the finding set for
  the rest of this skill; the "human review comments" step above does not apply.

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
- For other analysis docs: follow the flow document standard and review protocol in CLAUDE.md.
- Run the skill's 6Cs self-check on the sections you changed before writing the summary.

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
- **Locally**: present the addressed changes to the human partner first (per the CLAUDE.md
  review protocol), then commit with `docs: address review remarks (#<pr>)` and push to the
  PR branch.
