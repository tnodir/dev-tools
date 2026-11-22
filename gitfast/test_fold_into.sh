#!/bin/bash
# Tests fold-into.sh in a temporary repository (removed at the end):
# - a fold into an earlier commit: the series' trees, author and messages, the working files' times;
# - the default paths by `git config fold.path`, and the failure without them;
# - MSG_FILE;
# - a change of a line a later commit introduced: fails, the branch stays.
#
#   bash <the folder>/test_fold_into.sh
set -u
FOLD="$(cd "$(dirname "$0")" && pwd)/fold-into.sh"
T=$(mktemp -d) || exit 1
trap 'rm -rf "$T"' EXIT
cd "$T" || exit 1

ok=1
check() { if eval "$2"; then echo "ok      $1"; else echo "FAILED  $1"; ok=0; fi; }
quiet() { "$@" >/dev/null 2>&1; }
fold() { bash "$FOLD" "$@" >/dev/null 2>&1; }
commit() {
    git add -A && GIT_AUTHOR_DATE="2000-01-0$1T00:00:00" git commit -qm "$2" -m "Body $1." || exit 1
}

git init -q -b main . && git config user.name Test && git config user.email test@example.com
mkdir -p src docs
printf 'a1\na2\na3\n' > src/a.txt; echo doc > docs/d.txt; commit 1 "A"
printf 'b1\n' > src/b.txt; commit 2 "B"
printf 'a1\na2\na3\na4\n' > src/a.txt; commit 3 "C"
tip=$(git rev-parse HEAD)

echo "=== a fold into A"
sed -i 's/^a1$/a1 folded/' src/a.txt
echo "unfolded" >> docs/d.txt
want=$(git -c core.safecrlf=false hash-object src/a.txt)
mtime=$(stat -c %Y src/a.txt)
check "fails without paths and fold.path" '! fold HEAD~2 && [ "$(git rev-parse HEAD)" = "$tip" ]'
git config --add fold.path src
check "folds by fold.path" 'fold HEAD~2'
check "the tip has the change" '[ "$(git rev-parse HEAD:src/a.txt)" = "$want" ]'
check "A has the change" '[ "$(git show HEAD~2:src/a.txt | head -1)" = "a1 folded" ]'
check "the messages and authors stay" \
    '[ "$(git log --format="%s|%b|%an|%ad" --date=short main)" = "$(git log --format="%s|%b|%an|%ad" --date=short $tip)" ]'
check "src is clean, docs still changed" \
    '[ -z "$(git status --short src)" ] && [ "$(git status --short docs)" = " M docs/d.txt" ]'
check "the file's time stays" '[ "$(stat -c %Y src/a.txt)" = "$mtime" ]'

echo "=== MSG_FILE"
echo "b2" >> src/b.txt
printf 'B renamed\n\nNew body.\n' > "$T/.git/msg.txt"
check "folds into B with the message" 'MSG_FILE="$T/.git/msg.txt" fold HEAD~1 src'
check "B's message" '[ "$(git log -1 --format=%B HEAD~1)" = "$(printf "B renamed\n\nNew body.")" ]'

echo "=== a staged mode with core.filemode=false"
git config core.filemode false
git update-index --chmod=+x src/b.txt docs/d.txt
check "folds into B" 'fold HEAD~1 src'
check "B and the tip have the mode" \
    '[ "$(git ls-tree HEAD~1 src/b.txt | cut -c1-6)" = 100755 ] && [ "$(git ls-tree HEAD src/b.txt | cut -c1-6)" = 100755 ]'
check "the other path's mode stays staged only" \
    '[ "$(git ls-tree HEAD docs/d.txt | cut -c1-6)" = 100644 ] && [ "$(git ls-files -s docs/d.txt | cut -c1-6)" = 100755 ]'
git update-index --chmod=-x docs/d.txt

echo "=== a line of a later commit"
tip=$(git rev-parse HEAD)
sed -i 's/^a4$/a4 changed/' src/a.txt
check "fails" '! fold HEAD~2 src'
check "the branch stays" '[ "$(git rev-parse HEAD)" = "$tip" ]'
check "the change stays in the working tree" 'grep -q "a4 changed" src/a.txt'
check "from a subfolder with FOLD_REPO" '(cd src && FOLD_REPO=.. fold HEAD src)'

[ $ok = 1 ] && echo "ALL OK" || { echo "SOME FAILED"; exit 1; }
