"""STAC search with catalog fallback and retries."""
from __future__ import annotations

import time
from datetime import datetime

import planetary_computer
from pystac_client import Client

from settings import BBOX, CATALOGS

RETRIES = 3


def _search(cat: dict, collection: str, start: datetime, end: datetime) -> list:
    client = Client.open(cat["url"], timeout=60)
    bbox = [BBOX["xmin"], BBOX["ymin"], BBOX["xmax"], BBOX["ymax"]]
    items = list(client.search(collections=[collection], bbox=bbox,
                               datetime=[start, end], max_items=500).items())
    if cat["name"] == "planetary-computer":
        items = [planetary_computer.sign(i) for i in items]
    return items


def search_s2(start: datetime, end: datetime) -> tuple[dict, list]:
    """Return (catalog, items) from the first catalog that answers."""
    errors = []
    for cat in CATALOGS:
        for attempt in range(RETRIES):
            try:
                return cat, _search(cat, cat["s2"], start, end)
            except Exception as e:
                errors.append(f"{cat['name']} try {attempt + 1}: {type(e).__name__}: {e}")
                time.sleep(5 * (attempt + 1))
    raise RuntimeError("all STAC catalogs failed: " + " | ".join(errors))
