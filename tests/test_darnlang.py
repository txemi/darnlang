"""Tests for darnlang.

They pin the DECISIONS, not the dictionary: what counts as prose per file family, what is exempt,
how the two path resolutions stay in step, and what a coverage change is called. Every one of them
corresponds to a bug that actually happened in the vendored ancestors of this tool — which had no
tests at all, and that is how the bugs survived.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from darnlang import baseline as bl
from darnlang.cli import main
from darnlang.detect import DEFAULT_PATTERN, build_pattern, offending
from darnlang.project import baseline_path, project_root
from darnlang.scan import scan_prose, scan_tree

SPANISH_DOC = "La receta falla abierta por defecto: un commit offline no se bloquea"
SPANISH_HTML = f"<p>{SPANISH_DOC}</p>"


def _repo(tmp_path, files: dict[str, str]):
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def _run(argv, cwd) -> int:
    old = os.getcwd()
    os.chdir(cwd)
    try:
        return main(argv)
    finally:
        os.chdir(old)


# --- the prose rule, per family ---------------------------------------------------------------

def test_markdown_paragraph_is_judged_although_it_carries_code_punctuation():
    """The bug that let Spanish sit in a CHANGELOG under a green gate: the code rule rejects any
    line with `:` or `(`, which is most of a written paragraph."""
    assert offending(SPANISH_DOC, "CHANGELOG.md", DEFAULT_PATTERN)
    assert not offending(SPANISH_DOC, "CHANGELOG.md", DEFAULT_PATTERN, in_fence=True)


def test_html_interface_text_is_judged():
    """The bug NO ancestor fixed. One opened `.html` to the scan but kept the code rule, so a
    320-line Spanish interface template stayed invisible line by line."""
    assert offending(SPANISH_HTML, "views/index.html", DEFAULT_PATTERN)


def test_python_is_still_judged_by_the_comment_rule():
    assert offending("# esto no puede pasar aqui", "x.py", DEFAULT_PATTERN)
    assert not offending("total = para_value + 1", "x.py", DEFAULT_PATTERN)


def test_unknown_extension_is_treated_as_prose_not_as_code():
    assert offending(SPANISH_DOC, "notes.adoc", DEFAULT_PATTERN)


@pytest.mark.parametrize("line", [
    "See `docs/investigacion-de-errores.md` for the details.",
    "See https://example.invalid/una-pagina-con-nombre-largo for the details.",
    f"{SPANISH_DOC}  lang-ok",
])
def test_identifiers_urls_and_the_escape_hatch_are_exempt(line):
    assert not offending(line, "README.md", DEFAULT_PATTERN)


def test_solo_and_sin_are_english_words_and_do_not_fire():
    assert not scan_prose("Fine solo; with several sessions it is not.", DEFAULT_PATTERN)
    assert not scan_prose("since math.sin is a looping function", DEFAULT_PATTERN)
    assert scan_prose("sólo se comprueba al escribir", DEFAULT_PATTERN)


# --- free prose: the surfaces a file gate cannot see -------------------------------------------

def test_git_template_comments_are_not_judged():
    """git writes its template in the machine's LOCALE. Judging it fails the author for text they
    did not write and git is about to strip."""
    msg = "fix: keep the fence state per file\n\n# Por favor ingresa el mensaje de confirmacion\n"
    assert not scan_prose(msg, DEFAULT_PATTERN, git_comments=True)
    assert scan_prose(msg, DEFAULT_PATTERN)  # …so the exemption is the flag's doing


def test_verbose_commit_diff_below_the_scissors_is_not_judged():
    msg = ("fix: something\n"
           "# ------------------------ >8 ------------------------\n"
           "+# esto es una linea del diff que git pega con --verbose\n")
    assert not scan_prose(msg, DEFAULT_PATTERN, git_comments=True)


def test_fenced_output_pasted_into_an_issue_is_not_judged():
    body = ("The gate misses this case:\n\n```\n"
            "docs/investigacion.md: enlace roto para el destino que no existe\n"
            "```\n\nExpected: a finding.\n")
    assert not scan_prose(body, DEFAULT_PATTERN)


def test_prose_mode_exit_codes(tmp_path):
    (tmp_path / "msg.txt").write_text(SPANISH_DOC, encoding="utf-8")
    assert _run(["prose", str(tmp_path / "msg.txt")], tmp_path) == 1
    (tmp_path / "ok.txt").write_text("gate the surfaces that get published", encoding="utf-8")
    assert _run(["prose", str(tmp_path / "ok.txt")], tmp_path) == 0


def test_an_unreadable_message_fails_closed(tmp_path):
    """This mode exists for the surfaces nothing else watches; unreadable is not clean."""
    assert _run(["prose", str(tmp_path / "nope.txt")], tmp_path) == 3


# --- one root, two derived values ---------------------------------------------------------------

def test_the_scanned_tree_and_the_baseline_come_from_the_same_root(tmp_path):
    """The bug this tool was extracted over: two parallel resolutions drifted, and the gate
    congratulated a repo on debt it had never looked at. They are derived now, so they cannot."""
    repo = _repo(tmp_path / "repo", {"a.py": "# hola que tal esto es prosa\n"})
    sub = repo / "deep" / "deeper"
    sub.mkdir(parents=True)
    root = project_root(str(sub))
    assert os.path.realpath(root) == os.path.realpath(str(repo))
    assert baseline_path(root).startswith(os.path.realpath(str(repo)))


def test_running_from_a_subdirectory_gives_the_same_verdict(tmp_path):
    repo = _repo(tmp_path / "repo", {"a.py": "# hola que tal, esto es prosa\n"})
    sub = repo / "sub"
    sub.mkdir()
    assert _run(["update-baseline"], repo) == 0
    assert _run(["check"], repo) == 0
    assert _run(["check"], sub) == 0


def test_a_legacy_baseline_location_is_still_honoured(tmp_path):
    repo = _repo(tmp_path / "repo", {"tools/lang_gate_baseline.json":
                                     json.dumps({"count": 0, "files": {}})})
    assert baseline_path(project_root(str(repo))).endswith(
        os.path.join("tools", "lang_gate_baseline.json"))


# --- the ratchet, and what a coverage change is called ------------------------------------------

def test_a_clean_repo_is_fail_closed_at_zero(tmp_path):
    repo = _repo(tmp_path / "repo", {"a.py": "# perfectly ordinary english\n"})
    assert _run(["update-baseline"], repo) == 0
    assert _run(["check"], repo) == 0
    (repo / "b.py").write_text("# esto es prosa que no deberia estar aqui\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    assert _run(["check"], repo) == 1


def test_widening_coverage_is_reported_as_an_adoption_not_as_a_regression(tmp_path):
    """Reported as "the count GREW -- do NOT raise the baseline", the advice would be backwards:
    re-seeding once IS the correct move when the tool starts judging more."""
    repo = _repo(tmp_path / "repo", {"a.py": "# english only here\n", "DOC.md": SPANISH_DOC + "\n"})
    assert _run(["update-baseline"], repo) == 0            # covers .py, count 0
    assert _run(["check", "--ext", ".py,.md"], repo) == 2  # coverage changed -> its own code
    assert _run(["update-baseline", "--ext", ".py,.md"], repo) == 0
    assert _run(["check", "--ext", ".py,.md"], repo) == 0  # re-seeded: the debt is now the floor


def test_a_baseline_predating_the_field_is_not_a_coverage_change(tmp_path):
    """Consumers on the old format have no `scanned_exts`. Absent must mean "unknown", not
    "empty", or every one of them fails on a key it has never heard of."""
    repo = _repo(tmp_path / "repo", {"a.py": "# english\n"})
    bl.save(baseline_path(project_root(str(repo))), 0, [".py"], {})
    data = json.loads((repo / ".darnlang-baseline.json").read_text(encoding="utf-8"))
    del data["scanned_exts"]
    (repo / ".darnlang-baseline.json").write_text(json.dumps(data), encoding="utf-8")
    assert _run(["check"], repo) == 0


def test_a_missing_baseline_is_an_environment_error_not_a_pass(tmp_path):
    repo = _repo(tmp_path / "repo", {"a.py": "# english\n"})
    assert _run(["check"], repo) == 3


# --- file names ---------------------------------------------------------------------------------

def test_file_names_are_judged_too(tmp_path):
    """No ancestor did this, it costs nothing, and a file name is exactly as public as its
    contents."""
    repo = _repo(tmp_path / "repo", {"análisis_errores.py": "# english inside\n"})
    hits = scan_tree(str(repo), (".py",), DEFAULT_PATTERN)
    assert any(h.code == "filename" for h in hits)
    assert not any(h.code == "filename"
                   for h in scan_tree(str(repo), (".py",), DEFAULT_PATTERN, filenames=False))


def test_the_built_in_wordlist_barely_helps_on_file_names(tmp_path):
    """Stated as a test rather than left to be discovered: the built-in list is FUNCTION words, and
    file names are made of CONTENT words, so unaccented names slip through. Accents catch them, and
    a repo wordlist with content words catches the rest. Pinning it here so nobody reads
    `filenames=True` as a guarantee it cannot give."""
    repo = _repo(tmp_path / "repo", {"analisis_errores.py": "# english inside\n"})
    assert not [h for h in scan_tree(str(repo), (".py",), DEFAULT_PATTERN) if h.code == "filename"]
    custom = build_pattern(["analisis", "errores"])
    assert [h for h in scan_tree(str(repo), (".py",), custom) if h.code == "filename"]


# --- the wordlist ---------------------------------------------------------------------------------

def test_a_repo_wordlist_replaces_the_built_in_one():
    pattern = build_pattern(["gaztelania"])
    assert pattern.search("hau gaztelania da")
    assert not pattern.search("esto que tal")   # built-in words are gone…
    assert pattern.search("una decisión")       # …but accents always count


# --- "I examined nothing" is not "I found nothing" ----------------------------------------------

def test_a_repo_with_nothing_committed_is_an_error_not_a_clean_scan(tmp_path):
    """The trap this tool fell into on its own first commit: the baseline was seeded before the
    files were committed, `git ls-files` returned nothing, and the tool cheerfully wrote `count: 0`.
    That zero would then have become the floor the ratchet defends — a gate calibrated against
    nothing, green forever."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("# hola que tal esto es prosa\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)  # note: nothing added
    assert _run(["update-baseline"], repo) == 3
    assert _run(["check"], repo) == 3
    assert not (repo / ".darnlang-baseline.json").exists()


def test_scanning_a_tree_where_no_file_matches_the_extensions_is_an_error(tmp_path):
    repo = _repo(tmp_path / "repo", {"README.md": "english only\n"})
    assert _run(["update-baseline", "--ext", ".py"], repo) == 3


# --- layer 3, and refusing to answer when it cannot run -----------------------------------------

def _has_langdetect() -> bool:
    try:
        import langdetect  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.skipif(not _has_langdetect(), reason="needs the 'strict' extra")
def test_layer_three_catches_what_the_cheap_layers_cannot(tmp_path):
    """The justification for the extra, measured rather than assumed: prose with no accents and none
    of the dictionary's function words is invisible to layers 1 and 2."""
    msg = tmp_path / "m.txt"
    msg.write_text("Compilamos el proyecto usando herramientas modernas y guardamos resultados.\n",
                   encoding="utf-8")
    assert _run(["prose", str(msg)], tmp_path) == 0             # layers 1+2 see nothing
    assert _run(["prose", str(msg), "--strict"], tmp_path) == 1  # layer 3 sees it


def test_there_is_no_tree_level_strict(tmp_path):
    """Removed after measuring 11 findings on this repo's own English tree, 8 of them plainly
    English. langdetect classifies a SENTENCE; a line of a document is a fragment. Pinned so nobody
    reintroduces it as an obvious-looking feature."""
    repo = _repo(tmp_path / "repo", {"a.py": "# english\n"})
    assert _run(["update-baseline"], repo) == 0
    with pytest.raises(SystemExit):        # argparse rejects the flag
        _run(["check", "--strict"], repo)


@pytest.mark.skipif(_has_langdetect(), reason="only meaningful without the extra")
def test_strict_without_the_extra_refuses_instead_of_reporting_clean(tmp_path):
    """It used to warn and carry on, which means a caller who asked for the deep layer, did not get
    it, and saw exit 0 was told the tree is clean by a check that never ran."""
    repo = _repo(tmp_path / "repo", {"a.py": "# english\n"})
    assert _run(["update-baseline"], repo) == 0
    assert _run(["check", "--strict"], repo) == 3


@pytest.mark.skipif(not _has_langdetect(), reason="needs the 'strict' extra")
def test_strict_prose_catches_a_short_commit_subject_the_wordlist_cannot(tmp_path):
    """Found by dogfooding, on the very commit that migrated the first repo to this tool: "migra el
    gate de idioma al paquete darnlang" carries no accent and none of the dictionary's function
    words, so the cheap layers pass it. A commit subject is short by nature — the case a stopword
    list cannot cover."""
    msg = tmp_path / "msg.txt"
    msg.write_text("migra el gate de idioma al paquete darnlang\n", encoding="utf-8")
    assert _run(["prose", str(msg)], tmp_path) == 0             # layers 1+2 miss it
    assert _run(["prose", str(msg), "--strict"], tmp_path) == 1  # layer 3 catches it


@pytest.mark.skipif(not _has_langdetect(), reason="needs the 'strict' extra")
def test_strict_prose_does_not_fire_on_english():
    """langdetect labelled that same Spanish subject as CATALAN, which is why layer 3 asks "is this
    NOT English" rather than "is this Spanish". The cost of that framing is false positives on
    English, so it is pinned here."""
    import tempfile
    for text in ("migrates the language gate to the darnlang package\n",
                 "fix: derive the scanned tree and the baseline from one root\n",
                 "docs: Jenkins, which the wiring section had left out\n"):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
            fh.write(text)
            path = fh.name
        assert main(["prose", path, "--strict"]) == 0, text


# --- scan_diff: the path the pre-commit hook runs, and the one that had no tests --------------
#
# Three of the four false GREENs found in the first adversarial review lived here, in the only
# public function of the package with zero coverage. A mutation that made it judge just the first
# added line per file left the whole suite green.

def _staged(tmp_path, files: dict[str, str], *, seed: str = "# english seed\n"):
    repo = _repo(tmp_path / "repo", {"seed.py": seed})
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed"],
                   cwd=repo, check=True)
    for rel, body in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    return repo


SPANISH_LINE = "# esto es prosa que no deberia estar aqui para nada\n"


def test_diff_sees_a_file_whose_NAME_is_not_ascii(tmp_path):
    """git renders a non-ASCII path as an escaped C string, so the `+++ b/…` header did not match
    and every added line in that file was skipped. The file most likely to be NAMED in the wrong
    language is the file most likely to contain it."""
    repo = _staged(tmp_path, {"análisis.py": SPANISH_LINE})
    assert _run(["check", "--diff"], repo) == 1


def test_a_diff_that_cannot_be_read_is_an_error_not_a_clean_diff(tmp_path):
    """It used to print "cannot read the diff -> nothing judged" and then "OK -- nothing new",
    exit 0. The tree path invented NothingToScan for exactly this; the diff path had not applied
    the doctrine — in the one place the shipped pre-commit hook runs."""
    repo = _staged(tmp_path, {"a.py": SPANISH_LINE})
    assert _run(["check", "--diff", "v9.9.9-does-not-exist"], repo) == 3


def test_content_that_looks_like_a_diff_header_does_not_hijack_the_parser(tmp_path):
    """A line reading `++ b/vendor/thing.txt` inside a document is emitted as `+++ b/…` in the
    unified diff. Treating it as a header redirected every following line to a path that was not
    being edited, and dropped them all. Any repo documenting a patch format carries this."""
    repo = _staged(tmp_path, {"doc.md": ("Documenting a patch format below.\n"
                                         "++ b/vendor/thing.txt\n"
                                         "Esta linea deberia dar un hallazgo para todos.\n")})
    assert _run(["check", "--diff", "--ext", ".md"], repo) == 1


def test_diff_judges_every_added_line_not_just_the_first(tmp_path):
    """The mutation that survived the whole suite."""
    repo = _staged(tmp_path, {"a.py": "# english first line\n" + SPANISH_LINE})
    from darnlang.scan import scan_diff
    hits = scan_diff(str(repo), None, (".py",), DEFAULT_PATTERN)
    assert len(hits) == 1 and hits[0].line == 2


def test_diff_reports_the_right_file_when_several_change(tmp_path):
    """With an ASCII file earlier in the diff, a mis-parsed header blamed the PREVIOUS file — a
    user who opens that line, finds clean English and concludes the tool lies is one step from
    --no-verify."""
    repo = _staged(tmp_path, {"aaa.py": "# plain english comment here\n", "zzz.py": SPANISH_LINE})
    from darnlang.scan import scan_diff
    hits = scan_diff(str(repo), None, (".py",), DEFAULT_PATTERN)
    assert [h.path for h in hits] == ["zzz.py"]


# --- fences, at integration level ---------------------------------------------------------------

def test_an_unbalanced_fence_does_not_swallow_the_document(tmp_path):
    """An odd number of fences used to make everything after the last one invisible: "the author
    forgot a fence" must not be a way to make a document unjudgeable."""
    repo = _repo(tmp_path / "repo", {"doc.md": ("Intro in English.\n\n```\ncode\n\n"
                                                "Esta linea deberia dar un hallazgo para todos.\n")})
    assert _run(["update-baseline", "--ext", ".md"], repo) == 0
    import json
    assert json.loads((repo / ".darnlang-baseline.json").read_text(encoding="utf-8"))["count"] == 1


def test_an_inline_code_span_at_the_start_of_a_line_is_not_a_fence(tmp_path):
    """No typo needed: ```` ```x``` is the marker ```` is ordinary Markdown, and toggling on it hid
    the rest of the file."""
    repo = _repo(tmp_path / "repo", {"doc.md": ("Intro in English.\n\n```x``` is the marker.\n"
                                                "Esta linea deberia dar un hallazgo para todos.\n")})
    assert _run(["update-baseline", "--ext", ".md"], repo) == 0
    import json
    assert json.loads((repo / ".darnlang-baseline.json").read_text(encoding="utf-8"))["count"] == 1


def test_a_real_fenced_block_is_still_exempt(tmp_path):
    repo = _repo(tmp_path / "repo", {"doc.md": ("Intro in English.\n\n```\n"
                                                "Esta linea va dentro del bloque y no cuenta.\n"  # lang-ok
                                                "```\n\nOutro in English.\n")})
    assert _run(["update-baseline", "--ext", ".md"], repo) == 0
    import json
    assert json.loads((repo / ".darnlang-baseline.json").read_text(encoding="utf-8"))["count"] == 0


# --- a file that could not be read is not a file that was clean ---------------------------------

def test_an_undecodable_file_is_reported_not_silently_skipped(tmp_path, capfd):
    """NothingToScan's twin: the list was not empty, but the element failed to open. The profile
    that hits this — legacy files in latin-1 — is exactly the profile the ratchet exists for, so the
    silence would have written a floor of 0 over real debt."""
    repo = _repo(tmp_path / "repo", {"ok.py": "# english\n"})
    (repo / "legacy.py").write_bytes("# esta funcion calcula el numero de años\n".encode("latin-1"))
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    assert _run(["update-baseline"], repo) == 0
    err = capfd.readouterr().err
    assert "could NOT be read" in err and "legacy.py" in err


# --- coverage: the direction that was never tested ----------------------------------------------

def test_coverage_going_DOWN_is_reported_and_fails(tmp_path):
    """`baseline.py` calls a shrinking coverage "how a gate loosens without anyone noticing", and
    only the growing direction had a test — so the one that matters could be deleted for free."""
    repo = _repo(tmp_path / "repo", {"a.py": "# english\n", "DOC.md": "English doc.\n"})
    assert _run(["update-baseline", "--ext", ".py,.md"], repo) == 0
    r = _run(["check", "--ext", ".py"], repo)
    assert r == 2


def test_update_baseline_refuses_to_bake_in_a_coverage_reduction(tmp_path):
    """The one command that WRITES the floor had no coverage guard at all, so a narrowed scope was
    silently baked in — and the per-file map wiped with it."""
    repo = _repo(tmp_path / "repo", {"a.py": "# english\n", "DOC.md": "English doc.\n"})
    assert _run(["update-baseline", "--ext", ".py,.md"], repo) == 0
    assert _run(["update-baseline", "--ext", ".py"], repo) == 2
