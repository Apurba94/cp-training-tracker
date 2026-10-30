"""Rating mathematics: Elo probabilities, contest performance, the Codeforces rating-change algorithm,
and maximum-likelihood estimates of a user's skill or a problem's difficulty."""
import math


def win_probability(ra, rb):
    """Probability that a player rated ra beats a player rated rb (Elo, 400-point scale)."""
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def expected_rank(rating, others):
    """1 + expected number of opponents finishing ahead."""
    return 1.0 + sum(win_probability(o, rating) for o in others)


def _solve_decreasing(f, target, lo=-4000.0, hi=8000.0, iters=80):
    """x with f(x) == target for a decreasing f (bisection)."""
    for _ in range(iters):
        mid = (lo + hi) / 2
        if f(mid) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def performance(rank, others):
    """Rating at which `rank` is the expected place against these opponents."""
    if not others:
        raise ValueError("need opponent ratings")
    rank = max(1.0, min(float(rank), len(others) + 1.0))
    return _solve_decreasing(lambda r: expected_rank(r, others), rank)


def cf_rating_changes(rows):
    """Codeforces-style rating changes.

    rows: [(handle, old_rating, rank)] with rank = place (ties share a place).
    Each delta is half the gap between the old rating and the rating that would make the geometric mean
    of seed and rank the expected place, then corrected so the sum is slightly negative and the top
    participants do not inflate (the published CF procedure)."""
    n = len(rows)
    if n < 2:
        return {h: 0 for h, _, _ in rows}
    ratings = [float(r) for _, r, _ in rows]
    deltas = []
    for i, (_, old, rank) in enumerate(rows):
        others = ratings[:i] + ratings[i + 1:]
        seed = expected_rank(old, others)
        target = math.sqrt(seed * rank)
        need = _solve_decreasing(lambda r: expected_rank(r, others), target)
        deltas.append((need - old) / 2.0)
    inc = -sum(deltas) / n - 1.0
    deltas = [d + inc for d in deltas]
    order = sorted(range(n), key=lambda i: -ratings[i])
    top = min(n, 4 * int(round(math.sqrt(n))))
    top_sum = sum(deltas[i] for i in order[:top])
    inc2 = min(max(-top_sum / top, -10.0), 0.0)
    deltas = [d + inc2 for d in deltas]
    return {rows[i][0]: int(round(deltas[i])) for i in range(n)}


def simple_update(old, perf, contests_played, k_min=0.25):
    """Personal rating update for virtual contests: big steps while provisional, then k_min of the gap."""
    k = max(k_min, 1.0 / (1 + contests_played))
    return old + k * (perf - old)


def _mle(loglik, lo=-500.0, hi=4500.0, iters=100):
    """Ternary search for the maximum of a concave function."""
    for _ in range(iters):
        m1 = lo + (hi - lo) / 3
        m2 = hi - (hi - lo) / 3
        if loglik(m1) < loglik(m2):
            lo = m1
        else:
            hi = m2
    return (lo + hi) / 2


def estimate_skill(results, prior_mean=1500.0, prior_sd=700.0):
    """results: [(difficulty, solved: bool)]. MAP estimate of the rating R under
    P(solve) = win_probability(R, difficulty) with a weak Gaussian prior (keeps all-solved finite)."""
    results = [(float(d), bool(s)) for d, s in results if d is not None]

    def ll(r):
        total = -((r - prior_mean) ** 2) / (2 * prior_sd ** 2)
        for d, s in results:
            p = min(max(win_probability(r, d), 1e-12), 1 - 1e-12)
            total += math.log(p if s else 1 - p)
        return total
    return _mle(ll)


def estimate_difficulty(results, prior_mean=1500.0, prior_sd=700.0):
    """results: [(solver_rating, solved: bool)] -> difficulty D where P(solve) = win_probability(rating, D)."""
    flipped = [(r, not s) for r, s in results]
    return estimate_skill(flipped, prior_mean, prior_sd)


RANKS = [(0, "newbie"), (1200, "pupil"), (1400, "specialist"), (1600, "expert"), (1900, "candidate master"),
         (2100, "master"), (2300, "international master"), (2400, "grandmaster"),
         (2600, "international grandmaster"), (3000, "legendary grandmaster")]


def rank_title(rating):
    title = RANKS[0][1]
    for lo, name in RANKS:
        if rating >= lo:
            title = name
    return title
