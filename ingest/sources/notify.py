"""Phone push alerts through ntfy when conditions change in a way that may need farm action.

Runs after the other sources and works from the same condensed digest as the
briefing (sources/briefing.py), so alerts use the page's default thresholds.
Triggers are fixed rules, never a model:

- a new NWS weather or marine alert
- a change in the DOH recreational biotoxin zone or commercial growing area status
- the rain watch reaching 60% of the threshold, then the threshold
- a workable daylight low in the next 3 days with forecast air temp at the heat threshold
- gusts at or above the threshold in the next 24 h
- an exposed farm sensor at or above the heat threshold, or a sensor going offline

Each condition has a stable key. An alert is sent when its key first appears, and
re-armed once the condition clears. Keys already sent within NOTIFY_COOLDOWN_HOURS
are not repeated, which stops flapping values (rain hovering at 60%) from paging
growers every 20 minutes. During quiet hours only NWS alerts and DOH changes go
out; anything else waits until morning if it still holds.

The first run with no previous state records what is already true and sends
nothing. Without NTFY_TOPIC, alerts are logged in notify.json but not sent.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta

from config import (DEFAULT_THRESHOLDS, NOTIFY_COOLDOWN_HOURS, NOTIFY_QUIET_HOURS, NTFY_SERVER,
                    SITE_URL, USER_AGENT)
from sources.briefing import TZ, digest
from sources.common import iso, parse_iso, utcnow

LOG_KEEP = 30
# Alert key prefixes that depend on each source.
SOURCE_KEYS = {"alerts": ["nws"], "shellfish": ["doh"], "rain": ["rain"], "forecast": ["rain", "heat", "gust"],
               "tides": ["heat"], "sun": ["heat"], "sensors": ["sensorheat", "offline"]}


def _alert(title: str, message: str, priority: int = 3, tags: str = "", urgent: bool = False) -> dict:
    return {"title": title, "message": message, "priority": priority, "tags": tags, "urgent": urgent}


def conditions(data: dict, now: datetime) -> dict[str, dict]:
    """Every alert-worthy condition that holds right now, by stable key."""
    d, th, out = digest(data, now), DEFAULT_THRESHOLDS, {}

    for a in (data.get("alerts") or {}).get("alerts", []):
        until = a.get("ends") or a.get("expires")
        severe = a.get("severity") in ("Severe", "Extreme")
        out[f"nws:{a.get('event')}:{a.get('onset')}"] = _alert(
            a.get("event") or "NWS alert",
            (a.get("headline") or a.get("event") or "") +
            (f". Until {parse_iso(until).astimezone(TZ):%a %-I:%M %p}." if until else ""),
            5 if severe else 4, "warning", urgent=True)

    for label, value in d["shellfish"].items():
        if value:
            name = "Biotoxin zone" if label.startswith("recreational") else "Growing area"
            out[f"doh:{label}:{value}"] = _alert(f"DOH status: {value}",
                                                 f"{name} status is now {value}. Confirm with WA DOH.",
                                                 4, "oyster", urgent=True)

    rain = d["rain_in"]
    if rain["approaching_threshold"] or rain["at_or_above_threshold"]:
        over = rain["at_or_above_threshold"]
        out[f"rain:{'over' if over else 'approaching'}"] = _alert(
            f"Rain watch {rain['watch_total']} in" + (" — at threshold" if over else ""),
            f"{rain['observed_past_24h'] or 0} in observed past 24 h + {rain['forecast_next_24h'] or 0} in "
            f"forecast next 24 h, against the {th['rain_in_24h']} in threshold. Check conditional-area status with DOH.",
            4 if over else 3, "cloud_with_rain")

    for low in d["low_tides_next_72h"]:
        if low["heat_exposure"]:
            out[f"heat:{low['time']}"] = _alert(
                f"Heat exposure: {low['ft_mllw']} ft low {low['time']}",
                f"Forecast {low['air_f']}°F, sky {low['sky_cover_pct']}% cover, wind {low['wind_mph']} mph "
                f"(heat threshold {th['heat_f']}°F).", 4, "sunny")

    gust = d.get("max_gust_next_24h")
    if gust and gust["at_or_above_threshold"]:
        out[f"gust:{gust['time'].split()[0]}"] = _alert(
            f"Gusts to {gust['mph']} mph {gust['time']}",
            f"From {gust['from']}. Check gear and boat plans.", 3, "wind_face")

    if not d.get("farm_sensors_mock"):
        for s in d.get("farm_sensors", []):
            if s["out_of_water"] and (s["temp_f"] or 0) >= th["heat_f"]:
                out[f"sensorheat:{s['name']}"] = _alert(
                    f"{s['name']} at {s['temp_f']}°F, out of water",
                    f"Reading at {s['last_seen']}, at or above the {th['heat_f']}°F heat threshold.", 4, "thermometer")
            if s["status"] == "offline":
                out[f"offline:{s['name']}"] = _alert(
                    f"Sensor offline: {s['name']}",
                    f"Last reading {s['last_seen']}. Check battery, mount, or gateway.", 2, "electric_plug")
    return out


def plan(active: dict[str, dict], prev: dict | None, now: datetime) -> tuple[list[str], dict]:
    """Which keys to send now, and the state to keep for next run."""
    sent = {k: t for k, t in ((prev or {}).get("sent") or {}).items()
            if now - parse_iso(t) < timedelta(days=3)}
    if prev is None:
        return [], {"notified": sorted(active), "sent": sent}
    notified = set(prev.get("notified", [])) & set(active)  # cleared conditions re-arm
    start, end = NOTIFY_QUIET_HOURS
    hour = now.astimezone(TZ).hour
    quiet = hour >= start or hour < end
    send = []
    for key in sorted(set(active) - notified):
        recent = key in sent and now - parse_iso(sent[key]) < timedelta(hours=NOTIFY_COOLDOWN_HOURS)
        if recent:
            notified.add(key)
        elif not quiet or active[key]["urgent"]:
            send.append(key)
        # otherwise: quiet hours, leave un-notified so it goes out in the morning if it still holds
    return send, {"notified": sorted(notified), "sent": sent}


def _publish(topic: str, a: dict) -> None:
    body = {"topic": topic, "title": a["title"], "message": a["message"], "priority": a["priority"],
            "click": SITE_URL, "tags": [t for t in a["tags"].split(",") if t]}
    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    if os.environ.get("NTFY_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['NTFY_TOKEN']}"
    req = urllib.request.Request(NTFY_SERVER, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def fetch(ctx=None) -> dict:
    now = utcnow()
    names = ["tides", "sun", "forecast", "alerts", "rain", "shellfish", "sensors"]
    data = {n: ctx.current(n) for n in names} if ctx else {}
    active = conditions(data, now)
    prev = ctx.previous("notify") if ctx else None
    topic = os.environ.get("NTFY_TOPIC")

    send, state = plan(active, prev, now)
    # A source with no data this run (failed, no fallback) must not re-arm its alerts,
    # or they would all fire again when it comes back.
    missing = {p for n, ps in SOURCE_KEYS.items() if data.get(n) is None for p in ps}
    held = {k for k in (prev or {}).get("notified", []) if k.split(":")[0] in missing}
    state["notified"] = sorted(set(state["notified"]) | held)
    log, errors = list((prev or {}).get("log", [])), []
    for key in send:
        a = active[key]
        try:
            if topic:
                _publish(topic, a)
        except Exception as e:  # not marked notified, so the next run retries it
            errors.append(f"{key}: {type(e).__name__}: {e}")
            continue
        state["notified"] = sorted(set(state["notified"]) | {key})
        state["sent"][key] = iso(now)
        log.insert(0, {"t": iso(now), "key": key, "title": a["title"], "message": a["message"],
                       "delivered": bool(topic)})

    return {"source": f"Push alerts via ntfy ({NTFY_SERVER})", "configured": bool(topic),
            "active": [{"key": k, "title": a["title"]} for k, a in sorted(active.items())],
            **state, "log": log[:LOG_KEEP], "errors": errors}
