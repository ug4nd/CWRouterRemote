# CWRouterRemote Russian debug GUI patch v3

## Логика v2rayA

v2rayA устанавливается и подготавливается, но VPN НЕ включается.

Что делает программа:

- ставит `v2raya`;
- ставит `xray-core` или `v2ray-core`;
- ставит `luci-app-v2raya`, если пакет доступен;
- сохраняет VLESS/Xray ссылку из JSON в `/etc/v2raya/cwrouterremote_vless_uri.txt`;
- ставит права `0600`;
- делает `uci set v2raya.config.enabled='0'`;
- делает `/etc/init.d/v2raya stop`;
- делает `/etc/init.d/v2raya disable`.

То есть роутер подготовлен, но трафик через VPN не пойдёт.

## Временные кнопки

1. Проверить SSH
2. Определить OpenWrt
3. Установить cloudflared
4. Установить LuCI cloudflared
5. Настроить cloudflared
6. Проверить cloudflared
7. Установить v2rayA
8. Установить LuCI v2rayA
9. Подготовить VLESS для v2rayA
10. Проверить v2rayA

## Запуск

```bash
pip install -r requirements.txt
python src/main.py
```
