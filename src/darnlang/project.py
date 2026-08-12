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


def baseline_path(root: str, explicit: str | None = None) -> str:
    """The baseline file, DERIVED from `root` so the two can never disagree.

    Order: an explicit `--baseline-file` (you are declaring you accept writes there) -> the legacy
    `tools/lang_gate_baseline.json` if it already exists -> `<root>/.darnlang-baseline.json`.
    """
    if explicit:
        return os.path.realpath(explicit)
    legacy = os.path.join(root, LEGACY_BASELINE)
    if os.path.exists(legacy):
        return legacy
    return os.path.join(root, BASELINE_NAME)
