"""Tests gitfast.py on the history of the current directory's repository (or GITFAST_REPO's), its
current branch (writes no refs but the temporary branch gf-test):
- commits(): the metadata and messages equal the raw commit objects;
- FastImport: the commits rebuilt from their changes (by the blobs' hashes and inline) get the
  same hashes;
- move_branch(): its checks of the old tip and the trees.

  python <the folder>/test_gitfast.py [range]    -- by default HEAD~400..HEAD
"""
import contextlib
import io
import subprocess
import sys

import gitfast as gf

RANGE = sys.argv[1] if len(sys.argv) > 1 else 'HEAD~400..HEAD'


def check(name, ok):
    print('%-50s %s' % (name, 'ok' if ok else 'FAILED'))
    return ok


def test_commits(commits, blobs):
    bad = 0
    for c in commits:
        raw = blobs.obj(c.sha)[1].decode('utf-8')
        head, msg = raw.split('\n\n', 1)
        h = dict(line.split(' ', 1) for line in head.splitlines() if not line.startswith(' '))
        if (msg, h['author'], h['committer'], h.get('parent', '')) \
                != (c.message, c.author, c.committer, (c.parents or [''])[0]):
            bad += 1
            print('  mismatch:', c.sha[:9])
    return check('commits(): %d commits as the raw objects' % len(commits), not bad)


def test_rebuild(commits, blobs):
    fi = gf.FastImport(commits[0].parents[0])
    for i, c in enumerate(commits):
        # Every other commit by the inline contents, with their modes
        files = {ch.path: ch if (ch.deleted or i % 2) else (ch.mode, blobs.data(ch.sha))
                 for ch in c.changes}
        fi.commit(c.message, c.author, c.committer, files)
    shas = fi.run()
    same = sum(1 for c, sha in zip(commits, shas) if c.sha == sha)
    ok = same == len(commits) and gf.try_git('show-ref', gf.TMP_REF) is None
    return check('FastImport: %d of %d hashes the same, no ref left' % (same, len(commits)), ok)


def try_move(*args, **kw):
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            gf.move_branch(*args, **kw)
        return True
    except SystemExit:
        return False


def test_move(commits):
    a, b = commits[-2].sha, commits[-1].sha
    subprocess.run(['git', 'branch', '-f', 'gf-test', a], cwd=gf.REPO, check=True)
    try:
        ok = check('move_branch(): moves', try_move('gf-test', b, a) and gf.rev('gf-test') == b)
        ok &= check('move_branch(): not from a stale tip',
                    not try_move('gf-test', a, a) and gf.rev('gf-test') == b)
        ok &= check('move_branch(): same_tree', not try_move('gf-test', a, b, same_tree=True))
    finally:
        subprocess.run(['git', 'branch', '-D', '-q', 'gf-test'], cwd=gf.REPO, check=True)
    head = gf.try_git('symbolic-ref', '-q', '--short', 'HEAD')
    if head:
        # The old tip is wrong too: if the check failed, update-ref wouldn't move it
        ok &= check('move_branch(): not the checked-out one to another tree',
                    not try_move(head, a, 'HEAD~1') and gf.rev('HEAD') == gf.rev(head))
    return ok


def main():
    commits = gf.commits(RANGE)
    with gf.Blobs() as blobs:
        ok = test_commits(commits, blobs)
        ok &= test_rebuild(commits, blobs)
    ok &= test_move(commits)
    sys.exit(0 if ok else 1)


main()
