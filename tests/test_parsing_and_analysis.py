"""Unit tests for value parsing, sentiment and statistics."""

import json
from collections import Counter
from datetime import date

import pytest

from feedback_processor import FeedbackStats, clean_text, count_keywords, parse_date, parse_rating, score_sentiment


# ---------- ratings ----------
@pytest.mark.parametrize(
    "value, expected",
    [
        ("5", 5),
        (" 4 ", 4),
        ("4.0", 4),  # crashed the original (int('4.0'))
        ("1", 1),
        ("", None),  # blank
        ("   ", None),
        ("N/A", None),
        ("4.5", None),  # half stars are not valid
        ("0", None),  # out of range
        ("7", None),
        ("-3", None),
        (None, None),
    ],
)
def test_parse_rating(value, expected):
    assert parse_rating(value) == expected


# ---------- dates ----------
@pytest.mark.parametrize(
    "value, expected",
    [
        ("2026-09-01", date(2026, 9, 1)),
        ("2026/09/11", date(2026, 9, 11)),
        ("15/09/2026", date(2026, 9, 15)),  # day-first (European export)
        ("15.09.2026", date(2026, 9, 15)),
        (" 2026-09-01 ", date(2026, 9, 1)),
        ("", None),
        ("not a date", None),
        ("2026-02-30", None),  # impossible date
    ],
)
def test_parse_date(value, expected):
    assert parse_date(value) == expected


def test_parse_date_ambiguous_day_vs_month():
    assert parse_date("03/04/2026") == date(2026, 4, 3)  # default: day first
    assert parse_date("03/04/2026", month_first=True) == date(2026, 3, 4)
    assert parse_date("12/31/2026") == date(2026, 12, 31)  # only valid as month-first


def test_clean_text():
    assert clean_text("  good   value \n") == "good value"
    assert clean_text(None) == ""


# ---------- sentiment ----------
@pytest.mark.parametrize(
    "text, label",
    [
        ("Great service and fast delivery", "positive"),
        ("Terrible support - I want a refund", "negative"),
        ("It was okay", "neutral"),
        ("", "neutral"),
        ("GREAT!!! Love it.", "positive"),  # case and punctuation
        ("Customer is unhappy", "neutral"),  # original wrongly matched 'happy' inside 'unhappy'
        ("badge arrived", "neutral"),  # 'bad' inside 'badge' no longer counts
        ("Good product, but shipping was slow", "neutral"),
    ],
)
def test_score_sentiment_labels(text, label):
    assert score_sentiment(text)[1] == label


def test_sentiment_counts_distinct_words_like_original():
    # original rule: each word counts once per comment
    assert score_sentiment("good good good")[0] == 1
    assert score_sentiment("great, fast, helpful")[0] == 3


# ---------- keywords ----------
def test_count_keywords_has_no_hidden_shared_state():
    """The original used a mutable default argument, so counts leaked between calls."""
    first = count_keywords("delivery delivery late")
    second = count_keywords("delivery")
    assert first["delivery"] == 2
    assert second == Counter({"delivery": 1})


def test_count_keywords_skips_stopwords_and_punctuation():
    counts = count_keywords("The box was broken, the BOX!")
    assert counts == Counter({"box": 2, "broken": 1})


def test_count_keywords_handles_accents():
    assert count_keywords("Très bon café")["café"] == 1


# ---------- running statistics ----------
def _row(rid, rating, channel="web", comment="ok"):
    label = score_sentiment(comment)[1]
    return {"id": rid, "rating": rating, "channel": channel, "comment": comment, "sentiment": label}


def test_stats_averages_are_exact_not_floored():
    stats = FeedbackStats()
    for rid, rating in [("a", 4), ("b", 5), ("c", 4)]:
        stats.add(_row(rid, rating))
    assert stats.summary()["average_rating"] == 4.33  # original gave 4 (floor division)


def test_stats_follow_up_includes_two_star_reviews():
    stats = FeedbackStats()
    for rid, rating in [("one", 1), ("two", 2), ("three", 3)]:
        stats.add(_row(rid, rating))
    assert stats.summary()["follow_up_ids"] == ["one", "two"]  # original missed 'two'


def test_stats_unrated_rows_are_counted_but_not_averaged():
    stats = FeedbackStats()
    stats.add(_row("a", 4, "email"))
    stats.add(_row("b", None, "email"))
    stats.add(_row("c", None, "app"))
    s = stats.summary()
    assert s["total"] == 3 and s["rated_count"] == 1 and s["unrated_count"] == 2
    assert s["average_rating"] == 4.0
    assert s["channel_averages"] == {"email": 4.0, "app": None}  # no ZeroDivisionError


def test_empty_summary_is_valid_json():
    s = FeedbackStats().summary()
    assert s["total"] == 0 and s["average_rating"] is None
    json.dumps(s)  # must not raise


def test_top_keywords_respects_top_n():
    stats = FeedbackStats()
    stats.add(_row("a", 5, comment="alpha beta gamma delta alpha"))
    top = stats.summary(top_n=2)["top_keywords"]
    assert top[0] == ["alpha", 2] and len(top) == 2
