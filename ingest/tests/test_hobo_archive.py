"""python3 -m unittest discover ingest/tests"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "baseline"))

import hobo_archive as H  # noqa: E402

UTC = timezone.utc


class ReadCsvTest(unittest.TestCase):
    def test_z_clock_is_utc_minus_7_and_na_rows_dropped(self):
        text = ("logger,DateTime,temp.C\n"
                "22023411,2025-01-15T12:15:00Z,8.6\n"
                "22023410,2025-01-15T12:00:00Z,8.5\n"   # winter: still UTC-7, not PST
                "22023410,NA,9.0\n"
                "22023410,2025-01-15T12:30:00Z,NA\n")
        out = H.read_csv(text)
        self.assertEqual(out["22023410"], [(datetime(2025, 1, 15, 19, 0, tzinfo=UTC), 8.5)])
        self.assertEqual(out["22023411"], [(datetime(2025, 1, 15, 19, 15, tzinfo=UTC), 8.6)])


class PhaseTest(unittest.TestCase):
    def setUp(self):
        t0 = H.DEPLOYED
        # Tide falls through the bag, then rises back over it.
        self.tide = lambda t: -3.0 + abs((t - t0).total_seconds() / 3600 - 6) * 1.5
        self.times = [t0 + timedelta(minutes=15 * i) for i in range(4 * 16)]

    def series(self, visits=()):
        return H.logger_series("1", [(t, 10.0) for t in self.times], list(visits), self.tide)

    def test_exposed_then_flood_then_water(self):
        rows = self.series()
        phase = {r["t"]: r["phase"] for r in rows}
        tide = {r["t"]: r["tide_ft"] for r in rows}
        exposed = [t for t in self.times if phase[t] == "exposed"]
        self.assertTrue(exposed and all(tide[t] < H.ELEVATION_FT for t in exposed))
        covered = max(exposed) + timedelta(minutes=15)
        self.assertEqual(phase[covered], "flood")
        self.assertEqual(phase[covered + timedelta(minutes=H.FLOOD_SETTLE_MIN - 15)], "flood")
        self.assertEqual(phase[covered + timedelta(minutes=H.FLOOD_SETTLE_MIN)], "water")
        self.assertEqual(phase[self.times[0]], "water")   # bag starts submerged at deployment

    def test_handling_window_is_suspect_and_left_out_of_the_bag_series(self):
        visit = self.times[10]
        rows = self.series([visit])
        flagged = {r["t"] for r in rows if "handling" in r.get("qc_tests", [])}
        self.assertIn(visit, flagged)
        self.assertNotIn(visit + timedelta(minutes=H.HANDLING_MIN + 15), flagged)
        self.assertFalse(flagged & {r["t"] for r in H.combine({"1": rows})})

    def test_daily_water_columns_skip_exposed_and_flood(self):
        rows = H.logger_series("1", [(t, 20.0 if self.tide(t) < H.ELEVATION_FT else 10.0) for t in self.times], [], self.tide)
        for _, w_mean, w_min, w_max, bag_max, bag_min, hours in H.daily(H.combine({"1": rows})):
            if w_mean is not None:
                self.assertEqual((w_mean, w_min, w_max), (10.0, 10.0, 10.0))
            self.assertEqual(bag_max, 20.0)


if __name__ == "__main__":
    unittest.main()
