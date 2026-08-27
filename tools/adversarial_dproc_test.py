#!/usr/bin/env python3
"""Search D PROC-to-D POST disagreements and audit a separately seeded split."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import random
import shlex
import shutil
import statistics
import subprocess
import sys
from typing import Any

from generate_grouping_scenarios import BATCH_SIZES, scenario as grouping_scenario


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scheduler_versions" / "layered_scheduler.cpp"
JUDGE = ROOT / "tools" / "local_judge.py"
WORK_DIR = ROOT / "build" / "adversarial-dproc"
MODES = (
    "finite_remainder",
    "smooth_amortized",
    "proc_cliff",
    "post_cliff",
    "link_queue",
    "latency_tension",
    "mixed_waves",
    "schedule_heavy",
)


def run(command: list[str], timeout: float = 300.0) -> subprocess.CompletedProcess[str]:
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
    return completed


def stage_curve(rng: random.Random, mode: str, stage: str) -> list[float]:
    base = math.exp(rng.uniform(math.log(0.15), math.log(12.0)))
    exponent = rng.uniform(0.25, 0.8)
    knee = rng.choice([2, 4, 8, 16])
    values: list[float] = []
    for size in BATCH_SIZES:
        scale = 0.55 + 0.45 * size**exponent
        if stage == "proc" and mode == "finite_remainder":
            scale = 0.7 + 0.22 * size**0.55
            if size > knee:
                scale += rng.uniform(0.05, 0.4) * (size - knee) / knee
        elif stage == "proc" and mode == "proc_cliff" and size >= knee:
            scale *= rng.uniform(2.0, 8.0)
        elif stage == "post" and mode == "post_cliff" and size >= knee:
            scale *= rng.uniform(3.0, 12.0)
        elif mode == "smooth_amortized":
            scale = 0.8 + 0.2 * size ** rng.uniform(0.25, 0.55)
        elif mode == "latency_tension":
            scale = 0.9 + 0.1 * size ** rng.uniform(0.3, 0.65)
        values.append(round(max(0.001, base * scale), 9))
    return values


def make_scenario(seed: int, split: str, index: int) -> dict[str, Any]:
    rng = random.Random(seed)
    data = grouping_scenario(seed, split, index)
    mode = MODES[index % len(MODES)]
    data["name"] = f"dproc_{split}_{index:03d}_{mode}"
    data["description"] = (
        f"Deterministic D PROC adversarial {split} case; mode={mode}, seed={seed}."
    )

    system = data["system"]
    system["K"] = rng.choice([1, 1, 2, 3])
    system["S"] = round(
        rng.uniform(4.0, 15.0) if mode == "schedule_heavy" else rng.uniform(0.1, 5.0),
        9,
    )
    if mode == "link_queue":
        system["latency_in_ms"] = round(rng.uniform(5.0, 45.0), 9)
        system["bandwidth_gbps"] = round(
            math.exp(rng.uniform(math.log(0.01), math.log(0.25))), 9
        )
        system["bytes_per_token"] = rng.randint(50_000, 800_000)
    else:
        system["latency_in_ms"] = round(rng.uniform(0.001, 1.0), 9)
        system["bandwidth_gbps"] = round(rng.uniform(5.0, 100.0), 9)
        system["bytes_per_token"] = rng.choice([64, 128, 256, 512, 1024, 2048])

    proc_values = stage_curve(rng, mode, "proc")
    post_values = stage_curve(rng, mode, "post")
    for row_index, row in enumerate(data["task_times"]):
        row["decode_proc"] = proc_values[row_index]
        row["decode_post"] = post_values[row_index]
        row["decode_pre"] = round(max(0.001, float(row["decode_pre"]) * 0.06), 9)
        row["prefill_pre"] = round(max(0.001, float(row["prefill_pre"]) * 0.06), 9)
        row["prefill_proc"] = round(max(0.001, float(row["prefill_proc"]) * 0.05), 9)
        row["prefill_post"] = round(max(0.001, float(row["prefill_post"]) * 0.06), 9)

    requests = data["requests"]
    if mode in {"mixed_waves", "latency_tension", "link_queue"}:
        wave = rng.choice([2, 3, 4, 8])
        gap = rng.uniform(0.02, 8.0)
        for request_id, request in enumerate(requests):
            request["arrival"] = round(gap * (request_id // wave), 9)
    else:
        for request in requests:
            request["arrival"] = 0.0
    for request_id, request in enumerate(requests):
        request["input_length"] = rng.choice([1, 2, 4, 8, 16])
        request["output_length"] = (
            rng.choice([1, 2, 32, 48, 64])
            if request_id % 5 == 0
            else rng.choice([2, 4, 8, 12, 16, 24])
        )

    request_count = len(requests)
    eligible = [size for size in BATCH_SIZES if size <= request_count]
    schedule_cost = float(system["S"])
    proc_rate = max(
        size / (schedule_cost + proc_values[BATCH_SIZES.index(size)])
        for size in eligible
    ) * int(system["K"])
    post_rate = max(
        size / (schedule_cost + post_values[BATCH_SIZES.index(size)])
        for size in eligible
    )
    estimated_rate = max(1e-10, min(proc_rate, post_rate))
    singleton_path = (
        2.0 * schedule_cost + proc_values[0] + post_values[0]
        + 2.0 * float(system["latency_in_ms"])
    )
    throughput_weight = (
        rng.choice([0.0, 0.1, 0.25])
        if mode == "latency_tension"
        else rng.choice([0.25, 0.5, 0.75, 0.95, 1.0])
    )
    scoring = data["scoring"]
    scoring["SLO1"] = round(max(float(scoring["SLO1"]), 10_000.0), 9)
    scoring["SLO2"] = round(max(0.001, singleton_path * rng.uniform(0.8, 4.0)), 9)
    scoring["tp_base"] = round(0.05 * estimated_rate, 12)
    scoring["tp_UB"] = round(max(2e-10, 0.9 * estimated_rate), 12)
    scoring["dist_base"] = round(rng.uniform(0.5, 4.0), 9)
    scoring["w_tp"] = throughput_weight
    scoring["w_c"] = round(1.0 - throughput_weight, 9)
    return data


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_pool(
    search_count: int,
    holdout_count: int,
    search_seed_base: int,
    holdout_seed_base: int,
) -> dict[str, Any]:
    scenario_root = WORK_DIR / "scenarios"
    resolved = scenario_root.resolve()
    build_root = (ROOT / "build").resolve()
    if build_root not in resolved.parents:
        raise ValueError(f"refusing to replace generated data outside {build_root}")
    if scenario_root.exists():
        shutil.rmtree(scenario_root)
    manifest: dict[str, Any] = {"schema_version": 1, "splits": {}}
    for split, count, seed_base in (
        ("search", search_count, search_seed_base),
        ("holdout", holdout_count, holdout_seed_base),
    ):
        split_dir = scenario_root / split
        split_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for index in range(count):
            seed = seed_base + 1_009 * index
            path = split_dir / f"{index:03d}_{MODES[index % len(MODES)]}.json"
            path.write_text(json.dumps(make_scenario(seed, split, index), indent=2) + "\n")
            rows.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path)})
        manifest["splits"][split] = rows
    manifest_path = WORK_DIR / "scenario-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def verify_pool() -> dict[str, Any]:
    manifest_path = WORK_DIR / "scenario-manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("scenario pool does not exist; generate the search split first")
    manifest = json.loads(manifest_path.read_text())
    for rows in manifest["splits"].values():
        for row in rows:
            path = ROOT / row["path"]
            if not path.is_file() or sha256(path) != row["sha256"]:
                raise RuntimeError(f"sealed scenario changed: {path}")
    return manifest


def compile_level(level: int, cxx: str, cxxflags: list[str]) -> pathlib.Path:
    executable = WORK_DIR / "bin" / f"scheduler-v{level}"
    executable.parent.mkdir(parents=True, exist_ok=True)
    run([cxx, *cxxflags, f"-DOPT_LEVEL={level}", str(SOURCE), "-o", str(executable)])
    return executable


def evaluate(executable: pathlib.Path, split: str, label: str) -> list[dict[str, Any]]:
    output = WORK_DIR / "results" / f"{label}-{split}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            sys.executable,
            str(JUDGE),
            "--solver",
            str(executable),
            "--scenarios",
            str(WORK_DIR / "scenarios" / split),
            "--trace-assignments",
            "--json-out",
            str(output),
        ]
    )
    rows = json.loads(output.read_text())
    if not rows or not all(row.get("legal") for row in rows):
        raise RuntimeError(f"{label} produced an illegal {split} run")
    return rows


def dproc_signature(row: dict[str, Any]) -> list[tuple[float, str, tuple[int, ...]]]:
    signature = []
    for frame in row.get("assignment_trace", []):
        for assignment in frame["assignments"]:
            if assignment["family"] == "D" and assignment["step"] == "PROC":
                signature.append(
                    (
                        round(float(frame["time"]), 9),
                        assignment["server"],
                        tuple(assignment["members"]),
                    )
                )
    return signature


def compare(reference_rows: list[dict[str, Any]], candidate_rows: list[dict[str, Any]]) -> dict[str, Any]:
    reference = {row["scenario"]: row for row in reference_rows}
    comparisons = []
    for candidate in candidate_rows:
        baseline = reference[candidate["scenario"]]
        delta = float(candidate["score"]) - float(baseline["score"])
        comparisons.append(
            {
                "scenario": candidate["scenario"],
                "score_delta": delta,
                "throughput_delta": float(candidate["throughput"]) - float(baseline["throughput"]),
                "tdr_delta": float(candidate["tdr"]) - float(baseline["tdr"]),
                "tpot_delta": float(candidate["tpot"]) - float(baseline["tpot"]),
                "elapsed_delta": float(candidate["elapsed"]) - float(baseline["elapsed"]),
                "dproc_disagreement": dproc_signature(candidate) != dproc_signature(baseline),
            }
        )
    comparisons.sort(key=lambda row: (row["score_delta"], row["scenario"]))
    deltas = [row["score_delta"] for row in comparisons]
    return {
        "scenario_count": len(comparisons),
        "mean_score_delta": statistics.mean(deltas),
        "worst_score_delta": min(deltas),
        "best_score_delta": max(deltas),
        "wins": sum(delta > 1e-8 for delta in deltas),
        "ties": sum(abs(delta) <= 1e-8 for delta in deltas),
        "losses": sum(delta < -1e-8 for delta in deltas),
        "dproc_disagreements": sum(row["dproc_disagreement"] for row in comparisons),
        "worst_cases": comparisons[:10],
        "all_cases": comparisons,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("search", "holdout", "all"), default="all")
    parser.add_argument("--search-count", type=int, default=64)
    parser.add_argument("--holdout-count", type=int, default=32)
    parser.add_argument("--reference-level", type=int, default=19)
    parser.add_argument("--candidate-level", type=int, default=20)
    parser.add_argument("--work-dir", type=pathlib.Path, default=WORK_DIR)
    parser.add_argument("--search-seed-base", type=int, default=225_120_000)
    parser.add_argument("--holdout-seed-base", type=int, default=225_120_999)
    parser.add_argument("--json-out", type=pathlib.Path, default=None)
    parser.add_argument("--regenerate", action="store_true")
    return parser.parse_args()


def main() -> int:
    global WORK_DIR
    args = parse_args()
    WORK_DIR = args.work_dir.resolve()
    if args.json_out is None:
        args.json_out = WORK_DIR / "report.json"
    if args.search_count < 1 or args.holdout_count < 1:
        raise SystemExit("scenario counts must be positive")
    manifest_path = WORK_DIR / "scenario-manifest.json"
    if args.regenerate or not manifest_path.exists():
        manifest = generate_pool(
            args.search_count,
            args.holdout_count,
            args.search_seed_base,
            args.holdout_seed_base,
        )
    else:
        manifest = verify_pool()

    cxx = os.environ.get("CXX", "g++")
    cxxflags = shlex.split(
        os.environ.get("CXXFLAGS", "-std=c++17 -O2 -pipe -Wall -Wextra -Wpedantic")
    )
    reference = compile_level(args.reference_level, cxx, cxxflags)
    candidate = compile_level(args.candidate_level, cxx, cxxflags)
    report: dict[str, Any] = {
        "schema_version": 1,
        "reference_level": args.reference_level,
        "candidate_level": args.candidate_level,
        "scenario_manifest": str(manifest_path.relative_to(ROOT)),
        "split_counts": {split: len(rows) for split, rows in manifest["splits"].items()},
        "caveat": (
            "The search split may guide implementation. The separately seeded holdout split "
            "must be opened only after the candidate is frozen. Neither estimates hidden tests."
        ),
        "splits": {},
    }
    phases = ("search", "holdout") if args.phase == "all" else (args.phase,)
    for split in phases:
        reference_rows = evaluate(reference, split, f"v{args.reference_level}")
        candidate_rows = evaluate(candidate, split, f"v{args.candidate_level}")
        report["splits"][split] = compare(reference_rows, candidate_rows)
        summary = report["splits"][split]
        print(
            f"{split}: mean={summary['mean_score_delta']:+.6f} "
            f"worst={summary['worst_score_delta']:+.6f} "
            f"W/T/L={summary['wins']}/{summary['ties']}/{summary['losses']} "
            f"DPROC disagreements={summary['dproc_disagreements']}"
        )
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
