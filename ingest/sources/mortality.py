"""Farm mortality log: weekly green / yellow / red checks filed by growers.

Entries are filed with a GitHub issue form and kept in entries.csv on the
`mortality-log` branch (ingest/mortality_log.py, docs/mortality-log.md). This
reads that file and publishes the recent entries plus a week-by-week strip.

It is a record, not a forecast: the point is to have dated mortality
observations to compare against the temperature and water data later.

    MORTALITY_MOCK=1 python3 ingest/fetch.py --only mortality    fake entries for layout work
"""
from __future__ import annotations

import csv
import io
import os
import urllib.error
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from config import GITHUB_REPO, MORTALITY_BRANCH, MORTALITY_KEEP_DAYS, MORTALITY_WEEKS, SITE
from sources.common import get_text, utcnow

RANK = {"green": 0, "yellow": 1, "red": 2}
CSV_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{MORTALITY_BRANCH}/entries.csv"


def _entry(r: dict) -> dict | None:
    """One CSV row -> JSON entry; rows that don't parse are skipped rather than failing the source."""
    try:
        date.fromisoformat(r["date"])
        if r["status"] not in RANK:
            return None
        return {
            "date": r["date"],
            "status": r["status"],
            "percent_dead": float(r["percent_dead"]) if r.get("percent_dead") else None,
            "location": r.get("location") or None,
            "ploidy": r.get("ploidy") or None,
            "notes": r.get("notes") or None,
            "issue": int(r["issue"]) if r.get("issue") else None,
        }
    except (KeyError, ValueError):
        return None


def summarize(rows: list[dict], today: date) -> dict:
    """Recent entries (newest first) and the last MORTALITY_WEEKS Monday-start weeks, oldest first."""
    entries = [e for e in map(_entry, rows) if e]
    entries.sort(key=lambda e: (e["date"], e["issue"] or 0), reverse=True)
    cutoff = (today - timedelta(days=MORTALITY_KEEP_DAYS)).isoformat()
    recent = [e for e in entries if e["date"] >= cutoff]

    this_week = today - timedelta(days=today.weekday())
    weeks = []
    for i in range(MORTALITY_WEEKS - 1, -1, -1):
        start = this_week - timedelta(weeks=i)
        end = (start + timedelta(days=6)).isoformat()
        in_week = [e for e in entries if start.isoformat() <= e["date"] <= end]
        worst = max(in_week, key=lambda e: RANK[e["status"]], default=None)
        weeks.append({"start": start.isoformat(), "status": worst and worst["status"], "n": len(in_week)})
    return {"entries": recent, "latest": entries[0] if entries else None, "weeks": weeks,
            "total": len(entries)}


def _mock(today: date) -> list[dict]:
    pattern = ["green", "green", "", "green", "yellow", "yellow", "red", "yellow", "green", "", "green", "yellow"]
    monday = today - timedelta(days=today.weekday())
    rows = []
    for i, status in enumerate(pattern):
        day = min(monday - timedelta(weeks=len(pattern) - 1 - i) + timedelta(days=3), today)
        if status:
            rows.append({"date": day.isoformat(), "status": status,
                         "percent_dead": {"green": "", "yellow": "5", "red": "30"}[status],
                         "location": "Step 4 bag", "ploidy": "triploid",
                         "notes": "" if status == "green" else "Some gapers on the upper line.",
                         "issue": str(100 + i)})
    return rows


def fetch() -> dict:
    today = utcnow().astimezone(ZoneInfo(SITE["timezone"])).date()
    mock = os.environ.get("MORTALITY_MOCK") == "1"
    if mock:
        rows = _mock(today)
    else:
        try:
            rows = list(csv.DictReader(io.StringIO(get_text(CSV_URL, timeout=30))))
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            rows = []  # no entry has been filed yet, so the branch does not exist
    return {
        "configured": True,
        "mock": mock,
        **summarize(rows, today),
        "log_url": f"https://github.com/{GITHUB_REPO}/issues/new?template=mortality-log.yml",
        "archive_url": f"https://github.com/{GITHUB_REPO}/blob/{MORTALITY_BRANCH}/entries.csv",
    }
