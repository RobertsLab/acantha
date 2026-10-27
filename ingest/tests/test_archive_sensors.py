"""python3 -m unittest discover ingest/tests"""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from archive_sensors import archive  # noqa: E402


def sensors(series, mock=False):
    return {"configured": True, "mock": mock, "stations": [
        {"id": "little-dragon-01", "name": "Test sensor", "lat": 47.8, "lon": -122.7,
         "elevation_ft": 8.0, "placement": "test", "series": series}]}


def rows(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.src = self.tmp / "sensors.json"
        self.out = self.tmp / "archive"

    def run_with(self, series, mock=False):
        self.src.write_text(json.dumps(sensors(series, mock)))
        return archive(self.src, self.out)

    def test_appends_updates_and_keeps_old_rows(self):
        self.run_with([
            {"t": "2026-10-27T03:30:52Z", "temp_c": 17.7, "temp_f": 63.9, "exposed": True, "qc": 1,
             "battery_v": 3.618, "rssi": -18, "snr": 13.5},
            {"t": "2026-10-27T03:50:51Z", "temp_c": 17.6, "temp_f": 63.7, "qc": 2, "battery_v": 3.618},
        ])
        # Next run: the first reading has aged out of the window, the second has final QC
        # but no radio fields, and a new one arrived.
        written = self.run_with([
            {"t": "2026-10-27T03:50:51Z", "temp_c": 17.6, "temp_f": 63.7, "qc": 3, "qc_tests": ["spike"]},
            {"t": "2026-10-27T04:10:51Z", "temp_c": 17.6, "temp_f": 63.7, "qc": 2},
        ])
        self.assertEqual(written, {"2026-10.csv": 3})
        r = rows(self.out / "readings" / "2026-10.csv")
        self.assertEqual([x["t"] for x in r], ["2026-10-27T03:30:52Z", "2026-10-27T03:50:51Z",
                                               "2026-10-27T04:10:51Z"])
        self.assertEqual((r[0]["exposed"], r[0]["rssi"]), ("true", "-18"))
        self.assertEqual((r[1]["qc"], r[1]["qc_tests"], r[1]["battery_v"]), ("3", "spike", "3.618"))
        self.assertEqual(r[2]["exposed"], "")
        meta = json.loads((self.out / "stations.json").read_text())
        self.assertEqual(meta[0]["id"], "little-dragon-01")

    def test_splits_by_month(self):
        self.run_with([{"t": "2026-10-31T23:50:00Z", "temp_c": 10.0, "qc": 1},
                       {"t": "2026-11-01T00:10:00Z", "temp_c": 10.1, "qc": 2}])
        self.assertEqual(sorted(p.name for p in (self.out / "readings").iterdir()),
                         ["2026-10.csv", "2026-11.csv"])

    def test_skips_mock_data(self):
        self.assertEqual(self.run_with([{"t": "2026-10-27T03:30:52Z", "temp_c": 17.7, "qc": 1}], mock=True), {})
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
