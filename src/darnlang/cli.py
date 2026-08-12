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
from .detect import CODE_EXTS, DOC_EXTS, ESCAPE, build_pattern, langdetect_says_foreign
from .project import baseline_path, project_root
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


def _words(root: str, arg: str | None) -> list[str] | None:
    path = arg or next((p for p in (os.path.join(root, n) for n in WORDS_FILENAMES)
                        if os.path.exists(p)), None)
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
    p.add_argument("--baseline-file", help="explicit baseline location")
    p.add_argument("--show-text", action="store_true", help="print the offending line (local use)")
    p.add_argument("--no-filenames", action="store_true", help="do not judge file NAMES")
    p.add_argument("--strict", action="store_true",
                   help="also run langdetect on every prose line (needs the 'strict' extra)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="darnlang",
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
    p.add_argument("--root")

    args = ap.parse_args(argv)
    root = project_root(getattr(args, "root", None))
    pattern = build_pattern(_words(root, getattr(args, "words_file", None)))

    if args.cmd == "prose":
        try:
            text = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError) as exc:
            # Fail CLOSED. An unreadable message is not a clean message, and this mode exists for
            # the surfaces where nothing else is watching.
            print(f"darnlang: cannot read {args.file} ({exc})", file=sys.stderr)
            return 3
        hits = scan_prose(text, pattern, git_comments=args.git_comments)
        if hits:
            _report(hits, f"darnlang: this {args.label} is not in the expected language:",
                    args.show_text)
            print("\nCommit messages, PR titles/descriptions and issues are public, permanent, and "
                  "part of the project's documentation.", file=sys.stderr)
            return 1
        print(f"darnlang: OK -- the {args.label} is clean.")
        return 0

    exts = _exts(args.ext)
    bpath = baseline_path(root, args.baseline_file)

    if getattr(args, "diff", None) is not None:
        hits = scan_diff(root, args.diff or None, exts, pattern)
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
    if args.strict:
        hits = _add_langdetect(root, exts, hits)
    per_file: dict[str, int] = {}
    for h in hits:
        per_file[h.path] = per_file.get(h.path, 0) + 1
    n = len(hits)

    if args.cmd == "update-baseline":
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


def _add_langdetect(root: str, exts: tuple[str, ...], hits: list[Hit]) -> list[Hit]:
    """Layer 3, opt-in. Never replaces the cheap layers; only adds what they missed."""
    try:
        import langdetect  # noqa: F401,PLC0415
    except ImportError:
        print("darnlang: --strict needs the 'strict' extra (pip install darnlang[strict]) "
              "-> skipping layer 3", file=sys.stderr)
        return hits
    from .detect import family, is_fence, is_prose
    from .scan import _files

    seen = {(h.path, h.line) for h in hits}
    extra: list[Hit] = []
    langs = frozenset({"es"})
    for rel in _files(root, tracked_only=True):
        if exts and not rel.lower().endswith(exts):
            continue
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        in_fence = False
        for i, ln in enumerate(lines, 1):
            if family(rel) == "doc" and is_fence(ln):
                in_fence = not in_fence
                continue
            if (rel, i) in seen or ESCAPE in ln or not is_prose(rel, ln, in_fence):
                continue
            s = ln.strip()
            # Short strings are where langdetect is worst; below ~25 chars it guesses. The cheap
            # layers already cover short prose via the wordlist, so this floor costs nothing.
            if len(s) >= 25 and langdetect_says_foreign(s, langs):
                extra.append(Hit(rel, i, s, code="langdetect"))
    return hits + extra


if __name__ == "__main__":
    raise SystemExit(main())
