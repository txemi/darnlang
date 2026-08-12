"""What counts as foreign-language prose, and what counts as prose at all.

This module is the whole opinion of the tool. Everything else is plumbing.

THE PROBLEM IT SOLVES. Spanish and English share an alphabet, so the usual trick — flag characters
outside ASCII — misses about a third of the Spanish written in these repos, the third with no
accents. Measured before this was written, not assumed. So detection is three layers, cheapest
first, and each one is opt-in-able because each one costs something different:

  1. accented characters and inverted punctuation  (free, and never wrong on its own)
  2. a wordlist of function words that are NOT also English words  (free, needs curating)
  3. `langdetect` on the whole line  (a dependency; only with the `strict` extra)

WHAT COUNTS AS PROSE is the other half, and the half that is usually got wrong. A gate that judges
every line of a `.py` file fires on identifiers; a gate that judges a `.md` with the rule written
for `.py` sees almost nothing, because that rule rejects any line carrying `:` or `(` — which is
most of a written paragraph. Both mistakes have been made in this codebase's ancestors, both were
measured, and both are why `is_prose` takes the file family as an argument.
"""
from __future__ import annotations

import re

#: The escape hatch. A substring, deliberately: `# lang-ok` in code, `<!-- lang-ok -->` in Markdown,
#: `lang-ok` anywhere in a commit message. The detector is a heuristic and says so; a heuristic
#: without an override is a heuristic you end up bypassing wholesale.
ESCAPE = "lang-ok"

# Spanish function words that are NOT also common English words, nor common code identifiers.
#
# Absent on purpose: `no`, `final`, `total`, `real`, `error`, `base` — identical in both languages,
# they would fire on nearly every English comment, which is how a gate earns its way into
# `--no-verify`.
#
# Two words were removed after measuring, and the measurements are the point:
#
#   `sin` — it is the SINE function. In an audio/DSP repo it produced 3 of 7 hits, every one on
#           impeccable English ("since math.sin is a looping function").
#   `solo` — an ordinary English word. "Fine solo; with several sessions it is not" was 1 of the
#           8 hits in the first sweep of a repo's pull requests.
#
# In both cases the loss is small and known: Spanish prose containing them almost always trips
# another word in this list, and the accented forms are still caught by the character class.
_WORDS = (
    r"que|para|con|los|las|del|por|una|como|pero|desde|cuando|porque|sobre|hasta|"  # lang-ok
    r"as[ií]|aqu[ií]|esto|esta|este|ese|esa|cada|hay|ser|est[aá]n?|son|"  # lang-ok
    r"tiene|hace|puede|debe|siempre|nunca|tambi[eé]n|adem[aá]s|entonces|aunque|mientras|"  # lang-ok
    r"antes|despu[eé]s|ahora|luego|donde|qui[eé]n|cu[aá]l|nada|algo|otro|otra|mismo|misma"  # lang-ok
)
_CHARS = r"[áéíóúñ¿¡]"
DEFAULT_PATTERN = re.compile(rf"\b(?:{_WORDS})\b|{_CHARS}", re.IGNORECASE)

#: Accents alone, for repos that want the zero-false-positive layer and nothing else.
CHARS_ONLY = re.compile(_CHARS)

_FENCE = re.compile(r"^\s*(?:```|~~~)")
_INLINE_CODE = re.compile(r"`[^`]*`")
_URL = re.compile(r"https?://\S+")
_CODE_PUNCT = re.compile(r"[=(){}\[\];:]|^\s*(def|class|import|from|return|del)\b")

#: File families. `code` means "only comments and docstrings are prose"; `doc` means "everything is
#: prose except fenced blocks". Anything not listed is treated as `doc`, because a file type nobody
#: classified is far more likely to be text than to be Python.
CODE_EXTS = frozenset({".py", ".pyi"})
DOC_EXTS = frozenset({".md", ".markdown", ".rst", ".txt", ".html", ".htm", ".jinja", ".j2"})


def build_pattern(words: list[str] | None) -> re.Pattern[str]:
    """The detector regex, from a caller-supplied wordlist (or the built-in one when None).

    A repo can hand its own list — the reason being that a curated list beats a clever regex for
    short prose, and the person who knows which words matter in a given codebase is the person who
    works in it, not the tool author.
    """
    if words is None:
        return DEFAULT_PATTERN
    if not words:
        return CHARS_ONLY
    alt = "|".join(re.escape(w) for w in words)
    return re.compile(rf"\b(?:{alt})\b|{_CHARS}", re.IGNORECASE)


def strip_verbatim(line: str) -> str:
    """Drop what is not language: inline `code` spans and URLs.

    Without this, documentation is unjudgeable. `docs/investigacion.md` is not a sentence in another
    language, it is an identifier that happens to spell one — and a gate that fires on identifiers
    is a gate that gets bypassed.
    """
    return _URL.sub("", _INLINE_CODE.sub("", line))


def is_commentish(line: str) -> bool:
    """Code-family prose: a comment, a docstring delimiter, or a line that reads like prose.

    Intentionally crude. A user-facing string literal in Spanish is missed, and that is the right
    trade: a stricter parser costs false positives on data (URLs, fixtures, sample content) that
    nobody wants to translate.

    `del` is in the keyword list for a reason that took measuring to see: `del frame` is a whole
    statement with no punctuation, so without it the line reads as prose and `del` — high-signal
    Spanish — fires on real code.
    """
    s = line.strip()
    if s.startswith("#"):
        return True
    if '"""' in s or "'''" in s:
        return True
    return bool(s) and not _CODE_PUNCT.search(s)


def family(path: str) -> str:
    """`code` or `doc`, by extension. Unknown extensions are `doc` — see CODE_EXTS."""
    dot = path.rfind(".")
    ext = path[dot:].lower() if dot != -1 else ""
    return "code" if ext in CODE_EXTS else "doc"


def is_prose(path: str, line: str, in_fence: bool = False) -> bool:
    """Whether this line should be read as language at all.

    Docs invert the default: everything is prose EXCEPT fenced blocks, whereas in code everything is
    code EXCEPT comments and docstrings. This asymmetry is the fix for a measured bug — a sibling
    tool opened `.html` to its scan but kept the code rule, so the 320-line Spanish interface
    template that motivated the change stayed invisible line by line.
    """
    if family(path) == "doc":
        return not in_fence and bool(strip_verbatim(line).strip())
    return is_commentish(line)


def is_fence(line: str) -> bool:
    return bool(_FENCE.match(line))


def offending(line: str, path: str, pattern: re.Pattern[str], in_fence: bool = False) -> bool:
    """The whole judgment for one line."""
    if ESCAPE in line:
        return False
    if not is_prose(path, line, in_fence):
        return False
    text = strip_verbatim(line) if family(path) == "doc" else line
    return bool(pattern.search(text))


def langdetect_says_foreign(text: str, langs: frozenset[str]) -> bool:
    """Layer 3. Requires the `strict` extra; absent, the caller must not call this.

    Kept behind an extra on purpose. The zero-dependency path is what lets this run first in a
    pre-commit that fires dozens of times a day; `langdetect` needs a resolved environment, which is
    exactly the cost that turns a local gate into a silent no-op on an unprovisioned machine.
    """
    from langdetect import LangDetectException, detect  # noqa: PLC0415  (optional dependency)

    try:
        return detect(text) in langs
    except LangDetectException:
        return False
