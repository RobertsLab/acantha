# acantha: Thorndyke Bay conditions portal

A map-based portal of near-real-time conditions for oyster growers in Thorndyke Bay (Hood Canal, WA):
tides and low-tide work windows, weather and marine alerts, rain, water quality, and shellfish status.
See [PLAN.md](PLAN.md) for the full roadmap.

This is the **Phase 1 MVP** (public data only). It is a static site with no server or database:

```
GitHub Actions (every ~20 min)
  └─ ingest/fetch.py  → pulls NOAA, NWS, WA DOH, NANOOS
       └─ writes web/data/*.json
            └─ GitHub Pages serves web/ (MapLibre map + uPlot charts)
```

## Run locally

Python 3.9+ with only the standard library, no installs needed.

```bash
python3 ingest/fetch.py
```

```bash
python3 serve.py
```

Then open http://localhost:8000. Re-run `fetch.py` to refresh the data. `--only tides forecast` fetches a subset.

## Layout

```
ingest/
  config.py          site location, station IDs, NWS grid/zone
  fetch.py           runs every source, writes web/data/*.json + meta.json
  sources/           one module per data source
    tides.py         NOAA CO-OPS predictions (Lofall 9445088)
    nws.py           NWS gridded forecast, alerts (PZZ135), surface observations
    rain.py          observed rain: Stage IV at the site + CoCoRaHS gauges (via IEM)
    sun.py           sunrise/sunset (computed)
    doh.py           WA DOH biotoxin status + commercial growing areas
    water.py         NANOOS/IOOS ERDDAP water temp, salinity, oxygen
    sensors.py       farm LoRaWAN temperature nodes via The Things Network
                     (SENSORS_MOCK=1 python3 ingest/fetch.py --only sensors for fake data)
web/
  index.html         map + "Today at Thorndyke" panel
  tides.html         low-tide work-window calendar with .ics export
  about.html         data sources and freshness
  js/, css/
.github/workflows/update.yml   scheduled fetch + Pages deploy
```

## Adding a data source

1. Create `ingest/sources/<name>.py` with a `fetch() -> dict` function that returns JSON-serializable data.
2. Register it in `SOURCES` in `ingest/fetch.py`.
3. Read it in the browser with `load("<name>")` from `web/js/common.js`.

A failing source never blocks the others. In CI the previously published file is reused, and the
page shows how old the data is.

## Deploy

1. Push to GitHub.
2. In **Settings → Pages**, set **Source: GitHub Actions**.
3. The workflow runs on every push to `main`, every ~20 minutes, and on demand (**Actions → Run workflow**).

GitHub turns off scheduled workflows in public repos after 60 days with no commits. Push a commit
or re-enable the workflow when that happens.

## Known gaps in the MVP

- **No real-time tide gauge in Hood Canal.** Tides are NOAA predictions only.
- **Observed rain is an estimate, not a gauge at the bay.** None of the nearby NWS stations report rain,
  so the closure watch uses the NCEP Stage IV radar + gauge analysis at the site (about 2 h behind real
  time; in the Northwest its hourly values are 6-hour totals spread evenly) plus NWS forecast QPF.
  Nearby CoCoRaHS volunteer gauges (daily, ~7 am) are shown as a check. An on-farm gauge is Phase 2.
- **The rain threshold is a placeholder** (1.0 in / 24 h). Each grower should set it to their growing
  area's DOH conditional-closure rule.
- **No current water-quality data near the bay.** As of Sept 2026 the ORCA Hansville and Dabob Bay
  buoys aren't reporting water temperature, salinity or DO. The UW NWEM ERDDAP that serves their depth
  profiles was also unreachable. The portal shows NOAA Port Townsend water temperature (34 km away)
  and picks up the buoys automatically once they report again. Contacts listed in the NANOOS metadata:
  UW APL, setht1@uw.edu. On-site sensors are Phase 2.
- DOH biotoxin zones are **recreational** closures. Commercial harvest follows DOH commercial sampling.

Advisory only. Official harvest closures come from the WA Department of Health.
