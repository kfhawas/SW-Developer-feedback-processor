"""File-reading edge cases, the end-to-end pipeline and the CLI."""

import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from feedback_processor import OUTPUT_COLUMNS, InputFileError, process_files, read_numbered_rows, read_rows
from feedback_processor.cli import main

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
HEADER = "id,date,customer,channel,rating,comment\n"


def write(tmp_path, name, text, encoding="utf-8"):
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return path


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


# ---------- reading files ----------
def test_bom_and_messy_headers(tmp_path):
    path = write(
        tmp_path, "x.csv", "ID , Date,Customer,Channel,Rating ,Comment\n1,2026-09-01,A,Web,5,hi\n", "utf-8-sig"
    )
    rows = list(read_rows(path))
    assert rows[0]["id"] == "1" and rows[0]["rating"] == "5"


def test_quoted_commas_and_newlines_in_comments(tmp_path):
    text = HEADER + '1,2026-09-01,"Tan, Alice",web,4,"Good, but slow"\n2,2026-09-01,B,web,3,"line one\nline two"\n'
    rows = list(read_rows(write(tmp_path, "q.csv", text)))
    assert rows[0]["customer"] == "Tan, Alice"
    assert rows[0]["comment"] == "Good, but slow"
    assert rows[1]["comment"] == "line one\nline two"


def test_semicolon_and_windows_1252(tmp_path):
    text = "id;date;customer;channel;rating;comment\nE1;15/09/2026;Zoë Müller;email;4;Très bon\n"
    rows = list(read_rows(write(tmp_path, "eu.csv", text, "cp1252")))
    assert rows[0]["customer"] == "Zoë Müller"


@pytest.mark.parametrize("sep", ["\t", "|"])
def test_other_delimiters(tmp_path, sep):
    text = sep.join(["id", "date", "customer", "channel", "rating", "comment"]) + "\n"
    text += sep.join(["1", "2026-09-01", "A", "web", "5", "great"]) + "\n"
    assert next(read_rows(write(tmp_path, "d.csv", text)))["rating"] == "5"


def test_header_aliases(tmp_path):
    rows = list(read_rows(write(tmp_path, "a.csv", "Feedback ID,Score,Feedback,Source\n7,4,nice,app\n")))
    assert rows == [{"id": "7", "rating": "4", "comment": "nice", "channel": "app"}]


def test_blank_lines_skipped_and_short_rows_padded(tmp_path):
    rows = list(read_rows(write(tmp_path, "b.csv", HEADER + "\n1,2026-09-01,A\n\n,,,,,\n")))
    assert len(rows) == 1 and rows[0]["comment"] == ""


def test_missing_required_column_gives_clear_error(tmp_path):
    with pytest.raises(InputFileError, match="missing required column.*rating"):
        list(read_rows(write(tmp_path, "m.csv", "id,comment\n1,hi\n")))


def test_zero_byte_and_missing_files(tmp_path):
    with pytest.raises(InputFileError, match="empty"):
        list(read_rows(write(tmp_path, "z.csv", "")))
    with pytest.raises(InputFileError, match="not found"):
        list(read_rows(tmp_path / "nope.csv"))


# ---------- pipeline on the sample files ----------
@pytest.mark.parametrize(
    "sample, rows, unrated",
    [
        ("feedback_clean.csv", 8, 0),
        ("feedback_excel_export.csv", 4, 0),
        ("feedback_semicolon_eu.csv", 3, 0),
        ("feedback_messy_values.csv", 7, 3),
        ("feedback_empty.csv", 0, 0),
    ],
)
def test_every_readable_sample_processes(tmp_path, sample, rows, unrated):
    result = process_files([SAMPLES / sample], tmp_path / "out")
    summary = json.loads(result.output_json.read_text(encoding="utf-8"))
    assert summary["total"] == rows
    assert summary["unrated_count"] == unrated
    assert len(read_csv(result.output_csv)) == rows


def test_clean_sample_expected_values(tmp_path):
    result = process_files([SAMPLES / "feedback_clean.csv"], tmp_path)
    s = json.loads(result.output_json.read_text())
    assert s["total"] == 8  # original dropped the last row (F008)
    assert s["average_rating"] == 3.25  # 26 / 8
    assert s["channel_averages"] == {"email": 3.33, "web": 3.33, "app": 3.0}
    assert s["follow_up_ids"] == ["F002", "F004", "F006"]
    assert s["five_star_count"] == 2
    assert s["sentiment_counts"] == {"positive": 4, "negative": 3, "neutral": 1}
    assert s["top_keywords"][0] == ["delivery", 2]


def test_output_csv_round_trips_commas(tmp_path):
    result = process_files([SAMPLES / "feedback_excel_export.csv"], tmp_path)
    rows = read_csv(result.output_csv)
    assert list(rows[0].keys()) == OUTPUT_COLUMNS
    assert rows[0]["customer"] == "Tan, Alice"
    assert rows[0]["comment"] == "Good product, but shipping was slow"


def test_messy_values_become_blank_not_crashes(tmp_path):
    rows = {r["id"]: r for r in read_csv(process_files([SAMPLES / "feedback_messy_values.csv"], tmp_path).output_csv)}
    assert rows["M301"]["rating"] == "4" and rows["M301"]["channel"] == "web"  # '4.0' and '  WEB '
    assert rows["M302"]["rating"] == "" and rows["M303"]["rating"] == "" and rows["M305"]["rating"] == ""
    assert rows["M304"]["date"] == "2026-09-11"  # 2026/09/11 accepted
    assert rows["M307"]["date"] == ""  # 'not a date'


def test_multiple_files_are_combined_and_bad_ones_skipped(tmp_path):
    files = [SAMPLES / f for f in ("feedback_clean.csv", "feedback_missing_column.csv", "feedback_semicolon_eu.csv")]
    result = process_files(files, tmp_path)
    s = json.loads(result.output_json.read_text())
    assert s["total"] == 11
    assert len(s["files_processed"]) == 2
    assert "missing required column" in next(iter(s["files_failed"].values()))


def test_output_folder_is_created(tmp_path):
    out = tmp_path / "does" / "not" / "exist"
    process_files([SAMPLES / "feedback_clean.csv"], out)
    assert (out / "summary.json").exists()  # original crashed: FileNotFoundError


def test_large_file_streams_quickly(tmp_path):
    """50,000 rows: completes fast and memory stays small (rows are not all kept)."""
    import time
    import tracemalloc

    lines = [HEADER.strip()]
    for i in range(50_000):
        lines.append(
            f"L{i},2026-09-01,Cust {i},{('web', 'app', 'email')[i % 3]},{i % 5 + 1},great fast delivery {i % 50}"
        )
    path = write(tmp_path, "big.csv", "\n".join(lines) + "\n")
    tracemalloc.start()
    start = time.perf_counter()
    result = process_files([path], tmp_path / "out")
    elapsed = time.perf_counter() - start
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert result.stats.total == 50_000
    assert elapsed < 15
    assert peak < 20 * 1024 * 1024  # well under the size of all rows in memory


# ---------- CLI ----------
def test_cli_exit_codes(tmp_path, capsys):
    ok = main([str(SAMPLES / "feedback_clean.csv"), "-o", str(tmp_path / "a")])
    partial = main(
        [str(SAMPLES / "feedback_clean.csv"), str(SAMPLES / "feedback_zero_bytes.csv"), "-o", str(tmp_path / "b")]
    )
    nothing = main([str(SAMPLES / "feedback_missing_column.csv"), "-o", str(tmp_path / "c"), "-q"])
    assert (ok, partial, nothing) == (0, 1, 2)


def test_cli_top_option(tmp_path):
    main([str(SAMPLES / "feedback_clean.csv"), "-o", str(tmp_path), "--top", "3", "-q"])
    assert len(json.loads((tmp_path / "summary.json").read_text())["top_keywords"]) == 3


def test_entry_point_script_runs_like_before(tmp_path):
    """`python process_feedback.py file.csv` still works and writes to ./output."""
    run = subprocess.run(
        [sys.executable, str(ROOT / "process_feedback.py"), str(SAMPLES / "feedback_clean.csv")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    assert run.returncode == 0, run.stderr
    assert (tmp_path / "output" / "processed_feedback.csv").exists()


# ---------- nothing removed compared with the original script ----------
def test_no_functionality_removed_vs_original(tmp_path):
    """Run the teammate's original script on the one file it can read and compare outputs."""
    orig_dir = tmp_path / "orig"
    (orig_dir / "output").mkdir(parents=True)
    shutil.copy(SAMPLES / "feedback_clean.csv", orig_dir)
    run = subprocess.run(
        [sys.executable, "-W", "ignore", str(ROOT / "original" / "process_feedback.py"), "feedback_clean.csv"],
        cwd=orig_dir,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    old_summary = json.loads((orig_dir / "output" / "summary.json").read_text())
    old_rows = read_csv(orig_dir / "output" / "processed_feedback.csv")

    new = process_files([SAMPLES / "feedback_clean.csv"], tmp_path / "new")
    new_summary = json.loads(new.output_json.read_text())
    new_rows = read_csv(new.output_csv)

    assert set(old_summary) <= set(new_summary), "every original summary field is still produced"
    assert list(old_rows[0]) == list(new_rows[0]), "processed CSV has the same columns in the same order"
    same = ("id", "date", "customer", "channel", "rating", "comment")
    for old, fresh in zip(old_rows, new_rows):  # original only has 7 rows (off-by-one bug)
        assert {k: old[k] for k in same} == {k: fresh[k] for k in same}
    assert old_summary["five_star_count"] == new_summary["five_star_count"]


def test_line_numbers_match_the_file(tmp_path):
    """Warnings must point at the real line, even after blank lines or multi-line comments."""
    text = HEADER + '1,2026-09-01,A,web,5,"two\nlines"\n\n2,2026-09-01,B,web,9,bad rating\n'
    numbered = list(read_numbered_rows(write(tmp_path, "n.csv", text)))
    assert [n for n, _ in numbered] == [2, 5]


def test_warning_points_at_correct_line(tmp_path, caplog):
    process_files([SAMPLES / "feedback_messy_values.csv"], tmp_path)
    assert "feedback_messy_values.csv line 7: rating '7'" in caplog.text  # after the blank line 6
