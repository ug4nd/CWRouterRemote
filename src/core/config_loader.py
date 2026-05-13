from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.models import RouterConfig


def load_json(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_router_config(path: str | Path) -> RouterConfig:
    return RouterConfig.from_dict(load_json(path))


def router_config_to_dict(config: RouterConfig) -> dict[str, Any]:
    # В JSON специально нет имени файла / hostname-профиля.
    return {
        "ssh": {
            "host": config.ssh.host,
            "port": config.ssh.port,
            "username": config.ssh.username,
            "password": config.ssh.password,
            "ssh_key_path": config.ssh.ssh_key_path,
            "connect_timeout": config.ssh.connect_timeout,
            "command_timeout": config.ssh.command_timeout,
        },
        "cloudflared": {
            "enabled": config.cloudflared.enabled,
            "install_package": config.cloudflared.install_package,
            "install_luci": config.cloudflared.install_luci,
            "configure_token_service": config.cloudflared.configure_token_service,
            "tunnel_token": config.cloudflared.tunnel_token,
            "token_path": config.cloudflared.token_path,
            "init_script_path": config.cloudflared.init_script_path,
        },
        "v2raya": {
            "enabled": config.v2raya.enabled,
            "install_package": config.v2raya.install_package,
            "install_luci": config.v2raya.install_luci,
            "core": config.v2raya.core,
            "enable_service": config.v2raya.enable_service,
            "vless_uri": config.v2raya.vless_uri,
            "prepare_vless_config": config.v2raya.prepare_vless_config,
            "prepared_config_path": config.v2raya.prepared_config_path,
        },
        "deploy": {
            "dry_run": config.deploy.dry_run,
            "update_package_lists": config.deploy.update_package_lists,
            "check_status_after": config.deploy.check_status_after,
        },
    }


def save_router_config(path: str | Path, config: RouterConfig) -> None:
    config_path = Path(path).expanduser().resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with config_path.open("w", encoding="utf-8") as file:
        json.dump(router_config_to_dict(config), file, ensure_ascii=False, indent=2)
        file.write("\n")
