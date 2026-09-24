"""Sunrise/sunset times (NOAA solar position algorithm, ~1 minute accuracy)."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

from config import SITE, TIDE_DAYS
from sources.common import iso, utcnow


def _sun_times(d: date, lat: float, lon: float):
    """Return (sunrise, sunset) as UTC datetimes for calendar date d."""
    n = d.timetuple().tm_yday
    gamma = 2 * math.pi / 365 * (n - 1)
    eqtime = 229.18 * (
        0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma)
    )
    decl = (
        0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma)
    )
    phi = math.radians(lat)
    cos_ha = math.cos(math.radians(90.833)) / (math.cos(phi) * math.cos(decl)) - math.tan(phi) * math.tan(decl)
    ha = math.degrees(math.acos(max(-1.0, min(1.0, cos_ha))))
    midnight = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    rise = midnight + timedelta(minutes=720 - 4 * (lon + ha) - eqtime)
    sett = midnight + timedelta(minutes=720 - 4 * (lon - ha) - eqtime)
    return rise, sett


def fetch() -> dict:
    # Local dates for Pacific time: sunset in UTC falls on the next UTC day,
    # so compute per local date by anchoring on the local calendar date.
    today = (utcnow() - timedelta(hours=8)).date() - timedelta(days=1)
    days = []
    for i in range(TIDE_DAYS + 2):
        d = today + timedelta(days=i)
        rise, sett = _sun_times(d, SITE["lat"], SITE["lon"])
        days.append({"date": d.isoformat(), "sunrise": iso(rise), "sunset": iso(sett)})
    return {"source": "Computed (NOAA solar algorithm)", "days": days}
