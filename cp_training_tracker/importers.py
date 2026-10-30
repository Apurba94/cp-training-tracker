"""Import from CSV and from saved Codeforces API responses (user.status / user.rating); export to CSV."""
import csv
import datetime
import json

from . import srs
from .db import TrackerError, normalize_tags

CF_VERDICTS = {"OK": "AC", "WRONG_ANSWER": "WA", "TIME_LIMIT_EXCEEDED": "TLE", "MEMORY_LIMIT_EXCEEDED": "MLE",
               "RUNTIME_ERROR": "RE", "COMPILATION_ERROR": "CE", "PRESENTATION_ERROR": "PE",
               "IDLENESS_LIMIT_EXCEEDED": "TLE"}
CSV_FIELDS = ["platform", "code", "name", "difficulty", "tags", "day", "verdict", "minutes", "help", "notes"]


def _utc_day(ts):
    return datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc).date().isoformat()


def import_csv(store, path, use_queue=True):
    """Columns (header required): platform, code, name, difficulty, tags (';'-separated), day, verdict,
    minutes, help, notes. Rows without a verdict only register the problem."""
    n_prob = n_att = 0
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = {"platform", "code"} - set(reader.fieldnames or [])
        if missing:
            raise TrackerError("CSV needs columns %s" % ", ".join(sorted(missing)))
        for row in reader:
            diff = row.get("difficulty") or None
            pid = store.upsert_problem(row["platform"].strip().lower(), row["code"].strip(), row.get("name") or None,
                                       None, int(float(diff)) if diff else None, normalize_tags(row.get("tags") or ""))
            n_prob += 1
            if row.get("verdict"):
                minutes = float(row["minutes"]) if row.get("minutes") else None
                help_ = (row.get("help") or "none").strip().lower()
                store.log(pid, row["verdict"], row.get("day") or None, minutes, help_, row.get("notes") or None)
                if use_queue:
                    srs.on_attempt(store, pid, row["verdict"].upper(), help_, row.get("day") or store_today(), minutes)
                n_att += 1
    return n_prob, n_att


def store_today():
    return datetime.date.today().isoformat()


def import_codeforces_status(store, path, use_queue=False):
    """Saved JSON of https://codeforces.com/api/user.status?handle=... (no network access needed)."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("status") != "OK":
        raise TrackerError("not a successful Codeforces API response")
    added = 0
    for sub in sorted(data["result"], key=lambda s: s.get("creationTimeSeconds", 0)):
        note = "cf-sub:%s" % sub.get("id")
        if store.has_note(note):
            continue
        p = sub["problem"]
        code = "%s%s" % (p.get("contestId", ""), p.get("index", ""))
        pid = store.upsert_problem("cf", code, p.get("name"), None, p.get("rating"), p.get("tags") or [])
        verdict = CF_VERDICTS.get(sub.get("verdict"), "OTHER")
        day = _utc_day(sub.get("creationTimeSeconds", 0))
        store.log(pid, verdict, day, None, "none", note)
        if use_queue:
            srs.on_attempt(store, pid, verdict, "none", day)
        added += 1
    return added


def import_codeforces_rating(store, path):
    """Saved JSON of https://codeforces.com/api/user.rating?handle=..."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("status") != "OK":
        raise TrackerError("not a successful Codeforces API response")
    known = {(c["name"], c["day"]) for c in store.contests()}
    added = 0
    for c in data["result"]:
        day = _utc_day(c.get("ratingUpdateTimeSeconds", 0))
        if (c["contestName"], day) in known:
            continue
        store.add_contest(c["contestName"], day, "cf", c.get("rank"), None, None, c.get("oldRating"),
                          c.get("newRating"))
        added += 1
    return added


def export_csv(store, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, CSV_FIELDS)
        w.writeheader()
        probs = {p["id"]: p for p in store.problems()}
        logged = set()
        for a in store.attempts():
            p = probs[a["problem_id"]]
            logged.add(p["id"])
            w.writerow({"platform": p["platform"], "code": p["code"], "name": p["name"] or "",
                        "difficulty": p["difficulty"] or "", "tags": p["tags"].replace(",", ";"), "day": a["day"],
                        "verdict": a["verdict"], "minutes": a["minutes"] if a["minutes"] is not None else "",
                        "help": a["help"], "notes": a["notes"] or ""})
        for pid, p in probs.items():
            if pid not in logged:
                w.writerow({"platform": p["platform"], "code": p["code"], "name": p["name"] or "",
                            "difficulty": p["difficulty"] or "", "tags": p["tags"].replace(",", ";")})
    return path
