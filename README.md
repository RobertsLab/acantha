# Farm sensor archive

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
