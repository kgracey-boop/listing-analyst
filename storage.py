"""
Local file-based storage: one profile (static facts) and one history
(time-series activity snapshots) per property, keyed by a slug of the address.
"""
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent
PROPERTIES_DIR = BASE_DIR / "properties"
HISTORY_DIR = BASE_DIR / "history"
PROPERTIES_DIR.mkdir(exist_ok=True)
HISTORY_DIR.mkdir(exist_ok=True)


def slugify(address: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (address or "").lower()).strip("-") or "unknown-property"


def list_properties():
    """Return [(slug, profile_dict), ...] for every known property, newest first."""
    paths = sorted(PROPERTIES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [(p.stem, json.loads(p.read_text())) for p in paths]


def load_profile(slug: str):
    path = PROPERTIES_DIR / f"{slug}.json"
    return json.loads(path.read_text()) if path.exists() else None


def save_profile(slug: str, profile: dict):
    (PROPERTIES_DIR / f"{slug}.json").write_text(json.dumps(profile, indent=2))


def load_history(slug: str):
    path = HISTORY_DIR / f"{slug}.json"
    return json.loads(path.read_text()) if path.exists() else []


def save_snapshot(slug: str, snapshot: dict):
    entries = load_history(slug)
    entries.append(snapshot)
    (HISTORY_DIR / f"{slug}.json").write_text(json.dumps(entries, indent=2))


def delete_property(slug: str):
    for directory in (PROPERTIES_DIR, HISTORY_DIR):
        path = directory / f"{slug}.json"
        if path.exists():
            path.unlink()
