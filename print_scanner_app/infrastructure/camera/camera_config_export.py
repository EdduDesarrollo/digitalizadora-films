"""Export recursivo de configuración gphoto2."""

from __future__ import annotations

from typing import Any, Mapping

try:
    import gphoto2 as gp
except ImportError:  # pragma: no cover
    gp = None  # type: ignore[assignment]


def merge_camera_config(
    existing: Mapping[str, Any] | None,
    exported: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge CONFIG_CAMARA: claves exportadas pisan las existentes."""
    base: dict[str, Any] = dict(existing) if existing else {}
    base.update(exported)
    return base


def _is_io_or_claim_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    if hasattr(exc, "code") and exc.code in (-110, -53):
        return True
    return (
        "-110" in str(exc)
        or "-53" in str(exc)
        or "i/o in progress" in text
        or "could not claim" in text
    )


def export_camera_config_tree(camera: Any, gp_module: Any | None = None) -> dict[str, Any]:
    """
    Lee el árbol de configuración de la cámara y devuelve paths → valores serializables.
    """
    gphoto = gp_module if gp_module is not None else gp
    configuraciones: dict[str, Any] = {}

    config = camera.get_config()

    def walk(config_item: Any, path: str = "") -> None:
        try:
            name = config_item.get_name()
            full_path = f"{path}/{name}" if path else name
            try:
                value = config_item.get_value()
                if isinstance(value, (str, int, float, bool)):
                    configuraciones[full_path] = value
                elif value is None:
                    configuraciones[full_path] = None
                else:
                    configuraciones[full_path] = str(value)
            except (AttributeError, TypeError):
                pass
            except Exception as e:  # noqa: BLE001
                if gphoto is not None and isinstance(e, gphoto.GPhoto2Error):
                    pass
                else:
                    pass

            try:
                n = config_item.count_children()
                for i in range(n):
                    try:
                        child = config_item.get_child(i)
                        walk(child, full_path)
                    except (AttributeError, TypeError):
                        continue
                    except Exception as e:  # noqa: BLE001
                        if gphoto is not None and isinstance(e, gphoto.GPhoto2Error):
                            continue
                        continue
            except (AttributeError, TypeError):
                pass
            except Exception as e:  # noqa: BLE001
                if gphoto is not None and isinstance(e, gphoto.GPhoto2Error):
                    if not _is_io_or_claim_error(e):
                        raise
        except Exception as e:  # noqa: BLE001
            if gphoto is not None and isinstance(e, gphoto.GPhoto2Error):
                if not _is_io_or_claim_error(e):
                    raise

    walk(config)
    return configuraciones


def is_retryable_camera_io_error(exc: BaseException) -> bool:
    """Errores -110 / -53 o mensajes equivalentes."""
    return _is_io_or_claim_error(exc)
