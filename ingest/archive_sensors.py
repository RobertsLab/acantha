"""Append farm sensor readings to a permanent CSV archive.

Usage:
    python3 ingest/archive_sensors.py web/data/sensors.json ARCHIVE_DIR

sensors.json only holds the last SENSOR_RETENTION_DAYS, so after every fetch
the workflow runs this against a checkout of the `sensor-data` branch. Rows go
into ARCHIVE_DIR/readings/YYYY-MM.csv (UTC month), keyed by (device_id, t).
Readings still inside the 7-day window are rewritten on each run, so QC flags
that change later (the newest point is "not evaluated" until the next reading
arrives) end up final in the archive. A field that is missing from a newer
copy of a row keeps its archived value. Mock data is never archived.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

COLUMNS = ["t", "device_id", "temp_c", "temp_f", "exposed", "qc", "qc_tests", "battery_v", "rssi", "snr"]

README = """# Farm sensor archive

Every reading from the farm LoRaWAN sensors, written by the "Fetch data and deploy site"
workflow on `main` (`ingest/archive_sensors.py`). The site itself only keeps 7 days.

- `readings/YYYY-MM.csv`: one row per reading, by UTC month, sorted by time then device.
- `stations.json`: sensor metadata (name, position, probe elevation) from the latest run.
  Earlier versions are in this branch's git history.

| Column | Meaning |
|---|---|
| `t` | Time TTN received the uplink, UTC (ISO 8601) |
| `device_id` | TTN end device ID; see `stations.json` |
| `temp_c`, `temp_f` | Probe temperature |
| `exposed` | `true` if the predicted tide (NOAA Lofall) was below the probe, i.e. out of the water; empty if unknown |
| `qc` | IOOS QARTOD flag: 1 pass, 2 not evaluated, 3 suspect, 4 fail |
| `qc_tests` | Tests that raised the flag, `;`-separated (gross_range, climatology, spike, flat_line) |
| `battery_v`, `rssi`, `snr` | Node battery (V) and best gateway signal (dBm, dB) for that uplink; empty if not recorded |

Readings within the last 7 days may still be updated (QC is final once the next reading arrives).
"""


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ";".join(map(str, v))
    return str(v)


def archive(sensors_json: Path, out: Path) -> dict[str, int]:
    """Merge the readings in sensors_json into out/readings/*.csv. Returns rows written per month file."""
    data = json.loads(sensors_json.read_text())
    if data.get("mock") or not data.get("configured"):
        return {}
    by_month: dict[str, dict[tuple, dict]] = {}
    for st in data.get("stations", []):
        for r in st.get("series", []):
            row = {c: _cell(r.get(c)) for c in COLUMNS}
            row["device_id"] = st["id"]
            by_month.setdefault(r["t"][:7], {})[(row["device_id"], row["t"])] = row

    (out / "readings").mkdir(parents=True, exist_ok=True)
    written = {}
    for month, new in by_month.items():
        path = out / "readings" / f"{month}.csv"
        rows: dict[tuple, dict] = {}
        if path.exists():
            with path.open(newline="") as f:
                rows = {(r["device_id"], r["t"]): r for r in csv.DictReader(f)}
        for key, row in new.items():
            old = rows.get(key, {})
            rows[key] = {c: row[c] if row[c] != "" else old.get(c, "") for c in COLUMNS}
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
            w.writeheader()
            w.writerows(rows[k] for k in sorted(rows, key=lambda k: (k[1], k[0])))
        written[path.name] = len(rows)

    meta = [{k: st.get(k) for k in ("id", "name", "lat", "lon", "elevation_ft", "placement")}
            for st in data.get("stations", [])]
    (out / "stations.json").write_text(json.dumps(meta, indent=2) + "\n")
    (out / "README.md").write_text(README)
    return written


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    written = archive(Path(sys.argv[1]), Path(sys.argv[2]))
    if not written:
        print("No sensor readings to archive (mock data or sensors not configured).")
    for name, n in written.items():
        print(f"{name}: {n} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
