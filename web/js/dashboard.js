// "Today at Thorndyke" side panel: alerts, decision flags, tide/weather/rain/sensor/water cards.
import {
  load, loadAll, TZ, fmtTime, fmtDayTime, fmtDay, ago, num, compass, el, toDate, tideAt, isDaylight,
  nearestHour, latestValue, getSettings, saveSettings, DEFAULTS, uplotTz, nightShade, nowLine,
  cssVar, sourceBadge, sensorChart, liveoceanChart, modelVsObs, satScenes, cToF, hoboDays, hoboChart, localDateKey,
} from "./common.js";

const $ = (id) => document.getElementById(id);

const D = await loadAll(["meta", "tides", "sun", "forecast", "alerts", "observations", "rain", "water", "shellfish", "sensors", "liveocean"]);
const NORMAL = await load("liveocean_climatology", "baseline/liveocean_climatology.json");
const HOBO = await load("thorndyke_hobo", "baseline/thorndyke_hobo.json");
D.imagery = await load("imagery", "data/imagery/imagery.json");
let S = getSettings();

function render() {
  renderAlerts();
  renderFlags();
  renderTide();
  renderWeather();
  renderRain();
  renderSensors();
  renderWater();
  renderHobo();
  renderModel();
  renderSatellite();
  renderShellfish();
}

// ---------- alerts ----------
function renderAlerts() {
  const box = $("alerts");
  box.replaceChildren();
  for (const a of D.alerts?.alerts || []) {
    const severe = ["Severe", "Extreme"].includes(a.severity);
    box.append(el("div", { class: "alert" + (severe ? " severe" : "") },
      el("details", {},
        el("summary", {}, el("b", {}, a.event), a.ends || a.expires ? ` · until ${fmtDayTime(a.ends || a.expires)}` : ""),
        el("p", { class: "small", style: "white-space:pre-line" }, a.description || ""),
      )));
  }
}

// ---------- decision flags ----------
function upcomingLows(hours) {
  const now = Date.now(), end = now + hours * 3600e3;
  return (D.tides?.hilo || []).filter((h) => h.type === "L" && toDate(h.t) >= now && toDate(h.t) <= end);
}

function renderFlags() {
  const ul = $("flags");
  ul.replaceChildren();
  const add = (level, title, detail) => ul.append(el("li", { class: level }, el("b", {}, title), detail ? el("span", { class: "small" }, detail) : null));
  const hourly = D.forecast?.hourly || [];

  // Workable daylight low tides and heat exposure (next 72 h)
  const lows = upcomingLows(72);
  const work = lows.filter((l) => l.v <= S.lowTideFt && isDaylight(l.t, D.sun));
  for (const l of work) {
    const f = nearestHour(hourly, l.t);
    const hot = f?.air_temp_f != null && f.air_temp_f >= S.heatF;
    add(hot ? "bad" : "good",
      `${hot ? "Heat exposure risk: " : "Workable low: "}${num(l.v, 1)} ft at ${fmtDayTime(l.t)}`,
      f ? `Forecast ${num(f.air_temp_f)}°F, sky ${num(f.sky_pct)}% cover, wind ${num(f.wind_mph)} mph` : "");
  }
  if (!work.length && lows.length) {
    const min = lows.reduce((a, b) => (a.v < b.v ? a : b));
    add("", `No daylight lows ≤ ${S.lowTideFt} ft in the next 3 days`,
      `Lowest: ${num(min.v, 1)} ft at ${fmtDayTime(min.t)}${isDaylight(min.t, D.sun) ? "" : " (dark)"}`);
  }

  // Wind
  const next24 = hourly.filter((h) => toDate(h.t) - Date.now() < 24 * 3600e3);
  const gust = next24.reduce((m, h) => (h.gust_mph > (m?.gust_mph ?? -1) ? h : m), null);
  if (gust && gust.gust_mph >= S.gustMph) {
    add("warn", `Gusts to ${num(gust.gust_mph)} mph ${fmtDayTime(gust.t)}`, `From ${compass(gust.wind_dir_deg)}. Check gear and boat plans.`);
  }

  // Rain closure watch
  const r = rainTotals();
  const basis = r.past == null ? "next 24 h forecast; no observed rain available"
    : `${num(r.past, 2)} in observed past 24 h + ${num(r.next, 2)} in forecast next 24 h`;
  if (r.total != null && r.total >= S.rainIn24h) {
    add("bad", `Rain closure watch: ${num(r.total, 2)} in`, `${basis}. At or above your ${S.rainIn24h} in threshold. Confirm status with DOH.`);
  } else if (r.total != null && r.total >= S.rainIn24h * 0.6) {
    add("warn", `Rain approaching threshold: ${num(r.total, 2)} in`, `${basis}. Your threshold: ${S.rainIn24h} in.`);
  }

  // Biotoxin
  const closed = shellfishClosures();
  if (closed.length) add("bad", `Recreational biotoxin closure: ${closed[0].name}`, `${closed[0].status}. Check commercial biotoxin sampling results with DOH.`);

  // Farm sensors: in-bag heat while exposed, and sensors that stopped reporting
  const tag = D.sensors?.mock ? " (mock data)" : "";
  for (const s of liveSensors()) {
    if (s.latest.exposed && s.latest.temp_f >= S.heatF) {
      add("bad", `In-bag temp ${num(s.latest.temp_f, 1)}°F at ${s.name}${tag}`,
        `Probe is out of the water at low tide, reading ${ago(s.latest.t)}. At or above your ${S.heatF}°F heat threshold.`);
    }
  }
  for (const s of (D.sensors?.stations || []).filter((x) => x.status !== "live")) {
    add("warn", `Sensor ${s.status}: ${s.name}${tag}`, `Last reading ${ago(s.last_seen)}. Check battery, mount, or gateway.`);
  }

  // Water temperature (Vibrio season, May–Sept). Observed if it is current, else the LiveOcean
  // model surface value; the model forecast adds a heads-up when warm water is on the way.
  const month = Number(new Intl.DateTimeFormat("en-US", { timeZone: TZ, month: "numeric" }).format(new Date()));
  if (month >= 5 && month <= 9) {
    const obs = waterLatest();
    const fresh = obs?.water_temp_f != null && Date.now() - toDate(obs.t) < 6 * 3600e3;
    const cell = modelCell(), cur = cell && nearestHour(cell.series, Date.now());
    const wt = fresh ? obs.water_temp_f : cur?.temp_f;
    const src = fresh ? `Observed at ${obs.station.name}` : "LiveOcean model surface estimate (no current observation)";
    const peak = modelPeak(cell, 72);
    if (wt != null && wt >= S.vibrioF) {
      add("warn", `Water ${num(wt, 1)}°F during Vibrio season`, `${src}. Follow your Vibrio control plan for time-to-temperature after harvest.`);
    } else if (peak && peak.temp_f >= S.vibrioF) {
      add("warn", `Water forecast to reach ${num(peak.temp_f, 1)}°F ${fmtDayTime(peak.t)}`,
        "LiveOcean model surface temperature. Vibrio season: plan time-to-temperature for harvests on warm days.");
    }
  }

  // Freshening at the bay mouth (model salinity): runoff context for the closure watch, not a closure call.
  const fresh = modelFreshening(modelCell());
  if (fresh) {
    add("", `Model shows freshening at the bay mouth: salinity −${num(fresh.drop, 1)} ${fresh.when}`,
      "LiveOcean surface salinity, daily average. A freshwater-runoff signal for context only; closures come from DOH.");
  }

  if (!ul.children.length) add("good", "No flags", "Conditions within your thresholds.");
}

// ---------- tide ----------
function renderTide() {
  $("tide-badge").replaceChildren(sourceBadge(D.meta, "tides"));
  const t = D.tides;
  if (!t) return $("tide-now").replaceChildren(el("p", { class: "muted" }, "Tide data unavailable."));
  const now = tideAt(new Date(), t.hilo);
  const next = t.hilo.filter((h) => toDate(h.t) > Date.now()).slice(0, 4);
  $("tide-now").replaceChildren(
    el("div", { class: "row" },
      el("div", { class: "big" }, now ? num(now.v, 1) : "—", el("small", {}, ` ft ${now ? (now.rising ? "↑ rising" : "↓ falling") : ""}`)),
      ...next.map((h) => el("div", { class: "stat" },
        el("div", { class: "label" }, `${h.type === "L" ? "Low" : "High"} · ${fmtDayTime(h.t)}`),
        el("div", { class: "value" }, `${num(h.v, 1)} ft`)))),
    el("div", { class: "small muted" }, `${t.station.name} (NOAA ${t.station.id}), MLLW`),
  );

  const xs = t.curve.map((p) => toDate(p[0]) / 1e3);
  const ys = t.curve.map((p) => p[1]);
  const thr = xs.map(() => S.lowTideFt);
  const box = $("tide-chart");
  box.replaceChildren();
  new uPlot({
    width: box.clientWidth, height: 160, tzDate: uplotTz, legend: { show: false },
    cursor: { y: false },
    plugins: [nightShade(D.sun), nowLine()],
    scales: { x: { time: true } },
    axes: axes("ft"),
    series: [{},
      { label: "Tide", stroke: cssVar("--series-1"), width: 2, fill: cssVar("--series-1") + "22" },
      { label: "Threshold", stroke: cssVar("--accent-2"), width: 1, dash: [3, 3] }],
  }, [xs, ys, thr], box);
}

function axes(unit, unit2) {
  const ink = cssVar("--muted"), grid = cssVar("--line");
  const base = { stroke: ink, grid: { stroke: grid, width: 1 }, ticks: { stroke: grid }, font: "11px system-ui" };
  const a = [{ ...base }, { ...base, label: unit, size: 44, labelSize: 14 }];
  if (unit2) a.push({ ...base, side: 1, scale: "y2", label: unit2, grid: { show: false }, size: 44, labelSize: 14 });
  return a;
}

// ---------- weather ----------
function nearestObs() {
  return (D.observations?.stations || [])[0];
}

function renderWeather() {
  $("wx-badge").replaceChildren(sourceBadge(D.meta, "forecast"));
  const st = nearestObs();
  const hourly = D.forecast?.hourly || [];
  const today = hourly.filter((h) => toDate(h.t) - Date.now() < 18 * 3600e3);
  const hi = Math.max(...today.map((h) => h.air_temp_f ?? -99));
  const maxG = Math.max(...today.map((h) => h.gust_mph ?? 0));
  const cur = nearestHour(hourly, new Date());
  const obsT = latestValue(st?.series, "air_temp_f");
  const obsW = latestValue(st?.series, "wind_mph");
  const obsD = latestValue(st?.series, "wind_dir_deg");
  const period = D.forecast?.periods?.[0];

  $("wx-now").replaceChildren(
    el("div", { class: "row" },
      el("div", { class: "big" }, num(obsT?.v ?? cur?.air_temp_f), el("small", {}, "°F")),
      el("div", { class: "stat" }, el("div", { class: "label" }, "Wind"),
        el("div", { class: "value" }, `${num(obsW?.v ?? cur?.wind_mph)} mph ${compass(obsD?.v ?? cur?.wind_dir_deg)}`)),
      el("div", { class: "stat" }, el("div", { class: "label" }, "Next 18 h"),
        el("div", { class: "value" }, `${hi > -99 ? num(hi) : "—"}° · gust ${num(maxG)}`))),
    period ? el("p", { class: "small", style: "margin:6px 0" }, el("b", {}, period.name + ": "), period.detailedForecast || period.shortForecast) : "",
    el("div", { class: "small muted" }, st ? `Observed at ${st.name} (${st.distance_km} km away), ${ago(obsT?.t)}` : "Forecast values (no nearby observation)"),
  );

  if (!hourly.length) return;
  const xs = hourly.map((h) => toDate(h.t) / 1e3);
  const box = $("wx-chart");
  box.replaceChildren();
  new uPlot({
    width: box.clientWidth, height: 180, tzDate: uplotTz,
    plugins: [nightShade(D.sun), nowLine()],
    scales: { x: { time: true }, y2: { range: (u, mn, mx) => [0, Math.max(30, mx + 5)] } },
    axes: axes("°F", "mph"),
    series: [{},
      { label: "Air °F", stroke: cssVar("--series-2"), width: 2 },
      { label: "Wind", scale: "y2", stroke: cssVar("--series-3"), width: 1.5 },
      { label: "Gust", scale: "y2", stroke: cssVar("--series-3"), width: 1, dash: [4, 3] }],
  }, [xs, hourly.map((h) => h.air_temp_f), hourly.map((h) => h.wind_mph), hourly.map((h) => h.gust_mph)], box);
}

// ---------- rain ----------
const sumQpf = (hours) => (D.forecast?.hourly || [])
  .filter((h) => toDate(h.t) >= Date.now() - 3600e3 && toDate(h.t) - Date.now() < hours * 3600e3)
  .reduce((a, h) => a + (h.qpf_in || 0), 0);

function rainTotals() {
  // Past 24 h: Stage IV radar/gauge analysis at the site (ends ~2 h ago), else
  // the nearest NWS station that reports hourly precip.
  let past = null, pastSrc = null, through = null;
  if (D.rain?.totals?.h24 != null) {
    past = D.rain.totals.h24;
    pastSrc = "Stage IV radar + gauge estimate at the bay";
    through = D.rain.through;
  } else {
    for (const st of D.observations?.stations || []) {
      const rows = st.series.filter((r) => Date.now() - toDate(r.t) <= 24 * 3600e3 && r.precip_1h_in != null);
      if (rows.length >= 12) {
        // collapse to one value per clock hour (stations may report more often)
        const byHour = {};
        for (const r of rows) byHour[r.t.slice(0, 13)] = Math.max(byHour[r.t.slice(0, 13)] ?? 0, r.precip_1h_in);
        past = Object.values(byHour).reduce((a, b) => a + b, 0);
        pastSrc = st.name;
        break;
      }
    }
  }
  const next = sumQpf(24);
  const total = past == null && !D.forecast ? null : (past || 0) + next;
  return { past, pastSrc, through, next, total };
}

function renderRain() {
  $("rain-badge").replaceChildren(sourceBadge(D.meta, D.rain ? "rain" : "observations"));
  const r = rainTotals();
  const t = D.rain?.totals || {};
  const stat = (label, v) => el("div", { class: "stat" }, el("div", { class: "label" }, label),
    el("div", { class: "value" }, v == null ? "—" : `${num(v, 2)} in`));
  const gauges = D.rain?.gauges || [];
  $("rain-now").replaceChildren(
    el("div", { class: "row" },
      stat("Past 24 h", r.past), stat("Past 72 h", t.h72), stat("Next 24 h", r.next), stat("Next 72 h", sumQpf(72))),
    el("div", { class: "small muted" },
      r.pastSrc ? `Observed: ${r.pastSrc}${r.through ? `, through ${fmtDayTime(r.through)}` : ""}. ` : "No observed rain available. ",
      `Forecast: NWS QPF. Closure-watch threshold: ${S.rainIn24h} in (set below).`),
    gauges.length ? el("details", { class: "small" },
      el("summary", {}, `Nearby CoCoRaHS gauges (${gauges.length})`),
      el("ul", {}, ...gauges.map((g) => el("li", {},
        el("a", { href: g.url, target: "_blank", rel: "noopener" }, g.name), ` · ${num(g.distance_km, 1)} km · `,
        g.latest.trace ? "trace" : `${num(g.latest.precip_in, 2)} in`,
        ` for 24 h to ~7 am ${fmtDay(g.latest.date + "T12:00:00")}`))),
      el("div", { class: "muted" }, "Volunteer gauges, read once a day. Useful as a check on the radar estimate.")) : null,
  );
  renderRainChart();
}

function renderRainChart() {
  // Bars: observed hourly rain (past 72 h) then forecast QPF (next 72 h).
  const box = $("rain-chart");
  box.replaceChildren();
  const now = Date.now();
  const obs = (D.rain?.hourly || []).filter((h) => now - toDate(h.t) <= 72 * 3600e3);
  const fc = (D.forecast?.hourly || []).filter((h) => toDate(h.t) - now < 72 * 3600e3 && toDate(h.t) > now - 3600e3);
  if (!obs.length && !fc.length) return;
  // Stage IV times mark the end of the hour; shift to the start so bars line up with QPF.
  const rows = [
    ...obs.map((h) => [toDate(h.t) / 1e3 - 1800, h.precip_in, null]),
    ...fc.map((h) => [toDate(h.t) / 1e3 + 1800, null, h.qpf_in ?? 0]),
  ].sort((a, b) => a[0] - b[0]);
  const bars = uPlot.paths.bars({ size: [0.9, 12] });
  new uPlot({
    width: box.clientWidth, height: 140, tzDate: uplotTz,
    plugins: [nightShade(D.sun), nowLine()],
    scales: { x: { time: true }, y: { range: (u, mn, mx) => [0, Math.max(0.05, mx * 1.15)] } },
    axes: axes("in/hr"),
    series: [{},
      { label: "Observed in/hr", stroke: cssVar("--series-1"), fill: cssVar("--series-1"), paths: bars, points: { show: false } },
      { label: "Forecast in/hr", stroke: cssVar("--series-3"), fill: cssVar("--series-3") + "80", paths: bars, points: { show: false } }],
  }, [rows.map((r) => r[0]), rows.map((r) => r[1]), rows.map((r) => r[2])], box);
}

// ---------- farm sensors ----------
function liveSensors() {
  return (D.sensors?.stations || []).filter((s) => s.status === "live" && s.latest);
}

function renderSensors() {
  const stations = D.sensors?.stations || [];
  $("sensors-card").hidden = !stations.length;
  if (!stations.length) return;
  $("sensors-badge").replaceChildren(sourceBadge(D.meta, "sensors"));
  const state = (L) => (L?.exposed == null ? "" : L.exposed ? "out of water" : "in water");
  const statusCls = { live: "badge ok", stale: "badge warn", offline: "badge bad" };
  $("sensors-now").replaceChildren(
    D.sensors.mock ? el("div", { class: "mock-banner" }, "Mock data: simulated readings, not real measurements") : "",
    ...stations.map((s) => el("div", { class: "sensor-row" },
      el("div", {}, el("b", {}, s.name), " ", el("span", { class: statusCls[s.status] }, s.status),
        el("div", { class: "small muted" }, `${state(s.latest)}${s.latest ? ` · ${ago(s.latest.t)}` : ""} · ${num(s.elevation_ft, 1)} ft MLLW`)),
      el("div", { class: "value" }, s.latest ? `${num(s.latest.temp_f, 1)}°F` : "—"))),
  );
  sensorChart($("sensors-chart"), stations, { hours: 72, height: 180, sun: D.sun });
}

// ---------- water ----------
// Prefer an on-farm probe that is currently under water; fall back to the nearest public station.
function waterLatest() {
  const farm = liveSensors().find((s) => s.latest.exposed === false && !D.sensors.mock);
  if (farm) return { water_temp_f: farm.latest.temp_f, t: farm.latest.t, station: farm };
  const st = (D.water?.stations || []).find((s) => s.latest);
  return st ? { ...st.latest, station: st } : null;
}

// Compare the current reading with LiveOcean's monthly surface climatology at the bay mouth,
// and with the measured monthly normal from the archival loggers in the Step 4 bag.
const signed = (v, d) => `${v >= 0 ? "+" : "−"}${num(Math.abs(v), d)}`;

function renderNormal(latest) {
  const cell = NORMAL?.cells?.find((c) => c.id === "thorndyke");
  if (!cell) return null;
  const when = latest?.t ? toDate(latest.t) : new Date();
  const month = Number(new Intl.DateTimeFormat("en-US", { timeZone: TZ, month: "numeric" }).format(when));
  const monthName = new Intl.DateTimeFormat("en-US", { timeZone: TZ, month: "long" }).format(when);
  const m = cell.months.find((x) => x.month === month);
  if (!m) return null;
  const normF = cToF(m.surface.temp_c);
  const parts = [];
  if (latest?.water_temp_f != null && normF != null) {
    parts.push(`${signed(latest.water_temp_f - normF, 1)}°F vs. normal (${num(normF, 1)}°F)`);
  }
  if (latest?.salinity_psu != null && m.surface.salt != null) {
    parts.push(`salinity ${signed(latest.salinity_psu - m.surface.salt, 1)} (${num(m.surface.salt, 1)})`);
  }
  const head = parts.length
    ? `${latest.station?.name || "Reading"}: ${parts.join(", ")}`
    : `${monthName} normal: ${num(normF, 1)}°F, salinity ${num(m.surface.salt, 1)}`;
  const far = latest?.station?.distance_km > 15 ? ` ${latest.station.name} is ${latest.station.distance_km} km away, so compare loosely.` : "";
  const farm = HOBO?.monthly?.find((x) => x.month === month);
  let farmLine = null;
  if (farm) {
    const fF = cToF(farm.mean_c);
    const vs = latest?.water_temp_f != null ? ` Reading is ${signed(latest.water_temp_f - fF, 1)}°F vs. the farm.` : "";
    farmLine = el("div", { class: "small" },
      `Farm logger ${monthName} normal: ${num(fF, 1)}°F (${num(cToF(farm.p10_c), 0)}–${num(cToF(farm.p90_c), 0)}°F), ` +
      `Step 4 bag ${farm.years[0]}–${String(farm.years.at(-1)).slice(2)}.${vs}`);
  }
  return el("div", { style: "margin-bottom:8px" },
    el("div", { class: "small" }, head),
    farmLine,
    el("div", { class: "small muted" },
      `Normal = LiveOcean model ${monthName} surface average (${NORMAL.years}) at the Thorndyke Bay mouth; ` +
      `bottom oxygen normal ${num(m.bottom.do_mgl, 1)} mg/L at ${num(m.bottom.depth_m, 0)} m.${far}`));
}

function renderWater() {
  $("water-badge").replaceChildren(sourceBadge(D.meta, "water"));
  const stations = (D.water?.stations || []).filter((s) => s.latest);
  const normal = renderNormal(waterLatest());
  if (!stations.length) {
    return $("water-now").replaceChildren(el("p", { class: "muted small" },
      "No recent water-quality observations near Thorndyke Bay. On-site sensors are planned for Phase 2."),
      ...(normal ? [normal] : []));
  }
  $("water-now").replaceChildren(...stations.slice(0, 3).map((s) => el("div", { style: "margin-bottom:8px" },
    el("div", { class: "row" },
      el("div", { class: "stat" }, el("div", { class: "label" }, "Temp"), el("div", { class: "value" }, `${num(s.latest.water_temp_f, 1)}°F`)),
      el("div", { class: "stat" }, el("div", { class: "label" }, "Salinity"), el("div", { class: "value" }, `${num(s.latest.salinity_psu, 1)}`)),
      el("div", { class: "stat" }, el("div", { class: "label" }, "Oxygen"), el("div", { class: "value" }, s.latest.do_mgl == null ? "—" : `${num(s.latest.do_mgl, 1)} mg/L`))),
    el("div", { class: "small muted" }, `${s.name}${s.distance_km != null ? ` (${s.distance_km} km)` : ""}${s.latest.depth_m != null ? `, ${num(s.latest.depth_m, 0)} m depth` : ""}, ${ago(s.latest.t)}`))),
    ...(normal ? [normal] : []),
    ...(D.water.notes || []).map((n) => el("div", { class: "small muted" }, n)));
}

// ---------- archival bag temperature (HOBO loggers, Step 4) ----------
const fmtDate = (d) => new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });

function renderHobo() {
  const days = hoboDays(HOBO);
  $("hobo-card").hidden = !days.length;
  if (!days.length) return;

  // This week in earlier years: mean water temperature within ±3 days of today's date.
  const today = localDateKey(new Date()).slice(5);
  const doy = (md) => Date.UTC(2001, Number(md.slice(0, 2)) - 1, Number(md.slice(3, 5))) / 864e5;
  const near = (md) => Math.min(Math.abs(doy(md) - doy(today)), 365 - Math.abs(doy(md) - doy(today))) <= 3;
  const byYear = {};
  for (const d of days) {
    if (d.water_mean != null && near(d.date.slice(5))) (byYear[d.date.slice(0, 4)] ||= []).push(d.water_mean);
  }
  const years = Object.entries(byYear).filter(([, v]) => v.length >= 3)
    .map(([y, v]) => el("div", { class: "stat" }, el("div", { class: "label" }, `This week ${y}`),
      el("div", { class: "value" }, `${num(cToF(v.reduce((a, b) => a + b) / v.length), 1)}°F`)));

  const hot = days.filter((d) => cToF(d.bag_max) >= S.heatF);
  const peak = days.reduce((a, b) => (b.bag_max > a.bag_max ? b : a));
  const cold = days.reduce((a, b) => (b.bag_min < a.bag_min ? b : a));
  $("hobo-now").replaceChildren(
    years.length ? el("div", { class: "row" }, ...years) : "",
    el("div", { class: "small", style: "margin-top:6px" },
      `Bag reached your ${S.heatF}°F heat threshold on ${hot.length} day${hot.length === 1 ? "" : "s"}` +
      `${hot.length ? ` (last ${fmtDate(hot.at(-1).date)})` : ""}. Peak ${num(cToF(peak.bag_max), 1)}°F on ${fmtDate(peak.date)}; ` +
      `coldest ${num(cToF(cold.bag_min), 1)}°F on ${fmtDate(cold.date)}.`));
  hoboChart($("hobo-chart"), HOBO, { height: 170 });
  const first = days[0].date, last = days.at(-1).date;
  $("hobo-note").replaceChildren(el("div", { class: "small muted" },
    `HOBO loggers inside a research bag on Step 4 (~${num(HOBO.site.elevation_ft, 0)} ft MLLW), ${fmtDate(first)} to ${fmtDate(last)}. ` +
    "Water = readings while the bag was well covered; bag max/min include low-tide exposure. ",
    el("a", { href: "https://github.com/RobertsLab/acantha/tree/sensor-data/hobo", target: "_blank", rel: "noopener" }, "15-minute data"),
    ", ", el("a", { href: "about.html#hobo" }, "method"), "."));
}

// ---------- water forecast (LiveOcean model) ----------
const modelCell = () => D.liveocean?.cells?.find((c) => c.id === "thorndyke");

// Warmest model hour in the next `hours`.
function modelPeak(cell, hours) {
  const now = Date.now();
  return (cell?.series || []).filter((r) => r.temp_f != null && toDate(r.t) > now && toDate(r.t) - now <= hours * 3600e3)
    .reduce((m, r) => (m == null || r.temp_f > m.temp_f ? r : m), null);
}

// Daily-mean salinity drop of at least S.freshenPsu: past 24 h vs. the 24 h before, or the next 48 h vs. the past 24 h.
function modelFreshening(cell) {
  if (!cell) return null;
  const now = Date.now(), h = 3600e3;
  const mean = (from, to) => {
    const v = cell.series.filter((r) => r.salt != null && toDate(r.t) > now + from * h && toDate(r.t) <= now + to * h).map((r) => r.salt);
    return v.length >= 12 ? v.reduce((a, b) => a + b, 0) / v.length : null;
  };
  const before = mean(-48, -24), last = mean(-24, 0), next = mean(0, 24), later = mean(24, 48);
  const past = before != null && last != null ? before - last : 0;
  const ahead = last != null ? Math.max(...[next, later].filter((v) => v != null).map((v) => last - v), 0) : 0;
  if (past >= S.freshenPsu && past >= ahead) return { drop: past, when: "over the past day" };
  if (ahead >= S.freshenPsu) return { drop: ahead, when: "forecast in the next 2 days" };
  return null;
}

function renderModel() {
  const cell = modelCell();
  $("model-card").hidden = !cell;
  if (!cell) return;
  $("model-badge").replaceChildren(sourceBadge(D.meta, "liveocean"));
  const now = Date.now();
  const cur = nearestHour(cell.series, now);
  const ahead = cell.series.filter((r) => toDate(r.t) > now && toDate(r.t) - now <= 72 * 3600e3);
  const range = (key, d) => {
    const v = ahead.map((r) => r[key]).filter((x) => x != null);
    return v.length ? `${num(Math.min(...v), d)}–${num(Math.max(...v), d)}` : "—";
  };
  const stat = (label, v) => el("div", { class: "stat" }, el("div", { class: "label" }, label), el("div", { class: "value" }, v));
  const pt = (D.water?.stations || []).find((s) => s.series?.length);
  const check = pt && modelVsObs(cell, pt.series);
  const runAge = (now - toDate(D.liveocean.run)) / 3600e3;
  $("model-now").replaceChildren(...[
    el("div", { class: "row" },
      stat("Surface now", cur ? `${num(cur.temp_f, 1)}°F` : "—"),
      stat("Salinity now", cur ? num(cur.salt, 1) : "—"),
      stat("Next 3 days", `${range("temp_f", 0)}°F`),
      stat("Salinity range", range("salt", 1))),
    el("div", { class: "small muted" },
      `UW LiveOcean model, run ${fmtDay(D.liveocean.run)} ${fmtTime(D.liveocean.run)}, forecast to ${fmtDay(D.liveocean.forecast_end)}. ` +
      `Surface water at the ${cell.name} (~500 m grid cell, ${num(cell.depth_m, 0)} m deep). A model estimate, not a measurement.`),
    runAge > 48 ? el("div", { class: "small", style: "color:var(--warn)" }, `The model run is ${num(runAge / 24, 0)} days old; the forecast may be out of date.`) : null,
    check ? el("div", { class: "small muted" },
      `Past 7 days vs. ${pt.name}${pt.distance_km ? ` (${pt.distance_km} km away)` : ""}: ` +
      `model ${signed(check.bias, 1)}°F on average, typical difference ${num(check.rmse, 1)}°F.`) : null,
  ].filter(Boolean));
  const obs = [];
  if (pt) obs.push({ name: pt.name.replace(" (NOAA)", ""), series: pt.series });
  liveoceanChart($("model-chart"), D.liveocean, "thorndyke", { height: 180, sun: D.sun, obs });
}

// ---------- satellite ----------
function renderSatellite() {
  const scenes = satScenes(D.imagery);
  $("sat-card").hidden = !scenes.length;
  if (!scenes.length) return;
  const gen = D.imagery.generated_at;
  const stale = Date.now() - toDate(gen) > 36 * 3600e3;
  $("sat-badge").replaceChildren(el("span", { class: stale ? "badge warn" : "badge ok" }, `updated ${ago(gen)}`));
  const clear = scenes.find((s) => s.id === D.imagery.latest_clear) || scenes[0];
  const latest = scenes[0];
  const days = Math.round((Date.now() - toDate(clear.datetime)) / 86400e3);
  const link = (s, text) => el("a", { href: `#s2=${s.id}`, onclick: () => scrollTo({ top: 0, behavior: "smooth" }) }, text);
  $("sat-now").replaceChildren(
    el("div", { class: "row" },
      el("div", { class: "stat" }, el("div", { class: "label" }, "Last clear view"),
        el("div", { class: "value" }, link(clear, `${fmtDay(clear.datetime)} ${fmtTime(clear.datetime)}`))),
      el("div", { class: "stat" }, el("div", { class: "label" }, "Clear at the bay"), el("div", { class: "value" }, `${num(clear.site_clear_pct, 0)}%`)),
      el("div", { class: "stat" }, el("div", { class: "label" }, "Tide at capture"), el("div", { class: "value" }, `${num(clear.tide_ft, 1)} ft`))),
    el("div", { class: "small muted" },
      `Sentinel-2 true color, 10 m. ${days >= 10 ? `No clear pass in ${days} days (clouds). ` : ""}` +
      `${(D.imagery.scenes || []).length} passes in the last 30 days, ${scenes.length} with usable imagery` +
      (latest.id !== clear.id ? `; latest pass ${fmtDay(latest.datetime)} was ${num(latest.site_clear_pct, 0)}% clear` : "") + ". ",
      link(clear, "Show on map →")),
  );
}

// ---------- shellfish ----------
function shellfishClosures() {
  const z = D.shellfish?.site_zone;
  return z?.closed ? [z] : [];
}

function renderShellfish() {
  $("shellfish-badge").replaceChildren(sourceBadge(D.meta, "shellfish"));
  const sf = D.shellfish;
  const box = $("shellfish-now");
  if (!sf) return box.replaceChildren(el("p", { class: "muted small" }, "Shellfish status unavailable. ",
    el("a", { href: "https://doh.wa.gov/community-and-environment/shellfish", target: "_blank" }, "Check DOH")));
  const z = sf.site_zone, a = sf.site_growing_area;
  const nearby = (sf.beaches || []).filter((b) => b.growing_area && a && b.growing_area === a.name);
  box.replaceChildren(
    el("div", { class: "row" },
      el("div", { class: "stat" }, el("div", { class: "label" }, `Biotoxin zone: ${z?.name ?? "—"}`),
        el("div", { class: "value", style: `color:var(${z?.closed ? "--bad" : "--good"})` }, z ? z.status : "—")),
      el("div", { class: "stat" }, el("div", { class: "label" }, `Growing area: ${a?.name ?? "—"}`),
        el("div", { class: "value" }, a?.classification ?? "—"))),
    nearby.length ? el("details", { class: "small", style: "margin-top:6px" },
      el("summary", {}, `${nearby.length} recreational beaches in ${a.name}`),
      el("ul", { style: "margin:4px 0;padding-left:18px" },
        ...nearby.map((b) => el("li", {}, `${b.name}: ${b.status}${b.closed_for && b.status === "Closed" ? ` (${b.closed_for})` : ""}`)))) : "",
    el("p", { class: "small muted", style: "margin:6px 0" }, `${sf.note} DOH status updated ${ago(sf.status_updated)}.`),
    el("div", { class: "small" }, el("a", { href: sf.source_url, target: "_blank", rel: "noopener" }, "DOH biotoxin information →")),
  );
}

// ---------- settings ----------
function renderSettings() {
  const form = $("settings");
  const fields = [
    ["lowTideFt", "Workable low tide (ft, MLLW) ≤", 0.1],
    ["heatF", "Heat-exposure air temp (°F) ≥", 1],
    ["gustMph", "Wind gust flag (mph) ≥", 1],
    ["rainIn24h", "Rain closure watch (in, 24 h) ≥", 0.05],
    ["vibrioF", "Vibrio water temp (°F, May–Sept) ≥", 1],
    ["freshenPsu", "Model salinity drop note (per day) ≥", 0.1],
  ];
  form.replaceChildren(
    ...fields.flatMap(([k, label, step]) => [
      el("label", { for: `s-${k}` }, label),
      el("input", { id: `s-${k}`, type: "number", step, value: S[k],
        oninput: (e) => { S[k] = parseFloat(e.target.value); saveSettings(S); render(); } }),
    ]),
    el("span", { class: "small muted", style: "grid-column:1/-1" },
      "Set the rain value to your growing area's conditional-closure rule from DOH."),
    el("button", { type: "button", class: "secondary", style: "grid-column:1/-1;justify-self:start",
      onclick: () => { S = { ...DEFAULTS }; saveSettings(S); renderSettings(); render(); } }, "Reset to defaults"),
  );
}

renderSettings();
render();
let rt;
addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(render, 200); });
