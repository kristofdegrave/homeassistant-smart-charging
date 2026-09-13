#!/usr/bin/env bash
# Enforce the part of the authoring rule (docs/reference/ai-authoring.md) that a grep can
# decide with certainty: a skill or agent definition must not carry a MARKDOWN LINK to a
# project documentation file. It points at the CLAUDE.md section owning the topic instead.
#
# Why links and not paths. The rule separates documentation an artifact reads to learn how to
# operate (route it) from repo paths the artifact acts on (name them). Path shape does not tell
# those apart: write-adr's `docs/adl/template.md` is the template it drafts against and stays
# named, while diagnosing-bugs' [ADR-0009](../../../docs/adl/0009-...md) is a document it reads
# and must be routed. Both are concrete .md files in the same tree. What separates them is the
# link: a markdown link exists to be followed, so it IS a route; a bare path in prose is a
# name. Checked against the whole .claude/ tree, this flags every genuine route and nothing
# legal.
#
# Known false negative, stated so it is a limit rather than a surprise: a route written as a
# bare path is missed. That is judgment, and judgment belongs to the reviewer checklist, along
# with the rest of the rule a grep cannot see — a fact restated instead of routed, a route that
# should exist but does not, the project named, a project-specific resource list. See #1100.
#
# Diff-scoped on purpose. The reference converts the back-catalogue on its own track, so this
# only looks at lines a change ADDS — an untouched file that still carries a link is not this
# check's business, and a big-bang retrofit is explicitly not wanted.
#
# A PR can defeat this by editing the script, or by allowlisting its own violation. Both are
# inherent to running a checked-in script against its own PR, and both are contained by
# CODEOWNERS on .github/ and .claude/ plus the manual merge gate. A known limit, not a
# guarantee.
#
# Usage:  .github/check-authoring-rules.sh [base-ref]
#         base-ref defaults to origin/main.
#
# Exit 0 clean, 1 violations found, 2 usage/environment error.

set -euo pipefail

BASE="${1:-origin/main}"

if ! git rev-parse --verify --quiet "$BASE" >/dev/null; then
  echo "check-authoring-rules: cannot resolve base ref '$BASE'" >&2
  echo "  In CI, fetch it first; locally, try: git fetch origin" >&2
  exit 2
fi

# Paths that are subject matter rather than a route — a path the artifact exists to act on,
# which ai-authoring.md's subject-matter exception keeps named. One "<file>\t<path>" per line,
# with a comment saying why. Deliberately empty: every entry is an exception a reviewer has to
# agree with, so it should stay short enough to read.
ALLOW_FILE="${ALLOW_FILE:-.github/authoring-rule-allowlist.tsv}"

cd "$(git rev-parse --show-toplevel)" || exit 2

violations=0
current=""

# Captured to a file rather than piped from a process substitution: that form puts git's exit
# status out of reach of both errexit and pipefail, so a failed diff would read as an empty
# change and the run would report clean. A merge gate has to fail closed.
DIFF=$(mktemp)
trap 'rm -f "$DIFF"' EXIT
git -c core.quotePath=false diff --unified=0 "$BASE...HEAD" \
  -- '.claude/skills/*' '.claude/agents/*' > "$DIFF"

# --unified=0 so context lines never masquerade as additions.
#
# The current file comes from the `diff --git` header, not from `+++ b/`. In a unified diff
# every content line carries a +, - or space prefix, so a line of prose cannot forge a
# `diff --git` header — whereas a skill documenting diff syntax can contain a line starting
# `++`, which renders as `+++ b/...` and would otherwise retarget every later violation to the
# wrong file. The diff below sets core.quotePath=false so a non-ASCII path stays unquoted and
# the header keeps matching; an unmatched header would leave `current` pointing at the previous
# file, which is the mis-attribution this switch exists to prevent, so it is also guarded below.
while IFS= read -r line; do
  case "$line" in
    'diff --git a/'*)
      current="${line##* b/}"
      continue
      ;;
  esac

  case "$line" in
    '+'*) ;;
    *) continue ;;
  esac
  body="${line#+}"

  # A markdown link whose target is a project documentation file, relative or repo-rooted.
  # A bare path in prose is a name, not a route, and is deliberately not matched.
  # Match up to .md and no further, so none of the link forms that carry a tail can slip
  # past: an #anchor (the most natural routing form, and the style this repo's own docs use),
  # a "title", an <angle> wrapper, or a ./ or / prefix. Normalisation then strips the opener
  # and any leading ./ ../ / so an allowlist entry does not depend on how deep the artifact
  # sits or how the author spelled the relative path.
  matches=$(printf '%s\n' "$body" \
    | grep -oE '\]\(<?(\.*/)*docs/[A-Za-z0-9._/-]+\.md' \
    | sed -E 's/^\]\(<?//; s#^(\.*/)+##' || true)
  [ -z "$matches" ] && continue

  while IFS= read -r path; do
    [ -z "$path" ] && continue
    if [ -f "$ALLOW_FILE" ] \
       && awk -F'\t' -v a="$current" -v p="$path" '$1==a && $2==p {found=1} END{exit !found}' \
            "$ALLOW_FILE"; then
      continue
    fi

    if [ -z "$current" ]; then
      echo "check-authoring-rules: parse error — a change with no file header" >&2
      exit 2
    fi
    printf '%s: links to %s\n' "$current" "$path"
    printf '    %s\n' "$body"
    violations=$((violations + 1))
  done <<EOF
$matches
EOF
done < "$DIFF"

if [ "$violations" -gt 0 ]; then
  cat >&2 <<'MSG'

A skill or agent definition may not link to a project documentation file: a link is a route,
and routes go through CLAUDE.md. Point at the section owning the topic instead, and where no
section owns it, add the routing line to CLAUDE.md rather than the fact. The rule, its
boundaries and the subject-matter exception are in the document CLAUDE.md's "Authoring AI
artifacts" section routes to.

A path the artifact acts on rather than reads stays named — write it as a bare path, not a
link. If it genuinely has to be a link, add it to the allowlist with a reason so the exception
is reviewed:
MSG
  printf '  %s   (tab-separated: <artifact-path>\\t<named-path>)\n\n' "$ALLOW_FILE" >&2
  exit 1
fi

echo "check-authoring-rules: clean ($BASE...HEAD)"
