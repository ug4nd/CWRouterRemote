from __future__ import annotations

from core.models import V2RayAConfig
from core.package_manager import PackageManager
from core.ssh_client import SSHClient


class V2RayAInstaller:
    def __init__(self, ssh: SSHClient, package_manager: PackageManager):
        self.ssh = ssh
        self.pm = package_manager

    def install(self, pm_name: str, config: V2RayAConfig, update_lists: bool = True) -> None:
        if config.install_package:
            if update_lists:
                self.pm.update(pm_name)

            core_package = "xray-core" if config.core == "xray" else "v2ray-core"
            self.pm.install(pm_name, [core_package], required=False)
            self.pm.install(pm_name, ["v2raya"], required=True)

        if config.install_luci:
            self.pm.install(pm_name, ["luci-app-v2raya"], required=False)

        if config.enable_service:
            self.start_web_ui()
        else:
            self.stop_service()

    def start_web_ui(self) -> None:
        # Запускаем v2rayA web UI, но не импортируем VLESS и не включаем VPN-режимы.
        self.ssh.logger("Запускаю v2rayA web UI ...")
        self.ssh.run_command("uci set v2raya.config.enabled='1' 2>/dev/null || true", timeout=30)
        self.ssh.run_command("uci commit v2raya 2>/dev/null || true", timeout=30)
        self.ssh.run_command("/etc/init.d/v2raya enable || true", timeout=30)
        self.ssh.run_command("/etc/init.d/v2raya restart || /etc/init.d/v2raya start || true", timeout=90)
        self.ssh.logger("v2rayA запущен. Настрой VLESS/VPN вручную через web UI.")

    def stop_service(self) -> None:
        self.ssh.logger("v2rayA не запускаю.")
        self.ssh.run_command("/etc/init.d/v2raya stop || true", timeout=60)
        self.ssh.run_command("/etc/init.d/v2raya disable || true", timeout=30)

    def status(self, config: V2RayAConfig) -> None:
        if not config.enabled:
            return

        result = self.ssh.run_command("pgrep -a v2raya || true", timeout=30)
        if result.stdout.strip():
            self.ssh.logger("v2rayA: web UI должен быть доступен на 127.0.0.1:2017")
        else:
            self.ssh.logger("v2rayA: процесс не найден")
