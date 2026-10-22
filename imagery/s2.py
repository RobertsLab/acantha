"""Sentinel-2 L2A: group tiles into scenes, read the AOI onto the grid, clear-sky stats, true color."""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

from grid import GRID

# Scene Classification Layer classes (ESA L2A).
SCL_CLEAR = (2, 4, 5, 6, 11)   # dark/shadowed land, vegetation, bare, water, snow
SCL_CLOUD = (3, 8, 9, 10)      # cloud shadow, medium/high cloud, thin cirrus
# 1 saturated/defective and 7 unclassified count as valid but not clear.

GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF,.tiff",
    "AWS_NO_SIGN_REQUEST": "YES",
    "GDAL_HTTP_MAX_RETRY": "4",
    "GDAL_HTTP_RETRY_DELAY": "3",
    "GDAL_HTTP_MULTIRANGE": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
}


def group_scenes(items: list) -> list[dict]:
    """One scene per platform per UTC date (the AOI spans tiles 10TET and 10UEU)."""
    groups = defaultdict(list)
    for it in items:
        dt = it.datetime
        groups[(it.properties.get("platform", "sentinel-2").lower(), dt.date())].append(it)
    scenes = []
    for (platform, day), its in groups.items():
        its.sort(key=lambda i: i.id)
        scenes.append({"id": f"s2{platform[-1]}_{day:%Y%m%d}", "platform": platform,
                       "date": day.isoformat(), "datetime": min(i.datetime for i in its),
                       "items": its})
    scenes.sort(key=lambda s: s["datetime"])
    return scenes


def _read(href: str, resampling=Resampling.nearest) -> np.ndarray:
    with rasterio.open(href) as src, WarpedVRT(
            src, crs=GRID.crs, transform=GRID.transform, width=GRID.width, height=GRID.height,
            resampling=resampling, src_nodata=0, nodata=0) as vrt:
        return vrt.read(1)


def _mosaic(items: list, asset: str) -> np.ndarray:
    out = None
    for it in items:
        if asset not in it.assets:
            continue
        a = _read(it.assets[asset].href)
        out = a if out is None else np.where(out == 0, a, out)
    if out is None:
        raise RuntimeError(f"no '{asset}' asset in scene")
    return out


def _reflectance(dn: np.ndarray) -> np.ndarray:
    """Surface reflectance from L2A DN (scale 1e-4).

    Since processing baseline 04.00, ESA adds +1000 to every DN, but some catalogs serve
    "harmonized" COGs with it already removed while their STAC metadata still says
    offset -0.1 (Earth Search, checked Oct 2026: median red DN ~90). So decide from the
    data: raw offset DNs never go much below 1000, harmonized ones do.
    """
    valid = dn[dn > 0]
    offset = 1000 if valid.size and np.percentile(valid, 1) >= 900 else 0
    return (dn.astype("float32") - offset) * 1e-4


def clear_stats(scl: np.ndarray, site: tuple[slice, slice]) -> dict:
    def pct(a):
        valid = a > 0
        n = int(valid.sum())
        if not n:
            return None, None, 0.0
        clear = np.isin(a, SCL_CLEAR).sum() / n * 100
        cloud = np.isin(a, SCL_CLOUD).sum() / n * 100
        return round(float(clear), 1), round(float(cloud), 1), round(n / a.size * 100, 1)

    clear, cloud, coverage = pct(scl)
    site_clear, _, site_cov = pct(scl[site])
    return {"clear_pct": clear, "cloud_pct": cloud, "coverage_pct": coverage,
            "site_clear_pct": site_clear, "site_coverage_pct": site_cov}


def read_scl(scene: dict, bands: dict) -> np.ndarray:
    with rasterio.Env(**GDAL_ENV):
        return _mosaic(scene["items"], bands["scl"])


def true_color(scene: dict, bands: dict) -> np.ndarray:
    """RGBA uint8 on the grid. Alpha is 0 where there's no data."""
    rgb, valid = [], None
    with rasterio.Env(**GDAL_ENV):
        for key in ("red", "green", "blue"):
            asset = bands[key]
            dn = _mosaic(scene["items"], asset)
            refl = _reflectance(dn)
            v = np.clip(refl / 0.25, 0, 1) ** 0.6   # brighten dark water and shoreline
            rgb.append((v * 255).astype("uint8"))
            valid = dn > 0 if valid is None else valid & (dn > 0)
    alpha = np.where(valid, 255, 0).astype("uint8")
    return np.dstack(rgb + [alpha])
