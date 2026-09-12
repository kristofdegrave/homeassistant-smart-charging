#!/usr/bin/env bash
# Enforce the authoring rule from docs/reference/ai-authoring.md that a grep can decide:
#
#   A skill or agent definition never names a docs/** path directly; it points at the
#   CLAUDE.md section owning the topic, which routes onward.
#
# Diff-scoped on purpose. That reference converts the back-catalogue on its own track, so this
# only looks at lines a change ADDS — an untouched file that still names a path is not this
# check's business, and a big-bang retrofit is explicitly not wanted.
#
# What it cannot decide is the other half of the same rule: a fact restated instead of routed,
# and a route that should exist but does not. Both are judgment calls and belong to the
# reviewer checklist; see the epic this script was written for.
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

violations=0
current=""

# --unified=0 so context lines never masquerade as additions.
while IFS= read -r line; do
  case "$line" in
    '+++ b/'*)
      current="${line#+++ b/}"
      continue
      ;;
    '+++'*|'---'*|'+'*' '*) ;;
  esac

  case "$line" in
    '+'*) ;;
    *) continue ;;
  esac
  [ "$line" = "+++" ] && continue

  body="${line#+}"

  # A concrete documentation file: docs/<something>.md. A glob (docs/adl/**) names a tree the
  # artifact acts on, not a document it reads, so it is never matched here — and a pattern
  # that does contain a wildcard is skipped explicitly below in case one ever ends in .md.
  matches=$(printf '%s\n' "$body" | grep -oE 'docs/[A-Za-z0-9._/-]+\.md' || true)
  [ -z "$matches" ] && continue

  while IFS= read -r path; do
    [ -z "$path" ] && continue
    case "$path" in *'*'*) continue ;; esac

    if [ -f "$ALLOW_FILE" ] && grep -qF "$(printf '%s\t%s' "$current" "$path")" "$ALLOW_FILE"; then
      continue
    fi

    printf '%s: names %s\n' "$current" "$path"
    printf '    %s\n' "$body"
    violations=$((violations + 1))
  done <<EOF
$matches
EOF
done < <(git diff --unified=0 "$BASE...HEAD" -- '.claude/skills/*' '.claude/agents/*')

if [ "$violations" -gt 0 ]; then
  cat >&2 <<'MSG'

A skill or agent definition may not name a docs/** path. Point at the CLAUDE.md section that
owns the topic instead, and where no section owns it, add the routing line to CLAUDE.md rather
than the fact. The full rule, its four boundaries, and the subject-matter exception are in
CLAUDE.md's "Authoring AI artifacts" section.

If the path really is subject matter — something the artifact acts on rather than reads to
learn how to operate — add it to the allowlist with a reason, so the exception is reviewed:
MSG
  printf '  %s   (tab-separated: <artifact-path>\\t<named-path>)\n\n' "$ALLOW_FILE" >&2
  exit 1
fi

echo "check-authoring-rules: clean ($BASE...HEAD)"
