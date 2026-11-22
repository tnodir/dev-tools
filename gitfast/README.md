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

## Tests

```sh
bash test_fold_into.sh                     # in a temporary repository
python test_gitfast.py [range]             # on the current repository's history (HEAD~400..HEAD)
```
