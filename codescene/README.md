# codescene

Local checks of C/C++ code by CodeScene's Code Health rules, before committing: `cc-check.py`
reports the functions and files exceeding the thresholds, as CodeScene measures them (its docstring
describes how each one is counted). Based on [lizard](https://github.com/terryyin/lizard):
`pip install lizard`.

```sh
python cc-check.py --changed                # the .c/.cpp/.h files changed vs HEAD
python cc-check.py --changed --if-braces    # and the braces of their changed if's bodies
python cc-check.py src/a.cpp src/b.c        # given files
```

- Run it from the repository's root: the changed files' paths are relative to it.
- The rules: Complex Method, Excess Number of Function Arguments, Complex Conditional, Bumpy Road,
  Large Method, Lines of Code in a Single File, Duplicated Function Blocks. The options `-C`, `-A`,
  `-L`, `-B`, `-M`, `-F` set the allowed maxima (by default CodeScene's: 8, 4, 1, 1, 69, 999).
- A function's issue disabled by CodeScene's directive in a `//` comment right above it
  (`// @CodeScene(disable:"Excess Number of Function Arguments")`, `@CodeScene(disable-all)`) isn't
  listed, only counted in the summary.
- It checks whole files, so a changed file's old issues are listed too.
- The exit code is 1 when any issue is found.

## check-if-braces.py

A code style's convention, not CodeScene's rule: an `if` whose body isn't a simple jump has braces.
Simple jumps may stay without them: `continue;`, `break;`, `goto`, `return;`, a return of a constant
(`TRUE`/`FALSE`/`true`/`false`/`NULL`/`nullptr`/`{}`/a number/an ALL_CAPS name/a qualified enum) or
of a plain local variable. It checks the added lines only:

```sh
python check-if-braces.py            # the branch's: <the default branch>...HEAD
python check-if-braces.py HEAD       # the uncommitted changes and the untracked files
```

The default branch is `origin/HEAD`'s, else `master`. `cc-check.py --changed --if-braces` runs it
with `HEAD`.

## The thresholds' sources

CodeScene's defaults per language are the JSON files of the zip linked from helpcenter.codescene.com
"What Are the Default Threshold Values for Different Programming Languages?"
(`https://codescene.com/hubfs/Technical%20Support%20Data/default-rules.zip`,
`code-health-rules.cpp.json`); the `_warning` thresholds are reached by the value itself. Whether
70 and 1000 lines themselves are reported is not verified. The duplicates' criteria (lizard's
`nloc` ≥ 10, `difflib`'s ratio of the generalized tokens ≥ 0.96, the identifiers' Jaccard index
≥ 0.4) were fitted on 30 pairs of CodeScene's reports for Fort Firewall's sources, which they
reproduce exactly.
