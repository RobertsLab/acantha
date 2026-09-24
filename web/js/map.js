// Interactive map: basemaps, nautical chart overlay, stations, shellfish areas.
import { loadAll, fmtTime, fmtDayTime, ago, num, compass, el, latestValue, tideAt, cssVar, sensorChart } from "./common.js";

const D = await loadAll(["meta", "tides", "observations", "water", "shellfish", "sensors"]);
const site = D.meta?.site || { name: "Thorndyke Bay", lat: 47.806, lon: -122.735 };

const NOAA_ENC =
  "https://gis.charttools.noaa.gov/arcgis/rest/services/MCS/NOAAChartDisplay/MapServer/exts/MaritimeChartService/WMSServer" +
  "?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image/png&TRANSPARENT=true&LAYERS=0,1,2,3,4,5,6,7" +
  "&CRS=EPSG:3857&STYLES=&WIDTH=256&HEIGHT=256&BBOX={bbox-epsg-3857}";

const map = new maplibregl.Map({
  container: "map",
  center: [site.lon, site.lat],
  zoom: 10.5,
  attributionControl: { compact: true },
  style: {
    version: 8,
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
    sources: {
      osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 19,
        attribution: "© OpenStreetMap contributors" },
      imagery: { type: "raster", tileSize: 256, maxzoom: 19,
        tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
        attribution: "Imagery © Esri, Maxar, Earthstar Geographics" },
      chart: { type: "raster", tiles: [NOAA_ENC], tileSize: 256, attribution: "NOAA ENC® chart display" },
    },
    layers: [
      { id: "osm", type: "raster", source: "osm" },
      { id: "imagery", type: "raster", source: "imagery", layout: { visibility: "none" } },
      { id: "chart", type: "raster", source: "chart", layout: { visibility: "none" } },
    ],
  },
});
new ResizeObserver(() => map.resize()).observe(document.getElementById("map"));
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-left");
map.addControl(new maplibregl.GeolocateControl({ trackUserLocation: false }), "top-left");

// ---------- build point features ----------
function points() {
  const f = [];
  const add = (kind, lon, lat, props) => f.push({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: { kind, ...props } });
  add("site", site.lon, site.lat, { name: site.name });
  if (D.tides) add("tide", D.tides.station.lon, D.tides.station.lat, { name: `${D.tides.station.name} tide station`, id: D.tides.station.id });
  for (const s of D.observations?.stations || []) add("weather", s.lon, s.lat, { name: s.name, id: s.id });
  for (const s of D.water?.stations || []) add("water", s.lon, s.lat, { name: s.name, id: s.id });
  return { type: "FeatureCollection", features: f };
}

// Farm sensors get their own source so they can be toggled and colored by status.
function sensorPoints() {
  return { type: "FeatureCollection", features: (D.sensors?.stations || []).map((s) => ({
    type: "Feature", geometry: { type: "Point", coordinates: [s.lon, s.lat] },
    properties: { id: s.id, status: s.status,
      label: s.latest ? `${s.name} · ${num(s.latest.temp_f, 1)}°F` : s.name } })) };
}

const KIND_COLORS = () => ({
  site: cssVar("--accent-2"), tide: cssVar("--series-1"), weather: cssVar("--series-3"), water: "#2a9d8f",
});
const SENSOR_COLORS = { live: "#7b4fa0", stale: "#d9a21a", offline: "#888888" };
const CLASS_COLORS = {
  approved: "#2f7d4a", conditional: "#d9a21a", restricted: "#d9731a", prohibited: "#b83232", unclassified: "#888888",
};

map.on("load", () => {
  const kc = KIND_COLORS();

  // Shellfish growing areas (polygons) and biotoxin status
  const areas = D.shellfish?.growing_areas;
  if (areas?.features?.length) {
    map.addSource("areas", { type: "geojson", data: areas });
    map.addLayer({ id: "areas-fill", type: "fill", source: "areas", paint: {
      "fill-color": ["match", ["get", "class_key"], ...Object.entries(CLASS_COLORS).flat(), "#888"],
      "fill-opacity": 0.15 } });
    map.addLayer({ id: "areas-line", type: "line", source: "areas", paint: {
      "line-color": ["match", ["get", "class_key"], ...Object.entries(CLASS_COLORS).flat(), "#888"], "line-width": 1.2 } });
  }
  const bio = D.shellfish?.biotoxin;
  if (bio?.features?.length) {
    map.addSource("biotoxin", { type: "geojson", data: bio });
    map.addLayer({ id: "biotoxin-fill", type: "fill", source: "biotoxin", layout: { visibility: "none" },
      paint: { "fill-color": ["case", ["get", "closed"], "#b83232", "#2f7d4a"], "fill-opacity": 0.25 } });
    map.addLayer({ id: "biotoxin-line", type: "line", source: "biotoxin", layout: { visibility: "none" },
      paint: { "line-color": ["case", ["get", "closed"], "#b83232", "#2f7d4a"], "line-width": 2, "line-dasharray": [2, 1] } });
  }

  map.addSource("points", { type: "geojson", data: points() });
  map.addLayer({ id: "points", type: "circle", source: "points", paint: {
    "circle-radius": ["match", ["get", "kind"], "site", 9, 7],
    "circle-color": ["match", ["get", "kind"], "site", kc.site, "tide", kc.tide, "weather", kc.weather, "water", kc.water, "#666"],
    "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
  map.addLayer({ id: "labels", type: "symbol", source: "points", layout: {
    "text-field": ["get", "name"], "text-size": 12, "text-offset": [0, 1.3], "text-anchor": "top",
    "text-font": ["Open Sans Semibold"] },
    paint: { "text-color": "#16231f", "text-halo-color": "#fff", "text-halo-width": 1.5 } });

  if (D.sensors?.stations?.length) {
    map.addSource("sensors", { type: "geojson", data: sensorPoints() });
    map.addLayer({ id: "sensors", type: "circle", source: "sensors", paint: {
      "circle-radius": 6,
      "circle-color": ["match", ["get", "status"], "live", SENSOR_COLORS.live, "stale", SENSOR_COLORS.stale, SENSOR_COLORS.offline],
      "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
    map.addLayer({ id: "sensor-labels", type: "symbol", source: "sensors", minzoom: 13, layout: {
      "text-field": ["get", "label"], "text-size": 11.5, "text-offset": [0, 1.1], "text-anchor": "top",
      "text-font": ["Open Sans Semibold"] },
      paint: { "text-color": "#16231f", "text-halo-color": "#fff", "text-halo-width": 1.5 } });
    map.on("click", "sensors", (e) => sensorPopup(e.features[0], e.lngLat));
    map.on("mouseenter", "sensors", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "sensors", () => (map.getCanvas().style.cursor = ""));
  }

  map.resize();

  map.on("click", "points", (e) => popup(e.features[0], e.lngLat));
  for (const id of ["areas-fill", "biotoxin-fill"]) {
    if (map.getLayer(id)) map.on("click", id, (e) => {
      // A marker on top of the polygon gets its own popup instead.
      const markers = ["points", "sensors"].filter((l) => map.getLayer(l));
      if (map.queryRenderedFeatures(e.point, { layers: markers }).length) return;
      areaPopup(e.features[0], e.lngLat);
    });
  }
  map.on("mouseenter", "points", () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", "points", () => (map.getCanvas().style.cursor = ""));

  map.addControl(new LayerControl(), "top-right");
});

// ---------- popups ----------
function popup(f, lngLat) {
  const p = f.properties;
  const body = el("div", {}, el("h3", {}, p.name));
  if (p.kind === "site") {
    const t = D.tides && tideAt(new Date(), D.tides.hilo);
    body.append(el("div", {}, t ? `Tide now ≈ ${num(t.v, 1)} ft, ${t.rising ? "rising" : "falling"}` : ""),
      el("div", { class: "muted small" }, "See the panel for today's conditions."));
  } else if (p.kind === "tide") {
    const next = D.tides.hilo.filter((h) => new Date(h.t) > Date.now()).slice(0, 4);
    body.append(...next.map((h) => el("div", {}, `${h.type === "L" ? "Low " : "High"} ${fmtDayTime(h.t)} · ${num(h.v, 1)} ft`)),
      el("a", { href: D.tides.source_url, target: "_blank", rel: "noopener", class: "small" }, "NOAA station page →"));
  } else if (p.kind === "weather") {
    const s = D.observations.stations.find((x) => x.id === p.id);
    const T = latestValue(s.series, "air_temp_f"), W = latestValue(s.series, "wind_mph"),
      G = latestValue(s.series, "gust_mph"), Dd = latestValue(s.series, "wind_dir_deg");
    body.append(
      el("div", {}, `Air ${num(T?.v)}°F · Wind ${num(W?.v)} mph ${compass(Dd?.v)}${G ? `, gust ${num(G.v)}` : ""}`),
      el("div", { class: "muted small" }, `${s.id} · ${s.distance_km} km from site · ${ago(T?.t)}`));
  } else if (p.kind === "water") {
    const s = D.water.stations.find((x) => x.id === p.id);
    const L = s.latest;
    body.append(L
      ? el("div", {}, `Water ${num(L.water_temp_f, 1)}°F · Sal ${num(L.salinity_psu, 1)} · DO ${num(L.do_mgl, 1)} mg/L`)
      : el("div", { class: "muted" }, "No recent data"),
      el("div", { class: "muted small" }, `${s.provider || ""} · ${L ? ago(L.t) : ""}`),
      s.url ? el("a", { href: s.url, target: "_blank", rel: "noopener", class: "small" }, "Source →") : "");
  }
  new maplibregl.Popup({ offset: 10 }).setLngLat(lngLat).setDOMContent(body).addTo(map);
}

function sensorPopup(f, lngLat) {
  const s = D.sensors.stations.find((x) => x.id === f.properties.id);
  const L = s.latest;
  const chart = el("div", { class: "popup-chart" });
  const body = el("div", {},
    el("h3", {}, s.name, D.sensors.mock ? el("span", { class: "badge warn", style: "margin-left:6px" }, "mock") : ""),
    L ? el("div", {}, el("b", {}, `${num(L.temp_f, 1)}°F`), ` (${num(L.temp_c, 1)}°C) · `,
      L.exposed == null ? "" : L.exposed ? "out of water (low tide)" : "in water")
      : el("div", { class: "muted" }, "No valid readings"),
    el("div", { class: "muted small" }, `${s.placement || ""} · ${num(s.elevation_ft, 1)} ft MLLW`),
    el("div", { class: "small" }, el("span", { class: "legend-dot", style: `background:${SENSOR_COLORS[s.status]}` }),
      `${s.status} · last seen ${ago(s.last_seen)}`,
      s.battery_v != null ? ` · battery ${num(s.battery_v, 2)} V` : "", s.rssi != null ? ` · signal ${s.rssi} dBm` : ""),
    chart);
  new maplibregl.Popup({ offset: 10, maxWidth: "300px" }).setLngLat(lngLat).setDOMContent(body).addTo(map);
  sensorChart(chart, [s], { hours: 72, width: 260, height: 150, legend: false });
}

function areaPopup(f, lngLat) {
  const p = f.properties;
  const body = el("div", {}, el("h3", {}, p.name || "Area"),
    p.classification ? el("div", {}, `Classification: ${p.classification}`) : "",
    p.status ? el("div", {}, `Biotoxin: ${p.status}`) : "",
    p.detail ? el("div", { class: "small" }, p.detail) : "",
    p.updated ? el("div", { class: "muted small" }, `Updated ${p.updated}`) : "",
    el("div", { class: "muted small" }, "Source: WA DOH. Confirm before harvest."));
  new maplibregl.Popup().setLngLat(lngLat).setDOMContent(body).addTo(map);
}

// ---------- layer control ----------
class LayerControl {
  onAdd(m) {
    const kc = KIND_COLORS();
    const radio = (id, label, checked) => el("label", {}, el("input", { type: "radio", name: "base", value: id, ...(checked ? { checked: "" } : {}),
      onchange: () => { for (const b of ["osm", "imagery"]) m.setLayoutProperty(b, "visibility", b === id ? "visible" : "none"); } }), ` ${label}`);
    const check = (ids, label, on, dot) => {
      const present = ids.filter((i) => m.getLayer(i));
      if (!present.length) return null;
      return el("label", {}, el("input", { type: "checkbox", ...(on ? { checked: "" } : {}),
        onchange: (e) => present.forEach((i) => m.setLayoutProperty(i, "visibility", e.target.checked ? "visible" : "none")) }),
        " ", dot ? el("span", { class: "legend-dot", style: `background:${dot}` }) : "", label);
    };
    this._c = el("details", { class: "maplibregl-ctrl layer-ctl", ...(innerWidth > 860 ? { open: "" } : {}) },
      el("summary", {}, el("b", {}, "Layers")),
      radio("osm", "Streets", true), radio("imagery", "Satellite"),
      el("hr"),
      check(["chart"], "Nautical chart", false),
      check(["areas-fill", "areas-line"], "Commercial growing areas", true),
      check(["biotoxin-fill", "biotoxin-line"], "Recreational biotoxin zones", false),
      check(["points", "labels"], "Stations", true),
      check(["sensors", "sensor-labels"], D.sensors?.mock ? "Farm sensors (mock)" : "Farm sensors", true, SENSOR_COLORS.live),
      el("hr"),
      el("div", { class: "small" },
        el("div", {}, el("span", { class: "legend-dot", style: `background:${kc.site}` }), "Thorndyke Bay"),
        el("div", {}, el("span", { class: "legend-dot", style: `background:${kc.tide}` }), "Tide prediction"),
        el("div", {}, el("span", { class: "legend-dot", style: `background:${kc.weather}` }), "Weather obs"),
        (D.water?.stations || []).length ? el("div", {}, el("span", { class: "legend-dot", style: `background:${kc.water}` }), "Water quality") : null,
        m.getLayer("areas-fill") ? el("div", { style: "margin-top:4px" },
          ...["approved", "conditional", "restricted", "prohibited"].map((k) =>
            el("div", {}, el("span", { class: "legend-dot", style: `background:${CLASS_COLORS[k]};border-radius:2px` }), k[0].toUpperCase() + k.slice(1)))) : null),
    );
    return this._c;
  }
  onRemove() { this._c.remove(); }
}
