# Archival HOBO temperature plan

Goal: bring the 2024–2026 HOBO logger record from the Thorndyke outplant into the portal. It is the only
multi-year **in-situ** temperature record at the farm. The site's "normal" water temperature otherwise comes
from the LiveOcean model, and the farm's only other measurement is 7 days of LoRaWAN data.

## Status (2026-10-29)

Steps 1–5 are done:

- `baseline/hobo_archive.py` (standard library only) builds `web/baseline/thorndyke_hobo.json`.
- The dashboard has a **Bag temperature record** card, and the **Water** card shows a farm logger normal.
- The Data page has a method section (`about.html#hobo`).
- Tests are in `ingest/tests/test_hobo_archive.py`.

Still open:

- The 15-minute archive has been generated but **not yet pushed** to the `sensor-data` branch (§3).
- Step 6: the LiveOcean bias check and monthly QC bounds for the LoRaWAN sensors.
- Step 7: tell the SHIELD maintainers about their stale data.
- §6: where logger 22023395 was.

## 1. Sources

**Source of record:**
[`10K-seed-Cgigas/output/baywater_temperature_20260922.csv`](https://github.com/RobertsLab/10K-seed-Cgigas/blob/main/output/baywater_temperature_20260922.csv)
(`logger,DateTime,temp.C`, 15 min, ~133k rows). It covers loggers 22023410 and 22023411, 2024-10-30 → 2026-09-22.
The builder pins it by commit (`REF`).

- **The `Z` on `DateTime` is wrong.** The values are the loggers' "Date-Time (PDT)" clock, a fixed UTC−7
  (`CLOCK_UTC_OFFSET_H`). They match the `.xlsx` exports in `data/loggers/outplant/` exactly.
- **Field visits come from the `.xlsx` exports.** The CSV has no logger event log, so the "Host Connected" times
  were copied into `VISITS`.
- **Two things in the repo are not used.** The older `baywater_temperature_20250822.csv` holds 22023410 only. The
  22023406 export duplicates the same bag until 2025-08-11.
- **SHIELD's copy is stale.** [RobertsLab/SHIELD](https://github.com/RobertsLab/SHIELD) keeps only daily means
  (`public/data/archivalTemperatureData.json`, built 2026-06-20). They come from an older CSV with logger 22023395,
  a different location (below), and mix water and air.

## 2. What the data showed

- **Loggers.** 22023410 and 22023411 ran together in the Step 4 bag from 2024-10-30 to 2026-09-22 and agree within
  about 0.1 °C. 22023395 (2024-06-12 → 2026-06-06) reads about 1.3 °C
  warmer in winter and has much more scatter, so it **was not in that bag** and is left out.
- **Clock.** The exports say "Date-Time (PDT)". That is a fixed UTC−7 all year: a winter fit against Lofall tides is
  sharpest at −7 h, not −8.
- **Bag elevation ≈ 2.0 ft MLLW.** On the ebb, the switch from water to air temperature happens exactly when the
  predicted Lofall tide drops below 2 ft. CUDEM contours put the ground at Step 4 at about 0.8 ft, so the bag sits
  about a foot above it.
- **The flood is different.** For 2–3 h after the bag is covered again, it reads about 2.5 °C above the bay in
  summer and about 1 °C below in winter. That is water that just crossed the flats. Readings are split into
  `exposed`, `flood` (3 h after covering) and `water`. Only `water` feeds water temperature and normals.
- **Out of the bag 2025-08-20 → 21.** After that morning's visit the loggers read 29.6 °C at a 10 ft tide and 7.7 °C
  overnight. This span is hard-coded in `OUT_OF_WATER` and fails QC. Readings within 90 min of any download are
  flagged suspect and left out.
- **Results.** Monthly water normals run from 8.7 °C (Jan) to 15.4 °C (Aug). The bag peaked at 26.4 °C (79.5 °F) on
  2025-07-13 during a −2.0 ft low, and reached 24 °C or more on 8 low tides. The coldest reading was −4.5 °C at the
  Feb 2025 night lows.
- **Remaining noise.** Daily water min/max still catch some exposure edges, for example a few winter days near 3 °C.
  The UI uses daily means and monthly 10th–90th percentiles, not single-day extremes.

## 3. Outputs

- `web/baseline/thorndyke_hobo.json` (~32 KB): site and elevation, loggers, the source CSV pinned to a commit,
  field visits, daily rows (`date, water_mean, water_min, water_max, bag_max, bag_min, exposed_hours`), monthly
  normals, and heat events (low-tide windows peaking at 24 °C or more).
- `python3 baseline/hobo_archive.py --archive DIR` writes `DIR/hobo/readings-YYYY.csv` (~133k rows, ~7 MB),
  `loggers.json` and a README for the `sensor-data` branch. These live in `hobo/` rather than `readings/`, because
  `archive_sensors.py` rewrites the LoRaWAN `stations.json` on every run. To publish:

  ```bash
  git fetch origin sensor-data && git worktree add ../sd FETCH_HEAD -B sensor-data
  python3 baseline/hobo_archive.py --archive ../sd
  git -C ../sd add hobo && git -C ../sd commit -m "Add archival HOBO readings (Step 4 bag, 2024-26)" && git -C ../sd push origin sensor-data
  ```

## 4. Dashboard

Done:

- **Water card:** "Farm logger October normal: 53.1°F (52–55°F)" next to the LiveOcean normal, plus the current
  reading's difference from it.
- **Bag temperature record card:** this week's mean in earlier years; how many days the bag reached the grower's heat
  threshold (`heatF`), with peak and coldest; a full-record chart of daily water mean with bag max and min; links to
  the 15-minute data and the method.
- **Data page:** method, caveats and credit.

Not done: a map marker for Step 4's loggers. The card and the farm layout already cover it.

## 5. Steps

| # | Step | Status |
|---|---|---|
| 1 | Confirm layout, timezone, deployment, elevation | Done (from the data) |
| 2 | `baseline/hobo_archive.py` + tests; `_qc` gains `flat_line=False` | Done |
| 3 | `thorndyke_hobo.json`; 15-minute CSVs to `sensor-data` | JSON done; push pending |
| 4 | Water card farm normal; heat history | Done (on the record card) |
| 5 | Record card, chart, Data page | Done |
| 6 | LiveOcean bias vs. logger; monthly QC bounds for LoRaWAN (`CLIMATOLOGY` would flag the −4.5 °C lows) | Open |
| 7 | Tell SHIELD its Thorndyke series is stale and comes from 22023395, and offer the cleaned daily file | Open |

## 6. Questions

1. **Where was 22023395?** SHIELD labels it Thorndyke, but it was not in the Step 4 bag.
2. **The logger that is out now:** which serial, and is it back in the Step 4 bag? After the next download, add its
   file to `LOGGERS`, bump `REF` and re-run. Also check `OUT_OF_WATER` against any new visits.
