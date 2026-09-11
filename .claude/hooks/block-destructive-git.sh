#!/bin/sh
# PreToolUse(Bash) guard: refuse the destructive git commands that
# docs/reference/contribution-workflow.md's "Commit & push authorization" section
# excludes from the project's standing commit/push authorization.
#
# Contract: reads the PreToolUse payload on stdin; exit 0 with no output allows the
# call. A denial writes the PreToolUse "deny" decision to stdout *and* the same
# explanation to stderr, then exits 2 -- the two channels are redundant on purpose so
# the guard still bites on a Claude Code build that honours only one of them.
# POSIX sh only, and no jq -- neither is guaranteed on the machines this runs on.
#
# Scope and known limits. This is an accident guard, not a sandbox. It word-splits
# each command without understanding shell quoting, so a destructive command wrapped
# in another shell (`bash -c "git push --force"`) or in a heredoc body is not seen.
# Conversely, only a segment whose *first* word is git is inspected, so prose that
# merely mentions a blocked command (`gh pr comment --body "... git reset --hard ..."`)
# runs untouched. Anyone determined to force-push can still do it; the point is that
# nobody does it by reflex.
#
# Its own test suite lives next to it: sh .claude/hooks/test-block-destructive-git.sh

DOC='docs/reference/contribution-workflow.md, section "Commit & push authorization"'

payload=$(cat)

# Decode a string field out of the JSON payload without jq: find the key, then walk
# the string body honouring backslash escapes.
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

cmd=$(extract command)
if [ -z "$cmd" ]; then
  # Fail open, but not silently: a payload that carries a Bash tool_input and still
  # yields no command means this guard has stopped understanding its own input.
  case "$payload" in
    *'"tool_name"'*'"Bash"'*)
      echo "block-destructive-git.sh: could not read tool_input.command from the payload; allowing the call unchecked" >&2 ;;
  esac
  exit 0
fi

cwd=$(extract cwd)
[ -n "$cwd" ] || cwd=$(pwd)

json_escape() {
  printf '%s' "$1" |
    tr '\011' ' ' |
    tr -d '\000-\010\013\014\016-\037' |
    sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' |
    awk 'NR > 1 { printf "\\n" } { printf "%s", $0 }'
}

deny() {
  message="BLOCKED by .claude/hooks/block-destructive-git.sh: $1

Reason: $2

This command is destructive or rewrites published history, so it falls outside the
standing commit/push authorization granted in $DOC.
Ask the human partner to run it, or choose a non-destructive alternative."

  printf '%s\n' "$message" >&2
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$(json_escape "$message")"
  exit 2
}

# --- predicates over the subcommand's arguments, each called as `pred <needle> "$@"` ---

has_exact() { # an argument equal to the needle
  _n=$1
  shift
  for _t in "$@"; do
    [ "$_t" = "$_n" ] && return 0
  done
  return 1
}

has_long() { # an argument matching the glob (git accepts unambiguous abbreviations)
  _p=$1
  shift
  for _t in "$@"; do
    # shellcheck disable=SC2254  # the pattern is meant to glob
    case "$_t" in $_p) return 0 ;; esac
  done
  return 1
}

has_short_flag() { # a single-dash (non "--") argument carrying that letter
  _l=$1
  shift
  for _t in "$@"; do
    case "$_t" in
      --*) ;;
      -?*) case "$_t" in *"$_l"*) return 0 ;; esac ;;
    esac
  done
  return 1
}

# Split the command line on shell separators so a guarded command placed after
# && / || / ; / | / a newline is inspected in its own right.
segments=$(printf '%s\n' "$cmd" | sed -e 's/&&/\
/g' -e 's/||/\
/g' -e 's/[;|]/\
/g')

# Globbing stays off for the whole scan: segments are untrusted text, never paths.
set -f
IFS='
'
for seg in $segments; do
  # Unset rather than saved-and-restored: an IFS arriving unset from the environment
  # would restore as the empty string, which disables word splitting altogether and
  # would fail the guard open on every command.
  unset IFS
  # shellcheck disable=SC2086  # deliberate word splitting of the segment
  set -- $seg

  # Only a segment that *invokes* git is inspected, and only as its first word
  # (after environment assignments and transparent wrappers). Scanning deeper would
  # deny any command that merely quotes a git command in its text.
  found=0
  while [ $# -gt 0 ]; do
    tok=$1
    tok=${tok#'$('}
    tok=${tok#'`'}
    tok=${tok#'('}
    case "$tok" in
      sudo | env | command | exec | nohup | nice | time | xargs) shift; continue ;;
      git | git.exe | */git | */git.exe) found=1; shift; break ;;
      -*) break ;;
      *=*) shift; continue ;;
      *) break ;;
    esac
  done
  [ "$found" = 1 ] || { IFS='
'; continue; }

  # Skip git's own global options to reach the subcommand, remembering -C so the
  # rebase probe below can ask about the repository the command actually targets.
  sub=''
  repo=$cwd
  while [ $# -gt 0 ]; do
    case "$1" in
      -C)
        shift
        [ $# -gt 0 ] && { repo=$1; shift; }
        ;;
      -c | --git-dir | --work-tree | --namespace | --exec-path)
        shift
        [ $# -gt 0 ] && shift
        ;;
      -*) shift ;;
      *) sub=$1; shift; break ;;
    esac
  done
  [ -n "$sub" ] || { IFS='
'; continue; }

  case "$sub" in
    push)
      # --force, --force-with-lease[=...], --force-if-includes and every unambiguous
      # abbreviation of them all start "--force".
      if has_long '--force*' "$@" || has_short_flag f "$@"; then
        deny "$seg" "force-pushing rewrites history that other clones and the open PR depend on"
      fi
      if has_long '--mirror*' "$@"; then
        deny "$seg" "'git push --mirror' force-updates every ref on the remote"
      fi
      for t in "$@"; do
        case "$t" in
          +?*) deny "$seg" "a leading '+' on a refspec is a force-push in disguise" ;;
        esac
      done
      ;;
    reset)
      # --hard; --h alone is ambiguous with --help, so --ha is the shortest form.
      if has_long '--ha*' "$@"; then
        deny "$seg" "'git reset --hard' discards uncommitted work irrecoverably"
      fi
      ;;
    clean)
      # --force; no other git-clean long option starts with f.
      if has_long '--f*' "$@" || has_short_flag f "$@"; then
        deny "$seg" "'git clean -f' deletes untracked files irrecoverably"
      fi
      ;;
    branch)
      # -D, or --delete --force. --fo is ambiguous with --format, so --forc up.
      if has_short_flag D "$@" || { has_long '--d*' "$@" && has_long '--forc*' "$@"; }; then
        deny "$seg" "'git branch -D' force-deletes a branch whose commits may not be merged anywhere"
      fi
      ;;
    checkout | restore)
      # Whole-tree discards only. 'git restore --staged .' merely unstages, so it is
      # left alone unless the working tree is in scope too.
      if has_exact . "$@" || has_exact ./ "$@" || has_exact :/ "$@"; then
        if [ "$sub" = restore ] && has_long '--staged*' "$@" && ! has_long '--worktree*' "$@"; then
          : # unstaging the whole tree changes no file content
        else
          deny "$seg" "discarding the whole working tree throws away uncommitted work; name the specific files instead"
        fi
      fi
      ;;
    stash)
      case "$1" in
        drop | clear)
          deny "$seg" "'git stash $1' destroys stashed work that has no other copy" ;;
      esac
      ;;
    rebase)
      # Flags that only steer a rebase already in progress are an escape hatch, not a
      # new rewrite -- blocking them would strand the repository mid-rebase.
      control=1
      [ $# -gt 0 ] || control=0
      for t in "$@"; do
        case "$t" in
          --abort | --continue | --skip | --quit | --edit-todo | --show-current-patch) ;;
          *) control=0 ;;
        esac
      done
      # An upstream is the available proxy for "this branch is published". It is only
      # a proxy: a branch pushed without -u has none, and the probe can only look at
      # the payload's cwd (or an explicit -C), not at a directory an earlier segment
      # cd'd into.
      if [ "$control" = 0 ] &&
        git -C "$repo" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' >/dev/null 2>&1; then
        deny "$seg" "this branch is already pushed, so rebasing it rewrites published history; step 3 of the workflow lets you 'git merge origin/main' instead"
      fi
      ;;
  esac

  IFS='
'
done

exit 0
