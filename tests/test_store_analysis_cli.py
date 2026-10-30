import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from cp_training_tracker import analysis, dashboard, importers
from cp_training_tracker.cli import main
from cp_training_tracker.db import Store, TrackerError, normalize_tags, parse_ref


def seed(store):
    """A small history: strong at greedy/math, weak at dp/graphs."""
    data = [
        ("cf:1A", 800, "math", "AC", "none", "2026-03-01"),
        ("cf:2A", 1000, "greedy", "AC", "none", "2026-03-01"),
        ("cf:3A", 1200, "greedy,math", "AC", "none", "2026-03-02"),
        ("cf:4A", 1400, "greedy", "AC", "none", "2026-03-03"),
        ("cf:5A", 1300, "dp", "WA", "none", "2026-03-03"),
        ("cf:5A", 1300, "dp", "AC", "editorial", "2026-03-04"),
        ("cf:6A", 1200, "dp", "TLE", "none", "2026-03-04"),
        ("cf:7A", 1500, "graphs,dp", "WA", "none", "2026-03-05"),
        ("cf:8A", 1100, "graphs", "WA", "none", "2026-03-05"),
        ("cf:8A", 1100, "graphs", "WA", "none", "2026-03-05"),
        ("cf:8A", 1100, "graphs", "AC", "none", "2026-03-06"),
        ("cf:9A", 1600, "math", "AC", "none", "2026-03-08"),
    ]
    for ref, d, tags, verdict, help_, day in data:
        pid = store.problem_by_ref(ref, create=True, difficulty=d, tags=tags.split(","))
        store.log(pid, verdict, day, 30, help_)


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class TestStore(unittest.TestCase):
    def test_refs(self):
        self.assertEqual(parse_ref("https://codeforces.com/contest/1520/problem/a")[:2], ("cf", "1520A"))
        self.assertEqual(parse_ref("https://codeforces.com/problemset/problem/4/A")[:2], ("cf", "4A"))
        self.assertEqual(parse_ref("https://atcoder.jp/contests/abc300/tasks/abc300_a")[:2], ("atcoder", "abc300_a"))
        self.assertEqual(parse_ref("https://cses.fi/problemset/task/1068")[:2], ("cses", "1068"))
        self.assertEqual(parse_ref("codeforces:1520a")[:2], ("cf", "1520A"))
        self.assertEqual(parse_ref("lc:two-sum")[:2], ("leetcode", "two-sum"))
        with self.assertRaises(TrackerError):
            parse_ref("nonsense")

    def test_upsert_merges(self):
        s = Store()
        pid = s.upsert_problem("cf", "1A", tags=["Math"])
        self.assertEqual(s.upsert_problem("cf", "1A", name="Theatre", difficulty=1000, tags="brute force"), pid)
        p = s.problem(pid)
        self.assertEqual((p["name"], p["difficulty"], p["tags"]), ("Theatre", 1000, "brute-force,math"))
        self.assertEqual(normalize_tags("DP; Graphs|dp"), ["dp", "graphs"])
        with self.assertRaises(TrackerError):
            s.problem_by_ref("cf:999Z")
        with self.assertRaises(TrackerError):
            s.log(pid, "maybe")
        with self.assertRaises(TrackerError):
            s.log(pid, "AC", "03/01/2026")

    def test_summaries(self):
        s = Store()
        seed(s)
        sums = s.problem_summaries()
        by_code = {v["problem"]["code"]: v for v in sums.values()}
        self.assertEqual(by_code["8A"]["tries_to_ac"], 3)
        self.assertTrue(by_code["5A"]["solved"])
        self.assertFalse(by_code["5A"]["clean"])
        self.assertFalse(by_code["7A"]["solved"])


class TestAnalysis(unittest.TestCase):
    def setUp(self):
        self.s = Store()
        seed(self.s)

    def test_overall_and_tags(self):
        ov = analysis.overall_stats(self.s)
        self.assertEqual((ov["attempted"], ov["solved"], ov["clean"], ov["attempts"]), (9, 7, 6, 12))
        stats, overall = analysis.tag_stats(self.s)
        self.assertEqual(stats["greedy"]["clean"], 3)
        self.assertEqual(stats["dp"]["attempted"], 3)
        self.assertEqual(stats["dp"]["clean"], 0)
        self.assertAlmostEqual(overall, 6 / 9)
        self.assertLess(stats["dp"]["rate"], stats["greedy"]["rate"])

    def test_weaknesses_and_recommendation(self):
        weak = analysis.weaknesses(self.s)
        self.assertEqual(weak[0]["tag"], "dp")
        self.assertIn("graphs", [w["tag"] for w in weak[:2]])
        self.assertTrue(any("clean-solve rate" in r for r in weak[0]["reasons"]))
        rec = analysis.recommend(self.s)
        self.assertIn("dp", rec["tags"])
        lo, hi = rec["difficulty"]
        self.assertEqual(hi - lo, 200)
        self.assertTrue(900 <= lo <= 1700)

    def test_streaks_progress_histogram(self):
        self.assertEqual(analysis.streaks(["2026-03-01", "2026-03-02", "2026-03-03", "2026-03-05"], "2026-03-06"),
                         (1, 3))
        self.assertEqual(analysis.streaks(["2026-03-01", "2026-03-02"], "2026-03-02"), (2, 2))
        self.assertEqual(analysis.streaks(["2026-03-01"], "2026-03-05"), (0, 1))
        self.assertEqual(analysis.streaks([], "2026-03-05"), (0, 0))
        prog = analysis.difficulty_progress(self.s)
        self.assertEqual(prog[0], ("2026-03-01", 800))
        self.assertEqual(prog[-1], ("2026-03-08", 1600))
        self.assertEqual(analysis.difficulty_histogram(self.s)[1000], 1)
        weeks = analysis.weekly(self.s, weeks=2, today="2026-03-08")
        self.assertEqual(sum(n for _, n in weeks), 7)

    def test_dashboard(self):
        self.s.add_contest("Round 1", "2026-03-02", "cf", 500, 10000, 1450, 1400, 1430)
        self.s.add_contest("Round 2", "2026-03-07", "cf", 300, 10000, 1600, 1430, 1480)
        page = dashboard.build(self.s, "2026-03-08")
        for needle in ("<polyline", "Weakest topics", "1480 (specialist)", "prefers-color-scheme"):
            self.assertTrue(needle in page, needle)


class TestImportersAndCli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "t.sqlite3")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _file(self, name, text):
        p = os.path.join(self.dir, name)
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return p

    def test_csv_roundtrip(self):
        src = self._file("in.csv", "platform,code,name,difficulty,tags,day,verdict,minutes,help,notes\n"
                                   "cf,1A,Theatre,1000,math;implementation,2026-01-01,AC,10,none,\n"
                                   "cf,2B,Hard,1900,dp,2026-01-02,WA,40,none,stuck\n"
                                   "atcoder,abc300_a,,,,,,,,\n")
        s = Store(self.db)
        self.assertEqual(importers.import_csv(s, src), (3, 2))
        self.assertEqual(len(s.problems()), 3)
        out = importers.export_csv(s, os.path.join(self.dir, "out.csv"))
        s2 = Store()
        self.assertEqual(importers.import_csv(s2, out, use_queue=False), (3, 2))
        self.assertEqual(s2.problem(1)["tags"], "implementation,math")
        s.close()

    def test_codeforces_json(self):
        status = {"status": "OK", "result": [
            {"id": 11, "creationTimeSeconds": 1767225600, "verdict": "WRONG_ANSWER",
             "problem": {"contestId": 1520, "index": "B", "name": "Ordinary Numbers", "rating": 800,
                         "tags": ["brute force", "math"]}},
            {"id": 12, "creationTimeSeconds": 1767229200, "verdict": "OK",
             "problem": {"contestId": 1520, "index": "B", "name": "Ordinary Numbers", "rating": 800,
                         "tags": ["brute force", "math"]}}]}
        rating_json = {"status": "OK", "result": [
            {"contestId": 1520, "contestName": "Codeforces Round #719", "rank": 1234,
             "ratingUpdateTimeSeconds": 1767240000, "oldRating": 0, "newRating": 1350}]}
        sp = self._file("status.json", json.dumps(status))
        rp = self._file("rating.json", json.dumps(rating_json))
        s = Store()
        self.assertEqual(importers.import_codeforces_status(s, sp), 2)
        self.assertEqual(importers.import_codeforces_status(s, sp), 0)       # idempotent
        self.assertEqual(importers.import_codeforces_rating(s, rp), 1)
        self.assertEqual(importers.import_codeforces_rating(s, rp), 0)
        self.assertEqual([a["verdict"] for a in s.attempts()], ["WA", "AC"])
        self.assertEqual(s.attempts()[0]["day"], "2026-01-01")
        self.assertEqual(s.current_rating(), 1350)
        bad = self._file("bad.json", json.dumps({"status": "FAILED"}))
        with self.assertRaises(TrackerError):
            importers.import_codeforces_status(s, bad)

    def test_cli_workflow(self):
        db = ["--db", self.db]
        rc, out, _ = run_cli(*db, "log", "cf:1520B", "WA", "-d", "800", "-t", "math", "--date", "2026-04-01")
        self.assertEqual(rc, 0)
        self.assertIn("upsolve due 2026-04-02", out)
        rc, out, _ = run_cli(*db, "queue", "--date", "2026-04-02")
        self.assertIn("cf:1520B", out)
        rc, out, _ = run_cli(*db, "review", "cf:1520B", "AC", "--date", "2026-04-02")
        self.assertIn("next review on 2026-04-03", out)
        run_cli(*db, "log", "https://codeforces.com/contest/1521/problem/A", "AC", "-d", "1000", "-t", "greedy")
        rc, out, _ = run_cli(*db, "stats")
        self.assertIn("solved 1 of 2 attempted", out)
        rc, out, _ = run_cli(*db, "weak")
        self.assertIn("practise problems rated", out)
        opp = self._file("opp.txt", " ".join(["1500"] * 99))
        rc, out, _ = run_cli(*db, "contest", "Virtual 1", "--rank", "10", "--before", "1400", "--opponents", opp,
                             "--date", "2026-04-03")
        self.assertIn("performance", out)
        self.assertIn("rating 1400 ->", out)
        dash = os.path.join(self.dir, "d.html")
        rc, out, _ = run_cli(*db, "dashboard", "-o", dash, "--date", "2026-04-03")
        self.assertTrue(os.path.getsize(dash) > 2000)
        rc, _, err = run_cli(*db, "review", "cf:404Z", "3")
        self.assertEqual(rc, 1)
        self.assertIn("unknown problem", err)

    def test_cli_rating_changes(self):
        p = self._file("st.csv", "handle,rating,rank\nalice,1500,1\nbob,1500,2\ncarol,1800,3\n")
        rc, out, _ = run_cli("rating-changes", p)
        self.assertEqual(rc, 0)
        lines = out.strip().splitlines()
        self.assertTrue(lines[0].split()[1] == "alice" and "+" in lines[0])
        self.assertIn("-", lines[2].split()[3])


if __name__ == "__main__":
    unittest.main()
