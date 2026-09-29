# Bug report: `process_feedback.py`

**Script:** `original/process_feedback.py` (kept unchanged for reference)
**Fixed in:** the `feedback_processor/` package; `process_feedback.py` is still the entry point.
**How we found them:** we ran the original on 7 sample files (`samples/`), read its warnings and linter output, profiled it, and compared its numbers with hand-calculated ones.

## Summary for everyone

The script worked only on "perfect" files: plain English text, commas between columns, dates written as `2026-09-01`, a whole number in every rating, and an `output/` folder that already existed. Real exports from Excel, European systems or messy forms broke it. **Even when it did run, some numbers in the report were wrong.**

| Sample file | Original script | Fixed script |
|---|---|---|
| `feedback_clean.csv` | Runs, but **drops the last review** and reports wrong averages | 8 rows, correct numbers |
| `feedback_excel_export.csv` | ❌ Crash: `KeyError: 'rating'` | 4 rows |
| `feedback_semicolon_eu.csv` | ❌ Crash: `UnicodeDecodeError` | 3 rows, accents intact |
| `feedback_messy_values.csv` | ❌ Crash: `ValueError: '4.0'` | 7 rows, 3 bad ratings left blank + warnings |
| `feedback_empty.csv` (header only) | ❌ Crash: `ZeroDivisionError` | 0 rows, valid empty report |
| `feedback_zero_bytes.csv` | ❌ Crash: `IndexError` | Clear message: "file is empty" |
| `feedback_missing_column.csv` | ❌ Crash: `ZeroDivisionError` (misleading) | Clear message: "missing required column rating" |
| Any file, no `output/` folder | ❌ Crash: `FileNotFoundError` | Folder is created |

---

## A. Why some files could not be read (the reported problem)

### A1. Excel files: invisible marker and spaces in column names → `KeyError`
**In plain words:** Excel quietly adds an invisible character at the start of the file, and this export named a column `Rating ` (with a trailing space) and used capitals (`ID`). The script looked for exactly `rating`, didn't find it, and stopped.
**Cause:** headers were used as-is; no BOM handling, no trimming or lower-casing.
```python
# before
header = lines[0].strip().split(',')        # ['﻿ID', ..., 'Rating ', ...]
rating = int(row['rating'])                 # KeyError
# after (reader.py)
open(..., encoding="utf-8-sig")             # strips the BOM
header = [normalize_header(h) for h in raw_header]   # '  Rating ' -> 'rating', 'Score' -> 'rating'
```

### A2. Commas inside comments split the row → wrong columns
**In plain words:** the script cut each line at every comma. A comment like *"Good product, but slow"* was cut into two pieces, so everything after it moved one column to the right.
**Cause:** `line.split(',')` instead of a CSV parser, which understands quotes.
```python
# before
parts = lines[i].strip().split(',')
# after
reader = csv.reader(handle, delimiter=delimiter)   # respects "quoted, text" and multi-line comments
```

### A3. Accented characters (é, ü, ß) → `UnicodeDecodeError`
**In plain words:** files from some systems use an older way of storing letters like é. The script assumed one format and crashed on the first accented name. It also behaved differently on Windows and Mac, because it relied on each computer's default setting.
**Cause:** `open(fname)` with no encoding.
**Fix:** `detect_encoding()` tries UTF-8 (with or without BOM), then Windows-1252, then Latin-1, checking the whole file in chunks.

### A4. Semicolon-separated files → every value in one column
**In plain words:** European Excel saves CSV files with `;` between columns. The script only knew about `,`.
**Fix:** `sniff_delimiter()` detects `,` `;` tab or `|`.

### A5. Empty file (0 bytes) → `IndexError`
**Cause:** `lines[0]` on an empty list. **Fix:** checked up front, with a clear message. The other files are still processed.

### A6. Ratings like `4.0`, blank, `N/A` → `ValueError`; `7` silently accepted
**In plain words:** one odd rating stopped the whole job. Meanwhile an impossible rating of 7 was counted and pushed the average up.
```python
# before
rating = int(row['rating'])
# after (parsing.py)
def parse_rating(value):       # '4.0' -> 4; '', 'N/A', '4.5', '7' -> None (row kept, left out of averages, warning logged)
```

### A7. Dates in other formats → `ValueError`
**Cause:** only `%Y-%m-%d` was accepted. **Fix:** `parse_date()` accepts ISO, `2026/09/11`, `15/09/2026`, `15.09.2026` (day-first by default, `--month-first` for US). An unreadable date becomes blank with a warning; the row is kept.

### A8. No usable rows → `ZeroDivisionError`
**In plain words:** with nothing to average, the script divided by zero. The *missing-column* file also hit this, which hid the real problem.
**Fix:** averages are `None` when there is nothing to average, and a missing column gives its own clear error.

### A9. Missing `output/` folder → `FileNotFoundError`
**Fix:** `Path(output_dir).mkdir(parents=True, exist_ok=True)`. The folder can also be chosen with `-o`.

---

## B. Wrong results without any error (logic bugs)

| # | Plain-language explanation | Cause → fix |
|---|---|---|
| B1 | **The last review in every file was ignored.** On the clean sample, 7 of 8 reviews were counted. | `range(1, len(lines)-1)` stops one row early → iterate the CSV reader |
| B2 | **Averages were rounded down to whole numbers.** 3.25 was reported as 3, and 4.9 would show as 4. | `//` (whole-number division) → `/` rounded to 2 decimals |
| B3 | **2-star reviews were never flagged for follow-up**, although the comment says "1 and 2 star". On the clean sample, F002 and F006 were missed. | `rating < 2` → `rating <= FOLLOW_UP_MAX_RATING` (2) |
| B4 | **"unhappy" counted as happy, "badge" as bad**, because words were matched inside other words. | `if w in text` (substring) → split the text into whole words and compare sets |
| B5 | **Keyword counts could carry over between runs**, which made results depend on what ran before. It worked in a single run only by accident. | Mutable default `counts={}` → `count_keywords(text, counts=None)` with a fresh `Counter` |
| B6 | **The output CSV broke when a comment contained a comma** (Excel showed shifted columns). | Rows joined with `+ ","` → `csv.DictWriter`, which quotes fields |
| B7 | **The same channel could appear twice** (`web` and ` web `) because of stray spaces. | Only `.lower()` → `clean_text(...).lower()`, and a blank channel becomes `unknown` |
| B8 | **Running the processing twice in one program doubled the totals.** | Global `allRows` / `fiveStar` → state lives in a `FeedbackStats` object per run |

## C. Syntax-level problems and code hygiene

| # | Issue | Python / linter says | Fix |
|---|---|---|---|
| C1 | `if rating is 5:` | `SyntaxWarning: "is" with a literal. Did you mean "=="?` It works only by coincidence (small numbers are cached) | `== 5` |
| C2 | `re.sub('[^\w\s]', ...)` | `DeprecationWarning: invalid escape sequence '\w'` (a `SyntaxWarning` from Python 3.12, a future error) | Raw string `r"..."`, precompiled |
| C3 | Files opened without being closed | Data may not be fully written, and file handles leak | `with open(...)` everywhere |
| C4 | Style | **79 flake8 findings**: missing spaces, one-line `if`s, camelCase names, unused imports `os` and `csv`, several imports on one line | 0 findings (ruff + flake8, PEP 8, line length 120) |

## D. Performance problems

| # | Issue | Measured effect | Fix |
|---|---|---|---|
| D1 | The output file was built by gluing strings together one row at a time, which is quadratic: the work grows with the *square* of the number of rows | That loop alone takes **9.6 s for 10,000 rows**. Overall: 10k rows 8.3 s, 20k 45 s, 40k 198 s; 200k didn't finish in 6 minutes | Stream rows with `csv.DictWriter` |
| D2 | The whole file was loaded (`readlines()`), and every row was kept in memory | Memory grows with file size (59 MB at 40k rows) | Stream rows and keep only running totals, flat at about 17 MB |
| D3 | Word lists were checked item by item, keywords were counted by hand, and every row was re-scanned once per channel | Minor at this size | `frozenset`, `Counter`, one pass with per-channel totals |

See `docs/CHANGES.md` for the benchmark table.

## E. Known limitations (unchanged behaviour, documented rather than fixed)

- Sentiment is keyword based: "not good" still counts as positive. Handling negation would change results, so it was left for the team to decide.
- Duplicate feedback IDs across files are not removed, matching the original behaviour.
