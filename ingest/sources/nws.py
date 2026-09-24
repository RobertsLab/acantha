"""National Weather Service: gridded forecast, text forecast, alerts, observations."""
from __future__ import annotations

from datetime import timedelta

from config import NWS_GRID, NWS_MARINE_ZONE, NWS_OBS_HOURS, NWS_OBS_STATIONS, SITE
from sources.common import (
    c_to_f, distance_km, get_json, hour_floor, iso, kmh_to_mph, mm_to_in,
    parse_iso, parse_valid_time, utcnow,
)

BASE = "https://api.weather.gov"
GRID = f"{BASE}/gridpoints/{NWS_GRID['office']}/{NWS_GRID['x']},{NWS_GRID['y']}"

# gridpoint property -> (output key, converter, split_over_duration)
GRID_FIELDS = {
    "temperature": ("air_temp_f", c_to_f, False),
    "windSpeed": ("wind_mph", kmh_to_mph, False),
    "windGust": ("gust_mph", kmh_to_mph, False),
    "windDirection": ("wind_dir_deg", lambda v: None if v is None else round(v), False),
    "skyCover": ("sky_pct", lambda v: v, False),
    "probabilityOfPrecipitation": ("pop_pct", lambda v: v, False),
    "quantitativePrecipitation": ("qpf_in", mm_to_in, True),
    "relativeHumidity": ("rh_pct", lambda v: v, False),
}


def forecast() -> dict:
    props = get_json(GRID, accept="application/geo+json")["properties"]
    start = hour_floor(utcnow())
    end = start + timedelta(days=7)
    hours: dict[str, dict] = {}
    for prop, (key, conv, split) in GRID_FIELDS.items():
        for item in props.get(prop, {}).get("values", []):
            t0, n = parse_valid_time(item["validTime"])
            value = item["value"]
            if split and value is not None:
                value = value / n
            for h in range(n):
                t = t0 + timedelta(hours=h)
                if start <= t < end:
                    hours.setdefault(iso(t), {"t": iso(t)})[key] = conv(value)
    series = [hours[k] for k in sorted(hours)]

    periods = []
    try:
        text = get_json(f"{GRID}/forecast", accept="application/geo+json")["properties"]["periods"]
        periods = [
            {k: p.get(k) for k in ("name", "startTime", "endTime", "isDaytime",
                                   "temperature", "windSpeed", "windDirection",
                                   "shortForecast", "detailedForecast")}
            for p in text[:8]
        ]
    except Exception as e:  # text forecast is nice-to-have
        periods = [{"name": "unavailable", "detailedForecast": str(e)}]

    return {
        "source": "NWS api.weather.gov gridpoint forecast",
        "source_url": f"https://forecast.weather.gov/MapClick.php?lat={SITE['lat']}&lon={SITE['lon']}",
        "grid": NWS_GRID,
        "updated": props.get("updateTime"),
        "hourly": series,
        "periods": periods,
        "units": {"air_temp_f": "°F", "wind_mph": "mph", "gust_mph": "mph",
                  "qpf_in": "in/hr", "pop_pct": "%", "sky_pct": "%", "rh_pct": "%"},
    }


def alerts() -> dict:
    seen, items = set(), []
    for url in (f"{BASE}/alerts/active?point={SITE['lat']},{SITE['lon']}",
                f"{BASE}/alerts/active/zone/{NWS_MARINE_ZONE}"):
        for f in get_json(url, accept="application/geo+json").get("features", []):
            p = f["properties"]
            if p["id"] in seen:
                continue
            seen.add(p["id"])
            items.append({k: p.get(k) for k in ("event", "headline", "severity", "urgency",
                                               "onset", "ends", "expires", "areaDesc",
                                               "description", "instruction")})
    return {"source": "NWS active alerts", "zone": NWS_MARINE_ZONE, "alerts": items}


def _obs_value(props, key, conv):
    v = props.get(key) or {}
    return conv(v.get("value"))


def _thin(series: list[dict], minutes: int = 15) -> list[dict]:
    """Collapse to one record per time bucket, keeping the latest non-null value per field.

    Hourly precipitation is kept as the bucket maximum so it isn't lost when
    a station reports it only on the hourly (METAR) record.
    """
    buckets: dict[str, dict] = {}
    for r in sorted(series, key=lambda r: r["t"]):
        dt = parse_iso(r["t"])
        key = iso(dt.replace(minute=dt.minute - dt.minute % minutes, second=0))
        b = buckets.setdefault(key, {"t": key})
        for k, v in r.items():
            if k == "t" or v is None:
                continue
            b[k] = max(b.get(k) or 0, v) if k == "precip_1h_in" else v
    fields = [k for k in series[0] if k != "t"] if series else []
    return [{k: b.get(k) for k in ["t", *fields]} for b in buckets.values()]


def observations() -> dict:
    feats = get_json(f"{GRID}/stations?limit=25", accept="application/geo+json")["features"]
    stations = []
    for f in feats:
        lon, lat = f["geometry"]["coordinates"][:2]
        stations.append({
            "id": f["properties"]["stationIdentifier"],
            "name": f["properties"]["name"].strip(),
            "lat": lat, "lon": lon,
            "distance_km": round(distance_km(SITE["lat"], SITE["lon"], lat, lon), 1),
        })
    stations.sort(key=lambda s: s["distance_km"])

    start = iso(utcnow() - timedelta(hours=NWS_OBS_HOURS))
    # Nearest N stations that report temperature, plus the nearest ASOS
    # airport station (K***), which is the most reliable source of hourly rain.
    asos = next((s for s in stations if s["id"].startswith("K")), None)
    out = []
    for st in stations:
        if len(out) >= NWS_OBS_STATIONS and st is not asos:
            continue
        try:
            obs = get_json(f"{BASE}/stations/{st['id']}/observations?start={start}",
                           accept="application/geo+json")["features"]
        except Exception:
            continue
        if not obs:
            continue
        series = []
        for o in obs:
            p = o["properties"]
            series.append({
                "t": iso(parse_iso(p["timestamp"])),
                "air_temp_f": _obs_value(p, "temperature", c_to_f),
                "wind_mph": _obs_value(p, "windSpeed", kmh_to_mph),
                "gust_mph": _obs_value(p, "windGust", kmh_to_mph),
                "wind_dir_deg": _obs_value(p, "windDirection", lambda v: v),
                "precip_1h_in": _obs_value(p, "precipitationLastHour", mm_to_in),
                "rh_pct": _obs_value(p, "relativeHumidity",
                                     lambda v: None if v is None else round(v)),
            })
        series = _thin(series)
        temps = sum(r["air_temp_f"] is not None for r in series)
        if temps < len(series) / 2:  # skip stations that rarely report temperature
            continue
        st["series"] = series
        st["latest"] = series[-1]
        st["url"] = f"{BASE}/stations/{st['id']}/observations/latest"
        st["asos"] = st is asos
        out.append(st)
        if len(out) > NWS_OBS_STATIONS and any(o["asos"] for o in out):
            break
    return {"source": "NWS / MADIS surface observations", "stations": out}
