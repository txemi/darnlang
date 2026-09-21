#!/usr/bin/env bash
# The project's own gates, in one place: the workflows and the Jenkinsfile both call this.
# uv honours UV_PYTHON and UV_PROJECT_ENVIRONMENT, so one script covers the Python matrix.
#   check.sh            tests with the dev extras, then the tree judged by this very checkout
#   check.sh no-strict  tests WITHOUT the strict extra; --strict must then refuse (rc 3)
set -euo pipefail
cd "$(dirname "$0")/.."
# One environment, named explicitly: an inherited VIRTUAL_ENV would send `uv pip` somewhere else.
unset VIRTUAL_ENV
venv="${UV_PROJECT_ENVIRONMENT:-.venv}"
export UV_PROJECT_ENVIRONMENT="$venv"
case "${1:-all}" in
  all)
    uv venv --clear --quiet "$venv"
    uv pip install --quiet --python "$venv" -e ".[dev]"
    uv run --no-sync pytest -q
    uv run --no-sync darnlang check --ext all
    ;;
  no-strict)
    uv venv --clear --quiet "$venv"
    uv pip install --quiet --python "$venv" -e . pytest        # deliberately NOT .[dev]
    uv run --no-sync pytest -q
    set +e
    uv run --no-sync darnlang prose README.md --strict
    rc=$?
    set -e
    [ "$rc" = "3" ] || { echo "expected rc=3 from --strict without the extra, got $rc"; exit 1; }
    ;;
  *)
    echo "usage: check.sh [all|no-strict]" >&2
    exit 2
    ;;
esac
