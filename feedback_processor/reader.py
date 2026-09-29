"""Robust CSV reading: encoding detection, delimiter sniffing and header clean-up."""

from __future__ import annotations

import codecs
import csv
from collections.abc import Iterator
from pathlib import Path

# Tried in order. latin-1 can decode any byte sequence, so it is the last resort.
ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")
DELIMITERS = ",;\t|"
SNIFF_BYTES = 64 * 1024
CHUNK_BYTES = 1024 * 1024

REQUIRED_COLUMNS = ("id", "rating", "comment")
OPTIONAL_COLUMNS = ("date", "customer", "channel")

# Common alternative header names -> canonical name.
HEADER_ALIASES = {
    "feedback_id": "id",
    "review_id": "id",
    "score": "rating",
    "stars": "rating",
    "feedback": "comment",
    "comments": "comment",
    "review": "comment",
    "customer_name": "customer",
    "name": "customer",
    "source": "channel",
    "submitted": "date",
    "created_at": "date",
}


class InputFileError(Exception):
    """Raised when a file cannot be used at all (missing, empty, wrong columns)."""


def detect_encoding(path: Path) -> str:
    """Return the first encoding in ENCODINGS that decodes the whole file.

    The file is streamed in chunks, so large files do not need to fit in memory.
    """
    for encoding in ENCODINGS:
        decoder = codecs.getincrementaldecoder(encoding)()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
                    decoder.decode(chunk)
                decoder.decode(b"", final=True)
            return encoding
        except UnicodeDecodeError:
            continue
    return "latin-1"  # pragma: no cover - latin-1 never fails


def sniff_delimiter(sample: str) -> str:
    """Guess the delimiter from a text sample; default to a comma."""
    try:
        return csv.Sniffer().sniff(sample, delimiters=DELIMITERS).delimiter
    except csv.Error:
        return ","


def normalize_header(name: str) -> str:
    """'  Rating ' -> 'rating', 'Customer Name' -> 'customer' (via aliases)."""
    key = "_".join(name.replace("﻿", "").strip().lower().split())
    return HEADER_ALIASES.get(key, key)


def read_rows(path: str | Path) -> Iterator[dict[str, str]]:
    """Yield each data row of a CSV file as a dict keyed by canonical column names.

    See ``read_numbered_rows`` for details; this variant drops the line numbers.
    """
    for _line_no, row in read_numbered_rows(path):
        yield row


def read_numbered_rows(path: str | Path) -> Iterator[tuple[int, dict[str, str]]]:
    """Yield ``(line_number, row)`` for each data row; line numbers match the file.

    Handles UTF-8 (with or without BOM), Windows-1252/Latin-1, comma/semicolon/
    tab/pipe delimiters, quoted fields containing delimiters or newlines, and
    messy header names. Completely blank lines are skipped.

    Raises:
        InputFileError: if the file is missing, empty, or lacks required columns.
    """
    path = Path(path)
    if not path.is_file():
        raise InputFileError(f"file not found: {path}")
    if path.stat().st_size == 0:
        raise InputFileError(f"file is empty (0 bytes): {path}")

    encoding = detect_encoding(path)
    with path.open("r", encoding=encoding, newline="") as handle:
        delimiter = sniff_delimiter(handle.read(SNIFF_BYTES))
        handle.seek(0)
        reader = csv.reader(handle, delimiter=delimiter)
        try:
            raw_header = next(reader)
        except StopIteration:  # pragma: no cover - guarded by size check
            raise InputFileError(f"file has no header row: {path}") from None

        header = [normalize_header(h) for h in raw_header]
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        if missing:
            raise InputFileError(
                f"{path.name}: missing required column(s) {', '.join(missing)}; "
                f"found {', '.join(h for h in header if h) or 'none'}"
            )

        start_line = reader.line_num + 1
        for values in reader:
            line_no, start_line = start_line, reader.line_num + 1  # a quoted field may span lines
            if not any(v.strip() for v in values):
                continue  # blank line
            # Short rows are padded; extra trailing cells are ignored.
            values = values + [""] * (len(header) - len(values))
            yield line_no, {name: value for name, value in zip(header, values) if name}
