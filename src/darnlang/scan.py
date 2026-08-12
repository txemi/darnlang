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
    hits, in_fence = [], False
    for i, ln in enumerate(lines, 1):
        if family(rel) == "doc" and is_fence(ln):
            in_fence = not in_fence
            continue
        if offending(ln, rel, pattern, in_fence):
            hits.append(Hit(rel, i, ln.strip()))
    return hits


def scan_tree(root: str, exts: tuple[str, ...], pattern, *, filenames: bool = True,
              tracked_only: bool = True) -> list[Hit]:
    """Every offending line under `root`.

    `tracked_only` asks git for the file list, which is what you almost always want: an untracked
    scratch file is not the project, and scanning `.venv` is how a gate becomes slow enough to be
    switched off. With no git, it walks the tree and prunes SKIP_DIRS.

    `filenames` also judges the NAME of each file. No ancestor of this tool did that, it costs
    nothing, and a file called `investigacion_de_errores.py` is exactly as public as its contents.
    """
    hits: list[Hit] = []
    for rel in _files(root, tracked_only):
        if exts and not rel.lower().endswith(exts):
            continue
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        hits.extend(_scan_lines(rel, lines, pattern))
    if filenames:
        hits.extend(_scan_filenames(root, pattern, tracked_only))
    return hits


def _files(root: str, tracked_only: bool) -> list[str]:
    if tracked_only:
        try:
            # `-z` and `core.quotePath=false` are not cosmetic. By default git RENDERS a non-ASCII
            # path as an escaped C string -- `análisis.py` arrives as `"an\303\241lisis.py"` -- so
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
    cmd = ["git", "-C", root, "diff", "--unified=0"] + ([ref] if ref else ["--cached"])
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"darnlang: cannot read the diff ({exc.__class__.__name__}) -> nothing judged",
              file=sys.stderr)
        return []
    hits, path, lineno, fenced = [], None, 0, set()
    for ln in out.splitlines():
        if ln.startswith("+++ b/"):
            path = ln[6:]
            fenced = _fenced_lines(os.path.join(root, path)) if family(path) == "doc" else set()
            continue
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)", ln)
        if m:
            lineno = int(m.group(1))
            continue
        if ln.startswith("+") and not ln.startswith("+++"):
            body = ln[1:]
            if path and (not exts or path.lower().endswith(exts)):
                if offending(body, path, pattern, lineno in fenced):
                    hits.append(Hit(path, lineno, body.strip()))
            lineno += 1
    return hits


def _fenced_lines(path: str) -> set[int]:
    inside, fenced = False, set()
    try:
        with open(path, encoding="utf-8") as fh:
            for n, ln in enumerate(fh.read().splitlines(), 1):
                if is_fence(ln):
                    inside = not inside
                    fenced.add(n)
                elif inside:
                    fenced.add(n)
    except (OSError, UnicodeDecodeError):
        return set()
    return fenced


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
