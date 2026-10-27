# LiveOcean integration plan

Goal: add the UW LiveOcean model (nowcast and ~2–3 day forecast) for the water at Thorndyke Bay,
filling the gap left by the offline ORCA buoys (see README "Known gaps"), and feeding the
"DO now and 3-day forecast" and Vibrio rows of the decision table in [PLAN.md](../PLAN.md).

## Status (2026-10-26)

Steps 3–5 are done: `ingest/sources/liveocean.py` runs with the other sources and reuses its output
when the daily run hasn't changed, and the site shows the **Water forecast** dashboard card (surface
temperature and salinity, 3-day range, forecast shading, Port Townsend overlay and a 7-day model-vs-observation
bias), hollow **model cell markers** on the map with a popup chart, and a **Data page** section with the
caveats and credit. Step 6 (Vibrio and salinity hooks) and the step 2 email to the LiveOcean team are still open.
The OSU server (step 1) has not been rechecked.

## 1. What the data access actually looks like (probed 2026-10-20)

**Primary server is unreachable from here.** `nanoos.ceoas.oregonstate.edu` (CNAME
`chapman.ceoas.oregonstate.edu`, 128.193.72.30) timed out on every request, both from a local shell and
through a web fetch, while other hosts responded normally. It may be firewalled to some networks or down.
Test it from a GitHub Actions runner before depending on it.

**The IOOS EDS mirror works:**

| Dataset | OPeNDAP URL |
|---|---|
| Best time series (use this) | `https://eds.ioos.us/thredds/dodsC/ioos/nanoos/liveocean/NANOOS_Live_Ocean_best.ncd` |
| Forecast model run collection | `.../liveocean/NANOOS_Live_Ocean_fmrc.ncd` |
| Daily files | `.../liveocean/files/liveocean.surface.f.YYYYMMDD.nc` (latest: 20261020) |

**Variables exposed on the mirror: surface only, physics only.**

- `temp` (potential temperature, °C), `salt` (practical salinity), `zeta` (free surface, m).
  These are on `[time][eta_rho][xi_rho]`. `s_rho` is a scalar, so there is **one level: the surface**.
- Grid fields: `lat_rho`, `lon_rho`, `mask_rho`, `h` (bathymetry), `pm`, `pn`, `f`.
- **Not exposed: currents (u/v), oxygen, pH, NO3, TIC/alkalinity, chlorophyll.** The global attributes
  show the run itself (`cas7_t2_x11b`, `bio_Banas.in`) carries NO3, NH4, chlorophyll, phytoplankton,
  zooplankton, detritus and TIC. Those are computed but not published here.
- Your description of the OSU catalog mentions currents, so that catalog may list more variables than
  the mirror. Confirm once it's reachable. Don't count on biogeochemistry being exposed on either server.

**Grid and time.**

- Grid `cas7`, about 500 m resolution, plaid (lat varies only with eta, lon only with xi): 1302 × 663.
- Nearest wet cell to the site (47.806, −122.735): **eta 788, xi 553** → 47.8041, −122.7357,
  `h` ≈ 21.8 m, `mask_rho` = 1. The cells three columns west are land. At this resolution the bay is
  barely resolved, so this cell is effectively the bay mouth and the Hood Canal channel.
- Time: hourly, `hours since 2026-09-20 00:00 UTC`, 769 steps (2026-09-20 00Z → 2026-10-22 00Z).
  That is a rolling ~30-day window. The latest `time_run` is 2026-10-20 00Z, so the tail is forecast.
  `time_run` per step separates nowcast from forecast.
- Speed: one OPeNDAP `.ascii` request for 69 hours × temp + salt at one cell took **~8 s**. That's easy
  to parse with the standard library, which keeps the repo's no-dependency rule.

## 2. Ingest design: `ingest/sources/liveocean.py`

Stdlib-only, OPeNDAP ASCII, the same pattern as the other sources.

1. **Config** (`ingest/config.py`):
   ```python
   LIVEOCEAN_URLS = [  # tried in order
       "https://nanoos.ceoas.oregonstate.edu/thredds/dodsC/NANOOS/LiveOcean/<best dataset>",  # confirm path
       "https://eds.ioos.us/thredds/dodsC/ioos/nanoos/liveocean/NANOOS_Live_Ocean_best.ncd",
   ]
   LIVEOCEAN_CELLS = [  # precomputed nearest wet cells; checked each run
       {"id": "thorndyke", "name": "Thorndyke Bay mouth", "eta": 788, "xi": 553},
       # optional: "dabob" at the ORCA Dabob buoy (for model-vs-obs once it reports),
       #           "lofall" mid-canal off the tide station
   ]
   LIVEOCEAN_HINDCAST_DAYS = 7
   ```
2. **Fetch steps:**
   - Read `.dds` to get the current `time` length, N. The aggregation grows and slides, so indices aren't fixed.
   - In one request, read `time[N-k:N-1]`, `time_run[N-k:N-1]`, `temp`, `salt` and `zeta` at `[eta][xi]`,
     with k = 7 d hindcast plus the forecast tail. Server limitation: a variable can appear only once per
     constraint, so send one request per cell, or one request with a small `[eta0:eta1][xi0:xi1]` box.
   - Guard against grid changes: also read `lat_rho[eta][xi]`, `lon_rho[eta][xi]` and `mask_rho`. Raise if
     they've moved more than about 100 m or the cell is land, so a model regrid fails loudly instead of
     silently returning the wrong place.
   - Treat `1e20` and NaN as missing. Convert hours to ISO UTC. Mark steps with `time > latest time_run`
     as `forecast`.
3. **Skip unchanged runs.** The workflow runs every 20 min, but LiveOcean updates daily. Add `liveocean`
   to `WITH_CONTEXT`, read only `time_run[N-1]` first, and if it matches `ctx.previous("liveocean")["run"]`,
   return the previous payload. That avoids about 70 needless pulls a day against an academic server.
4. **Output** `web/data/liveocean.json`:
   ```json
   {"source": "UW LiveOcean via NANOOS/IOOS THREDDS", "server": "<url used>",
    "run": "2026-10-20T00:00:00Z", "model": "cas7_t2_x11b", "level": "surface",
    "cells": [{"id": "thorndyke", "lat": 47.8041, "lon": -122.7357, "depth_m": 21.8,
               "series": [{"t": "...", "temp_c": 12.1, "temp_f": 53.8, "salt": 28.4,
                           "zeta_m": 0.42, "kind": "nowcast|forecast"}]}]}
   ```
   At roughly 10 days × 24 h × 1–3 cells, that's a few tens of KB.
5. **Tests.** Save one `.ascii` response as a fixture and unit-test the parser: fill values, multiple
   arrays and splitting on `time_run`.

## 3. Web

- **Dashboard card: "Water forecast (model)".** Surface temperature and salinity now, plus 3-day min and max,
  and a uPlot chart with a nowcast/forecast divider. Where observations exist, overlay Port Townsend
  water temperature and the subtidal float sensor (`thorndyke-float`). Label it clearly as **model,
  surface, ~500 m cell**.
- **Decision hooks:**
  - *Vibrio* (May–Sept): use forecast surface temperature when no observed water temperature is current.
  - *Rain closure watch:* a sharp salinity drop is an independent freshwater-runoff signal. Show it as
    context only, never as a closure call.
  - *Heat stress:* leave as is; it's driven by air temperature at low tide.
- **Map:** a marker at the model cell, with a popup showing the mini-series. A later option is a surface
  temperature/salinity field over `BBOX`, a ~50 × 35 cell box per timestep, rendered as a raster or GeoJSON.
- **About page:** source, run time, the surface-only caveat, and model citation and credit to UW (Parker MacCready's group).

## 4. The biogeochemistry gap (DO / pH)

PLAN.md promises "DO now and 3-day forecast (LiveOcean + buoys)". On the public mirror that isn't possible:

- There's no oxygen, pH or carbonate variable.
- Even surface O₂ wouldn't answer the grower question. Hood Canal hypoxia and low-pH water sit at depth
  and arrive at the shore during fall turnover and upwelling events, so **bottom** values at lease depth matter.

Ways forward, in order:

1. When the OSU THREDDS is reachable, check its DDS for `oxygen`, `PH`/`pH`, `alkalinity`, `TIC`, `u`/`v`
   and any 3-D or bottom-layer files. If they're there, the ingest above extends with no redesign: just
   add variables and pick `s_rho` index 0 for the bottom.
2. Contact the LiveOcean team at UW. PLAN.md already lists "confirm access and licensing with UW". Ask for:
   (a) whether BGC fields are or can be published on THREDDS, and (b) a daily site-specific **mooring
   extraction** at the Thorndyke cell. The LO code base has a mooring-extraction tool that produces a full
   water-column time series of all variables. Published as a small daily NetCDF/JSON, that would be ideal
   for this portal.
3. Fallback: show model temperature and salinity only, and keep DO "observed when available" from the ORCA
   buoys, which `water.py` already picks up when they return.

## 5. Validation before growers see it

- Run for 2–4 weeks in "hidden" mode: write the JSON but leave the card off.
- Compare model surface temperature with Port Townsend (CO-OPS), the farm float sensor once deployed and
  the ORCA Dabob buoy if it returns. Report bias and RMSE on the about page.
- Check that `zeta` phases line up with the Lofall predictions. It's a cheap sanity check on time
  handling, but don't present it as a tide product.

## 6. Steps

| # | Task | Size |
|---|---|---|
| 1 | Confirm the OSU server from a GitHub Actions runner; record its dataset path and variables | small |
| 2 | Email the LiveOcean team about BGC exposure, a mooring extraction and terms of use | small, but long lead time, so start now |
| 3 | `liveocean.py` + config + run-skip logic + parser test fixture | ~1 day |
| 4 | Register in `fetch.py`, run in hidden mode, validate against observations | 2–4 weeks elapsed |
| 5 | Dashboard card, map marker, about-page entry | ~1 day |
| 6 | Wire into the Vibrio indicator and salinity context on the closure watch | ~½ day |
| 7 | If BGC becomes available: bottom DO/pH card + fall hypoxia flag | ~1 day |

## 7. Open questions

- Which OSU dataset path is canonical, and does it expose more than the IOOS mirror?
- Does the forecast horizon in the aggregation reach 72 h, or only ~48 h? The tail on 2026-10-20 ended
  48 h after the latest run. Check the daily `.f.` file, which has 73 steps.
- Are there LiveOcean terms of use or a citation requirement for display on a public site?
- Lease depths: needed to choose surface vs. bottom vs. an interpolated level once 3-D data is available.
