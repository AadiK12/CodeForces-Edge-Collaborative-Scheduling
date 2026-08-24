#!/usr/bin/env python3

from __future__ import annotations

import difflib
import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
BINARY = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "build/v0-baseline"


def normalized_lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.strip().splitlines()]


def run_case(input_path: pathlib.Path) -> bool:
    expected_path = input_path.with_suffix(".out")
    completed = subprocess.run(
        [str(BINARY)],
        input=input_path.read_text(),
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )

    expected = normalized_lines(expected_path.read_text())
    actual = normalized_lines(completed.stdout)
    if completed.returncode == 0 and actual == expected and not completed.stderr:
        print(f"PASS {input_path.stem}")
        return True

    print(f"FAIL {input_path.stem}")
    if completed.returncode != 0:
        print(f"  exit code: {completed.returncode}")
    if completed.stderr:
        print("  stderr:")
        print(completed.stderr.rstrip())
    if actual != expected:
        diff = difflib.unified_diff(
            expected,
            actual,
            fromfile=str(expected_path),
            tofile="actual stdout",
            lineterm="",
        )
        print("\n".join(diff))
    return False


def main() -> int:
    if not BINARY.is_file():
        print(f"Missing scheduler binary: {BINARY}", file=sys.stderr)
        return 2

    cases = sorted(ROOT.glob("tests/*.in"))
    if not cases:
        print("No transcript tests found", file=sys.stderr)
        return 2

    return 0 if all(run_case(case) for case in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
