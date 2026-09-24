"""Typed device connection settings shared by CLI and MCP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from tvuitree.infrastructure.adb import Adb, resolve_adb
from tvuitree.infrastructure.device_config import load_device_config


@dataclass(frozen=True)
class ConnectionOptions:
    TV_IP_Address: str
    port: int
    adb: Optional[str] = None
    no_connect: bool = False

    @property
    def target(self) -> str:
        return f"{self.TV_IP_Address}:{self.port}"


def connection_options(*, TV_IP_Address: Optional[str] = None,
                       port: Optional[int] = None, adb: Optional[str] = None,
                       no_connect: bool = False) -> ConnectionOptions:
    """Resolve explicit values over config defaults for both CLI and MCP."""
    config = load_device_config()
    address = config.get("TV_IP_Address") if TV_IP_Address is None else TV_IP_Address
    selected_port = config.get("port") if port is None else port
    selected_adb = config.get("adb") if adb is None else adb
    if not isinstance(address, str) or not address.strip():
        raise ValueError("TV_IP_Address 必须是非空字符串，请检查 config.json")
    if address != address.strip() or ":" in address or any(
        character.isspace() for character in address
    ):
        raise ValueError("TV_IP_Address 只能填写 IP 或主机名，不含端口")
    if isinstance(selected_port, bool) or not isinstance(selected_port, int) or not (
        1 <= selected_port <= 65535
    ):
        raise ValueError("port 必须是 1 到 65535 的整数，请检查 config.json")
    if selected_adb is not None and (
        not isinstance(selected_adb, str) or not selected_adb.strip()
    ):
        raise ValueError("adb 必须是非空路径字符串，请检查 config.json")
    return ConnectionOptions(address, selected_port, adb=selected_adb, no_connect=no_connect)


def connect_device(options: ConnectionOptions, *, quiet: bool = False) -> Optional[Adb]:
    """Return a connected device or None; presentation belongs to interfaces."""
    device = Adb(resolve_adb(options.adb), options.target,
                 auto_connect=not options.no_connect)
    return device if device.connect(quiet=quiet) else None
