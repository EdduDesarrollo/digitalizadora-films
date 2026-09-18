from __future__ import annotations

import argparse
import logging
from pathlib import Path

from print_scanner_app.infrastructure.logging.logger_factory import build_logger
from print_scanner_app.infrastructure.system.env_tools import project_root_from_here


def parse_args(argv: list[str] | None = None):
    p = argparse.ArgumentParser(description="Print Scanner")
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    p.add_argument(
        "--no-startup",
        action="store_true",
        help="No ejecutar StartupService automático al abrir la ventana Kivy",
    )
    p.add_argument(
        "--no-usb-reset-on-startup",
        action="store_true",
        help="Omitir reset USB en arranque (útil en desarrollo; más rápido)",
    )
    return p.parse_args(argv)


def bootstrap(argv: list[str] | None = None) -> tuple[argparse.Namespace, logging.Logger]:
    args = parse_args(argv)
    level = getattr(logging, args.log_level.upper(), logging.INFO)
    root = project_root_from_here(Path(__file__).resolve().parent)
    log_path = root / "print_scanner_app" / "logs" / "app.log"
    logger = build_logger("print_scanner_app", level=level, log_file=log_path)
    return args, logger
