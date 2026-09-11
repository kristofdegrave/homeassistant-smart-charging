#!/bin/sh
# Table-driven test for block-destructive-git.sh: feeds it real PreToolUse payloads
# and asserts the deny/allow decision. Run from anywhere:
#
#   sh .claude/hooks/test-block-destructive-git.sh
#
# The two tables are the block list and the never-block list from the hook's own
# contract in docs/reference/contribution-workflow.md -- add a case here before
# changing a matching rule.

HOOK=$(dirname "$0")/block-destructive-git.sh
[ -f "$HOOK" ] || { echo "cannot find $HOOK" >&2; exit 1; }

CWD=$(cd "$(dirname "$0")/../.." && pwd)
fail=0

# The rebase rule keys off "the checked-out branch has an upstream", so state plainly
# when the checkout cannot exercise it instead of failing four cases obscurely.
if git -C "$CWD" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' >/dev/null 2>&1; then
  rebase_testable=1
else
  rebase_testable=0
  echo "note: the branch checked out in $CWD has no upstream, so the rebase cases are skipped"
fi

run() { # run BLOCK|ALLOW <command> [cwd]
  expect=$1
  cmd=$2
  dir=${3:-$CWD}
  # A case may span lines (heredocs, newline-separated statements), so escape the
  # newlines the way JSON wants and render the case on one line in the report.
  esc=$(printf '%s' "$cmd" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' |
    awk 'NR > 1 { printf "\\n" } { printf "%s", $0 }')
  shown=$(printf '%s' "$cmd" | awk 'NR > 1 { printf "\\n" } { printf "%s", $0 }')
  out=$(printf '{"session_id":"t","cwd":"%s","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"%s","description":"t"}}' "$dir" "$esc" | sh "$HOOK" 2>&1)
  rc=$?
  case "$out" in *'"permissionDecision":"deny"'*) denied=1 ;; *) denied=0 ;; esac
  if [ "$expect" = BLOCK ]; then
    if [ "$rc" = 2 ] && [ "$denied" = 1 ]; then
      printf 'ok   BLOCK  %s\n' "$shown"
    else
      printf 'FAIL expected BLOCK, got rc=%s deny=%s  %s\n' "$rc" "$denied" "$shown"
      fail=1
    fi
  else
    if [ "$rc" = 0 ] && [ -z "$out" ]; then
      printf 'ok   ALLOW  %s\n' "$shown"
    else
      printf 'FAIL expected ALLOW, got rc=%s  %s\n%s\n' "$rc" "$shown" "$out"
      fail=1
    fi
  fi
}

echo "=== blocked: outside the standing authorization ==="
run BLOCK 'git push --force'
run BLOCK 'git push -f origin main'
run BLOCK 'git push --force-with-lease origin main'
run BLOCK 'git push --force-with-lease=main:abc123 origin'
run BLOCK 'git push --force-if-includes origin main'
run BLOCK 'git push --force-w origin main'
run BLOCK 'git push --mirror origin'
run BLOCK 'git push origin +main:main'
run BLOCK 'git push origin +main'
run BLOCK 'git push origin +HEAD'
run BLOCK 'git -C /some/worktree push --force'
run BLOCK 'git reset --hard'
run BLOCK 'git reset --hard origin/main'
run BLOCK 'git reset --har HEAD~1'
run BLOCK 'git clean -f'
run BLOCK 'git clean -fd'
run BLOCK 'git clean -ffdx'
run BLOCK 'git clean --force'
run BLOCK 'git clean --forc'
run BLOCK 'git branch -D some-branch'
run BLOCK 'git branch --delete --force some-branch'
run BLOCK 'git checkout -- .'
run BLOCK 'git checkout .'
run BLOCK 'git restore .'
run BLOCK 'git restore --staged --worktree .'
run BLOCK 'git restore -- :/'
run BLOCK 'git stash drop'
run BLOCK 'git stash clear'
run BLOCK 'git branch -df some-branch'
run BLOCK 'git branch -d --force some-branch'
run BLOCK 'git branch --delete -f some-branch'
run BLOCK 'git restore --staged --work .'
run BLOCK 'sudo -u someone git push --force'
run BLOCK 'nice -n 10 git clean -fd'
run BLOCK 'echo hi; git reset --hard HEAD~1'
run BLOCK 'gh pr comment 1 --body "x; git reset --hard is banned"'  # separator wins: fails safe
if [ "$rebase_testable" = 1 ]; then
  run BLOCK 'git rebase main'
  run BLOCK 'git rebase -i HEAD~3'
  run BLOCK 'git fetch origin && git rebase origin/main'
  run BLOCK 'GIT_EDITOR=true git rebase -i HEAD~2'
fi

echo
echo "=== allowed: the standing authorization must not be narrowed ==="
run ALLOW 'git push'
run ALLOW 'git push origin main'
run ALLOW 'git push -u origin some-branch'
run ALLOW 'git push --set-upstream origin some-branch'
run ALLOW 'git push --follow-tags'
run ALLOW 'git commit -m "workflow: add the guard hook"'
run ALLOW 'git commit --amend --no-edit'
run ALLOW 'git fetch origin'
run ALLOW 'git pull --ff-only'
run ALLOW 'git merge origin/main'
run ALLOW 'git worktree add /tmp/wt -b some-branch origin/main'
run ALLOW 'git worktree remove /tmp/wt'
run ALLOW 'git branch some-branch'
run ALLOW 'git branch -d merged-branch'
run ALLOW 'git checkout -b some-branch origin/main'
run ALLOW 'git switch -c some-branch'
run ALLOW 'git status'
run ALLOW 'git log --oneline -5'
run ALLOW 'git diff --stat'
run ALLOW 'git add .'
run ALLOW 'git clean -n'
run ALLOW 'git restore --staged .'
run ALLOW 'git restore docs/reference/contribution-workflow.md'
run ALLOW 'git checkout -- docs/reference/contribution-workflow.md'
run ALLOW 'git stash'
run ALLOW 'git stash pop'
run ALLOW 'git stash list'
run ALLOW 'git rebase --abort'
run ALLOW 'git rebase --continue'
run ALLOW 'git rebase --autostash --continue'
run ALLOW 'git restore --stage .'
run ALLOW 'sudo -u someone git status'
run ALLOW 'gh pr create --base main --title x'
run ALLOW 'ruff check .'
run ALLOW 'rm -rf build'

echo
echo "=== allowed: text that merely mentions a blocked command ==="
run ALLOW 'echo "git push --force is blocked"'
run ALLOW 'git commit -m "fix: stop using git reset --hard"'
run ALLOW 'gh pr comment 1 --body "we never run git reset --hard here"'
run ALLOW 'grep -rn "git push --force" docs/'
run ALLOW 'git add . && git commit -m wip && git push'

echo
echo "=== allowed: inert heredoc bodies that merely document a blocked command ==="
run ALLOW "cat > /tmp/doc.md <<'EOF'
Never run this:
git clean -f
EOF"
run ALLOW 'cat > /tmp/doc.md <<"EOF"
git push --force
EOF'
# `<<-` strips leading tabs from body and terminator alike, so this one uses real tabs.
tab=$(printf '\t')
run ALLOW "cat > /tmp/doc.md <<-'EOF'
${tab}git reset --hard
${tab}EOF"
# Several heredocs opened on one line are terminated in the order they were opened.
run ALLOW "cat <<'A' <<'B'
git clean -f
A
git push --force
B"
# Real commands after a terminated heredoc are still scanned -- these are allowed ones.
run ALLOW "cat > /tmp/doc.md <<'EOF'
git push --force
EOF
git add . && git commit -m 'docs: warn about force-pushing'"

echo
echo "=== still blocked: a real invocation after a newline, separator or heredoc ==="
run BLOCK 'git add .
git clean -f'
run BLOCK 'true && git clean -f'
# An unquoted delimiter leaves $(...) live inside the body, so the body is still scanned.
run BLOCK 'cat > /tmp/doc.md <<EOF
git clean -f
EOF'
# The opener line itself is a real command position.
run BLOCK "cat > /tmp/doc.md <<'EOF' && git clean -f
prose
EOF"
run BLOCK "cat > /tmp/doc.md <<'EOF'
prose
EOF
git reset --hard"
# A heredoc opener that is never terminated is prose, not a heredoc: blank nothing.
run BLOCK "echo \"see <<'EOF' below\"
git clean -f"
# A body handed to an interpreter is code however it is quoted.
run BLOCK "sh <<'EOF'
git clean -f
EOF"
run BLOCK "cat <<'EOF' | bash
git clean -f
EOF"
run BLOCK "ssh host <<'EOF'
git clean -f
EOF"
# A backslash-quoted delimiter is quoted in sh but not recognised here: fails closed.
run BLOCK 'cat <<\EOF
git clean -f
EOF'
# A herestring is not a heredoc opener, so the next line is still a command position.
run BLOCK 'grep -q x <<<"payload"
git clean -f'
# Trailing whitespace means the line is not a terminator -- in sh either.
run BLOCK "cat <<'EOF'
git clean -f
EOF "
# A real invocation sitting between two heredocs.
run BLOCK "cat <<'A'
prose
A
git clean -f
cat <<'B'
prose
B"

echo
[ "$fail" = 0 ] && echo "ALL CASES PASSED" || echo "SOME CASES FAILED"
exit $fail
