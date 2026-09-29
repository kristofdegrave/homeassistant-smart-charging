#!/bin/sh
# PreToolUse guard on the file tools (Edit, Write, NotebookEdit): refuse an edit that lands in
# the repository's main checkout while it is on main. Every unit of work is edited in its own
# task worktree -- docs/reference/method/contribution-workflow.md, "The chain", step 1 -- and a
# session or background agent that edits the main checkout instead leaves its change on
# nobody's branch.
#
# Contract, the same as block-destructive-git.sh beside it: reads the PreToolUse payload on
# stdin; exit 0 with no output allows the call. A denial writes the PreToolUse "deny" decision
# to stdout *and* the same explanation to stderr, then exits 2. A deny rather than an ask,
# because a background agent cannot answer a prompt. POSIX sh only, and no jq -- neither is
# guaranteed on the machines this runs on.
#
# The rule. The path is tool_input.notebook_path for NotebookEdit, tool_input.file_path for
# the other two. A relative path is taken against the payload's cwd; a Windows drive path
# (`D:\...` or `D:/...`) is turned into the shell's form with cygpath where one is on PATH, and
# every backslash is read as a separator. The nearest existing directory at or above the path
# is asked, with git, whether it lies inside a working tree, and if so whether that tree is the
# repository's main worktree (--git-dir and --git-common-dir resolve to the same directory) and
# its current branch is main. All three -> deny, an ignored file (`.claude/settings.local.json`)
# as much as a tracked one. So a path outside any git tree (the scratchpad, the memory
# directory), a linked worktree, the main checkout on any other branch or a detached HEAD, and a
# path inside a .git directory are all allowed.
#
# Fails OPEN, as the git rules of block-destructive-git.sh do: this is an accident guard, not a
# sandbox, and a guard that cannot decide must not stall every edit. A payload with no tool name,
# one that names a guarded tool but yields no path, no git on PATH, or a git that fails for any
# reason but "not a git repository" (`detected dubious ownership`, a corrupt repository) allows
# the call -- with a note on stderr, so the guard is not silently gone. Only the answers git
# gives on a readable repository, and "not a git repository", allow without one.
#
# Known gap, accepted: a write through the shell tools (`sed -i`, a heredoc, a redirection,
# `git checkout -- <path>`) never reaches this hook, and nothing here tries to cover it. A
# submodule checkout reads as a main worktree of its own repository, so one on main is refused.
#
# Its own test suite lives next to it: sh .claude/hooks/test-block-main-checkout-edits.sh

SELF=.claude/hooks/block-main-checkout-edits.sh
DOC='docs/reference/method/contribution-workflow.md, section "The chain", step 1 (Implement)'

payload=$(cat)

# Decode a string field out of the JSON payload without jq -- the same decoder as
# block-destructive-git.sh's: find the key, then walk the string body honouring escapes.
# The first match wins, and an escaped key inside a string value (\"file_path\") cannot match.
extract() {
  printf '%s' "$payload" | awk -v key="$1" '
    { buf = buf $0 "\n" }
    END {
      pat = "\"" key "\"[ \t]*:[ \t]*\""
      if (match(buf, pat) == 0) exit
      i = RSTART + RLENGTH
      out = ""
      while (i <= length(buf)) {
        c = substr(buf, i, 1)
        if (c == "\\") {
          e = substr(buf, i + 1, 1)
          if (e == "n") out = out "\n"
          else if (e == "t") out = out "\t"
          else if (e == "r") out = out ""
          else if (e == "u") { out = out " "; i += 4 }
          else out = out e
          i += 2
          continue
        }
        if (c == "\"") break
        out = out c
        i++
      }
      printf "%s", out
    }'
}

note_open() { # note_open <why> -- allow the call, saying why it went unchecked
  echo "$SELF: $1; allowing the ${tool:-tool} call unchecked" >&2
  exit 0
}

tool=$(extract tool_name)
case "$tool" in
  Edit | Write) path=$(extract file_path) ;;
  NotebookEdit) path=$(extract notebook_path) ;;
  # The matcher sends only the three tools above, so an empty name is the decoder failing.
  '') note_open "could not read tool_name from the payload" ;;
  *) exit 0 ;; # a tool this guard does not cover
esac
[ -n "$path" ] || note_open "could not read the path from the $tool payload"

# A Windows drive path, in either slash, into the shell's own form (`/d/...` under Git Bash).
# Backslashes become slashes first, so cygpath and the dirname walk below see one separator.
to_shell_path() {
  _p=$(printf '%s' "$1" | tr '\\' '/')
  case "$_p" in
    [A-Za-z]:/* | [A-Za-z]:)
      if command -v cygpath >/dev/null 2>&1; then
        _p=$(cygpath -u "$_p")
      fi ;;
  esac
  printf '%s' "$_p"
}

shown=$path
path=$(to_shell_path "$path")
case "$path" in
  /* | [A-Za-z]:/*) ;;
  *)
    cwd=$(extract cwd)
    [ -n "$cwd" ] || cwd=$(pwd)
    path=$(to_shell_path "$cwd")/$path ;;
esac

# The file itself may not exist yet (Write creates it, and its directories), so ask git from
# the nearest directory that does. The walk never ends on `.`, which would ask about the
# hook's own cwd instead: a drive path left unconverted (no cygpath) walks down to `D:` and
# then `.`, and nothing existing on the way means the path is in no working tree.
dir=$(dirname "$path")
while [ ! -d "$dir" ]; do
  up=$(dirname "$dir")
  { [ "$up" = "$dir" ] || [ "$up" = . ]; } && exit 0
  dir=$up
done

command -v git >/dev/null 2>&1 || note_open "no git on PATH"
errfile=$(mktemp 2>/dev/null) || note_open "could not make a temp file for git's errors"
trap 'rm -f "$errfile"' EXIT

# Ask git; on failure, allow silently only for "not a git repository" -- a parsed answer, the
# path is in no working tree -- and with a note for anything else.
ask() { # ask <git args...> -- sets $answer, or exits
  answer=$(git -C "$dir" "$@" 2>"$errfile") && return 0
  err=$(tr '\n' ' ' <"$errfile")
  case "$err" in *'not a git repository'*) exit 0 ;; esac
  note_open "git $1 failed in $dir (${err% })"
}

ask rev-parse --is-inside-work-tree
[ "$answer" = true ] || exit 0 # inside a .git directory

# Both directories resolved by cd, not by --path-format=absolute (git 2.31+, and an older
# rev-parse echoes the unknown option back as if it were an answer). Either may be relative.
ask rev-parse --git-dir --git-common-dir
git_dir=$(printf '%s\n' "$answer" | sed -n 1p)
common_dir=$(printf '%s\n' "$answer" | sed -n 2p)
resolve() { (cd "$dir" 2>/dev/null && cd "$1" 2>/dev/null && pwd -P); }
[ -n "$git_dir" ] && [ -n "$common_dir" ] &&
  git_dir=$(resolve "$git_dir") && common_dir=$(resolve "$common_dir") &&
  [ -n "$git_dir" ] && [ -n "$common_dir" ] ||
  note_open "git named no git directories that exist for $dir"
[ "$git_dir" = "$common_dir" ] || exit 0 # a linked worktree

# symbolic-ref -q exits 1, silently, on a detached HEAD; anything else is a failure.
if ! branch=$(git -C "$dir" symbolic-ref --short -q HEAD 2>"$errfile"); then
  [ -s "$errfile" ] || exit 0 # a detached HEAD
  note_open "git symbolic-ref failed in $dir ($(tr '\n' ' ' <"$errfile"))"
fi
[ "$branch" = main ] || exit 0 # another branch

top=$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null)

json_escape() {
  printf '%s' "$1" |
    tr '\011' ' ' |
    tr -d '\000-\010\013\014\016-\037' |
    sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' |
    awk 'NR > 1 { printf "\\n" } { printf "%s", $0 }'
}

message="BLOCKED by $SELF: $tool $shown

Reason: this path is in the repository's main checkout, $top, which is on main.
Every unit of work is edited in its own task worktree, never in the main checkout
($DOC).

Make the edit in the task's own worktree, on its branch, instead; if there is none yet,
create it as that step says."

printf '%s\n' "$message" >&2
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$(json_escape "$message")"
exit 2
