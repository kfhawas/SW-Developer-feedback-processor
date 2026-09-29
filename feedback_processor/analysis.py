"""Sentiment scoring, keyword counting and running statistics."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

# Sets give O(1) membership checks (the original used lists).
POSITIVE_WORDS = frozenset(
    {
        "great",
        "good",
        "love",
        "excellent",
        "happy",
        "fast",
        "helpful",
        "amazing",
        "easy",
        "friendly",
    }
)
NEGATIVE_WORDS = frozenset(
    {
        "bad",
        "slow",
        "terrible",
        "hate",
        "broken",
        "rude",
        "late",
        "poor",
        "difficult",
        "refund",
    }
)
STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "is",
        "was",
        "it",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "my",
        "i",
        "me",
        "this",
        "that",
        "very",
        "so",
        "they",
        "we",
        "you",
        "not",
        "be",
        "have",
        "had",
        "at",
        "are",
        "were",
        "as",
        "our",
        "your",
        "their",
        "from",
        "just",
        "too",
        "again",
        "all",
        "no",
    }
)

# Letters/digits (any language), allowing an inner apostrophe: "don't", "café".
_WORD_RE = re.compile(r"[^\W_]+(?:'[^\W_]+)*")

FOLLOW_UP_MAX_RATING = 2  # ratings of 1 or 2 need a follow-up


def tokenize(text: str) -> list[str]:
    """Lower-case words in the text, punctuation removed."""
    return _WORD_RE.findall(text.lower())


def score_sentiment(text: str) -> tuple[int, str]:
    """Return (score, label) for a comment.

    Score = number of distinct positive words minus number of distinct
    negative words (same rule as the original script, but matched on whole
    words, so 'unhappy' no longer counts as 'happy').
    """
    words = set(tokenize(text))
    score = len(words & POSITIVE_WORDS) - len(words & NEGATIVE_WORDS)
    if score > 0:
        return score, "positive"
    if score < 0:
        return score, "negative"
    return score, "neutral"


def count_keywords(text: str, counts: Counter[str] | None = None) -> Counter[str]:
    """Add non-stopword words from ``text`` to ``counts`` (a new Counter if None)."""
    counts = Counter() if counts is None else counts
    counts.update(w for w in tokenize(text) if w not in STOPWORDS)
    return counts


def _average(total: int, count: int) -> float | None:
    return round(total / count, 2) if count else None


@dataclass
class FeedbackStats:
    """Running totals, updated one row at a time (no need to keep all rows in memory)."""

    total: int = 0
    rated: int = 0
    rating_sum: int = 0
    five_star_count: int = 0
    channel_sums: dict[str, int] = field(default_factory=dict)
    channel_rated: dict[str, int] = field(default_factory=dict)
    channel_counts: Counter[str] = field(default_factory=Counter)
    sentiment_counts: dict[str, int] = field(default_factory=lambda: {"positive": 0, "negative": 0, "neutral": 0})
    keywords: Counter[str] = field(default_factory=Counter)
    follow_up_ids: list[str] = field(default_factory=list)

    def add(self, row: dict) -> None:
        """Update totals with one processed row."""
        self.total += 1
        channel = row["channel"]
        self.channel_counts[channel] += 1
        self.sentiment_counts[row["sentiment"]] += 1
        count_keywords(row["comment"], self.keywords)

        rating = row["rating"]
        if rating is None:
            return
        self.rated += 1
        self.rating_sum += rating
        self.channel_sums[channel] = self.channel_sums.get(channel, 0) + rating
        self.channel_rated[channel] = self.channel_rated.get(channel, 0) + 1
        if rating == 5:
            self.five_star_count += 1
        if rating <= FOLLOW_UP_MAX_RATING:
            self.follow_up_ids.append(row["id"])

    def summary(self, top_n: int = 10) -> dict:
        """JSON-serialisable summary. Keys match the original script, plus extras."""
        return {
            "total": self.total,
            "average_rating": _average(self.rating_sum, self.rated),
            "channel_averages": {
                ch: _average(self.channel_sums.get(ch, 0), self.channel_rated.get(ch, 0)) for ch in self.channel_counts
            },
            "sentiment_counts": dict(self.sentiment_counts),
            "five_star_count": self.five_star_count,
            "top_keywords": [[w, c] for w, c in self.keywords.most_common(top_n)],
            "follow_up_ids": list(self.follow_up_ids),
            # Added in the refactor (new keys only; nothing removed):
            "rated_count": self.rated,
            "unrated_count": self.total - self.rated,
            "channel_counts": dict(self.channel_counts),
        }
