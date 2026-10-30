"""SQLite storage: problems, attempts, contests and the upsolving review queue."""
import datetime
import re
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS problems(
    id INTEGER PRIMARY KEY, platform TEXT NOT NULL, code TEXT NOT NULL, name TEXT, url TEXT,
    difficulty INTEGER, tags TEXT NOT NULL DEFAULT '', UNIQUE(platform, code));
CREATE TABLE IF NOT EXISTS attempts(
    id INTEGER PRIMARY KEY, problem_id INTEGER NOT NULL REFERENCES problems(id), day TEXT NOT NULL,
    verdict TEXT NOT NULL, minutes REAL, help TEXT NOT NULL DEFAULT 'none', notes TEXT);
CREATE TABLE IF NOT EXISTS contests(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, day TEXT NOT NULL, platform TEXT, rank INTEGER,
    participants INTEGER, performance REAL, rating_before REAL, rating_after REAL, solved INTEGER);
CREATE TABLE IF NOT EXISTS reviews(
    problem_id INTEGER PRIMARY KEY REFERENCES problems(id), ease REAL NOT NULL, interval INTEGER NOT NULL,
    reps INTEGER NOT NULL, due TEXT NOT NULL, last TEXT, lapses INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS attempts_problem ON attempts(problem_id);
CREATE INDEX IF NOT EXISTS attempts_day ON attempts(day);
"""

VERDICTS = ("AC", "WA", "TLE", "MLE", "RE", "CE", "PE", "OTHER")
HELP = ("none", "hint", "editorial")
PLATFORM_ALIASES = {"codeforces": "cf", "cf": "cf", "atcoder": "atcoder", "ac": "atcoder", "cses": "cses",
                    "leetcode": "leetcode", "lc": "leetcode", "codechef": "codechef", "kattis": "kattis",
                    "spoj": "spoj", "uva": "uva", "usaco": "usaco"}


class TrackerError(Exception):
    pass


def today():
    return datetime.date.today().isoformat()


def parse_day(text):
    if text is None:
        return today()
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        raise TrackerError("dates must be YYYY-MM-DD, got %r" % text)


def normalize_tags(tags):
    if isinstance(tags, str):
        tags = re.split(r"[,;|]", tags)
    return sorted({t.strip().lower().replace(" ", "-") for t in (tags or []) if t and t.strip()})


def parse_ref(ref):
    """'cf:1520A', 'atcoder:abc300_a', or a problem URL -> (platform, code, url)."""
    ref = ref.strip()
    m = re.search(r"codeforces\.com/(?:contest|gym)/(\d+)/problem/(\w+)", ref) or \
        re.search(r"codeforces\.com/problemset/problem/(\d+)/(\w+)", ref)
    if m:
        return "cf", m.group(1) + m.group(2).upper(), ref
    m = re.search(r"atcoder\.jp/contests/[\w-]+/tasks/([\w-]+)", ref)
    if m:
        return "atcoder", m.group(1), ref
    m = re.search(r"cses\.fi/problemset/task/(\d+)", ref)
    if m:
        return "cses", m.group(1), ref
    m = re.search(r"leetcode\.com/problems/([\w-]+)", ref)
    if m:
        return "leetcode", m.group(1), ref
    if re.match(r"https?://", ref):
        return "other", ref.split("://", 1)[1].rstrip("/"), ref
    if ":" in ref:
        plat, code = ref.split(":", 1)
        plat = PLATFORM_ALIASES.get(plat.lower(), plat.lower())
        return plat, (code.upper() if plat == "cf" else code), None
    raise TrackerError("problem reference must look like platform:code or be a URL: %r" % ref)


class Store:
    def __init__(self, path=":memory:"):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self):
        self.conn.commit()
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- problems ----
    def upsert_problem(self, platform, code, name=None, url=None, difficulty=None, tags=None):
        row = self.conn.execute("SELECT * FROM problems WHERE platform=? AND code=?", (platform, code)).fetchone()
        tags = normalize_tags(tags)
        if row is None:
            cur = self.conn.execute("INSERT INTO problems(platform, code, name, url, difficulty, tags) VALUES (?,?,?,?,?,?)",
                                    (platform, code, name, url, difficulty, ",".join(tags)))
            self.conn.commit()
            return cur.lastrowid
        merged = sorted(set(filter(None, row["tags"].split(","))) | set(tags))
        self.conn.execute("UPDATE problems SET name=COALESCE(?, name), url=COALESCE(?, url), "
                          "difficulty=COALESCE(?, difficulty), tags=? WHERE id=?",
                          (name, url, difficulty, ",".join(merged), row["id"]))
        self.conn.commit()
        return row["id"]

    def problem_by_ref(self, ref, create=False, **fields):
        if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
            row = self.conn.execute("SELECT * FROM problems WHERE id=?", (int(ref),)).fetchone()
            if row is None:
                raise TrackerError("no problem with id %s" % ref)
            if any(v is not None for v in fields.values()):
                self.upsert_problem(row["platform"], row["code"], **fields)
            return row["id"]
        platform, code, url = parse_ref(ref)
        row = self.conn.execute("SELECT id FROM problems WHERE platform=? AND code=?", (platform, code)).fetchone()
        if row is None and not create:
            raise TrackerError("unknown problem %s:%s (add it first or pass details)" % (platform, code))
        if row is None or any(v is not None for v in fields.values()):
            if fields.get("url") is None:
                fields["url"] = url
            return self.upsert_problem(platform, code, **fields)
        return row["id"]

    def problem(self, pid):
        row = self.conn.execute("SELECT * FROM problems WHERE id=?", (pid,)).fetchone()
        return dict(row) if row else None

    def problems(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM problems ORDER BY id")]

    @staticmethod
    def label(p):
        return "%s:%s" % (p["platform"], p["code"]) + (" %s" % p["name"] if p.get("name") else "")

    # ---- attempts ----
    def log(self, pid, verdict, day=None, minutes=None, help="none", notes=None):
        verdict = verdict.upper()
        if verdict == "OK":
            verdict = "AC"
        if verdict not in VERDICTS:
            raise TrackerError("verdict must be one of %s" % ", ".join(VERDICTS))
        if help not in HELP:
            raise TrackerError("help must be one of %s" % ", ".join(HELP))
        cur = self.conn.execute("INSERT INTO attempts(problem_id, day, verdict, minutes, help, notes) VALUES (?,?,?,?,?,?)",
                                (pid, parse_day(day), verdict, minutes, help, notes))
        self.conn.commit()
        return cur.lastrowid

    def attempts(self, pid=None):
        if pid is None:
            rows = self.conn.execute("SELECT * FROM attempts ORDER BY day, id")
        else:
            rows = self.conn.execute("SELECT * FROM attempts WHERE problem_id=? ORDER BY day, id", (pid,))
        return [dict(r) for r in rows]

    def has_note(self, note):
        return self.conn.execute("SELECT 1 FROM attempts WHERE notes=?", (note,)).fetchone() is not None

    def problem_summaries(self):
        """Per problem: attempts before first AC, solved (any help), solved_clean (AC without help), days."""
        out = {}
        for p in self.problems():
            out[p["id"]] = {"problem": p, "attempts": 0, "solved": False, "clean": False, "first_ac": None,
                            "tries_to_ac": None, "minutes": 0.0, "first_day": None}
        for a in self.attempts():
            s = out[a["problem_id"]]
            s["attempts"] += 1
            s["minutes"] += a["minutes"] or 0
            s["first_day"] = s["first_day"] or a["day"]
            if a["verdict"] == "AC":
                if not s["solved"]:
                    s["first_ac"] = a["day"]
                    s["tries_to_ac"] = s["attempts"]
                s["solved"] = True
                if a["help"] == "none":
                    s["clean"] = True
        return out

    # ---- contests ----
    def add_contest(self, name, day=None, platform=None, rank=None, participants=None, performance=None,
                    rating_before=None, rating_after=None, solved=None):
        cur = self.conn.execute("INSERT INTO contests(name, day, platform, rank, participants, performance, "
                                "rating_before, rating_after, solved) VALUES (?,?,?,?,?,?,?,?,?)",
                                (name, parse_day(day), platform, rank, participants, performance, rating_before,
                                 rating_after, solved))
        self.conn.commit()
        return cur.lastrowid

    def contests(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM contests ORDER BY day, id")]

    def current_rating(self):
        row = self.conn.execute("SELECT rating_after FROM contests WHERE rating_after IS NOT NULL "
                                "ORDER BY day DESC, id DESC LIMIT 1").fetchone()
        return row[0] if row else None
