"""Enforcement exclusions.

Two — and only two — reasons the gate skips a key:

1. ``shouldTranslate: false`` (the sanctioned exception, Xcode-native).
2. ``extractionState == "stale"`` (Xcode saying "not referenced in code").
"""
from _helpers import catalog, entry, unit
from xcstrings_gate import DEFAULT_OK_STATES, current_violations, is_enforced


LANGS = ["es", "pt-BR"]


def test_should_translate_false_is_skipped():
    e = entry({"es": unit("hola")}, should_translate=False)  # pt-BR missing
    assert is_enforced(e) is False
    assert current_violations(catalog({"symbol.plus": e}), LANGS, DEFAULT_OK_STATES) == {}


def test_stale_extraction_is_skipped():
    e = entry({}, extraction_state="stale")  # nothing translated at all
    assert is_enforced(e) is False
    assert current_violations(catalog({"dead.key": e}), LANGS, DEFAULT_OK_STATES) == {}


def test_should_translate_true_is_enforced():
    # Explicit True (uncommon in real catalogs; Xcode omits the field) — still enforced.
    e = entry({"es": unit("hola")}, should_translate=True)
    assert is_enforced(e) is True
    v = current_violations(catalog({"k": e}), LANGS, DEFAULT_OK_STATES)
    assert v == {"k": ["pt-BR"]}


def test_extraction_state_manual_is_enforced():
    e = entry({"es": unit("hola")}, extraction_state="manual")
    assert is_enforced(e) is True
    v = current_violations(catalog({"k": e}), LANGS, DEFAULT_OK_STATES)
    assert v == {"k": ["pt-BR"]}


def test_default_entry_is_enforced():
    # Bare entry — no shouldTranslate, no extractionState — is enforced.
    e = entry({})
    assert is_enforced(e) is True
