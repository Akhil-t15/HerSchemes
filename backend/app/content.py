import json
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"

QUERY_REQUIRED = ["id", "text_en", "text_te", "answers"]


def _load(path, required):
    with open(path, encoding="utf-8") as f:
        items = json.load(f)
    result = []
    for index, item in enumerate(items):
        for key in required:
            if key not in item:
                raise ValueError(f"Item {index} in {path.name} is missing key '{key}'")
        result.append({key: item[key] for key in required})
    return result


def load_quick_queries(path=None):
    return _load(Path(path) if path else SEED_DIR / "quick_queries.json", QUERY_REQUIRED)
