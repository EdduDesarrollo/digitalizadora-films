from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


def main(argv: list[str] | None = None) -> int:
    from print_scanner_app.app.bootstrap import bootstrap
    from print_scanner_app.ui.kivy_app import run_modular_app

    args, logger = bootstrap(argv or sys.argv[1:])
    logger.info("Iniciando UI (Kivy)...")
    run_modular_app(
        logger,
        auto_startup=not args.no_startup,
        startup_reset_usb=not args.no_usb_reset_on_startup,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
