"""Small builders that keep fixture JSON out of the test bodies."""
from __future__ import annotations


def unit(value: str = "hola", state: str = "translated") -> dict:
    return {"stringUnit": {"state": state, "value": value}}


def entry(localizations: dict, *, should_translate: bool | None = None,
          extraction_state: str | None = None) -> dict:
    e: dict = {"localizations": localizations}
    if should_translate is not None:
        e["shouldTranslate"] = should_translate
    if extraction_state is not None:
        e["extractionState"] = extraction_state
    return e


def catalog(strings: dict, source_language: str = "en") -> dict:
    return {
        "sourceLanguage": source_language,
        "strings": strings,
        "version": "1.0",
    }


def plural_localization(cases: dict) -> dict:
    """``cases`` maps plural category (one/other/…) → (value, state) or just value."""
    by_case = {}
    for cat, v in cases.items():
        if isinstance(v, tuple):
            value, state = v
        else:
            value, state = v, "translated"
        by_case[cat] = {"stringUnit": {"state": state, "value": value}}
    return {"variations": {"plural": by_case}}
