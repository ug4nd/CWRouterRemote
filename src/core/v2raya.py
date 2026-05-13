from __future__ import annotations

from core.models import V2RayAConfig
from core.package_manager import PackageManager
from core.ssh_client import SSHClient


class V2RayAInstaller:
    def __init__(self, ssh: SSHClient, package_manager: PackageManager):
        self.ssh = ssh
        self.pm = package_manager

    def install(self, pm_name: str, config: V2RayAConfig, update_lists: bool = True) -> None:
        if not config.enabled:
            self.ssh.logger("v2rayA шаг пропущен.")
            return

        if config.install_package:
            self.ssh.logger("Устанавливаю v2rayA пакеты ...")
            if update_lists:
                self.pm.update(pm_name)

            core_package = "xray-core" if config.core == "xray" else "v2ray-core"
            self.pm.install(pm_name, [core_package], required=False)
            self.pm.install(pm_name, ["v2raya"], required=True)

            if config.install_luci:
                self.ssh.logger("Устанавливаю LuCI для v2rayA, если пакет доступен ...")
                self.pm.install(pm_name, ["luci-app-v2raya"], required=False)

        if config.prepare_vless_config:
            self.prepare_vless_config(config)

        if config.enable_service:
            self.ssh.logger("Включаю и запускаю v2rayA service ...")
            self.ssh.run_command("uci set v2raya.config.enabled='1' 2>/dev/null || true", timeout=30)
            self.ssh.run_command("uci commit v2raya 2>/dev/null || true", timeout=30)
            self.ssh.run_command("/etc/init.d/v2raya enable || true", timeout=30)
            self.ssh.run_command("/etc/init.d/v2raya restart || /etc/init.d/v2raya start || true", timeout=90)
        else:
            self.disable_runtime(config)

    def prepare_vless_config(self, config: V2RayAConfig) -> None:
        vless_uri = config.vless_uri.strip()
        if not vless_uri:
            raise ValueError("v2rayA VLESS URI is empty.")

        if not vless_uri.startswith("vless://"):
            self.ssh.logger("Предупреждение: VLESS URI не начинается с vless://. Всё равно сохраняю как есть.")

        self.ssh.logger("Сохраняю VLESS/Xray ссылку на роутере, но VPN не включаю ...")
        self.ssh.run_checked("mkdir -p /etc/v2raya", timeout=30)
        self.ssh.write_remote_file(config.prepared_config_path, vless_uri + "\n", mode="0600", timeout=30)

        note_path = "/etc/v2raya/CWRouterRemote_README.txt"
        note = f"""CWRouterRemote prepared v2rayA config

VLESS/Xray link was saved to:
{config.prepared_config_path}

VPN/proxy is intentionally NOT enabled by this tool at this stage.
Open v2rayA LuCI/Web UI later and import/connect manually, or implement API import in the next version.

"""
        self.ssh.write_remote_file(note_path, note, mode="0644", timeout=30)

    def disable_runtime(self, config: V2RayAConfig) -> None:
        self.ssh.logger("Оставляю v2rayA подготовленным, но выключенным: service disabled/stopped.")
        self.ssh.run_command("uci set v2raya.config.enabled='0' 2>/dev/null || true", timeout=30)
        self.ssh.run_command("uci commit v2raya 2>/dev/null || true", timeout=30)
        self.ssh.run_command("/etc/init.d/v2raya stop || true", timeout=60)
        self.ssh.run_command("/etc/init.d/v2raya disable || true", timeout=30)

    def status(self, config: V2RayAConfig) -> None:
        if not config.enabled:
            return

        self.ssh.logger("Проверяю v2rayA status ...")
        self.ssh.run_command("pgrep -a v2raya || true", timeout=30)
        self.ssh.run_command("/etc/init.d/v2raya status || true", timeout=30)
        self.ssh.run_command("uci show v2raya 2>/dev/null || true", timeout=30)
        self.ssh.run_command(f"ls -l {config.prepared_config_path} 2>/dev/null || true", timeout=30)
