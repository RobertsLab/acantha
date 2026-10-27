"""Satellite imagery for the Thorndyke Bay portal (true-color map layer and dashboard card).

Usage:
    pip install -r imagery/requirements.txt
    python imagery/run.py [--out web/data/imagery] [--days 30]

Each run searches the last --days of Sentinel-2 L2A over the AOI, skips scenes
already in imagery.json, and for each new scene:
  - reads the Scene Classification Layer onto the shared grid (grid.py),
  - computes clear-sky % over the AOI and around the site,
  - renders a true-color WebP in Web Mercator for the map (if clear enough),
  - tags the capture time with the predicted Lofall tide height.
Products older than RETAIN_DAYS are pruned. Output:
    <out>/imagery.json
    <out>/products/<date>_<sensor>_truecolor.webp
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from rasterio.enums import Resampling  # noqa: E402
from rasterio.transform import array_bounds  # noqa: E402
from rasterio.warp import calculate_default_transform, reproject, transform_bounds  # noqa: E402

import s2  # noqa: E402
from grid import GRID, site_window  # noqa: E402
from settings import (  # noqa: E402
    LATEST_CLEAR_SITE_PCT, LOOKBACK_DAYS, MIN_CLEAR_PCT, RETAIN_DAYS, SITE_RADIUS_M, TIDE_STATION,
)
from stac import search_s2  # noqa: E402
from sources.common import iso, utcnow  # noqa: E402  (ingest/)
from sources.sensors import _tide_at  # noqa: E402
from sources.tides import _hilo  # noqa: E402

WEB_CRS = "EPSG:3857"
WEBP_QUALITY = 80


def to_web(rgba: np.ndarray) -> tuple[np.ndarray, list[list[float]]]:
    """Reproject an RGBA grid array to Web Mercator. Returns (array, MapLibre image corners)."""
    transform, w, h = calculate_default_transform(GRID.crs, WEB_CRS, GRID.width, GRID.height,
                                                  *GRID.bounds)
    out = np.zeros((h, w, 4), dtype="uint8")
    for b in range(4):
        reproject(rgba[..., b], out[..., b], src_transform=GRID.transform, src_crs=GRID.crs,
                  dst_transform=transform, dst_crs=WEB_CRS, resampling=Resampling.nearest)
    w_, s_, e_, n_ = transform_bounds(WEB_CRS, "EPSG:4326", *array_bounds(h, w, transform))
    corners = [[round(w_, 6), round(n_, 6)], [round(e_, 6), round(n_, 6)],
               [round(e_, 6), round(s_, 6)], [round(w_, 6), round(s_, 6)]]
    return out, corners


class Tides:
    """Predicted tide (ft MLLW) at a time, from NOAA high/low predictions, cached per day."""

    def __init__(self):
        self.cache: dict[str, list] = {}

    def at(self, t: datetime) -> float | None:
        key = t.strftime("%Y%m%d")
        if key not in self.cache:
            begin = (t - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            try:
                self.cache[key] = _hilo(begin, 72)
            except Exception as e:
                print(f"  tide lookup failed: {e}")
                self.cache[key] = []
        v = _tide_at(self.cache[key], t)
        return None if v is None else round(v, 2)


def process(scene: dict, cat: dict, out: Path, tides: Tides, site) -> dict:
    bands = cat["bands"]
    scl = s2.read_scl(scene, bands)
    rec = {"id": scene["id"], "sensor": "sentinel-2", "platform": scene["platform"],
           "date": scene["date"], "datetime": iso(scene["datetime"]), "catalog": cat["name"],
           "items": [i.id for i in scene["items"]], **s2.clear_stats(scl, site),
           "tide_ft": tides.at(scene["datetime"]), "products": {}}
    if (rec["clear_pct"] or 0) >= MIN_CLEAR_PCT:
        web, corners = to_web(s2.true_color(scene, bands))
        name = f"products/{scene['date'].replace('-', '')}_{scene['id'].split('_')[0]}_truecolor.webp"
        Image.fromarray(web, "RGBA").save(out / name, "WEBP", quality=WEBP_QUALITY, method=6)
        rec["products"]["truecolor"] = {"path": name, "corners": corners}
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "web" / "data" / "imagery"))
    ap.add_argument("--days", type=int, default=LOOKBACK_DAYS)
    args = ap.parse_args()

    out = Path(args.out)
    (out / "products").mkdir(parents=True, exist_ok=True)
    index_path = out / "imagery.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    scenes = {s["id"]: s for s in index.get("scenes", [])}

    now = utcnow()
    cat, items = search_s2(now - timedelta(days=args.days), now)
    print(f"{cat['name']}: {len(items)} S2 items in the last {args.days} days")
    tides, site, errors = Tides(), site_window(SITE_RADIUS_M), []
    for scene in s2.group_scenes(items):
        known = scenes.get(scene["id"])
        if known and len(known["items"]) >= len(scene["items"]):
            continue
        try:
            rec = process(scene, cat, out, tides, site)
            scenes[scene["id"]] = rec
            print(f"[ok]   {scene['id']} clear {rec['clear_pct']}% (site {rec['site_clear_pct']}%) "
                  f"tide {rec['tide_ft']} ft {'truecolor' if rec['products'] else '(too cloudy)'}")
        except Exception as e:
            traceback.print_exc()
            errors.append(f"{scene['id']}: {type(e).__name__}: {e}")
            print(f"[FAIL] {scene['id']} {e}")

    # Prune old scenes and any product file no scene refers to.
    cutoff = (now - timedelta(days=RETAIN_DAYS)).date().isoformat()
    scenes = {k: v for k, v in scenes.items() if v["date"] >= cutoff}
    keep = {p["path"] for s in scenes.values() for p in s["products"].values()}
    for f in (out / "products").iterdir():
        if f"products/{f.name}" not in keep:
            f.unlink()

    ordered = sorted(scenes.values(), key=lambda s: s["datetime"], reverse=True)
    latest_clear = next((s["id"] for s in ordered if s["products"].get("truecolor")
                         and (s["site_clear_pct"] or 0) >= LATEST_CLEAR_SITE_PCT
                         and s["site_coverage_pct"] >= 99), None)
    index = {"generated_at": iso(now), "grid": GRID.describe(),
             "site_radius_m": SITE_RADIUS_M, "tide_station": TIDE_STATION, "tide_datum": "MLLW",
             "latest_clear": latest_clear, "scenes": ordered, "errors": errors,
             "attribution": "Contains modified Copernicus Sentinel data " + str(now.year)}
    index_path.write_text(json.dumps(index, indent=1))
    print(f"{len(ordered)} scenes kept, latest clear: {latest_clear}, {len(errors)} errors")
    return 1 if errors and not ordered else 0


if __name__ == "__main__":
    sys.exit(main())
