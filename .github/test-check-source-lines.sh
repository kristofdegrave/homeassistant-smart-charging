#!/usr/bin/env bash
# Tests for check-source-lines.py. Each case writes an issue body and runs the check against a
# throwaway git repository whose profile allows two trees. Findings are asserted on their text,
# not only the exit code, so a message that stops naming the offending line fails here. The
# `--issue` cases replace `gh` with a fake: one that answers, and one that fails -- the lookup
# failure CI must pass with a warning rather than read as a verdict.
#
# Usage: .github/test-check-source-lines.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/check-source-lines.sh"
pass=0
fail=0

REPO="$(mktemp -d)"
git -C "$REPO" init -q
git -C "$REPO" config user.email t@example.com
git -C "$REPO" config user.name t
git -C "$REPO" config core.autocrlf false
mkdir -p "$REPO/.claude" "$REPO/docs/analysis" "$REPO/docs/adl" "$REPO/docs/other"
cat > "$REPO/.claude/profile.yml" <<'EOF'
repo:
  owner: o
  name: r
source_lines:
  trees:
    - docs/analysis/
    - docs/adl
EOF
cat > "$REPO/docs/analysis/req.md" <<'EOF'
# Requirements

## R5 — Departure deadline guarantee

### Notes

## Notes

```markdown
## Fenced heading
```
EOF
echo "# Decision" > "$REPO/docs/adl/0001-x.md"
echo "not markdown" > "$REPO/docs/analysis/data.csv"
echo "# Other" > "$REPO/docs/other/o.md"
git -C "$REPO" add -A && git -C "$REPO" commit -qm base
# In the working tree only, never committed: resolves without --ref, not with --ref HEAD.
echo "# Draft" > "$REPO/docs/analysis/draft.md"

BODY="$(mktemp)"

# expect <name> <exit> <text or ""> <body> [extra args...]
expect() {
  local name="$1" want="$2" text="$3" body="$4" out code
  shift 4
  printf '%s\n' "$body" > "$BODY"
  out="$(bash "$CHECK" --body "$BODY" --root "$REPO" "$@" 2>&1)"
  code=$?
  report "$name" "$want" "$text" "$code" "$out"
}

report() {
  local name="$1" want="$2" text="$3" code="$4" out="$5"
  if [ "$code" -ne "$want" ] || { [ -n "$text" ] && ! grep -qF -- "$text" <<<"$out"; }; then
    printf 'FAIL  %s (exit %s, want %s)\n%s\n' "$name" "$code" "$want" "$out" | sed '2,$s/^/        /'
    fail=$((fail + 1))
  else
    printf 'ok    %s\n' "$name"
    pass=$((pass + 1))
  fi
}

# --- resolving ---------------------------------------------------------------------------
expect "no Source: lines at all" 0 "0 \`Source:\` line(s)" "Part of #1

Just a task."
expect "bare path in an allowed tree" 0 "1 \`Source:\` line(s), every one resolves" \
  "Source: docs/adl/0001-x.md"
expect "a tree listed without its trailing slash still matches" 0 "" \
  "Source: docs/adl/0001-x.md#decision"
expect "anchor with an em dash, GitHub's slug" 0 "" \
  "Source: docs/analysis/req.md#r5--departure-deadline-guarantee"
expect "a repeated heading's -1 suffix" 0 "" \
  "Source: docs/analysis/req.md#notes-1"
expect "trailing whitespace and CRLF are not content" 0 "" \
  "$(printf 'Source: docs/adl/0001-x.md  \r')"
expect "a Source: line inside a code fence is an example, not a line" 0 "0 \`Source:\` line(s)" \
  '```
Source: docs/nowhere.md
```'
expect "the working tree is what resolves without --ref" 0 "" \
  "Source: docs/analysis/draft.md"

# --- not resolving -----------------------------------------------------------------------
expect "missing file" 1 "line 1: Source: docs/analysis/gone.md" \
  "Source: docs/analysis/gone.md"
expect "a heading that is not there" 1 "no heading in docs/analysis/req.md has the anchor #r6" \
  "Source: docs/analysis/req.md#r6"
expect "a heading only inside a code fence is no anchor" 1 "#fenced-heading" \
  "Source: docs/analysis/req.md#fenced-heading"
expect "a path outside every allowed tree" 1 "outside every tree" \
  "Source: docs/other/o.md"
expect "an issue is not a target" 1 "not \`Source: <path>\`" \
  "Source: #1454 (decisions 1-4)"
expect "prose after the path" 1 "line 3: Source: \`docs/adl/0001-x.md\` — Decision" \
  "Part of #1

Source: \`docs/adl/0001-x.md\` — Decision"
expect "a .. segment" 1 "no \`..\`" \
  "Source: docs/analysis/../other/o.md"
expect "an anchor on a file that is not markdown" 1 "not markdown" \
  "Source: docs/analysis/data.csv#x"
expect "an empty anchor" 1 "an empty anchor" \
  "Source: docs/adl/0001-x.md#"
expect "every bad line is reported, not only the first" 1 "2 of 3" \
  "Source: docs/adl/0001-x.md
Source: docs/analysis/gone.md
Source: docs/other/o.md"
expect "--ref resolves against the ref, not the working tree" 1 "no such file at HEAD" \
  "Source: docs/analysis/draft.md" --ref HEAD

# --- environment and lookup --------------------------------------------------------------
expect "an unknown ref is an environment error" 2 "cannot resolve ref" \
  "Source: docs/adl/0001-x.md" --ref no-such-ref

NOKEY="$(mktemp -d)"
mkdir -p "$NOKEY/.claude" && echo "repo: {owner: o, name: r}" > "$NOKEY/.claude/profile.yml"
printf 'Source: docs/adl/0001-x.md\n' > "$BODY"
out="$(bash "$CHECK" --body "$BODY" --root "$NOKEY" 2>&1)"; code=$?
report "a profile without source_lines.trees is an environment error" 2 "source_lines.trees" "$code" "$out"

# The fake lookup is a Python script, not a shell script on PATH: a Windows Python cannot run a
# shebang script, and would quietly reach the real `gh` instead. Its path goes through cygpath
# where there is one, since the Windows Python reading the command cannot resolve /tmp.
py=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import yaml' >/dev/null 2>&1; then
    py="$candidate"; break
  fi
done
native() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else echo "$1"; fi; }
FAKE="$(mktemp -d)"
cat > "$FAKE/answers.py" <<'FAKEGH'
import sys
if sys.argv[1:] != ["api", "repos/o/r/issues/7"]:
    sys.exit(f"unexpected: {sys.argv[1:]}")
print(r'{"number": 7, "body": "Part of #1\r\n\r\nSource: docs/analysis/gone.md"}')
FAKEGH
cat > "$FAKE/fails.py" <<'FAKEGH'
import sys
sys.exit("HTTP 502: Bad Gateway")
FAKEGH
lookup() { CHECK_SOURCE_LINES_GH="$1" bash "$CHECK" --issue 7 --root "$REPO" 2>&1; }

out="$(lookup "$py $(native "$FAKE/answers.py")")"; code=$?
report "--issue fetches the body from the profile's repository and checks it" 1 \
  "line 3: Source: docs/analysis/gone.md" "$code" "$out"
out="$(lookup "$py $(native "$FAKE/fails.py")")"; code=$?
report "a failed lookup is exit 3, no verdict, never exit 1" 3 "HTTP 502" "$code" "$out"
out="$(lookup "$(native "$FAKE")/no-such-gh")"; code=$?
report "no gh to run is a lookup failure too" 3 "lookup failed, no verdict" "$code" "$out"

rm -rf "$REPO" "$NOKEY" "$FAKE" "$BODY"
printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
