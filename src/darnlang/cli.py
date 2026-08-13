"""Command line: four modes, one exit code each, and no surprises.

    darnlang check                 whole tree against the baseline (CI)
    darnlang check --diff [REF]    only lines ADDED (pre-commit)
    darnlang prose FILE|-          a commit message, an issue, a PR title+body
    darnlang update-baseline       record the new (lower) count after translating

EXIT CODES are part of the contract, because a caller has to tell "there is debt" from "I could not
run": 0 clean · 1 findings · 2 coverage changed (re-seed) · 3 usage/environment error.

ON PRINTING THE MATCHED TEXT. Off by default. CI logs of a public repository are public, and the
offending line is the one thing on the page most likely to contain something you did not mean to
publish. `--show-text` opts in, and is what you want locally.
"""
from __future__ import annotations

import argparse
import os
import sys

from . import baseline as bl
from .detect import (CODE_EXTS, DEFAULT_ALLOWED, DOC_EXTS, ESCAPE, build_pattern,
                     langdetect_is_foreign, strip_verbatim)
from .project import ForeignBaseline, baseline_path, project_root


class EmptyWordlistArgument(Exception):
    """A wordlist flag was given an empty path."""
from .detect import is_fence
from .scan import Hit, NothingToScan, scan_diff, scan_prose, scan_tree

DEFAULT_EXTS = (".py",)
WORDS_FILENAMES = ("darnlang-words.txt", os.path.join("tools", "spanish_words.txt"),
                   os.path.join("scripts", "devtools", "spanish_words.txt"))


def _exts(arg: str | None) -> tuple[str, ...]:
    """Extensions to scan.

    The default stays `.py`, and NOT out of timidity: switching a documentation-heavy repo to `.md`
    added 820 lines at once on top of an existing 1242 of debt. That is not a fix, it is an
    avalanche, and an avalanche is how a gate ends up switched off. Each repo widens on its own
    schedule and the ratchet absorbs what appears — which is the one good property the copy-per-repo
    model had, and the thing a careless extraction would destroy.
    """
    raw = arg or os.environ.get("DARNLANG_EXTS") or ",".join(DEFAULT_EXTS)
    if raw.strip() in {"all", "*"}:
        return tuple(sorted(CODE_EXTS | DOC_EXTS))
    return tuple(sorted({e if e.startswith(".") else f".{e}"
                         for e in (x.strip().lower() for x in raw.split(",")) if e}))


def _read_words(path: str | None, *, flag: str = "") -> list[str] | None:
    """Read a wordlist. An EMPTY string is an error, not an absence.

    A consumer passed `--extra-words-file ""` for weeks -- the variable holding the path was exported
    in one CI step and read in another process -- and this function's `if not path: return None`
    turned that into a silent no-op. The log said clean, the file was never opened, and the one thing
    that made that repo's configuration different was inert. An argument that was given must be
    honoured or refused; ignoring it is the third option nobody wants.
    """
    if path is None:
        return None
    if not path.strip():
        raise EmptyWordlistArgument(
            f"{flag or '--words-file'} was given an EMPTY path. Ignoring it would run a different "
            f"detector than the one you asked for, and say nothing.")
    try:
        with open(path, encoding="utf-8") as fh:
            return [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    except OSError as exc:
        print(f"darnlang: cannot read {path} ({exc})", file=sys.stderr)
        return None


def _autodetected(root: str) -> list[str] | None:
    """A wordlist found by convention. It EXTENDS the built-in list; it does not replace it.

    Replacing was the first design and it was a silent trap, found while wiring a repo that happens
    to ship `scripts/devtools/spanish_words.txt`: the file was picked up automatically, swapped out
    the built-in function words, and the gate stopped catching the commonest markers there are:
    the Spanish articles and conjunctions. Nothing said so. A file discovered by NAME must never change the meaning of
    the detector behind your back; only an explicit `--words-file` may, because that is a decision
    somebody typed.
    """
    path = next((p for p in (os.path.join(root, n) for n in WORDS_FILENAMES)
                 if os.path.exists(p)), None)
    if not path:
        return None
    words = _read_words(path)
    if words:
        print(f"darnlang: adding {len(words)} word(s) from {os.path.relpath(path, root)} "
              f"to the built-in list.", file=sys.stderr)
    return words


def _words(root: str, arg: str | None) -> list[str] | None:
    path = arg
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    except OSError as exc:
        print(f"darnlang: cannot read the wordlist {path} ({exc}) -> using the built-in one",
              file=sys.stderr)
        return None


def _report(hits: list[Hit], header: str, show_text: bool) -> None:
    print(header, file=sys.stderr)
    for h in hits[:25]:
        where = f"  {h.path}:{h.line}" if h.line else f"  {h.path}"
        print(f"{where}{': ' + h.text[:110] if show_text else f'  [{h.code}]'}", file=sys.stderr)
    if len(hits) > 25:
        print(f"  ... and {len(hits) - 25} more", file=sys.stderr)
    if not show_text:
        print("\n(the matching text is not printed: CI logs of a public repo are public. "
              "Use --show-text locally.)", file=sys.stderr)
    print(f"A genuine false positive is silenced with `{ESCAPE}` on that line.", file=sys.stderr)


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", help="project root (default: the git repo root of the cwd)")
    p.add_argument("--ext", help="extensions to scan, comma-separated, or 'all' (default: .py)")
    p.add_argument("--words-file", help="wordlist, one per line (default: auto-detected, else built-in)")
    p.add_argument("--extra-words-file",
                   help="words ADDED to the list in use (one per line) — for a word this repo needs "
                        "that the default drops as too ambiguous elsewhere")
    p.add_argument("--baseline-file", help="explicit baseline location")
    p.add_argument("--show-text", action="store_true", help="print the offending line (local use)")
    p.add_argument("--no-filenames", action="store_true", help="do not judge file NAMES")
    p.add_argument("--allow-narrower", action="store_true",
                   help="with update-baseline: permit writing a baseline that covers LESS")


class _ArgParser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error, and 2 is taken: it means "coverage changed, re-seed". A
    caller automating that would re-seed its baseline over a typo'd flag. Usage errors are 3, with
    every other "could not run"."""

    def error(self, message: str):  # noqa: D102
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(3)


def main(argv: list[str] | None = None) -> int:
    ap = _ArgParser(prog="darnlang",
                    description="Keep a repo's prose in one language, with a ratchet.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="whole tree vs the baseline, or only the lines a diff adds")
    c.add_argument("--diff", nargs="?", const="", metavar="REF",
                   help="judge only ADDED lines (default: the staged diff)")
    _add_common(c)

    u = sub.add_parser("update-baseline", help="record the current count (after translating)")
    _add_common(u)

    p = sub.add_parser("prose", help="judge free text: commit message, issue, PR title+body")
    p.add_argument("file", help="path, or '-' for stdin")
    p.add_argument("--git-comments", action="store_true",
                   help="drop '#' lines and everything after the scissors (a commit message)")
    p.add_argument("--label", default="text", help="what to call it in the error message")
    p.add_argument("--show-text", action="store_true")
    p.add_argument("--words-file")
    p.add_argument("--extra-words-file")
    p.add_argument("--root")
    p.add_argument("--strict", action="store_true",
                   help="also ask langdetect whether the whole text is English (needs the 'strict' extra)")

    args = ap.parse_args(argv)
    root = project_root(getattr(args, "root", None))
    try:
        extra = ((_read_words(getattr(args, "extra_words_file", None), flag="--extra-words-file") or [])
                 + (_autodetected(root) or []))
        pattern = build_pattern(_words(root, getattr(args, "words_file", None)), extra or None)
    except EmptyWordlistArgument as exc:
        print(f"darnlang: {exc}", file=sys.stderr)
        return 3

    if args.cmd == "prose":
        try:
            text = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError) as exc:
            # Fail CLOSED. An unreadable message is not a clean message, and this mode exists for
            # the surfaces where nothing else is watching.
            print(f"darnlang: cannot read {args.file} ({exc})", file=sys.stderr)
            return 3
        hits = scan_prose(text, pattern, git_comments=args.git_comments)
        if not hits and args.strict:
            # The cheap layers are weakest exactly here -- a commit subject is short by nature,
            # which is the case a stopword list cannot cover -- so layer 3 earns its place on a
            # message WITH A BODY, an issue, or a PR description.
            #
            # ⚠️ IT IS NOT RELIABLE ON A BARE SUBJECT LINE, and that is measured, not suspected:
            #
            #   "hooks: apply darnlang to darnlang"        -> tl (0.86)   English, FLAGGED
            #   "ci: uv venv --clear, setup-uv makes one"  -> et (0.71)   English, FLAGGED
            #   "migra el gate de idioma al paquete"       -> ca (0.86)   Spanish, caught
            #
            # A subject line is mostly identifiers, and two repetitions of an invented word dominate
            # it. Neither confidence nor length nor word count separates the two sets -- the false
            # positives score exactly as high as the true ones. So `--strict` belongs on prose, and
            # a wiring that feeds it bare subjects will block honest English. See README §Detection.
            try:
                hits = _strict_prose(text, args.git_comments)
            except StrictUnavailable as exc:
                print(f"darnlang: {exc}", file=sys.stderr)
                return 3
        if hits:
            _report(hits, f"darnlang: this {args.label} is not in the expected language:",
                    args.show_text)
            print("\nCommit messages, PR titles/descriptions and issues are public, permanent, and "
                  "part of the project's documentation.", file=sys.stderr)
            return 1
        print(f"darnlang: OK -- the {args.label} is clean.")
        return 0

    exts = _exts(args.ext)
    try:
        bpath = baseline_path(root, args.baseline_file)
    except ForeignBaseline as exc:
        print(f"darnlang: {exc}", file=sys.stderr)
        return 3

    if getattr(args, "diff", None) is not None:
        try:
            hits = scan_diff(root, args.diff or None, exts, pattern)
        except NothingToScan as exc:
            print(f"darnlang: {exc}", file=sys.stderr)
            return 3
        if hits:
            _report(hits, f"darnlang: {len(hits)} NEW line(s) in the wrong language:", args.show_text)
            return 1
        print("darnlang: OK -- nothing new.")
        return 0

    try:
        hits = scan_tree(root, exts, pattern, filenames=not args.no_filenames)
    except NothingToScan as exc:
        # Exit 3 (environment), never 0. "I examined nothing" is not "I found nothing", and the
        # difference is the whole reliability of a ratchet: a baseline seeded against zero files
        # becomes a floor of 0 that then passes forever.
        print(f"darnlang: {exc}", file=sys.stderr)
        return 3
    per_file: dict[str, int] = {}
    for h in hits:
        per_file[h.path] = per_file.get(h.path, 0) + 1
    n = len(hits)

    if args.cmd == "update-baseline":
        # THE ONE COMMAND THAT WRITES THE FLOOR had no coverage guard, so narrowing the scope was
        # silently baked in — and the per-file map wiped with it. `check` was loud about exactly the
        # same narrowing. A ratchet whose write path is laxer than its read path is not a ratchet.
        prev = bl.load(bpath)
        if prev is not None:
            changed = bl.coverage_changed(prev, list(exts))
            if changed and changed[1] and not args.allow_narrower:
                print(f"darnlang: refusing to write a NARROWER baseline. It would stop counting "
                      f"{', '.join(changed[1])}, and bake that reduction in as the new floor.",
                      file=sys.stderr)
                print("If you mean it, say so: --allow-narrower.", file=sys.stderr)
                return 2
        bl.save(bpath, n, list(exts), per_file)
        print(f"darnlang: baseline updated to {n} across {len(per_file)} file(s) "
              f"(covering {', '.join(exts)}).")
        return 0

    base = bl.load(bpath)
    if base is None:
        print(f"darnlang: no readable baseline at {bpath}; the current count is {n}. "
              f"Create it with `darnlang update-baseline`.", file=sys.stderr)
        return 3

    changed = bl.coverage_changed(base, list(exts))
    if changed is not None:
        gained, lost = changed
        print(f"darnlang: COVERAGE CHANGED -- the baseline counted "
              f"{', '.join(base.scanned_exts or [])} but this run judges {', '.join(exts)}.",
              file=sys.stderr)
        if gained:
            print(f"  now also judged: {', '.join(gained)}  (current total: {n})", file=sys.stderr)
        if lost:
            print(f"  NO LONGER judged: {', '.join(lost)} -- coverage went DOWN, which is what the "
                  f"ratchet exists to prevent. Do not accept this without knowing why.",
                  file=sys.stderr)
        if lost:
            # Do NOT tell somebody to re-seed here. The previous wording gave identical advice for a
            # gain and for a loss, so a reader who correctly took "do not accept this without
            # knowing why" seriously was told in the next sentence to run the command that accepts
            # it.
            print("\nRestore the missing extensions, or, if the reduction is deliberate, write it "
                  "down explicitly: `darnlang update-baseline --ext … --allow-narrower`.",
                  file=sys.stderr)
        else:
            print("\nThis is an ADOPTION, not a regression: re-seed once with `darnlang "
                  "update-baseline` and the number may only fall from there.", file=sys.stderr)
        return 2

    if n > base.count:
        grew = {f: (per_file[f], base.files.get(f, 0))
                for f in per_file if per_file[f] > base.files.get(f, 0)}
        print(f"darnlang: the count GREW: {n} > baseline {base.count}.", file=sys.stderr)
        if grew:
            # Name the files that grew, not the first 25 hits in the tree. A bare total answers
            # "it grew" and then lists arbitrary legacy lines, which is useless for fixing it.
            print("These files gained lines (translate them; do NOT raise the baseline):",
                  file=sys.stderr)
            for f, (now, was) in sorted(grew.items(), key=lambda kv: kv[1][0] - kv[1][1], reverse=True):
                print(f"  {f}: {was} -> {now}  (+{now - was})", file=sys.stderr)
        else:
            _report(hits, "Tree hits:", args.show_text)
        return 1
    if n < base.count:
        print(f"darnlang: OK -- and it went DOWN ({n} < {base.count}). "
              f"Lock the win in with `darnlang update-baseline`.")
        return 0
    print(f"darnlang: OK -- {n} legacy line(s), unchanged vs the baseline.")
    return 0


class StrictUnavailable(Exception):
    """`--strict` was asked for and layer 3 cannot run."""


def _strict_prose(text: str, git_comments: bool) -> list[Hit]:
    """Layer 3 over free prose, as a single block."""
    try:
        import langdetect  # noqa: F401,PLC0415
    except ImportError as exc:
        raise StrictUnavailable(
            "--strict needs the 'strict' extra (pip install 'darnlang[strict]')."
        ) from exc
    # The SAME exemptions `scan_prose` applies. Layer 3 honoured none of them, and each omission was
    # a measured defect: `--git-comments` dropped the scissors LINE but kept the diff below it, so
    # 40 lines of English diff diluted a Spanish subject past langdetect (rc=0) -- and the shipped
    # commit-msg hook is fed exactly that file whenever `commit.verbose` is on. The mirror case blamed
    # an author for code. And `lang-ok` did not work, while the error message recommended it.
    kept, in_fence = [], False
    for ln in text.splitlines():
        if git_comments and ln.startswith("# ------------------------ >8"):
            break
        if git_comments and ln.startswith("#"):
            continue
        if is_fence(ln):
            in_fence = not in_fence
            continue
        if in_fence or ESCAPE in ln:
            continue
        kept.append(strip_verbatim(ln))
    body = " ".join(l.strip() for l in kept if l.strip())
    if len(body) >= 20 and langdetect_is_foreign(body, DEFAULT_ALLOWED):
        return [Hit("<text>", 1, body[:200], code="langdetect")]
    return []


# WHY THERE IS NO `check --strict`. Layer 3 existed here and was removed after measuring it against
# this repo's own tree, which is English by construction and pins its baseline at 0: it produced
# ELEVEN findings, at least eight of them plainly English —
#
#   "green and its tree at zero:"        "| PR descriptions | 7 more | no |"
#   "[GPL-3.0-or-later](LICENSE)."       "module exists to prevent."
#
# and reported them with "translate them; do NOT raise the baseline". The cause is not fixable by
# tuning: langdetect classifies a SENTENCE, and a line of a document is a fragment. Judging line by
# line asks it a question it cannot answer, and a gate that fires on English is a gate that gets
# bypassed — this project's oldest rule.
#
# `prose --strict` survives because there the unit is right: a commit message or a PR body is judged
# as ONE text, which is a thing langdetect can classify. Measured on 338 real commit subjects, it
# takes detection from ~76% to ~99.4%.

if __name__ == "__main__":
    raise SystemExit(main())
