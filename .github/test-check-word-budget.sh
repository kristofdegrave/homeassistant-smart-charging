#!/usr/bin/env bash
# Tests for check-word-budget.py. Each case builds a throwaway git repository whose profile caps
# every class at 10 words, commits a base, changes it one way, and runs the check against that
# base. Findings are asserted on their text, not only the exit code, so a message that stops
# naming the file or the words to cut fails here.
#
# Usage: .github/test-check-word-budget.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/check-word-budget.sh"
pass=0
fail=0

words() { local n="$1" out=""; for _ in $(seq "$n"); do out="$out w"; done; echo "$out"; }

# A repository at its base commit: one file under its cap, one over it, one ADR, one file in no
# class. `special.md` sits in two classes, so the first one listed has to win.
new_repo() {
  local d
  d="$(mktemp -d)"
  git -C "$d" init -q
  git -C "$d" config user.email t@example.com
  git -C "$d" config user.name t
  git -C "$d" config core.autocrlf false
  mkdir -p "$d/.claude" "$d/docs/method" "$d/docs/adl"
  cat > "$d/.claude/profile.yml" <<'EOF'
word_budgets:
  - glob: "docs/method/special.md"
    cap: 30
  - glob: "docs/method/*.md"
    cap: 10
  - glob: "docs/tree/**/*.md"
    cap: 10
  - glob: "docs/adl/*.md"
    cap: 10
    added_only: true
EOF
  words 5 > "$d/docs/method/small.md"
  words 20 > "$d/docs/method/big.md"
  words 20 > "$d/docs/adl/0001-old.md"
  words 20 > "$d/docs/other.md"
  git -C "$d" add -A && git -C "$d" commit -qm base
  echo "$d"
}

commit() { git -C "$1" add -A && git -C "$1" commit -qm change; }

# expect <name> <exit> <text or ""> <repo>
expect() {
  local name="$1" want="$2" text="$3" d="$4" out code
  out="$(bash "$CHECK" "$(git -C "$d" rev-list --max-parents=0 HEAD)" --root "$d" 2>&1)"
  code=$?
  if [ "$code" -ne "$want" ] || { [ -n "$text" ] && ! grep -qF -- "$text" <<<"$out"; }; then
    printf 'FAIL  %s (exit %s, want %s)\n%s\n' "$name" "$code" "$want" "$out" | sed '2,$s/^/        /'
    fail=$((fail + 1))
  else
    printf 'ok    %s\n' "$name"
    pass=$((pass + 1))
  fi
  rm -rf "$d"
}

d="$(new_repo)"; words 10 > "$d/docs/method/small.md"; commit "$d"
expect "a file under its cap grows to the cap" 0 "clean" "$d"

d="$(new_repo)"; words 12 > "$d/docs/method/small.md"; commit "$d"
expect "a file grows past its cap" 1 "docs/method/small.md: 12 words (cap 10); cut 2" "$d"

d="$(new_repo)"; words 21 > "$d/docs/method/big.md"; commit "$d"
expect "a file over its cap grows" 1 "docs/method/big.md: 21 words (over its cap of 10, it may not grow past 20); cut 1" "$d"

d="$(new_repo)"; words 15 > "$d/docs/method/big.md"; commit "$d"
expect "a file over its cap shrinks but stays over" 0 "clean" "$d"

d="$(new_repo)"; git -C "$d" mv docs/method/big.md docs/method/moved.md; commit "$d"
expect "a file over its cap is renamed unchanged" 0 "clean" "$d"

d="$(new_repo)"; words 11 > "$d/docs/adl/0002-new.md"; commit "$d"
expect "an added ADR over its cap" 1 "docs/adl/0002-new.md: 11 words (cap 10); cut 1" "$d"

d="$(new_repo)"; words 25 > "$d/docs/adl/0001-old.md"; commit "$d"
expect "an existing ADR is not scored" 0 "clean" "$d"

d="$(new_repo)"; words 50 > "$d/docs/other.md"; commit "$d"
expect "a file in no class is not scored" 0 "clean" "$d"

d="$(new_repo)"; mkdir -p "$d/docs/tree"; words 12 > "$d/docs/tree/top.md"; commit "$d"
expect "a ** class matches its top level" 1 "docs/tree/top.md: 12 words (cap 10); cut 2" "$d"

d="$(new_repo)"; mkdir -p "$d/docs/tree/a/b"; words 12 > "$d/docs/tree/a/b/deep.md"; commit "$d"
expect "a ** class matches nested files" 1 "docs/tree/a/b/deep.md: 12 words (cap 10); cut 2" "$d"

d="$(new_repo)"; words 25 > "$d/docs/method/special.md"; commit "$d"
expect "the first class a path matches wins" 0 "clean" "$d"

d="$(new_repo)"; git -C "$d" mv docs/other.md docs/adl/0003-moved.md; commit "$d"
expect "a file renamed into an added_only class is scored" 1 "docs/adl/0003-moved.md: 20 words (cap 10); cut 10" "$d"

d="$(new_repo)"; git -C "$d" mv docs/other.md docs/method/moved-in.md; commit "$d"
expect "a file renamed in from no class is held to the cap" 1 "docs/method/moved-in.md: 20 words (cap 10); cut 10" "$d"

d="$(new_repo)"; git -C "$d" rm -q docs/method/big.md; commit "$d"
expect "a deleted file is not scored" 0 "clean" "$d"

d="$(new_repo)"; : > "$d/.claude/profile.yml"; commit "$d"
expect "no word_budgets exits 2" 2 "no word_budgets" "$d"

d="$(new_repo)"
out="$(bash "$CHECK" no-such-commit --root "$d" 2>&1)"; code=$?
if [ "$code" -eq 2 ] && grep -qF "git failed" <<<"$out"; then
  printf 'ok    %s\n' "an unknown base exits 2"; pass=$((pass + 1))
else
  printf 'FAIL  %s (exit %s)\n        %s\n' "an unknown base exits 2" "$code" "$out"; fail=$((fail + 1))
fi
rm -rf "$d"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
