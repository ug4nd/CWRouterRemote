from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse


@dataclass
class VlessConfig:
    uuid: str
    server: str
    port: int
    network: str = "tcp"
    security: str = "reality"
    public_key: str = ""
    fingerprint: str = "chrome"
    sni: str = ""
    short_id: str = ""
    spider_x: str = "/"
    flow: str = "xtls-rprx-vision"


def parse_vless_link(link: str) -> VlessConfig:
    link = link.strip()
    if not link.startswith("vless://"):
        raise ValueError("Ссылка должна начинаться с vless://")

    parsed = urlparse(link)
    query = parse_qs(parsed.query)

    def q(name: str, default: str = "") -> str:
        value = query.get(name, [default])[0]
        return unquote(value)

    uuid = parsed.username or ""
    server = parsed.hostname or ""
    port = parsed.port

    if not uuid or not server or not port:
        raise ValueError("Не удалось получить UUID, сервер или порт из VLESS-ссылки")

    return VlessConfig(
        uuid=uuid,
        server=server,
        port=int(port),
        network=q("type", "tcp"),
        security=q("security", "reality"),
        public_key=q("pbk", ""),
        fingerprint=q("fp", "chrome"),
        sni=q("sni", ""),
        short_id=q("sid", ""),
        spider_x=q("spx", "/"),
        flow=q("flow", "xtls-rprx-vision"),
    )


def build_xray_config(vless: VlessConfig, xray_port: int = 12345) -> str:
    user = {
        "id": vless.uuid,
        "encryption": "none",
    }
    if vless.flow:
        user["flow"] = vless.flow

    stream_settings = {
        "network": vless.network,
        "security": vless.security,
    }

    if vless.security == "reality":
        stream_settings["realitySettings"] = {
            "serverName": vless.sni,
            "fingerprint": vless.fingerprint,
            "publicKey": vless.public_key,
            "shortId": vless.short_id,
            "spiderX": vless.spider_x or "/",
        }
    elif vless.security == "tls":
        stream_settings["tlsSettings"] = {
            "serverName": vless.sni,
            "fingerprint": vless.fingerprint,
        }

    config = {
        "log": {"loglevel": "warning"},
        "dns": {"servers": ["8.8.8.8", "8.8.4.4", "9.9.9.9"]},
        "inbounds": [
            {
                "tag": "redirect-in",
                "port": int(xray_port),
                "protocol": "dokodemo-door",
                "settings": {"network": "tcp", "followRedirect": True},
            },
            {
                "tag": "socks-in",
                "port": 10808,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": {"udp": True},
            },
            {"tag": "http-in", "port": 10809, "listen": "127.0.0.1", "protocol": "http"},
        ],
        "outbounds": [
            {
                "tag": "proxy",
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": vless.server,
                            "port": int(vless.port),
                            "users": [user],
                        }
                    ]
                },
                "streamSettings": stream_settings,
            },
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
                {"type": "field", "network": "tcp,udp", "outboundTag": "proxy"},
            ],
        },
    }
    return json.dumps(config, indent=2, ensure_ascii=False)
