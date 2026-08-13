# Changelog

All notable changes to darnlang are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [0.4.0] — 2026-08-13

### Fixed
- **`--baseline-file` had no containment check.** It is the one place a caller can point at another
  project's numbers, so it is the one place the single-root derivation cannot help — and the
  ancestor's guard for it was deleted along with the file it lived in. Measured before restoring it:
  pointing at a foreign baseline of 1242 produced *"OK — and it went DOWN (0 < 1242). Lock the win
  in with `darnlang update-baseline`"*, and that suggested command then overwrote the real 1242 with
  a zero. Word for word the failure this tool was extracted to make impossible.

  Now exit 3, with `DARNLANG_ALLOW_FOREIGN_BASELINE=1` to say you mean it — refusing with no way to
  override is how a guard gets deleted a second time. Two tests, including that the other project's
  file is left untouched.

### Note for consumers wiring this in CI
Resolve the tool in its **own step** (`uv tool install`), not inside the judging call. `uvx` exits
**1** when it cannot resolve a ref — offline, moved tag, network policy — which is indistinguishable
from *"found something"*. On an issue-labelling workflow that difference is a public accusation
against a stranger whose only mistake was arriving while the runner could not reach a git tag.
`examples/lang-issue.yml` and `examples/Jenkinsfile` do it the safe way.

## [0.3.0] — 2026-08-13

Everything here comes from two adversarial reviews that were told to break the tool rather than
confirm it. They found **four false GREENs**, three of them in `scan_diff` — the function the shipped
pre-commit hook runs, and the only public function in the package with **zero tests**. A mutation
that made it judge just the first added line per file left the whole suite green.

### Fixed — the false greens

- **A file whose NAME is not ASCII was invisible to `--diff`.** git renders such a path as an escaped
  C string, so the `+++ b/…` header did not match and every added line in that file was skipped.
  `_files` had learned this; `scan_diff` had not. The file most likely to be *named* in the wrong
  language is the file most likely to contain it.
- **A diff that could not be read reported "OK — nothing new", exit 0.** The tree path invented
  `NothingToScan` for exactly this; the diff path had not applied the doctrine — in the one place
  the pre-commit hook runs. Now exit 3.
- **Content that looks like a diff header hijacked the parser.** A line reading `++ b/vendor/x.txt`
  inside a document is emitted as `+++ b/…` in the diff; treating it as a header redirected every
  following line to a file that was not being edited, and dropped them. Any repo documenting a patch
  format carries this, and it is attacker-reachable in a pull request.
- **An unreadable or undecodable file was skipped in total silence.** `NothingToScan`'s twin: the
  file list was not empty, but the element failed to open. The profile that hits it — legacy files in
  latin-1 — is exactly the profile the ratchet exists for, so the silence would have written a floor
  of 0 over real debt. They are now counted and named.
- **One unbalanced — or merely inline — fence blinded the rest of a document.** ```` ```x``` is the
  marker ```` is ordinary Markdown, and toggling on it hid everything after. Fence state is now
  resolved over the whole file, and an unclosed fence closes nothing.

### Fixed — the ratchet

- **`update-baseline` had no coverage guard**, so narrowing the scope silently baked the reduction
  in and wiped the per-file map — while `check` was loud about the identical narrowing. Now exit 2,
  with `--allow-narrower` to say you mean it.
- **The coverage message gave the same advice for a gain and a loss.** A reader who took "do not
  accept this without knowing why" seriously was told in the next sentence to run the command that
  accepts it.
- **Exit 2 was overloaded**: argparse returns 2 for a usage error, and 2 means "coverage changed,
  re-seed". A wrapper automating that would re-seed over a typo. Usage errors are 3.

### Removed

- **`check --strict`.** Measured against this repo's own tree — English by construction, baseline
  pinned at 0 — layer 3 produced **11 findings, at least 8 plainly English**, and reported them with
  "translate them". Not tunable: langdetect classifies a sentence, and a line of a document is a
  fragment. `prose --strict` stays, because there the unit is right — a message is judged as one
  text, which takes detection from ~76% to ~99.4% on 338 real commit subjects.
- `prose --strict` also now honours the scissors line, fences and `lang-ok`, which it ignored. With
  `commit.verbose` on, 40 lines of English diff diluted a Spanish subject past detection — and the
  shipped commit-msg hook is fed exactly that file.

### Testing

- **`scan_diff` has tests at all**, including every case above.
- Fence handling is tested through `scan_tree` rather than by passing `in_fence` in by hand.
- The **shrinking** direction of `coverage_changed` is tested — the direction the code calls "how a
  gate loosens without anyone noticing" was the one a refactor could delete for free.
- `langdetect` moved into the `dev` extra, because CI installed `.[dev]` and therefore **skipped
  every layer-3 test**: the feature 0.2.0 was released for was never exercised by the gate guarding
  merges. A second CI job installs without it, to cover the other half.

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
