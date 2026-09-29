"""Command-line interface.

Usage: python process_feedback.py FILE [FILE ...] [-o OUTPUT_DIR] [--top N] [--month-first]
"""

from __future__ import annotations

import argparse
import logging
import sys

from .processor import process_files

EXIT_OK = 0
EXIT_SOME_FILES_FAILED = 1
EXIT_NOTHING_PROCESSED = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="process_feedback.py",
        description="Clean customer feedback CSV files, score sentiment, and write a summary.",
    )
    parser.add_argument("files", nargs="+", help="one or more feedback CSV files")
    parser.add_argument("-o", "--output-dir", default="output", help="folder for results (default: output)")
    parser.add_argument("--top", type=int, default=10, metavar="N", help="number of top keywords (default: 10)")
    parser.add_argument(
        "--month-first",
        action="store_true",
        help="read ambiguous dates like 03/04/2026 as March 4 (default: 3 April)",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="only print errors")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.ERROR if args.quiet else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    result = process_files(args.files, args.output_dir, top_n=args.top, month_first=args.month_first)
    stats = result.stats
    if not args.quiet:
        print(
            f"done: {stats.total} rows from {len(result.files_ok)} file(s) "
            f"({stats.total - stats.rated} without a valid rating, {result.row_warnings} warnings)\n"
            f"  -> {result.output_csv}\n  -> {result.output_json}"
        )
    if not result.files_ok:
        return EXIT_NOTHING_PROCESSED
    return EXIT_SOME_FILES_FAILED if result.files_failed else EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
