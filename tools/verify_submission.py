#!/usr/bin/env python3
"""Verify that a stripped submission exactly matches its full policy source."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile
from typing import Any

from build_submission import MAX_CODEFORCES_CHARACTERS, build


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "main.cpp"
JUDGE = ROOT / "tools" / "local_judge.py"
VOLATILE_RESULT_FIELDS = {
    "scheduler_cpu_seconds",
    "judge_wall_seconds",
    "wall_seconds",
}


def run(command: list[str], timeout: float = 300.0) -> None:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"command failed: {' '.join(command)}\n{detail}")


def normalized(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = json.loads(json.dumps(rows))
    for row in result:
        for field in VOLATILE_RESULT_FIELDS:
            row.pop(field, None)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opt-level", type=int, default=15)
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=[str(ROOT / "scenarios")],
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    generated = build(SOURCE, args.opt_level, minified=True)
    if len(generated) > MAX_CODEFORCES_CHARACTERS:
        raise RuntimeError(
            f"submission has {len(generated)} characters; "
            f"limit is {MAX_CODEFORCES_CHARACTERS}"
        )
    cxx = os.environ.get("CXX", "g++")
    flags = shlex.split(
        os.environ.get("CXXFLAGS", "-std=c++17 -O2 -pipe -Wall -Wextra -Wpedantic")
    )
    build_root = ROOT / "build"
    build_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="submission-check-", dir=build_root) as temporary:
        directory = pathlib.Path(temporary)
        compact_source = directory / "submission.cpp"
        compact_source.write_text(generated)
        full_solver = directory / "full"
        compact_solver = directory / "compact"
        run([cxx, *flags, f"-DOPT_LEVEL={args.opt_level}", str(SOURCE), "-o", str(full_solver)])
        run([cxx, *flags, str(compact_source), "-o", str(compact_solver)])

        outputs = []
        for label, solver in (("full", full_solver), ("compact", compact_solver)):
            output = directory / f"{label}.json"
            run(
                [
                    sys.executable,
                    str(JUDGE),
                    "--solver",
                    str(solver),
                    "--scenarios",
                    *args.scenarios,
                    "--trace-assignments",
                    "--json-out",
                    str(output),
                ]
            )
            outputs.append(json.loads(output.read_text()))
        if normalized(outputs[0]) != normalized(outputs[1]):
            raise RuntimeError("stripped submission changed scheduler results or assignment traces")
        print(
            f"verified level {args.opt_level}: {len(outputs[0])} exact scenario traces, "
            f"{len(generated)} characters, "
            f"{MAX_CODEFORCES_CHARACTERS - len(generated)} remaining"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
