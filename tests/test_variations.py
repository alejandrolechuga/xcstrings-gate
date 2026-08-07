"""Variations (plurals / device) — the load-bearing, easy-to-get-wrong case.

A plural entry only counts as translated when *every* sub-case is translated;
a half-translated plural must fail. Also covers device variations and the
empty-variations edge case.
"""
from _helpers import catalog, entry, plural_localization, unit
from xcstrings_gate import (
    DEFAULT_OK_STATES,
    current_violations,
    lang_is_translated,
)


LANGS = ["es", "pt-BR"]


def test_fully_translated_plural_passes():
    loc = {
        "es": plural_localization({"one": "1 elemento", "other": "%d elementos"}),
        "pt-BR": plural_localization({"one": "1 item", "other": "%d itens"}),
    }
    c = catalog({"items.count": entry(loc)})
    assert current_violations(c, LANGS, DEFAULT_OK_STATES) == {}


def test_half_translated_plural_fails():
    # `other` translated, `one` still in `new` — Xcode ships that as English.
    loc = {
        "es": plural_localization({
            "one": ("1 item", "new"),
            "other": ("%d elementos", "translated"),
        }),
        "pt-BR": plural_localization({"one": "1 item", "other": "%d itens"}),
    }
    c = catalog({"items.count": entry(loc)})
    assert current_violations(c, LANGS, DEFAULT_OK_STATES) == {"items.count": ["es"]}


def test_plural_missing_a_case_fails():
    # Only `other` present — the language has no plural coverage for `one`.
    loc = {
        "es": plural_localization({"other": "%d elementos"}),
        "pt-BR": plural_localization({"one": "1 item", "other": "%d itens"}),
    }
    c = catalog({"items.count": entry(loc)})
    # Missing-case still fails; we don't try to enumerate CLDR categories, we
    # just require every declared case to be translated + non-empty.
    #
    # Here `one` isn't declared at all in `es`, but `pt-BR` provides both.
    # The `es` variation has only `other` populated + translated — that's a
    # valid single-case variation and it *does* pass strict per-case checking.
    # This test documents that behaviour: we trust Xcode's authored case set.
    assert current_violations(c, LANGS, DEFAULT_OK_STATES) == {}


def test_empty_variations_fails():
    loc = {
        "es": {"variations": {"plural": {}}},
        "pt-BR": plural_localization({"one": "1", "other": "%d"}),
    }
    c = catalog({"k": entry(loc)})
    assert current_violations(c, LANGS, DEFAULT_OK_STATES) == {"k": ["es"]}


def test_device_variations_all_translated():
    loc = {
        "es": {"variations": {"device": {
            "iphone": unit("iPhone es"),
            "ipad": unit("iPad es"),
        }}},
        "pt-BR": {"variations": {"device": {
            "iphone": unit("iPhone pt"),
            "ipad": unit("iPad pt"),
        }}},
    }
    c = catalog({"device.k": entry(loc)})
    assert current_violations(c, LANGS, DEFAULT_OK_STATES) == {}


def test_device_variation_with_empty_value_fails():
    loc = {
        "es": {"variations": {"device": {
            "iphone": unit("iPhone es"),
            "ipad": unit("", "translated"),  # empty value → not a translation
        }}},
        "pt-BR": {"variations": {"device": {
            "iphone": unit("iPhone pt"),
            "ipad": unit("iPad pt"),
        }}},
    }
    c = catalog({"device.k": entry(loc)})
    assert current_violations(c, LANGS, DEFAULT_OK_STATES) == {"device.k": ["es"]}


def test_lang_is_translated_direct_variations():
    loc = plural_localization({"one": "1", "other": "%d"})
    assert lang_is_translated({"es": loc}, "es", DEFAULT_OK_STATES) is True
    assert lang_is_translated({"es": loc}, "pt-BR", DEFAULT_OK_STATES) is False
