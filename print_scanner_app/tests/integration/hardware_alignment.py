"""
Alineación E2E: preview → detectar sprocket → move_film(1) si no hay blob.

No dispara RAW. Sin ventanas debug.

Uso:

    DIGITALIZADORA_HARDWARE_TEST=1 python -m print_scanner_app.tests.integration.hardware_alignment

Requiere: cámara USB, impresora ``/dev/usb/lp*``, film cargado, ``config.json``.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from print_scanner_app.app.container import Container
from print_scanner_app.domain.policies.alignment_constants import (
    ALIGNMENT_MAX_INTENTOS,
    ALIGNMENT_SEARCH_STEP_PX,
)
from print_scanner_app.infrastructure.logging.logger_factory import build_logger
from print_scanner_app.ui.presenters.app_presenter import AppPresenter


@dataclass(frozen=True)
class HardwareAlignmentOutcome:
    aligned: bool
    steps: int
    white_pixel_count: int
    umbral: int
    last_jpeg_path: Optional[Path]
    error: str | None = None


def _repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[3]


def run_hardware_alignment(
    project_root: Path,
    *,
    logger: Optional[logging.Logger] = None,
) -> HardwareAlignmentOutcome:
    log = logger or logging.getLogger(__name__)
    container = Container(project_root, None, log)
    presenter = AppPresenter(container=container, logger=log)
    presenter.clear_debug_ui()

    started = presenter.run_start_digitization()
    if not started.ok:
        return HardwareAlignmentOutcome(
            aligned=False,
            steps=0,
            white_pixel_count=0,
            umbral=presenter.get_threshold(),
            last_jpeg_path=None,
            error=started.error or "no se pudo iniciar digitación",
        )

    logs_dir = project_root / "print_scanner_app" / "logs"
    last_jpeg: Path | None = None
    count = 0
    aligned = False
    steps = 0
    err: str | None = None
    try:
        umbral = presenter.get_threshold()
        for steps in range(ALIGNMENT_MAX_INTENTOS):
            jpeg = presenter._capture_preview_for_alignment()
            if not jpeg:
                err = presenter._capture_last_error or "sin preview"
                break
            result = presenter._analyze_alignment_from_jpeg(jpeg)
            if result is None:
                err = presenter._capture_last_error or "análisis nulo"
                break
            count = int(result.white_pixel_count)
            if result.aligned:
                aligned = True
                log.info(
                    "hardware-align ok steps=%s blob_area=%s umbral=%s roi=%s",
                    steps,
                    count,
                    umbral,
                    result.roi_effective,
                )
                break
            ok_move = presenter._container.printer_service().move_film(ALIGNMENT_SEARCH_STEP_PX)
            if not ok_move:
                err = "fallo move_film"
                break
            log.info(
                "hardware-align step=%s blob_area=%s umbral=%s",
                steps,
                count,
                umbral,
            )
        else:
            err = (
                f"no alineó en {ALIGNMENT_MAX_INTENTOS} pasos "
                f"(blob_area={count}, umbral={umbral})"
            )
            last_jpeg = logs_dir / "hardware_align_last.jpg"
            logs_dir.mkdir(parents=True, exist_ok=True)
            jpeg_fail = presenter._last_captured_preview_jpeg
            if jpeg_fail:
                last_jpeg.write_bytes(jpeg_fail)
        if not aligned and last_jpeg is None and presenter._last_captured_preview_jpeg:
            logs_dir.mkdir(parents=True, exist_ok=True)
            last_jpeg = logs_dir / "hardware_align_last.jpg"
            last_jpeg.write_bytes(presenter._last_captured_preview_jpeg)
        return HardwareAlignmentOutcome(
            aligned=aligned,
            steps=steps if aligned else min(steps + 1, ALIGNMENT_MAX_INTENTOS),
            white_pixel_count=count,
            umbral=umbral,
            last_jpeg_path=last_jpeg,
            error=None if aligned else err,
        )
    finally:
        presenter.run_stop_digitization()


def main() -> int:
    root = _repo_root_from_here()
    log = build_logger(
        "hardware_alignment",
        level=logging.INFO,
        log_file=root / "print_scanner_app" / "logs" / "app.log",
    )
    out = run_hardware_alignment(root, logger=log)
    if out.aligned:
        print(f"OK aligned steps={out.steps} blob_area={out.white_pixel_count}")
        return 0
    print(f"FAIL {out.error} jpeg={out.last_jpeg_path}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
