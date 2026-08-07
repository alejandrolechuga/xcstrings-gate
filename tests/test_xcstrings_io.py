"""Format-preserving serializer.

Byte-for-byte round-trip against a self-contained fixture that exercises
every code path the serializer must handle (flat ``stringUnit`` entries,
plural + device ``variations``, ``shouldTranslate: false``, ``stale`` /
``manual`` extraction states, empty localizations, Unicode, format
specifiers, an empty string key), plus targeted micro-fixtures for the
fiddly formatting rules Xcode uses.

The fixture lives inside the package so the test runs standalone —
critical because this package must remain lift-safe (copy-out to a fresh
repo), and a test that reached out to a sibling app catalog would
silently ``skipif`` in that context.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from xcstrings_io import dumps


FIXTURE = Path(__file__).parent / "fixtures" / "Sample.xcstrings"


def test_empty_object_uses_blank_line_form():
    # Xcode: {\n\n<indent>}. At depth 0 that's exactly "{\n\n}".
    assert dumps({}) == "{\n\n}"


def test_empty_array_uses_blank_line_form():
    assert dumps([]) == "[\n\n]"


def test_scalar_object_uses_space_around_colon():
    # Two-space indent + " : " colon spacing is the Xcode signature.
    out = dumps({"a": 1})
    assert out == '{\n  "a" : 1\n}'


def test_nested_indent():
    out = dumps({"outer": {"inner": "v"}})
    assert out == '{\n  "outer" : {\n    "inner" : "v"\n  }\n}'


def test_unicode_is_not_escaped():
    # ensure_ascii=False, otherwise diffs blow up on every accented character.
    assert dumps({"k": "olá"}) == '{\n  "k" : "olá"\n}'


def test_preserves_insertion_order_not_sorted():
    # Documents the "ordering caveat" from the module docstring: we do NOT
    # sort keys, we preserve insertion order (which round-trips existing
    # Xcode-written files exactly, because their order is already baked in).
    out = dumps({"b": 1, "a": 2})
    assert out.index('"b"') < out.index('"a"')


def test_no_trailing_newline():
    # Xcode itself writes no trailing newline. Emitting one would produce a
    # spurious 1-line diff every time we touch the file.
    assert not dumps({"a": 1}).endswith("\n")


def test_dumps_matches_json_roundtrip_semantically():
    # Whatever we emit must still parse to the same object.
    obj = {"strings": {"k": {"localizations": {"es": {"stringUnit": {"state": "translated", "value": "hola"}}}}}}
    assert json.loads(dumps(obj)) == obj


def test_fixture_round_trip_byte_for_byte():
    """The real load-bearing test: round-trip a full realistic catalog.

    The fixture is hand-crafted to hit every serializer code path (see the
    module docstring). Anything that breaks Xcode-format compatibility — an
    accidentally-sorted key list, a dropped blank line in an empty object,
    a colon-spacing regression — will diverge here.
    """
    raw = FIXTURE.read_text(encoding="utf-8")
    obj = json.loads(raw)
    out = dumps(obj)
    if out != raw:
        # Surface the first divergence to make regressions debuggable.
        for i, (x, y) in enumerate(zip(raw.splitlines(), out.splitlines()), start=1):
            if x != y:
                pytest.fail(f"diverge at line {i}\n  orig: {x!r}\n  ours: {y!r}")
        pytest.fail(f"length mismatch: orig={len(raw)} ours={len(out)}")
