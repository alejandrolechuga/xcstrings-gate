#!/usr/bin/env python3
"""Format-preserving (Xcode-matching) serializer for .xcstrings catalogs.

Xcode writes a very specific JSON dialect: 2-space indent, ``"k" : v`` (space
on both sides of the colon), and empty objects/arrays as ``{\\n\\n<ind>}``.
A vanilla ``json.dump`` reformats all 8k lines. This module round-trips
byte-for-byte so a batch edit produces a minimal diff (only the lines it
actually adds).

Known limitation
----------------
This serializer preserves **insertion order** rather than replicating Xcode's
locale-aware key collation. In practice that means:

- Round-tripping an existing catalog is byte-for-byte identical (Xcode's own
  ordering is already baked into the file we read).
- Appending locales to existing entries produces a minimal diff.
- **Creating a brand-new entry (or brand-new locale key) will land wherever
  Python's dict insertion order puts it, which may not be where Xcode would
  sort it.** Xcode will silently re-sort on the next save, producing a large
  cosmetic diff. If you need Xcode-identical ordering for greenfield writes,
  open the catalog in Xcode and save once after your tool run.

CLI
---
``python3 xcstrings_io.py <path>`` runs a self-check: load + dump and assert
the output equals the input.
"""
from __future__ import annotations

import json
import sys

INDENT = "  "


def dumps(obj) -> str:
    """Serialize ``obj`` to Xcode's xcstrings JSON dialect."""
    # Xcode writes no trailing newline.
    return _val(obj, 0)


def _val(v, depth: int) -> str:
    if isinstance(v, dict):
        return _obj(v, depth)
    if isinstance(v, list):
        return _arr(v, depth)
    return json.dumps(v, ensure_ascii=False)


def _obj(d: dict, depth: int) -> str:
    if not d:
        # Xcode renders an empty object as "{", blank line, then the closing
        # brace at the *owner* indent level (depth).
        return "{\n\n" + INDENT * depth + "}"
    pad = INDENT * (depth + 1)
    items = []
    # See module docstring for the ordering caveat.
    for k in d.keys():
        items.append(
            f'{pad}{json.dumps(k, ensure_ascii=False)} : {_val(d[k], depth + 1)}'
        )
    return "{\n" + ",\n".join(items) + "\n" + INDENT * depth + "}"


def _arr(a: list, depth: int) -> str:
    if not a:
        return "[\n\n" + INDENT * depth + "]"
    pad = INDENT * (depth + 1)
    items = [f'{pad}{_val(x, depth + 1)}' for x in a]
    return "[\n" + ",\n".join(items) + "\n" + INDENT * depth + "]"


def _self_check(path: str) -> int:
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    obj = json.loads(raw)
    out = dumps(obj)
    if out == raw:
        print("round-trip OK (byte-for-byte identical)")
        return 0
    a, b = raw.splitlines(), out.splitlines()
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            print(f"DIVERGE at line {i+1}:\n  orig: {x!r}\n  ours: {y!r}")
            return 1
    print(f"len orig={len(a)} ours={len(b)} (one is a prefix of the other)")
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: xcstrings_io.py <catalog>", file=sys.stderr)
        sys.exit(2)
    sys.exit(_self_check(sys.argv[1]))
