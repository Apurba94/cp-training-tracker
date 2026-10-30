"""Self-contained HTML progress dashboard (inline SVG charts, no JavaScript, no external assets)."""
import datetime
import html

from . import analysis, srs
from .rating import rank_title

CSS = """
:root{--bg:#fafbfc;--card:#fff;--ink:#1f2328;--muted:#656d76;--line:#d0d7de;--accent:#0969da}
@media (prefers-color-scheme: dark){:root{--bg:#0d1117;--card:#161b22;--ink:#e6edf3;--muted:#8d96a0;--line:#30363d;--accent:#4493f8}}
body{background:var(--bg);color:var(--ink);font-family:system-ui,sans-serif;margin:0;padding:20px}
h1{font-size:22px;margin:0 0 14px}h2{font-size:15px;margin:0 0 10px;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px;overflow:auto}
.kpis{display:flex;flex-wrap:wrap;gap:18px}.kpi b{display:block;font-size:24px}.kpi span{color:var(--muted);font-size:12px}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{text-align:left;padding:4px 6px;border-bottom:1px solid var(--line)}
svg text{fill:var(--muted);font-size:10px}.muted{color:var(--muted)}
"""
LEVELS = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]


def _esc(s):
    return html.escape(str(s))


def line_chart(points, width=460, height=180, label=""):
    """points: [(day_iso, value)]"""
    if not points:
        return "<p class='muted'>no data yet</p>"
    days = [datetime.date.fromisoformat(d).toordinal() for d, _ in points]
    vals = [v for _, v in points]
    x0, x1 = min(days), max(days)
    y0, y1 = min(vals), max(vals)
    pad = max(50, (y1 - y0) * 0.1)
    y0, y1 = y0 - pad, y1 + pad

    def px(d):
        return 40 + (d - x0) / ((x1 - x0) or 1) * (width - 55)

    def py(v):
        return height - 20 - (v - y0) / ((y1 - y0) or 1) * (height - 35)
    pts = " ".join("%.1f,%.1f" % (px(d), py(v)) for d, v in zip(days, vals))
    out = ["<svg width='%d' height='%d' role='img' aria-label='%s'>" % (width, height, _esc(label))]
    for k in range(5):
        v = y0 + (y1 - y0) * k / 4
        out.append("<line x1='40' x2='%d' y1='%.1f' y2='%.1f' stroke='currentColor' opacity='0.12'/>"
                   "<text x='34' y='%.1f' text-anchor='end'>%d</text>" % (width - 15, py(v), py(v), py(v) + 3, v))
    out.append("<polyline fill='none' stroke='#0969da' stroke-width='2' points='%s'/>" % pts)
    for d, v in zip(days, vals):
        out.append("<circle cx='%.1f' cy='%.1f' r='3' fill='#0969da'><title>%s: %d</title></circle>"
                   % (px(d), py(v), datetime.date.fromordinal(d).isoformat(), v))
    out.append("<text x='40' y='%d'>%s</text><text x='%d' y='%d' text-anchor='end'>%s</text>" % (
        height - 4, datetime.date.fromordinal(x0).isoformat(), width - 15, height - 4,
        datetime.date.fromordinal(x1).isoformat()))
    out.append("</svg>")
    return "".join(out)


def calendar_heatmap(counts, today, weeks=26, cell=12):
    t = datetime.date.fromisoformat(today)
    start = t - datetime.timedelta(days=t.weekday() + 7 * (weeks - 1))
    width, height = 30 + weeks * (cell + 2), 20 + 7 * (cell + 2)
    out = ["<svg width='%d' height='%d' role='img' aria-label='activity'>" % (width, height)]
    for i, name in ((0, "Mon"), (2, "Wed"), (4, "Fri")):
        out.append("<text x='0' y='%d'>%s</text>" % (20 + i * (cell + 2) + cell - 2, name))
    mx = max(counts.values()) if counts else 1
    for w in range(weeks):
        for d in range(7):
            day = start + datetime.timedelta(days=7 * w + d)
            if day > t:
                continue
            c = counts.get(day.isoformat(), 0)
            level = 0 if c == 0 else min(4, 1 + int(3 * c / max(1, mx)))
            out.append("<rect x='%d' y='%d' width='%d' height='%d' rx='2' fill='%s'><title>%s: %d</title></rect>"
                       % (30 + w * (cell + 2), 20 + d * (cell + 2), cell, cell, LEVELS[level], day.isoformat(), c))
        if (start + datetime.timedelta(weeks=w)).day <= 7:
            out.append("<text x='%d' y='12'>%s</text>" % (30 + w * (cell + 2),
                                                          (start + datetime.timedelta(weeks=w)).strftime("%b")))
    out.append("</svg>")
    return "".join(out)


def bar_chart(items, width=460, bar_h=16, fmt="%.0f%%", scale=100.0, max_value=1.0):
    """items: [(label, value in 0..max_value, note)]"""
    if not items:
        return "<p class='muted'>no data yet</p>"
    height = 10 + len(items) * (bar_h + 6)
    out = ["<svg width='%d' height='%d'>" % (width, height)]
    for i, (label, value, note) in enumerate(items):
        y = 5 + i * (bar_h + 6)
        w = max(1, (width - 230) * min(value, max_value) / max_value)
        out.append("<text x='120' y='%d' text-anchor='end'>%s</text>" % (y + bar_h - 4, _esc(label[:20])))
        out.append("<rect x='126' y='%d' width='%.1f' height='%d' rx='3' fill='#40c463'/>" % (y, w, bar_h))
        out.append("<text x='%.1f' y='%d'>%s %s</text>" % (130 + w, y + bar_h - 4, fmt % (value * scale), _esc(note)))
    out.append("</svg>")
    return "".join(out)


def build(store, today=None, title="Training dashboard"):
    today = today or datetime.date.today().isoformat()
    ov = analysis.overall_stats(store)
    pr = analysis.practice_rating(store)
    cur, longest = analysis.streaks(analysis.activity(store).keys(), today)
    rating = store.current_rating()
    contests = [(c["day"], c["rating_after"]) for c in store.contests() if c["rating_after"] is not None]
    perf = [(c["day"], c["performance"]) for c in store.contests() if c["performance"] is not None]
    stats, _ = analysis.tag_stats(store)
    tag_items = sorted(stats.items(), key=lambda kv: -kv[1]["attempted"])[:14]
    bars = [(t, s["raw_rate"], "(%d/%d)" % (s["clean"], s["attempted"])) for t, s in tag_items]
    weak = analysis.weaknesses(store)
    rec = analysis.recommend(store)
    q = srs.queue(store, today, limit=12)
    hist = analysis.difficulty_histogram(store)
    hmax = max(hist.values()) if hist else 1
    hist_bars = [(str(k), v / hmax, "") for k, v in hist.items()]

    kpis = [("problems solved", ov["solved"]), ("clean solves", ov["clean"]),
            ("submissions", ov["attempts"]), ("hours", "%.1f" % (ov["minutes"] / 60.0)),
            ("current streak", "%d d" % cur), ("longest streak", "%d d" % longest),
            ("practice rating", "%d" % pr if pr is not None else "-"),
            ("contest rating", "%d (%s)" % (rating, rank_title(rating)) if rating is not None else "-"),
            ("due upsolves", len(srs.queue(store, today)))]
    kpi_html = "".join("<div class='kpi'><b>%s</b><span>%s</span></div>" % (_esc(v), _esc(k)) for k, v in kpis)
    weak_rows = "".join("<tr><td>%s</td><td>%d</td><td>%s</td></tr>" % (_esc(w["tag"]), w["attempted"],
                                                                      _esc("; ".join(w["reasons"]) or "-"))
                        for w in weak) or "<tr><td colspan='3' class='muted'>not enough data</td></tr>"
    q_rows = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        _esc("%s:%s" % (r["platform"], r["code"])), _esc(r["name"] or ""), _esc(r["difficulty"] or "-"),
        _esc(r["due"]) + (" (+%dd)" % r["overdue_days"] if r["overdue_days"] > 0 else ""))
        for r in q) or "<tr><td colspan='4' class='muted'>nothing due</td></tr>"
    rec_html = "Next: problems rated <b>%d-%d</b>%s" % (rec["difficulty"][0], rec["difficulty"][1],
                                                         ", topics: <b>%s</b>" % _esc(", ".join(rec["tags"]))
                                                         if rec["tags"] else "")
    return ("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            "<title>%s</title><style>%s</style></head><body><h1>%s</h1>"
            "<div class='card' style='margin-bottom:14px'><div class='kpis'>%s</div><p>%s</p></div>"
            "<div class='grid'>"
            "<div class='card'><h2>Activity</h2>%s</div>"
            "<div class='card'><h2>Contest rating</h2>%s</div>"
            "<div class='card'><h2>Best difficulty solved</h2>%s</div>"
            "<div class='card'><h2>Clean-solve rate by topic</h2>%s</div>"
            "<div class='card'><h2>Solved by difficulty</h2>%s</div>"
            "<div class='card'><h2>Weakest topics</h2><table><tr><th>topic</th><th>tried</th><th>why</th></tr>%s"
            "</table></div>"
            "<div class='card'><h2>Upsolve queue</h2><table><tr><th>problem</th><th>name</th><th>rating</th>"
            "<th>due</th></tr>%s</table></div>"
            "<div class='card'><h2>Contest performance</h2>%s</div>"
            "</div><p class='muted'>generated %s</p></body></html>"
            % (_esc(title), CSS, _esc(title), kpi_html, rec_html,
               calendar_heatmap(analysis.activity(store), today),
               line_chart(contests, label="rating"), line_chart(analysis.difficulty_progress(store), label="difficulty"),
               bar_chart(bars), bar_chart(hist_bars, fmt="%d", scale=hmax), weak_rows, q_rows,
               line_chart(perf, label="performance"), _esc(today)))
