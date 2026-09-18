import subprocess

from print_scanner_app.infrastructure.system.process_tools import kill_processes_using_device


def test_kill_skips_fuser_missing(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError()

    assert kill_processes_using_device("/dev/usb/lp0", run=fake_run) == []


def test_kill_pids(monkeypatch):
    seq = iter(
        [
            subprocess.CompletedProcess(["fuser"], 0, "123 456\n", ""),
            subprocess.CompletedProcess(["kill"], 0, "", ""),
            subprocess.CompletedProcess(["kill"], 0, "", ""),
        ]
    )

    def fake_run(cmd, **kwargs):
        return next(seq)

    killed = kill_processes_using_device("/dev/x", run=fake_run, own_pid=999)
    assert "123" in killed or "456" in killed


def test_fuser_nonzero_return_empty():
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(["fuser"], 1, "999\n", "")

    assert kill_processes_using_device("/dev/x", run=fake_run) == []


def test_skips_own_pid_only():
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[0] == "fuser":
            return subprocess.CompletedProcess(cmd, 0, "100 200\n", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    killed = kill_processes_using_device("/dev/x", run=fake_run, own_pid=100)
    assert killed == ["200"]
    assert sum(1 for c in calls if c[0] == "kill") == 1


def test_kill_permission_error_not_recorded():
    def fake_run(cmd, **kwargs):
        if cmd[0] == "fuser":
            return subprocess.CompletedProcess(cmd, 0, "300\n", "")
        raise subprocess.CalledProcessError(1, cmd)

    assert kill_processes_using_device("/dev/x", run=fake_run, own_pid=999) == []
