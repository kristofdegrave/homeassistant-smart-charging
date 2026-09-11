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
# in another shell (`bash -c "git push --force"`) is not seen. The one construct it
# does parse is the heredoc: the body of a *quoted*-delimiter heredoc (`<<'EOF'`,
# `<<"EOF"`) is inert text -- no expansion can run inside it -- so it is blanked out
# before the scan, which would otherwise read a documentation line beginning `git
# clean -f` as a command position. An *unquoted* delimiter (`<<EOF`) leaves `$(...)`
# live inside the body, so that body is still scanned and such prose is still denied.
# Conversely, only a segment whose *first* word is git is inspected, so prose that
# merely mentions a blocked command (`gh pr comment --body "... git reset --hard ..."`)
# runs untouched -- as long as that prose carries no shell separator, since the split on
# ; && || | happens first and a mention after one starts a segment of its own. A lone &
# is not treated as a separator either. The guard runs one command of its own -- a
# `git rev-parse` in a directory taken from the command text -- to decide the rebase
# rule. The block list is the one the workflow doc enumerates, so same-family commands
# it does not name (`git checkout -f`, `git switch --discard-changes`,
# `git push origin :branch`) are deliberately left alone rather than overlooked.
# Anyone determined to force-push can still do it; the point is that nobody does it by
# reflex.
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

# Blank out the body of every quoted-delimiter heredoc (`<<'EOF'`, `<<"EOF"`, `<<\EOF`,
# and their `<<-` forms), keeping the line count so the lines that remain are still real
# command positions. Deliberately narrow, so that it fails closed:
#   - an unquoted delimiter (`<<EOF`) keeps expansions live in the body, so that body is
#     left in place and scanned -- and is tracked separately when it shares an opener
#     line with a quoted one, so only the quoted heredoc's own lines are blanked;
#   - no line is blanked until every heredoc opened on that line has been terminated, so
#     an opener with no terminator blanks nothing;
#   - an opener that sits inside quotes on its own line (`echo "see <<'EOF' below"`) is
#     prose, not a redirection, and opens nothing -- otherwise a later line that happens
#     to equal the delimiter would swallow everything up to it;
#   - the opener line itself is kept, so `cat <<'EOF' && git clean -f` still denies;
#   - a heredoc fed to a shell (`sh <<'EOF'`, `cat <<'EOF' | bash`, `ssh host <<'EOF'`)
#     really does execute its body, so an opener line naming an interpreter keeps its
#     body in the scan.
strip_heredoc_bodies() {
  printf '%s\n' "$1" | awk '
    BEGIN {
      q = sprintf("%c", 39)  # a single quote, unwritable inside this quoted program
      # A delimiter is quoted (inert body), backslash-quoted, or a bare word.
      opener = "<<-?[ \t]*(\"[^\"]*\"|" q "[^" q "]*" q "|\\\\?[A-Za-z0-9_.-]+)"
      sep = "[ \t;|&()<>\"" q "]+"
      ni = split("sh bash dash ash ksh zsh busybox ssh su sudo docker podman eval source", s, " ")
      for (x = 1; x <= ni; x++) interpreter[s[x]] = 1
    }

    # Is position p of line s inside a quoted string?
    function inquote(s, p,   x, c, st) {
      st = 0
      for (x = 1; x < p; x++) {
        c = substr(s, x, 1)
        if (st == 0) {
          if (c == "\\") x++
          else if (c == q) st = 1
          else if (c == "\"") st = 2
        } else if (st == 1) {
          if (c == q) st = 0
        } else {
          if (c == "\\") x++
          else if (c == "\"") st = 0
        }
      }
      return st != 0
    }

    { line[NR] = $0 }
    END {
      n = NR
      for (i = 1; i <= n; i++) out[i] = line[i]
      i = 1
      while (i <= n) {
        seg = line[i]
        cnt = 0
        pos = 1
        # One line can open several heredocs (`cmd <<"A" <<B`); they are terminated in
        # the order they were opened, so all of them are tracked and only the inert
        # ones are blanked.
        while (pos <= length(seg) && match(substr(seg, pos), opener)) {
          abs = pos + RSTART - 1
          len = RLENGTH
          # A herestring (`<<<`) is not a heredoc, and neither is a `<<` inside quotes.
          if ((abs > 1 && substr(seg, abs - 1, 1) == "<") || inquote(seg, abs)) {
            pos = abs + 1
            continue
          }
          tok = substr(seg, abs, len)
          pos = abs + len
          cnt++
          tabbed[cnt] = (tok ~ /^<<-/)  # `<<-` strips leading tabs from the terminator
          sub(/^<<-?[ \t]*/, "", tok)
          c1 = substr(tok, 1, 1)
          if (c1 == q || c1 == "\"") {
            inert[cnt] = 1
            delim[cnt] = substr(tok, 2, length(tok) - 2)
          } else if (c1 == "\\") {
            inert[cnt] = 1
            delim[cnt] = substr(tok, 2)
          } else {
            inert[cnt] = 0
            delim[cnt] = tok
          }
        }
        if (cnt == 0) { i++; continue }
        # A body handed to an interpreter is code, not data, however it is quoted.
        nw = split(seg, w, sep)
        for (x = 1; x <= nw; x++) {
          v = w[x]
          sub(/^.*\//, "", v)
          if (v in interpreter) { cnt = 0; break }
        }
        if (cnt == 0) { i++; continue }
        j = i + 1
        k = 1
        while (k <= cnt && j <= n) {
          t = line[j]
          if (tabbed[k]) sub(/^\t+/, "", t)  # `<<-` strips tabs only, never spaces
          if (t == delim[k]) {
            bstart[k] = (k == 1) ? i + 1 : bend[k - 1] + 1
            bend[k] = j
            k++
          }
          j++
        }
        if (k > cnt) {
          for (k = 1; k <= cnt; k++) {
            if (!inert[k]) continue
            for (m = bstart[k]; m <= bend[k]; m++) out[m] = ""
          }
          i = bend[cnt] + 1
        } else {
          i++  # never terminated: not a heredoc after all, so blank nothing
        }
      }
      for (i = 1; i <= n; i++) print out[i]
    }'
}

cmd=$(strip_heredoc_bodies "$cmd")

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
  wrapper=0
  while [ $# -gt 0 ]; do
    tok=$1
    tok=${tok#'$('}
    tok=${tok#'`'}
    tok=${tok#'('}
    case "$tok" in
      git | git.exe | */git | */git.exe) found=1; shift; break ;;
      sudo | env | command | exec | nohup | nice | time | xargs) wrapper=1; shift ;;
      *=*) shift ;;
      # Once a wrapper is in play its own options and operands (`sudo -u x`,
      # `nice -n 10`, `xargs -I{}`) sit between it and git, so keep walking.
      *) [ "$wrapper" = 1 ] || break; shift ;;
    esac
  done
  [ "$found" = 1 ] || continue

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
  [ -n "$sub" ] || continue

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
      # -D, or delete and force in any mix of spellings. --fo is ambiguous with
      # --format, so --forc is the shortest form of --force here.
      if has_short_flag D "$@" ||
        { { has_short_flag d "$@" || has_long '--d*' "$@"; } &&
          { has_short_flag f "$@" || has_long '--forc*' "$@"; }; }; then
        deny "$seg" "'git branch -D' force-deletes a branch whose commits may not be merged anywhere"
      fi
      ;;
    checkout | restore)
      # Whole-tree discards only. 'git restore --staged .' merely unstages, so it is
      # left alone unless the working tree is in scope too.
      if has_exact . "$@" || has_exact ./ "$@" || has_exact :/ "$@"; then
        if [ "$sub" = restore ] && has_long '--sta*' "$@" && ! has_long '--w*' "$@"; then
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
      # A resume flag with no operand steers an existing rebase; other options
      # alongside it (--autostash and friends) do not change that.
      resume=0
      operand=0
      for t in "$@"; do
        case "$t" in
          --abort | --continue | --skip | --quit | --edit-todo | --show-current-patch) resume=1 ;;
          -*) ;;
          *) operand=1 ;;
        esac
      done
      control=0
      [ "$resume" = 1 ] && [ "$operand" = 0 ] && control=1
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
done

exit 0
