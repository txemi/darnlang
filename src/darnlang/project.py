"""Where the project is, and where its baseline lives — derived from ONE value.

WHY THIS FILE EXISTS AT ALL. Its ancestor resolved two things independently: the tree to scan
(`dirname(dirname(__file__))`) and the baseline file (`dirname(__file__)/…`). Both were anchored to
the tool, so they always agreed, and the gate worked — correct by accident of location. When one of
the two was later fixed to resolve against the repo and the other was not, the gate did something
worse than either: it read the real baseline (1242 legacy lines) and compared it against a count
taken from a different tree (0), concluded the debt had gone DOWN, exited 0, and printed
congratulations plus an invitation to run the command that overwrites the baseline with the wrong
number. Worse still, the answer was arbitrary — the scanned tree was whatever sat next to the
installed file, so the same command gave green on one machine and red on another.

The lesson is not "remember to change both lines". It is that two parallel resolutions of the same
concept will drift, and the only fix that stays fixed is to have one:

    root  =  git repo root  (or, with no git, the caller's directory)
      ├── tree to scan  = root
      └── baseline      = <root>/.darnlang-baseline.json

Derived from the same value, they cannot disagree.
"""
from __future__ import annotations

import os
import subprocess
import sys

BASELINE_NAME = ".darnlang-baseline.json"
#: Where the vendored ancestor kept it. Accepted when present so a repo migrating from a copied
#: `lang_gate.py` does not have to move a versioned file on the same day it changes tools.
LEGACY_BASELINE = os.path.join("tools", "lang_gate_baseline.json")


def project_root(start: str | None = None) -> str:
    """The repo root. Falls back to `start` (default: cwd), and SAYS SO when it does.

    The fallback is announced rather than silent because every other degradation in this tool is
    announced, and because a gate that quietly picks a different tree is precisely the failure this
    module exists to prevent.
    """
    start = os.path.realpath(start or os.getcwd())
    try:
        r = subprocess.run(["git", "-C", start, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return os.path.realpath(r.stdout.strip())
        print(f"darnlang: {start} is not inside a git repo -> scanning it as-is", file=sys.stderr)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"darnlang: cannot ask git for the repo root ({exc.__class__.__name__}) "
              f"-> scanning {start} as-is", file=sys.stderr)
    return start


class ForeignBaseline(Exception):
    """The explicit baseline belongs to a different project than the tree being scanned."""


def baseline_path(root: str, explicit: str | None = None) -> str:
    """The baseline file, DERIVED from `root` so the two can never disagree.

    Order: an explicit `--baseline-file` -> the legacy `tools/lang_gate_baseline.json` if it already
    exists -> `<root>/.darnlang-baseline.json`.

    THE EXPLICIT OVERRIDE IS CONTAINED, and that guard is not decoration. This tool was extracted
    from a script that resolved the tree and the baseline independently; the derivation fix removed
    the accidental version of the bug, but `--baseline-file` reintroduces it BY DESIGN, since it is
    the one place a caller can point at another project's numbers. The ancestor had this guard and
    two tests for it, and both were deleted with the file. Without it, measured:

        darnlang check --baseline-file /elsewhere/base.json
        -> "OK -- and it went DOWN (0 < 1242). Lock the win in with `darnlang update-baseline`."

    which is, word for word, the congratulation this project exists to make impossible — and the
    suggested command then overwrites a real 1242 with a 0.

    `DARNLANG_ALLOW_FOREIGN_BASELINE=1` is the escape, because a deliberate cross-tree comparison is
    a legitimate thing to want and guessing on the caller's behalf is what got us here.
    """
    if explicit:
        path = os.path.realpath(explicit)
        if not os.environ.get("DARNLANG_ALLOW_FOREIGN_BASELINE"):
            root_real = os.path.realpath(root)
            try:
                inside = os.path.commonpath([path, root_real]) == root_real
            except ValueError:      # different drives on Windows
                inside = False
            if not inside:
                raise ForeignBaseline(
                    f"the baseline {path} is outside the tree being scanned ({root_real}). "
                    f"Comparing a count from one project against another project's floor is how a "
                    f"gate congratulates you on debt it never looked at. Set "
                    f"DARNLANG_ALLOW_FOREIGN_BASELINE=1 if you mean it.")
        return path
    legacy = os.path.join(root, LEGACY_BASELINE)
    if os.path.exists(legacy):
        return legacy
    return os.path.join(root, BASELINE_NAME)
