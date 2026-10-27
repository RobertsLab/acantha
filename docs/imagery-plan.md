# Satellite imagery and OlmoEarth plan

Goal: add free satellite imagery (Sentinel-2, Sentinel-1, Landsat) for Thorndyke Bay, plus OlmoEarth embeddings and
fine-tuned model outputs, computed over one shared grid. As with LiveOcean, products run in hidden mode before they're shown.

## Status (2026-10-26)

Steps 1–3 and the true-color part of step 6 are built: `imagery/` (grid, STAC with fallback, S2 true color,
clear-sky %, tide at capture), `.github/workflows/imagery.yml` → `imagery-data` branch, the copy step in
`update.yml`, and on the site a **Satellite view** map layer with a scene picker (capture time, clear % at the
bay, tide at capture), a **Satellite** dashboard card with the last clear view linking to the map, and a Data
page section with the Copernicus attribution. Step 4 (turbidity, NDCI, Landsat, S1) and the step 5 validation
are next; the card and map layers for those products are the rest of step 6.

Implementation notes:

- **Earth Search S2 COGs are already harmonized.** The DNs have the +1000 offset removed (median red DN ~90),
  but the STAC `raster:bands` still say `offset: -0.1`. Planetary Computer serves raw DNs with the offset.
  `s2._reflectance` decides from the data. The two catalogs agree within WebP noise (mean 1.7/255 on 2026-10-16).
- Planetary Computer lagged Earth Search by several hours for the 2026-10-21 scene.
- **Grid COGs (`grid/`) are deferred to step 7.** At ~15–20 MB per scene they'd bloat the branch, and only the models need them.
  `imagery-data` is one force-pushed commit, so the branch stays at the 30-day window (~1–2 MB of WebP per week).
- One run over 10 days of scenes took ~2 min. A run with nothing new takes ~2 s.

## 1. What's available (probed 2026-10-20/21, AOI = `BBOX` in `ingest/config.py`)

| Sensor | Earth Search (AWS) | Planetary Computer | Use |
|---|---|---|---|
| **Sentinel-2 L2A** (10–20 m optical) | 30 items in 30 days. Public COGs on `sentinel-cogs` (us-west-2), no signing, HTTP range reads work (206) | 30 items, same scenes. Assets need a free anonymous SAS token | **Earth Search primary**, PC fallback |
| **Sentinel-1 RTC** (10 m radar, terrain corrected) | not offered (`sentinel-1-rtc` returned 0) | 6 items in 30 days (3 dates: 9-28, 10-01, 10-10) | **PC** |
| Sentinel-1 GRD | 6 items | 6 items | not needed; use RTC |
| **Landsat C2 L2** (30 m SR + surface temp) | 6 items, but assets are `s3://usgs-landsat/...` (requester-pays) | 6 items (L8 + L9), signed HTTPS | **PC** |

Notes:

- **The bay straddles two Sentinel-2 tiles, 10TET and 10UEU**, so every S2 date is two items. Both tiles are in UTM zone 10, so they mosaic cleanly.
- **Revisit:** S2 has a new date every ~2 days. Landsat 8 + 9 together have one about every 8 days. S1 had 3 dates in the last 30 days. Count on S1 for coverage during the cloudy season.
- **Clouds:** October tile-level cloud cover was 25–83%. The tile numbers say little about our ~17 × 20 km box, so compute clear fractions for the box itself from S2 `SCL` and Landsat `qa_pixel`.
- **Reliability:** Both APIs answered on the first probe, then both timed out for about 40 s on a second probe a few minutes later. The ingest needs retries, and each source needs its fallback catalog.
- **Overpass times:** S2 ~19:10 UTC and Landsat ~18:50 UTC, which is late morning local time. That decides whether a scene shows the beds exposed. **Every scene gets tagged with the Lofall tide height at capture time** (from `tides.json`).

**OlmoEarth (Ai2):**

- Open weights are on Hugging Face in Nano, Tiny, Small and Large sizes (v1, v1_1, v1_2) under the **OlmoEarth Artifact License**.
- Inputs: Sentinel-1, Sentinel-2 and Landsat images or time series. Embeddings are computed and models fine-tuned with **rslearn** (segmentation also through `olmoearth_run`).
- OlmoEarth Studio can export embeddings as int8 COGs (one band per dimension; 128-d for Nano, 192 for Tiny, 768 for Base) at 10/20/40/80 m. Exports cover an AOI over 1–12 monthly periods, from S2 L2A and/or S1 RTC. Studio access is by request.
- There's no precomputed global archive, so we compute the embeddings ourselves or request an export.

## 2. Architecture

The imagery stack can't follow the repo's stdlib-only, every-20-minute pattern. It needs rasterio/numpy, it runs daily, and its outputs are larger.

```
.github/workflows/imagery.yml   (daily, ~20:30 UTC after the S2/Landsat overpass + processing lag)
  └─ imagery/run.py              own requirements.txt: pystac-client, planetary-computer,
       │                         odc-stac (or stackstac), rasterio, numpy, pillow
       ├─ search STAC (ES / PC) for new items over AOI
       ├─ load only the AOI window from COGs (range reads) onto the shared grid
       ├─ derive products + per-scene stats
       └─ commit to orphan branch `imagery-data`:
            products/<date>_<sensor>_<product>.webp   (EPSG:3857, for the map)
            grid/<date>_<sensor>.tif                  (shared-grid COG, kept 90 days, for models)
            imagery.json                              index: scenes, clear %, tide at capture, stats

.github/workflows/update.yml   (existing, every 20 min)
  └─ adds one step: check out `imagery-data` products + imagery.json into web/data/imagery/
```

**Why a separate branch:** each Pages deploy replaces the whole site, and the 20-minute job rebuilds `web/data/` from
scratch. Committing imagery products to an orphan branch makes them persistent, versioned and cheap to copy into each deploy.
`ingest/` stays dependency-free.

**Shared grid.** Every sensor and every model output goes onto one grid:

- EPSG:32610 (UTM 10N), 10 m, `BBOX` snapped to 10 m. That's about 1,750 × 2,000 px.
- S2 is native to this grid (resampling 20 m bands up). S1 RTC is reprojected, and Landsat (30 m SR, 100 m thermal delivered at 30 m)
  is resampled up for display only, with its native resolution kept in the metadata.
- OlmoEarth embeddings are computed from these same arrays, so pixel (i, j) means the same place in every layer.

**Size budget.** A 10 m RGB WebP of the AOI is about 0.3–1 MB. Keep 30 days of products in `web/` (about 50–100 MB), so the Pages site
stays well under its 1 GB limit. Grid COGs stay on the branch only. Prune them with a squash/force-push of `imagery-data` monthly,
so the repo doesn't grow forever.

## 3. Products, tied to grower decisions (PLAN.md §1)

| Product | Sensor | Decision it supports | Caveats |
|---|---|---|---|
| **Latest clear true color**, with the tide at capture | S2 (Landsat backup) | Context: bed and gear layout, exposed intertidal at low-tide passes | Clear days are rare Nov–Mar |
| **Turbidity / sediment plume** (red-band reflectance; NDTI) | S2, Landsat | Rain closure watch context: is runoff from Thorndyke Creek reaching the beds? | Relative only. Adjacency effects in a narrow bay. L2A isn't a water-optimized correction (ACOLITE would be better later) |
| **Chlorophyll proxy** (NDCI, B05 vs B04) | S2 | Bloom context alongside DOH biotoxin status | Proxy, not a toxin indicator. Label it clearly |
| **Water surface temperature** | Landsat ST_B10 | Vibrio and heat context; checks LiveOcean surface temperature and the sensors | 100 m native. Only a few pixels span the bay |
| **Radar backscatter VV/VH + change** | S1 RTC | Works through cloud: gear and structures, storm damage, exposed flats, boat and float changes | Speckle. Read it as change between dates, not absolute values |
| **Clear-sky / coverage stats** | S2 SCL, Landsat QA | Tells growers when the imagery is fresh, and feeds every card | — |

Per-scene stats go into `imagery.json`: AOI clear %, median turbidity and NDCI over water in the bay and over each lease polygon
(once leases are mapped, an open question from PLAN.md §8), and Landsat bay temperature.

## 4. OlmoEarth: embeddings and fine-tuned outputs

Phased, because value depends on labels and compute.

1. **Monthly embeddings, unsupervised.** Use rslearn with **OlmoEarth Nano or Tiny** on the shared grid, with inputs of monthly S2 L2A + S1 RTC
   stacks over the AOI, saved as int8 COGs (Studio's format) at 10 m. Nano (1.4 M parameters) over a ~3.5 M-pixel AOI should run on a CPU, so it
   could run in Actions monthly. Benchmark it before committing to that.
   - **Change map:** cosine distance between this month's embedding and the same month last year (or last month) highlights shoreline,
     gear, eelgrass or sediment changes worth a look.
   - **Similarity search:** click a pixel or lease and highlight areas whose embeddings look alike. Useful for "where else looks like my best beds?".
2. **Fine-tuned heads, needing labels.** Train small heads on the embeddings, or fine-tune with rslearn/`olmoearth_run`, for:
   - intertidal habitat / substrate classes;
   - aquaculture gear footprint (bags, racks, floats), for gear inventory and change;
   - eelgrass extent, which matters for permitting.

   Labels come from grower interviews, lease maps and the site visit (Phase 0), plus a few hand-digitized S2 scenes. Run inference on the same tiles.
3. **Larger models (Small/Large/Base)** need a GPU: a lab workstation, UW Hyak or an OlmoEarth Studio export. Their outputs follow the same
   `grid/` + `products/` convention, uploaded to `imagery-data`.

Before public display, read the **OlmoEarth Artifact License** and Ai2's Responsible Use Guidelines: model outputs on a public site, and attribution.

## 5. Web (after the hidden period)

- **Map layer group "Satellite":** latest clear true color, turbidity, chlorophyll proxy, radar and Landsat temperature, as MapLibre `image`
  sources with `bounds` from `imagery.json`, plus a date picker. Each layer label shows the capture time, cloud-free % and **tide at capture**.
- **Dashboard:** one small card only, "Last clear satellite view: Oct 18, tide +6.2 ft, 70% clear", with a turbidity flag after big rain.
- **About page:** sources (Copernicus Sentinel data, USGS Landsat, Ai2 OlmoEarth) with the attribution each requires, and the caveats above.

## 6. Steps

| # | Task | Size |
|---|---|---|
| 1 | `imagery/` scaffold: shared grid definition, STAC search with ES→PC fallback and retries, AOI window load | ~1 day |
| 2 | S2 true color + SCL clear %, tide-at-capture tag, `imagery.json`; `imagery.yml` writing to `imagery-data` | ~1 day |
| 3 | Copy step in `update.yml`, hidden (files published, no UI) | ~½ day |
| 4 | Turbidity, NDCI, Landsat surface temp, S1 RTC + change products | ~1–2 days |
| 5 | Validate: turbidity against rain events, Landsat temperature against Port Townsend / sensors / LiveOcean | 2–4 weeks elapsed |
| 6 | Map layers + dashboard card + about page | ~1–2 days |
| 7 | OlmoEarth Nano monthly embeddings + change map (benchmark CPU time first) | ~2 days |
| 8 | Labels + fine-tuned gear/habitat/eelgrass head | depends on labels |

## 7. Open questions

- Lease and bed polygons (PLAN.md §8 Q1) for per-lease stats and training labels.
- Does the turbidity proxy actually track rain closures here? This is a validation question for step 5.
- Where do larger OlmoEarth models run (Hyak, a lab GPU, Studio access)?
- OlmoEarth license terms for public display of outputs.
- Is a public site OK for imagery of individual farms' gear? This ties to PLAN.md §8 Q4, public vs. login.

Sources: [OlmoEarth v1 Nano model card](https://huggingface.co/allenai/OlmoEarth-v1-Nano),
[OlmoEarth embeddings](https://allenai.org/blog/olmoearth-embeddings), [OlmoEarth v1.1](https://allenai.org/blog/olmoearth-v1-1),
[Earth Search STAC](https://earth-search.aws.element84.com/v1), [Planetary Computer STAC](https://planetarycomputer.microsoft.com/api/stac/v1).
