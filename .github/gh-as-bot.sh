#!/usr/bin/env bash
# Run one call of a pull request's author side as the bot account (docs/adl/0055-*.md and
# docs/adl/0057-*.md). The author side -- opening a pull request, replying in one of its review
# threads, commenting on it, resolving one of its threads -- runs with the token of the
# profile's `identity.bot_login`; every other call stays plain `gh`, as its active account,
# the owner.
#
#   bash .github/gh-as-bot.sh pr-create <head-branch> <title> <body-file>
#   bash .github/gh-as-bot.sh reply     <pr> <comment-id> <body-file>
#   bash .github/gh-as-bot.sh comment   <pr> <body-file>
#   bash .github/gh-as-bot.sh resolve   <pr> <thread-id>
#
# A closed list. Any other subcommand, a malformed argument, or a body file that cannot be read
# refuses (exit 2) before a token is read; `comment` refuses a number that is not a pull
# request, and `resolve` a thread that is not that pull request's, before posting. Each call
# prints its read-back on stdout: the pull request's URL, the reply's or comment's id, or the
# thread's isResolved. A pull request always bases `main` (contribution-workflow.md's **Base
# `main` and stacking**).
#
# Every call is REST but the resolve, which has no REST form; opening a pull request goes
# straight to REST, the fallback docs/reference/method/tracker-mechanics.md gives `gh pr
# create`. Bodies are read by gh from the file (`-F body=@<path>`), never passed inline.
#
# The repository and the bot's login come from .claude/profile.yml through profile-env.sh (a
# PROFILE in the environment is honoured, for the test suite). Its own tests:
#   bash .github/test-gh-as-bot.sh
#
# Exit 0 done; 2 refused; gh's own status when a gh call fails.

set -euo pipefail

refuse() { echo "gh-as-bot: $*" >&2; exit 2; }

usage="usage: gh-as-bot.sh pr-create <head-branch> <title> <body-file> | reply <pr> <comment-id> <body-file> | comment <pr> <body-file> | resolve <pr> <thread-id>"

is_number() { [[ $1 =~ ^[1-9][0-9]*$ ]]; }
readable() { [ "$1" != - ] && [ -f "$1" ] && [ -r "$1" ]; }

[ $# -ge 1 ] || refuse "$usage"
sub=$1
shift
case "$sub" in
  pr-create)
    [ $# -eq 3 ] || refuse "$usage"
    head=$1 title=$2 body=$3
    [[ $head =~ ^[A-Za-z0-9._/-]+$ && $head != -* ]] || refuse "head branch '$head' is not a plain branch name"
    [ -n "$title" ] || refuse "an empty title"
    readable "$body" || refuse "body file '$body' cannot be read"
    ;;
  reply)
    [ $# -eq 3 ] || refuse "$usage"
    pr=$1 comment_id=$2 body=$3
    is_number "$pr" || refuse "pull request '$pr' is not a number"
    is_number "$comment_id" || refuse "comment id '$comment_id' is not a number"
    readable "$body" || refuse "body file '$body' cannot be read"
    ;;
  comment)
    [ $# -eq 2 ] || refuse "$usage"
    pr=$1 body=$2
    is_number "$pr" || refuse "pull request '$pr' is not a number"
    readable "$body" || refuse "body file '$body' cannot be read"
    ;;
  resolve)
    [ $# -eq 2 ] || refuse "$usage"
    pr=$1 thread=$2
    is_number "$pr" || refuse "pull request '$pr' is not a number"
    [[ $thread =~ ^PRRT_[A-Za-z0-9_-]+$ ]] || refuse "thread id '$thread' is not a review thread's node id"
    ;;
  *) refuse "'$sub' is not an author-side call; $usage" ;;
esac

env_out=$(bash "$(dirname "$0")/profile-env.sh") || refuse "profile-env.sh could not read the profile"
eval "$env_out"
[ -n "${REPO:-}" ] || refuse "the profile names no repo"
[ -n "${BOT_LOGIN:-}" ] || refuse "the profile names no identity.bot_login, so there is no bot account to run as"

token=$(gh auth token --user "$BOT_LOGIN" 2>/dev/null) || token=''
[ -n "$token" ] || refuse "gh holds no login for '$BOT_LOGIN' (gh auth login, then gh auth status)"
export GH_TOKEN="$token"

case "$sub" in
  pr-create)
    gh api -X POST "repos/$REPO/pulls" -f title="$title" -f head="$head" -f base=main \
      -F body=@"$body" --jq '.html_url'
    ;;
  reply)
    gh api -X POST "repos/$REPO/pulls/$pr/comments/$comment_id/replies" -F body=@"$body" --jq '.id'
    ;;
  comment)
    # The comments endpoint serves an issue number too; read the pull request first so an
    # issue number refuses instead of posting there.
    got=$(gh api "repos/$REPO/pulls/$pr" --jq '.number' 2>/dev/null) || got=''
    [ "$got" = "$pr" ] || refuse "#$pr is not a pull request of $REPO"
    gh api -X POST "repos/$REPO/issues/$pr/comments" -F body=@"$body" --jq '.id'
    ;;
  resolve)
    owner_of=$(gh api graphql -f id="$thread" \
      -f query='query($id: ID!) { node(id: $id) { ... on PullRequestReviewThread { pullRequest { number repository { nameWithOwner } } } } }' \
      --jq '.data.node.pullRequest | "\(.repository.nameWithOwner) \(.number)"' 2>/dev/null) || owner_of=''
    [ "$owner_of" = "$REPO $pr" ] || refuse "thread $thread is not a review thread of $REPO#$pr"
    gh api graphql -f id="$thread" \
      -f query='mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }' \
      --jq '.data.resolveReviewThread.thread.isResolved'
    ;;
esac
