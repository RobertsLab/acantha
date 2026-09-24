"""On-farm temperature sensors via The Things Network (LoRaWAN).

Readings are pulled from the TTN Storage Integration, which keeps only a
short window of uplinks. History is therefore carried forward from the
previously published sensors.json, merged with new uplinks, and trimmed to
SENSOR_RETENTION_DAYS. QC is recomputed over the whole window on every run,
following IOOS QARTOD flag conventions (1 pass, 2 not evaluated, 3 suspect,
4 fail) so the data can later be shared with NANOOS.

Modes:
  TTN_APP_ID + TTN_API_KEY set  -> live data from TTN
  SENSORS_MOCK=1                -> realistic fake data for building the UI
  neither                       -> empty result with configured=false
"""
from __future__ import annotations

import json
import math
import os
import random
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from config import (SENSOR_OFFLINE_MIN, SENSOR_RETENTION_DAYS, SENSOR_STALE_MIN, SENSORS,
                    TTN_CLUSTER, USER_AGENT)
from sources.common import c_to_f, iso, parse_iso, utcnow

TEMP_KEYS = ("temp_c", "TempC1", "TempC_DS", "TempC_SHT", "temperature", "temp")
BATTERY_KEYS = ("battery_v", "BatV", "Bat_V", "battery")

# QC thresholds (deg C). The climatology range covers both Hood Canal water
# and air temperature on an exposed beach.
GROSS_RANGE = (-5.0, 40.0)
CLIMATOLOGY = (-2.0, 32.0)
SPIKE_SUSPECT, SPIKE_FAIL = 3.0, 8.0
FLAT_EPS, FLAT_SUSPECT, FLAT_FAIL = 0.005, 8, 16   # consecutive near-identical readings

MOCK_INTERVAL_MIN = 15


# ---------- TTN ----------

def _ttn_uplinks(app_id: str, api_key: str, after: datetime) -> list[dict]:
    """Return uplink results from the TTN Storage Integration since `after`."""
    q = urllib.parse.urlencode({"after": iso(after), "limit": 10000, "order": "received_at"})
    url = (f"https://{TTN_CLUSTER}.cloud.thethings.network/api/v3/as/applications/"
           f"{urllib.parse.quote(app_id)}/packages/storage/uplink_message?{q}")
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}", "Accept": "text/event-stream", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode()
    # The response is a stream of {"result": {...}} objects separated by newlines.
    out = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            line = line[5:].strip()
        if line:
            out.append(json.loads(line).get("result", {}))
    return out


def _pick(payload: dict, keys) -> float | None:
    for k in keys:
        v = payload.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return None


def _parse_uplink(r: dict, sensor: dict) -> dict | None:
    up = r.get("uplink_message") or {}
    payload = up.get("decoded_payload") or {}
    tkeys = (sensor["temp_field"],) if sensor.get("temp_field") else TEMP_KEYS
    bkeys = (sensor["battery_field"],) if sensor.get("battery_field") else BATTERY_KEYS
    temp = _pick(payload, tkeys)
    t = r.get("received_at") or up.get("received_at")
    if temp is None or not t:
        return None
    rx = up.get("rx_metadata") or []
    best = max(rx, key=lambda m: m.get("rssi", -999), default={})
    return {"t": iso(parse_iso(t)), "temp_c": round(temp, 2),
            "battery_v": _pick(payload, bkeys), "rssi": best.get("rssi"), "snr": best.get("snr")}


# ---------- tides / exposure ----------

def _tide_at(hilo: list[dict], t: datetime) -> float | None:
    """Tide height (ft MLLW) by cosine interpolation between NOAA high/low predictions."""
    for a, b in zip(hilo, hilo[1:]):
        ta, tb = parse_iso(a["t"]), parse_iso(b["t"])
        if ta <= t <= tb:
            frac = (t - ta).total_seconds() / (tb - ta).total_seconds()
            return a["v"] + (b["v"] - a["v"]) * (1 - math.cos(math.pi * frac)) / 2
    return None


def _synthetic_tide(t: datetime) -> float:
    """Plausible mixed semidiurnal Hood Canal tide (ft MLLW), for mock mode only."""
    h = t.timestamp() / 3600
    return 6.5 + 4.3 * math.cos(2 * math.pi * h / 12.42) + 2.4 * math.cos(2 * math.pi * h / 23.93 + 1.1)


# ---------- QC ----------

def _qc(series: list[dict]) -> None:
    """Annotate each row in place with a QARTOD-style `qc` flag and failed `qc_tests`."""
    vals = [r["temp_c"] for r in series]
    flat = 0
    for i, r in enumerate(series):
        v, flag, tests = vals[i], 1, []

        def worse(f, name):
            nonlocal flag
            flag = max(flag, f)
            tests.append(name)

        if not GROSS_RANGE[0] <= v <= GROSS_RANGE[1]:
            worse(4, "gross_range")
        elif not CLIMATOLOGY[0] <= v <= CLIMATOLOGY[1]:
            worse(3, "climatology")

        # QARTOD spike test: deviation from neighbors, discounting a genuine step
        # (e.g. the probe going from water to air as the tide drops).
        if 0 < i < len(vals) - 1:
            a, c = vals[i - 1], vals[i + 1]
            spike = abs(v - (a + c) / 2) - abs(c - a) / 2
            if spike > SPIKE_FAIL:
                worse(4, "spike")
            elif spike > SPIKE_SUSPECT:
                worse(3, "spike")
        elif flag == 1 and i == len(vals) - 1 and len(vals) > 1:
            flag = 2  # newest point: spike test needs the next reading

        flat = flat + 1 if i and abs(v - vals[i - 1]) < FLAT_EPS else 0
        if flat >= FLAT_FAIL:
            worse(4, "flat_line")
        elif flat >= FLAT_SUSPECT:
            worse(3, "flat_line")

        r["qc"] = flag
        if tests:
            r["qc_tests"] = tests
        else:
            r.pop("qc_tests", None)


# ---------- assembly ----------

def _status(last_seen: str | None, now: datetime) -> str:
    if not last_seen:
        return "offline"
    age = (now - parse_iso(last_seen)).total_seconds() / 60
    return "live" if age < SENSOR_STALE_MIN else "stale" if age < SENSOR_OFFLINE_MIN else "offline"


def _station(sensor: dict, rows: list[dict], hilo, tide_fn, now: datetime, prev: dict | None = None) -> dict:
    cutoff = now - timedelta(days=SENSOR_RETENTION_DAYS)
    rows = sorted((r for r in rows if parse_iso(r["t"]) >= cutoff), key=lambda r: r["t"])
    for r in rows:
        tide = tide_fn(parse_iso(r["t"])) if tide_fn else (_tide_at(hilo, parse_iso(r["t"])) if hilo else None)
        if tide is not None:
            r["exposed"] = tide < sensor["elevation_ft"]
        else:
            r.setdefault("exposed", None)  # keep what an earlier run computed
        r["temp_f"] = c_to_f(r["temp_c"])
    _qc(rows)
    series = [{k: r[k] for k in ("t", "temp_c", "temp_f", "exposed", "qc", "qc_tests") if k in r} for r in rows]
    good = [r for r in series if r["qc"] in (1, 2)]
    # Radio/battery health comes from the newest uplink; carried over if none arrived this run.
    radio = next((r for r in reversed(rows) if "rssi" in r), prev or {})
    last_seen = series[-1]["t"] if series else None
    return {
        "id": sensor["id"], "name": sensor["name"], "lat": sensor["lat"], "lon": sensor["lon"],
        "elevation_ft": sensor["elevation_ft"], "placement": sensor.get("placement"),
        "status": _status(last_seen, now), "last_seen": last_seen,
        "battery_v": radio.get("battery_v"), "rssi": radio.get("rssi"), "snr": radio.get("snr"),
        "latest": good[-1] if good else None,
        "series": series,
    }


def _previous_rows(previous: dict | None, mock: bool) -> dict[str, dict]:
    """History from the last published file, unless it came from the other mode."""
    if not previous or bool(previous.get("mock")) != mock or not previous.get("configured"):
        return {}
    return {s["id"]: s for s in previous.get("stations", [])}


def _mock_rows(sensor: dict, idx: int, now: datetime) -> list[dict]:
    """Probe temperature relaxing toward water when submerged and toward air when exposed."""
    step = timedelta(minutes=MOCK_INTERVAL_MIN)
    end = now.replace(second=0, microsecond=0)
    end -= timedelta(minutes=end.minute % MOCK_INTERVAL_MIN)
    t = end - timedelta(days=SENSOR_RETENTION_DAYS)
    temp, rows = None, []
    while t <= end:
        rng = random.Random(f"{sensor['id']}{iso(t)}")  # same value for the same timestamp every run
        days_ago = (now - t).total_seconds() / 86400
        local_h = ((t.timestamp() / 3600) - 7) % 24          # PDT
        water = 13.6 + 0.05 * days_ago + 0.4 * math.sin(2 * math.pi * (local_h - 10) / 24)
        air = 15.0 + 6.5 * math.cos(2 * math.pi * (local_h - 15) / 24)
        exposed = _synthetic_tide(t) < sensor["elevation_ft"]
        target, tau = (air, 40) if exposed else (water, 10)   # minutes
        temp = target if temp is None else target + (temp - target) * math.exp(-MOCK_INTERVAL_MIN / tau)
        v = temp + rng.gauss(0, 0.08)
        # Faults to exercise QC and the UI: a spike, and a 3 h radio dropout.
        if idx == 1 and 47.9 < days_ago * 24 < 48.2:
            v += 12.0
        if idx == 2 and 30 < days_ago * 24 < 33:
            t += step
            continue
        rows.append({"t": iso(t), "temp_c": round(v, 2),
                     "battery_v": round(3.62 - 0.004 * (SENSOR_RETENTION_DAYS - days_ago) - 0.02 * idx, 3),
                     "rssi": int(-78 - 9 * idx + rng.gauss(0, 3)), "snr": round(8 - 2 * idx + rng.gauss(0, 1), 1)})
        t += step
    return rows


def fetch(ctx=None) -> dict:
    now = utcnow()
    previous = ctx.previous("sensors") if ctx else None
    tides = ctx.current("tides") if ctx else None
    hilo = (tides or {}).get("hilo")
    app_id, api_key = os.environ.get("TTN_APP_ID"), os.environ.get("TTN_API_KEY")
    mock = os.environ.get("SENSORS_MOCK", "").lower() in ("1", "true", "yes")
    notes: list[str] = []

    if mock:
        stations = [_station(s, _mock_rows(s, i, now), None, _synthetic_tide, now) for i, s in enumerate(SENSORS)]
        notes.append("MOCK DATA: simulated readings for development, not real measurements.")
        source = "Mock data (SENSORS_MOCK=1)"
    elif app_id and api_key:
        prev = _previous_rows(previous, mock=False)
        seen = [st["last_seen"] for st in prev.values() if st.get("last_seen")]
        after = max([now - timedelta(days=SENSOR_RETENTION_DAYS)] +
                    [parse_iso(t) - timedelta(minutes=5) for t in seen])  # small overlap, deduped below
        uplinks = _ttn_uplinks(app_id, api_key, after)
        by_id = {s["id"]: s for s in SENSORS}
        new: dict[str, list[dict]] = {s["id"]: [] for s in SENSORS}
        unknown = set()
        for r in uplinks:
            dev = (r.get("end_device_ids") or {}).get("device_id")
            if dev not in by_id:
                unknown.add(dev)
                continue
            row = _parse_uplink(r, by_id[dev])
            if row:
                new[dev].append(row)
        if unknown:
            notes.append(f"Ignored uplinks from devices not in config.SENSORS: {', '.join(sorted(map(str, unknown)))}")
        stations = []
        for s in SENSORS:
            old = prev.get(s["id"], {})
            merged = {r["t"]: {"t": r["t"], "temp_c": r["temp_c"], "exposed": r.get("exposed")}
                      for r in old.get("series", [])}
            merged.update({r["t"]: r for r in new[s["id"]]})
            stations.append(_station(s, list(merged.values()), hilo, None, now, prev=old))
        source = f"The Things Network ({TTN_CLUSTER}), application {app_id}"
    else:
        return {"source": "The Things Network", "configured": False, "mock": False, "stations": [],
                "notes": ["Sensors not configured: set TTN_APP_ID and TTN_API_KEY, or SENSORS_MOCK=1."]}

    for st in stations:
        if st["status"] != "live":
            notes.append(f"{st['name']}: {st['status']}, last seen {st['last_seen'] or 'never'}")
    return {"source": source, "configured": True, "mock": mock, "units": {"temp": "C/F", "elevation": "ft MLLW"},
            "retention_days": SENSOR_RETENTION_DAYS, "qc_flags": {"1": "pass", "2": "not evaluated",
                                                                   "3": "suspect", "4": "fail"},
            "stations": stations, "notes": notes}
