"""NOAA CO-OPS tide predictions.

Lofall is a subordinate station, so NOAA publishes only high/low times and
heights. The continuous curve is interpolated between extremes with a cosine,
which is the standard way to approximate the tide between a high and a low.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from config import TIDE_DAYS, TIDE_STATION
from sources.common import get_json, iso, utcnow

API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"


def _hilo(begin: datetime, hours: int) -> list[dict]:
    url = (
        f"{API}?station={TIDE_STATION['id']}&product=predictions&datum=MLLW"
        f"&units=english&time_zone=gmt&format=json&interval=hilo"
        f"&begin_date={begin:%Y%m%d}&range={hours}&application=acantha"
    )
    data = get_json(url)
    if "error" in data:
        raise RuntimeError(data["error"].get("message", "NOAA error"))
    out = []
    for p in data["predictions"]:
        t = datetime.strptime(p["t"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        out.append({"t": iso(t), "v": round(float(p["v"]), 2), "type": p["type"]})
    return out


def _curve(hilo: list[dict], start: datetime, end: datetime, step_min: int = 10) -> list[list]:
    pts = [(datetime.fromisoformat(h["t"].replace("Z", "+00:00")), h["v"]) for h in hilo]
    out = []
    t = start
    i = 0
    while t <= end:
        while i < len(pts) - 2 and pts[i + 1][0] <= t:
            i += 1
        (t1, h1), (t2, h2) = pts[i], pts[i + 1]
        if t1 <= t <= t2:
            frac = (t - t1).total_seconds() / (t2 - t1).total_seconds()
            v = h1 + (h2 - h1) * (1 - math.cos(math.pi * frac)) / 2
            out.append([iso(t), round(v, 2)])
        t += timedelta(minutes=step_min)
    return out


def fetch() -> dict:
    now = utcnow()
    begin = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    hilo = _hilo(begin, 24 * (TIDE_DAYS + 1))
    curve_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=12)
    curve = _curve(hilo, curve_start, curve_start + timedelta(days=4))
    return {
        "station": TIDE_STATION,
        "datum": "MLLW",
        "units": "ft",
        "source": "NOAA CO-OPS tide predictions",
        "source_url": f"https://tidesandcurrents.noaa.gov/noaatidepredictions.html?id={TIDE_STATION['id']}",
        "hilo": hilo,
        "curve": curve,
        "curve_note": "Cosine interpolation between NOAA high/low predictions",
    }
