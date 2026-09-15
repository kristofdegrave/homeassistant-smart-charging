#!/usr/bin/env bash
# Tests for check-method.py. A minimal but complete method layout is built in a throwaway
# directory, shown to pass, and then broken one way per check — so each of the five checks has
# a fixture that fails it, plus the cases that pin down what the checks deliberately accept.
#
# Usage: .github/test-check-method.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/check-method.sh"
pass=0
fail=0

fail_case() { printf 'FAIL  %s\n' "$1"; shift; printf '%s\n' "$*" | sed 's/^/        /'; fail=$((fail + 1)); }
ok_case()   { printf 'ok    %s\n' "$1"; pass=$((pass + 1)); }

# A complete, passing layout: two enabled work types, one review-only; a routing table with a
# whole-document entry and an anchored one; one authored skill, one declared dependency skill
# and one user-installed dependency; an agent; three method documents and a project one.
build_fixture() {
  local d="$1"
  mkdir -p "$d/.claude/skills/step" "$d/.claude/skills/dep-skill" "$d/.claude/agents" \
           "$d/docs/reference/work-types/alpha" "$d/docs/reference/work-types/beta" "$d/src"
  cat > "$d/CLAUDE.md" <<'EOF'
# Guide

## Rules that hold before anything is chosen

- Read the **Contribution workflow** topic first.

## Model selection

| Context label | How the work is done | Work model | How it is reviewed | Review model |
|---|---|---|---|---|
| `alpha` | work file `docs/reference/work-types/alpha/implement.md`; completion bar `docs/reference/work-types/alpha/done.md` | opus | completion bar `docs/reference/work-types/alpha/done.md`; checklist `docs/reference/work-types/alpha/review.md` | opus |
| `beta` | none — human-authored | — | checklist `docs/reference/work-types/beta/review.md` | opus |
| *(no context label)* | none | — | by changed path | opus |

**The no-label row routes by changed path**, for every PR:
`src/**` → `docs/reference/work-types/alpha/review.md`;
`.claude/**`, `docs/reference/**` and
`CLAUDE.md` →
`docs/reference/work-types/beta/review.md`. Every entry names a checklist file.

**Label and path both route.** Nothing else here is parsed.

## Routing table

| Topic | Owner |
|---|---|
| **Contribution workflow** | [wf.md](docs/reference/wf.md) — the chain. |
| **Issue conventions** | [wf.md#issue-conventions](docs/reference/wf.md#issue-conventions) |
| **Project profile** | [profile.md](docs/reference/profile.md) and `.claude/profile.yml` |
EOF
  cat > "$d/.claude/profile.yml" <<'EOF'
repo:
  owner: acme
  name: widget-repo
board:
  number: 1
  name: BOARD
  project_id: PVT_projectnode
  fields:
    size:
      id: PVTSSF_sizefield
      type: single_select
      options:
        S: "aaaa1111"
    status:
      id: PVTSSF_statusfield
      type: single_select
      options:
        Backlog: "bbbb1111"
        In progress: "bbbb2222"
        Done: "bbbb3333"
labels:
  context:
    - name: alpha
      color: 1d76db
      description: "alpha work"
    - name: beta
      color: e99695
      description: "beta work"
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
      paths: [".claude/**", "docs/reference/**", "CLAUDE.md"]
dependencies:
  method:
    - name: dep-skill
      source: example/skills
      path: skills/dep-skill
      pin: commit:0000000
      installed: repo
    - name: user-skill
      source: example/skills
      path: skills/user-skill
      pin: commit:0000000
      installed: user
EOF
  cat > "$d/.claude/skills/step/SKILL.md" <<'EOF'
---
name: step
layer: method
description: A step skill.
---

Dispatch per `CLAUDE.md`'s **Model selection** table; the board move is the rule under
`CLAUDE.md`'s **Contribution workflow**. Filing conventions: `CLAUDE.md`'s **Issue
conventions** topic. The pointer form is written `` `CLAUDE.md`'s **Topic** ``.
EOF
  cat > "$d/.claude/skills/dep-skill/SKILL.md" <<'EOF'
---
name: dep-skill
description: Vendored upstream skill, no layer frontmatter by design.
---

Upstream content. Owner acme is named here and that is fine: this is not a method file.
EOF
  cat > "$d/.claude/agents/reviewer.md" <<'EOF'
---
name: reviewer
layer: method
tools: Read
---

Resolve the checklist from `CLAUDE.md`'s **Model selection** table.
EOF
  cat > "$d/docs/reference/wf.md" <<'EOF'
---
layer: method
---

# Contribution workflow

The chain moves an item from the *backlog* column to the *done* column. Prefix pointers
resolve: `CLAUDE.md`'s **Issue** is a prefix of a topic.

## Issue conventions

### Branch naming

`<label>/<n>`.
EOF
  cat > "$d/docs/reference/profile.md" <<'EOF'
---
layer: project
---

# Project profile

Owner acme, repository widget-repo, board BOARD; the `Backlog` column is the *backlog* role.
A project file may spell every one of these.
EOF
  for f in alpha/implement.md alpha/done.md alpha/review.md beta/review.md; do
    printf -- '---\nlayer: method\n---\n\n# %s\n\n## The bar\n\nContent.\n' "$f" > "$d/docs/reference/work-types/$f"
  done
}

new_fixture() {
  local dir
  dir=$(mktemp -d) || return 1
  build_fixture "$dir" || { rm -rf "$dir"; return 1; }
  printf '%s' "$dir"
}

# <name> <expected-exit> <expected-output-substring|-> <shell snippet run inside the fixture>
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
case_run "a complete layout is clean" 0 "check-method: clean" "true"
case_run "a pointer that is a prefix of a topic resolves" 0 - \
  "printf 'See \`CLAUDE.md\`'\"'\"'s **Model** table.\n' >> .claude/skills/step/SKILL.md"
case_run "a pointer wrapped across lines resolves" 0 - \
  "printf 'See \`CLAUDE.md\`'\"'\"'s **Contribution\n  workflow** topic.\n' >> docs/reference/wf.md"
case_run "the documented **Topic** placeholder is skipped" 0 - \
  "printf 'Written as \`CLAUDE.md\`'\"'\"'s **Topic**.\n' >> docs/reference/wf.md"
case_run "a declared dependency needs no layer frontmatter" 0 - "true"
case_run "a review-only row needs only review.md" 0 - "true"
case_run "a single-word status name written bare is not a value" 0 - \
  "printf 'Definition of Done; the work is Done when Ready.\n' >> docs/reference/wf.md"
case_run "a project-layer file may spell profile values" 0 - \
  "printf 'PVT_projectnode and \`In progress\` are fine here.\n' >> docs/reference/profile.md"

# --- 1  anchors, outward -------------------------------------------------------------------
case_run "1: an unresolvable pointer in a skill fails" 1 "**Nowhere**" \
  "printf 'See \`CLAUDE.md\`'\"'\"'s **Nowhere** section.\n' >> .claude/skills/step/SKILL.md"
case_run "1: an unresolvable pointer in a reference doc fails" 1 "[1 anchors, outward] docs/reference/wf.md" \
  "printf 'See \`CLAUDE.md\`'\"'\"'s **Nowhere** section.\n' >> docs/reference/wf.md"
case_run "1: an unresolvable pointer in a CI workflow fails" 1 ".github/workflows/_ai-x.yml" \
  "mkdir -p .github/workflows && printf 'prompt: CLAUDE.md'\"'\"'s **Nowhere**\n' > .github/workflows/_ai-x.yml"
case_run "1: renaming a CLAUDE.md heading breaks the skills pointing at it" 1 "**Model selection**" \
  "sed -i 's/^## Model selection$/## Row selection/' CLAUDE.md"

# --- 2  anchors, inward --------------------------------------------------------------------
case_run "2: a routing entry linking a missing file fails" 1 "docs/reference/gone.md does not exist" \
  "sed -i 's#\[wf.md\](docs/reference/wf.md)#[gone.md](docs/reference/gone.md)#' CLAUDE.md"
case_run "2: a routing entry with a missing anchor fails" 1 "no heading in docs/reference/wf.md has that anchor" \
  "sed -i 's/wf.md#issue-conventions)/wf.md#issue-rules)/' CLAUDE.md"
case_run "2: a table cell naming a missing file fails" 1 "docs/reference/work-types/alpha/bar.md, which does not exist" \
  "sed -i 's#work-types/alpha/done.md\`; checklist#work-types/alpha/bar.md\`; checklist#' CLAUDE.md"
case_run "2: a ### heading under no ## fails" 1 "sits under no \`##\`" \
  "printf -- '---\nlayer: method\n---\n\n# Loose\n\n### Orphan rule\n\nText.\n' > docs/reference/loose.md"

# --- 3  profile agreement ------------------------------------------------------------------
case_run "3: an enabled work type without a row fails" 1 "has no Model selection row" \
  "sed -i 's/^    - beta$/    - beta\n    - gamma/' .claude/profile.yml && sed -i 's/^    - name: beta$/    - name: gamma\n      color: 000000\n      description: \"g\"\n    - name: beta/' .claude/profile.yml"
case_run "3: a row for a work type the profile does not enable fails" 1 "is not an enabled work type" \
  "sed -i '/^    - beta$/d; /^    - name: beta$/,/^      description: \"beta work\"$/d' .claude/profile.yml"
case_run "3: context labels and enabled work types differing fails" 1 "name different sets" \
  "sed -i 's/^    - name: beta$/    - name: gamma/' .claude/profile.yml"
case_run "3: a path the table routes and the profile does not fails" 1 "profile.yml review.path_map does not" \
  "sed -i 's#paths: \[\"src/\*\*\"\]#paths: [\"lib/**\"]#' .claude/profile.yml"
case_run "3: a path the profile routes and the table does not fails" 1 "CLAUDE.md's path map does not" \
  "sed -i 's#paths: \[\"src/\*\*\"\]#paths: [\"src/**\", \"lib/**\"]#' .claude/profile.yml"

# --- 4  work-type completeness -------------------------------------------------------------
case_run "4: an enabled work type missing its bar fails" 1 "has no done.md" \
  "rm docs/reference/work-types/alpha/done.md"
case_run "4: a review-only work type missing review.md fails" 1 "has no review.md" \
  "rm docs/reference/work-types/beta/review.md"
case_run "4: a repo-installed dependency that is absent fails" 1 "declared dependency \`dep-skill\`" \
  "rm -r .claude/skills/dep-skill"
case_run "4: a skill that is neither layered nor declared fails" 1 "carries no \`layer:\`" \
  "mkdir .claude/skills/rogue && printf -- '---\nname: rogue\n---\n\nbody\n' > .claude/skills/rogue/SKILL.md"
case_run "4: an unknown layer value fails" 1 "is not one of" \
  "sed -i 's/^layer: method$/layer: stak/' .claude/agents/reviewer.md"
case_run "4: a reference doc without frontmatter fails" 1 "docs/reference/wf.md: carries no \`layer:\`" \
  "sed -i '1,3d' docs/reference/wf.md"

# --- 5  no profile values in method files --------------------------------------------------
case_run "5: the owner in a method doc fails" 1 "profile value repo.owner" \
  "printf 'Owned by acme.\n' >> docs/reference/wf.md"
case_run "5: a node id in a skill fails" 1 "profile value board.fields.status.id" \
  "printf 'Edit field PVTSSF_statusfield.\n' >> .claude/skills/step/SKILL.md"
case_run "5: a backticked status name in a method file fails" 1 "profile value status \`Done\`" \
  "printf 'Move it to \`Done\`.\n' >> docs/reference/wf.md"
case_run "5: a multi-word status name written bare fails" 1 "profile value status \`In progress\`" \
  "printf 'Status -> In progress.\n' >> .claude/agents/reviewer.md"

# --- modes and environment -----------------------------------------------------------------
dir=$(new_fixture) || dir=""
if [ -n "$dir" ]; then
  printf 'Owned by acme.\n' >> "$dir/docs/reference/wf.md"
  out=$(bash "$CHECK" --root "$dir" --warn 2>&1); rc=$?
  if [ "$rc" = 0 ] && printf '%s' "$out" | grep -qF 'warning: [5'; then
    ok_case "--warn: the same findings, exit 0"
  else
    fail_case "--warn: the same findings, exit 0" "exit $rc" "$out"
  fi
  rm -rf "$dir"
fi
dir=$(mktemp -d)
out=$(bash "$CHECK" --root "$dir" 2>&1); rc=$?
rm -rf "$dir"
[ "$rc" = 2 ] && ok_case "a root without CLAUDE.md and a profile exits 2, not 1" \
              || fail_case "a root without CLAUDE.md and a profile exits 2, not 1" "exit $rc" "$out"

EXPECTED=33
printf '\n%d passed, %d failed (of %d cases)\n' "$pass" "$fail" "$EXPECTED"
if [ $((pass + fail)) -ne "$EXPECTED" ]; then
  printf 'FAIL  only %d cases ran, expected %d — a fixture was skipped silently\n' \
    $((pass + fail)) "$EXPECTED"
  exit 1
fi
[ "$fail" -eq 0 ]
