"""Monthly "normal" water conditions at the LiveOcean cells near Thorndyke Bay.

Usage:
    pip install -r baseline/requirements.txt
    python baseline/liveocean_climatology.py [--out web/baseline/liveocean_climatology.json]

Reads UW LiveOcean's monthly climatologies (run cas7_t0_x4b, each month averaged
over 2014-2024) from s3.kopah.uw.edu and writes surface and bottom temperature,
salinity and dissolved oxygen for each cell in ingest/config.py LIVEOCEAN_CELLS.
Each file is ~780 MB, but only the HDF5 chunks holding the cells are fetched over
HTTP range requests (a few MB per variable), so a full run takes a few minutes.

This is a one-off: the climatology doesn't change. Re-run only if the cells or the
source files change. Caveats (see docs/liveocean-plan.md):
  - monthly means smooth over multi-day events such as low-oxygen intrusions;
  - UW notes this run's bottom oxygen in the Salish Sea is sometimes biased low;
  - it is an older model version than the one making the daily forecasts.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import fsspec
import h5py

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))

from config import LIVEOCEAN_CELLS  # noqa: E402
from sources.common import distance_km, iso, utcnow  # noqa: E402

URL = "https://s3.kopah.uw.edu/cas7-t0-x4b/climatologies/monthly_clim_{:02d}.nc"
MODEL_RUN = "cas7_t0_x4b"
YEARS = "2014-2024"
FILL = 1e19                  # _FillValue is 1e20
O2_UM_TO_MGL = 32 / 1000     # mmol/m3 (uM) O2 -> mg/L
MAX_CELL_SHIFT_KM = 0.1


def _val(v) -> float | None:
    v = float(v)
    return None if v != v or abs(v) > FILL else v


def _r(v, nd=2):
    return None if v is None else round(v, nd)


def _layer(h: h5py.File, e: int, x: int, k: int) -> dict:
    temp, salt, o2 = (_val(h[name][0, k, e, x]) for name in ("temp", "salt", "oxygen"))
    return {"temp_c": _r(temp), "salt": _r(salt),
            "do_mgl": _r(None if o2 is None else o2 * O2_UM_TO_MGL), "do_um": _r(o2, 1)}


def read_month(month: int, cells: list[dict]) -> dict:
    with fsspec.open(URL.format(month), block_size=2**20).open() as f, h5py.File(f, "r") as h:
        top = h["s_rho"].shape[0] - 1  # s_rho[0] is the bottom layer, s_rho[-1] the surface
        out = {}
        for c in cells:
            e, x = c["eta"], c["xi"]
            lat, lon = float(h["lat_rho"][e, x]), float(h["lon_rho"][e, x])
            shift = distance_km(lat, lon, c["lat"], c["lon"])
            if shift > MAX_CELL_SHIFT_KM or float(h["mask_rho"][e, x]) < 0.5:  # stored as 1.0000000000000002
                raise RuntimeError(f"{c['id']}: cell [{e}][{x}] is {shift:.2f} km off or land in month {month}")
            out[c["id"]] = {"month": month,
                            "surface": _layer(h, e, x, top),
                            "bottom": {**_layer(h, e, x, 0),
                                       "depth_m": _r(-float(h["z_rho"][0, 0, e, x]), 1)},
                            "_meta": {"lat": lat, "lon": lon, "depth_m": float(h["h"][e, x])}}
        return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(ROOT / "web/baseline/liveocean_climatology.json"))
    args = ap.parse_args()

    cells = {c["id"]: {"id": c["id"], "name": c["name"], "months": []} for c in LIVEOCEAN_CELLS}
    for month in range(1, 13):
        print(f"month {month:02d} ...", flush=True)
        for cid, row in read_month(month, LIVEOCEAN_CELLS).items():
            meta = row.pop("_meta")
            cells[cid].update(lat=round(meta["lat"], 4), lon=round(meta["lon"], 4),
                              depth_m=round(meta["depth_m"], 1))
            cells[cid]["months"].append(row)

    out = {"source": "UW LiveOcean monthly climatology", "model_run": MODEL_RUN, "years": YEARS,
           "url": URL.format(1).replace("_01.nc", "_[01-12].nc"),
           "units": {"temp_c": "degC (potential)", "salt": "PSU", "do_mgl": "mg/L", "do_um": "uM"},
           "note": "Monthly means; bottom = deepest model layer. Bottom O2 may be biased low in the Salish Sea.",
           "generated_at": iso(utcnow()), "cells": list(cells.values())}
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
