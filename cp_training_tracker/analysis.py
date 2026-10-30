"""Training statistics: per-topic performance, weaknesses, practice rating, streaks and progress."""
import datetime
import math
from collections import Counter, defaultdict

from .rating import estimate_skill


def tag_stats(store, prior_strength=2.0):
    """Per tag: attempted, solved, clean (no help), smoothed clean-solve rate, difficulty numbers."""
    sums = store.problem_summaries()
    attempted = [s for s in sums.values() if s["attempts"]]
    overall_rate = (sum(s["clean"] for s in attempted) / len(attempted)) if attempted else 0.5
    tags = defaultdict(list)
    for s in attempted:
        for t in filter(None, s["problem"]["tags"].split(",")):
            tags[t].append(s)
    out = {}
    for t, items in tags.items():
        n = len(items)
        clean = sum(1 for s in items if s["clean"])
        solved_d = [s["problem"]["difficulty"] for s in items if s["solved"] and s["problem"]["difficulty"]]
        tries = [s["tries_to_ac"] for s in items if s["tries_to_ac"]]
        out[t] = {
            "attempted": n, "solved": sum(1 for s in items if s["solved"]), "clean": clean,
            "rate": (clean + prior_strength * overall_rate) / (n + prior_strength),
            "raw_rate": clean / n,
            "avg_difficulty": sum(solved_d) / len(solved_d) if solved_d else None,
            "max_difficulty": max(solved_d) if solved_d else None,
            "avg_tries": sum(tries) / len(tries) if tries else None,
            "minutes": sum(s["minutes"] for s in items),
        }
    return out, overall_rate


def overall_stats(store):
    sums = store.problem_summaries()
    attempted = [s for s in sums.values() if s["attempts"]]
    solved = [s for s in attempted if s["solved"]]
    diffs = [s["problem"]["difficulty"] for s in solved if s["problem"]["difficulty"]]
    return {"problems": len(sums), "attempted": len(attempted), "solved": len(solved),
            "clean": sum(1 for s in attempted if s["clean"]),
            "attempts": sum(s["attempts"] for s in attempted),
            "minutes": sum(s["minutes"] for s in attempted),
            "avg_difficulty": sum(diffs) / len(diffs) if diffs else None,
            "max_difficulty": max(diffs) if diffs else None}


def practice_rating(store):
    """MAP skill estimate from clean solves vs. everything else on rated problems."""
    results = [(s["problem"]["difficulty"], s["clean"]) for s in store.problem_summaries().values()
               if s["attempts"] and s["problem"]["difficulty"]]
    return estimate_skill(results) if results else None


def weaknesses(store, min_attempted=2, top=5):
    """Topics ranked by how much they lag behind your average, with reasons."""
    stats, overall_rate = tag_stats(store)
    ov = overall_stats(store)
    base_diff = ov["avg_difficulty"]
    rows = []
    for t, s in stats.items():
        if s["attempted"] < min_attempted:
            continue
        deficit = overall_rate - s["rate"]
        diff_gap = ((base_diff - s["avg_difficulty"]) / 400.0) if base_diff and s["avg_difficulty"] else 0.0
        if s["avg_difficulty"] is None and base_diff:
            diff_gap = 0.5                               # never solved anything in this topic
        tries_pen = ((s["avg_tries"] or 1) - 1) * 0.05
        score = (deficit + 0.5 * diff_gap + tries_pen) * math.log(1 + s["attempted"])
        reasons = []
        if deficit > 0.05:
            reasons.append("clean-solve rate %.0f%% vs %.0f%% overall" % (100 * s["raw_rate"], 100 * overall_rate))
        if diff_gap > 0.1:
            reasons.append("solved problems are easier than your average")
        if s["avg_tries"] and s["avg_tries"] > 2:
            reasons.append("%.1f submissions per AC" % s["avg_tries"])
        rows.append({"tag": t, "score": score, "reasons": reasons, **s})
    rows.sort(key=lambda r: -r["score"])
    return rows[:top]


def recommend(store, n_tags=3):
    r = practice_rating(store)
    weak = [w["tag"] for w in weaknesses(store, top=n_tags) if w["score"] > 0]
    if r is None:
        return {"rating": None, "difficulty": (800, 1000), "tags": weak}
    lo = int(round(r / 100.0)) * 100
    return {"rating": r, "difficulty": (max(800, lo), max(800, lo) + 200), "tags": weak}


def activity(store):
    return Counter(a["day"] for a in store.attempts())


def streaks(days, today=None):
    """(current, longest) streak of consecutive active days; the current one may end today or yesterday."""
    ds = sorted({datetime.date.fromisoformat(d) for d in days})
    if not ds:
        return 0, 0
    longest = run = 1
    for a, b in zip(ds, ds[1:]):
        run = run + 1 if (b - a).days == 1 else 1
        longest = max(longest, run)
    t = datetime.date.fromisoformat(today) if today else datetime.date.today()
    s = set(ds)
    start = t if t in s else t - datetime.timedelta(days=1)
    cur = 0
    while start in s:
        cur += 1
        start -= datetime.timedelta(days=1)
    return cur, longest


def difficulty_progress(store):
    """[(day, best difficulty solved so far)] at each day the record improved."""
    best, out = 0, []
    sums = store.problem_summaries()
    for day, pid in sorted((s["first_ac"], pid) for pid, s in sums.items() if s["first_ac"]):
        d = sums[pid]["problem"]["difficulty"] or 0
        if d > best:
            best = d
            out.append((day, d))
    return out


def difficulty_histogram(store, bucket=100):
    h = Counter()
    for s in store.problem_summaries().values():
        d = s["problem"]["difficulty"]
        if s["solved"] and d:
            h[d // bucket * bucket] += 1
    return dict(sorted(h.items()))


def weekly(store, weeks=12, today=None):
    """Solved problems per ISO week for the last `weeks` weeks: [(week_start, solved)]."""
    t = datetime.date.fromisoformat(today) if today else datetime.date.today()
    start = t - datetime.timedelta(days=t.weekday() + 7 * (weeks - 1))
    buckets = Counter()
    for s in store.problem_summaries().values():
        if s["first_ac"]:
            d = datetime.date.fromisoformat(s["first_ac"])
            if d >= start:
                buckets[(d - datetime.timedelta(days=d.weekday())).isoformat()] += 1
    return [((start + datetime.timedelta(weeks=i)).isoformat(),
             buckets[(start + datetime.timedelta(weeks=i)).isoformat()]) for i in range(weeks)]
