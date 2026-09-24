# Thorndyke Bay Data Portal: Plan

A web portal that collects very local, near-real-time environmental data for Thorndyke Bay (Hood Canal, Jefferson County, WA, about 47.806° N, 122.735° W) and shows it to help oyster growers make day-to-day management decisions. The main page is an interactive map.

---

## 1. Growers' decisions drive the design

Each data stream is here because it feeds a decision. Features that don't support a decision get cut.

| Decision | Data needed | Output in the portal |
|---|---|---|
| When to work or harvest intertidal ground | Tide predictions, daylight, wind | "Workable low tides" calendar (daylight lows below a threshold the grower sets) |
| Heat-stress risk to exposed oysters | Low-tide timing × air temperature × sun/cloud × wind | Heat-exposure flag for upcoming low tides |
| *Vibrio parahaemolyticus* handling (May–Sept) | Water and air temperature at harvest | Temperature-based risk indicator with a link to the DOH Vibrio control plan requirements |
| Rain-triggered conditional closures | 24/48/72 h rainfall totals | "Closure watch" against the growing area's DOH rainfall threshold |
| Biotoxin (PSP/DSP/ASP) closures | WA DOH biotoxin status | Current status banner on the map and dashboard |
| Gear and boat safety | Wind speed/gust/direction, small craft advisories | Wind forecast and NWS marine alerts (zone PZZ135, Hood Canal) |
| Low dissolved oxygen and hypoxia in fall | DO and water-column forecasts | DO now and 3-day forecast (LiveOcean + buoys) |
| Seed and hatchery timing, OA stress | pH, salinity, temperature | Carbonate-chemistry trend panel (Phase 2+) |

> The portal is **advisory**. Official harvest closures come from WA DOH, and every closure-related panel links to the authoritative source.

---

## 2. Data sources

### Public feeds (Phase 1, no hardware)

| Variable | Source | Specifics / IDs | Notes |
|---|---|---|---|
| Tide predictions | NOAA CO-OPS API | **Lofall 9445088** (subordinate, closest). Reference station **Bangor Wharf 9445133**, directly across the canal | Predictions only. No real-time water-level gauge in Hood Canal. Nearest observed gauges are Bremerton 9445958 and Port Townsend 9444900 |
| Weather forecast | NWS `api.weather.gov` | Grid **SEW 114,80**. Marine zone **PZZ135** | Hourly temp, wind, precip probability, QPF. Alerts endpoint for advisories |
| Observed weather | Synoptic / MesoWest API (free tier), WSDOT Hood Canal Bridge weather station, nearby CWOP stations | Choose stations in Discovery | Gaps are likely, which is why we add our own station |
| Rainfall (gridded) | NOAA MRMS / NWS QPE; CoCoRaHS gauges | | Useful for closure watch until on-site gauge exists |
| Water temp, salinity, DO, chlorophyll | NANOOS NVS / ERDDAP (UW ORCA Hood Canal moorings, WA Ecology stations) | Pick nearest moorings in Discovery | Buoys are kilometers away. Good for context, not hyper-local |
| Water-column forecast | UW **LiveOcean** model | 3-day forecasts of temperature, salinity, O₂, pH | Extract the model grid cells nearest each lease. Confirm access and licensing with UW |
| Shellfish safety | WA DOH Shellfish Safety map and commercial growing-area classifications (ArcGIS feature services) | | Biotoxin closures, growing-area polygons, conditional-area rainfall rules |
| Base maps | OpenStreetMap / Esri, NOAA ENC nautical charts (WMS), WA DNR aquatic lands / parcels | | Chart layer shows bathymetry and intertidal extent |

### Local sensors (Phase 2)

These make the portal hyper-local. Suggested starter kit, one node per farm site:

| Measurement | Example hardware | Approx. cost | Telemetry |
|---|---|---|---|
| Weather (air T, RH, wind, rain, solar, pressure) | WeatherFlow Tempest or Davis Vantage Pro2 + WeatherLink | $350–$1,200 | Wi-Fi/cellular; both have cloud APIs |
| Water temp + conductivity (salinity) | Onset HOBO MX / U24 series, or DIY Atlas Scientific + microcontroller | $150–$800 | Bluetooth (manual) or LoRaWAN/cellular for real time |
| Intertidal / in-bag temperature | HOBO MX2201/2202 pendants, or LoRa temp probes | $50–$120 each | Place several across tidal elevations |
| Water level (observed tides, surge) | Vented pressure transducer | $300–$1,500 | Checks predictions against reality; shows storm surge |
| DO / pH (optional, higher upkeep) | Optical DO + pH sonde (e.g. PME miniDOT, Seabird/YSI) | $1k–$15k+ | Needs a biofouling and calibration plan |
| Backhaul | LoRaWAN gateway (The Things Network) or cellular modem | $200–$500 + ~$10/mo | Solar power where there is no mains |

Costs are rough 2026 estimates and need a real quote.

Sensor QA/QC: range and spike checks, flat-line detection, and flags for out-of-water or low-tide exposure. Store raw data alongside QC flags, following IOOS QARTOD conventions so the data can later go to NANOOS.

---

## 3. Architecture

```
 ┌───────────────┐   ┌──────────────────┐
 │ Public APIs   │   │ Farm sensors     │
 │ NOAA/NWS/DOH/ │   │ (LoRaWAN/cell,   │
 │ NANOOS/LiveOc │   │  Tempest API)    │
 └──────┬────────┘   └────────┬─────────┘
        │ scheduled fetch     │ push (HTTP/MQTT)
        ▼                     ▼
 ┌─────────────────────────────────────┐
 │ Ingestion workers (Python)          │
 │ - one adapter per source            │
 │ - normalize → common schema         │
 │ - QC flags, unit conversion         │
 └──────────────┬──────────────────────┘
                ▼
 ┌─────────────────────────────────────┐
 │ Postgres + TimescaleDB (+ PostGIS)  │
 │ stations, variables, observations,  │
 │ forecasts, alerts, leases           │
 └──────────────┬──────────────────────┘
                ▼
 ┌─────────────────────────────────────┐   ┌──────────────┐
 │ API (FastAPI): /stations /series    │──▶│ Alert engine │→ SMS/email
 │ /latest /tides /forecast /status    │   │ (thresholds) │
 └──────────────┬──────────────────────┘   └──────────────┘
                ▼
 ┌─────────────────────────────────────┐
 │ Frontend (mobile-first PWA)         │
 │ MapLibre GL map + charts            │
 └─────────────────────────────────────┘
```

### Recommended stack

- **Ingestion and API:** Python (FastAPI, httpx, pandas/xarray for LiveOcean NetCDF). The lab already knows Python/R, so maintenance stays in-house.
- **Database:** Postgres with TimescaleDB for time series and PostGIS for leases and stations. Supabase or Neon free tier to start.
- **Scheduler:** a cron container on Fly.io/Render, running every 10–15 min for observations and hourly for forecasts.
- **Frontend:** Vite + TypeScript (Svelte or React), **MapLibre GL JS** for the map, **uPlot** or Observable Plot for fast time-series charts. Installable PWA with offline cache of the last-known conditions, because shoreline cell coverage is poor.
- **Hosting:** static frontend on GitHub Pages / Cloudflare Pages. API and workers on Fly.io/Render.
- **Cheapest MVP option:** skip the DB and API for Phase 1. A GitHub Actions cron fetches the public feeds, writes compact JSON to the Pages branch, and the static frontend reads it. Move to the full stack when sensors arrive.

### Core data model

- `station(id, name, source, geom, elevation_m, type)`
- `variable(id, name, units, description)`
- `observation(station_id, variable_id, time, value, qc_flag)` (Timescale hypertable)
- `forecast(source, variable_id, geom/station_id, issued_at, valid_at, value)`
- `lease(id, name, owner, geom, doh_growing_area, rain_threshold_in)`
- `alert_rule(user_id, lease_id, variable_id, operator, threshold, window)`

---

## 4. Pages and UX

Design for a phone held in bright sun by someone with wet gloves: high contrast, large numbers, little typing.

1. **Map (home)**
   - Map centered on Thorndyke Bay. Layers can be toggled: stations (public and farm sensors), leases, DOH growing-area classification and closure status, nautical chart, LiveOcean surface field (temp / DO / salinity heat map with a time slider).
   - Marker colors show freshness (live / stale / offline) and threshold state.
   - Clicking a station opens a side panel with latest values, 72 h sparklines, and a link to the full station page.
   - A time slider scrubs the past 7 days and the next 3 days of forecast.
2. **Today at Thorndyke (dashboard)**
   - Cards: next two low tides (height, time, daylight?), air and water temp now, 24 h rain plus closure-watch status, wind now and max gust today, biotoxin status, DO forecast.
   - Decision flags in plain language, e.g. "Afternoon low −2.1 ft at 1:40 pm, forecast 27 °C: high heat-exposure risk."
3. **Tides and work windows:** monthly calendar of daylight low tides below a threshold the user sets, with an iCal export.
4. **Station detail:** interactive multi-variable charts with date-range picker, observed vs. forecast overlay, CSV download.
5. **Alerts:** growers subscribe to rules such as rain > X in / 24 h, water temp > Y, small craft advisory, or biotoxin change. Delivered by email or SMS (e.g. Twilio).
6. **Data and about:** source list with provenance and latency, QC methods, API docs, disclaimer.

---

## 5. Phased roadmap

| Phase | Duration | Deliverables |
|---|---|---|
| **0: Discovery** | 2–3 wks | Interview 3–5 Thorndyke growers. Map leases and their DOH growing areas and rain thresholds. Finalize the decision/threshold table (§1). Confirm API access (Synoptic token, LiveOcean, DOH services). Site visit to plan sensor locations and check power and connectivity |
| **1: MVP with public data** | 4–6 wks | Adapters for NOAA tides, NWS forecast and alerts, DOH status, NANOOS buoys, LiveOcean extraction. Map page plus dashboard plus tide calendar. Static hosting. Grower feedback round |
| **2: Local sensors** | 6–10 wks (starts during Phase 1; hardware lead times) | Buy and deploy 1–3 sensor nodes. Ingestion endpoint. Move to Postgres/Timescale plus API. QC pipeline. Sensors shown on the map |
| **3: Decision tools and alerts** | 4 wks | Heat-exposure index, closure watch, Vibrio indicator, alert subscriptions, iCal export |
| **4: Hardening and sustainability** | ongoing | Uptime and staleness monitoring, backups, sensor maintenance calendar (biofouling, calibration), NANOOS/IOOS data sharing via ERDDAP, docs for handoff |

---

## 6. Proposed repo layout

```
acantha/
├── ingest/            # Python: one module per source + scheduler
│   ├── sources/       # noaa_tides.py, nws.py, doh.py, nanoos.py, liveocean.py, tempest.py
│   ├── qc.py
│   └── schema.sql
├── api/               # FastAPI app
├── web/               # Vite + TS frontend (map, dashboard, charts)
├── hardware/          # sensor build notes, wiring, deployment log
├── docs/              # data dictionary, decision thresholds, runbooks
└── .github/workflows/ # cron fetch (MVP), CI, deploy
```

---

## 7. Risks and mitigations

- **Official data is sparse in Hood Canal** (no real-time tide gauge, distant buoys). Mitigation: local sensors in Phase 2, plus LiveOcean to fill the space between points.
- **Sensor fouling, theft, and storms.** Mitigation: rugged mounts, a maintenance schedule, staleness alerts, and a spare unit.
- **Users mistake advisory flags for regulatory status.** Mitigation: clear labeling and a direct link to DOH on every closure panel.
- **Upstream APIs change.** Mitigation: isolated adapters, contract tests, and a "source down" state in the UI.
- **Long-term funding and maintenance.** Mitigation: low-cost hosting and ties to NANOOS, WA Sea Grant, and PCSGA for sustainability.

---

## 8. Open questions

1. Who are the first users (specific farms), and where exactly are their leases and beds?
2. Which DOH growing area(s) cover Thorndyke Bay, and is any of it conditionally approved with a rainfall rule?
3. What is the budget for sensors (a weather station plus temperature loggers vs. a full DO/pH sonde)?
4. Should the portal be public, login-only for growers, or mixed (public map, private lease data)?
5. Are there existing loggers (lab, tribal, county, or grower-owned) we can ingest instead of duplicating?
6. Where will it be hosted and who owns it long-term (lab, Sea Grant, grower association)?
