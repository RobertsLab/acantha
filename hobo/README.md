# Archival HOBO loggers, Thorndyke Step 4

15-minute readings from the Onset MX2204 loggers that sat together in one research bag on
Step 4, written by `baseline/hobo_archive.py` on `main` from RobertsLab/10K-seed-Cgigas
(`output/baywater_temperature_20260922.csv`). The site shows daily summaries from `web/baseline/thorndyke_hobo.json`.

- `readings-YYYY.csv`: one row per logger per reading, by UTC year.
- `loggers.json`: serials, source file and commit, record span, field visits, bag elevation.

| Column | Meaning |
|---|---|
| `t` | Reading time, UTC (ISO 8601). The loggers export a fixed UTC-7 ("PDT") clock |
| `logger` | Logger serial number |
| `temp_c`, `temp_f` | Logger temperature |
| `exposed` | `true` if the predicted tide (NOAA Lofall 9445088) was below the bag (2.0 ft MLLW, estimated) |
| `phase` | `exposed`; `flood` for the first 3 h after the bag is covered (water off the flats, not bay water); else `water` |
| `tide_ft` | Predicted Lofall tide at `t`, ft MLLW |
| `qc` | IOOS QARTOD flag: 1 pass, 3 suspect, 4 fail |
| `qc_tests` | Tests that raised the flag, `;`-separated (gross_range, climatology, spike, handling, out_of_water) |

`handling` marks readings within 90 min of a logger download, when the bag may have been out of place;
`out_of_water` marks longer spans when the loggers were out of the bag.
