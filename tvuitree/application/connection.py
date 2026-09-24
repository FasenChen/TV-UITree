"""Typed device connection settings shared by CLI and MCP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from tvuitree.infrastructure.adb import Adb, DEFAULT_HOST, DEFAULT_PORT, resolve_adb


@dataclass(frozen=True)
class ConnectionOptions:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    serial: Optional[str] = None
    address: Optional[str] = None
    adb: Optional[str] = None
    no_connect: bool = False

    @property
    def target(self) -> str:
        return self.serial or self.address or f"{self.host}:{self.port}"


def connect_device(options: ConnectionOptions, *, quiet: bool = False) -> Optional[Adb]:
    """Return a connected device or None; presentation belongs to interfaces."""
    device = Adb(resolve_adb(options.adb), options.target,
                 auto_connect=not options.no_connect)
    return device if device.connect(quiet=quiet) else None
