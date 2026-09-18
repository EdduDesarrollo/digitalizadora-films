def test_dialogs_and_presenter_importable():
    from print_scanner_app.ui.dialogs import CameraDialogs, ErrorDialogs, ExitDialogs, PrinterCleanDialogs, RawDialogs
    from print_scanner_app.ui.presenters.app_presenter import AppPresenter

    assert CameraDialogs is not None
    assert AppPresenter is not None
    assert ErrorDialogs and RawDialogs and ExitDialogs and PrinterCleanDialogs
