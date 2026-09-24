// "Today at Thorndyke" side panel: alerts, decision flags, tide/weather/rain/sensor/water cards.
import {
  loadAll, fmtTime, fmtDayTime, fmtDay, ago, num, compass, el, toDate, tideAt, isDaylight,
  nearestHour, latestValue, getSettings, saveSettings, DEFAULTS, uplotTz, nightShade, nowLine,
  cssVar, sourceBadge, sensorChart,
} from "./common.js";

const $ = (id) => document.getElementById(id);

const D = await loadAll(["meta", "tides", "sun", "forecast", "alerts", "observations", "water", "shellfish", "sensors"]);
let S = getSettings();

function render() {
  renderAlerts();
  renderFlags();
  renderTide();
  renderWeather();
  renderRain();
  renderSensors();
  renderWater();
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
  const basis = r.past == null ? "next 24 h forecast; no observed rain gauge nearby"
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

  // Water temperature (Vibrio season)
  const wt = waterLatest()?.water_temp_f;
  const month = new Date().getMonth() + 1;
  if (wt != null && month >= 5 && month <= 9 && wt >= 60) {
    add("warn", `Water ${num(wt, 1)}°F during Vibrio season`, "Follow your Vibrio control plan for time-to-temperature after harvest.");
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
function rainTotals() {
  // Past 24 h: sum hourly precip from the nearest station that reports it.
  let past = null, pastSt = null;
  for (const st of D.observations?.stations || []) {
    const rows = st.series.filter((r) => Date.now() - toDate(r.t) <= 24 * 3600e3 && r.precip_1h_in != null);
    if (rows.length >= 12) {
      // collapse to one value per clock hour (stations may report more often)
      const byHour = {};
      for (const r of rows) byHour[r.t.slice(0, 13)] = Math.max(byHour[r.t.slice(0, 13)] ?? 0, r.precip_1h_in);
      past = Object.values(byHour).reduce((a, b) => a + b, 0);
      pastSt = st;
      break;
    }
  }
  const next = (D.forecast?.hourly || []).filter((h) => toDate(h.t) - Date.now() < 24 * 3600e3)
    .reduce((a, h) => a + (h.qpf_in || 0), 0);
  const total = past == null && !D.forecast ? null : (past || 0) + next;
  return { past, pastSt, next, total };
}

function renderRain() {
  $("rain-badge").replaceChildren(sourceBadge(D.meta, "observations"));
  const r = rainTotals();
  const next72 = (D.forecast?.hourly || []).filter((h) => toDate(h.t) - Date.now() < 72 * 3600e3)
    .reduce((a, h) => a + (h.qpf_in || 0), 0);
  $("rain-now").replaceChildren(
    el("div", { class: "row" },
      el("div", { class: "stat" }, el("div", { class: "label" }, "Past 24 h"), el("div", { class: "value" }, r.past == null ? "—" : `${num(r.past, 2)} in`)),
      el("div", { class: "stat" }, el("div", { class: "label" }, "Next 24 h"), el("div", { class: "value" }, `${num(r.next, 2)} in`)),
      el("div", { class: "stat" }, el("div", { class: "label" }, "Next 72 h"), el("div", { class: "value" }, `${num(next72, 2)} in`))),
    el("div", { class: "small muted" },
      r.pastSt ? `Observed: ${r.pastSt.name}. ` : "No nearby gauge reporting hourly rain. ",
      `Forecast: NWS QPF. Closure-watch threshold: ${S.rainIn24h} in (set below).`),
  );
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

function renderWater() {
  $("water-badge").replaceChildren(sourceBadge(D.meta, "water"));
  const stations = (D.water?.stations || []).filter((s) => s.latest);
  if (!stations.length) {
    return $("water-now").replaceChildren(el("p", { class: "muted small" },
      "No recent water-quality observations near Thorndyke Bay. On-site sensors are planned for Phase 2."));
  }
  $("water-now").replaceChildren(...stations.slice(0, 3).map((s) => el("div", { style: "margin-bottom:8px" },
    el("div", { class: "row" },
      el("div", { class: "stat" }, el("div", { class: "label" }, "Temp"), el("div", { class: "value" }, `${num(s.latest.water_temp_f, 1)}°F`)),
      el("div", { class: "stat" }, el("div", { class: "label" }, "Salinity"), el("div", { class: "value" }, `${num(s.latest.salinity_psu, 1)}`)),
      el("div", { class: "stat" }, el("div", { class: "label" }, "Oxygen"), el("div", { class: "value" }, s.latest.do_mgl == null ? "—" : `${num(s.latest.do_mgl, 1)} mg/L`))),
    el("div", { class: "small muted" }, `${s.name}${s.distance_km != null ? ` (${s.distance_km} km)` : ""}${s.latest.depth_m != null ? `, ${num(s.latest.depth_m, 0)} m depth` : ""}, ${ago(s.latest.t)}`))),
    ...(D.water.notes || []).map((n) => el("div", { class: "small muted" }, n)));
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
