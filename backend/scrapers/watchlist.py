"""Global watchlists (NOT per-profile): one JSON file per source, stored in
data/ at the project root, editable from the UI or by hand."""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR.mkdir(exist_ok=True)

DEFAULTS = {
    "join": ["pactos", "cocrafter", "gotfunded", "firstmomentum12"],
    "personio": ["adverity", "clark", "everphone", "personio", "pitch"],
}


def _path(source: str) -> Path:
    if source not in DEFAULTS:
        raise ValueError(f"unknown watchlist source: {source}")
    return DATA_DIR / f"watchlist_{source}.json"


def load(source: str) -> list[str]:
    p = _path(source)
    if p.exists():
        return json.loads(p.read_text())
    save(source, DEFAULTS[source])
    return list(DEFAULTS[source])


def save(source: str, slugs: list[str]):
    _path(source).write_text(json.dumps(sorted(set(slugs)), indent=2))


def add(source: str, slug: str) -> list[str]:
    slugs = load(source)
    slugs.append(slug.strip().lower())
    save(source, slugs)
    return load(source)


def remove(source: str, slug: str) -> list[str]:
    slugs = [s for s in load(source) if s != slug]
    save(source, slugs)
    return slugs
