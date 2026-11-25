"""python3 -m unittest discover ingest/tests"""
import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mortality_log import COLUMNS, EntryError, parse, upsert  # noqa: E402
from sources.mortality import _mock, summarize  # noqa: E402

CREATED = "2026-11-26T02:30:00Z"  # 6:30 pm Nov 25 Pacific


def body(status="Yellow: some concern", day="_No response_", pct="_No response_",
         loc="_No response_", ploidy="None", notes="_No response_"):
    return (f"### Status\n\n{status}\n\n### Date observed\n\n{day}\n\n### Percent dead\n\n{pct}\n\n"
            f"### Location or bag\n\n{loc}\n\n### Ploidy\n\n{ploidy}\n\n### Notes\n\n{notes}\n")


def entry(**kw):
    return parse(body(**kw), CREATED, "grower", 7)


class ParseTest(unittest.TestCase):
    def test_minimal_entry_uses_local_date_of_submission(self):
        row = entry()
        self.assertEqual(row["status"], "yellow")
        self.assertEqual(row["date"], "2026-11-25")  # local day, not the UTC day
        self.assertEqual(row["submitted_at"], CREATED)
        self.assertEqual((row["percent_dead"], row["location"], row["ploidy"], row["notes"]), ("", "", "", ""))
        self.assertEqual(set(row), set(COLUMNS))

    def test_full_entry(self):
        row = entry(status="Red: very concerned, seeing high mortality", day="2026-11-20", pct="32.50 %",
                    loc="Step 4 bag", ploidy="Triploid", notes="Gapers on the\r\nupper line.\n\nSmell.")
        self.assertEqual(row["status"], "red")
        self.assertEqual(row["date"], "2026-11-20")
        self.assertEqual(row["percent_dead"], "32.5")
        self.assertEqual(row["ploidy"], "triploid")
        self.assertEqual(row["notes"], "Gapers on the upper line. Smell.")

    def test_not_sure_ploidy_is_blank(self):
        self.assertEqual(entry(ploidy="Not sure")["ploidy"], "")

    def test_long_text_is_trimmed(self):
        row = entry(notes="x" * 900, loc="y" * 200)
        self.assertEqual((len(row["notes"]), len(row["location"])), (500, 80))

    def test_rejects_bad_fields(self):
        for kw in ({"status": "Purple"}, {"status": "_No response_"}, {"day": "11/20/2026"},
                   {"day": "2026-12-25"}, {"pct": "lots"}, {"pct": "140"}, {"pct": "-3"}):
            with self.subTest(kw), self.assertRaises(EntryError):
                entry(**kw)

    def test_body_that_is_not_the_form(self):
        with self.assertRaises(EntryError):
            parse("The site is down again", CREATED, "someone", 3)
        with self.assertRaises(EntryError):
            parse(None, CREATED, "someone", 3)


class UpsertTest(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp()) / "log"

    def rows(self):
        with (self.out / "entries.csv").open(newline="") as f:
            return list(csv.DictReader(f))

    def test_appends_sorted_by_date_and_edit_replaces(self):
        upsert(parse(body(day="2026-11-20"), CREATED, "a", 2), self.out)
        upsert(parse(body(day="2026-11-06", status="Green: nothing of concern"), CREATED, "a", 3), self.out)
        self.assertEqual([r["issue"] for r in self.rows()], ["3", "2"])
        n = upsert(parse(body(day="2026-11-20", status="Red: very concerned", notes='said "bad", =1+1'),
                         CREATED, "a", 2), self.out)
        rows = self.rows()
        self.assertEqual(n, 2)
        self.assertEqual(rows[1]["status"], "red")
        self.assertEqual(rows[1]["notes"], 'said "bad", =1+1')  # commas and quotes survive the CSV
        self.assertTrue((self.out / "README.md").exists())


class SummarizeTest(unittest.TestCase):
    TODAY = date(2026, 11, 25)  # a Wednesday; the week starts Mon Nov 23

    def row(self, day, status, issue, **kw):
        return {"date": day, "status": status, "issue": str(issue), "percent_dead": "", **kw}

    def test_empty_log(self):
        s = summarize([], self.TODAY)
        self.assertIsNone(s["latest"])
        self.assertEqual((s["entries"], s["total"], len(s["weeks"])), ([], 0, 12))
        self.assertEqual(s["weeks"][-1], {"start": "2026-11-23", "status": None, "n": 0})

    def test_weeks_take_the_worst_status(self):
        s = summarize([
            self.row("2026-11-16", "green", 1),
            self.row("2026-11-22", "red", 2, percent_dead="30"),   # Sunday: still the week of Nov 16
            self.row("2026-11-24", "yellow", 3),
            self.row("2025-06-01", "red", 4),                      # too old for the page, still counted
            {"date": "soon", "status": "green", "issue": "5"},     # unreadable rows are skipped
            self.row("2026-11-24", "purple", 6),
        ], self.TODAY)
        self.assertEqual(s["weeks"][-1], {"start": "2026-11-23", "status": "yellow", "n": 1})
        self.assertEqual(s["weeks"][-2], {"start": "2026-11-16", "status": "red", "n": 2})
        self.assertEqual(s["weeks"][0]["start"], "2026-09-07")
        self.assertEqual(s["latest"]["issue"], 3)
        self.assertEqual([e["issue"] for e in s["entries"]], [3, 2, 1])
        self.assertEqual(s["entries"][1]["percent_dead"], 30.0)
        self.assertEqual(s["total"], 4)

    def test_mock_rows_summarize(self):
        s = summarize(_mock(self.TODAY), self.TODAY)
        self.assertEqual(s["latest"]["date"], "2026-11-25")
        self.assertIn("red", [w["status"] for w in s["weeks"]])


if __name__ == "__main__":
    unittest.main()
