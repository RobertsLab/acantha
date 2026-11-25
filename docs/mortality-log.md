# Mortality log

A weekly green / yellow / red check on oyster mortality at the farm, kept so there is a dated
record to compare against the temperature and water data later. It is a record, not a forecast.
The idea follows the grower stop-light survey run by the
[VIMS Shellfish Aquaculture Program](https://www.vims.edu/research/units/programs/sap/oyster-mortality/).

## Adding an entry (growers)

1. On the portal, open the **Mortality log** card and tap **Log this week**. It opens a short
   form on GitHub; sign in with an account that has write access to this repository.
2. Pick a status. Everything else is optional.
3. Submit. A workflow files the entry, replies on the issue, and closes it. The portal shows
   it within about 20 minutes.

| Status | Meaning |
|---|---|
| Green | Nothing of concern |
| Yellow | Some concern |
| Red | Very concerned, seeing high mortality |

| Field | Notes |
|---|---|
| Date observed | `YYYY-MM-DD`; blank means the day you submit |
| Percent dead | Rough share dead in what you looked at, 0 to 100 |
| Location or bag | Where on the farm, or which bag or line |
| Ploidy | Diploid, triploid, or mixed |
| Notes | Size class, gapers, smell, fouling, recent handling; the first 500 characters are kept |

- **One entry a week is the aim**, on the same day if you can. Log green weeks too: a week with
  no entry is a gap, not a good week.
- **To correct an entry, edit its issue.** The row is rewritten. If the form was filled in
  wrong (a bad date or percent), the workflow says why and leaves the issue open for editing.
- **Entries are public**, like the rest of this repository and the portal.

## Where it goes

- The permanent record is [`entries.csv`](https://github.com/RobertsLab/acantha/blob/mortality-log/entries.csv)
  on the `mortality-log` branch, one row per entry. The branch is created by the first entry.
- The portal shows the latest entry and a 12-week strip. Each week takes the worst status
  logged that week. A yellow or red entry also stays in **Today's flags** for 10 days.
- [`data/mortality.json`](https://robertslab.github.io/acantha/data/mortality.json) holds the
  last year of entries.

## Setup (maintainers)

Nothing to configure. The pieces:

| File | Role |
|---|---|
| `.github/ISSUE_TEMPLATE/mortality-log.yml` | The form |
| `.github/workflows/mortality-log.yml` | Runs when a form issue is opened or edited; checks the author has write access, files the entry, comments, closes |
| `ingest/mortality_log.py` | Validates the form and writes the CSV row |
| `ingest/sources/mortality.py` | Reads the CSV for the dashboard |

- Give growers **write** access to the repository so their entries are accepted. An entry from
  anyone else is closed without being logged.
- To remove an entry, delete its row from `entries.csv` on the `mortality-log` branch.
- Preview the card without real entries: `MORTALITY_MOCK=1 python3 ingest/fetch.py --only mortality`.
