import subprocess

import pytest

import print_scanner_app.infrastructure.system.mount_tools as mt
from print_scanner_app.infrastructure.system.mount_tools import unmount_camera_mounts


def test_unmount_calls_gio(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    unmount_camera_mounts(run=fake_run)
    assert any("gio" in c and "gphoto2" in c for c in calls)


def test_unmount_scheme_file_not_found_continues(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(mt.os.path, "exists", lambda p: False)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[:3] == ["gio", "mount", "-s"]:
            raise FileNotFoundError()
        return subprocess.CompletedProcess(cmd, 0, "", "")

    assert unmount_camera_mounts(run=fake_run) is False
    assert sum(1 for c in calls if c[:3] == ["gio", "mount", "-s"]) == 2


def test_unmount_scheme_timeout_continues(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(mt.os.path, "exists", lambda p: False)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[:3] == ["gio", "mount", "-s"]:
            raise subprocess.TimeoutExpired(cmd, 1)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    assert unmount_camera_mounts(run=fake_run) is False


def test_unmount_gvfs_listdir_oserror(monkeypatch: pytest.MonkeyPatch):
    uid = 99
    gvfs = f"/run/user/{uid}/gvfs"
    monkeypatch.setattr(mt.os, "getuid", lambda: uid)
    monkeypatch.setattr(mt.os.path, "exists", lambda p: str(p) == gvfs)
    monkeypatch.setattr(mt.os, "listdir", lambda p: (_ for _ in ()).throw(OSError("boom")))

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, "", "")

    assert unmount_camera_mounts(run=fake_run) is True


def test_unmount_gvfs_umount_timeout_swallowed(monkeypatch: pytest.MonkeyPatch):
    uid = 100
    gvfs = f"/run/user/{uid}/gvfs"
    monkeypatch.setattr(mt.os, "getuid", lambda: uid)
    monkeypatch.setattr(mt.os.path, "exists", lambda p: str(p) == gvfs)
    monkeypatch.setattr(mt.os, "listdir", lambda p: ["gphoto2:cam"])

    def fake_run(cmd, **kwargs):
        if len(cmd) >= 4 and cmd[2] == "-u":
            raise subprocess.TimeoutExpired(cmd, 1)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    assert unmount_camera_mounts(run=fake_run) is True
