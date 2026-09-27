#!/bin/sh
# Table-driven test for block-destructive-git.sh: feeds it real PreToolUse payloads
# and asserts the deny/allow decision. Run from anywhere:
#
#   sh .claude/hooks/test-block-destructive-git.sh
#
# The two tables are the block list and the never-block list from the hook's own
# contract in docs/reference/method/contribution-workflow.md -- add a case here before
# changing a matching rule. The merge-rule cases at the end never reach GitHub: a stub
# `gh` on PATH answers `pr view` and `pr checks` from the canned facts each case sets.

HOOK=$(dirname "$0")/block-destructive-git.sh
[ -f "$HOOK" ] || { echo "cannot find $HOOK" >&2; exit 1; }

CWD=$(cd "$(dirname "$0")/../.." && pwd)
fail=0

# The stub gh: `pr view` prints $GH_VIEW, `pr checks` prints $GH_CHECKS, anything else
# nothing; GH_FAIL=1 makes every call fail the way an unauthenticated or absent gh does.
# It answers only the call the case expects -- `pr view|checks <$STUB_SEL> -R <$STUB_REPO>`,
# the number pinned to the profile's repository -- and fails on any other shape, so a
# forwarding bug (a selector dropped, a `-R` not pinned) fails its case instead of
# passing on canned facts. Nothing here is GH_-prefixed except GH_FAIL, which gh does not
# read; the hook reads the command text, not this environment.
STUB=$(mktemp -d)
trap 'rm -rf "$STUB"' EXIT
cat > "$STUB/gh" <<'EOF'
#!/bin/sh
[ "${GH_FAIL:-0}" = 1 ] && exit 1
[ "$3" = "$STUB_SEL" ] && [ "$4" = -R ] && [ "$5" = "$STUB_REPO" ] || exit 1
case "$1 $2" in
  "pr view") printf '%s\n' "$GH_VIEW" ;;
  "pr checks") printf '%s\n' "$GH_CHECKS" ;;
esac
EOF
chmod +x "$STUB/gh"
PATH="$STUB:$PATH"
export PATH GH_VIEW GH_CHECKS GH_FAIL STUB_SEL STUB_REPO
# The tool the payload names; the merge cases send one PowerShell payload.
TOOL=Bash

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
  # Tabs and newlines are escaped, not passed through raw, so the payload is the valid
  # JSON a real PreToolUse call would send.
  esc=$(printf '%s' "$cmd" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' |
    awk 'NR > 1 { printf "\\n" } { gsub(/\t/, "\\\\t"); printf "%s", $0 }')
  shown=$(printf '%s' "$cmd" | awk 'NR > 1 { printf "\\n" } { printf "%s", $0 }')
  out=$(printf '{"session_id":"t","cwd":"%s","hook_event_name":"PreToolUse","tool_name":"%s","tool_input":{"command":"%s","description":"t"}}' "$dir" "$TOOL" "$esc" | sh "$HOOK" 2>&1)
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
run ALLOW 'git restore docs/reference/method/contribution-workflow.md'
run ALLOW 'git checkout -- docs/reference/method/contribution-workflow.md'
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
# A backslash-quoted delimiter is quoted too: the body is still inert text.
run ALLOW 'cat <<\EOF
git clean -f
EOF'
# An empty body is a body: the terminator still closes it.
run ALLOW "cat <<'EOF'
EOF"
# An escaped quote must not flip the opener line's quote state.
run ALLOW "printf \"a\\\"b\" > /tmp/f; cat <<'EOF'
git clean -f
EOF"
# `<<` in an arithmetic shift is not a heredoc opener, and nothing follows it to blank.
run ALLOW 'echo $((1 << 2))'
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
# The interpreter is recognised through a path, not just as a bare name.
run BLOCK "/bin/sh <<'EOF'
git clean -f
EOF"
# `<<-` strips tabs only: a space-indented terminator does not terminate, in sh or here.
run BLOCK "cat > /tmp/doc.md <<-'EOF'
  git clean -f
  EOF"
# The single-quote arm of the opener-line quote scan.
run BLOCK "echo 'see <<\"EOF\" below'
git clean -f
EOF"
# An arithmetic shift must not open a heredoc that swallows what follows.
run BLOCK 'echo $((1 << 2))
git clean -f'
# An unquoted heredoc sharing an opener line with a quoted one keeps its own body.
run BLOCK "cat <<A <<'B'
git clean -f
A
prose
B"
# Prose that merely shows an opener is not a redirection, even when a later line
# happens to equal the delimiter.
run BLOCK "echo \"see <<'EOF' below\"
git clean -f
EOF"
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
echo "=== the merge rule: gh pr merge only under every auto-merge condition ==="
# A stub profile, so the cases do not depend on the real profile's tree list; the last
# case runs on the real profile. One tree is listed without its trailing slash on purpose:
# the hook normalises it, so `tests/test_x.py` still sits under `tests`.
printf 'repo:\n  owner: o\n  name: r\nautopilot:\n  auto_merge_trees:\n    - custom_components/\n    - tests\n    - docs/design/\n  lanes: 2\n' > "$STUB/profile.yml"
PROFILE=$STUB/profile.yml
export PROFILE
STUB_SEL=1234
STUB_REPO=o/r
# Facts under which the merge passes; each blocked case below breaks exactly one. The
# head, count and labels come before the files, in the order the hook's template asks.
GOOD_VIEW='cross=false
head=abc123
count=3
label=development
label=needs-approval
file=custom_components/smart_charging/coordinator.py
file=tests/test_coordinator.py
file=docs/design/system-design.md'
GOOD_CHECKS='check=pass lint
check=pass test
check=skipping perf
check=pass method'
GH_VIEW=$GOOD_VIEW
GH_CHECKS=$GOOD_CHECKS
GH_FAIL=0
run ALLOW 'gh pr merge 1234 --squash --admin --match-head-commit abc123'
run ALLOW 'gh pr merge --squash --delete-branch --match-head-commit=abc123 1234'
run ALLOW 'gh pr merge -sd --match-head-commit abc123 1234'
run ALLOW 'gh pr merge 1234 -R o/r --squash --match-head-commit abc123'          # the profile's repository
run ALLOW 'gh pr merge 1234 --repo=o/r --squash --match-head-commit abc123'
run ALLOW 'gh pr merge 1234 -R github.com/o/r --squash --match-head-commit abc123'
run ALLOW 'gh pr -R o/r merge 1234 --squash --match-head-commit abc123'          # -R before the subcommand
run ALLOW 'gh pr --repo=o/r merge 1234 --squash --match-head-commit abc123'
run ALLOW 'gh pr merge https://github.com/o/r/pull/1234 --squash --match-head-commit abc123'  # a URL: the guard reads by number
run ALLOW 'gh pr merge --squash --admin --body-file /tmp/msg.md --match-head-commit abc123 1234'
run ALLOW 'gh pr merge 1234 -bfixes --squash --match-head-commit abc123'         # -b takes "fixes": its s is no squash, but --squash is
run ALLOW 'gh pr merge 1234 --disable-auto'   # merges nothing
run ALLOW 'gh pr merge --help'
run ALLOW 'gh pr view 1234 --json labels'
run ALLOW 'gh pr comment 1234 --body "run gh pr merge --squash once it is green"'
run ALLOW 'gh api repos/o/r/pulls/1234/comments -f body=x'   # an api call that merges nothing
run ALLOW 'echo "gh pr merge is guarded"'                     # prose behind a non-interpreter
TOOL=PowerShell
run ALLOW '& gh pr merge 1234 --squash --admin --match-head-commit abc123'  # PowerShell's call operator
run BLOCK '& gh pr merge 1234 --admin'                                       # ... and the rule still bites behind it
TOOL=Bash
run BLOCK 'gh pr merge 1234 --admin --match-head-commit abc123'          # not a squash
run BLOCK 'gh pr merge 1234 --merge --match-head-commit abc123'
run BLOCK 'gh pr merge 1234 --rebase --admin --match-head-commit abc123'
run BLOCK 'gh pr merge 1234 -m --match-head-commit abc123'
run BLOCK 'gh pr merge 1234 -rd --match-head-commit abc123'
run BLOCK 'gh pr merge 1234 -Afoo@users.noreply.github.com --match-head-commit abc123'  # the s in a value is no squash
run BLOCK 'gh pr merge 1234 --merge -Afoo@users.noreply.github.com --match-head-commit abc123'
run BLOCK 'gh pr merge -bs 1234 --match-head-commit abc123'               # -b takes "s" as its value
run BLOCK 'echo hi; gh pr merge 1234'          # a separator starts a segment of its own
# Which pull request: exactly one selector, by number or URL, on the profile's repository.
run BLOCK 'gh pr merge --squash --admin --match-head-commit abc123'      # no selector
run BLOCK 'cd ../other-worktree && gh pr merge --squash --admin'         # no selector: gh would read that checkout's PR
run BLOCK 'gh pr merge --squash #1234 --match-head-commit abc123'        # a shell comment, not a selector
run BLOCK 'gh pr merge --squash some-branch --match-head-commit abc123'  # a branch is not pinnable
run BLOCK 'gh pr merge 1234 1235 --squash --match-head-commit abc123'    # two selectors
run BLOCK 'gh pr merge https://github.com/other/repo/pull/1234 --squash --match-head-commit abc123'
run BLOCK 'gh pr merge 1234 -R other/repo --squash --match-head-commit abc123'
run BLOCK 'gh pr merge 1234 --repo=other/repo --squash --match-head-commit abc123'
run BLOCK 'gh pr -R other/repo merge 1234 --squash --match-head-commit abc123'
run BLOCK 'gh pr -R o/r merge 1234 --admin --match-head-commit abc123'   # -R walked past, then the squash rule bites
run BLOCK 'gh pr merge 1234 -Ro/r --admin --match-head-commit abc123'
run BLOCK 'GH_REPO=o/r gh pr merge 1234 --squash --match-head-commit abc123'   # a GH_* assignment, even to the same repo
run BLOCK 'GH_HOST=ghe.example gh pr merge 1234 --squash --match-head-commit abc123'
run BLOCK 'echo 1234 | xargs gh pr merge --squash --match-head-commit abc123'  # a wrapper
run BLOCK 'sudo gh pr merge 1234 --squash --match-head-commit abc123'
run BLOCK 'sh -c "gh pr merge 1234 --squash --admin --match-head-commit abc123"'   # an interpreter
run BLOCK "bash -c 'gh pr -R o/r merge 1234 --squash'"
run BLOCK 'pwsh -c "& gh pr merge 1234 --squash"'
# A merge under another name.
run BLOCK 'gh api -X PUT repos/o/r/pulls/1234/merge -f merge_method=squash'
run BLOCK 'gh api graphql -f query="mutation { mergePullRequest(input: {pullRequestId: \"x\"}) { clientMutationId } }"'
# The head pin.
run BLOCK 'gh pr merge 1234 --squash --admin'                            # not pinned to the head the guard read
run BLOCK 'gh pr merge 1234 --squash --match-head-commit def456'          # pinned to a stale head
GH_VIEW='cross=true
head=abc123
count=1
label=needs-approval
file=tests/test_x.py'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # the head is a fork's branch
GH_VIEW='cross=false
head=abc123
count=1
label=development
file=tests/test_x.py'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # no needs-approval
GH_VIEW='cross=false
head=abc123
count=1
label=needs-approval
label=needs-decision
file=tests/test_x.py'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # needs-decision alongside
GH_VIEW='cross=false
head=abc123
count=2
label=needs-approval
file=tests/test_x.py
file=docs/analysis/requirements.md'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a file outside the auto-merge trees
GH_VIEW='cross=false
head=abc123
count=2
label=needs-approval
file=tests/test_x.py
file=CLAUDE.md'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a rules file at the root
GH_VIEW='cross=false
head=abc123
count=1
label=needs-approval
file=tests_extra/test_x.py'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a prefix match must not straddle a directory name
GH_VIEW='cross=false
head=abc123
count=101
label=needs-approval
file=tests/test_x.py'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # gh listed fewer files than the PR has
GH_VIEW='cross=false
head=abc123
count=0
label=needs-approval'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # no files at all
# A file name is the one fact a contributor chooses: one carrying a line break would forge
# a fact line, so it is refused, as is a control character in a name.
GH_VIEW='cross=false
head=abc123
count=1
label=development
file=tests/x
label=needs-approval'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a forged label after the files began
GH_VIEW='cross=false
head=abc123
count=2
label=needs-approval
file=tests/x
count=1'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a forged count: the first count stands, and the line is refused
GH_VIEW="cross=false
head=abc123
count=1
label=needs-approval
file=tests/x${tab}y"
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a control character in a name
GH_VIEW='cross=false
count=1
label=needs-approval
file=tests/test_x.py'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # no head to pin to
GH_VIEW=$GOOD_VIEW
GH_CHECKS='check=pass lint
check=fail test'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a red check
GH_CHECKS='check=pass lint
check=pending test'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a check still running
GH_CHECKS='check=cancel lint
check=pass test'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a cancelled check
GH_CHECKS=''
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # no checks reported
GH_CHECKS='not what gh prints'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # an unreadable checks answer
GH_CHECKS=$GOOD_CHECKS
GH_FAIL=1
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # gh itself fails: closed, not open
GH_FAIL=0
GH_VIEW=''
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # gh answers nothing
GH_VIEW=$GOOD_VIEW
printf 'repo:\n  owner: o\n  name: r\nautopilot:\n  lanes: 2\n' > "$STUB/profile.yml"
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a profile with no trees
printf 'autopilot:\n  auto_merge_trees:\n    - tests/\n' > "$STUB/profile.yml"
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a profile with no repo to pin to
unset PROFILE
STUB_REPO=kristofdegrave/homeassistant-smart-charging
run ALLOW 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # and the real profile still passes

echo
[ "$fail" = 0 ] && echo "ALL CASES PASSED" || echo "SOME CASES FAILED"
exit $fail
