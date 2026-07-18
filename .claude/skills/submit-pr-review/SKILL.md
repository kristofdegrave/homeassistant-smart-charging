---
name: submit-pr-review
description: "Use when posting review findings to a Smart Charging PR — from CI (_ai-review.yml) or from a local review after a reviewer agent (analysis-reviewer / adr-reviewer / system-design-reviewer) returns findings. Submits findings as a native GitHub PR review (event COMMENT) with inline line comments, so they render in the Files changed tab on the exact lines. The single source of truth for the review payload, anchoring rules, and the CI verdict marker — CI and local runs both follow it so they never drift."
---

# Submit a PR review

Post review findings as a **native pull request review** (`event: COMMENT`) with per-line
inline comments — never as a plain issue comment. Findings then render in the *Files changed*
tab and land on the exact diff lines.

**Never** use `event: APPROVE` or `event: REQUEST_CHANGES`. The human maintainer is the sole
merge gate (CLAUDE.md merge policy), and a bot cannot request-changes or approve a bot-authored
PR anyway (GitHub 422). Always `COMMENT`.

## 1. Build the review payload

Write it to a scratch JSON file (the ONLY file you create — do **not** edit any repository file):

```json
{
  "commit_id": "<the PR head SHA>",
  "event": "COMMENT",
  "body": "<grouped-findings summary markdown; see §3>",
  "comments": [
    { "path": "<repo-relative path>", "line": <line in the file's new version>,
      "side": "RIGHT", "body": "<severity>: <finding>" }
  ]
}
```

## 2. Anchor inline comments — the reviews API is strict

- Each inline comment MUST anchor to a line that is part of THIS diff
  (`git diff <base-sha>...<head-sha>`). `line` is the line number in the file's **new** version;
  `side` is `RIGHT` (use `LEFT` only to comment on a removed line).
- **A single out-of-range anchor makes the WHOLE submission fail with HTTP 422.**
- Put every Critical/Major/Minor finding that maps to a specific changed line inline.
- A finding that does NOT map to a changed line (e.g. "a required section is missing", a
  cross-file concern) goes in the summary body instead — never invent a line to place it inline.

## 3. Summary body

- Findings grouped by severity (Critical / Major / Minor / Nit), each with a file/line reference.
- Include a **Human review comments** section for any unaddressed human comments the caller
  identified (quote each with its file), treated as at least Major.
- End with a ready-to-merge recommendation.

## 4. Verdict marker — differs by caller

- **CI mode** (`_ai-review.yml`, running as a bot): the **VERY LAST line** of the body MUST be
  exactly one machine-readable marker — the router keys on it:
  - `<!-- ai-review-verdict: remarks -->` if there is at least one Critical or Major finding
    that must be addressed before merge;
  - `<!-- ai-review-verdict: clean -->` otherwise (Minor/Nit findings alone are clean).
- **Local mode** (you post as a human `gh` identity): do **NOT** emit the verdict marker. The
  marker is CI's routing/cycle-count signal; a local review carrying it would be miscounted as an
  automatic fix cycle. A markerless review reads as ordinary human feedback, which the
  `address-review-remarks` skill already picks up via its human-comment / `ai-fix-ack` path.

## 5. Submit — and recover from a 422

```
gh api "repos/<owner>/<repo>/pulls/<pr>/reviews" --input <payload-file>
```

If it fails with HTTP 422 on an inline anchor, resubmit with that one comment removed from
`comments` and its text appended to the summary body. Do **not** fall back to a plain issue
comment — the review must be posted.

## Who calls this

- **CI**: `_ai-review.yml`'s prompt references this skill and supplies the repo, PR number,
  head SHA, and base SHA. It runs as the workflow bot, so it uses CI mode (with the marker).
- **Locally**: the reviewer agents (`analysis-reviewer`, `adr-reviewer`, `system-design-reviewer`)
  are read-only — they return findings, they do not post. After one returns, the main session
  posts them here in local mode (no marker), following the CLAUDE.md review protocol
  (PR pushed first, then the fresh-agent review posted to it).
