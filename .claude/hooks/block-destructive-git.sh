#!/bin/sh
# PreToolUse guard on the shell tools (Bash, PowerShell): refuse the destructive git commands that
# docs/reference/method/contribution-workflow.md's "Commit & push authorization" section
# excludes from the project's standing commit/push authorization, and refuse a
# `gh pr merge` outside the auto-merge rule the same section states.
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
# does parse is the heredoc: the body of a quoted-delimiter heredoc (`<<'EOF'`,
# `<<"EOF"`, `<<\EOF`, and their `<<-` forms) is inert to the shell that reads it --
# quoting the delimiter disables every expansion -- so it is blanked out before the
# scan, which would otherwise read a documentation line beginning `git clean -f` as a
# command position. Quoting says nothing about what the *consumer* of the body does
# with it, so blanking has carve-outs, all spelled out at strip_heredoc_bodies below:
# an unquoted delimiter and any heredoc handed to an interpreter keep their body in
# the scan, an opener that is itself inside quotes opens nothing, and that quote scan
# is single-line and comment-blind.
# Conversely, only a segment whose *first* word is git or gh is inspected, so prose that
# merely mentions a blocked command (`gh pr comment --body "... git reset --hard ..."`)
# runs untouched -- as long as that prose carries no shell separator, since the split on
# ; && || | happens first and a mention after one starts a segment of its own. A lone &
# is not treated as a separator either. The guard runs commands of its own -- a
# `git rev-parse` in a directory taken from the command text -- to decide the rebase
# rule, and `gh pr view` plus `gh pr checks` to decide the merge rule below. The block
# list is the one the workflow doc enumerates, so same-family commands it does not name
# (`git checkout -f`, `git switch --discard-changes`, `git push origin :branch`) are
# deliberately left alone rather than overlooked. Anyone determined to force-push can
# still do it; the point is that nobody does it by reflex.
#
# The merge rule. `gh pr merge` is allowed only when every condition holds: `--squash`;
# the pull request's head is a branch of this repository, not a fork's; it carries
# `needs-approval` and not `needs-decision`; every changed file sits under one of the
# auto-merge trees .claude/profile.yml lists (`autopilot.auto_merge_trees`); and every
# check on it is green -- every check, not only branch protection's required ones,
# since the merge runs with `--admin`, which bypasses those. Unlike the git rules this
# one fails CLOSED: a `gh` that cannot be run, answers nothing, or lists fewer files
# than the pull request has, refuses the merge with the reason, because the rule cannot
# be shown to hold. The facts come from `gh` as the account running the session, so
# they are as current as its answer and no more; the merge itself is the human's
# `--admin` merge. What is not checked here -- a mixed-tree change waits for the human,
# the lane limit, the merge method gh applies -- is the workflow document's.
#
# Its own test suite lives next to it: sh .claude/hooks/test-block-destructive-git.sh

DOC='docs/reference/method/contribution-workflow.md, section "Commit & push authorization"'
# The profile the merge rule reads its trees from. Overridable for the test suite only,
# the same way .github/profile-env.sh takes it.
PROFILE=${PROFILE:-$(dirname "$0")/../profile.yml}

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
  # Fail open, but not silently: a payload that carries a shell tool_input and still
  # yields no command means this guard has stopped understanding its own input.
  case "$payload" in
    *'"tool_name"'*'"Bash"'* | *'"tool_name"'*'"PowerShell"'*)
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

deny() { # deny <segment> <reason> [closing paragraph]
  tail=${3:-"This command is destructive or rewrites published history, so it falls outside the
standing commit/push authorization granted in $DOC.
Ask the human partner to run it, or choose a non-destructive alternative."}
  message="BLOCKED by .claude/hooks/block-destructive-git.sh: $1

Reason: $2

$tail"

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

# --- the merge rule: `gh pr merge` outside the auto-merge conditions is refused ---

MERGE_TAIL="A merge outside the auto-merge rule is the human partner's, at their gate; the rule
and its conditions are in $DOC.
Fix the failing condition, or leave the merge to them."

deny_merge() { deny "$1" "$2" "$MERGE_TAIL"; }

# The auto-merge trees, one per line, from the profile's `autopilot.auto_merge_trees`
# list. Read with awk rather than a YAML parser (none is guaranteed here), so the key
# has to keep the plain block-list shape the profile gives it.
auto_merge_trees() {
  awk '
    /^[^ \t#]/ { top = ($0 ~ /^autopilot:/); list = 0 }
    top && /^  auto_merge_trees:/ { list = 1; next }
    top && list && /^    - / { t = $0; sub(/^    - */, "", t); sub(/[ \t]+(#.*)?$/, "", t); gsub(/["'"'"']/, "", t); if (t != "") print t; next }
    top && list && /^  [^ ]/ { list = 0 }
  ' "$PROFILE" 2>/dev/null
}

gh_merge_rule() { # gh_merge_rule <segment> <arguments after gh>
  seg=$1
  shift
  # Only `gh pr merge` is the merge; any other gh command, `gh pr merge --help` included,
  # merges nothing and is left alone.
  [ "${1:-}" = pr ] || return 0
  shift
  [ "${1:-}" = merge ] || return 0
  shift
  selector=''
  gh_repo=''
  squash=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --help | -h) return 0 ;;
      --squash) squash=1 ;;
      --repo=*) gh_repo=${1#--repo=} ;;
      -R | --repo) shift; gh_repo=${1:-} ;;
      # Flags that take a value: skip it so a value is never read as a selector or flag.
      -b | --body | -t | --subject | -F | --body-file | -A | --author-email | --match-head-commit) shift ;;
      --*) ;;
      # gh (cobra) clusters short flags: `-sd` is `--squash --delete-branch`.
      -?*) case "$1" in *s*) squash=1 ;; esac ;;
      *) [ -n "$selector" ] || selector=$1 ;;
    esac
    [ $# -gt 0 ] && shift
  done
  [ "$squash" = 1 ] ||
    deny_merge "$seg" "'gh pr merge' without --squash: every merge in this project is a squash"

  trees=$(auto_merge_trees)
  [ -n "$trees" ] ||
    deny_merge "$seg" "$PROFILE lists no auto-merge trees under autopilot.auto_merge_trees, so no tree is auto-mergeable"

  # The selector is forwarded as typed (a number, a URL or a branch; none means the
  # branch checked out in the payload's cwd), so the guard reads the pull request the
  # merge would act on. The template keeps the answer to one fact per line, which sh
  # can read without a JSON parser.
  # shellcheck disable=SC2086  # $selector and $gh_repo are single words, deliberately unquoted when empty
  facts=$(cd "$cwd" 2>/dev/null && gh pr view ${selector:+"$selector"} ${gh_repo:+-R "$gh_repo"} \
    --json isCrossRepository,changedFiles,files,labels \
    --template '{{"cross="}}{{.isCrossRepository}}{{"\n"}}{{"count="}}{{.changedFiles}}{{"\n"}}{{range .files}}{{"file="}}{{.path}}{{"\n"}}{{end}}{{range .labels}}{{"label="}}{{.name}}{{"\n"}}{{end}}' 2>/dev/null | tr -d '\r')
  case "$facts" in
    cross=true*) deny_merge "$seg" "the pull request's head is a branch of another repository (a fork), which never auto-merges" ;;
    cross=false*) ;;
    *) deny_merge "$seg" "'gh pr view' could not read the pull request's head, files and labels, so the auto-merge conditions cannot be shown to hold" ;;
  esac

  count=''
  nfiles=0
  outside=''
  approval=0
  decision=0
  IFS='
'
  for line in $facts; do
    case "$line" in
      count=*) count=${line#count=} ;;
      label=needs-approval) approval=1 ;;
      label=needs-decision) decision=1 ;;
      file=*)
        f=${line#file=}
        nfiles=$((nfiles + 1))
        inside=0
        for tree in $trees; do
          case "$f" in "$tree"*) inside=1 ;; esac
        done
        [ "$inside" = 1 ] || outside=$f
        ;;
    esac
  done
  unset IFS

  [ "$approval" = 1 ] ||
    deny_merge "$seg" "the pull request does not carry needs-approval: no review pass has found it clean"
  [ "$decision" = 0 ] ||
    deny_merge "$seg" "the pull request carries needs-decision: a reason not to merge is still open"
  [ "$nfiles" -gt 0 ] ||
    deny_merge "$seg" "the pull request lists no changed files, so nothing shows every one is under an auto-merge tree"
  case "$count" in
    *[!0-9]* | '') deny_merge "$seg" "'gh pr view' gave no readable changed-file count, so the file list cannot be known to be complete" ;;
  esac
  [ "$count" -le "$nfiles" ] ||
    deny_merge "$seg" "'gh pr view' listed $nfiles of the pull request's $count changed files, so not every one can be checked against the auto-merge trees"
  [ -z "$outside" ] ||
    deny_merge "$seg" "$outside is outside the auto-merge trees the profile lists, so this merge is the human's"

  # `gh pr checks` reports one line per check name, the most recent run of each, with
  # gh's own bucket: pass, fail, pending, skipping or cancel. Every check counts, not
  # only the required ones. A skipped check is a job the change did not reach (a
  # path-filtered test job on a docs change), not a red one.
  # shellcheck disable=SC2086
  checks=$(cd "$cwd" 2>/dev/null && gh pr checks ${selector:+"$selector"} ${gh_repo:+-R "$gh_repo"} \
    --json name,bucket --template '{{range .}}{{"check="}}{{.bucket}}{{" "}}{{.name}}{{"\n"}}{{end}}' 2>/dev/null | tr -d '\r')
  [ -n "$checks" ] ||
    deny_merge "$seg" "'gh pr checks' reported no checks on the pull request, so none is known to be green"
  IFS='
'
  for line in $checks; do
    case "$line" in
      check=pass\ * | check=skipping\ *) ;;
      check=*)
        state=${line#check=}
        name=${state#* }
        state=${state%% *}
        deny_merge "$seg" "check '$name' is $state, not green -- every check on the pull request has to be"
        ;;
      *) deny_merge "$seg" "'gh pr checks' gave an unreadable answer ($line), so no check is known to be green" ;;
    esac
  done
  unset IFS
  return 0
}

# Blank out the body of every quoted-delimiter heredoc (`<<'EOF'`, `<<"EOF"`, `<<\EOF`,
# and their `<<-` forms). Bodies are blanked rather than deleted, so every line that
# remains is still the command position it was. Deliberately narrow, so that it fails
# closed:
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
#
# The quote scan behind the third rule reads one line at a time and knows nothing about
# `#` comments or bash's `$'...'`, so an opener inside a quoted string that *opened on an
# earlier line* still reads as an opener. That is the residual fail-open here, and it is
# the same shape the header already concedes for `bash -c`: contrived to reach, and no
# harder to reach deliberately than the wrappers this guard never claimed to see.
strip_heredoc_bodies() {
  printf '%s\n' "$1" | awk '
    BEGIN {
      q = sprintf("%c", 39)  # a single quote, unwritable inside this quoted program
      # A delimiter is quoted (inert body), backslash-quoted, or a bare word. The bare
      # word arm also matches non-delimiters such as the `<< 2` of an arithmetic shift;
      # that is harmless because a bare word is never marked inert, so it can only cause
      # less to be blanked, never more.
      opener = "<<-?[ \t]*(\"[^\"]*\"|" q "[^" q "]*" q "|\\\\?[A-Za-z0-9_.-]+)"
      sep = "[ \t;|&()<>\"" q "]+"
      ni = split("sh bash dash ash ksh zsh busybox ssh su sudo docker podman eval source", s, " ")
      for (x = 1; x <= ni; x++) interpreter[s[x]] = 1
    }

    # Is position _p of line _s inside a quoted string? Parameters are prefixed so they
    # cannot shadow the globals the END rule walks with.
    function inquote(_s, _p,   _x, _c, _st) {
      _st = 0
      for (_x = 1; _x < _p; _x++) {
        _c = substr(_s, _x, 1)
        if (_st == 0) {
          if (_c == "\\") _x++
          else if (_c == q) _st = 1
          else if (_c == "\"") _st = 2
        } else if (_st == 1) {
          if (_c == q) _st = 0  # sh has no escapes inside single quotes
        } else {
          if (_c == "\\") _x++
          else if (_c == "\"") _st = 0
        }
      }
      return _st != 0
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

stripped=$(strip_heredoc_bodies "$cmd")
# An awk that chokes on the program above would yield nothing, and an empty command
# would sail through the scan below with every segment gone. Keep the unstripped text
# in that case: false positives on heredoc prose are the price, denial is preserved.
[ -n "$stripped" ] && cmd=$stripped

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

  # Only a segment that *invokes* git or gh is inspected, and only as its first word
  # (after environment assignments and transparent wrappers). Scanning deeper would
  # deny any command that merely quotes a git command in its text.
  found=''
  wrapper=0
  while [ $# -gt 0 ]; do
    tok=$1
    tok=${tok#'$('}
    tok=${tok#'`'}
    tok=${tok#'('}
    case "$tok" in
      git | git.exe | */git | */git.exe) found=git; shift; break ;;
      gh | gh.exe | */gh | */gh.exe) found=gh; shift; break ;;
      sudo | env | command | exec | nohup | nice | time | xargs) wrapper=1; shift ;;
      *=*) shift ;;
      # Once a wrapper is in play its own options and operands (`sudo -u x`,
      # `nice -n 10`, `xargs -I{}`) sit between it and git, so keep walking.
      *) [ "$wrapper" = 1 ] || break; shift ;;
    esac
  done
  [ -n "$found" ] || continue
  if [ "$found" = gh ]; then
    gh_merge_rule "$seg" "$@"
    continue
  fi

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
        deny "$seg" "this branch is already pushed, so rebasing it rewrites published history; the review step of the workflow lets you 'git merge origin/main' instead"
      fi
      ;;
  esac
done

exit 0
