from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, List, Optional, Sequence, Tuple

from print_scanner_app.domain.policies.retry_policy import RetryConfig
from print_scanner_app.infrastructure.system.usb_tools import reset_usb_address

Run = Callable[..., subprocess.CompletedProcess]

_GTIMEOUT = -10


def import_gphoto2():
    import gphoto2 as gp

    return gp


@contextmanager
def camera_file_scope(gp: Any) -> Iterator[Any]:
    """
    Ciclo de vida de ``gp.CameraFile``: crea, yield, ``del`` en ``finally``.

    Sin ``gc.collect()`` (docs/260724_LIBERAR_FDs.md): el caller debe copiar a
    ``bytes`` o hacer ``save`` a disco dentro del ``with``.
    """
    camera_file = gp.CameraFile()
    try:
        yield camera_file
    finally:
        del camera_file


class GPhotoClient:
    """Wrapper de bajo nivel; no contiene reglas de UI ni selección por serial."""

    def __init__(self, gp_module: Any | None = None):
        self._gp = gp_module

    @property
    def gp(self):
        if self._gp is None:
            self._gp = import_gphoto2()
        return self._gp

    def autodetect(self) -> List[Tuple[str, str]]:
        """Lista de (modelo, usb:bus,dev)."""
        return list(self.gp.Camera.autodetect())


def gphoto_cli_usb_ports(*, run: Run = subprocess.run, timeout: float = 10.0) -> List[str]:
    ports: List[str] = []
    try:
        r = run(
            ["gphoto2", "--auto-detect"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ports
    if r.returncode != 0:
        return ports
    for line in (r.stdout or "").splitlines():
        for m in re.finditer(r"usb:(\d+),(\d+)", line, re.IGNORECASE):
            ports.append(f"usb:{m.group(1)},{m.group(2)}")
    return ports


def list_camera_addresses(client: GPhotoClient, *, run: Run = subprocess.run) -> List[Tuple[str, str]]:
    """Combina autodetect y fallback CLI."""
    seen = set()
    out: List[Tuple[str, str]] = []
    for name, addr in client.autodetect():
        if addr not in seen:
            seen.add(addr)
            out.append((name, addr))
    if not out:
        for addr in gphoto_cli_usb_ports(run=run):
            if addr not in seen:
                seen.add(addr)
                out.append(("unknown", addr))
    return out


def _is_timeout_err(e: BaseException, gp) -> bool:
    if gp is not None:
        try:
            if isinstance(e, gp.GPhoto2Error):
                return getattr(e, "code", None) == _GTIMEOUT or "-10" in str(e)
        except Exception:  # noqa: BLE001
            pass
    return "-10" in str(e)


def init_camera_at_address(
    gp,
    addr: str,
    *,
    retries: RetryConfig | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    reset_on_fail: bool = True,
) -> Any:
    """Crea `gp.Camera`, asigna puerto e inicializa (reintentos ante timeout + reset USB opcional)."""
    port_info_list = gp.PortInfoList()
    port_info_list.load()
    cfg = retries or RetryConfig()

    def make_cam():
        camera = gp.Camera()
        idx = port_info_list.lookup_path(addr)
        camera.set_port_info(port_info_list[idx])
        return camera

    sleep_fn(2.0)
    last_exc: Optional[BaseException] = None
    for attempt in range(cfg.max_attempts):
        if attempt > 0:
            sleep_fn(cfg.delay_seconds)
        cam = make_cam()
        try:
            cam.init()
            return cam
        except BaseException as e:  # noqa: BLE001
            last_exc = e
            if not _is_timeout_err(e, gp):
                raise
            continue

    if reset_on_fail and last_exc is not None:
        if reset_usb_address(addr):
            sleep_fn(3.0)
            cam2 = make_cam()
            cam2.init()
            return cam2
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("init_camera_at_address: sin resultado")


def get_camera_serial(gp, camera) -> Optional[str]:
    try:
        cfg = camera.get_config()
        text = cfg.get_child_by_name("serialnumber").get_value()
        if text is None:
            return None
        return str(text).strip() or None
    except Exception:  # noqa: BLE001
        try:
            cfg = camera.get_config()

            def walk(item, depth: int = 0):
                if depth > 40:
                    return None
                try:
                    if item.get_name().lower() == "serialnumber":
                        return str(item.get_value())
                except Exception:
                    pass
                try:
                    for i in range(item.count_children()):
                        v = walk(item.get_child(i), depth + 1)
                        if v:
                            return v
                except Exception:
                    pass
                return None

            v = walk(cfg)
            return str(v).strip() if v else None
        except Exception:  # noqa: BLE001
            return None


def jpg_basename_to_cr3_name(jpg_name: str) -> str:
    """Convierte basename JPG a CR3: ``capt0000.jpg`` → ``capt0000.CR3``."""
    name = (jpg_name or "").strip()
    if not name:
        return ""
    if name.upper().endswith(".JPG"):
        return name[:-4] + ".CR3"
    base, _, _ext = name.rpartition(".")
    return (base or name) + ".CR3"


def _raw_lookup_names(raw_name: str) -> List[str]:
    """Nombres a probar en tarjeta; acepta pendientes antiguos con ``.jpg``."""
    s = (raw_name or "").strip()
    if not s:
        return []
    low = s.lower()
    if low.endswith(".cr3"):
        return [s]
    if low.endswith(".jpg") or low.endswith(".jpeg"):
        base = s.rsplit(".", 1)[0]
        if not base:
            return []
        return [base + ".CR3", base + ".cr3"]
    return [s]


def _buscar_en_carpeta(camera, carpeta_path: str, nombre: Optional[str], raw: bool):
    try:
        camera_list = camera.folder_list_files(carpeta_path)
        files_names = [camera_list.get_name(j) for j in range(camera_list.count())]
        if raw:
            image_files = [f for f in files_names if f.lower().endswith(".cr3")]
        else:
            image_files = [
                f for f in files_names if f.lower().endswith(".jpg") or f.lower().endswith(".jpeg")
            ]
        if nombre:
            for f in image_files:
                if f.lower() == nombre.lower():
                    return carpeta_path, f
        elif image_files:
            return carpeta_path, sorted(image_files)[-1]
    except Exception:  # noqa: BLE001
        pass
    return None, None


def _find_raw_on_camera_one(
    camera,
    gp,
    raw_name: str,
    folder: str,
    *,
    last_found_folder: Optional[list],
) -> Tuple[Optional[str], Optional[str]]:
    cache = last_found_folder if last_found_folder is not None else [None]
    if cache[0] and cache[0] != folder:
        r = _buscar_en_carpeta(camera, cache[0], raw_name, True)
        if r[1]:
            return r

    r = _buscar_en_carpeta(camera, folder, raw_name, True)
    if r[1]:
        cache[0] = r[0]
        return r

    try:
        folders = camera.folder_list_folders(folder)
        for i in range(folders.count()):
            subfolder = folders.get_name(i)
            full_subfolder = os.path.join(folder, subfolder).replace("\\", "/")
            r = _buscar_en_carpeta(camera, full_subfolder, raw_name, True)
            if r[1]:
                cache[0] = r[0]
                return r
            r2 = _find_raw_on_camera_one(
                camera, gp, raw_name, full_subfolder, last_found_folder=cache
            )
            if r2[1]:
                return r2
    except Exception:  # noqa: BLE001
        pass

    return None, None


def find_raw_on_camera(
    camera,
    gp,
    raw_name: str,
    folder: str = "/",
    *,
    last_found_folder: Optional[list] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Busca un RAW en la cámara por nombre.
    `last_found_folder`: lista mutable de un elemento para caché de carpeta.
    Si ``raw_name`` termina en ``.jpg``, busca el ``.CR3`` emparejado.
    """
    cache = last_found_folder if last_found_folder is not None else [None]
    for candidate in _raw_lookup_names(raw_name) or [raw_name]:
        hit = _find_raw_on_camera_one(
            camera, gp, candidate, folder, last_found_folder=cache
        )
        if hit[1]:
            return hit
    return None, None


def resolve_raw_name_after_capture(
    camera,
    gp,
    reported: Optional[str],
    *,
    last_found_folder: Optional[list] = None,
) -> Optional[str]:
    """
    Tras ``capture()``, gphoto suele devolver ``captNNNN.jpg`` aunque el RAW esté en tarjeta.

    Camino feliz: deriva el ``.CR3`` del nombre reportado **sin** listar la tarjeta
    (evita walk USB en el tick de captura).

    Si no hay nombre reportado: un único fallback acotado via ``find_latest_raw_on_camera``.
    """
    s = (reported or "").strip()
    if not s:
        _, latest = find_latest_raw_on_camera(
            camera, gp, last_found_folder=last_found_folder
        )
        return latest

    low = s.lower()
    if low.endswith(".cr3"):
        return s

    if low.endswith(".jpg") or low.endswith(".jpeg"):
        cr3 = jpg_basename_to_cr3_name(s)
        return cr3 or None

    return s


def find_latest_jpeg_on_camera(
    camera,
    gp,
    folder: str = "/",
    *,
    last_found_folder: Optional[list] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Localiza el JPEG más reciente en tarjeta (orden alfabético por nombre en cada carpeta),
    análogo a ``find_latest_raw_on_camera`` pero para ``.jpg`` / ``.jpeg``.
    """
    cache = last_found_folder if last_found_folder is not None else [None]
    if cache[0] and cache[0] != folder:
        r = _buscar_en_carpeta(camera, cache[0], None, False)
        if r[1]:
            return r

    r = _buscar_en_carpeta(camera, folder, None, False)
    if r[1]:
        cache[0] = r[0]
        return r

    try:
        folders = camera.folder_list_folders(folder)
        for i in range(folders.count()):
            subfolder = folders.get_name(i)
            full_subfolder = os.path.join(folder, subfolder).replace("\\", "/")
            r = _buscar_en_carpeta(camera, full_subfolder, None, False)
            if r[1]:
                cache[0] = r[0]
                return r
            r2 = find_latest_jpeg_on_camera(
                camera,
                gp,
                full_subfolder,
                last_found_folder=cache,
            )
            if r2[1]:
                return r2
    except Exception:  # noqa: BLE001
        pass

    return None, None


# libgphoto2: GP_ERROR_FILE_NOT_FOUND -107, GP_ERROR_DIRECTORY_NOT_FOUND -105
_GPHOTO_FILE_NOT_FOUND = -107
_GPHOTO_DIR_NOT_FOUND = -105


def is_not_found_error(exc: BaseException, gp) -> bool:
    """
    True si el error indica que el archivo ya no existe en cámara (objetivo de borrado cumplido).
    """
    if gp is not None:
        try:
            if isinstance(exc, gp.GPhoto2Error):
                code = getattr(exc, "code", None)
                if code in (_GPHOTO_FILE_NOT_FOUND, _GPHOTO_DIR_NOT_FOUND):
                    return True
        except Exception:  # noqa: BLE001
            pass
    s = str(exc).lower()
    for frag in (
        "not found",
        "no such file",
        "does not exist",
        "unknown object",
        "invalid object",
        "could not find",
    ):
        if frag in s:
            return True
    return False


def find_all_jpeg_paths_on_camera(
    camera,
    gp,
    jpg_basename: str,
    folder: str = "/",
) -> List[Tuple[str, str]]:
    """
    Todas las rutas ``(carpeta_gphoto, nombre)`` de un JPEG con ese basename en la tarjeta.
    Recorrido recursivo desde ``folder`` (típicamente ``/``).
    """
    needle = os.path.basename((jpg_basename or "").strip())
    if not needle:
        return []
    hits: List[Tuple[str, str]] = []

    def walk(path: str) -> None:
        try:
            camera_list = camera.folder_list_files(path)
            for j in range(camera_list.count()):
                fn = camera_list.get_name(j)
                low = fn.lower()
                if fn.lower() == needle.lower() and (
                    low.endswith(".jpg") or low.endswith(".jpeg")
                ):
                    hits.append((path, fn))
        except Exception:  # noqa: BLE001
            pass
        try:
            folders = camera.folder_list_folders(path)
            for i in range(folders.count()):
                subfolder = folders.get_name(i)
                full_subfolder = os.path.join(path, subfolder).replace("\\", "/")
                walk(full_subfolder)
        except Exception:  # noqa: BLE001
            pass

    walk(folder)
    hits.sort(key=lambda pair: (pair[0], pair[1]))
    return hits


def delete_jpeg_by_basename(
    camera,
    gp,
    jpg_basename: str,
    folder: str = "/",
    *,
    log: Optional[logging.Logger] = None,
) -> str:
    """
    Busca ``jpg_basename`` en toda la tarjeta y borra todas las coincidencias.
    Retorna ``deleted`` si al menos un ``file_delete`` tuvo éxito, ``absent`` si no había ninguna.
    """
    logger = log or logging.getLogger(__name__)
    paths = find_all_jpeg_paths_on_camera(camera, gp, jpg_basename, folder)
    if not paths:
        return "absent"
    if len(paths) > 1:
        logger.warning(
            "Varias copias de %s en cámara (%s); se intentará borrar todas",
            jpg_basename,
            ", ".join(f"{f}/{n}" for f, n in paths),
        )
    deleted_any = False
    for jf, jn in paths:
        status = delete_jpeg_status(camera, gp, jf, jn)
        if status == "deleted":
            deleted_any = True
        elif status == "absent":
            logger.info("JPG ya ausente en cámara: %s/%s", jf, jn)
    return "deleted" if deleted_any else "absent"


def delete_jpeg_status(camera, gp, folder: str, name: str) -> str:
    """
    Borra un JPEG en cámara. Retorna ``\"deleted\"`` o ``\"absent\"`` (ya no existía).
    Lanza otras excepciones sin modificar.
    """
    try:
        camera.file_delete(folder, name)
        return "deleted"
    except BaseException as e:  # noqa: BLE001
        if is_not_found_error(e, gp):
            return "absent"
        raise


def find_latest_raw_on_camera(
    camera,
    gp,
    folder: str = "/",
    *,
    last_found_folder: Optional[list] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Busca el RAW más reciente por nombre (orden alfabético) recorriendo carpetas.
    Retorna (folder, file) o (None, None).
    """
    cache = last_found_folder if last_found_folder is not None else [None]
    if cache[0] and cache[0] != folder:
        r = _buscar_en_carpeta(camera, cache[0], None, True)
        if r[1]:
            return r

    r = _buscar_en_carpeta(camera, folder, None, True)
    if r[1]:
        cache[0] = r[0]
        return r

    try:
        folders = camera.folder_list_folders(folder)
        for i in range(folders.count()):
            subfolder = folders.get_name(i)
            full_subfolder = os.path.join(folder, subfolder).replace("\\", "/")
            r = _buscar_en_carpeta(camera, full_subfolder, None, True)
            if r[1]:
                cache[0] = r[0]
                return r
            r2 = find_latest_raw_on_camera(
                camera,
                gp,
                full_subfolder,
                last_found_folder=cache,
            )
            if r2[1]:
                return r2
    except Exception:  # noqa: BLE001
        pass

    return None, None


def trigger_capture_and_get_raw_name(camera, gp) -> Optional[str]:
    """
    Dispara una captura y retorna el nombre ``.CR3`` (derivado del reportado por gphoto).

    No descarga archivos. Si ``capture()`` no reporta nombre, delega un fallback
    acotado a ``resolve_raw_name_after_capture`` (listar RAW más reciente una vez).

    Preferir ``trigger_eos_remote_immediate`` en digitación automática (mucho más rápido);
    este camino bloquea ~hasta que PTP publica el archivo.
    """
    file_path = camera.capture(gp.GP_CAPTURE_IMAGE)
    reported = getattr(file_path, "name", None)
    if reported is None:
        return resolve_raw_name_after_capture(camera, gp, None)
    s = str(reported).strip()
    if not s:
        return resolve_raw_name_after_capture(camera, gp, None)
    return resolve_raw_name_after_capture(camera, gp, s)


_EOSREMOTERELEASE_PATHS = (
    "main/actions/eosremoterelease",
    "eosremoterelease",
)


def _config_widget_at_path(config, gp, path: str):
    partes = [p for p in str(path).split("/") if p]
    widget = config
    for parte in partes:
        gp_ok, child = gp.gp_widget_get_child_by_name(widget, parte)
        if gp_ok < gp.GP_OK:
            return None
        widget = child
    return widget


def _eosremoterelease_choice_label(widget, gp, *, want_immediate: bool) -> Optional[str]:
    """Resuelve label locale-aware para Immediate o None."""
    from print_scanner_app.infrastructure.camera.camera_config_locale import get_widget_choices

    choices = get_widget_choices(widget, gp)
    if not choices:
        return None
    if want_immediate:
        for c in choices:
            if str(c).strip().casefold() == "immediate":
                return c
        # Fallback índice 5 (Canon EOS típico: 0 None … 5 Immediate)
        if len(choices) > 5:
            return choices[5]
        return None
    for c in choices:
        low = str(c).strip().casefold()
        if low in ("none", "ninguno"):
            return c
    return choices[0] if choices else None


def trigger_eos_remote_immediate(camera, gp) -> bool:
    """
    Dispara still vía ``eosremoterelease=Immediate`` y vuelve a ``None``.

    No espera a que el CR3 sea visible por PTP (típicamente << ``capture()``).
    """
    try:
        config = camera.get_config()
    except Exception:  # noqa: BLE001
        return False
    widget = None
    for path in _EOSREMOTERELEASE_PATHS:
        widget = _config_widget_at_path(config, gp, path)
        if widget is not None:
            break
    if widget is None:
        return False
    immediate = _eosremoterelease_choice_label(widget, gp, want_immediate=True)
    if not immediate:
        return False
    try:
        gp.gp_widget_set_value(widget, immediate)
        camera.set_config(config)
    except Exception:  # noqa: BLE001
        return False
    # Restaurar None (best-effort; el disparo ya se envió).
    try:
        config2 = camera.get_config()
        w2 = None
        for path in _EOSREMOTERELEASE_PATHS:
            w2 = _config_widget_at_path(config2, gp, path)
            if w2 is not None:
                break
        if w2 is not None:
            none_lbl = _eosremoterelease_choice_label(w2, gp, want_immediate=False)
            if none_lbl:
                gp.gp_widget_set_value(w2, none_lbl)
                camera.set_config(config2)
    except Exception:  # noqa: BLE001
        pass
    return True


_VIEWFINDER_PATHS = (
    "main/actions/viewfinder",
    "viewfinder",
)


def disable_viewfinder_best_effort(camera, gp) -> bool:
    """
    Apaga EVF/viewfinder antes de ``camera.exit()`` (best-effort).

    Reduce el riesgo de dejar la Canon en ``[-110] I/O in progress`` tras
    live view / ``capture_preview``.
    """
    try:
        config = camera.get_config()
    except Exception:  # noqa: BLE001
        return False
    widget = None
    for path in _VIEWFINDER_PATHS:
        widget = _config_widget_at_path(config, gp, path)
        if widget is not None:
            break
    if widget is None:
        return False
    try:
        # Toggle/int: 0 = off. Choice widgets: primer label "Off"/equivalente.
        try:
            gp.gp_widget_set_value(widget, 0)
        except Exception:  # noqa: BLE001
            from print_scanner_app.infrastructure.camera.camera_config_locale import get_widget_choices

            choices = get_widget_choices(widget, gp) or []
            off_lbl = None
            for c in choices:
                low = str(c).strip().casefold()
                if low in ("0", "off", "false", "no", "apagado", "desactivar"):
                    off_lbl = c
                    break
            if off_lbl is None and choices:
                off_lbl = choices[0]
            if off_lbl is None:
                return False
            gp.gp_widget_set_value(widget, off_lbl)
        camera.set_config(config)
        return True
    except Exception:  # noqa: BLE001
        return False


def raw_exists_on_camera(
    camera,
    gp,
    raw_name: str,
    *,
    last_found_folder: Optional[list] = None,
) -> bool:
    """True si el basename ``.CR3`` ya es listable en tarjeta."""
    _folder, found = find_raw_on_camera(
        camera, gp, raw_name, last_found_folder=last_found_folder
    )
    return bool(found)


def capture_preview_bytes(camera, gp) -> Optional[bytes]:
    """
    Captura preview JPEG desde cámara (equivalente conceptual a `capture_preview_from_camara`).
    Retorna bytes JPEG o None si falla.
    """
    try:
        with camera_file_scope(gp) as preview_file:
            camera.capture_preview(preview_file)
            data = preview_file.get_data_and_size()
            if not data:
                return None
            if isinstance(data, bytes):
                return data
            try:
                return bytes(data)
            except Exception:  # noqa: BLE001
                return None
    except Exception:  # noqa: BLE001
        return None
