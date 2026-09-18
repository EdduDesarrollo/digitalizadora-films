from pathlib import Path

from print_scanner_app.infrastructure.storage.config_repository import ConfigRepository
from print_scanner_app.infrastructure.storage.raw_pending_repository import RawPendingRepository


def test_append_load_1000_entries(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    cr = ConfigRepository(cfg)
    r = RawPendingRepository(tmp_path, cr, fixed_session_key="bulk")
    for i in range(1000):
        r.append(f"F{i}.CR3", f"p-{i:05d}.cr3")
    all_p = r.load_all()
    assert len(all_p) == 1000
    assert r.remove("F500.CR3") is False
    assert len(r.load_all()) == 999
