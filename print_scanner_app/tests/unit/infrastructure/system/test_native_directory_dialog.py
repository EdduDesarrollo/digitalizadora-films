import os
import subprocess
import sys
from pathlib import Path

import pytest

from print_scanner_app.infrastructure.system import native_directory_dialog as ndd


def test_pick_returns_none_non_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert ndd.pick_directory_ubuntu_zenity("/tmp") is None


def test_pick_returns_none_without_zenity(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(ndd.shutil, "which", lambda _x: None)
    assert ndd.pick_directory_ubuntu_zenity(str(tmp_path)) is None


def test_pick_cancel_returncode(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(ndd.shutil, "which", lambda _x: "/usr/bin/zenity")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "")

    monkeypatch.setattr(ndd.subprocess, "run", fake_run)
    assert ndd.pick_directory_ubuntu_zenity(str(tmp_path)) is None


def test_pick_empty_stdout_rejected(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(ndd.shutil, "which", lambda _x: "/usr/bin/zenity")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, "\n", "")

    monkeypatch.setattr(ndd.subprocess, "run", fake_run)
    assert ndd.pick_directory_ubuntu_zenity(str(tmp_path)) is None


def test_pick_success_resolves_directory(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(ndd.shutil, "which", lambda _x: "/usr/bin/zenity")
    target = tmp_path / "d"
    target.mkdir()

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, str(target) + "\n", "")

    monkeypatch.setattr(ndd.subprocess, "run", fake_run)
    assert ndd.pick_directory_ubuntu_zenity(str(tmp_path)) == str(target.resolve())


def test_zenity_start_directory_existing_dir(tmp_path: Path):
    d = tmp_path / "nest"
    d.mkdir()
    s = ndd._zenity_start_directory(str(d))
    assert s.endswith(os.sep)
    assert os.path.normpath(s.rstrip(os.sep)) == os.path.normpath(str(d.resolve()))


def test_zenity_start_directory_file_uses_parent(tmp_path: Path):
    d = tmp_path / "nest"
    d.mkdir()
    f = d / "x.txt"
    f.write_text("a")
    s = ndd._zenity_start_directory(str(f))
    assert s.endswith(os.sep)
    assert os.path.normpath(s.rstrip(os.sep)) == os.path.normpath(str(d.resolve()))

