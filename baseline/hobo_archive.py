"""Archival HOBO temperature record from the Thorndyke outplant bags (Step 4).

Usage:
    python3 baseline/hobo_archive.py [--archive DIR]

Reads the lab's combined logger CSV (RobertsLab/10K-seed-Cgigas,
output/baywater_temperature_20260922.csv, pinned to a commit): the two Onset
MX2204 loggers that sat together in one research bag on Step 4. Standard library only.

- The CSV's DateTime ends in "Z" but is the loggers' "Date-Time (PDT)" export
  clock: a fixed UTC-7 offset all year. A fit against Lofall tides in winter
  confirms it is neither UTC nor local clock time.
- Each reading gets a phase from the predicted Lofall tide: "exposed" while the
  tide is below the bag, "flood" for FLOOD_SETTLE_MIN after it is covered again,
  else "water". ELEVATION_FT was fitted from the loggers (the ebb-side air/water
  split is sharp there) and agrees with the CUDEM contours (ground ~0.8 ft) plus
  bag height. On the flood the bag sits in water that crossed the flats: ~2.5 C
  warmer than the bay in summer and ~1 C colder in winter for 2-3 h, so only
  "water" readings feed the water-temperature summaries and normals.
- QC reuses the farm-sensor QARTOD tests, without flat-line (HOBOs in still water
  repeat values for hours). Readings within HANDLING_MIN of a field visit (the
  loggers' "Host Connected" events, copied into VISITS from the .xlsx exports in
  data/loggers/outplant/) are flagged suspect: the bag may have been out.
  OUT_OF_WATER lists longer spans when the loggers were out of the bag (found by
  screening high-tide readings against the week's water temperature); those fail.

Writes web/baseline/thorndyke_hobo.json (daily summary, monthly normals, heat
events). With --archive, also writes the 15-minute readings to DIR/hobo/ for the
sensor-data branch. Re-run after each logger download, updating CSV_PATH, REF
and VISITS.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import io
import json
import math
import statistics
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))

from config import TIDE_STATION, USER_AGENT  # noqa: E402
from sources.common import c_to_f, get_json, iso, utcnow  # noqa: E402
from sources.sensors import _qc  # noqa: E402

REPO = "RobertsLab/10K-seed-Cgigas"
REF = "628dc4b4657a458781593e02b38e145dc4f6292c"   # main on 2026-10-29
CSV_PATH = "output/baywater_temperature_20260922.csv"
CLOCK_UTC_OFFSET_H = -7
MODEL = "Onset MX2204"
SITE = {"name": "Step 4 research bags", "lat": 47.80825, "lon": -122.73877}
ELEVATION_FT = 2.0                      # bag height, ft MLLW (fitted; see docstring)
DEPLOYED = datetime(2024, 10, 31, 9, tzinfo=timezone.utc)   # in the water by 02:00 PDT Oct 31
HANDLING_MIN = 90
# Field visits (UTC): logger "Host Connected" events from the .xlsx exports.
VISITS = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in (
    "2025-08-11T19:30", "2025-08-11T20:05", "2025-08-20T16:23", "2025-11-05T04:20",
    "2026-06-06T21:36", "2026-06-06T23:31", "2026-08-27T16:40", "2026-09-22T15:43")]
# Loggers out of the bag after the 2025-08-20 visit: 29.6 C at a 10 ft tide, 7.7 C overnight.
OUT_OF_WATER = [(datetime(2025, 8, 20, 16, tzinfo=timezone.utc), datetime(2025, 8, 22, 4, tzinfo=timezone.utc))]
FLOOD_SETTLE_MIN = 180
HEAT_EVENT_C = 24.0                     # low-tide windows peaking at or above this are listed
TZ = ZoneInfo("America/Los_Angeles")
OUT = ROOT / "web" / "baseline" / "thorndyke_hobo.json"


# ---------- source CSV ----------

def read_csv(text: str) -> dict[str, list[tuple[datetime, float]]]:
    """Readings per logger serial from `logger,DateTime,temp.C`; rows with NA time or value are dropped."""
    out = defaultdict(list)
    for r in csv.DictReader(io.StringIO(text)):
        try:
            clock = datetime.fromisoformat(r["DateTime"].rstrip("Z"))
            v = float(r["temp.C"])
        except (TypeError, ValueError):
            continue
        if math.isfinite(v):
            out[r["logger"]].append(((clock - timedelta(hours=CLOCK_UTC_OFFSET_H)).replace(tzinfo=timezone.utc), v))
    return {k: sorted(v) for k, v in out.items()}


def _download(path: str, cache: Path) -> bytes:
    f = cache / REF[:12] / Path(path).name
    if not f.exists():
        url = f"https://raw.githubusercontent.com/{REPO}/{REF}/{path}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(body)
    return f.read_bytes()


# ---------- tides ----------

def lofall_hilo(start: datetime, end: datetime) -> list[tuple[datetime, float]]:
    out = []
    for year in range(start.year, end.year + 1):
        url = ("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=predictions"
               f"&station={TIDE_STATION['id']}&begin_date={year}0101&end_date={year}1231&datum=MLLW"
               "&units=english&time_zone=gmt&format=json&interval=hilo&application=acantha")
        for p in get_json(url, timeout=60)["predictions"]:
            t = datetime.strptime(p["t"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            out.append((t, float(p["v"])))
    return out


class Tide:
    """Cosine interpolation between high/low predictions (as sensors._tide_at), with bisect lookup."""

    def __init__(self, hilo):
        self.hilo, self.t = hilo, [t for t, _ in hilo]

    def __call__(self, t: datetime) -> float | None:
        i = bisect.bisect_right(self.t, t)
        if i == 0 or i >= len(self.t):
            return None
        (ta, va), (tb, vb) = self.hilo[i - 1], self.hilo[i]
        frac = (t - ta) / (tb - ta)
        return va + (vb - va) * (1 - math.cos(math.pi * frac)) / 2


# ---------- processing ----------

def _flag(r: dict, level: int, test: str) -> None:
    r["qc"] = max(r["qc"], level)
    r.setdefault("qc_tests", []).append(test)


def logger_series(serial: str, readings, visits: list[datetime], tide) -> list[dict]:
    """Rows from DEPLOYED on, with QC, handling flags, tide height and tide phase."""
    series = [{"t": t, "temp_c": v} for t, v in readings if t >= DEPLOYED]
    _qc(series, flat_line=False)
    window = timedelta(minutes=HANDLING_MIN)
    settle = timedelta(minutes=FLOOD_SETTLE_MIN)
    vt = sorted(visits)
    covered_at = None
    for r in series:
        i = bisect.bisect_left(vt, r["t"] - window)
        if i < len(vt) and vt[i] <= r["t"] + window:
            _flag(r, 3, "handling")
        if any(a <= r["t"] < b for a, b in OUT_OF_WATER):
            _flag(r, 4, "out_of_water")
        h = tide(r["t"])
        r["tide_ft"] = None if h is None else round(h, 2)
        r["exposed"] = None if h is None else h < ELEVATION_FT
        if h is None:
            r["phase"] = None
        elif h < ELEVATION_FT:
            r["phase"], covered_at = "exposed", None
        else:
            if covered_at is None and series[0] is not r:
                covered_at = r["t"]
            r["phase"] = "flood" if covered_at and r["t"] - covered_at < settle else "water"
        r["logger"] = serial
    if series and series[-1]["qc"] == 2:
        series[-1]["qc"] = 1  # the record is closed; no newer reading is coming
    return series


def combine(per_logger: dict[str, list[dict]]) -> list[dict]:
    """One bag series: mean of the loggers with usable readings (qc 1-3, not handling) at each time."""
    # A logger only reaches the "covered" state after its first exposure; before that, every
    # reading counts as water, which is right for the deployment start (bag already submerged).
    by_t = defaultdict(list)
    for rows in per_logger.values():
        for r in rows:
            if r["qc"] < 4 and "handling" not in r.get("qc_tests", []):
                by_t[r["t"]].append(r)
    out = []
    for t in sorted(by_t):
        rs = by_t[t]
        out.append({"t": t, "temp_c": statistics.fmean(r["temp_c"] for r in rs), "phase": rs[0]["phase"],
                    "tide_ft": rs[0]["tide_ft"], "n": len(rs)})
    return out


def _r1(v):
    return None if v is None else round(v, 1)


def _pct(vals, q):
    s = sorted(vals)
    k = (len(s) - 1) * q
    lo = math.floor(k)
    return s[lo] + (s[min(lo + 1, len(s) - 1)] - s[lo]) * (k - lo)


def daily(bag: list[dict]) -> list[list]:
    """[date, water mean/min/max, bag max/min (any phase), hours exposed] per local day."""
    days = defaultdict(lambda: {"w": [], "all": [], "x": 0})
    for r in bag:
        if r["phase"] is None:
            continue
        d = days[r["t"].astimezone(TZ).date().isoformat()]
        d["all"].append(r["temp_c"])
        if r["phase"] == "water":
            d["w"].append(r["temp_c"])
        elif r["phase"] == "exposed":
            d["x"] += 1
    rows = []
    for d in sorted(days):
        w, a = days[d]["w"], days[d]["all"]
        rows.append([d, _r1(statistics.fmean(w)) if w else None, _r1(min(w)) if w else None,
                     _r1(max(w)) if w else None, _r1(max(a)), _r1(min(a)), days[d]["x"] / 4])
    return rows


def monthly(bag: list[dict]) -> list[dict]:
    by = defaultdict(list)
    years = defaultdict(set)
    for r in bag:
        if r["phase"] == "water":
            loc = r["t"].astimezone(TZ)
            by[loc.month].append(r["temp_c"])
            years[loc.month].add(loc.year)
    return [{"month": m, "mean_c": _r1(statistics.fmean(v)), "p10_c": _r1(_pct(v, 0.1)),
             "p90_c": _r1(_pct(v, 0.9)), "years": sorted(years[m]), "days": len(v) // 96}
            for m, v in sorted(by.items())]


def heat_events(bag: list[dict]) -> list[dict]:
    """Low-tide windows (exposed plus the flood that follows) that peak at or above HEAT_EVENT_C."""
    events, run = [], []

    def close():
        if run:
            peak = max(run, key=lambda r: r["temp_c"])
            if peak["temp_c"] >= HEAT_EVENT_C:
                lows = [r["tide_ft"] for r in run if r["tide_ft"] is not None]
                events.append({"start": iso(run[0]["t"]), "end": iso(run[-1]["t"] + timedelta(minutes=15)),
                               "peak_c": _r1(peak["temp_c"]), "peak_t": iso(peak["t"]),
                               "hours_over": sum(r["temp_c"] >= HEAT_EVENT_C for r in run) / 4,
                               "low_ft": _r1(min(lows)) if lows else None})
        run.clear()

    for r in bag:
        low = r["phase"] in ("exposed", "flood")
        if low and (not run or r["t"] - run[-1]["t"] <= timedelta(minutes=15)):
            run.append(r)
        else:
            close()
            if low:
                run.append(r)
    close()
    return events


# ---------- output ----------

ARCHIVE_COLUMNS = ["t", "logger", "temp_c", "temp_f", "exposed", "phase", "tide_ft", "qc", "qc_tests"]
ARCHIVE_README = f"""# Archival HOBO loggers, Thorndyke Step 4

15-minute readings from the Onset MX2204 loggers that sat together in one research bag on
Step 4, written by `baseline/hobo_archive.py` on `main` from {REPO}
(`{CSV_PATH}`). The site shows daily summaries from `web/baseline/thorndyke_hobo.json`.

- `readings-YYYY.csv`: one row per logger per reading, by UTC year.
- `loggers.json`: serials, source file and commit, record span, field visits, bag elevation.

| Column | Meaning |
|---|---|
| `t` | Reading time, UTC (ISO 8601). The loggers export a fixed UTC-7 ("PDT") clock |
| `logger` | Logger serial number |
| `temp_c`, `temp_f` | Logger temperature |
| `exposed` | `true` if the predicted tide (NOAA Lofall {TIDE_STATION['id']}) was below the bag ({ELEVATION_FT} ft MLLW, estimated) |
| `phase` | `exposed`; `flood` for the first {FLOOD_SETTLE_MIN // 60} h after the bag is covered (water off the flats, not bay water); else `water` |
| `tide_ft` | Predicted Lofall tide at `t`, ft MLLW |
| `qc` | IOOS QARTOD flag: 1 pass, 3 suspect, 4 fail |
| `qc_tests` | Tests that raised the flag, `;`-separated (gross_range, climatology, spike, handling, out_of_water) |

`handling` marks readings within {HANDLING_MIN} min of a logger download, when the bag may have been out of place;
`out_of_water` marks longer spans when the loggers were out of the bag.
"""


def write_archive(out: Path, per_logger: dict[str, list[dict]], meta: dict) -> dict[str, int]:
    d = out / "hobo"
    d.mkdir(parents=True, exist_ok=True)
    by_year = defaultdict(list)
    for rows in per_logger.values():
        for r in rows:
            by_year[r["t"].year].append(r)
    written = {}
    for year, rows in sorted(by_year.items()):
        rows.sort(key=lambda r: (r["t"], r["logger"]))
        path = d / f"readings-{year}.csv"
        with path.open("w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(ARCHIVE_COLUMNS)
            for r in rows:
                w.writerow([iso(r["t"]), r["logger"], round(r["temp_c"], 3), c_to_f(r["temp_c"]),
                            "" if r["exposed"] is None else str(r["exposed"]).lower(), r["phase"] or "",
                            "" if r["tide_ft"] is None else r["tide_ft"], r["qc"],
                            ";".join(r.get("qc_tests", []))])
        written[path.name] = len(rows)
    (d / "loggers.json").write_text(json.dumps(meta, indent=2) + "\n")
    (d / "README.md").write_text(ARCHIVE_README)
    return written


def build(cache: Path) -> tuple[dict, dict[str, list[dict]]]:
    print(f"Reading {CSV_PATH}…", file=sys.stderr)
    parsed = read_csv(_download(CSV_PATH, cache).decode())
    visits = sorted(VISITS)
    start = min(p[0][0] for p in parsed.values())
    end = max(p[-1][0] for p in parsed.values())
    print("Fetching Lofall tide predictions…", file=sys.stderr)
    tide = Tide(lofall_hilo(start, end))
    per_logger = {s: logger_series(s, p, visits, tide) for s, p in sorted(parsed.items())}
    bag = combine(per_logger)

    loggers = []
    for serial, rows in per_logger.items():
        loggers.append({"serial": serial, "model": MODEL,
                        "start": iso(rows[0]["t"]), "end": iso(rows[-1]["t"]), "readings": len(rows),
                        "flagged": sum(r["qc"] >= 3 for r in rows)})
    meta = {"site": {**SITE, "elevation_ft": ELEVATION_FT, "elevation_datum": "MLLW",
                     "elevation_note": "Estimated: fitted from the winter air/water split against "
                                       "Lofall tide predictions; CUDEM puts the ground at ~0.8 ft."},
            "repo": REPO, "ref": REF, "source": f"https://github.com/{REPO}/blob/{REF}/{CSV_PATH}",
            "deployed": iso(DEPLOYED),
            "visits": [iso(t) for t in visits if t >= DEPLOYED],
            "out_of_water": [[iso(a), iso(b)] for a, b in OUT_OF_WATER],
            "flood_settle_min": FLOOD_SETTLE_MIN, "loggers": loggers}
    result = {
        "generated": iso(utcnow()),
        "description": "Temperature inside an oyster bag on Step 4, from HOBO loggers at 15-minute intervals. "
                       "The bag is intertidal. Water columns use only readings taken while it was well covered "
                       "(not exposed, and past the first hours of the flood); bag columns use every reading.",
        **meta,
        "units": "C",
        "daily_columns": ["date", "water_mean", "water_min", "water_max", "bag_max", "bag_min", "exposed_hours"],
        "daily": daily(bag),
        "monthly": monthly(bag),
        "heat_event_c": HEAT_EVENT_C,
        "heat_events": heat_events(bag),
    }
    return result, per_logger


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--archive", type=Path, help="also write 15-minute CSVs to DIR/hobo/ (sensor-data branch)")
    ap.add_argument("--cache", type=Path, default=ROOT / "baseline" / ".cache" / "hobo")
    a = ap.parse_args()
    result, per_logger = build(a.cache)
    a.out.write_text(json.dumps(result, separators=(",", ":")) + "\n")
    print(f"Wrote {a.out} ({a.out.stat().st_size // 1024} KB): {len(result['daily'])} days, "
          f"{len(result['heat_events'])} heat events", file=sys.stderr)
    if a.archive:
        meta = {k: result[k] for k in ("site", "repo", "ref", "source", "deployed", "visits", "out_of_water",
                                       "flood_settle_min", "loggers")}
        for name, n in write_archive(a.archive, per_logger, meta).items():
            print(f"{name}: {n} rows", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
