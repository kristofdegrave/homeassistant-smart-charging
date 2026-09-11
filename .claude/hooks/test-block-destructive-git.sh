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

# A repository whose branch has an upstream, so the rebase rule has something to see.
CWD=$(cd "$(dirname "$0")/../.." && pwd)
fail=0

run() { # run BLOCK|ALLOW <command> [cwd]
  expect=$1
  cmd=$2
  dir=${3:-$CWD}
  esc=$(printf '%s' "$cmd" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')
  out=$(printf '{"session_id":"t","cwd":"%s","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"%s","description":"t"}}' "$dir" "$esc" | sh "$HOOK" 2>&1)
  rc=$?
  case "$out" in *'"permissionDecision":"deny"'*) denied=1 ;; *) denied=0 ;; esac
  if [ "$expect" = BLOCK ]; then
    if [ "$rc" = 2 ] && [ "$denied" = 1 ]; then
      printf 'ok   BLOCK  %s\n' "$cmd"
    else
      printf 'FAIL expected BLOCK, got rc=%s deny=%s  %s\n' "$rc" "$denied" "$cmd"
      fail=1
    fi
  else
    if [ "$rc" = 0 ] && [ -z "$out" ]; then
      printf 'ok   ALLOW  %s\n' "$cmd"
    else
      printf 'FAIL expected ALLOW, got rc=%s  %s\n%s\n' "$rc" "$cmd" "$out"
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
run BLOCK 'git rebase main'
run BLOCK 'git rebase -i HEAD~3'
run BLOCK 'git fetch origin && git rebase origin/main'
run BLOCK 'echo hi; git reset --hard HEAD~1'
run BLOCK 'GIT_EDITOR=true git rebase -i HEAD~2'

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
[ "$fail" = 0 ] && echo "ALL CASES PASSED" || echo "SOME CASES FAILED"
exit $fail
