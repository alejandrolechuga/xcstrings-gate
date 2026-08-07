#!/usr/bin/env python3
"""xcstrings-gate — CI-native String Catalog translation-coverage ratchet.

Invariant enforced
------------------
Any *live* key in one or more Xcode ``.xcstrings`` catalog(s) must be
translated into every required language — UNLESS it is explicitly exempted
with ``"shouldTranslate": false`` in the catalog (in Xcode: select the string
→ "Don't Translate"). That flag is the one and only "skip because of
exception" mechanism: it's co-located with the string, reviewable in the PR
diff, and native to Xcode, so a reader always sees *why* a string ships
without a translation.

Ratchet
-------
Pre-existing untranslated (key, language) pairs are grandfathered in a
baseline JSON file. The gate blocks only NET-NEW violations. The baseline is
a ratchet: ``--write-baseline`` regenerates it from the current catalog. As
translation debt is paid down, re-running ``--write-baseline`` shrinks the
file; it must never grow. **Do not run ``--write-baseline`` to silence a new
violation** — that defeats the purpose of the tool.

Baseline shape (per-language)
-----------------------------
::

    {
      "required_langs": ["es", "pt-BR"],
      "keys": {
        "some.grandfathered.key": ["pt-BR"],
        "another.key": ["es", "pt-BR"]
      }
    }

Each key maps to the list of languages it is currently grandfathered for.
Adding a third required language does not force a wholesale re-baseline of
every key that only misses the new language.

Exit codes
----------
- ``0`` clean, or ``--list`` / ``--write-baseline`` succeeded
- ``1`` new untranslated (key, language) pair(s) beyond the baseline
- ``2`` usage / I/O error
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from typing import Iterable

# Localizations "count" as translated when they carry a value in one of these
# states. ``new`` is Xcode's placeholder-not-yet-translated state and does NOT
# count; an absent language does not count. With ``--strict-states``,
# ``needs_review`` is also dropped (leaving only ``translated``).
DEFAULT_OK_STATES = frozenset({"translated", "needs_review"})
STRICT_OK_STATES = frozenset({"translated"})


# ---------------------------------------------------------------------------
# Catalog inspection
# ---------------------------------------------------------------------------

def load_catalog(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def lang_is_translated(localizations: dict, lang: str, ok_states: frozenset) -> bool:
    """True when ``lang`` has a real, non-empty translation.

    Handles both flat ``stringUnit`` entries and ``variations`` (plurals /
    device): for variations, *every* sub-case must itself be translated.
    """
    loc = localizations.get(lang)
    if not loc:
        return False
    if "stringUnit" in loc:
        unit = loc["stringUnit"]
        return unit.get("state") in ok_states and bool(unit.get("value", ""))
    if "variations" in loc:
        return _variations_translated(loc["variations"], ok_states)
    return False


def _variations_translated(variations: dict, ok_states: frozenset) -> bool:
    cases = []
    for _kind, by_case in variations.items():  # e.g. "plural", "device"
        if not isinstance(by_case, dict) or not by_case:
            return False
        cases.extend(by_case.values())
    if not cases:
        return False
    for case in cases:
        unit = case.get("stringUnit", {})
        if unit.get("state") not in ok_states or not unit.get("value", ""):
            return False
    return True


def is_enforced(entry: dict) -> bool:
    """Whether this key is subject to the gate.

    Excluded:
      - ``shouldTranslate: false``  → explicit exception (the escape hatch).
      - ``extractionState == "stale"`` → key no longer referenced in code;
        dead weight, not a shipping string.
    """
    if entry.get("shouldTranslate") is False:
        return False
    if entry.get("extractionState") == "stale":
        return False
    return True


def current_violations(
    catalog: dict, required_langs: Iterable[str], ok_states: frozenset
) -> dict:
    """Return ``{key: [missing_langs]}`` for every enforced key missing >=1 lang."""
    out: dict[str, list[str]] = {}
    for key, entry in catalog.get("strings", {}).items():
        if not is_enforced(entry):
            continue
        loc = entry.get("localizations", {})
        missing = [
            lang for lang in required_langs
            if not lang_is_translated(loc, lang, ok_states)
        ]
        if missing:
            out[key] = missing
    return out


def aggregate_violations(
    catalog_paths: list[str], required_langs: list[str], ok_states: frozenset
) -> dict:
    """Merge per-catalog violation maps into a single ``{key: [missing_langs]}``.

    When the same key appears in multiple catalogs (rare, but possible with
    per-target modularization), the union of missing languages wins.
    """
    merged: dict[str, set[str]] = {}
    for p in catalog_paths:
        cat = load_catalog(p)
        for k, missing in current_violations(cat, required_langs, ok_states).items():
            merged.setdefault(k, set()).update(missing)
    # Sort langs by their position in required_langs for stable output.
    order = {lang: i for i, lang in enumerate(required_langs)}
    return {k: sorted(v, key=lambda l: order.get(l, len(order))) for k, v in merged.items()}


# ---------------------------------------------------------------------------
# Baseline I/O (per-language shape)
# ---------------------------------------------------------------------------

def load_baseline(path: str) -> dict:
    """Load a per-language baseline into ``{key: [langs]}``.

    Missing file → empty. Also transparently migrates the legacy flat shape
    (``{"keys": ["k1", "k2"], "required_langs": [...]}``) into the new
    per-language shape at read time, applying every ``required_langs`` entry
    to every baselined key. That preserves ratchet semantics for a repo that
    hasn't yet run ``--write-baseline`` since upgrading.
    """
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw_keys = data.get("keys", {})
    if isinstance(raw_keys, list):
        # legacy flat shape
        langs = list(data.get("required_langs", []))
        return {k: list(langs) for k in raw_keys}
    if isinstance(raw_keys, dict):
        return {k: list(v) for k, v in raw_keys.items()}
    return {}


def write_baseline(path: str, violations: dict, required_langs: list[str]) -> None:
    payload = {
        "_comment": (
            "Grandfathered untranslated (key, language) pairs. Regenerate with "
            "`--write-baseline`. This list should only ever shrink — a new "
            "entry here means an untranslated string slipped in. Translate "
            "the string in every required language, or mark it "
            "shouldTranslate:false in the catalog, to drop it from this list."
        ),
        "required_langs": list(required_langs),
        "keys": {k: violations[k] for k in sorted(violations)},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# Ratchet diff
# ---------------------------------------------------------------------------

def diff_against_baseline(current: dict, baseline: dict) -> tuple[dict, dict]:
    """Return ``(new_violations, resolved)``.

    ``new_violations[key] = [langs]`` — languages missing that are NOT
    grandfathered for that key in the baseline.

    ``resolved[key] = [langs]`` — languages that WERE grandfathered but are
    no longer violating (either translated or the key vanished). Used to
    signal "you can shrink the baseline" progress.
    """
    new: dict[str, list[str]] = {}
    for k, missing in current.items():
        allowed = set(baseline.get(k, []))
        beyond = [l for l in missing if l not in allowed]
        if beyond:
            new[k] = beyond

    resolved: dict[str, list[str]] = {}
    for k, allowed_langs in baseline.items():
        curr_missing = set(current.get(k, []))
        fixed = [l for l in allowed_langs if l not in curr_missing]
        if fixed:
            resolved[k] = fixed
    return new, resolved


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _expand_catalogs(patterns: list[str]) -> list[str]:
    """Expand each pattern via ``glob`` (files pass through unchanged).

    Duplicates are removed while preserving first-seen order so the caller
    controls precedence in error messages.
    """
    seen: set[str] = set()
    out: list[str] = []
    for p in patterns:
        matches = sorted(glob.glob(p)) if any(c in p for c in "*?[") else [p]
        if not matches:
            # Preserve the pattern so downstream I/O produces a clear error.
            matches = [p]
        for m in matches:
            if m not in seen:
                seen.add(m)
                out.append(m)
    return out


def _parse_langs(spec: str) -> list[str]:
    langs = [s.strip() for s in spec.split(",") if s.strip()]
    if not langs:
        raise argparse.ArgumentTypeError("--langs must list >=1 language code")
    return langs


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="xcstrings-gate",
        description="CI translation-coverage gate for Xcode String Catalogs.",
    )
    ap.add_argument(
        "--catalog", action="append", required=True, metavar="GLOB",
        help="Path or glob to an .xcstrings catalog. Repeat to gate multiple.",
    )
    ap.add_argument(
        "--baseline", required=True, metavar="PATH",
        help="Path to the baseline JSON (per-language shape). "
             "Created on --write-baseline; treated as empty if absent otherwise.",
    )
    ap.add_argument(
        "--langs", required=True, type=_parse_langs, metavar="es,pt-BR",
        help="Comma-separated list of required language codes.",
    )
    ap.add_argument(
        "--strict-states", action="store_true",
        help="Only 'translated' counts. By default 'needs_review' also counts "
             "(matches Xcode's own 'shows in-app' semantics).",
    )
    ap.add_argument(
        "--remediation-hint", default=None, metavar="TEXT",
        help="Extra line printed on failure with project-specific guidance.",
    )
    ap.add_argument(
        "--list", action="store_true",
        help="Print every current (key, missing_langs) violation and exit 0.",
    )
    ap.add_argument(
        "--write-baseline", action="store_true",
        help="Snapshot the current violation set as the baseline. Do NOT use "
             "this to silence a new violation — the baseline may only shrink.",
    )
    return ap


def _format_missing(missing: list[str]) -> str:
    return "[" + ", ".join(missing) + "]"


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    catalog_paths = _expand_catalogs(args.catalog)
    missing_files = [p for p in catalog_paths if not os.path.exists(p)]
    if missing_files:
        for p in missing_files:
            print(f"error: catalog not found: {p}", file=sys.stderr)
        return 2

    ok_states = STRICT_OK_STATES if args.strict_states else DEFAULT_OK_STATES
    current = aggregate_violations(catalog_paths, args.langs, ok_states)

    if args.list:
        for k in sorted(current):
            print(f"{k}\t{_format_missing(current[k])}")
        total_pairs = sum(len(v) for v in current.values())
        print(
            f"\n{len(current)} untranslated enforced key(s), "
            f"{total_pairs} (key, language) pair(s)."
        )
        return 0

    if args.write_baseline:
        write_baseline(args.baseline, current, args.langs)
        total_pairs = sum(len(v) for v in current.values())
        print(
            f"wrote baseline: {len(current)} grandfathered key(s) "
            f"({total_pairs} pair(s)) → {args.baseline}"
        )
        return 0

    baseline = load_baseline(args.baseline)
    new_violations, resolved = diff_against_baseline(current, baseline)

    if new_violations:
        langs_str = ", ".join(args.langs)
        print(
            "❌ xcstrings-gate: new untranslated (key, language) pair(s) "
            f"beyond the baseline (required: {langs_str}):\n"
        )
        for k in sorted(new_violations):
            print(f"    · {k!r}  missing {_format_missing(new_violations[k])}")
        print(
            "\nResolve by either:\n"
            f"  1. Adding a translation in every required language "
            f"({langs_str}) for each key above, OR\n"
            "  2. Marking the string \"shouldTranslate\": false in the catalog\n"
            "     (Xcode: select the string → 'Don't Translate') if it genuinely\n"
            "     should not be localized (symbol, format-only fragment, brand).\n"
            "\nDo NOT run --write-baseline to silence this — the baseline is "
            "for pre-existing debt only and must not grow."
        )
        if args.remediation_hint:
            print(f"\n{args.remediation_hint}")
        return 1

    if resolved:
        total_fixed = sum(len(v) for v in resolved.values())
        print(
            f"✅ xcstrings-gate: no new untranslated strings. "
            f"({total_fixed} baselined pair(s) across {len(resolved)} key(s) "
            f"are now resolved — run --write-baseline to lock in the progress.)"
        )
    else:
        print("✅ xcstrings-gate: no new untranslated strings.")
    return 0


def _console_entry() -> None:
    """``pyproject.toml`` ``[project.scripts]`` entry point.

    Kept separate from ``main`` so ``main`` stays argv-injectable for tests.
    """
    raise SystemExit(main(sys.argv[1:]))


if __name__ == "__main__":
    _console_entry()
