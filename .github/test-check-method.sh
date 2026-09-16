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
# and one user-installed dependency; one declared stack (`widgets`) with a stack skill and its
# tokens; an agent; method documents placed by the default rule, one project document placed
# by its `layer:` override, and one overlay placed as stack by position; the work type with a
# work file carries the `### Skills` rule and the `## Overlays` slot, filled for the stack.
build_fixture() {
  local d="$1"
  mkdir -p "$d/.claude/skills/step" "$d/.claude/skills/dep-skill" "$d/.claude/skills/stack-skill" "$d/.claude/agents" \
           "$d/docs/reference/work-types/alpha/overlays" "$d/docs/reference/work-types/beta" "$d/src"
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
| **Definition of Done** | [dod.md](docs/reference/dod.md) — the floor, and the commit prefixes. |
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
stacks:
  widgets:
    tokens:
      - gizmo
      - Widget Kit
review:
  interactive_cap: 2
  path_map:
    - work_type: alpha
      paths: ["src/**"]
    - work_type: beta
      paths: [".claude/**", "docs/reference/**", "CLAUDE.md"]
dependencies:
  stack:
    - name: stack-skill
      stack: widgets
      source: example/stacks
      path: skills/stack-skill
      pin: commit:0000000
      installed: repo
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
  printf -- '---\nname: stack-skill\n---\n\nA stack package, declared in the stack group; owner acme spelled freely.\n' > "$d/.claude/skills/stack-skill/SKILL.md"
  cat > "$d/.claude/agents/reviewer.md" <<'EOF'
---
name: reviewer
layer: method
tools: Read
---
<!-- layer: method is legal and redundant: the agents tree defaults to it -->

Resolve the checklist from `CLAUDE.md`'s **Model selection** table.
EOF
  cat > "$d/docs/reference/wf.md" <<'EOF'
# Contribution workflow

The chain moves an item from the *backlog* column to the *done* column. Prefix pointers
resolve: `CLAUDE.md`'s **Issue** is a prefix of a topic.

## Issue conventions

### Branch naming

`<label>/<n>`.
EOF
  cat > "$d/docs/reference/dod.md" <<'EOF'
# Definition of Done

## Commit message conventions

| Context label | Default prefix | Example |
|---|---|---|
| `alpha` | `alpha:` | `alpha: a thing` |
| `beta` | `beta:` | `beta: another thing` |
| anything else | conventional-commit type | `fix: a thing` |
EOF
  cat > "$d/docs/reference/profile.md" <<'EOF'
---
layer: project
---

# Project profile

Owner acme, repository widget-repo, board BOARD; the `Backlog` column is the *backlog* role.
A project file may spell every one of these.

## Flow

**Default.** No `###` here means the flow as written.
EOF
  for f in alpha/done.md alpha/review.md beta/review.md; do
    printf -- '# %s\n\n## The bar\n\nContent.\n' "$f" > "$d/docs/reference/work-types/$f"
  done
  cat > "$d/docs/reference/work-types/alpha/implement.md" <<'EOF'
# alpha/implement.md

## Rules

### Skills

`step`, `dep-skill`, `user-skill` — by step.

## Overlays

Apply the overlays the declared stacks provide: `overlays/<stack>.md`, its Implement section.
EOF
  cat > "$d/docs/reference/work-types/alpha/overlays/widgets.md" <<'EOF'
# alpha — the widgets overlay

## Implement

The gizmo is read first; the Widget Kit is the product-code tree. Stack files spell acme too.
EOF
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
case_run "a declared dependency is neither layered nor scanned" 0 - "true"
case_run "a review-only row needs only review.md" 0 - "true"
case_run "a single-word status name written bare is not a value" 0 - \
  "printf 'Definition of Done; the work is Done when Ready.\n' >> docs/reference/wf.md"
case_run "a project-layer file may spell profile values" 0 - \
  "printf 'PVT_projectnode and \`In progress\` are fine here.\n' >> docs/reference/profile.md"
case_run "a layer: project override takes a method-tree doc out of check 5" 0 - \
  "sed -i '1i ---\nlayer: project\n---\n' docs/reference/wf.md && printf 'Owned by acme.\n' >> docs/reference/wf.md"
case_run "a pointer in a frozen tree is not checked" 0 - \
  "mkdir -p docs/postmortems && printf 'Then \`CLAUDE.md\`'\"'\"'s **Long Gone** section said so.\n' > docs/postmortems/2020-01-01-x.md"
case_run "a stack-group dependency is neither layered nor scanned" 0 - "true"
case_run "a layer: stack override on an authored skill file is accepted" 0 - \
  "printf -- '---\nlayer: stack\n---\n\nStack notes naming acme.\n' > .claude/skills/step/widgets.md"
case_run "a pointer inside a fenced block is not checked" 0 - \
  "printf '\`\`\`\nSee \`CLAUDE.md\`'\"'\"'s **Nowhere**.\n\`\`\`\n' >> docs/reference/wf.md"
case_run "a flow deviation naming an enabled work type is accepted" 0 - \
  "printf '\n### The \`alpha\` stage runs before \`beta\`\n\nBecause.\n' >> docs/reference/profile.md"
case_run "an overlay is stack by position: it may spell tokens and profile values" 0 - \
  "printf 'gizmo, Widget Kit, acme and PVT_projectnode.\n' >> docs/reference/work-types/alpha/overlays/widgets.md"
case_run "a none marker satisfies the slot for a stack with nothing to add" 0 - \
  "printf 'none\n' > docs/reference/work-types/alpha/overlays/widgets.md"
case_run "a stack token outside the work-type tree is not this check's" 0 - \
  "printf 'A gizmo is fine in the workflow doc.\n' >> docs/reference/wf.md"
case_run "one word of a multi-word token is not the token" 0 - \
  "printf 'A Widget alone, and a Kit alone.\n' >> docs/reference/work-types/alpha/done.md"
case_run "a review-only work type needs no Skills rule and no slot" 0 - "true"
case_run "one commit-prefix row may key two labels at once" 0 - \
  "printf '# DoD\n\n## Commit message conventions\n\n| L | P | E |\n|---|---|---|\n| \`alpha\` / \`beta\` | \`x:\` | \`x: a thing\` |\n' > docs/reference/dod.md"

# --- 1  anchors, outward -------------------------------------------------------------------
case_run "1: an unresolvable pointer in a skill fails" 1 "**Nowhere**" \
  "printf 'See \`CLAUDE.md\`'\"'\"'s **Nowhere** section.\n' >> .claude/skills/step/SKILL.md"
case_run "1: an unresolvable pointer in an ADR fails" 1 "[1 anchors, outward] docs/adl/0001.md" \
  "mkdir -p docs/adl && printf 'Per \`CLAUDE.md\`'\"'\"'s **Nowhere** topic.\n' > docs/adl/0001.md"
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
case_run "2: a routing-table entry with no link fails" 1 "links to no document" \
  "sed -i 's#| \[wf.md\](docs/reference/wf.md) — the chain. |#| the chain, in wf.md |#' CLAUDE.md"
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
case_run "3: a path map entry routing to a work type that is not enabled fails" 1 "which is not enabled" \
  "sed -i 's#    - work_type: alpha#    - work_type: gamma#' .claude/profile.yml"
case_run "3: a flow deviation naming a work type that is not enabled fails" 1 "flow deviation names \`gamma\`, which is not an enabled work type" \
  "printf '\n### The \`gamma\` stage is removed\n\nBecause.\n' >> docs/reference/profile.md"
case_run "3: a flow deviation naming no work type fails" 1 "names no work type in backticks" \
  "printf '\n### Verify live is skipped\n\nBecause.\n' >> docs/reference/profile.md"
case_run "3: a profile document without a Flow section fails" 1 "has no \`## Flow\` section" \
  "sed -i '/^## Flow$/,\$d' docs/reference/profile.md"
case_run "3: no profile document at all fails" 1 "the profile document is absent" \
  "rm docs/reference/profile.md && sed -i 's#\[profile.md\](docs/reference/profile.md)#[wf.md](docs/reference/wf.md)#' CLAUDE.md"
case_run "3: an enabled context label with no commit-prefix row fails" 1 "context label \`beta\` has no commit-prefix row" \
  "sed -i '/^| \`beta\` | \`beta:\`/d' docs/reference/dod.md"
case_run "3: a Definition of Done document without the prefix section fails" 1 "no \`## Commit message conventions\` section" \
  "sed -i '/^## Commit message conventions$/,\$d' docs/reference/dod.md"
case_run "3: a commit-prefix table with no backticked key fails" 1 "has no table keyed by context label" \
  "printf '# DoD\n\n## Commit message conventions\n\n| L | P | E |\n|---|---|---|\n| alpha | x: | x: a thing |\n' > docs/reference/dod.md"

# --- 4  work-type completeness -------------------------------------------------------------
case_run "4: an enabled work type missing its bar fails" 1 "has no done.md" \
  "rm docs/reference/work-types/alpha/done.md"
case_run "4: a review-only work type missing review.md fails" 1 "has no review.md" \
  "rm docs/reference/work-types/beta/review.md"
case_run "4: a repo-installed dependency that is absent fails" 1 "declared dependency \`dep-skill\`" \
  "rm -r .claude/skills/dep-skill"
case_run "4/5: an undeclared skill defaults to method and is scanned" 1 ".claude/skills/rogue/SKILL.md:5: method file spells profile value repo.owner" \
  "mkdir .claude/skills/rogue && printf -- '---\nname: rogue\n---\n\nby acme\n' > .claude/skills/rogue/SKILL.md"
case_run "4: a skill directory without SKILL.md fails" 1 "skill directory has no SKILL.md" \
  "mkdir .claude/skills/empty && printf 'notes\n' > .claude/skills/empty/notes.md"
case_run "4/5: an authored skill's reference file is a method file too" 1 ".claude/skills/step/notes.md:1: method file spells profile value repo.owner" \
  "printf 'Owned by acme.\n' > .claude/skills/step/notes.md"
case_run "4: an unknown layer value fails" 1 "is not one of" \
  "sed -i 's/^layer: method$/layer: stak/' .claude/agents/reviewer.md"
case_run "4: an unknown layer value on a doc fails" 1 "\`layer: profile\` is not one of" \
  "sed -i '1i ---\nlayer: profile\n---\n' docs/reference/wf.md"
case_run "4: a slot without an overlay for a declared stack fails" 1 "no widgets.md for declared stack \`widgets\`" \
  "rm docs/reference/work-types/alpha/overlays/widgets.md"
case_run "4: an overlays directory under a label with no slot fails" 1 "no \`## Overlays\` slot" \
  "mkdir docs/reference/work-types/beta/overlays && printf 'none\n' > docs/reference/work-types/beta/overlays/widgets.md"
case_run "4: an overlay for an undeclared stack fails" 1 "overlay for \`gadgets\`, which is not a declared stack" \
  "printf 'none\n' > docs/reference/work-types/alpha/overlays/gadgets.md"
case_run "4: a stack a dependency declares without a stacks entry fails" 1 "declares stack \`gadgets\`, which has no \`stacks\` entry" \
  "sed -i 's/^      stack: widgets$/      stack: gadgets/' .claude/profile.yml"
case_run "4: a work file without a Skills rule fails" 1 "work file has no \`### Skills\` rule" \
  "sed -i 's/^### Skills$/### Tools/' docs/reference/work-types/alpha/implement.md"
case_run "4: a Skills rule naming a stack skill fails" 1 "names \`stack-skill\`, which is not a method skill" \
  "sed -i 's/^\`step\`, \`dep-skill\`, \`user-skill\`/\`step\`, \`stack-skill\`/' docs/reference/work-types/alpha/implement.md"
case_run "4: a Skills rule naming an unknown skill fails" 1 "names \`nowhere\`, which is not a method skill" \
  "sed -i 's/^\`step\`, \`dep-skill\`, \`user-skill\`/\`step\`, \`nowhere\`/' docs/reference/work-types/alpha/implement.md"
case_run "4: an overlays directory under a label that is not enabled fails" 1 "overlays/ under \`gamma\`, which is not an enabled work type" \
  "mkdir -p docs/reference/work-types/gamma/overlays && printf 'none\n' > docs/reference/work-types/gamma/overlays/widgets.md"
case_run "4: an overlays directory under a branch directory fails" 1 "alpha/branch/overlays/: overlays/ under a branch directory" \
  "mkdir -p docs/reference/work-types/alpha/branch/overlays && printf 'none\n' > docs/reference/work-types/alpha/branch/overlays/widgets.md"

# --- 5  no profile values in method files --------------------------------------------------
case_run "5: the owner in a method doc fails" 1 "profile value repo.owner" \
  "printf 'Owned by acme.\n' >> docs/reference/wf.md"
case_run "5: a node id in a skill fails" 1 "profile value board.fields.status.id" \
  "printf 'Edit field PVTSSF_statusfield.\n' >> .claude/skills/step/SKILL.md"
case_run "5: a backticked status name in a method file fails" 1 "profile value status \`Done\`" \
  "printf 'Move it to \`Done\`.\n' >> docs/reference/wf.md"
case_run "5: a multi-word status name written bare fails" 1 "profile value status \`In progress\`" \
  "printf 'Status -> In progress.\n' >> .claude/agents/reviewer.md"
case_run "5: a stack token in a core work-type file fails" 1 "alpha/done.md:6: core work-type file spells stack token \`gizmo\` (widgets)" \
  "printf 'Read the gizmo first.\n' >> docs/reference/work-types/alpha/done.md"
case_run "5: a stack token in any case, inside backticks, fails" 1 "stack token \`gizmo\`" \
  "printf 'Read \`GIZMO\` first.\n' >> docs/reference/work-types/alpha/done.md"
case_run "5: a multi-word stack token across a line wrap fails" 1 "alpha/done.md:6: core work-type file spells stack token \`Widget Kit\`" \
  "printf 'Use the Widget\nKit here.\n' >> docs/reference/work-types/alpha/done.md"
case_run "5: a stack skill name in a core work-type file fails" 1 "core work-type file spells stack skill \`stack-skill\`" \
  "printf 'Read \`stack-skill\` first.\n' >> docs/reference/work-types/alpha/review.md"
case_run "5: the work-type README is a core file too" 1 "work-types/README.md:1: core work-type file spells stack token" \
  "printf 'A gizmo.\n' > docs/reference/work-types/README.md"
case_run "5: a hyphen-adjacent token is still the token" 1 "alpha/done.md:6: core work-type file spells stack token \`gizmo\`" \
  "printf 'The gizmo-harness split.\n' >> docs/reference/work-types/alpha/done.md"
case_run "5: a branch file is a core method file, not an overlay" 1 "alpha/branch/done.md:1: core work-type file spells stack token \`gizmo\`" \
  "mkdir docs/reference/work-types/alpha/branch && printf 'A gizmo.\n' > docs/reference/work-types/alpha/branch/done.md"

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

EXPECTED=73
printf '\n%d passed, %d failed (of %d cases)\n' "$pass" "$fail" "$EXPECTED"
if [ $((pass + fail)) -ne "$EXPECTED" ]; then
  printf 'FAIL  only %d cases ran, expected %d — a fixture was skipped silently\n' \
    $((pass + fail)) "$EXPECTED"
  exit 1
fi
[ "$fail" -eq 0 ]
