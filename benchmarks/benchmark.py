"""Compare the original script and the refactored one on a large clean file.

Usage: python benchmarks/benchmark.py [rows ...]    (default: 10,000 20,000 40,000)
Each version runs in its own subprocess; we record wall time and peak memory (max RSS).
"""

import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORDS = [
    "great",
    "good",
    "slow",
    "late",
    "helpful",
    "friendly",
    "broken",
    "delivery",
    "app",
    "service",
    "support",
    "refund",
    "easy",
    "box",
    "price",
    "staff",
]
CHANNELS = ["email", "web", "app", "phone", "chat", "store", "social", "kiosk"]

# Runs a script via runpy and reports its peak memory on stderr.
RUNNER = """
import resource, runpy, sys
sys.argv = sys.argv[1:]
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
except SystemExit:
    pass
print("MAXRSS", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, file=sys.stderr)
"""


def make_file(path: Path, rows: int) -> None:
    rnd = random.Random(1)
    with path.open("w", encoding="utf-8") as handle:
        handle.write("id,date,customer,channel,rating,comment\n")
        for i in range(rows):
            comment = " ".join(rnd.choices(WORDS, k=8))
            channel = rnd.choice(CHANNELS)
            handle.write(f"B{i},2026-09-{i % 28 + 1:02d},Customer {i},{channel},{rnd.randint(1, 5)},{comment}\n")


def run(args: list[str], cwd: Path, timeout: float = 300) -> tuple[float, float]:
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-W", "ignore", "-c", RUNNER, *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(ROOT)},
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return float("inf"), float("nan")
    elapsed = time.perf_counter() - start
    rss_kb = next(int(line.split()[1]) for line in proc.stderr.splitlines() if line.startswith("MAXRSS"))
    return elapsed, rss_kb / 1024


def main() -> None:
    sizes = [int(a) for a in sys.argv[1:]] or [10_000, 20_000, 40_000]
    print(f"{'rows':>9}{'original s':>12}{'refactored s':>14}{'speed-up':>10}{'orig MB':>9}{'new MB':>8}")
    for rows in sizes:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            data = tmp / "big.csv"
            make_file(data, rows)
            (tmp / "output").mkdir()  # the original needs this folder to exist
            old_t, old_m = run([str(ROOT / "original" / "process_feedback.py"), str(data)], tmp)
            new_t, new_m = run([str(ROOT / "process_feedback.py"), str(data), "-q", "-o", str(tmp / "new")], tmp)
        print(f"{rows:>9,}{old_t:>12.2f}{new_t:>14.2f}{old_t / new_t:>9.0f}x{old_m:>9.0f}{new_m:>8.0f}")


if __name__ == "__main__":
    main()
