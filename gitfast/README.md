# gitfast

Helpers for rewriting Git history from scripts without a checkout and without a `git` process per
file or commit (a process costs ~50–100 ms on Windows). They write objects only: the working tree,
the index and the files' times stay, and a branch moves only after the new commits are checked.

Requires Git 2.44+ (`git replay`), Bash (Git Bash on Windows) and Python 3.7+.

## fold-into.sh

Folds the working tree's changes into an earlier commit of the current branch and re-applies the
later commits (a fixup without `rebase -i`):

```sh
bash fold-into.sh <target commit> [paths...]
MSG_FILE=msg.txt bash fold-into.sh <target commit> [paths...]   # also replaces its message
```

- The paths are relative to the repository's root; their staged and unstaged changes are folded,
  the other files' changes stay in the working tree and the index.
- Without paths it takes the repository's `fold.path` values (one per path):
  `git config --add fold.path src`.
- The repository is the current directory's, or `FOLD_REPO`'s.
- The change goes into the target's tree by a 3-way merge (`git merge-tree`), on conflicts by its
  `-U1` patch; a change of lines that a later commit introduced fails, the branch stays.

## gitfast.py

A Python module for the scripts rebuilding a commit series in memory:

- `Blobs`: the objects by one `git cat-file --batch` process;
- `commits(range)`: the commits with their authors, committers, messages and changed files by one
  `git log`;
- `Snapshot`: a commit's files in memory, edited by the script (`read()`, `write()`, `sub()`,
  `remove()`, `find()`);
- `FastImport`: the new commits by one `git fast-import` stream, returning their hashes;
- `move_branch(branch, new, old)`: moves the branch by `git update-ref`, checking its old tip; the
  checked-out branch only to a commit of the same tree.

```python
import sys
sys.path.insert(0, r'<the folder of gitfast.py>')
import gitfast as gf

commits = gf.commits('master..feature')
fi = gf.FastImport(commits[0].parents[0])
with gf.Blobs() as blobs:
    for c in commits:
        t = gf.Snapshot(blobs, c.sha)
        if t.exists('src/a.cpp'):
            t.sub('src/a.cpp', 'oldName', 'newName', t.read('src/a.cpp').count('oldName'))
        files = {ch.path: ch for ch in c.changes}
        files.update(t.edits)
        fi.commit(c.message, c.author, c.committer, files)
new = fi.run()
gf.move_branch('feature', new[-1], commits[-1].sha)
```

The repository is the `repo` argument, else `GITFAST_REPO`, else the current directory.

## How to adopt in a project

1. Find the project's scripts that rewrite history or read it file by file: `checkout`,
   `cherry-pick`, `rebase -i`, `reset --hard`, `branch -f`, or a `git` call per file or commit in a
   loop. Note what each one does, and which were one-off and may simply be deleted.
2. Replace them:
   - a fix folded into an earlier commit: `fold-into.sh`;
   - a commit series rebuilt with edits (renames, substitutions, files moved between commits): a
     script on `gitfast` (`commits()` → `Snapshot` per commit → `FastImport` → `move_branch()`);
   - a check reading files over a branch: `Blobs` and `commits()` instead of `git show` per file.

   Don't keep own copies of these helpers in the project: import `gitfast` from this folder.
3. Set the default paths of `fold-into.sh` (relative to the repository's root), e.g. the sources
   and the docs:

   ```sh
   git config --add fold.path src
   git config --add fold.path README.md
   ```

4. Check each rewritten script on a temporary branch or a clone, not on a working branch: its result
   must equal the old script's (the commits' trees, authors and messages), and a failing step must
   leave the branch where it was.
5. Update the project's docs and agent instructions that name the old scripts.

A custom series script checks every step (`|| fail` in Bash; `set -e` doesn't stop inside some
compound commands) and compares the new tip's tree with the expected one before moving the branch.

## Tests

```sh
bash test_fold_into.sh                     # in a temporary repository
python test_gitfast.py [range]             # on the current repository's history (HEAD~400..HEAD)
```
