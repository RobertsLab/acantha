"""Shared helpers: HTTP, time parsing, unit conversion."""
from __future__ import annotations

import json
import math
import re
import urllib.request
from datetime import datetime, timedelta, timezone

from config import USER_AGENT


def get_json(url: str, timeout: int = 30, accept: str = "application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


_DUR = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?")


def parse_valid_time(s: str) -> tuple[datetime, int]:
    """Parse an NWS validTime like '2026-09-24T18:00:00+00:00/PT6H' -> (start, hours)."""
    start, dur = s.split("/")
    m = _DUR.fullmatch(dur)
    days, hours, minutes = (int(g) if g else 0 for g in m.groups())
    total = days * 24 + hours + (1 if minutes else 0)
    return parse_iso(start), max(total, 1)


def distance_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def c_to_f(c):
    return None if c is None else round(c * 9 / 5 + 32, 1)


def kmh_to_mph(v):
    return None if v is None else round(v * 0.621371, 1)


def mm_to_in(v):
    return None if v is None else round(v / 25.4, 3)


def hour_floor(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


__all__ = [
    "get_json", "utcnow", "iso", "parse_iso", "parse_valid_time", "distance_km",
    "c_to_f", "kmh_to_mph", "mm_to_in", "hour_floor", "timedelta", "timezone",
]
