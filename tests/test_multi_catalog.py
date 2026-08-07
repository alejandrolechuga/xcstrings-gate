"""Multi-catalog — violations aggregate across globbed catalogs.

Real adopters have several catalogs: per-target, per-module, plus
``InfoPlist.xcstrings``. ``--catalog`` accepts a glob or is repeated;
violations from every match must be unioned before the ratchet runs.
"""
from __future__ import annotations

import json
from pathlib import Path

from _helpers import catalog, entry, unit
from xcstrings_gate import aggregate_violations, main


LANGS = ["es", "pt-BR"]


def _write(p: Path, strings: dict) -> None:
    p.write_text(json.dumps(catalog(strings)), encoding="utf-8")


def test_aggregate_unions_missing_langs_across_catalogs(tmp_path):
    a = tmp_path / "A.xcstrings"
    b = tmp_path / "B.xcstrings"
    _write(a, {"same": entry({"es": unit("hola")})})       # missing pt-BR in A
    _write(b, {"same": entry({"pt-BR": unit("olá")})})     # missing es in B
    merged = aggregate_violations([str(a), str(b)], LANGS, frozenset({"translated"}))
    assert merged == {"same": ["es", "pt-BR"]}


def test_aggregate_disjoint_keys(tmp_path):
    a = tmp_path / "A.xcstrings"
    b = tmp_path / "B.xcstrings"
    _write(a, {"only.in.a": entry({})})
    _write(b, {"only.in.b": entry({"es": unit("hola")})})
    merged = aggregate_violations([str(a), str(b)], LANGS, frozenset({"translated", "needs_review"}))
    assert merged == {
        "only.in.a": ["es", "pt-BR"],
        "only.in.b": ["pt-BR"],
    }


def test_glob_pattern_expands(tmp_path, capsys):
    (tmp_path / "sub").mkdir()
    a = tmp_path / "sub" / "Localizable.xcstrings"
    b = tmp_path / "sub" / "InfoPlist.xcstrings"
    _write(a, {"k1": entry({})})
    _write(b, {"k2": entry({})})
    base = tmp_path / "b.json"
    base.write_text('{"required_langs":["es","pt-BR"],"keys":{}}', encoding="utf-8")
    rc = main([
        "--catalog", str(tmp_path / "sub" / "*.xcstrings"),
        "--baseline", str(base),
        "--langs", "es,pt-BR",
    ])
    out = capsys.readouterr().out
    assert rc == 1
    assert "k1" in out
    assert "k2" in out


def test_repeated_catalog_flag(tmp_path, capsys):
    a = tmp_path / "A.xcstrings"
    b = tmp_path / "B.xcstrings"
    _write(a, {"ka": entry({})})
    _write(b, {"kb": entry({})})
    base = tmp_path / "b.json"
    base.write_text('{"required_langs":["es","pt-BR"],"keys":{}}', encoding="utf-8")
    rc = main([
        "--catalog", str(a),
        "--catalog", str(b),
        "--baseline", str(base),
        "--langs", "es,pt-BR",
    ])
    out = capsys.readouterr().out
    assert rc == 1
    assert "ka" in out and "kb" in out


def test_glob_no_matches_reports_missing(tmp_path, capsys):
    base = tmp_path / "b.json"
    rc = main([
        "--catalog", str(tmp_path / "nomatch-*.xcstrings"),
        "--baseline", str(base),
        "--langs", "es,pt-BR",
    ])
    err = capsys.readouterr().err
    assert rc == 2
    assert "not found" in err
