# Changelog

All notable changes to darnlang are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-08-13

### Fixed
- **Layer 3 asked the wrong question.** It tested "is this Spanish"; it now tests **"is this not one
  of the accepted languages"** (default: English). Not pedantry — measured: `langdetect` labels the
  real commit subject *"migra el gate de idioma al paquete darnlang"* as **Catalan**, so the old
  question answered *no* and let it through. The new one answers *not English* and catches it. It
  also makes the tool useful to a project whose other language is not the one this was built for.
- **`--strict` without the extra installed used to warn and carry on**, which means a caller who
  asked for the deep layer, did not get it, and saw exit 0 was told the tree was clean by a check
  that never ran. It now exits **3**, the same code as any other "could not run".

### Added
- **`prose --strict`.** The cheap layers are weakest exactly where this tool matters most: a commit
  subject is short by nature, and a stopword list needs stopwords. Found by dogfooding — the commit
  that migrated the first repo onto darnlang was itself in the wrong language, passed the hook, and
  was caught only by adding this. The text is judged as one block rather than line by line, because
  a subject alone is often too short to classify.

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
