"""Pipeline: read files -> clean each row -> write processed CSV + summary JSON."""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .analysis import FeedbackStats, score_sentiment
from .parsing import clean_text, parse_date, parse_rating
from .reader import InputFileError, read_numbered_rows

log = logging.getLogger("feedback_processor")

OUTPUT_COLUMNS = ["id", "date", "customer", "channel", "rating", "comment", "sentiment_score", "sentiment"]
PROCESSED_CSV = "processed_feedback.csv"
SUMMARY_JSON = "summary.json"
MAX_ROW_WARNINGS = 20  # per file; the rest are counted, not printed


@dataclass
class RunResult:
    """What happened during a run (used by the CLI and by tests)."""

    stats: FeedbackStats
    files_ok: list[str] = field(default_factory=list)
    files_failed: dict[str, str] = field(default_factory=dict)
    row_warnings: int = 0
    output_csv: Path | None = None
    output_json: Path | None = None


def process_row(raw: dict[str, str], month_first: bool = False) -> tuple[dict, list[str]]:
    """Turn one raw CSV row into a processed row. Returns (row, warnings).

    Invalid values never stop the run: a bad rating becomes blank (and is left
    out of averages) and a bad date becomes blank.
    """
    warnings = []
    rating_text = raw.get("rating", "")
    rating = parse_rating(rating_text)
    if rating is None:
        warnings.append(f"rating {rating_text.strip()!r} is missing or not 1-5")

    date_text = raw.get("date", "")
    parsed_date = parse_date(date_text, month_first=month_first)
    if parsed_date is None and date_text.strip():
        warnings.append(f"date {date_text.strip()!r} not recognised")

    comment = clean_text(raw.get("comment"))
    score, label = score_sentiment(comment)
    row = {
        "id": clean_text(raw.get("id")),
        "date": parsed_date.isoformat() if parsed_date else "",
        "customer": clean_text(raw.get("customer")),
        "channel": clean_text(raw.get("channel")).lower() or "unknown",
        "rating": rating,
        "comment": comment,
        "sentiment_score": score,
        "sentiment": label,
    }
    if not row["id"]:
        warnings.append("row has no id")
    return row, warnings


def process_files(
    paths: Iterable[str | Path],
    output_dir: str | Path = "output",
    top_n: int = 10,
    month_first: bool = False,
) -> RunResult:
    """Process one or more feedback files into ``output_dir``.

    Rows are streamed: each row is written to the output CSV and added to the
    running statistics as soon as it is read, so memory use does not grow with
    file size. A file that cannot be read is reported and skipped; the other
    files are still processed.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = RunResult(stats=FeedbackStats())
    result.output_csv = out / PROCESSED_CSV
    result.output_json = out / SUMMARY_JSON

    with result.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for path in paths:
            _process_one_file(Path(path), writer, result, month_first)

    summary = result.stats.summary(top_n=top_n)
    summary["files_processed"] = result.files_ok
    summary["files_failed"] = result.files_failed
    summary["row_warnings"] = result.row_warnings
    with result.output_json.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
    return result


def _process_one_file(path: Path, writer: csv.DictWriter, result: RunResult, month_first: bool) -> None:
    rows_read = 0
    warnings_here = 0
    try:
        for line_no, raw in read_numbered_rows(path):
            row, warnings = process_row(raw, month_first=month_first)
            writer.writerow({**row, "rating": "" if row["rating"] is None else row["rating"]})
            result.stats.add(row)
            rows_read += 1
            for message in warnings:
                warnings_here += 1
                if warnings_here <= MAX_ROW_WARNINGS:
                    log.warning("%s line %d: %s", path.name, line_no, message)
    except InputFileError as exc:
        result.files_failed[str(path)] = str(exc)
        log.error("skipped %s", exc)
        return
    except (OSError, UnicodeError, ValueError) as exc:  # unexpected read problem
        result.files_failed[str(path)] = f"could not read file: {exc}"
        log.error("skipped %s: %s", path, exc)
        return

    if warnings_here > MAX_ROW_WARNINGS:
        log.warning("%s: %d more warnings not shown", path.name, warnings_here - MAX_ROW_WARNINGS)
    result.row_warnings += warnings_here
    result.files_ok.append(str(path))
    log.info("read %d rows from %s", rows_read, path)
