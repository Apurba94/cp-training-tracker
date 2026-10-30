import unittest

from cp_training_tracker import rating
from cp_training_tracker.db import Store
from cp_training_tracker.srs import on_attempt, quality_from, queue, review, schedule, sm2


class TestRating(unittest.TestCase):
    def test_win_probability(self):
        self.assertAlmostEqual(rating.win_probability(1500, 1500), 0.5)
        self.assertAlmostEqual(rating.win_probability(1900, 1500), 10 / 11)
        self.assertAlmostEqual(rating.win_probability(1500, 1900) + rating.win_probability(1900, 1500), 1.0)

    def test_performance(self):
        others = [1500] * 99
        self.assertAlmostEqual(rating.performance(50.5, others), 1500, delta=1)
        self.assertGreater(rating.performance(1, others), 2000)
        self.assertLess(rating.performance(100, others), 1000)
        perf = rating.performance(10, others)
        self.assertAlmostEqual(rating.expected_rank(perf, others), 10, places=3)
        with self.assertRaises(ValueError):
            rating.performance(1, [])

    def test_cf_rating_changes(self):
        rows = [("a", 1500, 1), ("b", 1500, 2), ("c", 1500, 3), ("d", 1500, 4)]
        d = rating.cf_rating_changes(rows)
        self.assertGreater(d["a"], 0)
        self.assertLess(d["d"], 0)
        self.assertTrue(d["a"] > d["b"] > d["c"] > d["d"])
        self.assertLessEqual(sum(d.values()), 0)                 # rating deflation, never inflation
        upset = rating.cf_rating_changes([("low", 1200, 1), ("high", 2400, 2)])
        self.assertGreater(upset["low"], 100)
        self.assertLess(upset["high"], -100)
        expected = rating.cf_rating_changes([("low", 1200, 2), ("high", 2400, 1)])
        self.assertLess(abs(expected["low"]) + abs(expected["high"]),
                        (abs(upset["low"]) + abs(upset["high"])) / 2)
        self.assertEqual(rating.cf_rating_changes([("solo", 1500, 1)]), {"solo": 0})

    def test_skill_and_difficulty_estimates(self):
        results = [(d, d <= 1600) for d in range(800, 2600, 100)]
        r = rating.estimate_skill(results)
        self.assertTrue(1450 < r < 1800, r)
        all_solved = rating.estimate_skill([(1000, True)] * 5)
        self.assertTrue(1000 < all_solved < 3500)
        d = rating.estimate_difficulty([(r_, r_ >= 1900) for r_ in range(1000, 3000, 100)])
        self.assertTrue(1700 < d < 2100, d)

    def test_titles_and_update(self):
        self.assertEqual(rating.rank_title(1250), "pupil")
        self.assertEqual(rating.rank_title(2450), "grandmaster")
        self.assertEqual(rating.rank_title(100), "newbie")
        self.assertEqual(rating.simple_update(1500, 1700, 0), 1700)
        self.assertEqual(rating.simple_update(1500, 1700, 10), 1550)


class TestSrs(unittest.TestCase):
    def test_sm2_sequence(self):
        ease, interval, reps = 2.5, 0, 0
        intervals = []
        for _ in range(4):
            ease, interval, reps, lapsed = sm2(ease, interval, reps, 5)
            intervals.append(interval)
            self.assertFalse(lapsed)
        self.assertEqual(intervals[:2], [1, 6])
        self.assertGreater(intervals[2], 6)
        self.assertGreater(intervals[3], intervals[2])
        e2, i2, r2, lapsed = sm2(ease, interval, reps, 1)
        self.assertEqual((i2, r2, lapsed), (1, 0, True))
        self.assertLess(e2, ease)
        self.assertEqual(sm2(1.3, 1, 0, 0)[0], 1.3)                # ease floor
        with self.assertRaises(ValueError):
            sm2(2.5, 1, 1, 6)

    def test_quality_mapping(self):
        self.assertEqual(quality_from("WA"), 1)
        self.assertEqual(quality_from("AC", "editorial"), 2)
        self.assertEqual(quality_from("AC", "hint"), 3)
        self.assertEqual(quality_from("AC"), 4)
        self.assertEqual(quality_from("AC", minutes=10, expected_minutes=30), 5)

    def test_queue_flow(self):
        s = Store()
        p1 = s.upsert_problem("cf", "1A", "Theatre", difficulty=1000)
        p2 = s.upsert_problem("cf", "2B", "Hard", difficulty=2000)
        self.assertTrue(schedule(s, p1, "2026-01-01"))
        self.assertFalse(schedule(s, p1, "2026-01-01"))
        schedule(s, p2, "2026-01-01")
        due = queue(s, "2026-01-02")
        self.assertEqual([r["problem_id"] for r in due], [p2, p1])   # same day: harder first
        self.assertEqual(queue(s, "2026-01-01"), [])
        nxt = review(s, p1, 5, "2026-01-02")
        self.assertEqual(nxt, "2026-01-03")
        self.assertEqual(len(queue(s, "2026-01-02")), 1)
        self.assertEqual(queue(s, "2026-01-10")[0]["overdue_days"], 8)

    def test_on_attempt_hook(self):
        s = Store()
        p = s.upsert_problem("cf", "3C")
        self.assertEqual(on_attempt(s, p, "WA", "none", "2026-02-01"), "2026-02-02")
        self.assertIsNone(on_attempt(s, p, "AC", "none", "2026-02-01"))     # early clean AC: keep schedule
        self.assertEqual(on_attempt(s, p, "AC", "none", "2026-02-02"), "2026-02-03")
        q = s.upsert_problem("cf", "4D")
        self.assertIsNone(on_attempt(s, q, "AC", "none", "2026-02-01"))     # clean first solve: not queued
        self.assertEqual(on_attempt(s, q, "AC", "editorial", "2026-02-01"), "2026-02-02")
        self.assertEqual(len(queue(s, "2026-02-02")), 1)


if __name__ == "__main__":
    unittest.main()
