"""Spaced repetition (SM-2) for upsolving: problems you failed or solved with help come back for a
clean re-solve after 1, 6, ~15, ~40 ... days, sooner if you fail again."""
import datetime

from .db import parse_day

DEFAULT_EASE = 2.5


def sm2(ease, interval, reps, quality):
    """One SM-2 step. quality 0..5 (>= 3 is a pass). Returns (ease, interval_days, reps, lapsed)."""
    if not 0 <= quality <= 5:
        raise ValueError("quality must be 0..5")
    lapsed = quality < 3
    if lapsed:
        reps, interval = 0, 1
    else:
        reps += 1
        interval = 1 if reps == 1 else 6 if reps == 2 else int(round(interval * ease))
    ease = max(1.3, ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    return ease, interval, reps, lapsed


def quality_from(verdict, help="none", minutes=None, expected_minutes=None):
    """Map an attempt to an SM-2 quality grade."""
    if verdict != "AC":
        return 1
    if help == "editorial":
        return 2
    if help == "hint":
        return 3
    if minutes is not None and expected_minutes and minutes > 2 * expected_minutes:
        return 4
    return 5 if minutes is not None and expected_minutes and minutes <= expected_minutes / 2 else 4


def _add_days(day, n):
    return (datetime.date.fromisoformat(day) + datetime.timedelta(days=n)).isoformat()


def schedule(store, pid, day=None, delay=1):
    """Put a problem into the upsolve queue (no-op if it is already there)."""
    day = parse_day(day)
    if store.conn.execute("SELECT 1 FROM reviews WHERE problem_id=?", (pid,)).fetchone():
        return False
    store.conn.execute("INSERT INTO reviews(problem_id, ease, interval, reps, due, last) VALUES (?,?,?,?,?,?)",
                       (pid, DEFAULT_EASE, 0, 0, _add_days(day, delay), day))
    store.conn.commit()
    return True


def review(store, pid, quality, day=None):
    """Record a review; returns the new due date."""
    day = parse_day(day)
    row = store.conn.execute("SELECT * FROM reviews WHERE problem_id=?", (pid,)).fetchone()
    if row is None:
        schedule(store, pid, day)
        row = store.conn.execute("SELECT * FROM reviews WHERE problem_id=?", (pid,)).fetchone()
    ease, interval, reps, lapsed = sm2(row["ease"], row["interval"], row["reps"], quality)
    due = _add_days(day, interval)
    store.conn.execute("UPDATE reviews SET ease=?, interval=?, reps=?, due=?, last=?, lapses=lapses+? "
                       "WHERE problem_id=?", (ease, interval, reps, due, day, 1 if lapsed else 0, pid))
    store.conn.commit()
    return due


def remove(store, pid):
    store.conn.execute("DELETE FROM reviews WHERE problem_id=?", (pid,))
    store.conn.commit()


def queue(store, day=None, include_future=False, limit=None):
    """Due reviews (most overdue first, harder problems first on ties)."""
    day = parse_day(day)
    sql = ("SELECT r.*, p.platform, p.code, p.name, p.difficulty, p.tags, p.url FROM reviews r "
           "JOIN problems p ON p.id = r.problem_id %s ORDER BY r.due, COALESCE(p.difficulty, 0) DESC, p.id"
           % ("" if include_future else "WHERE r.due <= ?"))
    rows = store.conn.execute(sql, () if include_future else (day,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["overdue_days"] = (datetime.date.fromisoformat(day) - datetime.date.fromisoformat(r["due"])).days
        out.append(d)
    return out[:limit] if limit else out


def on_attempt(store, pid, verdict, help, day, minutes=None):
    """Hook called after logging an attempt: failures and assisted solves enter the queue; a clean AC of a
    queued problem counts as a review."""
    row = store.conn.execute("SELECT due FROM reviews WHERE problem_id=?", (pid,)).fetchone()
    if row is not None:
        clean = verdict == "AC" and help == "none"
        if day >= row[0] or (verdict == "AC" and not clean):
            return review(store, pid, quality_from(verdict, help, minutes), day)
        return None                        # early clean solve or early failure: keep the schedule
    if verdict != "AC" or help != "none":
        schedule(store, pid, day)
        return _add_days(day, 1)
    return None
