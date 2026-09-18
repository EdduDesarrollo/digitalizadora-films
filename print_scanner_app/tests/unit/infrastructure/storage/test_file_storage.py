from pathlib import Path

import pytest

from print_scanner_app.infrastructure.storage.file_storage import ensure_dir, safe_destination_path


def test_ensure_dir(tmp_path):
    d = ensure_dir(tmp_path / "a" / "b")
    assert d.is_dir()


def test_safe_destination_path(tmp_path):
    base = tmp_path / "base"
    p = safe_destination_path(base, "sub", "file.cr3")
    assert p.parent.name == "sub"


def test_path_traversal(tmp_path):
    with pytest.raises(ValueError):
        safe_destination_path(tmp_path, "..", "x")


def test_safe_destination_parent_mkdir_permission_denied(monkeypatch, tmp_path):
    base = (tmp_path / "base").resolve()
    base.mkdir()

    real_mkdir = Path.mkdir

    def mkdir_guard(self: Path, *a, **kw):
        if self.name == "nop":
            raise PermissionError("simulado")
        return real_mkdir(self, *a, **kw)

    monkeypatch.setattr(Path, "mkdir", mkdir_guard)

    with pytest.raises(PermissionError, match="simulado"):
        safe_destination_path(base, "nop", "out.cr3")
