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
only_current="python - <<'PY'
import io
lines = io.open('.claude/profile.yml', encoding='utf-8').read().split('\n')
keep = lines[:lines.index('    - name: moved-skill')]
io.open('.claude/profile.yml', 'w', encoding='utf-8', newline='\n').write('\n'.join(keep) + '\n')
PY"
case_run "every pin current: exit 0 and no report" 0 "1 dependencies - 1 current" "$only_current"
case_run "a current pin produces no table row" 0 '!Upstream moved' "$only_current"

# --- one fixture per verdict ---------------------------------------------------------------
case_run "the full manifest reports and exits 1" 1 "Upstream moved" "true"
case_run "a moved pin is listed with its upstream head" 1 "999999999999" "true"
case_run "a moved pin links the compare view" 1 \
  "https://github.com/acme/skills/compare/bbbbbbbbbbbb...999999999999" "true"
case_run "a current pin appears nowhere in the report" 1 '!current-skill' "true"
case_run "a path no commit touches is reported, not passed" 1 "renamed, deleted or moved" "true"
case_run "an installer hash is unresolvable, not drifted" 1 "cannot be recomputed here" "true"
case_run "an installer hash never reaches the moved table" 1 "| \`hashed-skill\` | \`acme/widgets\` | \`skills/hashed\` | \`sha256:dddddddddddd\` |" "true"
case_run "the report carries the marker the workflow matches on" 1 \
  "<!-- ai-upstream-drift-report -->" "true"
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

EXPECTED=21
printf '\n%d passed, %d failed (of %d cases)\n' "$pass" "$fail" "$EXPECTED"
if [ $((pass + fail)) -ne "$EXPECTED" ]; then
  printf 'FAIL  only %d cases ran, expected %d - a fixture was skipped silently\n' \
    $((pass + fail)) "$EXPECTED"
  exit 1
fi
[ "$fail" -eq 0 ]
