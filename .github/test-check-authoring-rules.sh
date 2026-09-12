#!/usr/bin/env bash
# Tests for check-authoring-rules.sh. Builds a throwaway git repo per case so the fixtures are
# real commits and the script is exercised through the same `git diff base...HEAD` it uses in
# CI — not a stubbed diff, which would test the parser and not the rule.
#
# Usage: .github/test-check-authoring-rules.sh

set -uo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/check-authoring-rules.sh"
pass=0
fail=0

report() { # <name> <expected-exit> <actual-exit> <output>
  if [ "$2" = "$3" ]; then
    printf 'ok    %s\n' "$1"
    pass=$((pass + 1))
  else
    printf 'FAIL  %s (expected exit %s, got %s)\n' "$1" "$2" "$3"
    printf '%s\n' "$4" | sed 's/^/        /'
    fail=$((fail + 1))
  fi
}

# <name> <expected-exit> <file-path> <added-line>
case_add() {
  local name="$1" want="$2" path="$3" line="$4"
  local dir
  dir=$(mktemp -d)
  (
    cd "$dir" || exit 3
    git init -q -b main .
    git config user.email t@example.invalid
    git config user.name t
    mkdir -p "$(dirname "$path")"
    printf 'seed\n' > "$path"
    git add -A && git commit -qm seed
    git branch -q base
    printf '%s\n' "$line" >> "$path"
    git add -A && git commit -qm change
  ) >/dev/null 2>&1
  local out rc
  out=$(cd "$dir" && bash "$SCRIPT" base 2>&1)
  rc=$?
  report "$name" "$want" "$rc" "$out"
  rm -rf "$dir"
}

# --- flagged: a concrete documentation file, in either watched tree -------------------------
case_add "skill naming a docs file is rejected" 1 \
  ".claude/skills/demo/SKILL.md" "See [the workflow](../../../docs/reference/contribution-workflow.md)."
case_add "agent naming a docs file is rejected" 1 \
  ".claude/agents/demo.md" "Read docs/reference/ai-authoring.md first."
case_add "bare docs path without a link is rejected" 1 \
  ".claude/skills/demo/SKILL.md" "Its criteria live in docs/analysis/requirements.md."

# --- allowed: subject matter, routes, and untouched trees -----------------------------------
case_add "a tree glob is subject matter, not a route" 0 \
  ".claude/agents/demo.md" "Review any changed file under docs/adl/** against the template."
case_add "a CLAUDE.md section pointer is the correct form" 0 \
  ".claude/skills/demo/SKILL.md" "See \`CLAUDE.md\`'s **Contribution workflow** section."
case_add "CLAUDE.md itself is not a docs path" 0 \
  ".claude/skills/demo/SKILL.md" "Your instructions are this skill and CLAUDE.md."
case_add "a docs path outside the watched trees is ignored" 0 \
  "docs/reference/something.md" "Links to docs/reference/ci-pipeline.md freely."
case_add "a workflow file naming a docs path is ignored" 0 \
  ".github/workflows/_ai-draft.yml" "# follows docs/reference/contribution-workflow.md"

# --- the back-catalogue is out of scope: only ADDED lines count -----------------------------
preexisting=$(mktemp -d)
(
  cd "$preexisting" || exit 3
  git init -q -b main .
  git config user.email t@example.invalid
  git config user.name t
  mkdir -p .claude/skills/demo
  printf 'Read docs/reference/contribution-workflow.md.\nunrelated\n' > .claude/skills/demo/SKILL.md
  git add -A && git commit -qm seed
  git branch -q base
  printf 'a harmless new line\n' >> .claude/skills/demo/SKILL.md
  git add -A && git commit -qm change
) >/dev/null 2>&1
out=$(cd "$preexisting" && bash "$SCRIPT" base 2>&1); rc=$?
report "an untouched pre-existing path is not flagged" 0 "$rc" "$out"
rm -rf "$preexisting"

# --- environment errors are distinguishable from violations ---------------------------------
badbase=$(mktemp -d)
(
  cd "$badbase" || exit 3
  git init -q -b main .
  git config user.email t@example.invalid
  git config user.name t
  printf 'x\n' > f && git add -A && git commit -qm seed
) >/dev/null 2>&1
out=$(cd "$badbase" && bash "$SCRIPT" no-such-ref 2>&1); rc=$?
report "an unresolvable base ref exits 2, not 1" 2 "$rc" "$out"
rm -rf "$badbase"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
