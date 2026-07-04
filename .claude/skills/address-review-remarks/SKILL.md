---
name: address-review-remarks
description: Use when addressing review findings on Smart Charging analysis documents (docs/analysis/**) — from the AI review loop (a PR comment containing `ai-review-verdict: remarks`) or from a human review. Works locally and in CI.
---

# Address review remarks

Fix the findings a review raised against analysis documents (`docs/analysis/**`), then account
for every finding in a summary. The fix policy and the summary contract below are the single
source of truth — the CI workflow (`fix-review.yml`) and local runs both follow them.

## 1. Locate the review

- If the caller did not hand you the review text: run `gh pr view <pr> --comments` and take the
  **most recent** comment containing `ai-review-verdict: remarks`. Older review comments are
  context only.
- For a human review (no marker), use the review comment(s) the caller points at.

## 2. Fix policy

- Fix every **Critical** and **Major** finding.
- Also fix **Minor**/**Nit** findings when the change is trivial and local.
- If you disagree with a finding, leave the document unchanged for that finding and record why —
  it becomes a **Skipped** entry in the summary. Never half-apply a fix you think is wrong.

## 3. Keep cross-document consistency

The same rules as the `write-use-case` skill:

- A fix that introduces a domain term → add it to the `system-overview.md` glossary first.
- Keep `entity-catalog.md` *Read by* / *Written by* columns accurate for every entity touched.
- Reference — do not restate — `control-cycle.md` and `resolution-rules.md`.

## 4. Summary (one per run, finding-by-finding)

Post exactly **one** PR comment via `gh pr comment <pr> --body "<markdown>"`:

- Start the body with `<!-- ai-fix-summary -->`.
- One bullet or table row per finding of the review: **Fixed** (what changed, with file
  references), **Skipped** (and why you disagree), or **Partially fixed**. Keep it short.
- **CRITICAL: the comment must NOT contain the text "ai-review-verdict" anywhere — not even
  quoted.** The workflows route and count fix cycles by searching comment bodies for that
  marker; a summary containing it would be miscounted as a review and break the cycle limit.
  This applies to locally posted summaries too — they land in the same comment stream the
  workflow counts.
- If there is no PR (reviewing an uncommitted local draft), report the same summary inline
  instead of commenting.

## 5. Commit — depends on where you run

- **In CI**: do NOT commit or push — the workflow commits and hands back to review.
- **Locally**: present the addressed changes to the human partner first (per the CLAUDE.md
  review protocol), then commit with `docs: address review remarks (#<pr>)` and push to the
  PR branch.
