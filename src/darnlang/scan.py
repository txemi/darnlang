"""The three things that can be scanned: a tree, a diff, and free prose.

The third is the one that is usually missing, and it is the one that matters most on a public repo.
A file gate cannot see a commit message, a pull-request title or an issue body — they are written
straight into the forge — so a project can have a green gate, a clean tree, and still be publishing
in the wrong language. Measured on one public repo the day this was written: 2 of 2 open issues,
4 PR titles, 7 PR descriptions and 7 commit subjects, with everything green the whole time. Those
surfaces are also the least retractable: an indexed PR title cannot be taken back.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass

from .detect import ESCAPE, family, is_fence, offending, strip_verbatim

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "_build", "build", "dist",
             ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "site-packages"}


@dataclass(frozen=True)
class Hit:
    path: str
    line: int
    text: str
    code: str = "prose"


def _scan_lines(rel: str, lines: list[str], pattern) -> list[Hit]:
    """Offending lines of one file, tracking fenced blocks for documents.

    Fence state is resolved by `fenced_line_numbers`, which refuses to trust an UNBALANCED fence.
    Toggling naively cost two measured blind spots: a document with an odd number of fences hid
    everything after the last one, and — with no typo needed — a line beginning with an inline span
    (```` ```x``` is the marker ````) toggled the state and swallowed the rest of the file. Both
    reported a clean scan.
    """
    hits = []
    fenced = fenced_line_numbers(lines) if family(rel) == "doc" else set()
    for i, ln in enumerate(lines, 1):
        if i in fenced:
            continue
        if offending(ln, rel, pattern, i in fenced):
            hits.append(Hit(rel, i, ln.strip()))
    return hits


def fenced_line_numbers(lines: list[str]) -> set[int]:
    """Line numbers inside a fenced code block, fences included.

    Two rules that a naive toggle does not have, both from measured false greens:

    * a fence OPENER must be a lone fence on its line. ```` ```x``` is the marker ```` is an inline
      code span in ordinary Markdown, not the start of a block, and treating it as one hid every
      following line of the document.
    * an UNBALANCED fence closes nothing. If a block is opened and never closed, the file is treated
      as having no block at all rather than as being entirely code — because "the author forgot a
      fence" must not be a way to make a whole document unjudgeable. It errs toward MORE findings,
      which is the direction a gate should be wrong in.
    """
    opens: list[int] = []
    spans: list[tuple[int, int]] = []
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if not (s.startswith("```") or s.startswith("~~~")):
            continue
        marker = s[:3]
        # A closing fence carries nothing but the marker; an opener may carry an info string. A line
        # that OPENS and CLOSES on itself (```x```) is an inline span and neither.
        if s.count(marker) > 1:
            continue
        if opens:
            spans.append((opens.pop(), i))
        else:
            opens.append(i)
    fenced: set[int] = set()
    for start, end in spans:
        fenced.update(range(start, end + 1))
    return fenced


class NothingToScan(Exception):
    """No file was examined. NEVER the same answer as "nothing was wrong".

    Raised rather than returning an empty list, because the empty list is indistinguishable from a
    clean tree and every caller would report it as a pass. This is not hypothetical: seeding a
    baseline in a repo whose files were not yet committed produced `count: 0` with a cheerful
    message, and that zero would then have become the floor the ratchet defends — a gate calibrated
    against nothing, reporting success forever. It happened while writing this tool's own first
    commit.
    """


def scan_tree(root: str, exts: tuple[str, ...], pattern, *, filenames: bool = True,
              tracked_only: bool = True, exclude: tuple[str, ...] = ()) -> list[Hit]:
    """Every offending line under `root`.

    `tracked_only` asks git for the file list, which is what you almost always want: an untracked
    scratch file is not the project, and scanning `.venv` is how a gate becomes slow enough to be
    switched off. With no git, it walks the tree and prunes SKIP_DIRS.

    `filenames` also judges the NAME of each file. No ancestor of this tool did that, it costs
    nothing, and a file called `investigacion_de_errores.py` is exactly as public as its contents.

    `exclude` is repo-relative paths the caller knows must not be judged. It exists for exactly one
    thing today and the thing is not cosmetic: THE DETECTOR MUST NOT JUDGE ITS OWN DICTIONARY. A
    wordlist is a file whose every line is, by construction, a word in the language being hunted, so
    scanning it yields one finding per line, forever, and not one of them means anything. Measured on
    a repo that ships a 100-word list: 100 of its 129 findings were that single file. Left in, the
    number stops being a debt count and becomes noise that punishes whoever tries to bring it down.

    Raises NothingToScan when the file list is empty, or when no file matched `exts`.
    """
    files = _files(root, tracked_only)
    if not files:
        raise NothingToScan(
            f"no files to scan under {root}. If this is a git repo, nothing is committed yet "
            f"(a scan of zero files is not a clean scan); otherwise check the path.")
    if exts and not any(rel.lower().endswith(exts) for rel in files):
        raise NothingToScan(
            f"none of the {len(files)} files under {root} match {', '.join(exts)}. "
            f"Widen --ext, or you are measuring nothing.")
    hits: list[Hit] = []
    unread: list[str] = []
    skip = {os.path.normpath(p) for p in exclude}
    for rel in files:
        if exts and not rel.lower().endswith(exts):
            continue
        if os.path.normpath(rel) in skip:
            continue
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            # SAY IT. A bare `continue` here was NothingToScan's twin: the list was not empty, but
            # every element in it failed to open, and the tool reported a clean tree. The profile
            # that hits this is exactly the profile the ratchet exists for — a repo that adopted the
            # rule late, whose legacy files are latin-1 — so the silence would have written a floor
            # of 0 over real debt. `chmod 000` and a vendored gitlink do the same.
            unread.append(f"{rel} ({exc.__class__.__name__})")
            continue
        hits.extend(_scan_lines(rel, lines, pattern))
    if unread:
        print(f"darnlang: {len(unread)} file(s) could NOT be read and were not judged "
              f"(this is not the same as clean):", file=sys.stderr)
        for u in unread[:10]:
            print(f"  {u}", file=sys.stderr)
        if len(unread) > 10:
            print(f"  ... and {len(unread) - 10} more", file=sys.stderr)
    if filenames:
        hits.extend(_scan_filenames(root, pattern, tracked_only))
    return hits


def _files(root: str, tracked_only: bool) -> list[str]:
    if tracked_only:
        try:
            # `-z` and `core.quotePath=false` are not cosmetic. By default git RENDERS a non-ASCII
            # path as an escaped C string -- an accented name arrives as `"an\303\241lisis.py"` -- so  # lang-ok
            # the accent that the name check exists to find never reaches the detector, and a file
            # named in the wrong language passes because of how it was named. Caught by a test, and
            # invisible without one.
            r = subprocess.run(["git", "-c", "core.quotePath=false", "-C", root, "ls-files", "-z"],
                               capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                return [p for p in r.stdout.split("\0") if p]
        except (OSError, subprocess.SubprocessError):
            pass
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            out.append(os.path.relpath(os.path.join(dirpath, fn), root))
    return out


def _scan_filenames(root: str, pattern, tracked_only: bool) -> list[Hit]:
    """Judge path COMPONENTS, split on the separators names actually use.

    Whole-name matching would miss `analisis_de_errores.py`; matching anywhere in the string would
    fire on any English word that happens to contain a listed one. Splitting is the middle that
    behaves.

    KNOWN LIMIT, stated because it is easy to mistake this for a guarantee: the built-in wordlist is
    FUNCTION words (`que`, `para`, `donde`), and file names are made of CONTENT words (`analisis`,
    `errores`). So with the default list an unaccented name mostly slips through, and what catches
    it is the accent class. A repo that cares about names should ship a wordlist with its own
    content words — which is one of the reasons the wordlist is replaceable at all. There is a test
    pinning exactly this, so the limit cannot quietly become a surprise.
    """
    hits = []
    for rel in _files(root, tracked_only):
        for token in re.split(r"[\s_\-./]+", rel):
            if token and pattern.search(token):
                hits.append(Hit(rel, 0, token, code="filename"))
                break
    return hits


def scan_diff(root: str, ref: str | None, exts: tuple[str, ...], pattern) -> list[Hit]:
    """Offending lines among those ADDED by a diff. Only `+` lines are judged: touching a file must
    not make you responsible for prose you did not write.

    Fence state cannot be read from a unified diff — an added line inside a ``` block looks exactly
    like an added paragraph — so doc files are re-read from the working tree to find out. When that
    read fails the line is judged as prose, which errs toward MORE findings. That is the correct
    direction for a gate to be wrong in.
    """
    # `core.quotePath=false`: without it git RENDERS a non-ASCII path as an escaped C string, so the
    # `+++ b/…` line does not match and EVERY added line in that file is skipped. `_files` learned
    # this and this function did not — and the file most likely to be NAMED in the wrong language is
    # the file most likely to contain it. `-z` is not usable here: a unified diff is line-oriented.
    cmd = ["git", "-c", "core.quotePath=false", "-C", root, "diff", "--unified=0"]
    cmd += [ref] if ref else ["--cached"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        # RAISE, never `return []`. An empty finding list is indistinguishable from a clean diff, so
        # "I could not look" was being reported as "I found nothing" — in the one place this tool
        # had not applied its own doctrine, and the place the shipped pre-commit hook runs.
        raise NothingToScan(
            f"cannot read the diff ({exc.__class__.__name__}). A diff that could not be read is not "
            f"a clean diff.") from exc
    hits, path, lineno, fenced, in_hunk = [], None, 0, set(), False
    for ln in out.splitlines():
        # `+++ b/…` is only a header OUTSIDE a hunk. Inside one it is an ADDED LINE whose content
        # begins with `++ b/…` — which any file documenting a patch format contains. Treating it as
        # a header silently redirected every following line to a path that was not being edited, and
        # dropped them all when that path failed the extension filter. Attacker-reachable in a PR.
        if not in_hunk and ln.startswith("+++ b/"):
            path = ln[6:]
            fenced = _fenced_lines(os.path.join(root, path)) if family(path) == "doc" else set()
            continue
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)", ln)
        if m:
            lineno = int(m.group(1))
            in_hunk = True
            continue
        if ln.startswith("diff --git "):
            in_hunk, path = False, None
            continue
        if ln.startswith("+") and not ln.startswith("+++"):
            body = ln[1:]
            if path and (not exts or path.lower().endswith(exts)):
                if offending(body, path, pattern, lineno in fenced):
                    hits.append(Hit(path, lineno, body.strip()))
            lineno += 1
    return hits


def _fenced_lines(path: str) -> set[int]:
    """Fence state for a doc file in a diff, from the post-image on disk.

    Shares `fenced_line_numbers` with the tree scan on purpose: two implementations of "is this line
    inside a fence" is two answers, and the pre-commit path disagreeing with the CI path is how a
    contributor learns the gate is arbitrary.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            return fenced_line_numbers(fh.read().splitlines())
    except (OSError, UnicodeDecodeError):
        return set()


def scan_prose(text: str, pattern, *, git_comments: bool = False) -> list[Hit]:
    """Free prose: a commit message, an issue, a PR title and body.

    Judged with the doc rule — everything is language except fences, inline `code` and URLs —
    because that is what these texts are. Two deliberate details:

    * `git_comments` drops `#` lines. In a commit message those are git's own template, written in
      the machine's LOCALE, which would fail the author for text they never wrote and git is about
      to strip. In Markdown a `#` is a heading, i.e. prose that must be judged, so the two cases
      cannot share a default.
    * A scissors line ends the message: everything below it is the diff `--verbose` pastes in, and
      judging somebody's code as prose is how a gate earns a reputation for lying.
    """
    hits, in_fence = [], False
    for i, ln in enumerate(text.splitlines(), 1):
        if git_comments and ln.startswith("# ------------------------ >8"):
            break
        if git_comments and ln.startswith("#"):
            continue
        if is_fence(ln):
            in_fence = not in_fence
            continue
        if in_fence or ESCAPE in ln:
            continue
        if pattern.search(strip_verbatim(ln)):
            hits.append(Hit("<text>", i, ln.strip()))
    return hits
