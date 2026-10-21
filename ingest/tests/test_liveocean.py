"""python3 -m unittest discover ingest/tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

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


if __name__ == "__main__":
    unittest.main()
