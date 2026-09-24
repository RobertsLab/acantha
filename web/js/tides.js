// Tide windows page: calendar of daylight low tides and an .ics export.
import {
  loadAll, fmtTime, fmtDay, localDateKey, num, el, toDate, isDaylight, getSettings, saveSettings,
  uplotTz, nightShade, nowLine, cssVar, sourceBadge,
} from "./common.js";

const D = await loadAll(["meta", "tides", "sun"]);
const S = getSettings();
const thr = document.getElementById("thr");
const daylight = document.getElementById("daylight");
thr.value = S.lowTideFt;

document.getElementById("badge").replaceChildren(sourceBadge(D.meta, "tides"));
if (D.tides) {
  document.getElementById("station").textContent =
    `${D.tides.station.name}, NOAA station ${D.tides.station.id}. Heights in feet above MLLW. Times Pacific.`;
}

function windows() {
  const lim = parseFloat(thr.value);
  return (D.tides?.hilo || []).filter((h) => h.type === "L" && toDate(h.t) >= Date.now() - 6 * 3600e3)
    .map((h) => ({ ...h, day: isDaylight(h.t, D.sun), hit: h.v <= lim }));
}

function renderCal() {
  const byDay = {};
  for (const l of windows()) (byDay[localDateKey(l.t)] ||= []).push(l);
  const cal = document.getElementById("cal");
  cal.replaceChildren(...Object.entries(byDay).map(([k, lows]) => {
    const work = lows.some((l) => l.hit && (l.day || !daylight.checked));
    const sun = D.sun?.days.find((d) => d.date === k);
    return el("div", { class: "day" + (work ? " work" : "") },
      el("h3", {}, fmtDay(lows[0].t)),
      ...lows.map((l) => el("div", { class: "low" + (l.hit && (l.day || !daylight.checked) ? " hit" : "") + (l.day ? "" : " night") },
        `${fmtTime(l.t)} · ${num(l.v, 1)} ft${l.day ? "" : " ☾"}`)),
      sun ? el("div", { class: "small muted" }, `☀ ${fmtTime(sun.sunrise)}–${fmtTime(sun.sunset)}`) : "");
  }));
}

function renderChart() {
  const h = D.tides?.hilo || [];
  if (!h.length) return;
  const box = document.getElementById("chart");
  box.replaceChildren();
  // Densify with cosine interpolation for a smooth line
  const xs = [], ys = [];
  for (let i = 0; i < h.length - 1; i++) {
    const a = toDate(h[i].t) / 1e3, b = toDate(h[i + 1].t) / 1e3;
    for (let k = 0; k < 12; k++) {
      const f = k / 12;
      xs.push(a + (b - a) * f);
      ys.push(h[i].v + (h[i + 1].v - h[i].v) * (1 - Math.cos(Math.PI * f)) / 2);
    }
  }
  const lim = parseFloat(thr.value);
  const muted = cssVar("--muted"), grid = cssVar("--line");
  const ax = { stroke: muted, grid: { stroke: grid }, ticks: { stroke: grid }, font: "11px system-ui" };
  new uPlot({
    width: box.clientWidth, height: 240, tzDate: uplotTz, legend: { show: false },
    plugins: [nightShade(D.sun), nowLine()],
    axes: [ax, { ...ax, label: "ft", size: 44 }],
    series: [{}, { stroke: cssVar("--series-1"), width: 1.5, fill: cssVar("--series-1") + "18" },
      { stroke: cssVar("--accent-2"), dash: [3, 3], width: 1 }],
  }, [xs, ys, xs.map(() => lim)], box);
}

function ics() {
  const stamp = (s) => toDate(s).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//acantha//Thorndyke tides//EN", "CALSCALE:GREGORIAN"];
  for (const l of windows().filter((l) => l.hit && (l.day || !daylight.checked))) {
    const t = toDate(l.t);
    lines.push("BEGIN:VEVENT", `UID:${stamp(l.t)}-thorndyke@acantha`, `DTSTAMP:${stamp(new Date())}`,
      `DTSTART:${stamp(new Date(t - 90 * 60000))}`, `DTEND:${stamp(new Date(+t + 90 * 60000))}`,
      `SUMMARY:Low tide ${l.v.toFixed(1)} ft (Thorndyke)`,
      `DESCRIPTION:Predicted low ${l.v.toFixed(1)} ft MLLW at ${fmtTime(l.t)}\\, NOAA ${D.tides.station.id} ${D.tides.station.name}. Window ±90 min.`,
      "END:VEVENT");
  }
  lines.push("END:VCALENDAR");
  const a = el("a", { href: URL.createObjectURL(new Blob([lines.join("\r\n")], { type: "text/calendar" })), download: "thorndyke-low-tides.ics" });
  document.body.append(a); a.click(); a.remove();
}

thr.addEventListener("input", () => { S.lowTideFt = parseFloat(thr.value); saveSettings(S); renderCal(); renderChart(); });
daylight.addEventListener("change", renderCal);
document.getElementById("ics").addEventListener("click", ics);
renderCal();
renderChart();
