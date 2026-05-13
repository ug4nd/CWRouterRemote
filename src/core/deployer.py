from __future__ import annotations

from typing import Callable

from core.cloudflared import CloudflaredInstaller
from core.models import RouterConfig
from core.package_manager import PackageManager
from core.ssh_client import SSHClient
from core.v2raya import V2RayAInstaller


class RouterDeployer:
    def __init__(self, config: RouterConfig, logger: Callable[[str], None] | None = None):
        self.config = config
        self.logger = logger or (lambda message: None)

    def run(self, action: str = "deploy") -> str | None:
        errors = self.config.validate()

        # Для проверки внешнего IP Cloudflare token не нужен.
        if action == "check_public_ip":
            errors = [error for error in errors if error != "Cloudflare tunnel token пустой."]

        if errors:
            raise ValueError("Проверь настройки:\n" + "\n".join(f"- {error}" for error in errors))

        with SSHClient(self.config.ssh, logger=self.logger, dry_run=self.config.deploy.dry_run) as ssh:
            if action == "check_public_ip":
                return self._check_public_ip(ssh, self.config.deploy.public_ip_service_url)

            pm = PackageManager(ssh)
            system = pm.detect_system()

            if system.package_manager not in {"apk", "opkg"}:
                raise RuntimeError("На роутере не найден ни apk, ни opkg.")

            self.logger(
                f"OpenWrt найден: {system.package_manager}, {system.architecture}, kernel {system.kernel}"
            )

            if self.config.cloudflared.enabled:
                CloudflaredInstaller(ssh, pm).install(
                    system.package_manager,
                    self.config.cloudflared,
                    update_lists=self.config.deploy.update_package_lists,
                )

            if self.config.v2raya.enabled:
                V2RayAInstaller(ssh, pm).install(
                    system.package_manager,
                    self.config.v2raya,
                    update_lists=self.config.deploy.update_package_lists,
                )

            if self.config.deploy.check_status_after:
                CloudflaredInstaller(ssh, pm).status(self.config.cloudflared)
                V2RayAInstaller(ssh, pm).status(self.config.v2raya)

            self.logger("Готово. Дальше заходи в LuCI/v2rayA через Cloudflare routes.")
            return None

    def _check_public_ip(self, ssh: SSHClient, service_url: str) -> str:
        service_url = (service_url or "https://api.ipify.org").strip()
        if not service_url.startswith(("http://", "https://")):
            raise RuntimeError("Адрес сервера должен начинаться с http:// или https://")

        self.logger(f"Проверяю внешний IP через: {service_url}")

        safe_url = service_url.replace("'", "'\"'\"'")
        command = f"""
URL='{safe_url}'
IP="$(
  curl -4 -s --max-time 12 "$URL" 2>/dev/null ||
  wget -qO- --timeout=12 "$URL" 2>/dev/null
)"
echo "$IP" | tr -d '\\r\\n '
"""
        result = ssh.run_checked(command, timeout=25)
        ip = result.stdout.strip().splitlines()[-1].strip() if result.stdout.strip() else ""

        if not ip:
            raise RuntimeError("Не удалось получить внешний IP. Проверь интернет на роутере или адрес сервера.")

        self.logger(f"Внешний IP роутера: {ip}")
        return ip
