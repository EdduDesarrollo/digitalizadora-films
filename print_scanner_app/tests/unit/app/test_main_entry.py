import argparse
import logging
import sys

import pytest


def test_main_module_inserts_repo_root_on_path():
    import print_scanner_app.app.main as main_mod

    root = str(main_mod._root.resolve())
    assert root in sys.path


def test_main_runs_bootstrap_and_mocks_kivy(monkeypatch: pytest.MonkeyPatch):
    called = {}

    def fake_bootstrap(argv=None):
        args = argparse.Namespace(
            log_level="INFO",
            no_startup=False,
            no_usb_reset_on_startup=False,
        )
        return args, logging.getLogger("t.main")

    def fake_run_modular_app(logger, **kwargs):
        called["kivy"] = kwargs

    monkeypatch.setattr("print_scanner_app.app.bootstrap.bootstrap", fake_bootstrap)
    monkeypatch.setattr("print_scanner_app.ui.kivy_app.run_modular_app", fake_run_modular_app)

    from print_scanner_app.app import main as main_mod

    assert main_mod.main(["--log-level", "INFO"]) == 0
    assert called["kivy"] == {"auto_startup": True, "startup_reset_usb": True}


def test_main_passes_no_startup_flags(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def fake_bootstrap(argv=None):
        args = argparse.Namespace(
            log_level="INFO",
            no_startup=True,
            no_usb_reset_on_startup=True,
        )
        return args, logging.getLogger("t.main2")

    def fake_run(logger, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("print_scanner_app.app.bootstrap.bootstrap", fake_bootstrap)
    monkeypatch.setattr("print_scanner_app.ui.kivy_app.run_modular_app", fake_run)

    from print_scanner_app.app import main as main_mod

    main_mod.main([])
    assert captured == {"auto_startup": False, "startup_reset_usb": False}
