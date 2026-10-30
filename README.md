# cp-training-tracker

A local, private training log for competitive programmers that does the thinking a spreadsheet does
not: it rates your practice, schedules upsolves with spaced repetition, finds the topics that hold you
back, and renders a dashboard.

* **Log** problems (Codeforces, AtCoder, CSES, LeetCode, … by `platform:code` or URL) with difficulty,
  tags, verdicts, minutes and how much help you used (`none` / `hint` / `editorial`).
* **Upsolving queue (SM-2)** – a failed attempt or a solve that needed the editorial enters the queue;
  re-solving cleanly pushes it out 1 → 6 → ~15 → ~40 days, failing resets it. Logging an AC on a due
  problem counts as the review automatically.
* **Ratings**
  * contest *performance* against a list of opponent ratings (the rating at which your place is the
    expected place under Elo),
  * the full **Codeforces rating-change algorithm** for a standings file (seed, geometric mean with the
    rank, half-gap delta, sum and top-participant corrections),
  * a **practice rating**: maximum-a-posteriori skill from clean solves vs. failures on rated problems,
  * the reverse — estimate a problem's difficulty from who solved it.
* **Weakness analysis** – per-topic clean-solve rates with Bayesian smoothing, difficulty gap against
  your average, submissions per AC; ranked with reasons, plus a recommended difficulty band.
* **Dashboard** – one self-contained HTML file (light/dark), with activity calendar, rating and
  best-difficulty lines, per-topic bars, difficulty histogram, weakest topics and the due queue.
* **Import/export** – generic CSV, and saved Codeforces API JSON (`user.status`, `user.rating`)
  imported idempotently without network access from the tool.

Pure standard library (sqlite3), Python ≥ 3.9. Data lives in `~/.cp-training.sqlite3`
(override with `--db` or `CP_TRACKER_DB`).

## Usage

```bash
cp-tracker log cf:1520B WA -d 800 -t math,brute-force -m 25
cp-tracker log https://codeforces.com/contest/1520/problem/B AC --help-used hint
cp-tracker queue                       # what to upsolve today
cp-tracker review cf:1520B 5           # or: review cf:1520B AC
cp-tracker stats
cp-tracker weak
cp-tracker contest "Virtual ABC 300" --rank 412 --before 1450 --opponents ratings.txt
cp-tracker rating-changes standings.csv   # handle,rating,rank
cp-tracker import-cf --status status.json --rating rating.json --queue
cp-tracker dashboard -o dashboard.html
```

(`cp-tracker` is `python -m cp_training_tracker`.)

### CSV format

```
platform,code,name,difficulty,tags,day,verdict,minutes,help,notes
cf,1A,Theatre Square,1000,math;implementation,2026-01-01,AC,10,none,
```

## Design notes

* "Clean" solves (AC without help) drive the ratings and weaknesses: a solve after reading the
  editorial is progress, but it is not evidence that you can do it in a contest.
* The practice rating uses a weak Gaussian prior (1500 ± 700) so it is defined after one problem and
  does not diverge when everything is solved.
* All dates are ISO `YYYY-MM-DD`; `--date` lets you back-fill history.

## Tests

```bash
python -m unittest discover -s tests -t .
```

## License

MIT
