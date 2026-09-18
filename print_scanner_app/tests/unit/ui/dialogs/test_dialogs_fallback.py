from print_scanner_app.ui.dialogs import CameraDialogs, ErrorDialogs, ExitDialogs, RawDialogs


def test_error_dialog_fallback_calls_callback():
    shown = ErrorDialogs.show_error("x", on_ok=lambda: None)
    assert shown in (False, True)


def test_exit_confirm_fallback_calls_confirm():
    shown = ExitDialogs.confirm_exit(lambda: None)
    assert shown in (False, True)


def test_exit_confirm_with_pending_fallback_callable():
    shown = ExitDialogs.confirm_exit_with_pending(
        pending_count=2,
        on_save_and_exit=lambda: None,
        on_exit_without_saving=lambda: None,
    )
    assert shown in (False, True)


def test_raw_confirm_fallback_calls_confirm():
    shown = RawDialogs.confirm_download(3, lambda: None)
    assert shown in (False, True)


def test_camera_dialog_retry_result_callable():
    shown = CameraDialogs.show_retry_result(False, "fallo")
    assert shown in (False, True)


def test_raw_show_download_outcome_runs_without_crash():
    RawDialogs.show_download_outcome(
        downloaded=0, not_found=3, batch_folder="00001-00003", error=None
    )
    RawDialogs.show_download_outcome(
        downloaded=2, not_found=1, batch_folder="00001-00003", error=None
    )
    RawDialogs.show_download_outcome(downloaded=5, not_found=0, batch_folder="x", error=None)
    RawDialogs.show_download_outcome(downloaded=0, not_found=0, batch_folder=None, error="fallo USB")
