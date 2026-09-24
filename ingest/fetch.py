"""Fetch all public data sources and write JSON files for the static site.

Usage:
    python3 ingest/fetch.py [--out web/data] [--fallback-url https://.../data]

Each source is fetched independently; one failing source never blocks the
others. If a source fails and --fallback-url is given, the previously
published file is reused so the site keeps showing the last good data
(its age is visible in meta.json and on the page).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import SITE  # noqa: E402
from sources import doh, nws, rain, sensors, sun, tides, water  # noqa: E402
from sources.common import iso, utcnow  # noqa: E402

SOURCES = {
    "tides": tides.fetch,
    "sun": sun.fetch,
    "forecast": nws.forecast,
    "alerts": nws.alerts,
    "observations": nws.observations,
    "rain": rain.fetch,
    "shellfish": doh.fetch,
    "water": water.fetch,
    "sensors": sensors.fetch,  # after tides: uses tides.json to flag low-tide exposure
}

# Sources that take a Context argument (previous output, other sources' output).
WITH_CONTEXT = {"sensors"}


def load_fallback(base: str, name: str):
    try:
        with urllib.request.urlopen(f"{base.rstrip('/')}/{name}.json", timeout=20) as r:
            return json.load(r)
    except Exception:
        return None


class Context:
    """Lets a source read its previously published output and files written earlier in this run."""

    def __init__(self, out: Path, fallback_url: str | None):
        self.out, self.fallback_url = out, fallback_url

    def current(self, name: str):
        p = self.out / f"{name}.json"
        return json.loads(p.read_text()) if p.exists() else None

    def previous(self, name: str):
        cur = self.current(name)
        if cur is not None or not self.fallback_url:
            return cur
        return load_fallback(self.fallback_url, name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent.parent / "web" / "data"))
    ap.add_argument("--fallback-url", default=None)
    ap.add_argument("--only", nargs="*", help="fetch only these sources")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    prev_meta = {}
    if (out / "meta.json").exists():
        prev_meta = json.loads((out / "meta.json").read_text()).get("sources", {})
    elif args.fallback_url:
        prev_meta = (load_fallback(args.fallback_url, "meta") or {}).get("sources", {})

    status = dict(prev_meta)
    ctx = Context(out, args.fallback_url)
    for name, fn in SOURCES.items():
        if args.only and name not in args.only:
            continue
        t0 = time.time()
        try:
            data = fn(ctx) if name in WITH_CONTEXT else fn()
            data["fetched_at"] = iso(utcnow())
            (out / f"{name}.json").write_text(json.dumps(data, separators=(",", ":")))
            status[name] = {"ok": True, "fetched_at": data["fetched_at"],
                            "seconds": round(time.time() - t0, 1)}
            print(f"[ok]   {name:13s} {time.time() - t0:5.1f}s")
        except Exception as e:
            traceback.print_exc()
            prev = status.get(name, {})
            status[name] = {"ok": False, "error": f"{type(e).__name__}: {e}",
                            "attempted_at": iso(utcnow()),
                            "fetched_at": prev.get("fetched_at")}
            if args.fallback_url and not (out / f"{name}.json").exists():
                old = load_fallback(args.fallback_url, name)
                if old is not None:
                    (out / f"{name}.json").write_text(json.dumps(old, separators=(",", ":")))
                    status[name]["using_fallback"] = True
            print(f"[FAIL] {name:13s} {e}")

    meta = {"site": SITE, "generated_at": iso(utcnow()), "sources": status}
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    return 0 if any(s.get("ok") for s in status.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
