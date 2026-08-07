"""Ratchet paths — the reason this tool exists.

Cases:
- New violation beyond a *non-empty* baseline fails with exit 1.
- A baselined violation passes silently.
- A resolved baseline entry produces a progress hint (still exit 0).
- ``--write-baseline`` snapshots the current violations correctly and, once
  written, subsequent runs pass.
- The gate never grows the baseline as a side effect of a normal run.
- The legacy flat-list baseline shape is auto-migrated on read.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from _helpers import catalog, entry, unit
from xcstrings_gate import (
    diff_against_baseline,
    load_baseline,
    main,
    write_baseline,
)


LANGS = ["es", "pt-BR"]


def _write_catalog(tmp_path: Path, strings: dict) -> Path:
    p = tmp_path / "Localizable.xcstrings"
    p.write_text(json.dumps(catalog(strings)), encoding="utf-8")
    return p


def _write_baseline(tmp_path: Path, keys: dict, name: str = "baseline.json") -> Path:
    p = tmp_path / name
    write_baseline(str(p), keys, LANGS)
    return p


# ---------------------------------------------------------------------------
# Pure diff logic
# ---------------------------------------------------------------------------

def test_diff_new_violation_beyond_baseline():
    current = {"new.key": ["es", "pt-BR"], "old.key": ["pt-BR"]}
    baseline = {"old.key": ["pt-BR"]}
    new, resolved = diff_against_baseline(current, baseline)
    assert new == {"new.key": ["es", "pt-BR"]}
    assert resolved == {}


def test_diff_baselined_pair_is_ignored():
    current = {"old.key": ["pt-BR"]}
    baseline = {"old.key": ["pt-BR"]}
    new, resolved = diff_against_baseline(current, baseline)
    assert new == {}
    assert resolved == {}


def test_diff_partial_baseline_still_reports_extras():
    # baseline grandfathers pt-BR only; es is now also missing → that's new.
    current = {"k": ["es", "pt-BR"]}
    baseline = {"k": ["pt-BR"]}
    new, resolved = diff_against_baseline(current, baseline)
    assert new == {"k": ["es"]}
    assert resolved == {}


def test_diff_resolved_key_reports_progress():
    current = {}  # everything translated
    baseline = {"was.broken": ["es", "pt-BR"]}
    new, resolved = diff_against_baseline(current, baseline)
    assert new == {}
    assert resolved == {"was.broken": ["es", "pt-BR"]}


def test_diff_partially_resolved_key():
    current = {"k": ["pt-BR"]}
    baseline = {"k": ["es", "pt-BR"]}
    new, resolved = diff_against_baseline(current, baseline)
    assert new == {}
    assert resolved == {"k": ["es"]}


# ---------------------------------------------------------------------------
# CLI integration — the ratchet against a synthetic non-empty baseline
# ---------------------------------------------------------------------------

def _run(argv, capsys) -> tuple[int, str, str]:
    rc = main(argv)
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def test_cli_baselined_only_passes(tmp_path, capsys):
    strings = {"old.key": entry({"es": unit("hola")})}  # missing pt-BR
    cat = _write_catalog(tmp_path, strings)
    base = _write_baseline(tmp_path, {"old.key": ["pt-BR"]})
    rc, out, _ = _run(
        ["--catalog", str(cat), "--baseline", str(base), "--langs", "es,pt-BR"],
        capsys,
    )
    assert rc == 0
    assert "no new untranslated" in out


def test_cli_new_violation_fails(tmp_path, capsys):
    strings = {
        "old.key": entry({"es": unit("hola")}),  # baselined
        "new.key": entry({}),                    # brand new violation
    }
    cat = _write_catalog(tmp_path, strings)
    base = _write_baseline(tmp_path, {"old.key": ["pt-BR"]})
    rc, out, _ = _run(
        ["--catalog", str(cat), "--baseline", str(base), "--langs", "es,pt-BR"],
        capsys,
    )
    assert rc == 1
    assert "new.key" in out
    assert "es" in out and "pt-BR" in out
    # Baselined key must not appear in the failure list.
    assert "old.key" not in out


def test_cli_resolved_baseline_reports_progress(tmp_path, capsys):
    strings = {"was.broken": entry({"es": unit("hola"), "pt-BR": unit("olá")})}
    cat = _write_catalog(tmp_path, strings)
    base = _write_baseline(tmp_path, {"was.broken": ["pt-BR"]})
    rc, out, _ = _run(
        ["--catalog", str(cat), "--baseline", str(base), "--langs", "es,pt-BR"],
        capsys,
    )
    assert rc == 0
    assert "resolved" in out
    assert "--write-baseline" in out


def test_cli_expanded_baseline_pair_fails(tmp_path, capsys):
    # baseline grandfathers pt-BR; es regresses → must fail.
    strings = {"k": entry({})}
    cat = _write_catalog(tmp_path, strings)
    base = _write_baseline(tmp_path, {"k": ["pt-BR"]})
    rc, out, _ = _run(
        ["--catalog", str(cat), "--baseline", str(base), "--langs", "es,pt-BR"],
        capsys,
    )
    assert rc == 1
    assert "'k'" in out
    assert "[es]" in out


def test_cli_write_baseline_snapshots(tmp_path, capsys):
    strings = {
        "a": entry({}),
        "b": entry({"es": unit("hola")}),
    }
    cat = _write_catalog(tmp_path, strings)
    base = tmp_path / "baseline.json"
    rc, _, _ = _run(
        [
            "--catalog", str(cat), "--baseline", str(base),
            "--langs", "es,pt-BR", "--write-baseline",
        ],
        capsys,
    )
    assert rc == 0
    data = json.loads(base.read_text(encoding="utf-8"))
    assert data["required_langs"] == ["es", "pt-BR"]
    assert data["keys"] == {"a": ["es", "pt-BR"], "b": ["pt-BR"]}
    # Subsequent run against the snapshot must pass.
    rc, out, _ = _run(
        ["--catalog", str(cat), "--baseline", str(base), "--langs", "es,pt-BR"],
        capsys,
    )
    assert rc == 0
    assert "no new untranslated" in out


def test_cli_write_baseline_is_not_run_by_default(tmp_path, capsys):
    """A failing gate must not mutate the baseline as a side effect."""
    strings = {"a": entry({})}
    cat = _write_catalog(tmp_path, strings)
    base = _write_baseline(tmp_path, {})  # empty baseline
    before = base.read_text(encoding="utf-8")
    rc, _, _ = _run(
        ["--catalog", str(cat), "--baseline", str(base), "--langs", "es,pt-BR"],
        capsys,
    )
    assert rc == 1
    assert base.read_text(encoding="utf-8") == before


def test_cli_missing_baseline_file_treated_as_empty(tmp_path, capsys):
    strings = {"a": entry({"es": unit("hola"), "pt-BR": unit("olá")})}
    cat = _write_catalog(tmp_path, strings)
    missing = tmp_path / "does-not-exist.json"
    rc, out, _ = _run(
        ["--catalog", str(cat), "--baseline", str(missing), "--langs", "es,pt-BR"],
        capsys,
    )
    assert rc == 0
    assert "no new untranslated" in out


def test_cli_missing_catalog_is_error(tmp_path, capsys):
    rc, _, err = _run(
        [
            "--catalog", str(tmp_path / "nope.xcstrings"),
            "--baseline", str(tmp_path / "b.json"),
            "--langs", "es,pt-BR",
        ],
        capsys,
    )
    assert rc == 2
    assert "not found" in err


def test_cli_remediation_hint_printed_on_failure(tmp_path, capsys):
    strings = {"a": entry({})}
    cat = _write_catalog(tmp_path, strings)
    base = _write_baseline(tmp_path, {})
    rc, out, _ = _run(
        [
            "--catalog", str(cat), "--baseline", str(base),
            "--langs", "es,pt-BR",
            "--remediation-hint", "See docs/i18n.md for the local workflow.",
        ],
        capsys,
    )
    assert rc == 1
    assert "docs/i18n.md" in out


def test_cli_list_mode_exits_zero_with_violations(tmp_path, capsys):
    strings = {"a": entry({}), "b": entry({"es": unit("hola")})}
    cat = _write_catalog(tmp_path, strings)
    base = _write_baseline(tmp_path, {})
    rc, out, _ = _run(
        ["--catalog", str(cat), "--baseline", str(base),
         "--langs", "es,pt-BR", "--list"],
        capsys,
    )
    assert rc == 0
    assert "a\t[es, pt-BR]" in out
    assert "b\t[pt-BR]" in out


# ---------------------------------------------------------------------------
# Baseline shape migration
# ---------------------------------------------------------------------------

def test_legacy_flat_baseline_migrates_on_read(tmp_path):
    p = tmp_path / "legacy.json"
    p.write_text(json.dumps({
        "required_langs": ["es", "pt-BR"],
        "keys": ["k1", "k2"],
    }), encoding="utf-8")
    got = load_baseline(str(p))
    assert got == {"k1": ["es", "pt-BR"], "k2": ["es", "pt-BR"]}


def test_new_baseline_shape_round_trips(tmp_path):
    p = tmp_path / "b.json"
    write_baseline(str(p), {"k": ["pt-BR"]}, ["es", "pt-BR"])
    assert load_baseline(str(p)) == {"k": ["pt-BR"]}


def test_empty_baseline_file_round_trips(tmp_path):
    p = tmp_path / "b.json"
    write_baseline(str(p), {}, ["es", "pt-BR"])
    loaded = json.loads(p.read_text(encoding="utf-8"))
    assert loaded["keys"] == {}
    assert loaded["required_langs"] == ["es", "pt-BR"]
    assert load_baseline(str(p)) == {}


def test_langs_flag_rejects_empty(tmp_path, capsys):
    with pytest.raises(SystemExit):
        main([
            "--catalog", str(tmp_path / "x"),
            "--baseline", str(tmp_path / "b"),
            "--langs", ",,",
        ])
