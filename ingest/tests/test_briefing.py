"""python3 -m unittest discover ingest/tests"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest import mock  # noqa: E402

from sources import briefing  # noqa: E402
from sources.common import iso  # noqa: E402

NOW = datetime(2026, 7, 15, 18, 0, tzinfo=timezone.utc)  # 11 am Pacific

DATA = {
    "tides": {"hilo": [
        {"t": "2026-07-15T20:00:00Z", "v": -1.5, "type": "L"},  # 1 pm, daylight, below 0 ft
        {"t": "2026-07-16T08:00:00Z", "v": -2.5, "type": "L"},  # 1 am, dark
        {"t": "2026-07-16T02:00:00Z", "v": 9.0, "type": "H"},
    ]},
    "sun": {"days": [{"date": "2026-07-15", "sunrise": "2026-07-15T12:30:00Z", "sunset": "2026-07-16T04:00:00Z"}]},
    "forecast": {
        "hourly": [{"t": "2026-07-15T20:00:00Z", "air_temp_f": 82.0, "wind_mph": 5, "gust_mph": 24,
                    "wind_dir_deg": 315, "sky_pct": 10, "qpf_in": 0.0},
                   {"t": "2026-07-16T08:00:00Z", "air_temp_f": 58.0, "wind_mph": 2, "gust_mph": 4,
                    "wind_dir_deg": 180, "sky_pct": 20, "qpf_in": 0.0}],
        "periods": [{"name": "Today", "shortForecast": "Sunny", "temperature": 84,
                     "windDirection": "NW", "windSpeed": "5 mph"}],
    },
    "alerts": {"alerts": []},
    "rain": {"totals": {"h24": 0.0}},
    "shellfish": {"site_zone": {"name": "Thorndyke Bay", "status": "Open"},
                  "site_growing_area": {"name": "Hood Canal #1", "classification": "Approved"}},
    "water": {"stations": []},
    "liveocean": {"cells": []},
    "sensors": {"stations": [{"name": "Bag 1", "status": "live", "last_seen": "2026-07-15T17:50:00Z",
                              "latest": {"temp_f": 71.3, "exposed": False}}]},
}


class Ctx:
    def __init__(self, data, previous=None):
        self.data, self.prev = data, previous

    def current(self, name):
        return self.data.get(name)

    def previous(self, name):
        return self.prev


class Digest(unittest.TestCase):
    def test_threshold_checks(self):
        d = briefing.digest(DATA, NOW)
        day, night = d["low_tides_next_72h"]
        self.assertEqual(day["time"], "Wed 1:00 PM")
        self.assertTrue(day["workable_daylight_low"])
        self.assertTrue(day["heat_exposure"])
        self.assertFalse(night["daylight"])
        self.assertFalse(night["workable_daylight_low"])
        self.assertTrue(d["max_gust_next_24h"]["at_or_above_threshold"])
        self.assertEqual(d["max_gust_next_24h"]["from"], "NW")
        self.assertFalse(d["rain_in"]["at_or_above_threshold"])
        self.assertTrue(d["vibrio_season"])

    def test_missing_sources(self):
        d = briefing.digest({}, NOW)
        self.assertEqual(d["low_tides_next_72h"], [])
        self.assertIsNone(d["rain_in"]["watch_total"])
        self.assertNotIn("farm_sensors", d)

    def test_hash_ignores_sensor_noise(self):
        a = briefing.digest(DATA, NOW)
        warmer = {**DATA, "sensors": {"stations": [{**DATA["sensors"]["stations"][0],
                                                    "latest": {"temp_f": 72.1, "exposed": False}}]}}
        b = briefing.digest(warmer, NOW)
        self.assertEqual(briefing._hash(briefing._hash_view(a)), briefing._hash(briefing._hash_view(b)))


WRITTEN = {"headline": "Workable low at 1 pm, hot", "points": ["One."], "model": "claude-opus-5-5"}


@mock.patch.object(briefing, "utcnow", lambda: NOW)
@mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"})
class Fetch(unittest.TestCase):
    def previous(self, minutes_ago, data=DATA):
        d = briefing.digest(data, NOW)
        return {"headline": "old", "points": [], "configured": True,
                "generated_at": iso(NOW - timedelta(minutes=minutes_ago)),
                "inputs_hash": briefing._hash(briefing._hash_view(d)), "urgent_hash": briefing._urgent(d)}

    @mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""})
    def test_no_key(self):
        out = briefing.fetch(Ctx(DATA))
        self.assertFalse(out["configured"])

    @mock.patch.object(briefing, "_write", return_value=dict(WRITTEN))
    def test_writes_when_no_previous(self, write):
        out = briefing.fetch(Ctx(DATA))
        write.assert_called_once()
        self.assertEqual(out["headline"], WRITTEN["headline"])
        self.assertFalse(out["reused"])
        self.assertIn("digest", out)

    @mock.patch.object(briefing, "_write")
    def test_reuses_when_unchanged(self, write):
        out = briefing.fetch(Ctx(DATA, self.previous(300)))
        write.assert_not_called()
        self.assertTrue(out["reused"])

    @mock.patch.object(briefing, "_write")
    def test_reuses_recent_when_only_detail_changed(self, write):
        prev = {**self.previous(20), "inputs_hash": "stale"}
        self.assertTrue(briefing.fetch(Ctx(DATA, prev))["reused"])
        write.assert_not_called()

    @mock.patch.object(briefing, "_write", return_value=dict(WRITTEN))
    def test_rewrites_recent_when_alert_arrives(self, write):
        prev = self.previous(20)
        alerted = {**DATA, "alerts": {"alerts": [{"event": "Small Craft Advisory", "headline": "SCA",
                                                  "ends": "2026-07-16T05:00:00Z"}]}}
        self.assertFalse(briefing.fetch(Ctx(alerted, prev))["reused"])
        write.assert_called_once()

    @mock.patch.object(briefing, "_write", return_value=dict(WRITTEN))
    def test_rewrites_old_when_changed(self, write):
        prev = {**self.previous(120), "inputs_hash": "stale"}
        self.assertFalse(briefing.fetch(Ctx(DATA, prev))["reused"])
        write.assert_called_once()


if __name__ == "__main__":
    unittest.main()
