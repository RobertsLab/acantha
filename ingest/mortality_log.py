"""File one mortality log entry (a GitHub issue form) into the permanent CSV.

Usage (run by .github/workflows/mortality-log.yml):
    ISSUE_NUMBER=12 ISSUE_AUTHOR=login ISSUE_CREATED_AT=2026-11-25T18:00:00Z ISSUE_BODY=... \\
        python3 ingest/mortality_log.py ARCHIVE_DIR

Growers record a weekly green / yellow / red status with the "Mortality log entry"
issue form (.github/ISSUE_TEMPLATE/mortality-log.yml). This parses the issue body
and writes one row to ARCHIVE_DIR/entries.csv on the `mortality-log` branch, keyed
by issue number, so editing an issue corrects its row. sources/mortality.py reads
that file for the dashboard. How to use it: docs/mortality-log.md

The issue body is untrusted text: every field is validated or trimmed here, and
an entry that fails validation is not written (exit 1, reason on stdout).
"""
from __future__ import annotations

import csv
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))

from config import SITE  # noqa: E402

COLUMNS = ["date", "status", "percent_dead", "location", "ploidy", "notes",
           "reported_by", "issue", "submitted_at"]
STATUSES = ("green", "yellow", "red")
PLOIDY = {"diploid": "diploid", "triploid": "triploid", "mixed": "mixed"}
MAX_NOTES, MAX_LOCATION = 500, 80

README = """# Farm mortality log

Weekly green / yellow / red checks on oyster mortality, one row per entry, written by the
"Mortality log entry" workflow on `main` (`ingest/mortality_log.py`) from the issue form.
How to add an entry: `docs/mortality-log.md` on `main`.

| Column | Meaning |
|---|---|
| `date` | Date observed (local, YYYY-MM-DD) |
| `status` | `green` nothing of concern, `yellow` some concern, `red` very concerned / high mortality |
| `percent_dead` | Rough share dead in what was looked at (0-100); empty if not counted |
| `location` | Where on the farm, or which bag or line |
| `ploidy` | `diploid`, `triploid`, `mixed`, or empty |
| `notes` | Free text, at most 500 characters |
| `reported_by` | GitHub login of the person who filed the entry |
| `issue` | Issue number the entry came from; editing that issue rewrites this row |
| `submitted_at` | When the issue was opened, UTC |
"""


class EntryError(ValueError):
    """The issue is not a usable entry; the message is shown to the person who filed it."""


def _sections(body: str) -> dict[str, str]:
    """Issue forms render as '### Label' followed by the answer."""
    out = {}
    parts = re.split(r"^### +(.+?)\s*$", (body or "").replace("\r\n", "\n"), flags=re.M)
    for label, value in zip(parts[1::2], parts[2::2]):
        value = value.strip()
        out[label.strip().lower()] = "" if value in ("_No response_", "None") else value
    return out


def _one_line(s: str, limit: int) -> str:
    return re.sub(r"\s+", " ", s).strip()[:limit]


def parse(body: str, created_at: str, author: str, number: int) -> dict:
    """Turn an issue-form body into a CSV row (all values str). Raises EntryError."""
    f = _sections(body)
    word = (re.match(r"[a-z]+", f.get("status", "").lower()) or [""])[0]
    if word not in STATUSES:
        raise EntryError("Status must be Green, Yellow, or Red.")

    created = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(timezone.utc)
    today = created.astimezone(ZoneInfo(SITE["timezone"])).date()
    raw = f.get("date observed", "")
    if raw:
        try:
            day = date.fromisoformat(raw)
        except ValueError:
            raise EntryError(f"Date observed must look like {today.isoformat()} (YYYY-MM-DD).") from None
        if day > today + timedelta(days=1):
            raise EntryError("Date observed is in the future.")
    else:
        day = today

    pct = f.get("percent dead", "").rstrip("% ").strip()
    if pct:
        try:
            v = float(pct)
        except ValueError:
            raise EntryError("Percent dead must be a number from 0 to 100.") from None
        if not 0 <= v <= 100:
            raise EntryError("Percent dead must be a number from 0 to 100.")
        pct = f"{v:g}"

    return {
        "date": day.isoformat(),
        "status": word,
        "percent_dead": pct,
        "location": _one_line(f.get("location or bag", ""), MAX_LOCATION),
        "ploidy": PLOIDY.get(f.get("ploidy", "").lower(), ""),
        "notes": _one_line(f.get("notes", ""), MAX_NOTES),
        "reported_by": _one_line(author, 40),
        "issue": str(int(number)),
        "submitted_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def upsert(row: dict, out: Path) -> int:
    """Write row into out/entries.csv, replacing any row from the same issue. Returns the row count."""
    out.mkdir(parents=True, exist_ok=True)
    path = out / "entries.csv"
    rows: dict[str, dict] = {}
    if path.exists():
        with path.open(newline="") as fh:
            rows = {r["issue"]: {c: r.get(c, "") for c in COLUMNS} for r in csv.DictReader(fh)}
    rows[row["issue"]] = row
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: (r["date"], int(r["issue"]))))
    (out / "README.md").write_text(README)
    return len(rows)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    env = os.environ
    try:
        row = parse(env.get("ISSUE_BODY", ""), env["ISSUE_CREATED_AT"], env.get("ISSUE_AUTHOR", ""),
                    int(env["ISSUE_NUMBER"]))
    except EntryError as e:
        print(f"Not logged: {e} Edit this issue to fix it and it will be read again.")
        return 1
    upsert(row, Path(sys.argv[1]))
    pct = f", {row['percent_dead']}% dead" if row["percent_dead"] else ""
    print(f"Logged **{row['status']}** for {row['date']}{pct}. It shows on the portal within about "
          "20 minutes. To correct it, edit this issue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
