# Farm mortality log

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
