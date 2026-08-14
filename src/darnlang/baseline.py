"""The ratchet: legacy debt is tolerated, and the number may only go DOWN.

WHY A RATCHET AND NOT FAIL-CLOSED. A repo that adopts the rule late already carries offending lines
— the first one to do so had ~1300 across 172 files, accumulated because the rule had never been
written down. Demanding they all be translated before the next commit simply gets the gate deleted.
So legacy lines sit in a baseline whose count can only shrink, while new lines must be clean from
now on. A repo that starts clean pins its baseline at 0, which is fail-closed with no extra
machinery.

WHY THE BASELINE RECORDS ITS COVERAGE. Widening what the tool judges — a new file family, a bigger
wordlist, a third detection layer — makes every consumer's count jump through nobody's fault.
Reported as "the count GREW", with "do not raise the baseline" underneath, that message is exactly
backwards: re-seeding once IS the correct move, the same as adopting the rule late. So the baseline
stores what it counted, and a mismatch is reported as an ADOPTION, in its own words, naming the
direction — because coverage silently going DOWN is how a gate loosens without anyone noticing.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

NOTE = "Legacy foreign-language lines. This number may only DECREASE."


@dataclass(frozen=True)
class Baseline:
    count: int
    scanned_exts: list[str] | None
    files: dict[str, int]
    exists: bool = True
    #: Extensionless files judged by NAME (Jenkinsfile, Dockerfile, ...). Recorded separately
    #: because they cannot be expressed as extensions, and a coverage record that cannot express
    #: part of its coverage is a blind spot -- see `coverage_changed`.
    scanned_names: list[str] | None = None


def load(path: str) -> Baseline | None:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return Baseline(count=int(data["count"]),
                        # Absent means "written before this field existed", NOT "counts nothing".
                        # A consumer on the old format must not fail on a key it never heard of.
                        scanned_exts=data.get("scanned_exts"),
                        scanned_names=data.get("scanned_names"),
                        files=data.get("files") or {})
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save(path: str, count: int, exts: list[str], per_file: dict[str, int],
         names: list[str] | None = None) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {"count": count, "note": NOTE, "scanned_exts": sorted(exts),
               "scanned_names": sorted(names or []),
               "files": dict(sorted(per_file.items()))}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")


def coverage_changed(base: Baseline, exts: list[str],
                     names: list[str] | None = None) -> tuple[list[str], list[str]] | None:
    """(gained, lost) when the recorded coverage differs from the current one, else None.

    NAMES ARE PART OF COVERAGE, and leaving them out was a blind spot with weight on it. The
    extensionless CI files -- Jenkinsfile, Dockerfile, Makefile -- are genuinely judged, and one
    consumer already carries a live `Jenkinsfile` entry in its baseline. But `scanned_exts` cannot
    represent them, so if the basename branch of `in_scope()` ever narrowed or broke, the count
    would FALL and the ratchet would report it as a win: "it went DOWN, lock it in". That is the
    precise failure this whole file exists to refuse, hiding in the one dimension the record could
    not express.

    An absent `scanned_names` means the baseline predates the field. Treated as "unknown", not as
    "empty": inferring zero would turn every old baseline into a spurious coverage GAIN on the next
    run, and a gate that cries wolf on adoption is one people stop reading.
    """
    if base.scanned_exts is None:
        return None
    gained = sorted(set(exts) - set(base.scanned_exts))
    lost = sorted(set(base.scanned_exts) - set(exts))
    if base.scanned_names is not None and names is not None:
        gained += sorted(set(names) - set(base.scanned_names))
        lost += sorted(set(base.scanned_names) - set(names))
    if not gained and not lost:
        return None
    return gained, lost
