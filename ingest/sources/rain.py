"""Observed rainfall at the site, for the rain closure watch.

None of the NWS/MADIS stations near the bay report hourly rain, so rain comes
from two other free, keyless feeds, both served by the Iowa Environmental
Mesonet (IEM):

- NCEP Stage IV hourly precipitation analysis (radar + gauges, ~4 km grid)
  at the site's own coordinates. Arrives about 2 h behind real time. In the
  Northwest the River Forecast Center analysis is 6-hourly, so hourly values
  are that total spread across its hours: 24/48/72 h sums are sound, but
  single-hour timing is approximate.
- CoCoRaHS volunteer gauges near the bay. One reading per day, taken around
  7 am local and covering the previous 24 h. Reports are often missing.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import (
    RAIN_GAUGE_DAYS, RAIN_GAUGE_MAX_KM, RAIN_GAUGE_MAX_N, RAIN_HOURS, SITE,
)
from sources.common import distance_km, get_json, iso, parse_iso, utcnow

IEM = "https://mesonet.agron.iastate.edu"
STAGE4 = f"{IEM}/json/stage4.py"
COCORAHS_NET = "WA_COCORAHS"


def _stage4() -> list[dict]:
    """Hourly Stage IV precip for the last RAIN_HOURS, one record per hour ending at `t`."""
    now = utcnow()
    start = now - timedelta(hours=RAIN_HOURS)
    series = {}
    d = start.date()
    while d <= now.date():  # the service takes one UTC date per request
        url = f"{STAGE4}?lat={SITE['lat']}&lon={SITE['lon']}&valid={d.isoformat()}"
        for r in get_json(url).get("data", []):
            t = parse_iso(r["end_valid"])
            if start < t <= now and r["precip_in"] is not None:
                series[iso(t)] = {"t": iso(t), "precip_in": round(r["precip_in"], 3)}
        d += timedelta(days=1)
    return [series[k] for k in sorted(series)]


def _gauges() -> list[dict]:
    """Recent daily CoCoRaHS reports within RAIN_GAUGE_MAX_KM of the site."""
    feats = get_json(f"{IEM}/geojson/network/{COCORAHS_NET}.geojson")["features"]
    near = {}
    for f in feats:
        lon, lat = f["geometry"]["coordinates"][:2]
        km = distance_km(SITE["lat"], SITE["lon"], lat, lon)
        if km <= RAIN_GAUGE_MAX_KM:
            sid = f["properties"].get("sid") or f["id"]
            near[sid] = {"id": sid, "name": f["properties"].get("sname"), "lat": lat, "lon": lon,
                         "distance_km": round(km, 1), "reports": []}
    if not near:
        return []

    # Report dates are local; walk back from today in the site's time zone.
    today = datetime.now(ZoneInfo(SITE["timezone"])).date()
    for i in range(RAIN_GAUGE_DAYS):
        day = (today - timedelta(days=i)).isoformat()
        rows = get_json(f"{IEM}/api/1/daily.json?network={COCORAHS_NET}&date={day}").get("data", [])
        for r in rows:
            g = near.get(r["station"])
            if g is None or r.get("precip") is None:
                continue
            trace = 0 < r["precip"] < 0.005  # IEM encodes a trace as 0.0001
            g["reports"].append({"date": r["date"], "precip_in": 0.0 if trace else r["precip"],
                                 "trace": trace})

    out = []
    for g in near.values():
        if not g["reports"]:
            continue
        g["reports"].sort(key=lambda r: r["date"])
        g["latest"] = g["reports"][-1]
        g["url"] = f"https://dex.cocorahs.org/stations/{g['id']}"
        out.append(g)
    out.sort(key=lambda g: g["distance_km"])
    return out[:RAIN_GAUGE_MAX_N]


def _sum(series: list[dict], hours: int) -> float | None:
    """Total over the `hours` ending at the latest analysed hour (data lag ~2 h behind now)."""
    if not series:
        return None
    end = parse_iso(series[-1]["t"])
    return round(sum(r["precip_in"] for r in series
                     if end - parse_iso(r["t"]) < timedelta(hours=hours)), 2)


def fetch() -> dict:
    notes = []
    series = []
    try:
        series = _stage4()
    except Exception as e:
        notes.append(f"Stage IV: {type(e).__name__}: {e}")
    gauges = []
    try:
        gauges = _gauges()
        if not gauges:
            notes.append(f"No CoCoRaHS reports within {RAIN_GAUGE_MAX_KM} km "
                         f"in the last {RAIN_GAUGE_DAYS} days")
    except Exception as e:
        notes.append(f"CoCoRaHS: {type(e).__name__}: {e}")
    if not series and not gauges:
        raise RuntimeError("; ".join(notes) or "no rain data")

    return {
        "source": "NCEP Stage IV (radar + gauge) and CoCoRaHS, via Iowa Environmental Mesonet",
        "source_url": f"{IEM}/rainfall/",
        "point": {"lat": SITE["lat"], "lon": SITE["lon"]},
        "hourly": series,
        "through": series[-1]["t"] if series else None,
        "totals": {f"h{h}": _sum(series, h) for h in (24, 48, 72)},
        "gauges": gauges,
        "notes": notes,
        "units": {"precip_in": "in"},
    }
