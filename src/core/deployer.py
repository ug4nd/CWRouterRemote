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

    def run(self) -> None:
        errors = self.config.validate()
        if errors:
            raise ValueError("Проверь настройки:\n" + "\n".join(f"- {error}" for error in errors))

        with SSHClient(self.config.ssh, logger=self.logger, dry_run=self.config.deploy.dry_run) as ssh:
            pm = PackageManager(ssh)
            system = pm.detect_system()

            if system.package_manager not in {"apk", "opkg"}:
                raise RuntimeError("На роутере не найден ни apk, ни opkg.")

            self.logger(
                f"OpenWrt найден: {system.package_manager}, {system.architecture}, kernel {system.kernel}"
            )

            cloudflared = CloudflaredInstaller(ssh, pm)
            v2raya = V2RayAInstaller(ssh, pm)

            if self.config.cloudflared.enabled:
                cloudflared.install(
                    system.package_manager,
                    self.config.cloudflared,
                    update_lists=self.config.deploy.update_package_lists,
                )

            if self.config.v2raya.enabled:
                v2raya.install(
                    system.package_manager,
                    self.config.v2raya,
                    update_lists=self.config.deploy.update_package_lists,
                )

            if self.config.deploy.check_status_after:
                cloudflared.status(self.config.cloudflared)
                v2raya.status(self.config.v2raya)

            self.logger("Готово.")
