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

        if config.prepare_vless_config:
            self.prepare_vless_config(config)

        if config.enable_service:
            self.enable_runtime()
        else:
            self.disable_runtime()

    def prepare_vless_config(self, config: V2RayAConfig) -> None:
        vless_uri = config.vless_uri.strip()
        if not vless_uri:
            raise ValueError("VLESS/Xray ссылка пустая.")

        self.ssh.logger("Сохраняю VLESS/Xray ссылку. VPN не включаю ...")
        self.ssh.run_checked("mkdir -p /etc/v2raya", timeout=30)
        self.ssh.write_remote_file(config.prepared_config_path, vless_uri + "\n", mode="0600", timeout=30)

        note = f"""CFRRemote

VLESS/Xray link saved to:
{config.prepared_config_path}

VPN is intentionally disabled.
Import/connect it manually in v2rayA later.
"""
        self.ssh.write_remote_file("/etc/v2raya/CFRRemote_README.txt", note, mode="0644", timeout=30)
        self.ssh.logger("VLESS/Xray ссылка сохранена.")

    def enable_runtime(self) -> None:
        self.ssh.logger("Включаю v2rayA ...")
        self.ssh.run_command("uci set v2raya.config.enabled='1' 2>/dev/null || true", timeout=30)
        self.ssh.run_command("uci commit v2raya 2>/dev/null || true", timeout=30)
        self.ssh.run_command("/etc/init.d/v2raya enable || true", timeout=30)
        self.ssh.run_command("/etc/init.d/v2raya restart || /etc/init.d/v2raya start || true", timeout=90)

    def disable_runtime(self) -> None:
        self.ssh.logger("Оставляю v2rayA выключенным ...")
        self.ssh.run_command("uci set v2raya.config.enabled='0' 2>/dev/null || true", timeout=30)
        self.ssh.run_command("uci commit v2raya 2>/dev/null || true", timeout=30)
        self.ssh.run_command("/etc/init.d/v2raya stop || true", timeout=60)
        self.ssh.run_command("/etc/init.d/v2raya disable || true", timeout=30)
        self.ssh.logger("v2rayA подготовлен, VPN выключен.")

    def status(self, config: V2RayAConfig) -> None:
        if not config.enabled:
            return

        result = self.ssh.run_command("pgrep -a v2raya || true", timeout=30)
        if result.stdout.strip():
            self.ssh.logger("v2rayA: процесс запущен")
        else:
            self.ssh.logger("v2rayA: процесс не запущен")
