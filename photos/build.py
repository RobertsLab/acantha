"""Geotagged farm photos -> web-sized copies + web/photos/photos.geojson for the map.

Usage:
    pip install -r photos/requirements.txt
    python photos/build.py

Drop original photos (JPEG, HEIC or PNG, any subfolder) into photos/. Each one with a
GPS position gets a 1600 px copy and a 400 px thumbnail in web/photos/, saved without
any metadata, plus a point in photos.geojson. Photos without a position are listed and
skipped; give them one with a "lat, lon" in captions.txt (see photos/README.md).

Originals are git-ignored (full-size phone photos would bloat the repo); only the
web copies and photos.geojson are committed. Re-running is safe: unchanged photos are
skipped, and web copies whose original is gone are deleted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

try:  # iPhone photos are HEIC
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF = True
except ImportError:  # fall back to macOS's built-in sips, which keeps the EXIF
    HEIF = False

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "photos"
OUT = ROOT / "web/photos"
EXTS = {".jpg", ".jpeg", ".heic", ".heif", ".png"}
FULL_PX, THUMB_PX = 1600, 400
GPS_IFD, EXIF_IFD = 0x8825, 0x8769
DATETIME_ORIGINAL, IMAGE_DESCRIPTION = 0x9003, 0x010E


def read_captions(path: Path) -> dict[str, dict]:
    """captions.txt lines: `<file name>: <caption>`, optionally `@ <lat>, <lon>` at the end."""
    out = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        name, text = (s.strip() for s in line.split(":", 1))
        entry = {}
        m = re.search(r"@\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", text)
        if m:
            entry["lat"], entry["lon"] = float(m[1]), float(m[2])
            text = text[: m.start()].strip()
        if text:
            entry["caption"] = text
        out[name.lower()] = entry
    return out


def gps(exif) -> tuple[float, float] | None:
    g = exif.get_ifd(GPS_IFD)
    if not g or 2 not in g or 4 not in g:
        return None
    dms = lambda v: float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
    lat, lon = dms(g[2]), dms(g[4])
    if g.get(1) == "S":
        lat = -lat
    if g.get(3) == "W":
        lon = -lon
    return (lat, lon) if (lat or lon) else None


def taken(exif) -> str | None:
    s = exif.get_ifd(EXIF_IFD).get(DATETIME_ORIGINAL) or exif.get(0x0132)
    try:
        return datetime.strptime(s.strip("\x00 "), "%Y:%m:%d %H:%M:%S").isoformat()  # camera local time
    except (AttributeError, ValueError):
        return None


def open_image(path: Path, tmp: Path) -> Image.Image:
    if path.suffix.lower() in {".heic", ".heif"} and not HEIF:
        if not shutil.which("sips"):
            sys.exit(f"{path.name}: HEIC needs pillow-heif (pip install pillow-heif) or macOS sips")
        jpg = tmp / f"{path.stem}.jpg"
        subprocess.run(["sips", "-s", "format", "jpeg", str(path), "--out", str(jpg)], check=True, capture_output=True)
        path = jpg
    return Image.open(path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.parse_args()
    captions = read_captions(SRC / "captions.txt")
    (OUT / "thumbs").mkdir(parents=True, exist_ok=True)

    features, keep, missing = [], set(), []
    tmp = Path(tempfile.mkdtemp())
    for path in sorted(p for p in SRC.rglob("*") if p.suffix.lower() in EXTS):
        info = captions.get(path.name.lower(), {})
        with open_image(path, tmp) as im:
            exif = im.getexif()
            pos = gps(exif)
            if "lat" in info:
                pos = (info["lat"], info["lon"])
            if not pos:
                missing.append(path.relative_to(ROOT))
                continue
            when = taken(exif)
            # Name the copies by content, so re-runs skip unchanged photos and renames are harmless.
            digest = hashlib.sha1(path.read_bytes()).hexdigest()[:10]
            name = f"{(when or '')[:10].replace('-', '') or 'undated'}-{digest}.jpg"
            keep.add(name)
            if not (OUT / name).exists() or not (OUT / "thumbs" / name).exists():
                img = ImageOps.exif_transpose(im).convert("RGB")  # bake in rotation, then drop all metadata
                for px, dest in ((FULL_PX, OUT / name), (THUMB_PX, OUT / "thumbs" / name)):
                    copy = img.copy()
                    copy.thumbnail((px, px))
                    copy.save(dest, "JPEG", quality=82, optimize=True, progressive=True)
            caption = info.get("caption") or (exif.get(IMAGE_DESCRIPTION) or "").strip("\x00 ")
        features.append({"type": "Feature",
                         "geometry": {"type": "Point", "coordinates": [round(pos[1], 6), round(pos[0], 6)]},
                         "properties": {"src": f"photos/{name}", "thumb": f"photos/thumbs/{name}",
                                        "taken": when, "caption": caption or None}})

    shutil.rmtree(tmp)
    for old in [*OUT.glob("*.jpg"), *(OUT / "thumbs").glob("*.jpg")]:
        if old.name not in keep:
            old.unlink()
    features.sort(key=lambda f: f["properties"]["taken"] or "")
    (OUT / "photos.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=1) + "\n")

    print(f"{len(features)} photos on the map")
    if missing:
        print(f"{len(missing)} skipped, no GPS position (add '<file>: caption @ lat, lon' to photos/captions.txt):",
              *missing, sep="\n  ", file=sys.stderr)


if __name__ == "__main__":
    main()
