# Customer Feedback Processor

Reads customer-feedback CSV files, cleans them, scores each comment's sentiment, and writes:

1. a cleaned **CSV** with one row per review, and
2. a **summary JSON**: averages, sentiment counts, top keywords, and the reviews that need a follow-up.

Needs Python 3.9 or newer. There are no third-party dependencies (the standard library only).

## Quick start

```bash
python process_feedback.py samples/feedback_clean.csv
# INFO: read 8 rows from samples/feedback_clean.csv
# done: 8 rows from 1 file(s) (0 without a valid rating, 0 warnings)
#   -> output/processed_feedback.csv
#   -> output/summary.json
```

Several files are combined into one report:

```bash
python process_feedback.py jan.csv feb.csv mar.csv -o reports/q1
```

| Option | Meaning | Default |
|---|---|---|
| `-o`, `--output-dir` | Folder for results (created if missing) | `output` |
| `--top N` | How many top keywords to list | `10` |
| `--month-first` | Read `03/04/2026` as 4 March (US style) | day first (3 April) |
| `-q`, `--quiet` | Only print errors | off |

Exit codes: `0` all files processed · `1` some files skipped · `2` nothing could be processed.

## Input

A CSV file with a header row and one review per row.

| Column | Required | Accepted values |
|---|---|---|
| `id` | yes | any text |
| `rating` | yes | whole number 1–5 (`4` or `4.0`). Anything else is left blank and excluded from averages |
| `comment` | yes | free text (may contain commas or line breaks if quoted) |
| `date` | no | `2026-09-01`, `2026/09/01`, `01/09/2026`, `01.09.2026` |
| `customer` | no | any text |
| `channel` | no | e.g. email / web / app. Blank becomes `unknown` |

**Tolerated automatically:**
- Header names in any case or with extra spaces, plus common alternatives (`Score`, `Stars`, `Feedback`, `Comments`, `Source`, `Customer Name`, …).
- Commas, semicolons, tabs or pipes as the column separator.
- UTF-8 (with or without the Excel BOM), Windows-1252 and Latin-1 encodings.
- Blank lines, and extra spaces around values.

A file that is empty or missing a required column is **skipped with a clear message**; the other files still run. A bad value in a single row never stops the run: the row is kept, the bad field is left blank, and a warning with the line number is printed.

## Output

**`processed_feedback.csv`** has the same columns as before:
`id, date, customer, channel, rating, comment, sentiment_score, sentiment`. Dates are ISO (`YYYY-MM-DD`), channels are lower-case, and comments are trimmed.

**`summary.json`** (see `examples/output/summary.json`):

| Key | Meaning |
|---|---|
| `total` | Reviews read |
| `average_rating` | Mean of valid ratings, 2 decimals (`null` if none) |
| `channel_averages` | Mean rating per channel |
| `sentiment_counts` | Number of positive / negative / neutral comments |
| `five_star_count` | Number of 5-star reviews |
| `top_keywords` | `[word, count]` pairs, stop-words removed |
| `follow_up_ids` | IDs of 1- and 2-star reviews |
| `rated_count`, `unrated_count`, `channel_counts` | Data-quality and volume details |
| `files_processed`, `files_failed`, `row_warnings` | What happened during the run |

## How it works

```
CSV file(s) ─► reader.py ─────► parsing.py ─────► analysis.py ─────► processor.py
               encoding,         rating, date,     sentiment,         write CSV row,
               delimiter,        text clean-up     keywords,          update totals ─► summary.json
               headers                             running totals
```

Rows are **streamed**: each row is written out and added to running totals as soon as it is read. Large files therefore use little memory. A 200,000-row file takes about 5 seconds.

**Sentiment** counts the distinct positive words in a comment (great, good, love, …) and subtracts the distinct negative words (bad, slow, refund, …). A score above 0 is positive, below 0 is negative, and 0 is neutral. Whole words are matched, so "unhappy" is not "happy". This is a simple keyword method: it does not understand negation ("not good").

## Development

```bash
pip install pytest ruff flake8
python -m pytest              # 65 tests: typical files, edge cases, CLI, parity with the original
ruff check . && flake8 .      # PEP 8 / lint: 0 issues
python benchmarks/benchmark.py
```

## Project layout

```
process_feedback.py        entry point (same name and usage as the original script)
feedback_processor/        reader.py · parsing.py · analysis.py · processor.py · cli.py
tests/                     unit, edge-case, end-to-end and "nothing removed" tests
samples/                   7 test inputs: clean, Excel/BOM, semicolon + accents, messy values, empty, 0-byte, missing column
examples/                  output produced from the samples (+ run log)
original/                  the teammate's script, unchanged, for comparison
docs/BUG_REPORT.md         every bug found, explained in plain language
docs/CHANGES.md            refactoring, performance benchmark, conventions
benchmarks/benchmark.py    original vs refactored speed and memory
```
