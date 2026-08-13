"""darnlang — keep a repository's prose in one language, with a ratchet.

Public API is small on purpose; the command line is the product.
"""
from .baseline import Baseline, coverage_changed, load, save
from .detect import ESCAPE, build_pattern, is_prose, offending
from .project import baseline_path, project_root
from .scan import Hit, NothingToScan, scan_diff, scan_prose, scan_tree

__version__ = "0.6.0"
__all__ = [
    "Baseline", "ESCAPE", "Hit", "__version__", "baseline_path", "build_pattern",
    "coverage_changed", "is_prose", "load", "offending", "project_root", "save",
    "NothingToScan", "scan_diff", "scan_prose", "scan_tree",
]
