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

    def _validate_for_action(self, action: str) -> None:
        errors = self.config.validate()

        no_cloudflare_token_actions = {
            "test_ssh",
            "detect_system",
            "install_cloudflared",
            "install_cloudflared_luci",
            "check_cloudflared",
            "install_v2raya",
            "install_v2raya_luci",
            "configure_v2raya",
            "check_v2raya",
        }

        no_vless_actions = {
            "test_ssh",
            "detect_system",
            "install_cloudflared",
            "install_cloudflared_luci",
            "configure_cloudflared",
            "check_cloudflared",
            "install_v2raya",
            "install_v2raya_luci",
            "check_v2raya",
        }

        if action in no_cloudflare_token_actions:
            errors = [error for error in errors if error != "Cloudflared tunnel token is empty."]

        if action in no_vless_actions:
            errors = [error for error in errors if error != "v2rayA VLESS URI is empty."]

        if errors:
            raise ValueError("Проверка настроек не пройдена:\n" + "\n".join(f"- {error}" for error in errors))

    def run(self, action: str = "deploy_selected") -> None:
        self._validate_for_action(action)

        with SSHClient(self.config.ssh, logger=self.logger, dry_run=self.config.deploy.dry_run) as ssh:
            pm = PackageManager(ssh)

            if action == "test_ssh":
                ssh.run_checked(
                    "echo SSH_OK; "
                    "echo USER=$(whoami 2>/dev/null || echo unknown); "
                    "echo SHELL=$SHELL; "
                    "cat /etc/openwrt_release 2>/dev/null || true; "
                    "uname -a 2>/dev/null || true",
                    timeout=30,
                )
                self.logger("SSH-подключение работает.")
                return

            system = pm.detect_system()
            self._log_system(system)

            if system.package_manager not in {"apk", "opkg"}:
                raise RuntimeError("На роутере не найден ни apk, ни opkg.")

            if action == "detect_system":
                self.logger("Проверка системы завершена.")
                return

            cloudflared = CloudflaredInstaller(ssh, pm)
            v2raya = V2RayAInstaller(ssh, pm)

            if action == "install_cloudflared":
                if self.config.deploy.update_package_lists:
                    pm.update(system.package_manager)
                pm.install(system.package_manager, ["cloudflared"], required=True)
                self.logger("cloudflared установлен.")
                return

            if action == "install_cloudflared_luci":
                if self.config.deploy.update_package_lists:
                    pm.update(system.package_manager)
                pm.install(system.package_manager, ["luci-app-cloudflared"], required=False)
                self.logger("LuCI для cloudflared установлен, если пакет доступен в feeds.")
                return

            if action == "configure_cloudflared":
                cloudflared.configure_token_service(self.config.cloudflared)
                self.logger("cloudflared tunnel service настроен.")
                return

            if action == "check_cloudflared":
                cloudflared.status(self.config.cloudflared)
                self.logger("Проверка cloudflared завершена.")
                return

            if action == "install_v2raya":
                core_package = "xray-core" if self.config.v2raya.core == "xray" else "v2ray-core"
                if self.config.deploy.update_package_lists:
                    pm.update(system.package_manager)
                pm.install(system.package_manager, [core_package], required=False)
                pm.install(system.package_manager, ["v2raya"], required=True)
                v2raya.disable_runtime(self.config.v2raya)
                self.logger("v2rayA установлен и оставлен выключенным.")
                return

            if action == "install_v2raya_luci":
                if self.config.deploy.update_package_lists:
                    pm.update(system.package_manager)
                pm.install(system.package_manager, ["luci-app-v2raya"], required=False)
                self.logger("LuCI для v2rayA установлен, если пакет доступен в feeds.")
                return

            if action == "configure_v2raya":
                v2raya.prepare_vless_config(self.config.v2raya)
                v2raya.disable_runtime(self.config.v2raya)
                self.logger("v2rayA сконфигурирован как подготовленный, но VPN выключен.")
                return

            if action == "check_v2raya":
                v2raya.status(self.config.v2raya)
                self.logger("Проверка v2rayA завершена.")
                return

            if action == "deploy_selected":
                cloudflared.install(
                    system.package_manager,
                    self.config.cloudflared,
                    update_lists=self.config.deploy.update_package_lists,
                )

                v2raya.install(
                    system.package_manager,
                    self.config.v2raya,
                    update_lists=self.config.deploy.update_package_lists,
                )

                if self.config.deploy.check_status_after:
                    cloudflared.status(self.config.cloudflared)
                    v2raya.status(self.config.v2raya)

                self.logger("Выбранные действия завершены.")
                return

            raise ValueError(f"Неизвестное действие: {action}")

    def _log_system(self, system) -> None:
        self.logger("Система определена:")
        self.logger(f"  пакетный менеджер: {system.package_manager}")
        self.logger(f"  архитектура: {system.architecture}")
        self.logger(f"  kernel: {system.kernel}")
        if system.openwrt_release:
            self.logger(system.openwrt_release)
