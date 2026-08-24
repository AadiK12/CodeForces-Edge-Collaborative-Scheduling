#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import pathlib


def load(path: pathlib.Path) -> dict[str, dict]:
    return {row["scenario"]: row for row in json.loads(path.read_text())}


def percent_change(current: float, baseline: float) -> str:
    if baseline == 0:
        return "   n/a"
    return f"{100.0 * (current / baseline - 1.0):+6.1f}%"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare scheduler scenario results")
    parser.add_argument("baseline", type=pathlib.Path)
    parser.add_argument("current", type=pathlib.Path)
    args = parser.parse_args()

    baseline = load(args.baseline)
    current = load(args.current)
    missing = sorted(set(baseline) - set(current))
    if missing:
        parser.error(f"current result is missing scenarios: {', '.join(missing)}")

    print(
        f"{'scenario':<30} {'score Δ':>10} {'throughput':>11} "
        f"{'TDR':>8} {'TPOT':>8} {'elapsed':>9}"
    )
    for name in baseline:
        old = baseline[name]
        new = current[name]
        if not new.get("legal", True):
            print(f"{name:<30} {'ILLEGAL':>10}")
            continue
        print(
            f"{name:<30} "
            f"{new['score'] - old['score']:+10.3f} "
            f"{percent_change(new['throughput'], old['throughput']):>11} "
            f"{percent_change(new['tdr'], old['tdr']):>8} "
            f"{percent_change(new['tpot'], old['tpot']):>8} "
            f"{percent_change(new['elapsed'], old['elapsed']):>9}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
