---
name: submit-pr-review
description: "Use when posting review findings to a pull request in this project from a pass run by the review skill, once the pass's reviewer agents have returned findings. Submits findings as a native GitHub PR review (event COMMENT) with inline line comments, so they render in the Files changed tab on the exact lines. The single source of truth for the review payload, anchoring rules and the round marker."
---

# Submit a PR review

Post review findings as a **native pull request review** (`event: COMMENT`) with per-line
inline comments — never as a plain issue comment. Findings then render in the *Files changed*
tab and land on the exact diff lines.

**Never** use `event: APPROVE` or `event: REQUEST_CHANGES`. The human maintainer is the sole
merge gate (the merge rule under `CLAUDE.md`'s **Contribution workflow** topic), and the
account that opened the PR cannot approve or request changes on it anyway (GitHub 422).
Always `COMMENT`.

## 1. Build the review payload

Write it to a scratch JSON file (the ONLY file you create — do **not** edit any repository
file):

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
  (`git diff <base-sha>...<head-sha>`). `line` is the line number in the file's **new**
  version;
  `side` is `RIGHT` (use `LEFT` only to comment on a removed line).
- **A single out-of-range anchor makes the WHOLE submission fail with HTTP 422.**
- Put every Critical/Major/Minor finding that maps to a specific changed line inline.
- A finding that does NOT map to a changed line (e.g. "a required section is missing", a
  cross-file concern) goes in the summary body instead — never invent a line to place it
  inline.

## 3. Summary body

- Findings grouped by severity (Critical / Major / Minor / Nit), each with a file/line
reference.
- End with a ready-to-merge recommendation.

## 4. Round marker

- The **last line** of the body is exactly `<!-- local-review-round -->`, and the body carries
  no other marker. It exists only for the round count the `review` skill keeps.
- The fix step does not key on it: the review is posted under the human partner's own
  account, so the `fix` skill's §2 finds its comments as it finds any comment by that
  account.

## 5. Submit — and recover from a 422

```
gh api "repos/<owner>/<repo>/pulls/<pr>/reviews" --input <payload-file>
```

If it fails with HTTP 422 on an inline anchor, resubmit with that one comment removed from
`comments` and its text appended to the summary body. Do **not** fall back to a plain issue
comment — the review must be posted.

## Who calls this

The `review` skill runs the pass and supplies the repo, PR number, head SHA and base SHA.
Every reviewer it spawns is read-only — they return findings, they do not post — so once they
have all returned, the main session posts their findings here as **one** review, carrying the
round marker. One pass is one review, however many reviewers ran. The PR always exists by
then: the implement step of the contribution workflow — the doc `CLAUDE.md`'s **Contribution
workflow** section routes to — guarantees it. Anchor each finding that carries a file path +
new-version line as an inline comment; put the rest in the body. If there is no PR (an
uncommitted local draft), report the findings in the session instead of posting.
