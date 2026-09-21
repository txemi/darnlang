#!/usr/bin/env python3
"""Every shipped YAML parses, and the files the README points at exist."""
import pathlib
import sys

import yaml

bad = []
for path in sorted(pathlib.Path(".").rglob("*.y*ml")):
    if ".git/" in str(path) or ".venv" in path.parts[0:1] or any(p.startswith(".venv") for p in path.parts):
        continue
    try:
        yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - any parse failure is the finding
        bad.append(f"{path}: {exc}")
for extra in ("examples/Jenkinsfile",):
    pathlib.Path(extra).exists() or bad.append(f"{extra}: missing")
print("\n".join(bad) or "ok")
sys.exit(1 if bad else 0)
