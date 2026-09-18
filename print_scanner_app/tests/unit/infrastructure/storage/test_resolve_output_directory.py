from print_scanner_app.infrastructure.storage.config_repository import resolve_output_directory


def test_resolve_ignores_legacy_carpeta_destino():
    assert resolve_output_directory({"DIRECTORIO": "", "CARPETA_DESTINO": "fotos"}) == ""
