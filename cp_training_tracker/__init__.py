"""cp-training-tracker: practice log, contest ratings, spaced-repetition upsolving and weakness analysis."""
from .analysis import (difficulty_progress, overall_stats, practice_rating, recommend, streaks, tag_stats,
                       weaknesses)
from .db import Store, TrackerError, parse_ref
from .rating import (cf_rating_changes, estimate_difficulty, estimate_skill, performance, rank_title,
                     win_probability)
from .srs import queue, review, schedule, sm2

__version__ = "0.1.0"
