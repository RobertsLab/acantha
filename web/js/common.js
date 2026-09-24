// Shared helpers: data loading, time formatting, user settings, tide math.

export const TZ = "America/Los_Angeles";

const cache = {};
export async function load(name) {
  if (!cache[name]) {
    cache[name] = fetch(`data/${name}.json`, { cache: "no-cache" })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null);
  }
  return cache[name];
}

export async function loadAll(names) {
  const vals = await Promise.all(names.map(load));
  return Object.fromEntries(names.map((n, i) => [n, vals[i]]));
}

// ---------- time ----------
const fmtCache = {};
function fmt(opts) {
  const k = JSON.stringify(opts);
  return (fmtCache[k] ||= new Intl.DateTimeFormat("en-US", { timeZone: TZ, ...opts }));
}
export const toDate = (s) => (s instanceof Date ? s : new Date(s));
export const fmtTime = (s) => fmt({ hour: "numeric", minute: "2-digit" }).format(toDate(s));
export const fmtDay = (s) => fmt({ weekday: "short", month: "short", day: "numeric" }).format(toDate(s));
export const fmtDayTime = (s) =>
  fmt({ weekday: "short", hour: "numeric", minute: "2-digit" }).format(toDate(s));
export const localDateKey = (s) => fmt({ year: "numeric", month: "2-digit", day: "2-digit" })
  .format(toDate(s)).replace(/(\d+)\/(\d+)\/(\d+)/, "$3-$1-$2");

export function ago(s) {
  if (!s) return "never";
  const min = Math.round((Date.now() - toDate(s)) / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const h = Math.round(min / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.round(h / 24)} d ago`;
}

export function uplotTz(ts) {
  return uPlot.tzDate(new Date(ts * 1e3), TZ);
}

// ---------- settings ----------
export const DEFAULTS = {
  lowTideFt: 0.0,     // "workable" low tide threshold (ft MLLW)
  heatF: 75,          // air temp at low tide that raises a heat-exposure flag
  rainIn24h: 1.0,     // placeholder — set to your growing area's DOH rule
  gustMph: 20,        // gust that raises a wind flag
};

export function getSettings() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem("acantha-settings") || "{}") };
  } catch {
    return { ...DEFAULTS };
  }
}
export function saveSettings(s) {
  try { localStorage.setItem("acantha-settings", JSON.stringify(s)); } catch {}
}

// ---------- tides & sun ----------
export function isDaylight(t, sun) {
  const key = localDateKey(t);
  const d = sun?.days?.find((x) => x.date === key);
  if (!d) return null;
  const ts = toDate(t);
  return ts >= toDate(d.sunrise) && ts <= toDate(d.sunset);
}

// Tide height at time t by cosine interpolation between hi/lo predictions.
export function tideAt(t, hilo) {
  const ms = toDate(t).getTime();
  for (let i = 0; i < hilo.length - 1; i++) {
    const a = toDate(hilo[i].t).getTime(), b = toDate(hilo[i + 1].t).getTime();
    if (ms >= a && ms <= b) {
      const f = (ms - a) / (b - a);
      const v = hilo[i].v + (hilo[i + 1].v - hilo[i].v) * (1 - Math.cos(Math.PI * f)) / 2;
      return { v, rising: hilo[i + 1].v > hilo[i].v, next: hilo[i + 1] };
    }
  }
  return null;
}

export function nearestHour(series, t) {
  const ms = toDate(t).getTime();
  let best = null, bd = Infinity;
  for (const r of series || []) {
    const d = Math.abs(toDate(r.t).getTime() - ms);
    if (d < bd) { bd = d; best = r; }
  }
  return bd <= 90 * 60000 ? best : null;
}

// Latest non-null value for a field across an observation series.
export function latestValue(series, key) {
  for (let i = (series?.length || 0) - 1; i >= 0; i--) {
    if (series[i][key] != null) return { v: series[i][key], t: series[i].t };
  }
  return null;
}

export const compass = (deg) =>
  deg == null ? "" : ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"][
    Math.round(deg / 22.5) % 16];

export const num = (v, d = 0) => (v == null || Number.isNaN(v) ? "—" : Number(v).toFixed(d));

export function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "html") e.innerHTML = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v != null) e.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null) e.append(k.nodeType ? k : document.createTextNode(k));
  return e;
}

// uPlot plugin: shade night-time using sunrise/sunset.
export function nightShade(sun) {
  return {
    hooks: {
      drawClear: (u) => {
        if (!sun?.days) return;
        const { ctx, bbox } = u;
        const style = getComputedStyle(document.documentElement).getPropertyValue("--night").trim();
        ctx.save();
        ctx.fillStyle = style || "rgba(0,0,0,.06)";
        const days = sun.days;
        for (let i = 0; i < days.length - 1; i++) {
          const x0 = u.valToPos(toDate(days[i].sunset) / 1e3, "x", true);
          const x1 = u.valToPos(toDate(days[i + 1].sunrise) / 1e3, "x", true);
          const a = Math.max(x0, bbox.left), b = Math.min(x1, bbox.left + bbox.width);
          if (b > a) ctx.fillRect(a, bbox.top, b - a, bbox.height);
        }
        ctx.restore();
      },
    },
  };
}

export function nowLine() {
  return {
    hooks: {
      draw: (u) => {
        const x = u.valToPos(Date.now() / 1e3, "x", true);
        if (x < u.bbox.left || x > u.bbox.left + u.bbox.width) return;
        const { ctx } = u;
        ctx.save();
        ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--accent-2").trim();
        ctx.setLineDash([4, 4]);
        ctx.lineWidth = 1.5 * devicePixelRatio;
        ctx.beginPath();
        ctx.moveTo(x, u.bbox.top);
        ctx.lineTo(x, u.bbox.top + u.bbox.height);
        ctx.stroke();
        ctx.restore();
      },
    },
  };
}

export const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

export function sourceBadge(meta, key) {
  const s = meta?.sources?.[key];
  if (!s) return el("span", { class: "badge muted" }, "no data");
  const stale = s.fetched_at && Date.now() - toDate(s.fetched_at) > 3 * 3600e3;
  const cls = !s.ok ? "badge bad" : stale ? "badge warn" : "badge ok";
  return el("span", { class: cls, title: s.error || "" }, s.ok ? `updated ${ago(s.fetched_at)}` :
    `source error · last good ${ago(s.fetched_at)}`);
}
