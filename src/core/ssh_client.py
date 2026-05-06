from __future__ import annotations

from dataclasses import dataclass
import socket

import paramiko


@dataclass
class RouterInfo:
    host: str
    username: str
    openwrt_release: str
    architecture: str
    package_manager: str


class SSHConnectionError(Exception):
    pass


class RouterSSHClient:
    def __init__(self) -> None:
        self.client: paramiko.SSHClient | None = None
        self.router_info: RouterInfo | None = None

    def connect(self, host: str, username: str, password: str, timeout: int = 8) -> RouterInfo:
        self.disconnect()

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(
                hostname=host,
                username=username,
                password=password,
                timeout=timeout,
                banner_timeout=timeout,
                auth_timeout=timeout,
                look_for_keys=False,
                allow_agent=False,
            )
        except (paramiko.AuthenticationException, paramiko.SSHException, socket.error) as e:
            raise SSHConnectionError(f"Не удалось подключиться по SSH: {e}") from e

        openwrt_release = self._run_command(
            client,
            r". /etc/openwrt_release 2>/dev/null && echo ${DISTRIB_RELEASE:-unknown}"
        )
        architecture = self._run_command(client, "uname -m")
        package_manager = self._run_command(
            client,
            r"if command -v apk >/dev/null 2>&1; then echo apk; "
            r"elif command -v opkg >/dev/null 2>&1; then echo opkg; "
            r"else echo none; fi"
        )

        info = RouterInfo(
            host=host,
            username=username,
            openwrt_release=openwrt_release.strip() or "unknown",
            architecture=architecture.strip() or "unknown",
            package_manager=package_manager.strip() or "none",
        )

        self.client = client
        self.router_info = info
        return info

    def disconnect(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
            self.router_info = None

    def is_connected(self) -> bool:
        if self.client is None:
            return False
        transport = self.client.get_transport()
        return transport is not None and transport.is_active()

    def run_command(self, command: str, timeout: int = 15) -> tuple[int, str, str]:
        if self.client is None:
            raise SSHConnectionError("SSH-сессия не установлена")

        stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        return exit_code, out, err

    @staticmethod
    def _run_command(client: paramiko.SSHClient, command: str, timeout: int = 10) -> str:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        _ = stdout.channel.recv_exit_status()
        return stdout.read().decode("utf-8", errors="replace").strip()