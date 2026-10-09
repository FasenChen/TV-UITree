"""Typed device connection settings shared by CLI and MCP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from tvuitree.infrastructure import device_config
from tvuitree.infrastructure.adb import Adb, resolve_adb


@dataclass(frozen=True)
class ConnectionOptions:
    TV_IP_Address: Optional[str] = None
    port: Optional[int] = None
    adb: Optional[str] = None
    no_connect: bool = False
    serial: Optional[str] = None

    @property
    def target(self) -> str:
        return self.serial if self.serial is not None else f"{self.TV_IP_Address}:{self.port}"


def _check_address(address: object) -> str:
    if not isinstance(address, str) or not address.strip():
        raise ValueError("TV_IP_Address 必须是非空字符串，请检查 config.json")
    if address != address.strip() or ":" in address or any(
        character.isspace() for character in address
    ):
        raise ValueError("TV_IP_Address 只能填写 IP 或主机名，不含端口")
    return address


def _check_port(port: object) -> int:
    if isinstance(port, bool) or not isinstance(port, int) or not (1 <= port <= 65535):
        raise ValueError("port 必须是 1 到 65535 的整数，请检查 config.json")
    return port


def _check_serial(serial: object) -> str:
    if not isinstance(serial, str) or not serial or ":" in serial or any(
        character.isspace() or not character.isprintable() for character in serial
    ):
        raise ValueError("serial 必须是 adb devices 中的非空 USB 序列号，不含空白、控制字符或冒号")
    return serial


def connection_options(*, TV_IP_Address: Optional[str] = None,
                       port: Optional[int] = None, adb: Optional[str] = None,
                       no_connect: bool = False, serial: Optional[str] = None) -> ConnectionOptions:
    """显式参数覆盖 config 默认值，供 CLI 与 MCP 共用。"""
    config = device_config.load_device_config()
    if serial is not None and (TV_IP_Address is not None or port is not None):
        raise ValueError("serial 与 TV_IP_Address/port 不能同时指定")
    selected_serial = serial
    if serial is None and TV_IP_Address is None and port is None:
        selected_serial = config.get("serial")
    if selected_serial is not None:
        selected_serial = _check_serial(selected_serial)
        address, selected_port = None, None
    else:
        address = _check_address(
            config.get("TV_IP_Address") if TV_IP_Address is None else TV_IP_Address)
        selected_port = _check_port(config.get("port") if port is None else port)
    selected_adb = config.get("adb") if adb is None else adb
    if selected_adb is not None and (
        not isinstance(selected_adb, str) or not selected_adb.strip()
    ):
        raise ValueError("adb 必须是非空路径字符串，请检查 config.json")
    return ConnectionOptions(address, selected_port, adb=selected_adb,
                             no_connect=no_connect, serial=selected_serial)


def update_default_device(*, TV_IP_Address: Optional[str] = None,
                          port: Optional[int] = None, serial: Optional[str] = None) -> dict:
    """校验并写入新的默认目标；config 里其他字段保持原样。"""
    config = device_config.load_device_config()
    previous = ({"serial": config["serial"]} if config.get("serial") is not None else
                {"TV_IP_Address": config.get("TV_IP_Address"), "port": config.get("port")})
    if serial is not None:
        if TV_IP_Address is not None or port is not None:
            raise ValueError("serial 与 TV_IP_Address/port 不能同时指定")
        current = {"serial": _check_serial(serial)}
    else:
        address = _check_address(TV_IP_Address)
        selected_port = _check_port(config.get("port") if port is None else port)
        current = {"TV_IP_Address": address, "port": selected_port}
        config.pop("serial", None)
    config.update(current)
    device_config.save_device_config(config)
    return {
        "previous": previous,
        "current": current,
        "config_path": str(device_config.CONFIG_PATH),
    }


def connect_device(options: ConnectionOptions, *, quiet: bool = False) -> Optional[Adb]:
    """返回已连接设备或 None；文案属于 interfaces。"""
    device = Adb(resolve_adb(options.adb), options.target,
                 auto_connect=not options.no_connect)
    return device if device.connect(quiet=quiet) else None
