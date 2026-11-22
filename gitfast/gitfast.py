"""Git's objects for the history-rewriting scripts, by a few processes instead of one per file or
commit (a process costs ~50-100 ms on Windows):

- Blobs: the objects by one `git cat-file --batch` process;
- commits(): the range's commits with their metadata and changed files by one `git log`;
- Snapshot: a commit's files in memory (read lazily by Blobs, edited by the script);
- FastImport: the new commits by one `git fast-import` stream;
- move_branch(): the branch moved by `git update-ref`, checking its old tip.

Nothing touches the working tree or the index. The repository is the `repo` argument, else
`GITFAST_REPO`, else the current directory at the import.

    import sys
    sys.path.insert(0, r'<the folder of gitfast.py>')
    import gitfast as gf
"""
import os
import subprocess
import sys
from dataclasses import dataclass, field

REPO = os.environ.get('GITFAST_REPO') or os.getcwd()

# fast-import's commits go to this ref, deleted after the run
TMP_REF = 'refs/gitfast/tmp'


def fail(msg):
    print('FAIL:', msg)
    sys.exit(1)


def git(*args, input=None, env=None, text=True, repo=None):
    """The command's stdout (str, stripped of the trailing newline; bytes if not text); fails on
    an error"""
    if isinstance(input, str):
        input = input.encode('utf-8')
    r = subprocess.run(['git', *args], cwd=repo or REPO, input=input, env=env,
                       capture_output=True)
    if r.returncode != 0:
        fail('git %s: %s' % (' '.join(args[:3]), r.stderr.decode('utf-8', 'replace').strip()))
    return r.stdout.decode('utf-8').rstrip('\n') if text else r.stdout


def try_git(*args, repo=None):
    """The command's stdout, None on an error"""
    r = subprocess.run(['git', *args], cwd=repo or REPO, capture_output=True)
    return r.stdout.decode('utf-8').rstrip('\n') if r.returncode == 0 else None


def rev(spec, repo=None):
    """The full hash of a commit"""
    sha = try_git('rev-parse', '--verify', '-q', spec + '^{commit}', repo=repo)
    if not sha:
        fail('no commit %s' % spec)
    return sha


def to_bytes(data):
    return data.encode('utf-8') if isinstance(data, str) else data


class Blobs:
    """The objects by '<rev>:<path>' or a hash from one `git cat-file --batch` process, cached"""

    def __init__(self, repo=None, cache=True):
        self.proc = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=repo or REPO,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.cache = {} if cache else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if self.proc.poll() is None:
            self.proc.stdin.close()
            self.proc.wait()

    def obj(self, spec):
        """(type, data) of the object, or (None, None) if missing"""
        if self.cache is not None and spec in self.cache:
            return self.cache[spec]
        if '\n' in spec:
            fail('a newline in the object name: %r' % spec)
        self.proc.stdin.write(spec.encode('utf-8') + b'\n')
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().split()
        if not header:
            fail('git cat-file --batch has exited')
        if len(header) != 3:  # '<spec> missing' or '<spec> ambiguous'
            result = (None, None)
        else:
            data = self.proc.stdout.read(int(header[2]))
            self.proc.stdout.read(1)  # the LF after the contents
            result = (header[1].decode(), data)
        if self.cache is not None:
            self.cache[spec] = result
        return result

    def data(self, rev, path=None):
        """The blob's bytes ('<rev>:<path>' or a hash), None if missing or not a blob"""
        kind, data = self.obj('%s:%s' % (rev, path) if path is not None else rev)
        return data if kind == 'blob' else None

    def text(self, rev, path=None):
        """The blob's text, None if missing or not a blob"""
        data = self.data(rev, path)
        return data.decode('utf-8') if data is not None else None


@dataclass
class Change:
    """A file's change in a commit, of `git log --raw`: status 'A', 'M', 'D' or 'T'; the new mode
    and blob hash (of zeros when deleted)"""
    status: str
    mode: str
    sha: str
    path: str

    @property
    def deleted(self):
        return self.status == 'D'


@dataclass
class Commit:
    """A commit's metadata: author and committer as 'Name <email> <time> <tz>' (fast-import's raw
    format), the message as is"""
    sha: str
    parents: list
    author: str
    committer: str
    message: str
    changes: list = field(default_factory=list)

    @property
    def subject(self):
        return self.message.split('\n', 1)[0]

    @property
    def paths(self):
        return [ch.path for ch in self.changes]

    def update_paths(self, paths):
        """Applies the commit's additions and deletions to the set of the parent's paths"""
        for ch in self.changes:
            if ch.deleted:
                paths.discard(ch.path)
            else:
                paths.add(ch.path)
        return paths


def commits(rng, *paths, repo=None, merges=False):
    """The range's commits, oldest first, by one `git log` (`paths` limit the commits and their
    changes). A merge's changes aren't listed: it fails unless merges=True."""
    out = git('log', '--reverse', '--topo-order', '--no-renames', '--raw', '--no-abbrev', '-z',
              '--date=raw',
              '--format=%x01%H%x00%P%x00%an <%ae> %ad%x00%cn <%ce> %cd%x00%B%x02',
              rng, '--', *paths, text=False, repo=repo).decode('utf-8')
    result = []
    for chunk in out.split('\x01')[1:]:
        head, _, raw = chunk.partition('\x02')
        sha, parents, author, committer, message = head.split('\x00', 4)
        c = Commit(sha, parents.split(), author, committer, message)
        if len(c.parents) > 1 and not merges:
            fail('a merge in %s: %s' % (rng, sha))
        items = [s for s in raw.split('\x00') if s.strip('\n')]
        for meta, path in zip(items[::2], items[1::2]):
            _, mode, _, blob, status = meta.strip('\n').lstrip(':').split(' ')
            c.changes.append(Change(status, mode, blob, path))
        result.append(c)
    return result


def ls_tree(rev, *paths, repo=None):
    """The commit's file paths by one `git ls-tree`"""
    out = git('ls-tree', '-r', '-z', '--name-only', rev, '--', *paths, repo=repo)
    return set(p for p in out.split('\x00') if p)


def identity(repo=None):
    """The current committer as 'Name <email> <time> <tz>'"""
    return git('var', 'GIT_COMMITTER_IDENT', repo=repo)


class Snapshot:
    """A commit's files in memory: read lazily by Blobs, edited by the script. The edits are
    `edits` (path -> bytes, None if removed); `paths` (if given, the commit's paths: see
    Commit.update_paths()) serve find()."""

    def __init__(self, blobs, rev, paths=None):
        self.blobs = blobs
        self.rev = rev
        self.paths = paths
        self.edits = {}

    def data(self, path):
        if path in self.edits:
            return self.edits[path]
        return self.blobs.data(self.rev, path)

    def exists(self, path):
        return self.data(path) is not None

    def read(self, path):
        data = self.data(path)
        if data is None:
            fail('%s: no %s' % (self.rev[:9], path))
        return data.decode('utf-8')

    def write(self, path, data):
        self.edits[path] = to_bytes(data)

    def remove(self, path):
        if not self.exists(path):
            fail('%s: no %s to remove' % (self.rev[:9], path))
        self.edits[path] = None

    def sub(self, path, old, new, count=1):
        """Replaces the text, which must occur `count` times"""
        text = self.read(path)
        if text.count(old) != count:
            fail('%s: %s: %d of %r' % (self.rev[:9], path, text.count(old), old))
        self.write(path, text.replace(old, new))

    def find(self, prefix='', suffix=''):
        """The existing paths by the prefix and suffix, sorted"""
        if self.paths is None:
            self.paths = ls_tree(self.rev)
        names = set(self.paths) | set(self.edits)
        return sorted(p for p in names
                      if p.startswith(prefix) and p.endswith(suffix) and self.edits.get(p, 1))


class FastImport:
    """The new commits by one `git fast-import` stream, each on the previous one (the first on
    `base`). A commit lists its changed files only: `files` maps a path to
    - bytes or str: the contents (mode 100644);
    - (mode, bytes or str): the contents with the mode;
    - a Change: as in its commit (its blob by the hash, or deleted);
    - None: deleted."""

    def __init__(self, base, repo=None):
        self.repo = repo
        self.base = rev(base, repo) if base else None
        self.stream = []
        self.marks = 0
        self.committer = None

    def commit(self, message, author, committer=None, files=None, parent=None):
        """Adds a commit; returns its mark (':<n>'). `committer` defaults to the current one now,
        `parent` to the previous commit (or base)."""
        if committer is None:
            committer = self.committer = self.committer or identity(self.repo)
        if parent is None:
            parent = ':%d' % self.marks if self.marks else self.base
        self.marks += 1
        msg = to_bytes(message)
        s = self.stream
        s += [b'commit %s\n' % TMP_REF.encode(), b'mark :%d\n' % self.marks,
              b'author %s\n' % author.encode('utf-8'),
              b'committer %s\n' % committer.encode('utf-8'),
              b'data %d\n' % len(msg), msg, b'\n']
        if parent:
            s.append(b'from %s\n' % parent.encode())
        for path, value in (files or {}).items():
            self.file(path, value)
        s.append(b'\n')
        return ':%d' % self.marks

    def file(self, path, value):
        p = path.encode('utf-8')
        if b'\n' in p or p.startswith(b'"'):
            fail('a path to quote: %r' % path)
        if isinstance(value, Change):
            if value.deleted:
                self.stream.append(b'D %s\n' % p)
            else:
                self.stream.append(b'M %s %s %s\n' % (value.mode.encode(), value.sha.encode(), p))
            return
        if value is None:
            self.stream.append(b'D %s\n' % p)
            return
        mode, data = value if isinstance(value, tuple) else ('100644', value)
        data = to_bytes(data)
        self.stream += [b'M %s inline %s\n' % (mode.encode(), p), b'data %d\n' % len(data), data,
                        b'\n']

    def run(self):
        """Writes the objects; returns the commits' hashes by their order. No ref is left: move a
        branch by move_branch()."""
        if not self.marks:
            fail('no commits')
        marks_file = git('rev-parse', '--git-path', 'gitfast.marks', repo=self.repo)
        marks_path = os.path.join(self.repo or REPO, marks_file)
        if try_git('rev-parse', '--verify', '-q', TMP_REF, repo=self.repo):
            fail('%s exists: another run?' % TMP_REF)
        try:
            git('fast-import', '--quiet', '--date-format=raw', '--export-marks=' + marks_path,
                input=b''.join(self.stream), text=False, repo=self.repo)
            git('update-ref', '-d', TMP_REF, repo=self.repo)
            with open(marks_path, encoding='ascii') as f:
                marks = dict(line.split() for line in f if line.strip())
        finally:
            if os.path.exists(marks_path):
                os.remove(marks_path)
        return [marks[':%d' % n] for n in range(1, self.marks + 1)]


def tree(rev, repo=None):
    return git('rev-parse', rev + '^{tree}', repo=repo)


def move_branch(branch, new, old, repo=None, same_tree=False):
    """Moves the branch from `old` (fails if it has moved meanwhile) to `new`. The checked-out
    branch only to a commit of the same tree (the working tree and the index stay as they are)."""
    ref = 'refs/heads/' + branch
    head = try_git('symbolic-ref', '-q', 'HEAD', repo=repo)
    if (same_tree or head == ref) and tree(new, repo) != tree(old, repo):
        fail('%s: the tree of %s differs from %s' % (branch, new[:9], old[:9]))
    git('update-ref', '-m', 'gitfast', ref, rev(new, repo), rev(old, repo), repo=repo)
