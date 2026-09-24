"""Near-real-time water temperature, salinity, and dissolved oxygen.

As of Sept 2026 no current T/S/DO source is available inside northern Hood
Canal: the ORCA Hansville (NDBC 46125) and Dabob Bay (46122) water sensors
have been reporting NaN/stale, and the UW NWEM ERDDAP serving the profiles
was unreachable. The buoys are still queried so they reappear automatically
when they come back online; a station is only included when it has valid
data within MAX_AGE_DAYS. NOAA Port Townsend provides a current (but distant)
water temperature.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError

from config import SITE
from sources.common import c_to_f, distance_km, get_json, iso, parse_iso, utcnow

MAX_AGE_DAYS = 3
ERDDAP = "https://erddap.sensors.ioos.us/erddap/tabledap"

BUOYS = [
    {"id": "gov-ndbc-46125", "name": "ORCA Hansville buoy", "lat": 47.907, "lon": -122.627,
     "url": "https://nvs.nanoos.org/Explorer?action=oiw:fixed_platform:ORCA_Hansville"},
    {"id": "gov-ndbc-46122", "name": "ORCA Dabob Bay buoy", "lat": 47.803, "lon": -122.803,
     "url": "https://nvs.nanoos.org/Explorer?action=oiw:fixed_platform:ORCA_Dabobbay"},
]
COOPS = {"id": "9444900", "name": "Port Townsend (NOAA)", "lat": 48.111, "lon": -122.760,
         "url": "https://tidesandcurrents.noaa.gov/stationhome.html?id=9444900"}


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN -> None


def _row(t, temp_c=None, sal=None, do=None, depth=None):
    return {"t": t, "water_temp_c": None if temp_c is None else round(temp_c, 2),
            "water_temp_f": c_to_f(temp_c), "salinity_psu": None if sal is None else round(sal, 2),
            "do_mgl": None if do is None else round(do, 2), "depth_m": depth}


def _station(meta: dict, provider: str, series: list[dict]) -> dict | None:
    series = [r for r in series if any(r[k] is not None for k in ("water_temp_c", "salinity_psu", "do_mgl"))]
    if not series or utcnow() - parse_iso(series[-1]["t"]) > timedelta(days=MAX_AGE_DAYS):
        return None
    return {**meta, "provider": provider, "latest": series[-1], "series": series,
            "distance_km": round(distance_km(SITE["lat"], SITE["lon"], meta["lat"], meta["lon"]), 1)}


def _buoy(b: dict) -> dict | None:
    url = (f"{ERDDAP}/{b['id']}.json?time,z,sea_water_temperature,sea_water_practical_salinity,"
           f"mass_concentration_of_oxygen_in_sea_water&time%3E=now-7days")
    try:
        table = get_json(url)["table"]
    except HTTPError as e:
        if e.code == 404:  # ERDDAP returns 404 when no rows match the time range
            return None
        raise
    series = []
    for t, z, temp, sal, do in table["rows"]:
        series.append(_row(iso(parse_iso(t)), _num(temp), _num(sal), _num(do), _num(z)))
    series.sort(key=lambda r: r["t"])
    return _station(b, "NANOOS / NDBC via IOOS ERDDAP", series)


def _coops(s: dict) -> dict | None:
    url = ("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=water_temperature"
           f"&station={s['id']}&range=72&time_zone=gmt&units=metric&format=json&application=acantha")
    data = get_json(url)
    if "error" in data:
        raise RuntimeError(data["error"].get("message"))
    series = []
    for i, d in enumerate(data.get("data", [])):
        if i % 5:  # 6-minute data -> 30-minute
            continue
        t = datetime.strptime(d["t"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        series.append(_row(iso(t), _num(d["v"])))
    return _station(s, "NOAA CO-OPS", series)


def fetch() -> dict:
    stations, notes = [], []
    for b in BUOYS:
        try:
            st = _buoy(b)
            if st:
                stations.append(st)
            else:
                notes.append(f"{b['name']}: no valid water data in the last {MAX_AGE_DAYS} days")
        except Exception as e:
            notes.append(f"{b['name']}: {type(e).__name__}: {e}")
    try:
        st = _coops(COOPS)
        if st:
            stations.append(st)
    except Exception as e:
        notes.append(f"{COOPS['name']}: {type(e).__name__}: {e}")
    if not stations and notes:
        raise RuntimeError("; ".join(notes))
    stations.sort(key=lambda s: s["distance_km"])
    return {"source": "IOOS ERDDAP (ORCA buoys), NOAA CO-OPS", "stations": stations, "notes": notes}
