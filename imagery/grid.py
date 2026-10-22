"""The shared imagery grid: UTM 10N at 10 m over the portal's BBOX.

Every sensor and model output is resampled onto this grid, so a pixel (row, col)
is the same place in every layer. The edges are snapped to 60 m, which lines up
with Sentinel-2's 10, 20 and 60 m pixel edges, so S2 reads need no resampling.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from rasterio.crs import CRS
from rasterio.transform import Affine
from rasterio.warp import transform_bounds

from settings import BBOX, SITE

CRS_UTM = CRS.from_epsg(32610)
RES = 10
SNAP = 60


@dataclass(frozen=True)
class Grid:
    crs: CRS
    transform: Affine
    width: int
    height: int

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        x0, y1 = self.transform.c, self.transform.f
        return x0, y1 - self.height * RES, x0 + self.width * RES, y1

    def describe(self) -> dict:
        return {"crs": self.crs.to_string(), "res_m": RES, "width": self.width,
                "height": self.height, "bounds": [round(v) for v in self.bounds]}


def make_grid() -> Grid:
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", CRS_UTM, BBOX["xmin"], BBOX["ymin"],
                                      BBOX["xmax"], BBOX["ymax"])
    x0, y0 = math.floor(x0 / SNAP) * SNAP, math.floor(y0 / SNAP) * SNAP
    x1, y1 = math.ceil(x1 / SNAP) * SNAP, math.ceil(y1 / SNAP) * SNAP
    return Grid(CRS_UTM, Affine(RES, 0, x0, 0, -RES, y1), int((x1 - x0) / RES), int((y1 - y0) / RES))


GRID = make_grid()


def site_window(radius_m: float = 1500):
    """(row slice, col slice) of a square around the site, for bay-local stats."""
    from rasterio.warp import transform

    xs, ys = transform("EPSG:4326", CRS_UTM, [SITE["lon"]], [SITE["lat"]])
    col = int((xs[0] - GRID.transform.c) / RES)
    row = int((GRID.transform.f - ys[0]) / RES)
    r = int(radius_m / RES)
    return slice(max(row - r, 0), row + r), slice(max(col - r, 0), col + r)
