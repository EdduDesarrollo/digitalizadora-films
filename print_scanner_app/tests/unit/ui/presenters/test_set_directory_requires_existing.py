import json

from print_scanner_app.app.container import Container
from print_scanner_app.ui.presenters.app_presenter import AppPresenter


def test_set_directory_rejects_missing_path(tmp_path, test_logger):
    (tmp_path / "config.json").write_text(json.dumps({"DIRECTORIO": ""}), encoding="utf-8")
    p = AppPresenter(container=Container(tmp_path, "d", test_logger), logger=test_logger)
    assert not p.set_directory(str(tmp_path / "no_existe"))
