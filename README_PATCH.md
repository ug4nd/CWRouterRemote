# CFRRemote compact GUI

## Что изменено

- Убраны тестовые кнопки слева.
- GUI стал компактнее.
- Добавлены поля Cloudflare token и VLESS/Xray ссылка.
- Имя сверху используется только для имени файла, в JSON оно не сохраняется.
- Пример: `Router1` -> `router1_config.json`.
- Пути token/VLESS в GUI не показываются, они остаются в JSON:
  - `/etc/cloudflared/token`
  - `/etc/init.d/cloudflared`
  - `/etc/v2raya/cfrremote_vless_uri.txt`
- v2rayA подготавливается, но VPN не включается:
  - `enable_service: false`
  - service stop/disable.

## Запуск

```bash
pip install -r requirements.txt
python src/main.py
```


## v2 UI update

- Зелёный цвет оставлен как акцент вокруг блоков и кнопок.
- Внутри окон поля сделаны светлее.
- Галочки сделаны крупнее и нагляднее.
- Действия разделены на группы: Общее, Cloudflared, v2rayA.
