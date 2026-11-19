"""Plain-language briefing for the dashboard, written by Claude from this run's data.

Runs after every other source. It reads their output, condenses it into a small
digest (times already in local time, values rounded), and asks Claude for a
headline and a few short points. The page shows the briefing above the flags;
the flags, alerts, and DOH status remain the authority.

The workflow runs every ~20 minutes, so the previous briefing is reused when the
digest is unchanged, or when it is younger than BRIEFING_MIN_MINUTES and no alert
or shellfish status has changed. Most runs make no API call.

Without ANTHROPIC_API_KEY the source returns `configured: false` and the card
stays hidden, so local runs and forks work unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import BRIEFING_MIN_MINUTES, BRIEFING_MODEL, BRIEFING_THRESHOLDS, SITE
from sources.common import iso, parse_iso, utcnow

TZ = ZoneInfo(SITE["timezone"])
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

SYSTEM = """You write the short briefing at the top of a conditions page for oyster growers \
at Thorndyke Bay, Hood Canal, Washington. The input is JSON condensed from NOAA tide \
predictions, the NWS forecast and alerts, observed rain, WA Department of Health shellfish \
layers, water observations, the UW LiveOcean model, and on-farm temperature sensors.

Return a headline (under 90 characters) and 2 to 5 points, one sentence each, most \
decision-relevant first: daylight low-tide work windows and heat exposure, wind and marine \
alerts, rain toward the closure threshold, shellfish status, water temperature in Vibrio \
season (May to September), and sensors that stopped reporting.

Rules:
- Use only facts in the input. Copy numbers, times, and names as given; times are already \
local. Do not add up totals or forecast beyond the data.
- Leave out anything that is null or missing rather than guessing.
- Threshold checks are already done against the page's default thresholds \
(workable_daylight_low, heat_exposure, at_or_above_threshold, approaching_threshold). Rely on \
them instead of comparing numbers yourself, and when one is true say so, e.g. "at or above \
the default 75°F heat threshold". A low tide that is not a workable daylight low is not a \
work window.
- Shellfish: report the DOH status as given. The biotoxin zone is a recreational closure; \
never say commercial harvest is open or closed.
- Name a source only when it changes how far to trust a number (a model estimate, a station \
34 km away).
- Plain words for someone on a beach with a phone. No markdown, no emoji."""

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "points"],
    "additionalProperties": False,
}


def _local(t: str | datetime, fmt: str = "%a %-I:%M %p") -> str:
    dt = parse_iso(t) if isinstance(t, str) else t
    return dt.astimezone(TZ).strftime(fmt)


def _nearest(rows: list[dict], t: datetime) -> dict | None:
    return min(rows, key=lambda r: abs(parse_iso(r["t"]) - t), default=None)


def _daylight(t: datetime, sun: dict | None) -> bool | None:
    for d in (sun or {}).get("days", []):
        if parse_iso(d["sunrise"]) <= t <= parse_iso(d["sunset"]):
            return True
    return False if sun else None


def _compass(deg) -> str | None:
    return None if deg is None else COMPASS[round(deg / 45) % 8]


def digest(data: dict, now: datetime) -> dict:
    """Condense the other sources' output into what the briefing needs."""
    hourly = (data.get("forecast") or {}).get("hourly", [])
    th = BRIEFING_THRESHOLDS
    out: dict = {
        "today": _local(now, "%A, %B %-d"),
        "now": _local(now),
        "vibrio_season": 5 <= now.astimezone(TZ).month <= 9,
        "default_thresholds": BRIEFING_THRESHOLDS,
    }

    lows = []
    for h in (data.get("tides") or {}).get("hilo", []):
        t = parse_iso(h["t"])
        if h["type"] == "L" and now <= t <= now + timedelta(hours=72):
            f = _nearest(hourly, t) or {}
            daylight = _daylight(t, data.get("sun"))
            workable = bool(daylight) and h["v"] <= th["low_tide_ft"]
            lows.append({"time": _local(t), "ft_mllw": h["v"], "daylight": daylight,
                         "air_f": f.get("air_temp_f"), "wind_mph": f.get("wind_mph"),
                         "sky_cover_pct": f.get("sky_pct"), "workable_daylight_low": workable,
                         "heat_exposure": workable and (f.get("air_temp_f") or -99) >= th["heat_f"]})
    out["low_tides_next_72h"] = lows

    out["forecast"] = [{"period": p["name"], "summary": p["shortForecast"], "temp_f": p["temperature"],
                        "wind": f"{p['windDirection']} {p['windSpeed']}"}
                       for p in (data.get("forecast") or {}).get("periods", [])[:4]]
    next24 = [h for h in hourly if now <= parse_iso(h["t"]) <= now + timedelta(hours=24)]
    gust = max((h for h in next24 if h.get("gust_mph") is not None), key=lambda h: h["gust_mph"], default=None)
    if gust:
        out["max_gust_next_24h"] = {"mph": round(gust["gust_mph"]), "time": _local(gust["t"]),
                                    "from": _compass(gust.get("wind_dir_deg")),
                                    "at_or_above_threshold": gust["gust_mph"] >= th["gust_mph"]}

    # Same closure-watch window as the page's flag: observed past 24 h + forecast next 24 h.
    past = ((data.get("rain") or {}).get("totals") or {}).get("h24")
    ahead = round(sum(h.get("qpf_in") or 0 for h in next24), 2) if next24 else None
    total = None if past is None and ahead is None else round((past or 0) + (ahead or 0), 2)
    out["rain_in"] = {"observed_past_24h": past, "forecast_next_24h": ahead, "watch_total": total,
                      "at_or_above_threshold": total is not None and total >= th["rain_in_24h"],
                      "approaching_threshold": total is not None and th["rain_in_24h"] * 0.6 <= total < th["rain_in_24h"]}

    out["alerts"] = [{"event": a.get("event"), "headline": a.get("headline"),
                      "until": _local(a["ends"] or a["expires"]) if a.get("ends") or a.get("expires") else None,
                      "instruction": (a.get("instruction") or "")[:400] or None}
                     for a in (data.get("alerts") or {}).get("alerts", [])]

    sf = data.get("shellfish") or {}
    zone, area = sf.get("site_zone") or {}, sf.get("site_growing_area") or {}
    out["shellfish"] = {
        "recreational_biotoxin_zone": f"{zone['name']}: {zone['status']}" if zone else None,
        "commercial_growing_area": f"{area['name']}: {area['classification']}" if area else None,
    }

    water = []
    for s in (data.get("water") or {}).get("stations", []):
        lt = s.get("latest") or {}
        if lt.get("water_temp_f") is not None and now - parse_iso(lt["t"]) < timedelta(hours=6):
            water.append({"station": s["name"], "km_away": s.get("distance_km"), "temp_f": lt["water_temp_f"]})
    out["water_observed"] = water[:2]

    cell = next((c for c in (data.get("liveocean") or {}).get("cells", []) if c["id"] == "thorndyke"), None)
    if cell:
        cur = _nearest(cell["series"], now)
        ahead = [r for r in cell["series"] if now <= parse_iso(r["t"]) <= now + timedelta(hours=72)]
        peak = max(ahead, key=lambda r: r["temp_f"], default=None)
        out["model_bay_mouth"] = {"temp_f_now": cur and cur["temp_f"], "salinity_now": cur and cur["salt"],
                                  "peak_temp_f_next_72h": peak and peak["temp_f"],
                                  "peak_time": peak and _local(peak["t"])}

    sensors = []
    for s in (data.get("sensors") or {}).get("stations", []):
        lt = s.get("latest") or {}
        sensors.append({"name": s["name"], "status": s["status"], "temp_f": lt.get("temp_f"),
                        "out_of_water": lt.get("exposed"),
                        "last_seen": _local(s["last_seen"]) if s.get("last_seen") else None})
    if sensors:
        out["farm_sensors"] = sensors
        out["farm_sensors_mock"] = bool((data.get("sensors") or {}).get("mock"))
    return out


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:16]


def _hash_view(d: dict) -> dict:
    """The digest minus what changes every run without changing the story."""
    v = {k: val for k, val in d.items() if k != "now"}
    v["farm_sensors"] = [{"name": s["name"], "status": s["status"],
                          "hot": bool(s["out_of_water"] and (s["temp_f"] or 0) >= BRIEFING_THRESHOLDS["heat_f"])}
                         for s in d.get("farm_sensors", [])]
    v["water_observed"] = [{**w, "temp_f": round(w["temp_f"])} for w in d.get("water_observed", [])]
    return v


def _urgent(d: dict) -> str:
    return _hash([[a["event"], a["headline"]] for a in d["alerts"]] + [d["shellfish"]])


def _write(d: dict) -> dict:
    import anthropic  # only this source needs the SDK: pip install -r ingest/requirements.txt

    kwargs = {}
    if not BRIEFING_MODEL.startswith("claude-haiku"):  # Haiku has no server-side fallback
        kwargs = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    resp = anthropic.Anthropic().beta.messages.create(
        model=BRIEFING_MODEL,
        max_tokens=4000,
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(d, indent=1)}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        **kwargs,
    )
    if resp.stop_reason != "end_turn":
        raise RuntimeError(f"briefing not written: stop_reason={resp.stop_reason}")
    out = json.loads(next(b.text for b in resp.content if b.type == "text"))
    out["model"] = resp.model
    return out


def fetch(ctx=None) -> dict:
    base = {"source": "Written by Claude from this run's data. Advisory; the flags and DOH status are the authority."}
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {**base, "configured": False, "note": "Set ANTHROPIC_API_KEY to write the briefing."}

    now = utcnow()
    names = ["tides", "sun", "forecast", "alerts", "rain", "shellfish", "water", "liveocean", "sensors"]
    d = digest({n: ctx.current(n) for n in names} if ctx else {}, now)
    h, urgent = _hash(_hash_view(d)), _urgent(d)

    prev = ctx.previous("briefing") if ctx else None
    if prev and prev.get("headline"):
        young = now - parse_iso(prev["generated_at"]) < timedelta(minutes=BRIEFING_MIN_MINUTES)
        if prev.get("inputs_hash") == h or (young and prev.get("urgent_hash") == urgent):
            return {**prev, "reused": True}

    return {**base, "configured": True, **_write(d), "generated_at": iso(now),
            "inputs_hash": h, "urgent_hash": urgent, "digest": d, "reused": False}
