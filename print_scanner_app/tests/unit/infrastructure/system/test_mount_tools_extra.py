import subprocess

import pytest

import print_scanner_app.infrastructure.system.mount_tools as mt


def test_unmount_hits_gvfs_entries(monkeypatch: pytest.MonkeyPatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    uid = 4242
    gvfs = f"/run/user/{uid}/gvfs"
    monkeypatch.setattr(mt.os, "getuid", lambda: uid)
    monkeypatch.setattr(mt.os.path, "exists", lambda p: str(p) == gvfs)
    monkeypatch.setattr(mt.os, "listdir", lambda p: ["gphoto2:Canon", "plain"])

    mt.unmount_camera_mounts(run=fake_run)

    assert any(c[:3] == ["gio", "mount", "-s"] for c in calls)
    assert any(len(c) >= 4 and c[2] == "-u" and c[3].startswith(gvfs) for c in calls)
