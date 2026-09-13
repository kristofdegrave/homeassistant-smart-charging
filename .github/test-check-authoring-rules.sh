#!/usr/bin/env bash
# Tests for check-authoring-rules.sh. Each case builds a throwaway git repo so the script is
# exercised through the same `git diff base...HEAD` CI uses, rather than a stubbed diff.
#
# Usage: .github/test-check-authoring-rules.sh

set -uo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/check-authoring-rules.sh"
pass=0
fail=0

fail_case() { printf 'FAIL  %s\n' "$1"; shift; printf '%s\n' "$*" | sed 's/^/        /'; fail=$((fail + 1)); }
ok_case()   { printf 'ok    %s\n' "$1"; pass=$((pass + 1)); }

# Build a repo with `seed` committed on `base`, then the caller's changes on top.
# Fails the test rather than silently producing an empty diff if git itself misbehaves.
new_repo() {
  local dir
  dir=$(mktemp -d)
  if ! (
    cd "$dir" || exit 3
    git init -q -b main . && git config user.email t@example.invalid && git config user.name t
  ) >/dev/null 2>&1; then
    rm -rf "$dir"
    return 1
  fi
  printf '%s' "$dir"
}

commit_all() { # <dir> <message>
  (cd "$1" && git add -A && git commit -qm "$2") >/dev/null 2>&1
}

# <name> <expected-exit> <expected-output-substring|-> <file> <added-line>
case_add() {
  local name="$1" want="$2" want_out="$3" path="$4" line="$5" dir out rc
  dir=$(new_repo) || { fail_case "$name" "could not create fixture repo"; return; }
  mkdir -p "$dir/$(dirname "$path")"
  printf 'seed\n' > "$dir/$path"
  commit_all "$dir" seed || { fail_case "$name" "seed commit failed"; rm -rf "$dir"; return; }
  (cd "$dir" && git branch -q base) || { fail_case "$name" "branch failed"; rm -rf "$dir"; return; }
  printf '%s\n' "$line" >> "$dir/$path"
  commit_all "$dir" change || { fail_case "$name" "change commit failed"; rm -rf "$dir"; return; }

  out=$(cd "$dir" && bash "$SCRIPT" base 2>&1); rc=$?
  rm -rf "$dir"

  if [ "$rc" != "$want" ]; then
    fail_case "$name" "expected exit $want, got $rc" "$out"
  elif [ "$want_out" != "-" ] && ! printf '%s' "$out" | grep -qF "$want_out"; then
    fail_case "$name" "output did not contain: $want_out" "$out"
  else
    ok_case "$name"
  fi
}

LINK='See [the workflow](../../../docs/reference/contribution-workflow.md) first.'

# --- a markdown link to project documentation is a route, and is rejected ------------------
case_add "a link from a skill is rejected" 1 \
  "docs/reference/contribution-workflow.md" ".claude/skills/demo/SKILL.md" "$LINK"
case_add "a link from an agent is rejected" 1 \
  "docs/reference/ai-authoring.md" ".claude/agents/demo.md" \
  'Read [the reference](../../docs/reference/ai-authoring.md) for the criteria.'
case_add "a repo-rooted link is rejected" 1 \
  "docs/adl/0009-testing-strategy.md" ".claude/skills/demo/SKILL.md" \
  'Per [ADR-0009](docs/adl/0009-testing-strategy.md), pick the harness.'
case_add "two links on one line: the second is reported too" 1 \
  "docs/adl/0009-testing-strategy.md" ".claude/skills/demo/SKILL.md" \
  'narrowed by [A](../../../docs/adl/0037-scenario-timeline-test-tier.md), reading [B](../../../docs/adl/0009-testing-strategy.md)'

case_add "an anchored link is rejected" 1   "docs/reference/contribution-workflow.md" ".claude/skills/demo/SKILL.md"   'See [Step 3](../../../docs/reference/contribution-workflow.md#step-3-review).'
case_add "a ./-prefixed link is rejected" 1   "docs/adl/0009-testing-strategy.md" ".claude/skills/demo/SKILL.md"   'Per [ADR-0009](./docs/adl/0009-testing-strategy.md), pick the harness.'
case_add "a titled link is rejected" 1   "docs/reference/ai-authoring.md" ".claude/skills/demo/SKILL.md"   'Read [it](../../docs/reference/ai-authoring.md "the reference") first.'

# --- a bare path is a name, not a route, and is legal --------------------------------------
# These are the subject-matter cases the rule expressly keeps named: the template a write-*
# skill drafts against, the index it writes a row into, the artifact it produces.
case_add "a bare path is a name, not a route" 0 - \
  ".claude/skills/demo/SKILL.md" 'Draft against `docs/adl/template.md` — Status, Context.'
case_add "the ADL index it writes into stays named" 0 - \
  ".claude/skills/demo/SKILL.md" '`docs/adl/README.md` gains a row for this ADR.'
case_add "a tree glob stays named" 0 - \
  ".claude/agents/demo.md" 'Review any changed file under docs/adl/** against the template.'
case_add "a CLAUDE.md section pointer is the correct form" 0 - \
  ".claude/skills/demo/SKILL.md" "See \`CLAUDE.md\`'s **Contribution workflow** section."
case_add "CLAUDE.md itself is not project documentation here" 0 - \
  ".claude/skills/demo/SKILL.md" 'Your instructions are this skill and CLAUDE.md.'
case_add "a link to a CLAUDE.md section is the correct form" 0 - \
  ".claude/skills/demo/SKILL.md" 'See [Contribution workflow](../../CLAUDE.md#contribution-workflow).'
case_add "an intra-skill reference link stays legal" 0 - \
  ".claude/skills/demo/SKILL.md" 'Detail in [the notes](references/details.md).'

# --- scope: only the watched trees, only added lines ---------------------------------------
case_add "a link outside the watched trees is ignored" 0 - \
  "docs/reference/some-doc.md" 'Links to [x](../reference/ci-pipeline.md) freely.'
case_add "a link in a workflow file is ignored" 0 - \
  ".github/workflows/_ai-draft.yml" "# follows [it](../../docs/reference/contribution-workflow.md)"

# a pre-existing link on an untouched line must not be flagged
dir=$(new_repo) || { fail_case "untouched pre-existing link" "fixture failed"; dir=""; }
if [ -n "$dir" ]; then
  mkdir -p "$dir/.claude/skills/demo"
  printf '%s\nunrelated\n' "$LINK" > "$dir/.claude/skills/demo/SKILL.md"
  commit_all "$dir" seed
  (cd "$dir" && git branch -q base)
  printf 'a harmless new line\n' >> "$dir/.claude/skills/demo/SKILL.md"
  commit_all "$dir" change
  out=$(cd "$dir" && bash "$SCRIPT" base 2>&1); rc=$?
  [ "$rc" = 0 ] && ok_case "an untouched pre-existing link is not flagged" \
                || fail_case "an untouched pre-existing link is not flagged" "exit $rc" "$out"
  rm -rf "$dir"
fi

# a removed link must not be flagged
dir=$(new_repo) || dir=""
if [ -n "$dir" ]; then
  mkdir -p "$dir/.claude/skills/demo"
  printf '%s\n' "$LINK" > "$dir/.claude/skills/demo/SKILL.md"
  commit_all "$dir" seed
  (cd "$dir" && git branch -q base)
  printf 'replaced\n' > "$dir/.claude/skills/demo/SKILL.md"
  commit_all "$dir" change
  out=$(cd "$dir" && bash "$SCRIPT" base 2>&1); rc=$?
  [ "$rc" = 0 ] && ok_case "a removed link is not flagged" \
                || fail_case "a removed link is not flagged" "exit $rc" "$out"
  rm -rf "$dir"
fi

# --- attribution across a multi-file diff, and a newly added file --------------------------
dir=$(new_repo) || dir=""
if [ -n "$dir" ]; then
  mkdir -p "$dir/.claude/skills/clean" "$dir/.claude/skills/dirty"
  printf 'seed\n' > "$dir/.claude/skills/clean/SKILL.md"
  printf 'seed\n' > "$dir/.claude/skills/dirty/SKILL.md"
  commit_all "$dir" seed
  (cd "$dir" && git branch -q base)
  # a line that renders as `+++ b/...` in the diff, in the file edited FIRST
  printf '++ b/docs/adl/decoy.md is how a diff header looks\n' >> "$dir/.claude/skills/clean/SKILL.md"
  printf '%s\n' "$LINK" >> "$dir/.claude/skills/dirty/SKILL.md"
  commit_all "$dir" change
  out=$(cd "$dir" && bash "$SCRIPT" base 2>&1); rc=$?
  if [ "$rc" != 1 ]; then
    fail_case "a violation is attributed to the right file" "expected exit 1, got $rc" "$out"
  elif printf '%s' "$out" | grep -qF '.claude/skills/dirty/SKILL.md: links to'; then
    ok_case "a violation is attributed to the right file"
  else
    fail_case "a violation is attributed to the right file" "wrong attribution" "$out"
  fi
  rm -rf "$dir"
fi

dir=$(new_repo) || dir=""
if [ -n "$dir" ]; then
  printf 'unrelated\n' > "$dir/README.md"
  commit_all "$dir" seed
  (cd "$dir" && git branch -q base)
  mkdir -p "$dir/.claude/skills/brand-new"
  printf '%s\n' "$LINK" > "$dir/.claude/skills/brand-new/SKILL.md"
  commit_all "$dir" change
  out=$(cd "$dir" && bash "$SCRIPT" base 2>&1); rc=$?
  [ "$rc" = 1 ] && ok_case "a newly added file is checked" \
                || fail_case "a newly added file is checked" "expected exit 1, got $rc" "$out"
  rm -rf "$dir"
fi

# --- the allowlist excuses a reviewed exception --------------------------------------------
dir=$(new_repo) || dir=""
if [ -n "$dir" ]; then
  mkdir -p "$dir/.claude/skills/demo" "$dir/.github"
  printf 'seed\n' > "$dir/.claude/skills/demo/SKILL.md"
  commit_all "$dir" seed
  (cd "$dir" && git branch -q base)
  printf '%s\n' "$LINK" >> "$dir/.claude/skills/demo/SKILL.md"
  printf '.claude/skills/demo/SKILL.md\tdocs/reference/contribution-workflow.md\t# reviewed\n' \
    > "$dir/.github/authoring-rule-allowlist.tsv"
  commit_all "$dir" change
  out=$(cd "$dir" && bash "$SCRIPT" base 2>&1); rc=$?
  [ "$rc" = 0 ] && ok_case "an allowlisted exception passes" \
                || fail_case "an allowlisted exception passes" "expected exit 0, got $rc" "$out"
  rm -rf "$dir"
fi

# --- environment errors stay distinguishable from violations -------------------------------
dir=$(new_repo) || dir=""
if [ -n "$dir" ]; then
  printf 'x\n' > "$dir/f"
  commit_all "$dir" seed
  out=$(cd "$dir" && bash "$SCRIPT" no-such-ref 2>&1); rc=$?
  [ "$rc" = 2 ] && ok_case "an unresolvable base ref exits 2, not 1" \
                || fail_case "an unresolvable base ref exits 2, not 1" "exit $rc" "$out"
  rm -rf "$dir"
fi

EXPECTED=22
printf '\n%d passed, %d failed (of %d cases)\n' "$pass" "$fail" "$EXPECTED"
if [ $((pass + fail)) -ne "$EXPECTED" ]; then
  printf 'FAIL  only %d cases ran, expected %d — a fixture was skipped silently\n' \
    $((pass + fail)) "$EXPECTED"
  exit 1
fi
[ "$fail" -eq 0 ]
