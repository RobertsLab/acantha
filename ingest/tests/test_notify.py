"""python3 -m unittest discover ingest/tests"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest import mock  # noqa: E402

from sources import notify  # noqa: E402
from sources.common import iso  # noqa: E402
from tests.test_briefing import DATA, Ctx  # noqa: E402

NOON = datetime(2026, 7, 15, 19, 0, tzinfo=timezone.utc)   # noon Pacific
NIGHT = datetime(2026, 7, 16, 7, 0, tzinfo=timezone.utc)   # midnight Pacific

SCA = {"event": "Small Craft Advisory", "headline": "Small Craft Advisory until Thu 5 AM",
       "onset": "2026-07-15T18:00:00Z", "ends": "2026-07-16T12:00:00Z", "severity": "Minor"}


def with_(**changes):
    return {**DATA, **changes}


class Conditions(unittest.TestCase):
    def test_keys(self):
        keys = set(notify.conditions(with_(alerts={"alerts": [SCA]}), NOON))
        self.assertIn("nws:Small Craft Advisory:2026-07-15T18:00:00Z", keys)
        self.assertIn("heat:Wed 1:00 PM", keys)  # -1.5 ft daylight low, 82°F forecast
        self.assertIn("gust:Wed", keys)          # 24 mph gust
        self.assertIn("doh:recreational_biotoxin_zone:Thorndyke Bay: Open", keys)
        self.assertFalse(any(k.startswith("rain:") for k in keys))

    def test_sensor_alerts(self):
        hot = with_(sensors={"stations": [
            {"name": "Bag 1", "status": "live", "last_seen": "2026-07-15T18:50:00Z",
             "latest": {"temp_f": 80.0, "exposed": True}},
            {"name": "Bag 2", "status": "offline", "last_seen": "2026-07-15T10:00:00Z", "latest": {}}]})
        keys = set(notify.conditions(hot, NOON))
        self.assertIn("sensorheat:Bag 1", keys)
        self.assertIn("offline:Bag 2", keys)
        mocked = {**hot, "sensors": {**hot["sensors"], "mock": True}}
        self.assertFalse(any(k.startswith(("sensorheat", "offline")) for k in notify.conditions(mocked, NOON)))


A = {"x": notify._alert("x", "x"), "u": notify._alert("u", "u", urgent=True)}


class Plan(unittest.TestCase):
    def test_first_run_is_baseline(self):
        send, state = notify.plan(A, None, NOON)
        self.assertEqual(send, [])
        self.assertEqual(state["notified"], ["u", "x"])

    def test_new_condition_sends_once(self):
        send, state = notify.plan(A, {"notified": ["u"]}, NOON)
        self.assertEqual(send, ["x"])
        state["notified"].append("x")
        self.assertEqual(notify.plan(A, state, NOON)[0], [])

    def test_quiet_hours_hold_non_urgent(self):
        send, state = notify.plan(A, {"notified": []}, NIGHT)
        self.assertEqual(send, ["u"])
        self.assertNotIn("x", state["notified"])  # waits for morning

    def test_rearms_after_clearing_but_respects_cooldown(self):
        _, state = notify.plan({}, {"notified": ["x"], "sent": {"x": iso(NOON)}}, NOON)
        self.assertEqual(state["notified"], [])
        self.assertEqual(notify.plan(A, state, NOON + timedelta(hours=1))[0], ["u"])  # x still cooling down
        self.assertEqual(notify.plan(A, state, NOON + timedelta(hours=20))[0], ["u", "x"])  # next morning


@mock.patch.object(notify, "utcnow", lambda: NOON)
class Fetch(unittest.TestCase):
    def prev(self):
        return {"notified": sorted(notify.conditions(DATA, NOON)), "sent": {}, "log": []}

    @mock.patch.dict(os.environ, {"NTFY_TOPIC": "test-topic"})
    @mock.patch.object(notify, "_publish")
    def test_sends_new_alert(self, publish):
        out = notify.fetch(Ctx(with_(alerts={"alerts": [SCA]}), self.prev()))
        publish.assert_called_once()
        self.assertEqual(publish.call_args[0][0], "test-topic")
        self.assertEqual(out["log"][0]["title"], "Small Craft Advisory")
        self.assertTrue(out["log"][0]["delivered"])

    @mock.patch.dict(os.environ, {"NTFY_TOPIC": "test-topic"})
    @mock.patch.object(notify, "_publish", side_effect=OSError("down"))
    def test_failed_send_retries_next_run(self, publish):
        out = notify.fetch(Ctx(with_(alerts={"alerts": [SCA]}), self.prev()))
        self.assertEqual(len(out["errors"]), 1)
        self.assertFalse(any(k.startswith("nws:") for k in out["notified"]))

    @mock.patch.dict(os.environ, {"NTFY_TOPIC": ""})
    @mock.patch.object(notify, "_publish")
    def test_logs_without_topic(self, publish):
        out = notify.fetch(Ctx(with_(alerts={"alerts": [SCA]}), self.prev()))
        publish.assert_not_called()
        self.assertFalse(out["log"][0]["delivered"])
        self.assertFalse(out["configured"])

    @mock.patch.dict(os.environ, {"NTFY_TOPIC": "test-topic"})
    @mock.patch.object(notify, "_publish")
    def test_missing_source_does_not_rearm(self, publish):
        prev = self.prev()
        out = notify.fetch(Ctx(with_(shellfish=None), prev))
        self.assertIn("doh:recreational_biotoxin_zone:Thorndyke Bay: Open", out["notified"])
        out = notify.fetch(Ctx(DATA, out))
        publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
