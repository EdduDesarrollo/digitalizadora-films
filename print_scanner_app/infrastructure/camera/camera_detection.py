from __future__ import annotations

import subprocess
from typing import Callable, List, Tuple

from print_scanner_app.infrastructure.camera.gphoto_client import GPhotoClient, gphoto_cli_usb_ports, list_camera_addresses
from print_scanner_app.infrastructure.system.mount_tools import unmount_camera_mounts

Run = Callable[..., subprocess.CompletedProcess]


def prepare_and_list_cameras(
    client: GPhotoClient,
    *,
    run: Run = subprocess.run,
    unmount_first: bool = True,
) -> List[Tuple[str, str]]:
    if unmount_first:
        unmount_camera_mounts(run=run)
    return list_camera_addresses(client, run=run)


__all__ = ["prepare_and_list_cameras", "gphoto_cli_usb_ports", "list_camera_addresses"]
