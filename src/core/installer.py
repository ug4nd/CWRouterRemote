from __future__ import annotations

from core.ssh_client import RouterSSHClient, SSHConnectionError


class InstallError(Exception):
    pass


class CloudflaredInstaller:
    def __init__(self, ssh_client: RouterSSHClient) -> None:
        self.ssh_client = ssh_client

    def install_from_repo(self) -> list[str]:
        if not self.ssh_client.is_connected():
            raise InstallError("SSH-сессия не установлена")

        info = self.ssh_client.router_info
        if info is None:
            raise InstallError("Нет информации о роутере")

        logs: list[str] = []
        logs.append(f"Начинаю установку cloudflared через {info.package_manager}")

        if info.package_manager == "apk":
            commands = [
                ("Обновляю индекс apk", "apk update"),
                ("Устанавливаю cloudflared", "apk add cloudflared"),
            ]
        elif info.package_manager == "opkg":
            commands = [
                ("Обновляю индекс opkg", "opkg update"),
                ("Устанавливаю cloudflared", "opkg install cloudflared"),
            ]
        else:
            raise InstallError("Неизвестный пакетный менеджер")

        for title, command in commands:
            logs.append(f"[RUN] {title}")
            exit_code, out, err = self.ssh_client.run_command(command, timeout=120)

            if out:
                logs.append(out)
            if err:
                logs.append(err)

            if exit_code != 0:
                raise InstallError(
                    f"{title} завершилось с ошибкой (exit code {exit_code})"
                )

        logs.append("[RUN] Проверяю наличие cloudflared")
        exit_code, out, err = self.ssh_client.run_command(
            "command -v cloudflared || which cloudflared",
            timeout=20,
        )

        if out:
            logs.append(out)
        if err:
            logs.append(err)

        if exit_code != 0 or not out.strip():
            raise InstallError("cloudflared не найден после установки")

        logs.append("[OK] cloudflared установлен")
        return logs