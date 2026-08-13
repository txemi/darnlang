# darnlang

**Keep a repository's prose in one language — including the parts a file linter can never see.**

Most "no foreign language in the codebase" checks look at source files. That leaves the surfaces
that are actually published unguarded: **commit messages, pull-request titles and descriptions, and
issues**. Measured on one public repository the day this tool was extracted — with its file gate
green and its tree at zero:

| Surface | In the wrong language | Was anything checking it? |
|---|---|---|
| `.py` comments | 0 | yes — the only one |
| `.md` documentation | 5, for two releases | no |
| commit subjects on `main` | 7 | no |
| PR titles | 4 | no |
| PR descriptions | 7 more | no |
| open issues | 2 of 2 | no |

Nobody had been careless seventeen times. There was simply nothing looking — and those surfaces are
the least retractable ones you have. An indexed pull-request title cannot be taken back.

## Install

**Not on PyPI yet**, so install from git and pin the tag:

```bash
# no install at all
uvx --from git+https://github.com/txemi/darnlang@v0.1.0 darnlang check

# or properly
pipx install git+https://github.com/txemi/darnlang@v0.1.0
pip install 'darnlang[strict] @ git+https://github.com/txemi/darnlang@v0.1.0'   # + deep layer
```

<sub>Once it is published the short forms — `uvx darnlang`, `pip install darnlang` — start working
and this section shrinks. They are written out in full here rather than promised, because a README
that documents an install command that does not work is the first thing a reader tries and the first
way a tool loses their trust.</sub>

Python 3.10+. **No runtime dependencies** in the default path — that is what lets it run first in a
pre-commit hook that fires dozens of times a day, and what stops it degrading into a silent no-op on
a machine nobody provisioned.

## Use

```bash
darnlang check                       # whole tree vs the baseline          (CI)
darnlang check --diff                # only the lines your commit ADDS     (pre-commit)
darnlang prose .git/COMMIT_EDITMSG --git-comments   # a commit message
darnlang prose - --label "PR title"  # anything, from stdin                (CI)
darnlang update-baseline             # record the new, lower count
```

Exit codes are part of the contract, because a caller has to tell *"there is debt"* from *"I could
not run"*: **0** clean · **1** findings · **2** coverage changed, re-seed · **3** usage or
environment error.

### The ratchet

A repo adopting the rule late already carries debt — the first one to run this had ~1300 offending
lines across 172 files. Demanding they all be fixed before the next commit just gets the gate
deleted. So legacy lines sit in a baseline whose count **may only decrease**, while new lines must
be clean from now on. A repo that starts clean pins its baseline at 0, which is fail-closed with no
extra machinery.

```bash
darnlang update-baseline    # writes .darnlang-baseline.json — commit it
```

### Scope

The default is `.py`. Widen it per repo, on your own schedule:

```bash
darnlang check --ext .py,.md,.html      # or DARNLANG_EXTS=.py,.md
darnlang check --ext all
```

The default is conservative for a measured reason: switching one documentation-heavy repo to `.md`
surfaced 820 lines at once on top of 1242 of existing debt. That is not a fix, it is an avalanche —
and an avalanche is how a gate ends up switched off. When you do widen, the tool says so in its own
words rather than reporting it as *"the count grew"*:

```
darnlang: COVERAGE CHANGED -- the baseline counted .py but this run judges .md, .py
  now also judged: .md  (current total: 820)

This is an ADOPTION, not a regression: re-seed once with `darnlang update-baseline`
and the number may only fall from there.
```

It still fails, because coverage that changes unnoticed is how a gate quietly loosens. And it names
the direction, so coverage going *down* can never hide inside the same message.

## What counts as prose

Two file families, two rules, because getting this wrong is the classic failure:

- **code** (`.py`) — only comments and docstrings are judged. Judging every line fires on
  identifiers.
- **doc** (`.md`, `.html`, `.rst`, `.txt`, templates, and anything unrecognised) — everything is
  judged **except** fenced code blocks, inline `` `code` `` spans and URLs.

Applying the code rule to a document is not a small miss: it rejects any line containing `:` or `(`,
which is most of a written paragraph. A sibling tool once opened `.html` to its scan but kept the
code rule, and the 320-line interface template that motivated the change stayed invisible.

**File names are judged too**, split on `_ - . /`. A file called `analisis_de_errores.py` is exactly
as public as its contents, and no tool this one descends from looked at names.

## Detection

Three layers, cheapest first:

1. **accented characters and inverted punctuation** — free, never wrong on its own;
2. **a wordlist of function words that are not also English words** — free; drop a
   `darnlang-words.txt` in the repo to replace it;
3. **`langdetect` over each prose line** — `--strict`, and it needs the `strict` extra.

Layer 1 alone is the usual approach, and it is why the usual approach misses: about a third of the
Spanish in the repos this was built for carries no accent at all. Layer 2 is what catches that
third, and it is why the wordlist is curated rather than clever — `no`, `total`, `final`, `sin` and
`solo` are deliberately **absent**, because each one fires on ordinary English. Every removal was
made after measuring a real false positive, not out of caution.

A genuine false positive is silenced with `lang-ok` on the line — `# lang-ok` in code,
`<!-- lang-ok -->` in Markdown.

## Wiring it up

**pre-commit** (`.pre-commit-config.yaml`):

```yaml
repos:
  - repo: https://github.com/txemi/darnlang
    rev: v0.1.0
    hooks:
      - id: darnlang           # added lines only
      - id: darnlang-commit-msg
```

**GitHub Actions** — the three published surfaces, which is the point of the tool:

```yaml
- uses: txemi/darnlang@v0.1.0
  with:
    ext: .py,.md
    surfaces: files,commits,pr    # issues need their own workflow: see action.yml
```

**Jenkins** — a declarative stage (complete pipeline: [`examples/Jenkinsfile`](examples/Jenkinsfile)). Worth documenting rather than leaving as an exercise, because a
self-hosted controller is often the wall that keeps working when a hosted one stops: it does not
meter minutes and it does not stop because a card expired.

```groovy
stage('darnlang') {
  steps {
    sh '''
      set -eu
      # uvx needs no venv and leaves nothing behind. `pip install --user darnlang` works too.
      export PATH="$HOME/.local/bin:$PATH"
      uvx darnlang check --ext .py,.md
    '''
  }
}
```

Three things that are specific to Jenkins and cost time to rediscover:

- **The workspace is a real git checkout**, so the repo root resolves normally and the baseline is
  found where you committed it. But a *shallow* clone (the default in many jobs) still carries the
  full working tree, which is all this tool reads — no extra depth needed for `check`.
- **Distinguish "there is debt" from "I could not run".** Exit `1` is findings, `3` is an
  environment problem — a missing baseline, or a scan that examined **zero** files. Failing the
  build on both is right; treating `3` as a pass is how a gate silently stops gating:

  ```groovy
  script {
    def rc = sh(returnStatus: true, script: 'uvx darnlang check --ext .py,.md')
    if (rc == 3) { error 'darnlang could not run — this is not a pass' }
    if (rc != 0) { error "darnlang found issues (rc=${rc})" }
  }
  ```

- **The PR surfaces work here too**, via the GitHub/Bitbucket Branch Source plugin, which exposes
  the change's title and body as environment variables on a multibranch pipeline:

  ```groovy
  when { changeRequest() }
  steps {
    sh '''
      set -eu
      printf '%s\\n\\n%s\\n' "$CHANGE_TITLE" "${CHANGE_BODY:-}" > pr.txt
      uvx darnlang prose pr.txt --label "PR title/description"
      git log --format=%B "origin/${CHANGE_TARGET}..HEAD" > msgs.txt
      uvx darnlang prose msgs.txt --label "set of commit messages"
    '''
  }
  ```

  Note the variables go through the environment, never interpolated into the Groovy string: a change
  title is written by whoever opened it, and `sh "echo ${env.CHANGE_TITLE}"` is a shell injection.
  Jenkins already exports them, so `"$CHANGE_TITLE"` inside single-quoted `'''` is both safer and
  shorter.

  **Issues have no Jenkins equivalent at all** — there is no webhook that fires before an issue is
  published, on any forge. That surface stays with the forge's own automation
  (`examples/lang-issue.yml`), and it can only label, never block.

## Why the matched text is not printed

By default findings are reported as `path:line`, without the offending text. CI logs of a public
repository are public, and the offending line is the single item on the page most likely to contain
something you did not mean to publish. `--show-text` opts back in, and is what you want locally.

## Licence

[GPL-3.0-or-later](LICENSE).
