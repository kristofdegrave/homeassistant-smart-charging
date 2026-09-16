#!/usr/bin/env bash
# Tests for check-upstream-drift.py. A throwaway root holding a minimal .claude/profile.yml and
# a recorded set of upstream answers is built, shown to pass, and then varied one way per
# verdict - so every verdict the script can reach has a fixture, alongside the cases that pin
# down what it deliberately refuses to call drift.
#
# No case touches the network: every run passes --responses, so the suite is as fast and as
# deterministic offline as on a runner, and an API rate limit can never turn it red.
#
# Usage: .github/test-check-upstream-drift.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/check-upstream-drift.sh"
pass=0
fail=0

# The same discovery the wrapper does, for the one mutation that needs an interpreter of its
# own: hardcoding `python` would fail a case on a host that has only `python3`, for an
# environment reason the wrapper already solves.
PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "test-check-upstream-drift: no python on PATH (tried python3, python)" >&2
  exit 2
fi

fail_case() { printf 'FAIL  %s\n' "$1"; shift; printf '%s\n' "$*" | sed 's/^/        /'; fail=$((fail + 1)); }
ok_case()   { printf 'ok    %s\n' "$1"; pass=$((pass + 1)); }

# A manifest with one row per shape the real profile has: two groups, a commit pin that is
# current, a commit pin that has moved, a commit pin whose path no longer exists upstream, and
# an installer content hash. Every commit pin is written as the 12-character prefix the profile
# uses, against a 40-character upstream sha, so the prefix match is exercised rather than
# assumed.
build_fixture() {
  local d="$1"
  mkdir -p "$d/.claude"
  cat > "$d/.claude/profile.yml" <<'EOF'
dependencies:
  method:
    - name: current-skill
      source: acme/skills
      path: skills/current
      pin: commit:aaaaaaaaaaaa
      installed: user
    - name: moved-skill
      source: acme/skills
      path: skills/moved
      pin: commit:bbbbbbbbbbbb
      installed: repo
  stack:
    - name: gone-skill
      source: acme/widgets
      path: skills/gone
      pin: commit:cccccccccccc
      installed: repo
    - name: hashed-skill
      source: acme/widgets
      path: skills/hashed
      pin: sha256:dddddddddddd
      installed: repo
EOF
  cat > "$d/responses.json" <<'EOF'
{
  "acme/skills|skills/current": {
    "sha": "aaaaaaaaaaaa1111111111111111111111111111",
    "date": "2026-01-02T03:04:05Z"
  },
  "acme/skills|skills/moved": {
    "sha": "9999999999992222222222222222222222222222",
    "date": "2026-02-03T04:05:06Z"
  },
  "acme/widgets|skills/gone": {},
  "acme/widgets|skills/hashed": {
    "sha": "8888888888883333333333333333333333333333",
    "date": "2026-03-04T05:06:07Z"
  }
}
EOF
}

new_fixture() {
  local dir
  dir=$(mktemp -d) || return 1
  build_fixture "$dir" || { rm -rf "$dir"; return 1; }
  printf '%s' "$dir"
}

# <name> <expected-exit> <expected-output-substring|-> <shell snippet run inside the fixture>
# A substring written `!<text>` asserts the opposite: the run must NOT print it. The absent
# cases matter as much as the present ones here - the whole point of a verdict like
# `unresolvable` is that the row does not show up as drift.
case_run() {
  local name="$1" want="$2" want_out="$3" mutate="$4" dir out rc
  dir=$(new_fixture) || { fail_case "$name" "could not build fixture"; return; }
  (cd "$dir" && eval "$mutate") || { fail_case "$name" "mutation failed"; rm -rf "$dir"; return; }
  out=$(bash "$CHECK" --root "$dir" --responses "$dir/responses.json" 2>&1); rc=$?
  rm -rf "$dir"
  if [ "$rc" != "$want" ]; then
    fail_case "$name" "expected exit $want, got $rc" "$out"
  elif [ "${want_out#!}" != "$want_out" ]; then
    if printf '%s' "$out" | grep -qF -- "${want_out#!}"; then
      fail_case "$name" "output should not have contained: ${want_out#!}" "$out"
    else
      ok_case "$name"
    fi
  elif [ "$want_out" != "-" ] && ! printf '%s' "$out" | grep -qF -- "$want_out"; then
    fail_case "$name" "output did not contain: $want_out" "$out"
  else
    ok_case "$name"
  fi
}

# --- a manifest with nothing to report -----------------------------------------------------
# Every row but the current one is dropped, so exit 0 is the whole verdict: no report at all,
# not an empty one.
only_current="\$PY - <<'PY'
import io
lines = io.open('.claude/profile.yml', encoding='utf-8').read().split('\n')
keep = lines[:lines.index('    - name: moved-skill')]
io.open('.claude/profile.yml', 'w', encoding='utf-8', newline='\n').write('\n'.join(keep) + '\n')
PY"
case_run "every pin current: exit 0 and no report" 0 "1 dependencies - 1 current" "$only_current"
dir=$(new_fixture) || dir=""
if [ -n "$dir" ]; then
  (cd "$dir" && eval "$only_current") >/dev/null 2>&1
  out=$(bash "$CHECK" --root "$dir" --responses "$dir/responses.json" --out "$dir/none.md" 2>&1); rc=$?
  if [ "$rc" = 0 ] && [ ! -e "$dir/none.md" ]; then
    ok_case "a clean run writes no report file at all, not an empty one"
  else
    fail_case "a clean run writes no report file at all, not an empty one" "exit $rc" "$out"
  fi
  rm -rf "$dir"
fi

# --- one fixture per verdict ---------------------------------------------------------------
case_run "the full manifest reports and exits 1" 1 "Upstream moved" "true"
case_run "a moved pin is listed with its upstream head" 1 "999999999999" "true"
case_run "a moved pin links the compare view" 1 \
  "https://github.com/acme/skills/compare/bbbbbbbbbbbb...999999999999" "true"
case_run "a current pin appears nowhere in the report" 1 '!current-skill' "true"
case_run "a path no commit touches gets its own section" 1 "## Gone from upstream" "true"
case_run "a gone path is not folded in with the unverifiable rows" 1 \
  '!| `gone-skill` | `acme/widgets` | `skills/gone` | `commit:cccccccccccc` | no commit' "true"
case_run "an installer hash is unresolvable, not drifted" 1 "cannot be recomputed here" "true"
case_run "an installer hash lands in the Cannot-be-checked table" 1 "| \`hashed-skill\` | \`acme/widgets\` | \`skills/hashed\` | \`sha256:dddddddddddd\` |" "true"
case_run "an installer hash is absent from the moved table's rendering" 1 \
  '!`skills/hashed` | `dddddddddddd`' "true"
case_run "the report carries the marker the workflow matches on" 1 \
  "<!-- ai-upstream-drift-report -->" "true"
case_run "the report is delimited, so the workflow can replace only its own region" 1 \
  "<!-- /ai-upstream-drift-report -->" "true"
case_run "the report says where a human note belongs" 1 "Write notes outside the two markers" "true"

# --markers is the workflow's only source for both markers; if it ever disagreed with what
# report() writes, the workflow would match nothing and open a fresh issue every week.
dir=$(new_fixture) || dir=""
if [ -n "$dir" ]; then
  markers=$(bash "$CHECK" --root "$dir" --markers 2>/dev/null)
  bash "$CHECK" --root "$dir" --responses "$dir/responses.json" --out "$dir/r.md" >/dev/null 2>&1
  start=$(printf '%s\n' "$markers" | sed -n 1p)
  end=$(printf '%s\n' "$markers" | sed -n 2p)
  if [ -n "$start" ] && [ -n "$end" ] \
     && grep -qF -- "$start" "$dir/r.md" && grep -qF -- "$end" "$dir/r.md"; then
    ok_case "--markers prints exactly the two markers the report carries"
  else
    fail_case "--markers prints exactly the two markers the report carries" "got: $markers"
  fi
  rm -rf "$dir"
fi

# --- --validate: the parse-only mode ci.yml runs against the real manifest -----------------
validate_run() {
  local name="$1" want="$2" want_out="$3" mutate="$4" dir out rc
  dir=$(new_fixture) || { fail_case "$name" "could not build fixture"; return; }
  (cd "$dir" && eval "$mutate") || { fail_case "$name" "mutation failed"; rm -rf "$dir"; return; }
  out=$(bash "$CHECK" --root "$dir" --validate 2>&1); rc=$?
  rm -rf "$dir"
  if [ "$rc" != "$want" ]; then
    fail_case "$name" "expected exit $want, got $rc" "$out"
  elif [ "$want_out" != "-" ] && ! printf '%s' "$out" | grep -qF -- "$want_out"; then
    fail_case "$name" "output did not contain: $want_out" "$out"
  else
    ok_case "$name"
  fi
}
validate_run "--validate accepts a readable manifest, with no network" 0 \
  "manifest valid (4 dependencies)" "rm -f responses.json"
validate_run "--validate rejects a row missing a key" 2 "is missing path" \
  "sed -i '/^      path: skills\/moved$/d' .claude/profile.yml"
validate_run "--validate rejects an unrecognised pin scheme" 2 "unrecognised pin" \
  "sed -i 's#pin: commit:bbbbbbbbbbbb#pin: v1.2.3#' .claude/profile.yml"
# The two shapes --validate used to pass and the weekly run then aborted or mis-verdicted on:
# both modes now go through one predicate, and these are what prove it.
validate_run "--validate rejects an empty commit value" 2 "unrecognised pin" \
  "sed -i 's#pin: commit:bbbbbbbbbbbb#pin: \"commit:\"#' .claude/profile.yml"
validate_run "--validate rejects a commit pin that is not a sha prefix" 2 "not a sha prefix" \
  "sed -i 's#pin: commit:bbbbbbbbbbbb#pin: commit:not-a-sha#' .claude/profile.yml"
case_run "a non-sha commit pin is refused by the run too, not reported as drift" 2 \
  "not a sha prefix" "sed -i 's#pin: commit:bbbbbbbbbbbb#pin: commit:not-a-sha#' .claude/profile.yml"

# --- --splice: putting a fresh report back into an issue body -------------------------------
# This is what rewrites a real issue body, so every shape it can meet has a fixture: the happy
# path with a maintainer's note on both sides, the no-op, and the three degenerate bodies that
# destroy text if they are merged optimistically rather than refused.
splice_case() {
  local name="$1" want="$2" want_out="$3" body="$4" dir out rc
  dir=$(mktemp -d) || { fail_case "$name" "no tmpdir"; return; }
  printf '%s\n' "$body" > "$dir/body.md"
  printf '%s\n' "$MARKER_START" "" "FRESH REPORT" "" "$GENERATED_LINE" \
    "$MARKER_END" > "$dir/report.md"
  out=$(bash "$CHECK" --root "$dir" --splice --body "$dir/body.md" --report "$dir/report.md" \
    --out "$dir/merged.md" 2>&1); rc=$?
  # Built as one string rather than piped: a refused case writes no merged body, and under
  # `pipefail` the failing `cat` would become the pipeline's status and read as "no match"
  # however well the grep did.
  local haystack="$out"
  [ -e "$dir/merged.md" ] && haystack="$out
$(cat "$dir/merged.md")"
  if [ "$rc" != "$want" ]; then
    fail_case "$name" "expected exit $want, got $rc" "$out"
  elif [ "$want_out" != "-" ] && ! printf '%s' "$haystack" | grep -qF -- "$want_out"; then
    fail_case "$name" "neither output nor merged body contained: $want_out" "$out"
  else
    ok_case "$name"
  fi
  rm -rf "$dir"
}
MARKER_START=$(bash "$CHECK" --markers | sed -n 1p)
# The exact generated-on line the report writes, so the no-op cases exercise the real
# prefix `comparable()` ignores rather than a stand-in that would pass either way.
GENERATED_LINE="Generated by \`.github/workflows/upstream-drift.yml\`, 2026-01-02."
MARKER_END=$(bash "$CHECK" --markers | sed -n 2p)

wellformed="A maintainer's note above.
$MARKER_START
OLD STALE CONTENT
$MARKER_END
A note below."
splice_case "a note above the report survives the splice" 0 "A maintainer's note above." "$wellformed"
splice_case "a note below the report survives the splice" 0 "A note below." "$wellformed"
splice_case "the stale region is replaced" 0 "FRESH REPORT" "$wellformed"
splice_case "an unclosed opening marker is refused, not merged" 2 "expected one each" \
  "Note.
$MARKER_START
content that would be swallowed"
splice_case "a doubled opening marker is refused" 2 "expected one each" \
  "$MARKER_START
a
$MARKER_START
b
$MARKER_END"
splice_case "markers in the wrong order are refused" 2 "precedes its opening marker" \
  "$MARKER_END
middle that would be swallowed
$MARKER_START"
splice_case "a body with no markers at all is refused" 2 "expected one each" "Just a note."
splice_case "a marker quoted in prose does not delimit anything" 2 "expected one each" \
  "We match on $MARKER_START inside this sentence, which is prose."

# Re-splicing an unchanged report is the weekly no-op: exit 3, and nothing written.
dir=$(mktemp -d)
printf '%s\n' "$MARKER_START" "" "FRESH REPORT" "" "$GENERATED_LINE" "$MARKER_END" \
  > "$dir/report.md"
printf '%s\n%s\n' "Note above." "$(cat "$dir/report.md")" > "$dir/body.md"
out=$(bash "$CHECK" --root "$dir" --splice --body "$dir/body.md" --report "$dir/report.md" \
  --out "$dir/merged.md" 2>&1); rc=$?
if [ "$rc" = 3 ] && [ ! -e "$dir/merged.md" ]; then
  ok_case "an unchanged report exits 3 and writes nothing"
else
  fail_case "an unchanged report exits 3 and writes nothing" "exit $rc" "$out"
fi
# Only the generated-on date moving is still no change - the noise the comparison must ignore.
sed -i 's/2026-01-02/2026-12-31/' "$dir/report.md"
out=$(bash "$CHECK" --root "$dir" --splice --body "$dir/body.md" --report "$dir/report.md" 2>&1); rc=$?
[ "$rc" = 3 ] && ok_case "a moved generated-on date alone is not a change" \
              || fail_case "a moved generated-on date alone is not a change" "exit $rc" "$out"
# A CR on every line is GitHub's normalisation, not a change either.
sed -i 's/$/\r/' "$dir/body.md"
out=$(bash "$CHECK" --root "$dir" --splice --body "$dir/body.md" --report "$dir/report.md" 2>&1); rc=$?
[ "$rc" = 3 ] && ok_case "CRs in the stored body are not a change" \
              || fail_case "CRs in the stored body are not a change" "exit $rc" "$out"
# A real content change is one.
sed -i 's/FRESH REPORT/DIFFERENT REPORT/' "$dir/report.md"
out=$(bash "$CHECK" --root "$dir" --splice --body "$dir/body.md" --report "$dir/report.md" 2>&1); rc=$?
[ "$rc" = 0 ] && ok_case "a changed report row exits 0" \
              || fail_case "a changed report row exits 0" "exit $rc" "$out"
rm -rf "$dir"

dir=$(mktemp -d)
out=$(bash "$CHECK" --root "$dir" --splice --body /nonexistent --report /nonexistent 2>&1); rc=$?
rm -rf "$dir"
[ "$rc" = 2 ] && ok_case "--splice on a missing file exits 2" \
              || fail_case "--splice on a missing file exits 2" "exit $rc" "$out"
case_run "both groups are read, not just the first" 1 "gone-skill" "true"
case_run "the summary counts every verdict" 1 \
  "4 dependencies - 1 current, 1 drifted, 1 missing, 1 unresolvable" "true"

# --- what is refused rather than guessed ---------------------------------------------------
case_run "a lookup that errors exits 2, reporting nothing" 2 "upstream lookup failed" \
  "sed -i 's#\"sha\": \"999999999999#\"error\": \"HTTP 403 rate limited\", \"sha\": \"999999999999#' responses.json"
case_run "a lookup that errors writes no report at all" 2 '!Upstream moved' \
  "sed -i 's#\"sha\": \"999999999999#\"error\": \"HTTP 403 rate limited\", \"sha\": \"999999999999#' responses.json"
case_run "a row with no recorded answer exits 2" 2 "no recorded response" \
  "sed -i 's#skills/moved#skills/renamed#' .claude/profile.yml"
case_run "an unrecognised pin scheme exits 2" 2 "unrecognised pin" \
  "sed -i 's#pin: commit:bbbbbbbbbbbb#pin: v1.2.3#' .claude/profile.yml"
case_run "a dependency missing a key exits 2, naming it" 2 "is missing path" \
  "sed -i '/^      path: skills\/moved$/d' .claude/profile.yml"
case_run "dependencies that is not a mapping exits 2" 2 "dependencies is not a mapping" \
  "printf 'dependencies: []\n' > .claude/profile.yml"
case_run "a profile with no dependencies at all exits 0" 0 "0 dependencies" \
  "printf 'repo:\n  owner: acme\n' > .claude/profile.yml"

# --- --out writes the report to a file rather than stdout ----------------------------------
dir=$(new_fixture) || dir=""
if [ -n "$dir" ]; then
  out=$(bash "$CHECK" --root "$dir" --responses "$dir/responses.json" --out "$dir/report.md" 2>&1); rc=$?
  if [ "$rc" = 1 ] && [ -s "$dir/report.md" ] && ! printf '%s' "$out" | grep -qF 'Upstream moved'; then
    ok_case "--out writes the report to the file, not to stdout"
  else
    fail_case "--out writes the report to the file, not to stdout" "exit $rc" "$out"
  fi
  rm -rf "$dir"
fi

# --- an unusable root is an environment error, never a clean run ---------------------------
dir=$(mktemp -d)
out=$(bash "$CHECK" --root "$dir" 2>&1); rc=$?
rm -rf "$dir"
[ "$rc" = 2 ] && ok_case "a root without a profile exits 2, not 0" \
              || fail_case "a root without a profile exits 2, not 0" "exit $rc" "$out"

EXPECTED=45
printf '\n%d passed, %d failed (of %d cases)\n' "$pass" "$fail" "$EXPECTED"
if [ $((pass + fail)) -ne "$EXPECTED" ]; then
  printf 'FAIL  only %d cases ran, expected %d - a fixture was skipped silently\n' \
    $((pass + fail)) "$EXPECTED"
  exit 1
fi
[ "$fail" -eq 0 ]
