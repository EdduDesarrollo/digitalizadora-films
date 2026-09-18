import json
import logging
from pathlib import Path

import pytest

from print_scanner_app.infrastructure.storage import raw_pending_repository as rpr_mod
from print_scanner_app.infrastructure.storage.config_repository import ConfigRepository
from print_scanner_app.infrastructure.storage.raw_pending_repository import (
    RawPendingBlock,
    RawPendingRepository,
    persist_raw_pending_file,
)


def _cfg(tmp_path: Path) -> ConfigRepository:
    p = tmp_path / "config.json"
    p.write_text("{}", encoding="utf-8")
    return ConfigRepository(p)


def test_load_all_missing_file_returns_empty(tmp_path):
    (tmp_path / "Utils").mkdir(parents=True)
    r = RawPendingRepository(tmp_path / "Utils", _cfg(tmp_path), fixed_session_key="nueva")
    assert r.load_all() == []


def test_load_all_skips_malformed_lines(tmp_path):
    r = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="fix")
    p: Path = r.file_path
    p.write_text(
        "good|dest.cr3\nsin_pipe\n  \nonly|parts|extra\na|b\n",
        encoding="utf-8",
    )
    pairs = r.load_all()
    assert ["good", "dest.cr3"] in pairs
    assert ["a", "b"] in pairs
    assert ["only", "parts|extra"] in pairs
    assert len(pairs) == 3


def test_remove_when_no_file_returns_false(tmp_path):
    r = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="void")
    assert r.remove("ANY") is False


def test_append_load_remove(tmp_path):
    r = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="sesion1")
    r.append("A.CR3", "a.cr3")
    r.append("B.CR3", "b.cr3")
    assert len(r.load_all()) == 2
    empty = r.remove("A.CR3")
    assert not empty
    assert len(r.load_all()) == 1
    empty2 = r.remove("B.CR3")
    assert empty2
    assert r.is_empty()


def test_pending_dest_basename_uses_session_key(tmp_path):
    (tmp_path / "Utils").mkdir()
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps({"PREFIJO_ARCHIVO": "UY-UDELAR-AGU-AIH", "CODIGO_REFERENCIA": "AIH-I-ICUR-01-127"}),
        encoding="utf-8",
    )
    r = RawPendingRepository(tmp_path / "Utils", ConfigRepository(cfg_path))
    assert r.pending_dest_basename(1) == "UY-UDELAR-AGU-AIH-AIH-I-ICUR-01-127-000001.cr3"
    assert r.file_path.name == "raw_pendientes_UY-UDELAR-AGU-AIH-AIH-I-ICUR-01-127.txt"


def test_file_path_uses_config_when_no_fixed_key(tmp_path):
    (tmp_path / "Utils").mkdir()
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps({"PREFIJO_ARCHIVO": "PF", "CODIGO_REFERENCIA": "ZZ"}),
        encoding="utf-8",
    )
    cr = ConfigRepository(cfg_path)
    r = RawPendingRepository(tmp_path / "Utils", cr, fixed_session_key=None)
    assert r.file_path == tmp_path / "Utils" / "Pending_raws" / "raw_pendientes_PF-ZZ.txt"


def test_migrates_legacy_file_from_utils_root(tmp_path):
    (tmp_path / "Utils").mkdir()
    r = RawPendingRepository(tmp_path / "Utils", _cfg(tmp_path), fixed_session_key="legacy")
    legacy = tmp_path / "Utils" / "raw_pendientes_legacy.txt"
    legacy.write_text("A.CR3|a.cr3\n", encoding="utf-8")
    assert not r.file_path.is_file()
    blocks = r.load_blocks()
    assert len(blocks) == 1
    assert r.file_path.is_file()
    assert not legacy.is_file()
    assert blocks[0].raw_name == "A.CR3"


def test_migrates_legacy_file_from_old_subdir(tmp_path):
    (tmp_path / "Utils" / "raw_pendientes").mkdir(parents=True)
    r = RawPendingRepository(tmp_path / "Utils", _cfg(tmp_path), fixed_session_key="oldsub")
    legacy = tmp_path / "Utils" / "raw_pendientes" / "raw_pendientes_oldsub.txt"
    legacy.write_text("B.CR3|b.cr3\n", encoding="utf-8")
    assert not r.file_path.is_file()
    blocks = r.load_blocks()
    assert len(blocks) == 1
    assert r.file_path.is_file()
    assert not legacy.is_file()
    assert blocks[0].raw_name == "B.CR3"


def test_normalize_crlf_blank_lines_and_spaces_only(tmp_path):
    r = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="nl")
    # La línea tras los vacíos no es metadato JPG (primer campo ≠ "JPG").
    r.file_path.write_text("a|b.cr3\r\n\r\n  \nnot|jpg|extra\n", encoding="utf-8")
    blocks = r.load_blocks()
    assert len(blocks) == 2
    assert blocks[0].raw_name == "a" and blocks[0].dest_basename == "b.cr3" and not blocks[0].has_jpg
    assert blocks[1].raw_name == "not" and blocks[1].dest_basename == "jpg|extra"


def test_load_blocks_raw_plus_jpg_roundtrip(tmp_path):
    r = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="jpg")
    r.append_with_jpg("R.CR3", "dest.cr3", "IMG_01.JPG")
    blocks = r.load_blocks()
    assert len(blocks) == 1
    b = blocks[0]
    assert b.raw_name == "R.CR3" and b.dest_basename == "dest.cr3"
    assert b.has_jpg and b.jpg_name == "IMG_01.JPG"
    text = r.file_path.read_text(encoding="utf-8")
    assert "R.CR3|dest.cr3\n" in text
    assert "JPG|IMG_01.JPG\n" in text
    assert "\n\n" not in text


def test_load_blocks_legacy_jpg_three_fields_keeps_basename_only(tmp_path):
    r = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="leg")
    r.file_path.write_text(
        "R.CR3|dest.cr3\nJPG|/store_1/DCIM|IMG_01.JPG\n",
        encoding="utf-8",
    )
    b = r.load_blocks()[0]
    assert b.has_jpg and b.jpg_name == "IMG_01.JPG"


def test_jpg_two_segments_attaches_to_previous_raw(tmp_path):
    r = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="amb")
    r.file_path.write_text("first|a.cr3\nJPG|FOO.JPG\n", encoding="utf-8")
    blocks = r.load_blocks()
    assert len(blocks) == 1
    assert blocks[0].raw_name == "first" and blocks[0].jpg_name == "FOO.JPG"


def test_orphan_jpg_line_skipped(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    r = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="orph")
    r.file_path.write_text("JPG|/|orphan.jpg\nx|y.cr3\n", encoding="utf-8")
    blocks = r.load_blocks()
    assert len(blocks) == 1 and blocks[0].raw_name == "x"
    assert any("huérfana" in rec.message for rec in caplog.records)


def test_malformed_jpg_empty_basename_skipped(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    r = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="bad")
    r.file_path.write_text("r|d.cr3\nJPG|\n", encoding="utf-8")
    blocks = r.load_blocks()
    assert len(blocks) == 1 and blocks[0].raw_name == "r" and not blocks[0].has_jpg
    assert any("mal formada" in rec.message for rec in caplog.records)


def test_remove_eliminates_raw_and_jpg_line(tmp_path):
    r = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="rm")
    r.append_with_jpg("A.CR3", "a.cr3", "x.JPG")
    assert r.remove("A.CR3") is True
    assert r.is_empty()


def test_remove_block_sync_idempotent_when_missing(tmp_path):
    r = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="syn")
    assert r.remove_block_sync("NOPE.CR3") is True


def test_append_with_jpg_rejects_pipe_in_name(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    r = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="pipe")
    r.append_with_jpg("A.CR3", "a.cr3", "bad|name.jpg")
    blocks = r.load_blocks()
    assert len(blocks) == 1 and not blocks[0].has_jpg


def test_persist_raw_pending_file_succeeds_after_transient_failures(tmp_path, monkeypatch: pytest.MonkeyPatch):
    log = logging.getLogger("t.persist")
    log.setLevel(logging.DEBUG)
    path = tmp_path / "p.txt"
    orig = rpr_mod._atomic_replace
    state = {"n": 0}

    def flaky(pth, content):
        state["n"] += 1
        if state["n"] < 3:
            raise OSError("simulado")
        return orig(pth, content)

    monkeypatch.setattr(rpr_mod, "_atomic_replace", flaky)
    assert persist_raw_pending_file(path, "contenido\n", log=log) is True
    assert path.read_text(encoding="utf-8") == "contenido\n"
    assert state["n"] == 3


def test_persist_raw_pending_file_fails_after_six_attempts(tmp_path, monkeypatch: pytest.MonkeyPatch, caplog):
    caplog.set_level(logging.ERROR)
    monkeypatch.setattr(rpr_mod, "_atomic_replace", lambda p, c: (_ for _ in ()).throw(OSError("perm")))
    path = tmp_path / "q.txt"
    log = logging.getLogger("t.fail")
    body = "x" * 40000
    assert persist_raw_pending_file(path, body, log=log) is False
    assert not path.is_file()
    joined = " ".join(r.message for r in caplog.records)
    assert "truncado" in joined or "bytes en total" in joined


def test_remove_block_sync_uses_persist_retries(tmp_path, monkeypatch: pytest.MonkeyPatch):
    r = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="rbs")
    r.append("A.CR3", "a.cr3")
    r.append("B.CR3", "b.cr3")
    calls = {"n": 0}
    real = rpr_mod._atomic_replace

    def flaky(path, content):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("simulado")
        return real(path, content)

    monkeypatch.setattr(rpr_mod, "_atomic_replace", flaky)
    assert r.remove_block_sync("A.CR3") is True
    assert calls["n"] == 3
    assert len(r.load_blocks()) == 1 and r.load_blocks()[0].raw_name == "B.CR3"


def test_save_blocks_with_post_phase_b_retries_uses_persist(tmp_path, monkeypatch: pytest.MonkeyPatch):
    r = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="sb")
    calls = {"persist": 0}
    real = rpr_mod.persist_raw_pending_file

    def wrap(path, content, **kw):
        calls["persist"] += 1
        return real(path, content, **kw)

    monkeypatch.setattr(rpr_mod, "persist_raw_pending_file", wrap)
    ok = r.save_blocks([RawPendingBlock("a", "b.cr3")], use_post_phase_b_retries=True)
    assert ok and calls["persist"] == 1
    assert r.load_blocks()[0].raw_name == "a"
