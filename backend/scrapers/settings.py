"""User-defined scrape constraints (global, like the watchlists).

No hardcoded keyword restrictions: by default both lists are empty, which
means every scraped posting is ingested and marked relevant. The user can add
include/exclude keywords from the UI; they apply at scrape time and can be
re-applied retroactively to the existing pool.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR.mkdir(exist_ok=True)
PATH = DATA_DIR / "scrape_settings.json"

DEFAULTS = {"include_keywords": [], "exclude_keywords": []}


def load() -> dict:
    if PATH.exists():
        data = json.loads(PATH.read_text())
        return {k: list(data.get(k, [])) for k in DEFAULTS}
    return {k: list(v) for k, v in DEFAULTS.items()}


def save(include_keywords: list[str], exclude_keywords: list[str]) -> dict:
    cfg = {
        "include_keywords": sorted({k.strip().lower() for k in include_keywords if k.strip()}),
        "exclude_keywords": sorted({k.strip().lower() for k in exclude_keywords if k.strip()}),
    }
    PATH.write_text(json.dumps(cfg, indent=2))
    return cfg
