"""python3 -m unittest discover ingest/tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest import mock  # noqa: E402

from sources import liveocean  # noqa: E402
from sources.liveocean import parse_ascii  # noqa: E402

# Trimmed from a real eds.ioos.us response (variables come back in server order).
SAMPLE = """Dataset {
    Float64 lat_rho[eta_rho = 1][xi_rho = 1];
    Float64 time_run[time = 3];
    Float32 temp[time = 3][eta_rho = 1][xi_rho = 1];
} ioos/nanoos/liveocean/NANOOS_Live_Ocean_best.ncd;
---------------------------------------------
lat_rho[1][1]
[0], 47.804108093420226

time_run[3]
696.0, 720.0, 720.0

temp[3][1][1]
[0][0], 12.236139
[1][0], 1.0E20
[2][0], NaN
"""


class ParseAscii(unittest.TestCase):
    def test_parse(self):
        d = parse_ascii(SAMPLE)
        self.assertEqual(d["lat_rho"], [47.804108093420226])
        self.assertEqual(d["time_run"], [696.0, 720.0, 720.0])
        self.assertEqual(d["temp"], [12.236139, None, None])

    def test_2d_rows(self):
        d = parse_ascii("x\n" + "-" * 45 + "\nmask_rho[2][3]\n[0], 0.0, 1.0, 1.0\n[1], 1.0, 1.0, 0.0\n")
        self.assertEqual(d["mask_rho"], [0.0, 1.0, 1.0, 1.0, 1.0, 0.0])


class MissingTime(unittest.TestCase):
    """A fill value in the time axis must be skipped, not crash or shift rows."""

    DAS = ('Attributes {\n    time {\n        String units "hours since 2026-10-01 00:00:00";\n    }\n'
           '    time_run {\n        String units "hours since 2026-10-01 00:00:00";\n    }\n}')

    def fake_ascii(self, base, constraint):
        if constraint.startswith("time_run"):
            return {"time_run": [1.0]}
        if constraint.startswith("time"):
            return {"time": [0.0, None, 2.0]}
        return {"temp": [10.0, 11.0, 12.0], "salt": [28.0, 28.1, 28.2], "zeta": [0.1, 0.2, 0.3],
                "lat_rho": [47.8041], "lon_rho": [-122.7357], "mask_rho": [1.0], "h": [21.8]}

    def test_skips_missing_time(self):
        cells = [{"id": "thorndyke", "name": "t", "eta": 0, "xi": 0, "lat": 47.8041, "lon": -122.7357}]
        texts = {"base.dds": "Float64 time[time = 3];", "base.das": self.DAS}
        with mock.patch.object(liveocean, "get_text", lambda u: texts[u]), \
                mock.patch.object(liveocean, "_ascii", self.fake_ascii), \
                mock.patch.object(liveocean, "LIVEOCEAN_CELLS", cells):
            out = liveocean._fetch_from("base", None)
        series = out["cells"][0]["series"]
        self.assertEqual([r["t"] for r in series], ["2026-10-01T00:00:00Z", "2026-10-01T02:00:00Z"])
        self.assertEqual([r["temp_c"] for r in series], [10.0, 12.0])
        self.assertEqual([r["kind"] for r in series], ["nowcast", "forecast"])
        self.assertEqual(out["forecast_end"], "2026-10-01T02:00:00Z")


if __name__ == "__main__":
    unittest.main()
