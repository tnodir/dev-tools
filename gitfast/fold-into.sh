#!/bin/bash
# Usage: [MSG_FILE=<file>] fold-into.sh <target commit> [paths...] — folds the working tree's
# changes of the paths (relative to the repository's root; by default the repository's
# `git config fold.path` values, one per path; staged ones too) into the target commit and
# re-applies the later commits. It writes objects only: the working tree, the other paths' index
# entries and the files' times stay; the branch moves only if the new tip's tree matches.
# FOLD_REPO selects another work tree (default: the current directory's).
set -uo pipefail

fail() { echo "FAIL: $*"; exit 1; }

cd "${FOLD_REPO:-.}" || exit 1
top=$(git rev-parse --show-toplevel) || fail "not a work tree"
cd "$top" || exit 1

[ $# -ge 1 ] || fail "usage: fold-into.sh <target commit> [paths...]"
target=$(git rev-parse --verify -q "$1^{commit}") || fail "bad target"
branch=$(git symbolic-ref -q --short HEAD) || fail "no current branch"
old_tip=$(git rev-parse HEAD) || fail "HEAD"

# The branch may be rebased meanwhile: the target's old hash isn't in it
git merge-base --is-ancestor "$target" "$old_tip" || fail "target isn't in $branch"

paths=("${@:2}")
if [ ${#paths[@]} -eq 0 ]; then
    mapfile -t paths < <(git config --get-all fold.path)
    [ ${#paths[@]} -gt 0 ] || fail "no paths: pass them or set git config fold.path"
fi

idx=$(git rev-parse --git-path fold-into.index) || fail "git dir"
patch=$(git rev-parse --git-path fold-into.patch) || fail "git dir"
trap 'rm -f "$idx" "$patch"' EXIT

# The new tip's tree: HEAD + the paths' working files, by a copy of the index (its files' stat
# data spares hashing the unchanged ones) with the other paths reset to HEAD. The paths' entries
# stay: with core.filemode=false `git add` keeps their modes, staged ones too.
cp "$(git rev-parse --git-path index)" "$idx" || fail "copy index"
export GIT_INDEX_FILE=$idx
excludes=()
for p in "${paths[@]}"; do excludes+=(":(exclude,literal)$p"); done
git reset -q HEAD -- . "${excludes[@]}" || fail "reset the other paths"
git add -A -- "${paths[@]}" || fail add
tree=$(git write-tree) || fail "write-tree"
[ "$tree" != "$(git rev-parse "$old_tip^{tree}")" ] || fail "nothing to fold"

# The fold into the target's tree: a 3-way merge; on conflicts the -U1 patch applied directly
if ! new_tree=$(git merge-tree --write-tree --merge-base="$old_tip" "$target" "$tree" | head -1)
then
    echo "merge-tree conflicts: applying the -U1 patch"
    git diff --binary -U1 "$old_tip" "$tree" > "$patch" || fail diff
    git read-tree "$target" || fail "read-tree target"
    git apply --cached "$patch" || fail "apply patch"
    new_tree=$(git write-tree) || fail "write-tree target"
fi
unset GIT_INDEX_FILE

# The target's commit anew: its parents, author and message (or MSG_FILE's)
parents=()
for p in $(git rev-parse "$target^@"); do parents+=(-p "$p"); done
mapfile -t author < <(git log -1 --format='%an%n%ae%n%ad' "$target") || fail "author"
if [ -n "${MSG_FILE:-}" ]; then
    msg=$(cat "$MSG_FILE") || fail "MSG_FILE"
else
    msg=$(git cat-file commit "$target" | sed '1,/^$/d') || fail "message"
fi
new_target=$(printf '%s\n' "$msg" | GIT_AUTHOR_NAME=${author[0]} GIT_AUTHOR_EMAIL=${author[1]} \
    GIT_AUTHOR_DATE=${author[2]} git commit-tree "$new_tree" "${parents[@]}") || fail "commit-tree"

# The later commits re-applied in memory
new_tip=$new_target
if [ "$target" != "$old_tip" ]; then
    out=$(git replay --onto="$new_target" --ref="refs/heads/$branch" --ref-action=print \
        "$target..$old_tip") || fail "replay"
    new_tip=$(echo "$out" | awk -v ref="refs/heads/$branch" '$1 == "update" && $2 == ref { print $3 }')
    [ -n "$new_tip" ] || fail "replay output: $out"
fi

[ "$(git rev-parse "$new_tip^{tree}")" = "$tree" ] || fail "tree of $new_tip differs from $tree"

# Fails if the branch moved meanwhile
git update-ref -m "fold-into $1" "refs/heads/$branch" "$new_tip" "$old_tip" || fail "update-ref"

# The paths' index entries as the new HEAD, i.e. as the working files
git reset -q -- "${paths[@]}" || fail "reset the paths' index (the branch has moved)"

git log --oneline -1 "$new_target"
echo "OK $old_tip -> $new_tip"
