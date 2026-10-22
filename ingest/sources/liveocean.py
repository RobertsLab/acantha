"""UW LiveOcean model: surface water temperature, salinity, and free surface.

LiveOcean (UW, MacCready group) is a ROMS model of the Salish Sea and coast,
run daily with a ~2-3 day forecast. NANOOS publishes a surface-only extract
over THREDDS/OPeNDAP; the "best time series" aggregation is a rolling ~30-day
hourly window. Only the model cells near the site are read, as OPeNDAP ASCII,
so no NetCDF library is needed.

The public extract has no oxygen, pH, or currents (see docs/liveocean-plan.md).

The model updates once a day but the workflow runs every ~20 minutes, so the
latest run time is checked first and the previous output is reused when it
hasn't changed.

Each series row has `kind`: "forecast" for times after the latest run's start,
otherwise "nowcast". The latest run's first hours lie in the past, so the page
should compare `t` with the current time to tell past from future.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from config import LIVEOCEAN_CELLS, LIVEOCEAN_HINDCAST_DAYS, LIVEOCEAN_URLS, SITE
from sources.common import c_to_f, distance_km, get_text, iso

FILL = 1e19            # ROMS _FillValue is 1e20
MAX_CELL_SHIFT_KM = 0.1

_DDS_TIME = re.compile(r"\btime\[time = (\d+)\]")
_HEADER = re.compile(r"^(\w+)\[[\d\]\[]+$")
_INDEX = re.compile(r"^(?:\[\d+\])+,\s*")


def parse_ascii(text: str) -> dict[str, list[float | None]]:
    """Parse a DAP2 .ascii response into {variable: flat list of values}.

    The server returns variables in its own order, not the request's, so they're
    keyed by name. Fill values and NaN become None.
    """
    body = text.split("-" * 45, 1)[1]
    out: dict[str, list[float | None]] = {}
    name = None
    for line in body.splitlines():
        line = line.strip()
        if not line:
            name = None
            continue
        m = _HEADER.match(line)
        if m and name is None:
            name = m.group(1)
            out[name] = []
            continue
        if name is None:
            continue
        for tok in _INDEX.sub("", line).split(","):
            tok = tok.strip()
            if not tok:
                continue
            v = float(tok)
            out[name].append(None if v != v or abs(v) > FILL else v)
    return out


def _time_base(das: str, var: str) -> datetime:
    m = re.search(rf"\n\s*{var} \{{[^}}]*?units \"hours since ([\d-]+)[ T]([\d:]+)", das)
    if not m:
        raise RuntimeError(f"no 'hours since' units for {var} in DAS")
    return datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}").replace(tzinfo=timezone.utc)


def _ascii(base: str, constraint: str) -> dict:
    return parse_ascii(get_text(f"{base}.ascii?{constraint}"))


def _cell(base: str, cell: dict, i0: int, i1: int, times: list[datetime | None], run: datetime) -> dict:
    e, x, sl = cell["eta"], cell["xi"], f"[{i0}:1:{i1}]"
    d = _ascii(base, f"temp{sl}[{e}][{x}],salt{sl}[{e}][{x}],zeta{sl}[{e}][{x}],"
                     f"lat_rho[{e}][{x}],lon_rho[{e}][{x}],mask_rho[{e}][{x}],h[{e}][{x}]")
    lat, lon = d["lat_rho"][0], d["lon_rho"][0]
    shift = distance_km(lat, lon, cell["lat"], cell["lon"])
    if shift > MAX_CELL_SHIFT_KM or d["mask_rho"][0] != 1:
        raise RuntimeError(f"{cell['id']}: model cell [{e}][{x}] moved {shift:.2f} km or is land; "
                           "the grid may have changed, recompute LIVEOCEAN_CELLS")
    series = []
    for t, temp, salt, zeta in zip(times, d["temp"], d["salt"], d["zeta"]):
        if t is None or (temp is None and salt is None and zeta is None):
            continue
        series.append({"t": iso(t), "temp_c": None if temp is None else round(temp, 2),
                       "temp_f": c_to_f(temp), "salt": None if salt is None else round(salt, 2),
                       "zeta_m": None if zeta is None else round(zeta, 3),
                       "kind": "forecast" if t > run else "nowcast"})
    if not series:
        raise RuntimeError(f"{cell['id']}: no valid model values")
    return {"id": cell["id"], "name": cell["name"], "lat": round(lat, 4), "lon": round(lon, 4),
            "depth_m": round(d["h"][0], 1),
            "distance_km": round(distance_km(SITE["lat"], SITE["lon"], lat, lon), 1),
            "series": series}


def _fetch_from(base: str, previous: dict | None) -> dict:
    m = _DDS_TIME.search(get_text(f"{base}.dds"))
    if not m:
        raise RuntimeError("no time dimension in DDS")
    n = int(m.group(1))
    das = get_text(f"{base}.das")
    t0, r0 = _time_base(das, "time"), _time_base(das, "time_run")

    run = r0 + timedelta(hours=_ascii(base, f"time_run[{n - 1}]")["time_run"][0])
    cell_ids = [c["id"] for c in LIVEOCEAN_CELLS]
    if (previous and previous.get("run") == iso(run) and previous.get("server") == base
            and [c["id"] for c in previous.get("cells", [])] == cell_ids):
        previous = {k: v for k, v in previous.items() if k != "fetched_at"}
        previous["reused"] = True
        return previous

    hours = _ascii(base, f"time[0:1:{n - 1}]")["time"]
    start = run - timedelta(days=LIVEOCEAN_HINDCAST_DAYS)
    i0 = next(i for i, h in enumerate(hours) if h is not None and t0 + timedelta(hours=h) >= start)
    # Keep a None slot for a missing time so indices stay aligned with the value arrays.
    times = [None if h is None else t0 + timedelta(hours=h) for h in hours[i0:]]
    cells = [_cell(base, c, i0, n - 1, times, run) for c in LIVEOCEAN_CELLS]
    return {"source": "UW LiveOcean via NANOOS/IOOS THREDDS", "server": base,
            "run": iso(run), "level": "surface", "hidden": True,
            "forecast_end": iso(max(t for t in times if t)), "cells": cells, "reused": False}


def fetch(ctx=None) -> dict:
    previous = ctx.previous("liveocean") if ctx else None
    errors = []
    for base in LIVEOCEAN_URLS:
        try:
            return _fetch_from(base, previous)
        except Exception as e:
            errors.append(f"{base}: {type(e).__name__}: {e}")
    raise RuntimeError("; ".join(errors))
