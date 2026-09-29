"""Customer feedback processor: clean CSV feedback, score sentiment, summarise."""

from .analysis import FeedbackStats, count_keywords, score_sentiment, tokenize
from .parsing import clean_text, parse_date, parse_rating
from .processor import OUTPUT_COLUMNS, process_files, process_row
from .reader import InputFileError, read_numbered_rows, read_rows

__all__ = [
    "OUTPUT_COLUMNS",
    "FeedbackStats",
    "InputFileError",
    "clean_text",
    "count_keywords",
    "parse_date",
    "parse_rating",
    "process_files",
    "process_row",
    "read_numbered_rows",
    "read_rows",
    "score_sentiment",
    "tokenize",
]
__version__ = "2.0.0"
