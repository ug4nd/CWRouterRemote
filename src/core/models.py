from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SSHConfig:
    host: str = "192.168.1.1"
    port: int = 22
    username: str = "root"
    password: str = ""
    ssh_key_path: str = ""
    connect_timeout: int = 15
    command_timeout: int = 300


@dataclass
class CloudflaredConfig:
    enabled: bool = True
    install_package: bool = True
    install_luci: bool = True
    configure_token_service: bool = True
    tunnel_token: str = ""
    token_path: str = "/etc/cloudflared/token"
    init_script_path: str = "/etc/init.d/cloudflared"


@dataclass
class V2RayAConfig:
    enabled: bool = True
    install_package: bool = True
    install_luci: bool = True
    core: str = "xray"
    enable_service: bool = False
    vless_uri: str = ""
    prepare_vless_config: bool = True
    prepared_config_path: str = "/etc/v2raya/cwrouterremote_vless_uri.txt"


@dataclass
class DeployOptions:
    dry_run: bool = False
    update_package_lists: bool = True
    check_status_after: bool = True


@dataclass
class RouterConfig:
    ssh: SSHConfig = field(default_factory=SSHConfig)
    cloudflared: CloudflaredConfig = field(default_factory=CloudflaredConfig)
    v2raya: V2RayAConfig = field(default_factory=V2RayAConfig)
    deploy: DeployOptions = field(default_factory=DeployOptions)

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "RouterConfig":
        ssh_raw = raw.get("ssh", {})
        cloudflared_raw = raw.get("cloudflared", {})
        v2raya_raw = raw.get("v2raya", {})
        deploy_raw = raw.get("deploy", {})

        # Совместимость со старым плоским JSON.
        if "host" in raw:
            ssh_raw.setdefault("host", raw.get("host", "192.168.1.1"))
        if "port" in raw:
            ssh_raw.setdefault("port", raw.get("port", 22))
        if "username" in raw:
            ssh_raw.setdefault("username", raw.get("username", "root"))
        if "password" in raw:
            ssh_raw.setdefault("password", raw.get("password", ""))
        if "ssh_key_path" in raw:
            ssh_raw.setdefault("ssh_key_path", raw.get("ssh_key_path", ""))
        if "tunnel_token" in raw:
            cloudflared_raw.setdefault("tunnel_token", raw.get("tunnel_token", ""))

        return RouterConfig(
            ssh=SSHConfig(
                host=str(ssh_raw.get("host", "192.168.1.1")),
                port=int(ssh_raw.get("port", 22)),
                username=str(ssh_raw.get("username", "root")),
                password=str(ssh_raw.get("password", "")),
                ssh_key_path=str(ssh_raw.get("ssh_key_path", "")),
                connect_timeout=int(ssh_raw.get("connect_timeout", 15)),
                command_timeout=int(ssh_raw.get("command_timeout", 300)),
            ),
            cloudflared=CloudflaredConfig(
                enabled=bool(cloudflared_raw.get("enabled", True)),
                install_package=bool(cloudflared_raw.get("install_package", True)),
                install_luci=bool(cloudflared_raw.get("install_luci", True)),
                configure_token_service=bool(cloudflared_raw.get("configure_token_service", True)),
                tunnel_token=str(cloudflared_raw.get("tunnel_token", "")),
                token_path=str(cloudflared_raw.get("token_path", "/etc/cloudflared/token")),
                init_script_path=str(cloudflared_raw.get("init_script_path", "/etc/init.d/cloudflared")),
            ),
            v2raya=V2RayAConfig(
                enabled=bool(v2raya_raw.get("enabled", True)),
                install_package=bool(v2raya_raw.get("install_package", True)),
                install_luci=bool(v2raya_raw.get("install_luci", True)),
                core=str(v2raya_raw.get("core", "xray")).lower(),
                enable_service=bool(v2raya_raw.get("enable_service", False)),
                vless_uri=str(v2raya_raw.get("vless_uri", "")),
                prepare_vless_config=bool(v2raya_raw.get("prepare_vless_config", True)),
                prepared_config_path=str(
                    v2raya_raw.get("prepared_config_path", "/etc/v2raya/cwrouterremote_vless_uri.txt")
                ),
            ),
            deploy=DeployOptions(
                dry_run=bool(deploy_raw.get("dry_run", False)),
                update_package_lists=bool(deploy_raw.get("update_package_lists", True)),
                check_status_after=bool(deploy_raw.get("check_status_after", True)),
            ),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []

        if not self.ssh.host.strip():
            errors.append("IP / Host пустой.")
        if not (1 <= self.ssh.port <= 65535):
            errors.append("Порт должен быть от 1 до 65535.")
        if not self.ssh.username.strip():
            errors.append("Логин пустой.")

        if self.ssh.ssh_key_path:
            key_path = Path(self.ssh.ssh_key_path).expanduser()
            if not key_path.exists():
                errors.append(f"SSH ключ не найден: {key_path}")

        if self.cloudflared.configure_token_service and not self.cloudflared.tunnel_token.strip():
            errors.append("Cloudflare tunnel token пустой.")

        if self.v2raya.core not in {"xray", "v2ray"}:
            errors.append("v2rayA core должен быть 'xray' или 'v2ray'.")

        if self.v2raya.prepare_vless_config and not self.v2raya.vless_uri.strip():
            errors.append("VLESS/Xray ссылка пустая.")

        return errors
