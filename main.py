import requests
from pathlib import Path
import json
from datetime import datetime
import time

TOKEN = "345c75ba-26c0-4f3e-acd4-09e63982ca52"
BASE_URL = "https://games-test.datsteam.dev/api/"
ARENA = BASE_URL + "arena"
BOOSTER = BASE_URL + "booster"
LOGS = BASE_URL + "logs"
MOVE = BASE_URL + "move"
ROUNDS = BASE_URL + "rounds"
out_dir =  Path("out")

HEADERS = {
    "accept": "application/json",
    "X-Auth-Token" : TOKEN
}


def save_response_json(
    response,
    *,
    filename: str | None = None,
    prefix: str = "response",
    out_dir: str | Path = ".",
    add_timestamp: bool = True,
    indent: int = 2,
) -> Path:
    """
    Сохраняет response.json() в файл.
    Возвращает путь к сохранённому файлу.
    """
    data = response.json()

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S") if add_timestamp else ""
        filename = f"{prefix}{'_' + ts if ts else ''}.json"

    path = out_dir / filename

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)

    return path


out_dir.mkdir(parents=True, exist_ok=True)


response = requests.get(ROUNDS, headers=HEADERS)
print(response.text)

# while True:
#     response = requests.get(ARENA, headers=HEADERS)
#     path = save_response_json(response, prefix="arena", out_dir="round5")
#     print("Saved to:", path)
#     time.sleep(1.0)