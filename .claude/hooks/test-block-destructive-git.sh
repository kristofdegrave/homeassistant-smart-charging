#!/bin/sh
# Table-driven test for block-destructive-git.sh: feeds it real PreToolUse payloads
# and asserts the deny/allow decision. Run from anywhere:
#
#   sh .claude/hooks/test-block-destructive-git.sh
#
# The two tables are the block list and the never-block list from the hook's own
# contract in docs/reference/method/contribution-workflow.md -- add a case here before
# changing a matching rule. The merge-rule cases never reach GitHub: a stub `gh` on PATH
# answers `pr view` and `pr checks` from the canned facts each case sets. The approval-rule
# cases close the file.

HOOK=$(dirname "$0")/block-destructive-git.sh
[ -f "$HOOK" ] || { echo "cannot find $HOOK" >&2; exit 1; }

CWD=$(cd "$(dirname "$0")/../.." && pwd)
fail=0

# The stub gh: `pr view` prints $GH_VIEW, `pr checks` prints $GH_CHECKS, anything else
# nothing; GH_FAIL=1 makes every call fail the way an unauthenticated or absent gh does.
# It answers only the call the case expects -- `pr view|checks <$STUB_SEL> -R <$STUB_REPO>`,
# the number pinned to the profile's repository -- and fails on any other shape, so a
# forwarding bug (a selector dropped, a `-R` not pinned) fails its case instead of
# passing on canned facts. GH_VIEW, GH_CHECKS and GH_FAIL are the stub's own, and gh reads
# none of them; the hook reads the command text, not this environment.
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

# runr <reason substring> <command> [cwd]: a BLOCK that must be refused for that reason, so a
# neighbouring rule cannot pass it.
runr() {
  want=$1
  shift
  run BLOCK "$@"
  case "$out" in
    *"$want"*) ;;
    *) printf 'FAIL refused, but not for "%s"  %s\n%s\n' "$want" "$1" "$out"; fail=1 ;;
  esac
}

run() { # run BLOCK|ALLOW <command> [cwd]
  expect=$1
  cmd=$2
  dir=${3:-$CWD}
  # A case may span lines (heredocs, newline-separated statements), so escape the
  # newlines the way JSON wants and render the case on one line in the report.
  # Tabs and newlines are escaped, not passed through raw, so the payload is the valid
  # JSON a real PreToolUse call would send.
  esc=$(printf '%s' "$cmd" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' |
    awk 'NR > 1 { printf "\\n" } { gsub(/\t/, "\\t"); printf "%s", $0 }')
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
runr "refused rather than read" '2>/dev/null git push --force origin x' # a redirection before git: refused, not read
runr "refused rather than read" '>/dev/null git reset --hard'
runr "refused rather than read" '(2>/dev/null git reset --hard)'  # ... glued to an opener
runr "refused rather than read" 'git>/dev/null reset --hard'    # ... attached to git
runr "refused rather than read" 'git >/dev/null reset --hard'   # ... between git and its subcommand
runr "refused rather than read" 'git 2> /dev/null reset --hard'
runr "refused rather than read" 'git 2>&1> /dev/null reset --hard'
runr "refused rather than read" 'git push>/dev/null --force origin x' # ... attached to the subcommand
runr "refused rather than read" '2>/dev/null gh pr merge 1234'    # the same for gh
runr "refused rather than read" 'gh>/dev/null pr merge 1234'
runr "refused rather than read" 'gh 2>/dev/null pr merge 1234'   # ... in its command path
runr "refused rather than read" 'gh pr merge>/dev/null 1234'
runr "refused rather than read" 'gh >/dev/null pr review 1 --approve'
run BLOCK '> >(sh) echo gh pr merge 1234 --squash'              # a redirection into a process substitution is not stepped over
run BLOCK '> >(sh) echo gh pr review 1 --approve'
run BLOCK 'diff <(gh pr merge 1234) /dev/null'                  # a substitution opening onto gh is still read as gh
run BLOCK 'echo x \>|gh pr merge 1234'                           # an escaped > before a real pipe
TOOL=PowerShell
runr "refused rather than read" 'git *>$null reset --hard'      # PowerShell's all-streams redirection
TOOL=Bash
runr "could not read past" '{fd}>/tmp/o git push --force origin x' # a redirection the walk cannot step over
runr "could not read past" '2> >(cat) git reset --hard'          # ... into a process substitution
runr "refused rather than read" 'git --namespace >/dev/null reset --hard' # an option's value counts
runr "refused rather than read" 'git -C >/dev/null reset --hard'
runr "refused rather than read" 'gh -R o/r pr >/dev/null merge 1234' # a flag's value is no gh path word
runr "refused rather than read" '"git">/dev/null reset --hard'   # a quoted name with one attached
runr "refused rather than read" '<<EOF git push --force origin x
EOF'                                                              # a heredoc opener before git
runr "refused rather than read" 'sudo 2>/dev/null git push --force origin x' # ... after a wrapper
runr "refused rather than read" 'GIT_X=1 2>/dev/null git push --force origin x' # ... after an assignment
runr "refused rather than read" "gh \"pr\">\"x\" merge 1234"     # two quoted parts with a redirection between
runr "refused rather than read" "gh pr 'merge'>'x' 1234"
runr "refused rather than read" "gh \"pr\">\"x\" review 1 --approve"
runr "could not read past" 'A=v> /dev/null git reset --hard'     # an assignment carrying one, its target a word
runr "could not read past" '2> "a b" git reset --hard'            # a target holding a quoted blank
runr "could not read past" '2>/dev/null echo use git'             # prose after a redirection: the stated cost
runr "refused rather than read" '>|/tmp/o git push --force origin x' # >| before git, read as > by the plain split
runr "refused rather than read" "gh \"-R\" o/r pr >/dev/null merge 1234" # a quoted flag is no path word
runr "refused rather than read" 'gh pr merge>/dev/null'           # one attached to the last path word
runr "refused rather than read" 'git push>/dev/null'              # ... and to git's subcommand
runr "could not read past" '2>/dev/null cat <(git push --force origin x)' # git glued inside a process substitution
runr "refused rather than read" 'git > -C reset --hard'            # a spaced target is no option value
runr "refused rather than read" 'git 2> --namespace reset --hard'
runr "refused rather than read" 'gh > -- pr merge 1234'            # ... nor gh's end of options
runr "refused rather than read" 'gh > -- pr review 1 --approve'
runr "refused rather than read" 'git > a\ -C reset --hard'          # a target continued through an escaped blank
runr "refused rather than read" 'git >a\ --namespace reset --hard'  # ... attached
runr "refused rather than read" "git > 'a -C' reset --hard"          # ... through a quoted blank
runr "refused rather than read" 'gh > a\ -- pr merge 1234'           # ... and for gh
runr "refused rather than read" "gh >'a --repo' pr merge 1234"
runr "refused rather than read" 'gh > a\ -- pr review 1 --approve'
run ALLOW 'command -v git > /dev/null 2>&1'                        # the spaced spellings run too
run ALLOW 'git --version > /dev/null'
run ALLOW 'command -v gh > /dev/null'
run ALLOW 'command -v git >/dev/null 2>&1'                         # no subcommand: nothing to guard
run ALLOW 'command -v gh >/dev/null'
run ALLOW 'git --version 2>&1'
run ALLOW 'gh --version >/dev/null'
run ALLOW 'git status >| /tmp/o'                                   # >| after the subcommand
run ALLOW 'git log --format=%h >/tmp/o'                           # no false refusal on common shapes
run ALLOW 'diff <(git show a:f) <(git show b:f)'
run ALLOW "gh api repos/o/r/pulls --jq 'map(select(.n > 5))'"
run ALLOW 'git commit -m "a>b"'
run ALLOW "gh api 'repos/o/r/pulls'"                              # a word that is one quoted part
run ALLOW 'git status >/dev/null 2>&1'                           # a redirection after the subcommand is untouched
run ALLOW "gh api 'repos/o/r/issues?x>1' --jq length"            # a > in a word quoted whole is no redirection
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
# The unstage exemption trusts the word --staged only where it is the shell's own word.
runr "whole working tree" 'git restore "a --staged" .'          # a piece of a quoted pathspec
runr "whole working tree" 'git restore . > out\ --staged'       # a target continued through an escaped blank
runr "whole working tree" 'git restore . <> --staged'           # a redirection's target
runr "whole working tree" 'git restore --staged . 2>/dev/null'  # any redirection drops it (conceded)
runr "whole working tree" 'git restore . # --staged'            # a comment
runr "whole working tree" 'git restore --source $empty --staged .'  # an expansion: --source may take --staged
TOOL=PowerShell
runr "whole working tree" 'git restore “a --staged ” .'         # typographic quotes
TOOL=Bash
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
cr=$(printf '\r')
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
# Every interpreter is_interp knows, not only a shell, runs a heredoc's body.
run BLOCK "python3 - <<'EOF'
import os
os.system('gh pr merge 1234 --squash --admin')
EOF"
run BLOCK "cat <<'EOF' | node
require('child_process').execSync('gh pr merge 1234 --admin')
EOF"
run ALLOW "python3 - <<'EOF'
print(1)
EOF"
run ALLOW "cat <<'EOF' > /tmp/msg.txt
docs: never gh pr merge 1234 --admin by hand
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
# head, count and labels come before the files, in the order the hook's template asks,
# and each file line carries its change type before its path.
GOOD_VIEW='cross=false
head=abc123
count=3
listed=3
label=development
label=needs-approval
file=MODIFIED custom_components/smart_charging/coordinator.py
file=ADDED tests/test_coordinator.py
file=DELETED docs/design/system-design.md'
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
run ALLOW 'gh pr merge 1234 --repo o/r --squash --match-head-commit abc123'      # --repo's value is no selector
run ALLOW 'gh pr merge 1234 -Ro/r --squash --match-head-commit abc123'           # -R's value: its r is no rebase
run ALLOW 'gh pr merge 1234 -Afoo@users.noreply.github.com --squash --match-head-commit abc123'  # -A's value: its r is no rebase
run ALLOW 'gh pr merge 1234 --squash -t fixup -F /tmp/body.md --match-head-commit abc123'  # -t/-F values are no selectors
run ALLOW 'gh pr merge 1234 --squash -tmerged -Fmsg.md --match-head-commit abc123'  # ... nor flags inside a cluster
run ALLOW 'gh pr merge https://github.com/o/r/pull/1234 --squash --match-head-commit abc123'  # a URL: the guard reads by number
run ALLOW 'gh pr merge --squash --admin --body-file /tmp/msg.md --match-head-commit abc123 1234'
run ALLOW 'gh pr merge 1234 -bfixes --squash --match-head-commit abc123'         # -b takes "fixes": its s is no squash, but --squash is
run ALLOW 'gh pr merge 1234 --disable-auto'   # merges nothing
run ALLOW 'gh pr merge --help'
run ALLOW 'gh pr view 1234 --json labels'
run ALLOW 'gh pr comment 1234 --body "run gh pr merge --squash once it is green"'
run ALLOW 'gh api repos/o/r/pulls/1234/comments -f body=x'   # an api call that merges nothing
run ALLOW 'echo "gh pr merge is guarded"'                     # prose behind a non-interpreter
run ALLOW 'echo "gh pr merge 1234"'
run ALLOW 'git commit -m "gh pr merge notes"'                 # git's own rules read it, not the merge rule
run ALLOW 'gh pr merge 1234 --squash=true --match-head-commit abc123'
run ALLOW 'gh pr merge 1234 -s=true --match-head-commit abc123'
run ALLOW 'gh pr merge 1234 --squash --match-head-commit abc123 2>&1'   # a redirection is no selector
run ALLOW 'gh pr merge 1234 --squash --match-head-commit abc123 > /tmp/out.txt'
run ALLOW 'if gh pr merge 1234 --squash --match-head-commit abc123; then echo merged; fi'  # a reserved word is stepped over
run ALLOW '"gh" "pr" "merge" 1234 --squash --match-head-commit abc123'  # quotes are not part of the words
TOOL=PowerShell
run ALLOW '& gh pr merge 1234 --squash --admin --match-head-commit abc123'  # PowerShell's call operator
run ALLOW 'gh pr merge 1234 --squash --match-head-commit abc123 2>$null'
run BLOCK '& gh pr merge 1234 --admin'                                       # ... and the rule still bites behind it
run BLOCK '& git push --force'                                               # ... as do the git rules
run BLOCK 'iex "gh pr merge 1234 --squash --admin"'                          # PowerShell's interpreters
run BLOCK 'Invoke-Expression "gh pr merge 1234 --squash --admin"'
run BLOCK 'IEX "gh pr merge 1234 --squash --match-head-commit abc123"'       # in any case
run BLOCK "echo 'gh pr merge 1234 --admin' | iex"                            # prose piped into one
run BLOCK 'gh pr `
merge 1234 --merge --admin'                                                  # a backtick continuation
run BLOCK '$r = gh pr merge 1234 --squash --match-head-commit abc123'        # an assignment's command
run BLOCK '& "C:\Program Files\GitHub CLI\gh.exe" pr merge 1234 --squash --match-head-commit abc123'  # a quoted full path
TOOL=Bash
# Wrapped merges fail closed: words naming a merge behind anything but gh or prose.
run BLOCK 'timeout 60 gh pr merge 1234 --squash --match-head-commit abc123'
run BLOCK 'timeout 60 git push --force'                                     # timeout is a wrapper for the git rules too
run BLOCK 'if gh pr merge 1234 --admin; then echo merged; fi'
run BLOCK '! gh pr merge 1234 --admin'
run BLOCK '{ gh pr merge 1234 --admin; }'
run BLOCK 'r="$(gh pr merge 1234 --squash --match-head-commit abc123)"'
run BLOCK '"gh" pr merge 1234 --admin'
run BLOCK 'gh "pr" "merge" 1234 --admin'                  # gh's own words lose their quotes too
run BLOCK '\gh pr merge 1234 --admin'
run BLOCK "python -c \"__import__('os').system('gh pr merge 1234 --squash --match-head-commit abc123')\""
run BLOCK "node -e \"require('child_process').execSync('gh pr merge 1234 --squash --match-head-commit abc123')\""
run BLOCK 'echo "$(gh pr merge 1234 --squash --match-head-commit abc123)"'    # prose running a substitution
run BLOCK 'echo hi & gh pr merge 1234 --squash --match-head-commit abc123'    # a background & starts another command
run BLOCK 'GH_REPO=$(cat repo.txt) gh pr merge 1234 --squash --match-head-commit abc123'
run BLOCK 'echo `gh pr merge 1234 --squash --match-head-commit abc123`'        # a backtick substitution
run BLOCK "env SH -c 'git status' 'gh pr merge 1234 --admin'"    # SH behind a wrapper is an interpreter, not walked past to git
run ALLOW 'ECHO "gh pr merge 1234"'                                           # ... and prose in any case
# Prose piped on, through any prose, into anything but prose may be run.
run BLOCK 'echo "gh pr merge 1234 --merge --admin" | sh'
run BLOCK "printf 'gh pr merge 1234 --admin' | bash"
run BLOCK 'echo "gh pr merge 1234 --admin" | cat | sh'
run BLOCK 'echo "gh pr merge 1234 --admin" |
sh'
run ALLOW 'echo "gh pr merge 1234" | grep merge'
run ALLOW "rg -n 'gh pr merge' | wc -l"                                      # a read-only consumer runs nothing
run BLOCK "rg -n 'gh pr merge' | wc -l | sh"                                 # ... and passes the words on
run ALLOW "rg -n 'gh pr merge' | head -5"
run ALLOW "rg -n 'gh pr merge' | tail -5"
run ALLOW "rg -n 'gh pr merge' | sort"
run ALLOW "rg -n 'gh pr merge' | sort | uniq -c"
run ALLOW 'echo "gh pr merge 1234" |
grep merge'                                                                    # a trailing pipe continues the line
run ALLOW 'echo "gh pr merge 1234"; echo hi | sh'                             # a new pipeline reads no words
# A line continuation is one line.
run BLOCK 'gh pr \
merge 1234 --merge --admin'
run BLOCK 'git push \
--force'
# A push that lands on main is a merge by another name.
run BLOCK 'git push origin HEAD:main'
run BLOCK 'git push origin some-branch:refs/heads/main'
run BLOCK 'git push origin :main'
run BLOCK 'git push origin :refs/heads/main'
run BLOCK 'git push origin "HEAD:main"'                                      # one layer of quotes is stripped
run ALLOW 'git push origin HEAD:some-branch'
# A bare main after the remote pushes local main to it, whatever is checked out.
run BLOCK 'git push origin main'
run BLOCK 'git push origin refs/heads/main'
run BLOCK 'git push -u origin "main"'                                      # after a flag, in quotes
run ALLOW 'git push origin workflow/1438'
run ALLOW 'git push -u origin workflow/1438'
run ALLOW 'git push origin maintenance'                                     # a name that starts with main
run ALLOW 'git push origin HEAD'                                            # the text cannot decide it
run BLOCK 'git push --all origin'                                        # every local branch, main among them
run BLOCK 'git push origin --all'
run BLOCK 'git push --branches'
run BLOCK 'git push --al'
run ALLOW 'git push --tags origin'                                       # tags, no branch
run ALLOW 'git push --atomic origin workflow/1438'
run BLOCK 'gh pr merge 1234 --admin --match-head-commit abc123'          # not a squash
run BLOCK 'gh pr merge 1234 --merge --match-head-commit abc123'
run BLOCK 'gh pr merge 1234 --rebase --admin --match-head-commit abc123'
run BLOCK 'gh pr merge 1234 -m --match-head-commit abc123'
run BLOCK 'gh pr merge 1234 -rd --match-head-commit abc123'
run BLOCK 'gh pr merge 1234 -Afoo@users.noreply.github.com --match-head-commit abc123'  # the s in a value is no squash
run BLOCK 'gh pr merge 1234 --merge -Afoo@users.noreply.github.com --match-head-commit abc123'
run BLOCK 'gh pr merge -bs 1234 --match-head-commit abc123'               # -b takes "s" as its value
run BLOCK 'gh pr merge 1234 -Ajess@x.io --match-head-commit abc123'        # the s in -A's value is no squash
run BLOCK 'gh pr merge 1234 --squash --merge --match-head-commit abc123'  # a squash alongside does not excuse --merge
run BLOCK 'gh pr merge 1234 -sr --match-head-commit abc123'               # ... nor -r in a cluster
run BLOCK 'gh pr merge 1234 --squash --rebase=true --match-head-commit abc123'
run BLOCK 'gh pr merge 1234 --squash --merge=true --match-head-commit abc123'
run BLOCK 'gh pr merge 1234 -s --squash=false --match-head-commit abc123'  # the last word on --squash is false
run BLOCK 'gh pr merge 1234 -s=false --match-head-commit abc123'       # a boolean letter takes its =value
run BLOCK 'gh pr merge 1234 -d=false --match-head-commit abc123'       # ... so the s in "false" is no squash
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
run BLOCK 'gh pr --repo other/repo merge 1234 --squash --match-head-commit abc123'
run BLOCK 'gh pr merge 1234 --repo other/repo --squash --match-head-commit abc123'
run BLOCK 'gh pr -R o/r merge 1234 --admin --match-head-commit abc123'   # -R walked past, then the squash rule bites
run BLOCK 'gh pr merge 1234 -Ro/r --admin --match-head-commit abc123'
# gh steps over flags to find its subcommand, so a flag before `merge` is still the merge's.
run BLOCK 'gh pr -Ro/r merge 1234 --admin'
run BLOCK 'gh pr -R=other/repo merge 1234 --squash --match-head-commit abc123'
run BLOCK 'gh pr -Rother/repo merge 1234 --squash --match-head-commit abc123'
run BLOCK 'gh -R other/repo pr merge 1234 --squash --match-head-commit abc123'   # before pr, too
run BLOCK 'gh pr -md merge 1234 --match-head-commit abc123'                     # a cluster before merge
run BLOCK 'gh -X PUT api repos/o/r/pulls/1234/merge -f merge_method=squash'      # ... and before api
run ALLOW 'gh pr -Ro/r merge 1234 --squash --match-head-commit abc123'
run ALLOW 'gh pr -R=o/r merge 1234 --squash --match-head-commit abc123'
run BLOCK 'GH_REPO=o/r gh pr merge 1234 --squash --match-head-commit abc123'   # a GH_* assignment, even to the same repo
run BLOCK 'GH_HOST=ghe.example gh pr merge 1234 --squash --match-head-commit abc123'
run BLOCK 'xargs gh pr merge 1234 --squash --match-head-commit abc123'  # a wrapper
run BLOCK 'sudo gh pr merge 1234 --squash --match-head-commit abc123'
run BLOCK 'sh -c "gh pr merge 1234 --squash --admin --match-head-commit abc123"'   # an interpreter
run BLOCK "bash -c 'gh pr -R o/r merge 1234 --squash'"
run BLOCK 'pwsh -c "& gh pr merge 1234 --squash"'
run BLOCK 'env sh -c "gh pr merge 1234 --squash --admin"'   # an interpreter behind a wrapper
run BLOCK "sudo bash -c 'gh pr merge 1234 --squash'"
run BLOCK 'nohup sh -c "gh pr merge 1234 --squash"'
run BLOCK 'r=$(gh pr merge 1234 --match-head-commit abc123 -s)'   # a command substitution, though every condition holds
run BLOCK 'sh -c "gh api -X PUT repos/o/r/pulls/1234/merge -f merge_method=squash"'  # the merge endpoint behind an interpreter
run BLOCK 'sh -c "gh -X PUT api repos/o/r/pulls/1234/merge"'           # ... with gh's flags before api
run ALLOW 'echo "gh api repos/o/r/pulls/1/merge"'                           # prose naming the endpoint
run ALLOW 'sh -c "gh api repos/o/r/pulls/1234/comments"'
# A merge under another name.
run BLOCK 'gh api -X PUT repos/o/r/pulls/1234/merge -f merge_method=squash'
run BLOCK 'gh api graphql -f query="mutation { mergePullRequest(input: {pullRequestId: \"x\"}) { clientMutationId } }"'
# The head pin.
run BLOCK 'gh pr merge 1234 --squash --admin'                            # not pinned to the head the guard read
run BLOCK 'gh pr merge 1234 --squash --match-head-commit def456'          # pinned to a stale head
GH_VIEW='cross=true
head=abc123
count=1
listed=1
label=needs-approval
file=MODIFIED tests/test_x.py'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # the head is a fork's branch
GH_VIEW='cross=false
head=abc123
count=1
listed=1
label=development
file=MODIFIED tests/test_x.py'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # no needs-approval
GH_VIEW='cross=false
head=abc123
count=1
listed=1
label=needs-approval
label=needs-decision
file=MODIFIED tests/test_x.py'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # needs-decision alongside
GH_VIEW='cross=false
head=abc123
count=2
listed=2
label=needs-approval
file=MODIFIED tests/test_x.py
file=MODIFIED docs/analysis/requirements.md'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a file outside the auto-merge trees
GH_VIEW='cross=false
head=abc123
count=2
listed=2
label=needs-approval
file=MODIFIED tests/test_x.py
file=MODIFIED CLAUDE.md'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a rules file at the root
# A rules file a later run loads stays the human's, whichever tree holds it.
for rf in tests/CLAUDE.md docs/design/claude.local.md custom_components/x/.claude/settings.json; do
  GH_VIEW="cross=false
head=abc123
count=1
listed=1
label=needs-approval
file=ADDED $rf"
  run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a nested rules file
done
GH_VIEW='cross=false
head=abc123
count=1
listed=1
label=needs-approval
file=MODIFIED tests_extra/test_x.py'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a prefix match must not straddle a directory name
GH_VIEW='cross=false
head=abc123
count=101
listed=1
label=needs-approval
file=MODIFIED tests/test_x.py'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # gh listed fewer files than the PR has
GH_VIEW='cross=false
head=abc123
count=0
listed=0
label=needs-approval'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # no files at all
# A file name is the one fact a contributor chooses: one carrying a line break would forge
# a fact line, so it is refused, as is a control character in a name.
GH_VIEW='cross=false
head=abc123
count=1
listed=1
label=development
file=MODIFIED tests/x
label=needs-approval'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a forged label after the files began
GH_VIEW='cross=false
head=abc123
count=2
listed=1
count=1
label=needs-approval
file=MODIFIED tests/x'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a second count before the files: the first stands
GH_VIEW='cross=false
head=abc123
count=2
listed=1
label=needs-approval
file=MODIFIED tests/x
file=MODIFIED tests/y'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a forged file line: more file lines than gh listed
GH_VIEW="cross=false
head=abc123
count=1
listed=1
label=needs-approval
file=MODIFIED tests/x${tab}y"
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a control character in a name
GH_VIEW="cross=false
head=abc123
count=1
listed=1
label=needs-approval
file=MODIFIED ${cr}tests/x"
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a CR inside a name is refused, not deleted
GH_VIEW=$(printf '%s\n' "$GOOD_VIEW" | sed "s/\$/$cr/")
GH_CHECKS=$(printf '%s\n' "$GOOD_CHECKS" | sed "s/\$/$cr/")
run ALLOW 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a trailing CR per line is Windows gh's line ending
GH_CHECKS=$GOOD_CHECKS
GH_VIEW='cross=false
count=1
listed=1
label=needs-approval
file=MODIFIED tests/test_x.py'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit='  # no head to pin to, and an empty pin does not match it
# gh names a renamed or copied file by its new path only, so only a change that keeps one
# path is readable; any other change type, or none, refuses.
for ctype in RENAMED COPIED CHANGED; do
  GH_VIEW="cross=false
head=abc123
count=1
listed=1
label=needs-approval
file=$ctype tests/block-destructive-git.sh"
  run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a file moved or copied into the trees
done
GH_VIEW='cross=false
head=abc123
count=1
listed=1
label=needs-approval
file=tests/test_x.py'
run BLOCK 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a file line with no change type
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
run ALLOW 'gh pr view 1234'                                               # ... which refuses the merge alone
printf 'repo:\r\n  owner: o\r\n  name: r\r\nautopilot:\r\n  auto_merge_trees:\r\n    - custom_components/\r\n    - tests\r\n    - docs/design/\r\n' > "$STUB/profile.yml"
run ALLOW 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # a CRLF profile reads the same
unset PROFILE
STUB_REPO=kristofdegrave/homeassistant-smart-charging
run ALLOW 'gh pr merge 1234 --squash --admin --match-head-commit abc123'  # and the real profile still passes
# A word the guard trusts alone -- an early exit, the pin, a selector -- counts only where the
# words are gh's own: a quoted value spanning a blank, an escaped blank, a comment, an
# expansion, or a word after a redirection refuses the merge rather than being read.
runr "spanning a blank" 'gh pr merge 1234 --squash --admin --body "done --help"'     # a split value supplies --help
runr "spanning a blank" 'gh pr merge 1234 --squash --admin -t "fix -h"'               # ... -h
runr "spanning a blank" "gh pr merge 1234 --squash --admin --body 'a --disable-auto'" # ... --disable-auto
runr "spanning a blank" "gh pr merge 1234 --squash --admin --body \"'\"' --help '\"'\"" # each part quoted evenly, one value still
runr "spanning a blank" 'gh pr merge 1234 --squash --admin > out\ --help'            # a target continued through an escaped blank
runr "spanning a blank" 'gh pr merge 1234 --squash --admin >out\ --disable-auto'
runr "spanning a blank" 'gh pr merge 1234 --squash --admin --body "x --match-head-commit=abc123"'  # a swallowed pin
runr "names 0 pull requests" 'gh pr merge --squash --admin --match-head-commit abc123 <> 1234'   # the selector is the target
runr "not pinned" 'gh pr merge 1234 --squash --admin &>> --match-head-commit=abc123'              # ... the pin
runr "not pinned" 'gh pr merge 1234 --squash --admin <> --help'                                  # ... an early exit
runr "after the redirection" 'gh pr merge 1234 --squash --admin 2>/dev/null --match-head-commit abc123'  # a word after any redirection
runr "after the redirection" 'gh pr merge 1234 --squash --admin --body 2>x --help'               # ... a value slot included: gh gets --body --help
runr "after the redirection" 'gh pr merge 1234 --squash --admin -t >x --match-head-commit=abc123'
runr "words it splits" 'gh pr merge 1234 --squash --admin # --help'                             # a comment drops the rest
runr "words it splits" 'gh pr merge 1234 --squash --admin --body $empty --help'                 # an expansion can vanish
runr "words it splits" 'gh pr merge 1234 --squash --admin --body {,} --help'                    # ... or multiply
runr "words it splits" 'gh pr merge 1234 --squash --admin --body * --help'                      # ... or glob
runr "words it splits" 'gh pr merge 1234 --squash --admin --body "$empty" --help'               # ... in double quotes too
runr "words it splits" 'gh pr merge 1234 --squash --admin --body "" --help'                     # an empty value older PowerShell drops
TOOL=PowerShell
runr "words it splits" 'gh pr merge 1234 --squash --admin --body “x --help ”'                   # typographic quotes are quotes
runr "words it splits" 'gh pr merge 1234 --squash --admin --body ‘x --disable-auto ’'
runr "words it splits" 'gh pr merge 1234 --squash --admin --body @a --help'                      # a splat
TOOL=Bash
run ALLOW 'gh pr merge 1234 --squash --admin --match-head-commit abc123 <> --help'    # a target is the shell's: the merge gh gets is read
run ALLOW "gh pr merge 1234 --squash --admin --body '\$5' --match-head-commit abc123"  # single quotes expand nothing
run ALLOW 'gh pr merge --help 2>&1'                                                    # a real early exit, redirection last
run ALLOW 'gh pr merge 1234 -h'
run ALLOW 'gh pr merge 1234 --disable-auto > /tmp/out.txt'
run ALLOW 'gh pr merge 1234 --squash --admin --body "done" --match-head-commit abc123'  # a value quoted whole is one word
run ALLOW "gh pr merge 1234 --squash --admin --subject 'fix' --match-head-commit abc123 2>&1"

# The loop rule: with the marker the real profile names set to 1, a commit or push touching
# the harness is refused. A throwaway repository stands in for a task worktree: `main` is
# pushed to a bare origin, then a branch is cut from it.
LR=$STUB/loop
git init -q -b main "$LR/origin.git" --bare
git init -q -b main "$LR/wt"
g() { git -C "$LR/wt" -c user.name=t -c user.email=t@t "$@" >/dev/null 2>&1; }
mkdir -p "$LR/wt/src" "$LR/wt/.github" "$LR/wt/docs"
echo a > "$LR/wt/src/a.py"; echo a > "$LR/wt/.github/ci.yml"; echo a > "$LR/wt/CLAUDE.md"
g add -A; g commit -qm base; g remote add origin "$LR/origin.git"; g push -q origin main
g checkout -qb task
g worktree add -q -b side "$LR/wt2" main   # a linked worktree of the same repository
MARKER=$(awk '/^autopilot:/{t=1} t&&/^  loop_marker:/{print $2; exit}' "$CWD/.claude/profile.yml")
[ -n "$MARKER" ] || { echo "FAIL the real profile names no loop_marker"; fail=1; }

echo b > "$LR/wt/.github/ci.yml"; g add .github/ci.yml
run ALLOW "git commit -m x" "$LR/wt"                                   # marker unset: interactive, unaffected
export "$MARKER=0"
run ALLOW "git commit -m x" "$LR/wt"                                   # a marker other than 1: not the loop
export "$MARKER=1"
export GUARD_REPO="$LR/wt"   # the repository the loop works in, which the hook itself is not part of here
run BLOCK "git commit -m x" "$LR/wt"                                   # a staged .github/ change
run BLOCK "git -C $LR/wt commit -m x" "$LR/wt2"                       # ... reached through -C from a sibling worktree
runr "refused rather than read" "git </dev/null commit -m x" "$LR/wt"   # ... behind a redirection before the subcommand
g reset -q
run BLOCK "git commit -am x" "$LR/wt"                                  # an unstaged one, which -a would take
g checkout -q -- .github/ci.yml
echo b > "$LR/wt/CLAUDE.md"
run BLOCK "git commit -am x" "$LR/wt"                                  # CLAUDE.md
g checkout -q -- CLAUDE.md
mkdir -p "$LR/wt/docs/.Claude"; echo b > "$LR/wt/docs/.Claude/s.json"; g add docs
run BLOCK "git commit -m x" "$LR/wt"                                   # a nested .claude/, any case
g reset -q
run BLOCK "git add docs && git commit -m x" "$LR/wt"                   # an untracked one a git add before it would stage
rm -rf "$LR/wt/docs/.Claude"
g mv .github/ci.yml src/ci.yml
run BLOCK "git commit -m x" "$LR/wt"                                   # a rename out of .github/
g mv src/ci.yml .github/ci.yml
g mv src/a.py .github/a.py
run BLOCK "git commit -m x" "$LR/wt"                                   # a rename into .github/, read only once split
g mv .github/a.py src/a.py
echo b > "$LR/wt/src/a.py"; g add src
run ALLOW "git commit -m x" "$LR/wt"                                   # a change outside the harness
echo z > "$LR/wt2/.github/ci.yml"; git -C "$LR/wt2" add .github/ci.yml
run ALLOW "git -C $LR/wt commit -m x" "$LR/wt2"                        # ... through -C, from a worktree with harness edits
run ALLOW "git -C \"$LR/wt\" commit -m x" "$LR/wt2"                    # ... with the -C path quoted
git -C "$LR/wt2" reset -q; git -C "$LR/wt2" checkout -q -- .github/ci.yml
mkdir -p "$LR/other"; git init -q "$LR/other"
run BLOCK "git -C $LR/other status" "$LR/wt"                           # a -C into another repository: its config and hooks
run BLOCK "git -c core.pager=cat log -1" "$LR/wt"                      # a -c override
run BLOCK "git --config-env=core.pager=P log -1" "$LR/wt"              # ... or --config-env
run BLOCK "git log -1 --out''put=x" "$LR/wt"                           # --output, quote-split
run BLOCK "git fetch '--upload-pack=x' origin" "$LR/wt"                # --upload-pack, quoted
run ALLOW "git fetch origin" "$LR/wt"                                  # a plain fetch of origin
run ALLOW "git fetch origin main" "$LR/wt"                             # ... of one branch
run BLOCK "git fetch https://example.invalid/fork main" "$LR/wt"       # a fetch from a URL
run BLOCK "git pull fork main" "$LR/wt"                                # a pull from another remote
run BLOCK "git fetch origin refs/pull/1/head" "$LR/wt"                 # a pull-request ref
runr "pull-request ref" "git fetch origin '+pull/1/head:x'" "$LR/wt"   # ... quoted, with a destination
run BLOCK "git fetch origin task:refs/remotes/origin/main" "$LR/wt"    # a fetch that moves origin/main
run BLOCK "git fetch . HEAD:refs/remotes/origin/main" "$LR/wt"         # ... from the repository itself (the source rule)
run BLOCK "git remote add fork https://example.invalid/fork" "$LR/wt"  # a new remote
run BLOCK "git remote set-url origin https://example.invalid/x" "$LR/wt" # a moved one
run ALLOW "git remote -v" "$LR/wt"                                     # reading the remotes
run BLOCK "gh issue edit 5 --remove-label NEEDS-APPROVAL"              # the human's go, upper case
run BLOCK "gh issue edit 5 --remove-label needs-appro''val"            # ... quote-split
run BLOCK "gh issue edit 5 --remove-label=needs-decision,Needs-Approval" # ... in a list
run ALLOW "gh issue edit 5 --add-label needs-approval --remove-label needs-decision" # adding it is not removing it
run ALLOW "gh pr edit 5 --remove-label needs-approval"                 # a pull request's label: the admitted gesture
run BLOCK "gh api -X delete repos/o/r/issues/5/labels/Needs-Approval"  # a REST DELETE, any case
run BLOCK "gh api -X PUT repos/o/r/issues/5/labels -f 'labels[]=workflow'" # a PUT replacing the set
run BLOCK "gh api --method=PATCH repos/o/r/issues/5 -f 'labels[]=x'"   # an issue PATCH setting labels
run BLOCK "gh api graphql -f query='mutation{ removeLabels''FromLabelable(input:{}){ clientMutationId } }'" # a GraphQL removal, quote-split
run ALLOW "gh api repos/o/r/issues/5/labels"                           # reading the labels
run BLOCK "git status" "$LR/other"                                     # a cwd that is another repository
run BLOCK "git -C $LR/wt -C . status" "$LR/wt"                         # more than one -C: git chains them
run BLOCK "cd $LR/wt && git status" "$LR/wt"                           # any git after a cd
run BLOCK "git fe''tch https://example.invalid/fork main" "$LR/wt"     # a quote-split subcommand
run BLOCK "git re''mote add fork https://example.invalid/fork" "$LR/wt"
run BLOCK "git '-c' core.fsmonitor=x status" "$LR/wt"                  # a quoted -c
run BLOCK "git -cfoo=bar status" "$LR/wt"                              # ... attached
run BLOCK "git --con''fig-env=a=b status" "$LR/wt"                     # a quote-split --config-env
run BLOCK "git --exec-path=/x fetch origin" "$LR/wt"                   # --exec-path: git runs its helpers from there
run BLOCK "git --git''-dir=/x status" "$LR/wt"                         # --git-dir, quote-split
run BLOCK "git --work-tree=/x status" "$LR/wt"                         # --work-tree
run BLOCK "git push --receive-pack=x origin task" "$LR/wt"             # --receive-pack
runr "'--exec=x' is refused" "git fetch --exec=x origin" "$LR/wt"      # --exec
run BLOCK "git log -1 --out\\put=x" "$LR/wt"                           # --output behind a backslash escape
run BLOCK "git remote rename origin o2" "$LR/wt"                       # the remotes: rename
run BLOCK "git remote set-branches origin x" "$LR/wt"                  # ... set-branches
run BLOCK "git remote set-head origin x" "$LR/wt"                      # ... set-head
run BLOCK "git fetch --multiple origin fork" "$LR/wt"                  # --multiple makes every operand a remote
run BLOCK "git fetch --negotiation-tip x origin main" "$LR/wt"         # an option the guard does not read
run BLOCK "git fetch origin 0123456789abcdef0123456789abcdef01234567" "$LR/wt" # an object id
run ALLOW "git fetch --prune origin" "$LR/wt"                          # an option it does read
run BLOCK "git config core.hooksPath x" "$LR/wt"                       # a config write
run ALLOW "git con''fig --get remote.origin.url" "$LR/wt"              # a config read
run BLOCK "git sub''module foreach true" "$LR/wt"                      # a subcommand the loop file denies, quote-split
run BLOCK "git replace HEAD HEAD~1" "$LR/wt"                           # replace refs rewrite what history reads as
run BLOCK "git checkout main -- src/a.py" "$LR/wt"                     # a checkout of paths
run BLOCK "gh issue edit 5 --remove-label needs-appro\\val"            # the human's go behind a backslash escape
run BLOCK "gh api -XDELETE repos/o/r/issues/5/labels/needs-approval"   # an attached -X
run BLOCK "gh api --method PATCH repos/o/r/issues/5 -f 'labels[]=x'"   # a separate --method
run BLOCK "gh api graphql -f query='mutation{ clearLabelsFromLabelable(input:{}){ clientMutationId } }'"
run BLOCK "gh api graphql -f query='mutation{ updateIssue(input:{labelIds:[]}){ clientMutationId } }'"
run BLOCK "gh api graphql -f query='mutation{ merge''Branch(input:{}){ clientMutationId } }'" # a merge into main, quote-split
run BLOCK "gh api graphql -f query='mutation{ updateRef (input:{}){ clientMutationId } }'"   # ... or spaced
run BLOCK "gh api graphql -f query='mutation{ removeLabels''FromLabelable(input:{clientMutationId:\"issue edit\"}){ clientMutationId } }'" # words that read like issue edit
runr "removing needs-approval" "A=1 gh issue edit 5 --remove-label needs-appro''val" # behind an assignment
runr "mergebranch" "{ gh api graphql -f query='mutation{ merge''Branch(input:{}){ clientMutationId } }'; }" # behind a brace
runr "deletelabel" "gh api graphql -f query='mutation{ deleteLabel(input:{}){ clientMutationId } }'" # deleting the label itself
runr "sets labels" "gh api repos/o/r/issues/5 -f 'labels[]=workflow'"  # an issue write by gh's default POST
runr "sets labels" "gh api -X POST repos/o/r/issues/5 -f 'labels[]=x'" # ... spelled out
runr "carrying" "gh issue edit 5 --remove-label $'needs\\055approval'" # an ANSI-C quote builds the word
runr "carrying" "git -C $LR/wt $'\\055c' core.fsmonitor=x status" "$LR/wt" # ... -c, which stripping would misread
runr "GIT_" "GIT_CONFIG_PARAMETERS=x git status" "$LR/wt"              # the environment form of -c
runr "GIT_" "GIT_DIR=/x git -C $LR/wt status" "$LR/wt"                 # ... of --git-dir
runr "GIT_" "git_ssh_command=x git fetch origin" "$LR/wt"              # ... GIT_SSH_COMMAND, any case
runr "git grep" "git gr''ep -Ocat x" "$LR/wt"                          # grep -O runs a program
runr "git grep" "git grep --open-files-in-pager=cat x" "$LR/wt"
runr "archive -o" "git archive -o x.tar HEAD" "$LR/wt"                 # archive -o writes a file
runr "naming paths" "git checkout origin/main .github/hooks/pre-commit" "$LR/wt" # a path checkout without --
run ALLOW "git checkout task" "$LR/wt"                                 # a branch checkout
run ALLOW "git checkout task 2>/dev/null" "$LR/wt"                     # ... a redirection is not a path
runr "is no commit" "git checkout .github/hooks/pre-commit" "$LR/wt"   # one operand that is no commit: a path
runr "tracked path" "git checkout --ours .github/ci.yml" "$LR/wt"      # ... a tracked one behind --ours
runr "naming paths" "git checkout --pathspec-fr=f main" "$LR/wt"       # --pathspec-from-file by a prefix
runr "global" "git --bare status" "$LR/wt"                             # --bare: the cwd as the git directory
runr "bash would expand" "git -C $LR/wt {-c,} core.fsmonitor=x status" "$LR/wt" # a brace list rebuilds -c
runr "bash would expand" "git log HEAD{1..2}" "$LR/wt"                 # ... a brace range
runr "bash would expand" "git log -[c]" "$LR/wt"                       # ... an unquoted glob
run ALLOW "git ls-files '*.md'" "$LR/wt"                               # a quoted pathspec is no expansion
run ALLOW "git log -1 HEAD@{1}" "$LR/wt"                               # a reflog brace is no list
runr "would expand" "gh issue edit 5 --remove-label=needs-appro{v,v}al" # a brace list rebuilds the label
runr "sets labels" "gh api 'repos/o/r/issues/5?/labels' -f 'labels[]=workflow'" # a query string fools no exemption
runr "naming paths" "git checkout --pathspec-from-file=f main" "$LR/wt" # paths from a file
runr "bash would expand" "git ''{-c,core.fsmonitor=x} status" "$LR/wt"  # a quoted prefix hides no brace
runr "bash would expand" "git '-'[c] status" "$LR/wt"                   # ... nor a glob
runr "bash would expand" "git log HEAD@{1,2}" "$LR/wt"                  # a reflog brace with a comma is a list
runr "bash would expand" "gh issue edit 5 {--remove-label,needs-approval}" # a brace list rebuilds the option
runr "bash would expand" "gh api -X {DELETE,} repos/o/r/issues/5/labels/needs-approval" # ... or the method
runr "is no commit" "git checkout '.github/hooks/pre-commi[!>]'" "$LR/wt" # a quoted > is no redirection
runr "is no commit" "git checkout ':!>'" "$LR/wt"                       # ... an exclude-only pathspec
runr "sets labels" "gh api repos/o/r/issues/5x/labels -f 'labels[]=workflow'" # <n> is digits only
run ALLOW "git log HEAD@{1}..HEAD" "$LR/wt"                             # a reflog range is no brace list
run ALLOW "git log --grep=\"a b?\" --format='[%h]'" "$LR/wt"            # quoted text split on its space
run ALLOW "git checkout -b x origin/main" "$LR/wt"                      # a new branch from a commit
run ALLOW "git checkout main" "$LR/wt"                                  # a branch
g update-ref refs/remotes/origin/only HEAD
run ALLOW "git checkout only" "$LR/wt"                                  # a branch only origin has: tracking
echo a > "$LR/wt/only"; g add only
runr "tracked path" "git checkout --no-guess only" "$LR/wt"             # ... that is also a path git restores
g rm -q --cached only; rm -f "$LR/wt/only"
runr "bash would expand" "git {-c,'alias.zz=!touch /tmp/p #'{}} zz" "$LR/wt" # a nested brace hides no list
runr "bash would expand" "gh issue edit 5 {--remove-label=needs-approval,--title=t{}}"
runr "sets labels" "gh api 'repos/o/r/issues/5?a=/6/labels' -f 'labels[]=x'" # a query string ending in <n>/labels
runr "sets labels" "gh api 'repos/o/r/issues/5#/6/labels' -f 'labels[]=x'"   # ... a fragment
runr "bash would expand" "git -C $LR/wt @(-c) core.fsmonitor=x status" "$LR/wt" # an extended glob
runr "--patch" "git checkout -p main" "$LR/wt"                           # hunks written into paths
runr "--patch" "git checkout --patc main" "$LR/wt"                       # ... by a prefix
runr "--patch" "git checkout -fp main" "$LR/wt"                          # ... in a cluster
run ALLOW "git checkout -bpatch main" "$LR/wt"                          # a -b cluster names a branch
runr "bash would expand" "git status # why?" "$LR/wt"                   # a comment is read as text: conceded
# An awk that fails while `expands` reads counts as expanding: a stub awk fails that call
# alone (the one passing `sq=`) and hands every other to the real one.
mkdir -p "$STUB/awkfail"
printf '#!/bin/sh\ncase " $* " in *" sq="*) exit 2 ;; esac\nexec "%s" "$@"\n' "$(command -v awk)" > "$STUB/awkfail/awk"
chmod +x "$STUB/awkfail/awk"
OLD_PATH=$PATH
PATH="$STUB/awkfail:$PATH"
runr "bash would expand" "git status" "$LR/wt"                          # fails closed
PATH=$OLD_PATH
run ALLOW "bash .github/gh-as-bot.sh pr-create workflow/1 \"t?\" /tmp/b.md" # the author-side wrapper: bash, not gh
runr "bash would expand" "gh issue edit 5 --title ''# {--remove-label,needs-approval}" # a # inside a word is no comment
runr "bash would expand" "git --namespace ''# {-c,core.fsmonitor=x} status" "$LR/wt"   # ... before git's -c
runr "bash would expand" "gh issue edit 5 --title \\ # {--remove-label,needs-approval}" # ... after an escaped blank
runr "segment carrying" "A=\$'\\'' gh issue edit 5 {--remove-label,needs-approval}" # an ANSI-C quote unreads the rest
runr "segment carrying" "A=\$'\\'' git {-c,core.fsmonitor=x} status" "$LR/wt"     # ... before git
run ALLOW "git checkout -Bpx main" "$LR/wt"                             # a -B cluster names a branch
runr "abbreviates" "git ls-remote --up=x ." "$LR/wt"                   # --upload-pack by a prefix
runr "abbreviates" "git push --ex=x origin task" "$LR/wt"              # --exec by a prefix
runr "abbreviates" "git archive --remote=. --e=x HEAD" "$LR/wt"
runr "abbreviates" "git archive --out=x HEAD" "$LR/wt"                 # --output by a prefix
runr "abbreviates" "git grep --op=cat x" "$LR/wt"                      # --open-files-in-pager by a prefix
runr "-o writes" "git archive -vox HEAD" "$LR/wt"                      # -o clustered
runr "-O runs" "git grep -nOcat x" "$LR/wt"                            # -O clustered
runr "fetch pattern" "git fetch origin 'refs/*/1/head'" "$LR/wt"       # a glob reaching a pull-request ref
runr "sets labels" "gh api repos/o/r/issues/5 '-flabels[]=workflow'"     # the field attached to -f
runr "label delete" "gh api -X=DELETE repos/o/r/issues/5/labels/needs-approval" # -X=
run ALLOW "gh api -X POST repos/o/r/issues/5/labels -f 'labels[]=needs-approval'" # the add-labels endpoint only adds
run ALLOW "gh api -X POST repos/o/r/issues/5/comments -F body=@/tmp/b.md" # the loop's gh steps: a comment
printf '{"commit_id":"a","event":"COMMENT","body":"x"}\n' > "$STUB/p.json"
run ALLOW "gh api repos/o/r/pulls/5/reviews --input $STUB/p.json"       # ... a review
run ALLOW "gh api graphql -f query='query{ repository(owner:\"o\", name:\"r\") { pullRequest(number:5) { reviewThreads(first:100) { pageInfo { hasNextPage endCursor } nodes { id isResolved isOutdated comments(first:1){ nodes { databaseId path line body } } } } } } }'" # ... the thread listing
run ALLOW "gh api graphql -f query='mutation{ resolveReviewThread(input:{threadId:\"x\"}){ thread { id isResolved } } }'" # ... a resolve mutation the guard does not refuse; the loop resolves through the wrapper
run ALLOW "gh pr edit 5 --add-label needs-approval"                    # ... a label on a pull request
run BLOCK "cd $LR/wt && git commit -m x" "$LR/wt"                      # after a cd the guard cannot follow (the tree is clean of harness)
g commit -qm code
run ALLOW "git push origin task" "$LR/wt"                              # a push of code only
run ALLOW "git push" "$LR/wt"                                          # no refspec: HEAD
run ALLOW "git -C $LR/wt push -u origin task" "$LR/wt"                 # the loop's own steps: push -u
printf 'm\n' > "$STUB/msg.txt"
run ALLOW "git -C $LR/wt commit -F $STUB/msg.txt" "$LR/wt"             # ... commit -F
run ALLOW "git -C $LR/wt merge origin/main" "$LR/wt"                   # ... merge origin/main
run ALLOW "git worktree add $LR/wt3 origin/main" "$LR/wt"              # ... worktree add
run ALLOW "git worktree add -b b3 $LR/wt3 origin/main" "$LR/wt"
run ALLOW "git -C $LR/wt worktree remove $LR/wt2" "$LR/wt"             # ... worktree remove
g checkout -q main
run BLOCK "git push" "$LR/wt"                                          # no refspec while main is checked out: a push to main
run BLOCK "git push origin HEAD" "$LR/wt"                              # ... HEAD named
run BLOCK "git -C $LR/wt push" "$LR/wt2"                               # ... through -C
run BLOCK "git push origin @" "$LR/wt"                                 # ... as @
run BLOCK "git pu''sh" "$LR/wt"                                        # ... quote-split
run BLOCK "git push origin Head" "$LR/wt"                              # ... in mixed case
run ALLOW "git push origin HEAD:task" "$LR/wt"                         # HEAD with a destination is not a push to main
g checkout -q task
run ALLOW "git push -o ci.skip origin task" "$LR/wt"                   # an option's separate value is not read as the remote
run BLOCK "git push origin --tags" "$LR/wt"                            # tags carry commits no source diff sees
run BLOCK "git push --follow-tags origin task" "$LR/wt"                # ... followed ones too
run BLOCK "cd $LR/wt && git push origin task" "$LR/wt"                 # a push after a cd
run BLOCK "{ cd $LR/wt; git commit -m x; }" "$LR/wt"                   # a cd behind a brace
run BLOCK "if cd $LR/wt; then git commit -m x; fi" "$LR/wt"            # ... or a reserved word
run BLOCK "Set-Location $LR/wt; git commit -m x" "$LR/wt"              # PowerShell's, any case
run BLOCK "env -C $LR/wt git commit -m x" "$LR/wt"                     # env -C
echo c > "$LR/wt/.github/ci.yml"; g commit -qam harness
g tag origin/main HEAD
run BLOCK "git push origin task" "$LR/wt"                              # a tag named origin/main does not shadow the remote ref
g tag -d origin/main
run BLOCK "git push origin task" "$LR/wt"                              # a pushed commit touching .github/
run BLOCK "git push -u origin HEAD:task" "$LR/wt"                      # ... whatever the refspec spells
run BLOCK "git push" "$LR/wt"                                          # ... or with none
run BLOCK "git push -o ci.skip origin task" "$LR/wt"                   # ... behind an option's separate value
g branch other main
run BLOCK "git push origin other task" "$LR/wt"                        # ... as the second of two sources
g reset -q --hard HEAD~1
g mv .github/ci.yml src/moved.yml; g commit -qm move
run BLOCK "git push origin task" "$LR/wt"                              # a pushed rename out of .github/
g reset -q --hard HEAD~1
g checkout -q main; echo m > "$LR/wt/.github/ci.yml"; g commit -qam main-harness; g push -q origin main
g checkout -q task
run ALLOW "git push origin task" "$LR/wt"                              # main moved on with a harness change the branch lacks: three-dot
g merge -q --no-edit main
run ALLOW "git push origin task" "$LR/wt"                              # a merge of main brings harness content in: not the branch's
g checkout -q main; echo m2 > "$LR/wt/.github/ci.yml"; echo mainside > "$LR/wt/src/a.py"; g commit -qam main2; g push -q origin main
g checkout -q task; echo taskside > "$LR/wt/src/a.py"; g commit -qam taskside; g merge main
echo resolved > "$LR/wt/src/a.py"; g add src/a.py
run ALLOW "git commit -m x" "$LR/wt"                                   # finishing a conflicted merge of main: its harness change is main's
echo mine > "$LR/wt/.github/ci.yml"; g add .github/ci.yml
run BLOCK "git commit -m x" "$LR/wt"                                   # ... but not with a harness edit on top
g checkout -q MERGE_HEAD -- .github/ci.yml; g commit -qm merged
echo q > "$LR/wt/src/a b.py"
run BLOCK "git commit -m x" "$LR/wt"                                   # a path git had to quote (a space): closed
rm -f "$LR/wt/src/a b.py"
g checkout -q main; echo s > "$LR/wt/.github/a b.yml"; g add -A; g commit -qm spaced; g push -q origin main
g checkout -q task; g merge -q --no-edit main; echo t > "$LR/wt/src/a.py"; g commit -qam t2
g checkout -q main; g rm -q ".github/a b.yml"; echo u > "$LR/wt/src/a.py"; g commit -qam unspace; g push -q origin main
g checkout -q task; g merge main; echo r > "$LR/wt/src/a.py"; g add src/a.py
run BLOCK "git commit -m x" "$LR/wt"                                   # a merge's staged deletion of a quoted harness path: closed, not excepted
g commit -qm merged2
run BLOCK "git push origin nosuchbranch" "$LR/wt"                      # a source git cannot diff: closed
run BLOCK "git commit -m x" "$STUB"                                    # not a repository: closed
runr "refused rather than read" "git >/dev/null -c core.fsmonitor=x status" "$LR/wt" # in the loop too
runr "refused rather than read" "git 2>&1 -c core.fsmonitor=x status" "$LR/wt"
runr "refused rather than read" "</dev/null git -c core.fsmonitor=x status" "$LR/wt"
runr "refused rather than read" "git >| /tmp/o -c core.fsmonitor=x status" "$LR/wt"
runr "refused rather than read" "gh 2>/dev/null issue edit 5 --remove-label needs-approval"
runr "directory change" "2>/dev/null cd $LR/wt && git commit -m x" "$LR/wt" # a redirection where cd would be: a directory change
run ALLOW "git status >/dev/null 2>&1" "$LR/wt"                        # a redirection after the subcommand
# A quoted or escaped separator does not cut a git or gh segment short: the loop reads the
# command again, split only where bash splits it.
runr "global -c" "git --namespace ';' -c core.fsmonitor=x status" "$LR/wt"
runr "global -c" "git --namespace '|' -c core.fsmonitor=x status" "$LR/wt"
runr "global -c" "git --namespace '&&' -c core.fsmonitor=x status" "$LR/wt"
runr "global -c" "git --namespace \";\" -c core.fsmonitor=x status" "$LR/wt" # ... in double quotes
runr "global -c" "git --namespace \\; -c core.fsmonitor=x status" "$LR/wt"   # ... escaped
runr "bash would expand" "git {-ccore.fsmonitor=a\\;b,} status" "$LR/wt"  # ... escaped, in a brace list
runr "removing needs-approval" "gh issue edit 5 --title ';' --remove-label needs-approval"
runr "global -c" "git commit -m 'a;b'; git -c core.fsmonitor=x status" "$LR/wt" # a real one after a quoted one
runr "global -c" "echo \"\$(echo \")\"; git -c core.fsmonitor=x status; echo \"(\")\"" "$LR/wt" # bash requotes in a substitution: the plain split reads it
run ALLOW "git commit -m \"a; b\"" "$LR/wt"                            # a quoted separator in a message
run ALLOW "git commit -m 'a | b && c'" "$LR/wt"
run ALLOW "git commit -m 'a;b' && cd .." "$LR/wt"                      # each reading starts with no directory change
runr "global -c" "git status # it's clean
git --namespace ';' -c core.fsmonitor=x status" "$LR/wt"               # a comment's quote opens nothing
runr "global -c" "cat <<EOF >/dev/null
it's done
EOF
git --namespace ';' -c core.fsmonitor=x status" "$LR/wt"               # ... nor a heredoc body's
runr "global -c" "cat <<-'EOF' >/dev/null
	it's done
	EOF
git --namespace ';' -c core.fsmonitor=x status" "$LR/wt"               # ... a <<- one, its delimiter quoted
runr "global -c" "echo \$((1<<2))
git --namespace ';' -c core.fsmonitor=x status" "$LR/wt"               # a << with no delimiter line drops nothing
runr "global -c" "git status & git -c core.fsmonitor=x status" "$LR/wt" # a background & splits
run ALLOW "git status >/dev/null 2>&1" "$LR/wt"                        # ... a redirection's & does not
run ALLOW "git status &>/dev/null" "$LR/wt"
run ALLOW "git commit -m 'a & b'" "$LR/wt"
run ALLOW "# a note" "$LR/wt"                                          # all comment: nothing to scan
runr "global -c" "cat <<'EOF' >/dev/null
x
EOF
git --namespace ';' -c core.fsmonitor=x status
cat <<EOF >/dev/null
y
EOF" "$LR/wt"                                                         # a stripped terminator does not let a later one match
runr "global -c" "cat <<EOF >/dev/null
| it's | a |
EOF
git --namespace ';' -c core.fsmonitor=x status" "$LR/wt"               # ... nor a body line ending in | hide one
runr "global -c" "cat <<-EOF >/dev/null
	it's done
	EOF
git --namespace ';' -c core.fsmonitor=x status" "$LR/wt"               # an unquoted <<- body: the tab strip
runr "global -c" "grep -c x <<< 'a b'
git --namespace ';' -c core.fsmonitor=x status" "$LR/wt"               # a here-string opens no heredoc
runr "global -c" "git \\
-c core.fsmonitor=x status" "$LR/wt"                                    # a backslash-newline joins, leaving no stray word
runr "global -c" "git status # see \\
git -c core.fsmonitor=x status" "$LR/wt"                                # ... but not inside a comment
runr "global -c" "cat <<\"a\\\"b\" >/dev/null; git --namespace ';' -c core.fsmonitor=x status
x
a\"b" "$LR/wt"                                                          # an escaped quote in a double-quoted delimiter
runr "global -c" "cat <<'E'\"O\"F >/dev/null
it's
EOF
git --namespace ';' -c core.fsmonitor=x status" "$LR/wt"               # a delimiter quoted in parts
runr "global -c" "cat <<\\EOF >/dev/null
it's
EOF
git --namespace ';' -c core.fsmonitor=x status" "$LR/wt"               # ... and backslash-quoted
runr "global -c" "cat <<A <<B >/dev/null
it's
A
it's
B
git --namespace ';' -c core.fsmonitor=x status" "$LR/wt"               # two openers on one line
runr "global -c" "cat <<EOF |
it's
EOF
git --namespace ';' -c core.fsmonitor=x status" "$LR/wt"               # a pipe ending the opener's line: the body is dropped
runr "global -c" "git --namespace \"a\\
b\" -c core.fsmonitor=x status" "$LR/wt"                                # a backslash-newline in double quotes joins
runr "global -c" "echo \\\\
git -c core.fsmonitor=x status" "$LR/wt"                                # an even run of backslashes: the newline separates
runr "delimiter carries" "cat <<\$'E\\x4fF' >/dev/null
it's
EOF
git status" "$LR/wt"                                                    # a delimiter bash builds: refused, not read
runr "delimiter carries" "cat <<\"\${x}\" >/dev/null
y
EOF" "$LR/wt"
runr "delimiter carries" "cat <<E\$(echo O)F >/dev/null
y
EOF" "$LR/wt"
runr "delimiter carries" "cat <<E\`echo O\`F >/dev/null
y
EOF" "$LR/wt"                                                           # ... a backquoted part
runr "delimiter carries" "cat <<-\$X >/dev/null
	y
	\$X" "$LR/wt"                                                          # ... after <<-
runr "delimiter carries" "cat <<A <<\$B >/dev/null
a
A
b
\$B" "$LR/wt"                                                           # ... in a second opener on the line
runr "delimiter carries" "cat <<\$" "$LR/wt"                            # ... as the input's last character
run ALLOW "cat <<'\$X' >/dev/null
y
\$X" "$LR/wt"                                                           # ... a single-quoted \$ is a letter
run ALLOW "cat <<\\\$X >/dev/null
y
\$X" "$LR/wt"                                                           # ... and so is an escaped one
run ALLOW "cat <<EOF >/dev/null
cost: \$5 and \`date\`
EOF
git status" "$LR/wt"                                                    # a \$ or backtick in the body, not the delimiter
run ALLOW "git status |& cat" "$LR/wt"                                 # |& and >& are no background &
run ALLOW "git status >&2" "$LR/wt"
run ALLOW "git log --oneline |
wc -l" "$LR/wt"                                                        # a pipe ending its line feeds the next
run ALLOW "git status \\
--short" "$LR/wt"                                                      # a real continuation
mkdir -p "$STUB/splitfail"
printf '#!/bin/sh\ncase " $* " in *" q1="*) exit 2 ;; esac\nexec "%s" "$@"\n' "$(command -v awk)" > "$STUB/splitfail/awk"
chmod +x "$STUB/splitfail/awk"
OLD_PATH=$PATH
PATH="$STUB/splitfail:$PATH"
runr "could not be split" "git status" "$LR/wt"                         # an awk that fails: closed
PATH=$OLD_PATH
unset "$MARKER" GUARD_REPO
run ALLOW "git --namespace ';' -c core.fsmonitor=x status" "$LR/wt"   # the second reading: interactive, unaffected
run ALLOW "git commit -m x" "$STUB"                                    # ... and with the marker unset, untouched
run ALLOW "git -c core.pager=cat log -1" "$LR/wt"                      # the loop's git rules: interactive, unaffected
run ALLOW "git fetch https://example.invalid/fork main" "$LR/wt"
run ALLOW "gh issue edit 5 --remove-label NEEDS-APPROVAL"
run ALLOW "git log HEAD{1..2}" "$LR/wt"                                # the expansion rule: interactive, unaffected
run ALLOW "GIT_DIR=/x git status" "$LR/wt"                             # a GIT_* prefix: interactive, unaffected
run ALLOW "gh issue edit 5 --remove-label \$'x'"                       # ... a \$ word too
run BLOCK "GIT_X=\$(git push --force) true"                           # an assignment's substitution is still read
run BLOCK "GH_X=\$(git push --force) x"

# --- the approval rule: the session never approves a pull request ---
printf '{"commit_id":"a","event":"APPROVE","body":"x"}\n' > "$STUB/ev-event.json"
printf '{"commit_id":"a", "event" : "approve"}\n' > "$STUB/ev-spaced.json"
printf '{"commit_id":"a","event":"COMMENT","body":"do not APPROVE yet"}\n' > "$STUB/comment.json"
runr "posts an approval" "gh pr review 12 --approve"
run BLOCK "gh pr review 12 --approve=true"
run BLOCK "gh pr review 12 --approve=1"                                  # gh's bools take what ParseBool takes
run BLOCK "gh pr review 12 --approve=T"
run BLOCK "gh pr review 12 --approve=TRUE"
run ALLOW "gh pr review 12 --approve=false -c -b x"                      # a false value approves nothing
run ALLOW "gh pr review 12 --approve=0 -c -b x"
run ALLOW "gh pr review 12 --approve=False -c -b x"
run ALLOW "gh pr review 12 --approve=FALSE -c -b x"
run ALLOW "gh pr review 12 --approve=f -c -b x"
run ALLOW "gh pr review 12 --approve=F -c -b x"
printf 'APPROVE\n' > "$STUB/ev.txt"
runr "reads a value from a file" "gh api repos/o/r/pulls/12/reviews -F event=@$STUB/ev.txt"
run BLOCK "gh api repos/o/r/pulls/12/reviews --field event=@$STUB/ev.txt"
run BLOCK "gh api repos/o/r/pulls/12/reviews --field=event=@$STUB/ev.txt"
run BLOCK "gh api repos/o/r/pulls/12/reviews -f event=COMMENT -F body=@$STUB/comment.json"   # any value from a file on a review call
run BLOCK "gh api repos/o/r/pulls/12/reviews -Fevent=@$STUB/ev.txt"     # attached to the flag
run BLOCK "gh api repos/o/r/pulls/12/reviews --field=event=@$STUB/ev.txt"
runr "reads a value from a file" "gh api graphql -F query=@$STUB/m.graphql"
run BLOCK "gh api graphql -Fquery=@$STUB/m.graphql"
run BLOCK "gh api graphql --field=query=@$STUB/m.graphql"
run BLOCK "gh api graphql -f query='mutation(\$e: PullRequestReviewEvent!){ addPullRequestReview(input:{pullRequestId:\"x\",event:\$e}){ clientMutationId } }' -F e=@$STUB/ev.txt"   # a variable from a file
runr "from --input" "gh api graphql --input $STUB/q.json"
run BLOCK "gh api graphql --input=$STUB/q.json"
run ALLOW "gh api graphql -f query='query{ repository(owner:\"o\", name:\"r\") { pullRequest(number:5) { reviewThreads(first:100) { nodes { id } } } } }'"   # an inline document is read
runr "changed directory" "cd $STUB && gh api repos/o/r/pulls/12/reviews --input comment.json"
runr "posts an approval" "gh pr review 12 -a"
run BLOCK "gh pr review 12 -ca"                                          # a cluster carrying a
run BLOCK "gh -R o/r pr review 12 --approve"                             # flags before the path are walked past
run BLOCK "timeout 60 gh pr review 12 -a"                                # behind a transparent wrapper
run ALLOW "gh pr review 12 --comment -b approve"                         # -b takes the value: a body, not a flag
run ALLOW "gh pr review 12 -bapprove"                                    # ... in a cluster too
run ALLOW "gh pr review 12 -c -F body.md"
run ALLOW "gh pr review --help"
runr "names APPROVE" "gh api repos/o/r/pulls/12/reviews -f event=APPROVE"
run BLOCK "gh api repos/o/r/pulls/12/reviews -F event=approve -f body=x"
runr "carries an APPROVE event" "gh api repos/o/r/pulls/12/reviews --input $STUB/ev-event.json"
runr "carries an APPROVE event" "gh api repos/o/r/pulls/12/reviews --input=$STUB/ev-event.json"
runr "carries an APPROVE event" "gh api repos/o/r/pulls/12/reviews --input \"$STUB/ev-spaced.json\""
runr "carries an APPROVE event" "gh api repos/o/r/pulls/12/reviews --input ev-event.json" "$STUB"   # resolved against the command's cwd
runr "not a readable regular file" "gh api repos/o/r/pulls/12/reviews --input $STUB/missing.json"
runr "device or process file" "gh api repos/o/r/pulls/12/reviews --input /dev/stdin"   # stdin by another name
run BLOCK "gh api repos/o/r/pulls/12/reviews --input /dev/fd/0"
run BLOCK "gh api repos/o/r/pulls/12/reviews --input /proc/self/fd/0"
run BLOCK "gh api repos/o/r/pulls/12/reviews --input $STUB"            # a directory, not a regular file
runr "command of its own" "printf x > $STUB/comment.json && gh api repos/o/r/pulls/12/reviews --input $STUB/comment.json"   # another segment could write the payload first
run BLOCK "gh api repos/o/r/pulls/12/reviews --input $STUB/comment.json; echo done"
runr "stdin" "gh api repos/o/r/pulls/12/reviews --input -"
runr "names APPROVE" "gh api graphql -f query='mutation{ addPullRequestReview(input:{pullRequestId:\"x\",event:APPROVE}){ clientMutationId } }'"
run BLOCK "gh api --silent graphql -f query='mutation{ addPullRequestReview(input:{pullRequestId:\"x\",event:APPROVE}){ clientMutationId } }'"   # a boolean flag before the endpoint
run BLOCK "gh api -i --paginate graphql -f query='mutation{ submitPullRequestReview(input:{pullRequestReviewId:\"x\",event:APPROVE}){ clientMutationId } }'"
run BLOCK "gh api /graphql -f query='mutation{ addPullRequestReview(input:{pullRequestId:\"x\",event:APPROVE}){ clientMutationId } }'"   # the endpoint spelled as a path
run BLOCK "gh api repos/o/r/pulls/12/reviews/9/events -f event=APPROVE"   # submitting a pending review
run ALLOW "gh api repos/o/r/pulls/12/reviews --input $STUB/comment.json"   # a COMMENT review, APPROVE only in its prose
printf '{
  "commit_id": "a",
  "event":
    "APPROVE"
}
' > "$STUB/ev-split.json"
runr "carries an APPROVE event" "gh api repos/o/r/pulls/12/reviews --input $STUB/ev-split.json"   # split across lines
run ALLOW "gh api -X POST repos/o/r/issues/5/comments -F body=@$STUB/review.md"   # an issue comment from a file named review: no review target
run ALLOW "gh api repos/o/r/pulls/12/reviews --paginate --jq '.[].state'"
run ALLOW "gh api repos/o/r/pulls/12/comments --paginate"
run ALLOW "echo 'gh pr review 12 --approve'"                             # prose
run ALLOW "gh pr view 12 --json reviews"
# ... behind a first word the guard does not read as gh, the words alone decide
runr "behind a command the guard does not read" '$r = gh pr review 12 --approve'   # a PowerShell assignment
run BLOCK '$x = gh api repos/o/r/pulls/12/reviews -f event=APPROVE'
run BLOCK 'sh -c "gh pr review 12 --approve"'                          # an interpreter
run BLOCK 'pwsh -c "gh pr review 12 -a"'
run BLOCK '& "C:\Program Files\GitHub CLI\gh.exe" pr review 12 -a'     # a quoted full-path gh.exe
run BLOCK 'sh -c "gh api repos/o/r/pulls/12/reviews --input p.json"'   # a review payload the guard cannot locate
run BLOCK 'r=$(gh pr review 12 --approve)'                             # an assignment's substitution
run ALLOW 'sh -c "gh pr review 12 -b approve"'                         # -b takes the value
run ALLOW 'sh -c "gh pr review 12 --approve=false -c -b x"'
run ALLOW 'sh -c "gh api repos/o/r/pulls/12/comments --paginate"'      # no review target
# ... whatever heads the segment, approval words beside a substitution or a background & refuse
runr "another command may run it" 'echo "$(gh pr review 12 --approve)"'   # a prose word first
run BLOCK 'echo `gh pr review 12 --approve`'
run BLOCK 'git status & gh pr review 12 --approve'                     # git first
run BLOCK 'cat x & gh api repos/o/r/pulls/12/reviews -f event=APPROVE'
run BLOCK 'gh pr view 12 & gh pr review 12 --approve'                  # a second gh behind &
runr "behind xargs" 'echo --approve | xargs gh pr review 12'           # xargs appends the flag
run BLOCK 'printf 12 | xargs -I{} gh pr review {} -a'
run ALLOW 'echo "$(gh pr view 12 --json reviews)"'                     # a substitution naming no approval
run ALLOW 'git status & gh pr view 12'
run ALLOW 'bash .github/gh-as-bot.sh reply 12 5 /tmp/b.md'              # the wrapper's own calls pass
run ALLOW 'bash .github/gh-as-bot.sh comment 12 /tmp/b.md'
run ALLOW 'bash .github/gh-as-bot.sh resolve 12 PRRT_x'
run ALLOW 'bash .github/gh-as-bot.sh pr-create workflow/1 "t" /tmp/b.md'
TOOL=PowerShell
runr "under PowerShell" "gh api repos/o/r/pulls/12/reviews --input $STUB/comment.json"   # a /-rooted payload names another file to gh.exe
TOOL=Bash

echo
[ "$fail" = 0 ] && echo "ALL CASES PASSED" || echo "SOME CASES FAILED"
exit $fail
