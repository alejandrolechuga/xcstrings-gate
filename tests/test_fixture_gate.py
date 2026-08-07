"""End-to-end sanity check on the packaged fixture.

Runs ``current_violations`` against ``fixtures/Sample.xcstrings`` and asserts
the exact expected violation set. This pins the fixture's semantics — if
someone edits the fixture (e.g. to add a new serializer case) without
thinking, this test forces them to update the expectations too.
"""
from __future__ import annotations

import json
from pathlib import Path

from xcstrings_gate import (
    DEFAULT_OK_STATES,
    STRICT_OK_STATES,
    current_violations,
)


FIXTURE = Path(__file__).parent / "fixtures" / "Sample.xcstrings"


def _load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_default_states_expected_violations():
    # All translated + Café's pt-BR is `needs_review` (counts by default).
    # `Continue` is stale → skipped. `•` is shouldTranslate:false → skipped.
    # The empty-string key has empty localizations → both langs missing.
    # `Version %@` and the plural / device variations are fully translated.
    v = current_violations(_load(), ["es", "pt-BR"], DEFAULT_OK_STATES)
    assert v == {"": ["es", "pt-BR"]}


def test_fixture_strict_states_flags_needs_review():
    # Under --strict-states, Café's pt-BR (needs_review) no longer counts.
    v = current_violations(_load(), ["es", "pt-BR"], STRICT_OK_STATES)
    assert v == {
        "": ["es", "pt-BR"],
        "Café": ["pt-BR"],
    }


def test_fixture_added_third_language_flags_all_untranslated():
    # Adopters adding a new required language should see every enforced key
    # with no entry for that language flagged — this is exactly the case the
    # per-language baseline shape was designed for.
    v = current_violations(_load(), ["es", "pt-BR", "fr"], DEFAULT_OK_STATES)
    # Only enforced keys (not `Continue`/stale, not `•`/shouldTranslate:false).
    enforced = {"", "%lld items", "Cancel", "Café", "Device banner", "Version %@"}
    assert set(v) == enforced
    for k in enforced - {""}:
        assert "fr" in v[k], f"{k!r} should be flagged missing 'fr'"
