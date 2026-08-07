"""State semantics.

- ``translated`` counts.
- ``needs_review`` counts by default (Xcode ships it in-app).
- ``new`` never counts — it's the placeholder Xcode inserts for keys the
  extractor found but no human has touched yet.
- Under ``--strict-states``, only ``translated`` counts (``needs_review`` no
  longer does).
- An absent language never counts.
- An empty-value ``stringUnit`` never counts, regardless of state.
"""
from _helpers import catalog, entry, unit
from xcstrings_gate import (
    DEFAULT_OK_STATES,
    STRICT_OK_STATES,
    current_violations,
)


LANGS = ["es", "pt-BR"]


def _cat(es_state=None, pt_state=None, es_val="hola", pt_val="olá"):
    loc = {}
    if es_state is not None:
        loc["es"] = unit(es_val, es_state)
    if pt_state is not None:
        loc["pt-BR"] = unit(pt_val, pt_state)
    return catalog({"k": entry(loc)})


def test_translated_counts_default():
    assert current_violations(_cat("translated", "translated"), LANGS, DEFAULT_OK_STATES) == {}


def test_needs_review_counts_default():
    assert current_violations(_cat("needs_review", "needs_review"), LANGS, DEFAULT_OK_STATES) == {}


def test_new_never_counts():
    v = current_violations(_cat("new", "translated"), LANGS, DEFAULT_OK_STATES)
    assert v == {"k": ["es"]}


def test_absent_language_never_counts():
    v = current_violations(_cat("translated", None), LANGS, DEFAULT_OK_STATES)
    assert v == {"k": ["pt-BR"]}


def test_empty_value_never_counts():
    v = current_violations(_cat("translated", "translated", es_val=""), LANGS, DEFAULT_OK_STATES)
    assert v == {"k": ["es"]}


def test_strict_states_drops_needs_review():
    v = current_violations(_cat("needs_review", "translated"), LANGS, STRICT_OK_STATES)
    assert v == {"k": ["es"]}


def test_strict_states_keeps_translated():
    v = current_violations(_cat("translated", "translated"), LANGS, STRICT_OK_STATES)
    assert v == {}


def test_multiple_missing_langs_reported_in_order():
    v = current_violations(_cat("new", "new"), LANGS, DEFAULT_OK_STATES)
    assert v == {"k": ["es", "pt-BR"]}
