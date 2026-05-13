from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import paramiko

from core.models import SSHConfig


@dataclass
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class SSHCommandError(RuntimeError):
    def __init__(self, result: CommandResult):
        self.result = result
        details = result.stderr.strip() or result.stdout.strip() or "нет вывода"
        super().__init__(f"Команда завершилась ошибкой {result.exit_code}: {result.command}\n{details}")


class SSHClient:
    def __init__(
        self,
        config: SSHConfig,
        logger: Callable[[str], None] | None = None,
        dry_run: bool = False,
    ):
        self.config = config
        self.logger = logger or (lambda message: None)
        self.dry_run = dry_run
        self.client: paramiko.SSHClient | None = None

    def connect(self) -> None:
        self.logger(f"SSH: подключение к {self.config.username}@{self.config.host}:{self.config.port}")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict = {
            "hostname": self.config.host,
            "port": self.config.port,
            "username": self.config.username,
            "timeout": self.config.connect_timeout,
            "banner_timeout": self.config.connect_timeout,
            "auth_timeout": self.config.connect_timeout,
            "look_for_keys": False,
            "allow_agent": False,
        }

        if self.config.ssh_key_path.strip():
            key_path = Path(self.config.ssh_key_path).expanduser()
            connect_kwargs["key_filename"] = str(key_path)
            if self.config.password:
                connect_kwargs["passphrase"] = self.config.password
        else:
            connect_kwargs["password"] = self.config.password

        client.connect(**connect_kwargs)
        self.client = client
        self.logger("SSH: подключено")

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
            self.logger("SSH: отключено")

    def __enter__(self) -> "SSHClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def run_command(
        self,
        command: str,
        timeout: int | None = None,
        show_output: bool = False,
    ) -> CommandResult:
        if self.dry_run:
            self.logger(f"[dry-run] {command}")
            return CommandResult(command=command, exit_code=0, stdout="", stderr="")

        if self.client is None:
            raise RuntimeError("SSH client is not connected.")

        stdin, stdout, stderr = self.client.exec_command(
            command,
            timeout=timeout or self.config.command_timeout,
            get_pty=False,
        )

        exit_code = stdout.channel.recv_exit_status()
        out_text = stdout.read().decode("utf-8", errors="replace")
        err_text = stderr.read().decode("utf-8", errors="replace")

        if show_output:
            if out_text.strip():
                self.logger(out_text.rstrip())
            if err_text.strip():
                self.logger(err_text.rstrip())

        if exit_code != 0:
            short_err = (err_text.strip() or out_text.strip() or "нет вывода").splitlines()
            self.logger(f"Ошибка команды: {command}")
            if short_err:
                self.logger(short_err[-1])

        return CommandResult(command=command, exit_code=exit_code, stdout=out_text, stderr=err_text)

    def run_checked(
        self,
        command: str,
        timeout: int | None = None,
        show_output: bool = False,
    ) -> CommandResult:
        result = self.run_command(command, timeout=timeout, show_output=show_output)
        if not result.ok:
            raise SSHCommandError(result)
        return result

    def write_remote_file(
        self,
        remote_path: str,
        content: str,
        mode: str = "0644",
        timeout: int | None = None,
    ) -> CommandResult:
        command = f"""cat > {remote_path} <<'CWROUTERREMOTE_EOF'
{content}
CWROUTERREMOTE_EOF
chmod {mode} {remote_path}
"""
        return self.run_checked(command, timeout=timeout)
