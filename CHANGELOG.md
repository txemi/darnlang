# Changelog

All notable changes to darnlang are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-08-13

First release. Extracted from a script that had been vendored, byte for byte, into four repositories
— which is the reason the tool exists rather than a footnote about it: a bug found in one copy was
fixed in one copy, and the same blind spot stayed open in the other three for months.

### The surfaces

- **`darnlang prose`** judges free text: a commit message, an issue, a PR title and body. No file
  linter can see those, they are the most public thing a project has, and an indexed PR title cannot
  be retracted. Measured on the repository this came from, with its file gate green: 2 of 2 open
  issues, 4 PR titles, 7 PR descriptions and 7 commit subjects in the wrong language.
- **`darnlang check`** judges tracked files, with a rule **per file family** — comments only in
  code, everything but fenced blocks in documents. An ancestor applied the code rule to every file,
  and that rule rejects any line carrying `:` or `(`, so most written prose was invisible to it.
- **File NAMES** are judged too. No ancestor did that, and a name is exactly as public as the file.

### The ratchet

- Legacy debt lives in a baseline whose count may only decrease; a clean repo pins it at 0, which is
  fail-closed with no extra machinery.
- The baseline records **what it counted** (`scanned_exts`). Widening coverage is then reported as
  an **adoption** — re-seed once — instead of as "the count grew, do not raise the baseline", which
  is advice that is exactly backwards. It still fails, and it names the direction, so coverage going
  *down* cannot hide in the same message.

### The path resolution, which is why extraction was worth doing at all

One root, two derived values: the tree scanned and the baseline both come from the git repo root, so
they cannot drift. The vendored ancestor resolved them independently against `__file__`; when only
one was later fixed, the gate read a real baseline of 1242 lines, compared it against a count from a
different tree, concluded the debt had gone *down*, exited 0 with congratulations, and suggested the
command that overwrites the baseline with the wrong number. The result was also arbitrary — it
depended on what sat next to the installed file.

### Detection

Three layers: accented characters, a curated wordlist of function words, and `langdetect` behind the
optional `strict` extra. The default path has **no runtime dependencies**, which is what lets it run
first in a pre-commit hook and what stops it becoming a silent no-op on an unprovisioned machine.
`no`, `total`, `final`, `sin` and `solo` are deliberately absent from the wordlist: every removal
followed a measured false positive on ordinary English.

### Wiring

`.pre-commit-hooks.yaml` (added lines, commit message, whole tree), a composite GitHub Action for
files + commit messages + PR text, and `examples/lang-issue.yml` for issues — which **cannot** block
and does not pretend to.
