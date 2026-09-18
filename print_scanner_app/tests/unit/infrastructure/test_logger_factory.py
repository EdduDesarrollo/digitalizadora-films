import logging
import uuid
from pathlib import Path

from print_scanner_app.infrastructure.logging.logger_factory import build_logger


def test_build_logger_with_file(tmp_path: Path):
    p = tmp_path / "a.log"
    log = build_logger(f"app.{uuid.uuid4().hex}", log_file=p)
    log.info("x")
    assert p.is_file()


def test_build_logger_second_call_reuses_handlers():
    name = f"dup.{uuid.uuid4().hex}"
    build_logger(name)
    build_logger(name, level=logging.DEBUG)
