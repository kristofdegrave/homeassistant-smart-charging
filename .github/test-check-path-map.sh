#!/usr/bin/env bash
# Tests for check-path-map.py. A throwaway root holding the source and all three consumers,
# each spelling the same four trees in its own grammar, is built, shown to pass, and then
# varied one way per verdict — so every finding the script can report has a fixture, alongside
# the cases that pin down what it deliberately accepts.
#
# Two properties get their own cases rather than being assumed. That a finding names WHICH
# consumer is missing WHICH tree: the cases assert on that sentence, not on the exit code, so a
# message degrading to "they disagree" fails here. And that an enumeration the script cannot
# find exits 2 rather than passing over nothing — a check that is green because it read nothing
# is the failure mode this whole check exists to remove.
#
# No case touches the network or the real repository: every run passes --root.
#
# Usage: .github/test-check-path-map.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/check-path-map.sh"
pass=0
fail=0

fail_case() { printf 'FAIL  %s\n' "$1"; shift; printf '%s\n' "$*" | sed 's/^/        /'; fail=$((fail + 1)); }
ok_case()   { printf 'ok    %s\n' "$1"; pass=$((pass + 1)); }

# Four trees, one per shape the real map has: a plain tree glob, a tree glob whose consumers
# spell it differently, a `*` glob that must survive the prompt's shell quoting, and a single
# file. Two work types, so a mis-routed tree is expressible.
build_fixture() {
  local d="$1"
  mkdir -p "$d/.claude" "$d/.github/workflows"
  cat > "$d/.claude/profile.yml" <<'EOF'
work_types:
  enabled:
    - alpha
    - beta
review:
  interactive_cap: 2
  path_map:
    - work_type: alpha
      paths: ["src/**"]
    - work_type: beta
      paths:
        - ".github/workflows/**"
        - ".github/check-*"
        - "CLAUDE.md"
EOF
  cat > "$d/CLAUDE.md" <<'EOF'
# Guide

## Model selection

**The no-label row routes by changed path**, for every PR:
`src/**` → `docs/reference/work-types/alpha/review.md`;
`.github/workflows/**`, `.github/check-*` and
`CLAUDE.md` →
`docs/reference/work-types/beta/review.md`. Every entry names a checklist file.

Nothing else in this file is parsed.
EOF
  cat > "$d/.github/workflows/ai-pipeline.yml" <<'EOF'
name: Router
on:
  pull_request:
    types: [labeled]
    paths:
      - "src/**"
      - ".github/workflows/**"
      - ".github/check-*"
      - "CLAUDE.md"
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - run: "true"
EOF
  cat > "$d/.github/workflows/_ai-review.yml" <<'EOF'
name: Review
on:
  workflow_call:
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - name: Fresh-agent review
        uses: anthropics/claude-code-action@v1
        with:
          prompt: |
            Review the changes in pull request #1.
            Run `git diff BASE...HEAD -- src .github/workflows '.github/check-*' CLAUDE.md`
            to see the changed files.
EOF
}

new_fixture() {
  local dir
  dir=$(mktemp -d) || return 1
  build_fixture "$dir" || { rm -rf "$dir"; return 1; }
  printf '%s' "$dir"
}

# One case: build the layout, apply `mutate` inside it, and assert the exit code and — unless
# want_out is `-` — one literal sentence of the output.
case_run() {
  local name="$1" want="$2" want_out="$3" mutate="$4" dir out rc
  dir=$(new_fixture) || { fail_case "$name" "could not build fixture"; return; }
  (cd "$dir" && eval "$mutate") || { fail_case "$name" "mutation failed"; rm -rf "$dir"; return; }
  out=$(bash "$CHECK" --root "$dir" 2>&1); rc=$?
  rm -rf "$dir"
  if [ "$rc" != "$want" ]; then
    fail_case "$name" "expected exit $want, got $rc" "$out"
  elif [ "$want_out" != "-" ] && ! printf '%s' "$out" | grep -qF -- "$want_out"; then
    fail_case "$name" "output did not contain: $want_out" "$out"
  else
    ok_case "$name"
  fi
}

# --- the layout as built passes, and the accepted shapes are pinned ------------------------
# An accepted shape expects the verdict the *unmutated* layout already gives, so a mutation
# that quietly matched nothing would pass its case for the wrong reason — a `sed -i` with no
# match succeeds. Each of these therefore ends in an assertion that its edit landed, which the
# harness reads as "mutation failed" rather than as a pass. The exit-1 and exit-2 cases need no
# such assertion: their baseline is 0, so a no-op fails them loudly.
case_run "four trees across three consumers is clean" 0 "check-path-map: clean (4 trees, 3 consumers)" "true"
case_run "a consumer may list the trees in another order" 0 - \
  "sed -i '/^      - \"src\/\*\*\"\$/d' .github/workflows/ai-pipeline.yml \
   && sed -i 's#^      - \"CLAUDE.md\"#      - \"CLAUDE.md\"\n      - \"src/**\"#' .github/workflows/ai-pipeline.yml \
   && [ \"\$(grep -E '^      - \"' .github/workflows/ai-pipeline.yml | tail -1)\" = '      - \"src/**\"' ]"
# Inserted INSIDE the marker's paragraph, not after the blank line below it: the paragraph
# scoping alone would carry a case written the easy way, and it would still pass with the
# arrow-cursor scan removed. The real CLAUDE.md names the other enumerations, and
# `docs/postmortems/**`, in backticks inside this paragraph — that is the shape being pinned.
case_run "backticked prose after the last arrow is not part of the map" 0 - \
  "sed -i 's#^\`docs/reference/work-types/beta/review.md\`. Every entry names a checklist file.\$#\`docs/reference/work-types/beta/review.md\`. The same set is in \`ai-pipeline.yml\`; \`docs/postmortems/**\` keeps its own rule.#' CLAUDE.md \
   && grep -qF 'docs/postmortems/**' CLAUDE.md"
case_run "a pathspec entry quoted where it need not be is still one tree" 0 - \
  "sed -i \"s#-- src #-- 'src' #\" .github/workflows/_ai-review.yml \
   && grep -qF -- \"-- 'src' \" .github/workflows/_ai-review.yml"

# --- a tree in the source that a consumer does not carry -----------------------------------
# The acceptance criterion, as a fixture: adding a tree to the source fails until all three
# follow, and each of the three says so in its own name.
case_run "a tree added to the source fails the path filter by name" 1 \
  ".github/workflows/ai-pipeline.yml: \`on.pull_request.paths\` is missing \`docs/new/**\`" \
  "sed -i 's#^        - \"CLAUDE.md\"#        - \"CLAUDE.md\"\n        - \"docs/new/**\"#' .claude/profile.yml"
case_run "a tree added to the source fails the diff enumeration, in its own spelling" 1 \
  ".github/workflows/_ai-review.yml: the \`git diff ... -- <paths>\` enumeration is missing \`docs/new\`" \
  "sed -i 's#^        - \"CLAUDE.md\"#        - \"CLAUDE.md\"\n        - \"docs/new/**\"#' .claude/profile.yml"
case_run "a tree added to the source fails CLAUDE.md, with the work type it routes to" 1 \
  "CLAUDE.md: the no-label row's path map is missing \`docs/new/** -> beta\`" \
  "sed -i 's#^        - \"CLAUDE.md\"#        - \"CLAUDE.md\"\n        - \"docs/new/**\"#' .claude/profile.yml"
case_run "a tree dropped from the path filter alone fails, naming only that file" 1 \
  ".github/workflows/ai-pipeline.yml: \`on.pull_request.paths\` is missing \`src/**\`" \
  "sed -i '/^      - \"src\/\*\*\"$/d' .github/workflows/ai-pipeline.yml"
case_run "a tree dropped from the diff enumeration alone fails" 1 \
  ".github/workflows/_ai-review.yml: the \`git diff ... -- <paths>\` enumeration is missing \`src\`" \
  "sed -i 's#-- src .github/workflows#-- .github/workflows#' .github/workflows/_ai-review.yml"
case_run "a tree dropped from CLAUDE.md's row alone fails" 1 \
  "CLAUDE.md: the no-label row's path map is missing \`src/** -> alpha\`" \
  "sed -i '/^\`src\/\*\*\` → /d' CLAUDE.md"

# --- a tree in a consumer that the source does not carry -----------------------------------
case_run "a tree the path filter carries and the source does not fails" 1 \
  ".github/workflows/ai-pipeline.yml: \`on.pull_request.paths\` carries \`docs/stray/**\`" \
  "sed -i 's#^      - \"CLAUDE.md\"#      - \"CLAUDE.md\"\n      - \"docs/stray/**\"#' .github/workflows/ai-pipeline.yml"
case_run "a tree the diff enumeration carries and the source does not fails" 1 \
  "the \`git diff ... -- <paths>\` enumeration carries \`docs/stray\`" \
  "sed -i 's#-- src .github/workflows#-- src docs/stray .github/workflows#' .github/workflows/_ai-review.yml"

# --- the same tree, spelled wrong --------------------------------------------------------
# Both halves report, and that is the point: "missing X" alone would read as a tree nobody
# carries, when what happened is that one consumer spelled it in another consumer's grammar.
case_run "a glob left in the pathspec reads as a missing tree" 1 \
  "enumeration is missing \`src\`" \
  "sed -i 's#-- src #-- src/** #' .github/workflows/_ai-review.yml"
case_run "a glob left in the pathspec reads as an extra one too" 1 \
  "enumeration carries \`src/**\`" \
  "sed -i 's#-- src #-- src/** #' .github/workflows/_ai-review.yml"
case_run "a tree CLAUDE.md routes to the wrong checklist fails" 1 \
  "CLAUDE.md: the no-label row's path map is missing \`src/** -> alpha\`" \
  "sed -i 's#^\`src/\*\*\` → \`docs/reference/work-types/alpha/review.md\`;#\`src/**\` → \`docs/reference/work-types/beta/review.md\`;#' CLAUDE.md"
case_run "a tree routed to a work type nobody enables fails at the source" 1   ".claude/profile.yml: \`review.path_map\` routes \`src/**\` to \`alpha\`, which \`work_types.enabled\` does not name"   "sed -i '/^    - alpha$/d' .claude/profile.yml"
case_run "a tree listed twice in the source fails there, not silently" 1 \
  ".claude/profile.yml: \`review.path_map\` lists \`src/**\` more than once" \
  "sed -i 's#^      paths: \[\"src/\*\*\"\]#      paths: [\"src/**\", \"src/**\"]#' .claude/profile.yml"
case_run "a tree listed twice in one consumer fails" 1 \
  "\`on.pull_request.paths\` lists \`src/**\` more than once" \
  "sed -i 's#^      - \"src/\*\*\"#      - \"src/**\"\n      - \"src/**\"#' .github/workflows/ai-pipeline.yml"

# --- an enumeration that cannot be found is 2, never a pass --------------------------------
case_run "a path filter that is gone exits 2, not 0" 2 "has no \`on.pull_request.paths\` filter" \
  "sed -i '/^    paths:$/,/^      - \"CLAUDE.md\"$/d' .github/workflows/ai-pipeline.yml"
case_run "a diff enumeration that is gone exits 2, not 0" 2 "has no \`git diff ... -- <paths>\` enumeration" \
  "sed -i 's#Run \`git diff.*\`#Run the diff.#' .github/workflows/_ai-review.yml"
case_run "a second diff enumeration exits 2 rather than picking one" 2 "has 2 \`git diff" \
  "sed -i 's#            to see the changed files.#            Or \`git diff BASE...HEAD -- src\`.\n            to see the changed files.#' .github/workflows/_ai-review.yml"
case_run "a CLAUDE.md without the path-map paragraph exits 2" 2 "has no \`**The no-label row routes by changed path**\` paragraph" \
  "sed -i '/^\*\*The no-label row routes by changed path\*\*/,+5d' CLAUDE.md"
case_run "a source with no path_map exits 2" 2 "declares no \`review.path_map\` entries" \
  "sed -i '/^  path_map:$/,\$d' .claude/profile.yml"
case_run "a profile that is not valid YAML exits 2" 2 "is not valid YAML" \
  "printf '  : : :\n' >> .claude/profile.yml"

# --- --warn: the same findings, exit 0 ----------------------------------------------------
dir=$(new_fixture) || dir=""
if [ -n "$dir" ]; then
  sed -i '/^      - "src\/\*\*"$/d' "$dir/.github/workflows/ai-pipeline.yml"
  out=$(bash "$CHECK" --root "$dir" --warn 2>&1); rc=$?
  if [ "$rc" = 0 ] && printf '%s' "$out" | grep -qF 'warning: .github/workflows/ai-pipeline.yml'; then
    ok_case "--warn: the same findings, exit 0"
  else
    fail_case "--warn: the same findings, exit 0" "exit $rc" "$out"
  fi
  rm -rf "$dir"
fi

dir=$(mktemp -d)
out=$(bash "$CHECK" --root "$dir" 2>&1); rc=$?
rm -rf "$dir"
[ "$rc" = 2 ] && ok_case "a root with no profile at all exits 2, not 1" \
              || fail_case "a root with no profile at all exits 2, not 1" "exit $rc" "$out"

EXPECTED=26
printf '\n%d passed, %d failed (of %d cases)\n' "$pass" "$fail" "$EXPECTED"
if [ $((pass + fail)) -ne "$EXPECTED" ]; then
  printf 'FAIL  only %d cases ran, expected %d — a fixture was skipped silently\n' \
    $((pass + fail)) "$EXPECTED"
  exit 1
fi
[ "$fail" -eq 0 ]
