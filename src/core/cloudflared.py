from __future__ import annotations

from core.models import CloudflaredConfig
from core.package_manager import PackageManager
from core.ssh_client import SSHClient


class CloudflaredInstaller:
    def __init__(self, ssh: SSHClient, package_manager: PackageManager):
        self.ssh = ssh
        self.pm = package_manager

    def install(self, pm_name: str, config: CloudflaredConfig, update_lists: bool = True) -> None:
        if config.install_package:
            if update_lists:
                self.pm.update(pm_name)
            self.pm.install(pm_name, ["cloudflared"], required=True)

        if config.install_luci:
            self.pm.install(pm_name, ["luci-app-cloudflared"], required=False)

        if config.configure_token_service:
            self.configure_token_service(config)

    def configure_token_service(self, config: CloudflaredConfig) -> None:
        token = config.tunnel_token.strip()
        if not token:
            raise ValueError("Cloudflare tunnel token пустой.")

        self.ssh.logger("Проверяю cloudflared ...")
        self.ssh.run_checked("command -v cloudflared >/dev/null 2>&1", timeout=30)

        self.ssh.logger("Настраиваю Cloudflare tunnel ...")

        self.ssh.run_checked("mkdir -p /etc/cloudflared", timeout=30)
        self.ssh.write_remote_file(config.token_path, token + "\n", mode="0600", timeout=30)

        init_script = f"""#!/bin/sh /etc/rc.common

START=99
STOP=10
USE_PROCD=1

start_service() {{
    TOKEN="$(cat {config.token_path})"

    procd_open_instance
    procd_set_param command /usr/bin/cloudflared tunnel --no-autoupdate run --token "$TOKEN"
    procd_set_param respawn
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
}}
"""
        self.ssh.write_remote_file(config.init_script_path, init_script, mode="0755", timeout=30)

        self.ssh.run_checked(f"{config.init_script_path} enable", timeout=30)
        self.ssh.run_checked(f"{config.init_script_path} restart", timeout=90)
        self.ssh.logger("Cloudflare tunnel настроен и запущен.")

    def status(self, config: CloudflaredConfig) -> None:
        if not config.enabled:
            return

        result = self.ssh.run_command("pgrep -a cloudflared || true", timeout=30)
        if result.stdout.strip():
            self.ssh.logger("cloudflared: работает")
        else:
            self.ssh.logger("cloudflared: процесс не найден")
