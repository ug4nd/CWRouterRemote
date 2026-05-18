from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Optional

import paramiko


@dataclass
class CommandResult:
    code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.code == 0


class RouterSSH:
    def __init__(self, host: str, username: str, password: str, port: int = 22, timeout: int = 15):
        self.host = host.strip()
        self.username = username.strip()
        self.password = password
        self.port = int(port)
        self.timeout = int(timeout)
        self.client: Optional[paramiko.SSHClient] = None

    def __enter__(self) -> "RouterSSH":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def connect(self) -> None:
        if not self.host:
            raise ValueError("Не указан адрес роутера")
        if not self.username:
            raise ValueError("Не указан SSH логин")
        if not self.password:
            raise ValueError("Не указан SSH пароль")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=self.timeout,
                banner_timeout=self.timeout,
                auth_timeout=self.timeout,
                look_for_keys=False,
                allow_agent=False,
            )
        except (socket.timeout, OSError, paramiko.SSHException) as exc:
            raise RuntimeError(f"Не удалось подключиться по SSH: {exc}") from exc
        self.client = client

    def close(self) -> None:
        if self.client:
            self.client.close()
            self.client = None

    def run(self, command: str, timeout: int = 120) -> CommandResult:
        if not self.client:
            raise RuntimeError("SSH не подключен")
        stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        return CommandResult(code, out, err)

    def upload_text(self, text: str, remote_path: str) -> None:
        if not self.client:
            raise RuntimeError("SSH не подключен")
        sftp = self.client.open_sftp()
        try:
            with sftp.file(remote_path, "w") as f:
                f.write(text)
        finally:
            sftp.close()
