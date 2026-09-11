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
          else if (e == "r") out = out "\n"
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
[ -n "$cmd" ] || exit 0

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

# Split the command line on shell separators so a guarded command hidden behind
# && / || / ; / | / newline is still inspected.
segments=$(printf '%s\n' "$cmd" | sed -e 's/&&/\
/g' -e 's/||/\
/g' -e 's/[;|]/\
/g')

has_word() {
  # $padded holds " tok tok tok " for the current segment
  case "$padded" in *" $1 "*) return 0 ;; esac
  return 1
}

has_short_flag() {
  # true when a single-dash (non "--") token carries that letter
  for _t in $rest_tokens; do
    case "$_t" in
      --*) ;;
      -*) case "$_t" in *"$1"*) return 0 ;; esac ;;
    esac
  done
  return 1
}

oldIFS=$IFS
IFS='
'
for seg in $segments; do
  IFS=$oldIFS

  set -f
  # shellcheck disable=SC2086
  set -- $seg
  set +f

  # Find the git invocation in this segment (skipping env assignments, sudo, ...).
  found=0
  while [ $# -gt 0 ]; do
    case "$1" in
      git | git.exe | */git | */git.exe) found=1; shift; break ;;
    esac
    shift
  done
  [ "$found" = 1 ] || { IFS='
'; continue; }

  # Skip git's own global options to reach the subcommand.
  sub=''
  while [ $# -gt 0 ]; do
    case "$1" in
      -C | -c | --git-dir | --work-tree | --namespace | --exec-path)
        shift
        [ $# -gt 0 ] && shift
        ;;
      -*) shift ;;
      *) sub=$1; shift; break ;;
    esac
  done
  [ -n "$sub" ] || { IFS='
'; continue; }

  rest_tokens=$*
  padded=" $* "

  case "$sub" in
    push)
      if has_word --force || has_word --force-with-lease || has_word --force-if-includes; then
        deny "$seg" "force-push rewrites history that other clones and open PRs depend on"
      fi
      case "$padded" in
        *" --force-with-lease="* | *" --force-if-includes="*)
          deny "$seg" "force-push rewrites history that other clones and open PRs depend on" ;;
      esac
      if has_short_flag f; then
        deny "$seg" "'git push -f' is a force-push; it rewrites published history"
      fi
      for t in $rest_tokens; do
        case "$t" in
          +*:*) deny "$seg" "a leading '+' on a refspec is a force-push in disguise" ;;
        esac
      done
      ;;
    reset)
      if has_word --hard; then
        deny "$seg" "'git reset --hard' discards uncommitted work irrecoverably"
      fi
      ;;
    clean)
      if has_word --force || has_short_flag f; then
        deny "$seg" "'git clean -f' deletes untracked files irrecoverably"
      fi
      ;;
    branch)
      if has_short_flag D || { has_word --delete && has_word --force; }; then
        deny "$seg" "'git branch -D' force-deletes a branch whose commits may not be merged anywhere"
      fi
      ;;
    checkout | restore)
      if has_word . || has_word ./ || has_word :/; then
        deny "$seg" "discarding the whole working tree throws away uncommitted work; name the specific files instead"
      fi
      ;;
    stash)
      case "$1" in
        drop | clear)
          deny "$seg" "'git stash $1' destroys stashed work that has no other copy" ;;
      esac
      ;;
    rebase)
      # In-progress control flags are an escape hatch, not a new rewrite.
      control=1
      [ -n "$rest_tokens" ] || control=0
      for t in $rest_tokens; do
        case "$t" in
          --abort | --continue | --skip | --quit | --edit-todo | --show-current-patch) ;;
          *) control=0 ;;
        esac
      done
      if [ "$control" = 0 ] &&
        git -C "$cwd" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' >/dev/null 2>&1; then
        deny "$seg" "this branch is already pushed, so rebasing it rewrites published history"
      fi
      ;;
  esac

  IFS='
'
done
IFS=$oldIFS

exit 0
