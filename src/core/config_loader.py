import json
from pathlib import Path


REQUIRED_KEYS = {"name", "host", "username", "password", "tunnel_token"}


def load_router_config(file_path: str) -> dict:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    if path.suffix.lower() != ".json":
        raise ValueError("Нужен JSON-файл")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Корень JSON должен быть объектом")

    missing = REQUIRED_KEYS - data.keys()
    if missing:
        raise ValueError(
            f"В конфиге не хватает полей: {', '.join(sorted(missing))}"
        )

    for key in REQUIRED_KEYS:
        if not isinstance(data[key], str):
            raise ValueError(f"Поле '{key}' должно быть строкой")

    return data