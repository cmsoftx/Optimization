"""Configuration loading and path resolution."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


@lru_cache(maxsize=1)
def load_config(path: str | Path = CONFIG_PATH) -> dict[str, Any]:
    """Load ``config.yaml`` once and cache it."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def get_path(key: str, create: bool = True) -> Path:
    """Return an absolute project path from the ``paths`` section."""
    cfg = load_config()
    try:
        rel = cfg["paths"][key]
    except KeyError as exc:
        raise KeyError(f"Unknown path key '{key}' in config.yaml") from exc
    p = PROJECT_ROOT / rel
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p
