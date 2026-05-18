# UGRemoteTools

UGRemoteTools — Windows GUI для подготовки OpenWrt-роутеров под удалённый доступ Tailscale, переход с v2rayA на чистый xray-core/VLESS, DNS/Force-DNS и KillSwitch.

## Запуск

```bat
run.bat
```

или вручную:

```powershell
pip install -r requirements.txt
python src/main.py
```

## Сборка EXE

```bat
build_exe.bat
```

Готовый файл появится в:

```text
dist\UGRemoteTools.exe
```

## Структура окон

### 1. Удалённый доступ Tailscale

В этом окне все действия относятся только к Tailscale:

- установить Tailscale, если его нет;
- подключить роутер к сети по auth key;
- применить `--shields-up=false --accept-dns=false`;
- создать/починить firewall-зону `tailscale` для доступа к LuCI/SSH по `100.x.x.x`;
- настроить cron: health-check каждые 5 минут и ежедневный restart в 12:00;
- настроить rc.local wake-ping после холодного старта: скрипт ждёт delay и пингует указанный peer IP, чтобы Tailscale соединение просыпалось.

### 2. Установка и настройка Xray

В этом окне находятся действия для миграции:

- удалить v2rayA и luci-app-v2raya;
- установить/проверить xray-core;
- сменить VLESS-ключ;
- настроить REDIRECT TCP на порт xray;
- включить полную блокировку прямого UDP LAN→WAN.

### 3. Настройка DNS для Vless

В этом окне программа:

- отключает DNS провайдера через `peerdns=0`;
- ставит DNS `8.8.8.8`, `8.8.4.4`, `9.9.9.9`;
- включает Force-LAN-DNS, чтобы клиенты LAN не ходили на DNS `:53` мимо роутера.

## Автоматическое выполнение через JSON

В главном окне блок “Основные функции” открывает отдельные окна, а блок “Настройка VLESS и DNS” содержит общие параметры. Логи выполнения открываются в отдельном окне. Можно выбрать JSON config и нажать `Выполнить JSON`. Пример лежит в `router_config.example.json`.

### Минимальный пример

```json
{
  "router": {
    "host": "192.168.7.1",
    "port": 22,
    "username": "root",
    "password": "password_here",
    "lan_ip": "192.168.7.1"
  },
  "backup": true,
  "tailscale": {
    "enabled": true,
    "auth_key": "tskey-auth-...",
    "wake_peer_ip": "100.77.73.23",
    "wake_delay": 90,
    "install_connect": true,
    "configure_zone": true,
    "configure_cron": true
  },
  "xray": {
    "enabled": true,
    "remove_v2raya": true,
    "install_xray_core": true,
    "update_vless": true,
    "vless_link": "vless://UUID@SERVER:PORT?type=tcp&encryption=none&security=reality&pbk=PUBLIC_KEY&fp=chrome&sni=DOMAIN&sid=SHORT_ID&spx=%2F&flow=xtls-rprx-vision#name",
    "xray_port": 12345,
    "configure_redirect": true,
    "block_udp": true,
    "vless_server_ip": "SERVER_IP"
  },
  "dns": {
    "enabled": true,
    "configure": true,
    "dns1": "8.8.8.8",
    "dns2": "8.8.4.4",
    "dns3": "9.9.9.9"
  }
}
```

## Поддержка OpenWrt apk/opkg

Команды установки автоматически определяют пакетный менеджер:

- `apk` для новых сборок OpenWrt;
- `opkg` для классических сборок.

Cloudflare/cloudflared в проекте не используется. Настройки SNI/маскировки не добавлялись.


## JSON preview / выбор действий

При выборе JSON-файла программа теперь открывает отдельное окно автоматического выполнения.
Слева показывается весь JSON config, справа — галочки по функциям из разделов:

- Удалённый доступ Tailscale
- Установка и настройка Xray
- Настройка DNS для Vless

Можно выбрать только нужные действия и нажать «Выполнить отмеченное».
