from print_scanner_app.ui.dialogs.camera_settings_dialogs import (
    CAMERA_SETTINGS_BLOCKED_MESSAGE,
    ENTANGLE_SAVE_FAILURE_MESSAGE,
)


def test_blocked_message_constant():
    assert "Pausá la digitación" in CAMERA_SETTINGS_BLOCKED_MESSAGE


def test_save_failure_message_exact():
    assert ENTANGLE_SAVE_FAILURE_MESSAGE == (
        "Error al guardar configuración de la camara. ¿Desea continuar igualmente?"
    )
