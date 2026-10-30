"""Command-line interface for cp-training-tracker."""
import argparse
import csv
import os
import sys

from . import analysis, dashboard, importers, rating, srs
from .db import Store, TrackerError, parse_day

DEFAULT_DB = os.environ.get("CP_TRACKER_DB", os.path.join(os.path.expanduser("~"), ".cp-training.sqlite3"))


def _problem_fields(args):
    return {"name": getattr(args, "name", None), "difficulty": getattr(args, "difficulty", None),
            "tags": args.tags.split(",") if getattr(args, "tags", None) else None}


def _read_ratings(path):
    with open(path, encoding="utf-8") as fh:
        return [float(x) for x in fh.read().replace(",", " ").split()]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cp-tracker", description="Log practice, rate contests, upsolve, analyse.")
    ap.add_argument("--db", default=DEFAULT_DB, help="SQLite file (env CP_TRACKER_DB)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="register a problem")
    a.add_argument("ref", help="platform:code or URL")
    a.add_argument("--name")
    a.add_argument("-d", "--difficulty", type=int)
    a.add_argument("-t", "--tags", help="comma separated")
    lg = sub.add_parser("log", help="log an attempt (creates the problem if needed)")
    lg.add_argument("ref")
    lg.add_argument("verdict", help="AC WA TLE MLE RE CE PE OTHER")
    lg.add_argument("-m", "--minutes", type=float)
    lg.add_argument("--help-used", dest="help_used", default="none", choices=["none", "hint", "editorial"])
    lg.add_argument("--date")
    lg.add_argument("--name")
    lg.add_argument("-d", "--difficulty", type=int)
    lg.add_argument("-t", "--tags")
    lg.add_argument("--notes")
    lg.add_argument("--no-queue", action="store_true", help="do not touch the upsolve queue")
    c = sub.add_parser("contest", help="record a contest result")
    c.add_argument("name")
    c.add_argument("--rank", type=int)
    c.add_argument("--participants", type=int)
    c.add_argument("--before", type=float)
    c.add_argument("--after", type=float)
    c.add_argument("--solved", type=int)
    c.add_argument("--date")
    c.add_argument("--platform")
    c.add_argument("--opponents", help="file with opponents' ratings: computes your performance (and a "
                                       "provisional new rating when --after is not given)")
    q = sub.add_parser("queue", help="problems due for upsolving")
    q.add_argument("--date")
    q.add_argument("--all", action="store_true", help="include future reviews")
    q.add_argument("-n", "--limit", type=int)
    rv = sub.add_parser("review", help="grade a re-solve 0-5 (or give a verdict)")
    rv.add_argument("ref")
    rv.add_argument("quality", help="0..5, or a verdict such as AC/WA")
    rv.add_argument("--date")
    sub.add_parser("stats", help="overall and per-topic statistics")
    w = sub.add_parser("weak", help="weakest topics and what to practise next")
    w.add_argument("-n", type=int, default=5)
    d = sub.add_parser("dashboard", help="write the HTML dashboard")
    d.add_argument("-o", "--output", default="dashboard.html")
    d.add_argument("--date")
    ic = sub.add_parser("import-csv")
    ic.add_argument("path")
    ic.add_argument("--no-queue", action="store_true")
    icf = sub.add_parser("import-cf", help="import saved Codeforces API JSON (user.status / user.rating)")
    icf.add_argument("--status")
    icf.add_argument("--rating")
    icf.add_argument("--queue", action="store_true", help="queue failed problems for upsolving")
    ex = sub.add_parser("export")
    ex.add_argument("path")
    rc = sub.add_parser("rating-changes", help="Codeforces-style deltas for a standings CSV handle,rating,rank")
    rc.add_argument("path")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "rating-changes":
            with open(args.path, newline="", encoding="utf-8") as fh:
                rows = [(r[0].strip(), float(r[1]), int(r[2])) for r in csv.reader(fh)
                        if len(r) >= 3 and r[1].strip().lstrip("-").replace(".", "").isdigit()]
            deltas = rating.cf_rating_changes(rows)
            for h, old, rank in sorted(rows, key=lambda r: r[2]):
                print("%4d  %-20s %5d  %+4d -> %d" % (rank, h, old, deltas[h], old + deltas[h]))
            return 0
        with Store(args.db) as store:
            return _dispatch(store, args)
    except (TrackerError, ValueError, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1


def _dispatch(store, args):
    if args.cmd == "add":
        pid = store.problem_by_ref(args.ref, create=True, **_problem_fields(args))
        print("problem #%d %s" % (pid, store.label(store.problem(pid))))
    elif args.cmd == "log":
        pid = store.problem_by_ref(args.ref, create=True, **_problem_fields(args))
        day = parse_day(args.date)
        store.log(pid, args.verdict, day, args.minutes, args.help_used, args.notes)
        msg = "logged %s on %s" % (args.verdict.upper(), store.label(store.problem(pid)))
        if not args.no_queue:
            due = srs.on_attempt(store, pid, "AC" if args.verdict.upper() == "OK" else args.verdict.upper(),
                                 args.help_used, day, args.minutes)
            if due:
                msg += "; upsolve due %s" % due
        print(msg)
    elif args.cmd == "contest":
        perf, after = None, args.after
        if args.opponents:
            if args.rank is None:
                raise TrackerError("--opponents needs --rank")
            others = _read_ratings(args.opponents)
            perf = rating.performance(args.rank, others)
            if after is None and args.before is not None:
                played = len([c for c in store.contests() if c["rating_after"] is not None])
                after = round(rating.simple_update(args.before, perf, played))
        store.add_contest(args.name, args.date, args.platform, args.rank, args.participants, perf, args.before,
                          after, args.solved)
        print("contest recorded" + (": performance %d" % perf if perf is not None else "") +
              (", rating %s -> %d (%s)" % (int(args.before) if args.before is not None else "?", after,
                                           rating.rank_title(after)) if after is not None else ""))
    elif args.cmd == "queue":
        rows = srs.queue(store, args.date, include_future=args.all, limit=args.limit)
        if not rows:
            print("nothing due")
        for r in rows:
            print("%-10s %-18s %-30s %5s  reps %d  ease %.2f%s" % (
                r["due"], "%s:%s" % (r["platform"], r["code"]), (r["name"] or "")[:30], r["difficulty"] or "-",
                r["reps"], r["ease"], "  overdue %dd" % r["overdue_days"] if r["overdue_days"] > 0 else ""))
    elif args.cmd == "review":
        pid = store.problem_by_ref(args.ref)
        quality = int(args.quality) if args.quality.isdigit() else srs.quality_from(args.quality.upper())
        print("next review on %s" % srs.review(store, pid, quality, args.date))
    elif args.cmd == "stats":
        ov = analysis.overall_stats(store)
        print("solved %(solved)d of %(attempted)d attempted (%(clean)d without help), %(attempts)d submissions" % ov)
        if ov["avg_difficulty"]:
            print("average solved difficulty %.0f, hardest %d" % (ov["avg_difficulty"], ov["max_difficulty"]))
        pr = analysis.practice_rating(store)
        if pr is not None:
            print("practice rating %.0f (%s)" % (pr, rating.rank_title(pr)))
        cur, longest = analysis.streaks(analysis.activity(store).keys())
        print("streak %d days (longest %d)" % (cur, longest))
        stats, _ = analysis.tag_stats(store)
        if stats:
            print("\n%-22s %6s %6s %7s %8s %8s" % ("topic", "tried", "clean", "rate", "avg D", "max D"))
            for t, s in sorted(stats.items(), key=lambda kv: -kv[1]["attempted"]):
                print("%-22s %6d %6d %6.0f%% %8s %8s" % (t, s["attempted"], s["clean"], 100 * s["raw_rate"],
                                                        "%.0f" % s["avg_difficulty"] if s["avg_difficulty"] else "-",
                                                        s["max_difficulty"] or "-"))
    elif args.cmd == "weak":
        rows = analysis.weaknesses(store, top=args.n)
        if not rows:
            print("not enough data: log a few attempts per topic first")
        for r in rows:
            print("%-22s score %.2f  %s" % (r["tag"], r["score"], "; ".join(r["reasons"]) or "-"))
        rec = analysis.recommend(store)
        print("practise problems rated %d-%d%s" % (rec["difficulty"][0], rec["difficulty"][1],
                                                   " on " + ", ".join(rec["tags"]) if rec["tags"] else ""))
    elif args.cmd == "dashboard":
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(dashboard.build(store, parse_day(args.date)))
        print("wrote " + args.output)
    elif args.cmd == "import-csv":
        n_p, n_a = importers.import_csv(store, args.path, not args.no_queue)
        print("imported %d rows, %d attempts" % (n_p, n_a))
    elif args.cmd == "import-cf":
        if not (args.status or args.rating):
            raise TrackerError("give --status and/or --rating JSON files")
        if args.status:
            print("submissions imported: %d" % importers.import_codeforces_status(store, args.status, args.queue))
        if args.rating:
            print("contests imported: %d" % importers.import_codeforces_rating(store, args.rating))
    elif args.cmd == "export":
        print("wrote " + importers.export_csv(store, args.path))
    return 0
