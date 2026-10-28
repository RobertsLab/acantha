"""Tide-height contour lines (feet above MLLW) for the beach and flats around the farm.

Usage:
    pip install -r baseline/requirements.txt
    python baseline/tide_contours.py [--out web/baseline/tide_contours.geojson]

Reads NOAA NCEI's 1/9 arc-second (~3 m) Continuously Updated DEM for Puget Sound
(tile ncei19_n48x00_w122x75, 2023v1; elevations in meters above NAVD88). The tile is
~200 MB, but it is a tiled GeoTIFF, so only the blocks around the bay are fetched over
HTTP range requests.

NAVD88 is shifted to MLLW with the datums at NOAA's Whitney Point station (9445246),
the nearest Hood Canal station tied to NAVD88: MLLW is 0.814 m below NAVD88. Lofall,
the station the tide predictions use, has no NAVD88 tie. Expect the lines to be good
to a few tenths of a foot, and the DEM itself to lag changes to the beach.

This is a one-off: re-run only if the area, levels or source DEM change.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from scipy.ndimage import gaussian_filter
from skimage.measure import approximate_polygon, find_contours

ROOT = Path(__file__).resolve().parent.parent
DEM_URL = ("https://chs.coast.noaa.gov/htdata/raster2/elevation/NCEI_ninth_Topobathy_2014_8483/"
           "wash_pugetsound/ncei19_n48x00_w122x75_2023v1.tif")
BOUNDS = (-122.748, 47.800, -122.725, 47.815)  # lon/lat box around Thorndyke Bay's flats
NAVD88_ABOVE_MLLW_M = 1.407 - 0.593              # Whitney Point 9445246 datums
LEVELS_FT = list(range(-6, 13, 2))               # every 2 ft from -6 to +12 ft MLLW
SOURCE = "NOAA NCEI CUDEM 1/9 arc-second (Puget Sound, 2023v1); NAVD88 to MLLW via NOAA 9445246 Whitney Point"


def contours(dem_ft: np.ndarray, transform) -> list[dict]:
    feats = []
    for level in LEVELS_FT:
        for path in find_contours(dem_ft, level):
            if len(path) < 8:  # specks: single pools and bumps
                continue
            path = approximate_polygon(path, tolerance=0.5)  # half a cell
            # find_contours gives (row, col) at cell centers.
            coords = [[round(c, 6) for c in transform * (col + 0.5, row + 0.5)] for row, col in path]
            feats.append({"type": "Feature", "properties": {"ft": level},
                          "geometry": {"type": "LineString", "coordinates": coords}})
    return feats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "web/baseline/tide_contours.geojson"))
    args = ap.parse_args()

    with rasterio.open(f"/vsicurl/{DEM_URL}") as src:
        win = from_bounds(*BOUNDS, src.transform)
        z = src.read(1, window=win, masked=True).astype("float64")
        transform = src.window_transform(win)
    ft = (z.filled(np.nan) + NAVD88_ABOVE_MLLW_M) / 0.3048
    # A light blur keeps the 3 m grid from making the lines jagged.
    ft = gaussian_filter(np.nan_to_num(ft, nan=-100), sigma=1)

    out = {"type": "FeatureCollection", "source": SOURCE, "datum": "MLLW", "units": "ft",
           "features": contours(ft, transform)}
    Path(args.out).write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(f"wrote {len(out['features'])} lines to {args.out}")


if __name__ == "__main__":
    main()
