#!/usr/bin/env python3
"""Fit compact grouping-policy coefficients with deterministic black-box policy search.

Model selection uses only generated training scenarios. The selected policies are then measured
once on a separate holdout split and on the checked-in mechanism suite. The output is an audit
artifact; it does not rewrite the C++ source automatically.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import random
import shlex
import statistics
import subprocess
import sys
from typing import Any

from generate_grouping_scenarios import generate


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scheduler_versions" / "layered_scheduler.cpp"
JUDGE = ROOT / "tools" / "local_judge.py"
WORK_DIR = ROOT / "build" / "learned-grouping"

BASE_WEIGHT_NAMES = (
    "GROUP_RATE_WEIGHT",
    "GROUP_EFFICIENCY_WEIGHT",
    "GROUP_LATENCY_WEIGHT",
    "GROUP_URGENCY_WEIGHT",
    "GROUP_COMPLETION_WEIGHT",
    "GROUP_FANOUT_PENALTY",
    "GROUP_EXCLUDED_PENALTY",
    "GROUP_DISPERSION_PENALTY",
    "GROUP_DECISION_MARGIN",
)
INTERACTION_WEIGHT_NAMES = (
    "GROUP_INTERACTION_EFFICIENCY",
    "GROUP_INTERACTION_URGENCY",
    "GROUP_INTERACTION_CONGESTION",
)

DEFAULT_WEIGHTS = {
    "GROUP_RATE_WEIGHT": 1.35,
    "GROUP_EFFICIENCY_WEIGHT": 0.55,
    "GROUP_LATENCY_WEIGHT": 1.10,
    "GROUP_URGENCY_WEIGHT": 0.45,
    "GROUP_COMPLETION_WEIGHT": 0.12,
    "GROUP_FANOUT_PENALTY": 0.22,
    "GROUP_EXCLUDED_PENALTY": 0.32,
    "GROUP_DISPERSION_PENALTY": 0.18,
    "GROUP_DECISION_MARGIN": 0.02,
    "GROUP_INTERACTION_EFFICIENCY": 0.30,
    "GROUP_INTERACTION_URGENCY": 0.25,
    "GROUP_INTERACTION_CONGESTION": 0.35,
}


def run(command: list[str], timeout: float = 180.0) -> subprocess.CompletedProcess[str]:
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


def compile_policy(
    name: str,
    level: int,
    weights: dict[str, float],
    cxx: str,
    cxxflags: list[str],
) -> pathlib.Path:
    executable = WORK_DIR / "candidates" / name
    executable.parent.mkdir(parents=True, exist_ok=True)
    defines = [f"-DOPT_LEVEL={level}"]
    defines.extend(f"-D{key}={value:.12g}" for key, value in sorted(weights.items()))
    run([cxx, *cxxflags, *defines, str(SOURCE), "-o", str(executable)])
    return executable


def evaluate(
    name: str,
    executable: pathlib.Path,
    scenario_path: pathlib.Path,
) -> list[dict[str, Any]]:
    output_path = WORK_DIR / "results" / f"{name}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            sys.executable,
            str(JUDGE),
            "--solver",
            str(executable),
            "--scenarios",
            str(scenario_path),
            "--json-out",
            str(output_path),
        ],
        timeout=300.0,
    )
    rows = json.loads(output_path.read_text())
    if not rows or not all(row.get("legal") for row in rows):
        raise RuntimeError(f"{name} produced an illegal local run")
    return rows


def summarize(
    rows: list[dict[str, Any]],
    reference: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    deltas = [row["score"] - reference[row["scenario"]]["score"] for row in rows]
    losses = [-delta for delta in deltas if delta < 0]
    mean_delta = statistics.mean(deltas)
    mean_loss = statistics.mean(losses) if losses else 0.0
    worst_loss = max(losses, default=0.0)
    robust_objective = mean_delta - 0.35 * mean_loss - 0.05 * worst_loss
    return {
        "mean_score": statistics.mean(row["score"] for row in rows),
        "mean_delta_vs_v15": mean_delta,
        "robust_objective": robust_objective,
        "wins": sum(delta > 1e-8 for delta in deltas),
        "ties": sum(abs(delta) <= 1e-8 for delta in deltas),
        "losses": sum(delta < -1e-8 for delta in deltas),
        "worst_delta": min(deltas),
        "scheduler_cpu_seconds": sum(row["scheduler_cpu_seconds"] for row in rows),
    }


def log_scaled(rng: random.Random, value: float, spread: float = 1.6) -> float:
    return value * math.exp(rng.uniform(-math.log(spread), math.log(spread)))


def base_candidates(count: int, seed: int) -> list[dict[str, float]]:
    rng = random.Random(seed)
    candidates = [dict(DEFAULT_WEIGHTS)]
    conservative = dict(DEFAULT_WEIGHTS)
    conservative.update(
        {
            "GROUP_RATE_WEIGHT": 0.9,
            "GROUP_FANOUT_PENALTY": 1.2,
            "GROUP_EXCLUDED_PENALTY": 1.0,
            "GROUP_DISPERSION_PENALTY": 0.8,
        }
    )
    candidates.append(conservative)
    while len(candidates) < count:
        weights = dict(DEFAULT_WEIGHTS)
        for name in BASE_WEIGHT_NAMES:
            weights[name] = log_scaled(rng, DEFAULT_WEIGHTS[name], spread=3.0)
        candidates.append(weights)
    return candidates


def interaction_candidates(
    count: int,
    seed: int,
    learned_base: dict[str, float],
) -> list[dict[str, float]]:
    rng = random.Random(seed)
    candidates: list[dict[str, float]] = []
    zero_interactions = dict(learned_base)
    zero_interactions.update({name: 0.0 for name in INTERACTION_WEIGHT_NAMES})
    candidates.append(zero_interactions)
    while len(candidates) < count:
        weights = dict(learned_base)
        for name in BASE_WEIGHT_NAMES:
            weights[name] = log_scaled(rng, learned_base[name], spread=1.35)
        for name in INTERACTION_WEIGHT_NAMES:
            weights[name] = rng.uniform(0.0, 1.5)
        candidates.append(weights)
    return candidates


def select_on_training(
    level: int,
    candidates: list[dict[str, float]],
    train_dir: pathlib.Path,
    train_reference: dict[str, dict[str, Any]],
    cxx: str,
    cxxflags: list[str],
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    summaries = []
    for index, weights in enumerate(candidates):
        name = f"v{level}-candidate-{index:03d}"
        executable = compile_policy(name, level, weights, cxx, cxxflags)
        rows = evaluate(f"{name}-train", executable, train_dir)
        metrics = summarize(rows, train_reference)
        summaries.append({"name": name, "weights": weights, **metrics})
        print(
            f"{name}: objective={metrics['robust_objective']:+.3f} "
            f"mean_delta={metrics['mean_delta_vs_v15']:+.3f} "
            f"W/T/L={metrics['wins']}/{metrics['ties']}/{metrics['losses']}"
        )
    summaries.sort(
        key=lambda row: (row["robust_objective"], row["mean_delta_vs_v15"]),
        reverse=True,
    )
    return dict(summaries[0]["weights"]), summaries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-count", type=int, default=18)
    parser.add_argument("--holdout-count", type=int, default=12)
    parser.add_argument("--v17-candidates", type=int, default=24)
    parser.add_argument("--v18-candidates", type=int, default=24)
    parser.add_argument(
        "--json-out",
        type=pathlib.Path,
        default=ROOT / "build" / "learned-grouping" / "tuning-report.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if min(
        args.train_count,
        args.holdout_count,
        args.v17_candidates,
        args.v18_candidates,
    ) < 1:
        raise SystemExit("scenario and candidate counts must be positive")

    scenario_root = WORK_DIR / "scenarios"
    generate(scenario_root, args.train_count, args.holdout_count)
    train_dir = scenario_root / "train"
    holdout_dir = scenario_root / "holdout"
    cxx = os.environ.get("CXX", "g++")
    cxxflags = shlex.split(
        os.environ.get("CXXFLAGS", "-std=c++17 -O2 -pipe -Wall -Wextra -Wpedantic")
    )

    v15_executable = compile_policy("v15-reference", 15, {}, cxx, cxxflags)
    v15_train_rows = evaluate("v15-reference-train", v15_executable, train_dir)
    v15_holdout_rows = evaluate("v15-reference-holdout", v15_executable, holdout_dir)
    train_reference = {row["scenario"]: row for row in v15_train_rows}
    holdout_reference = {row["scenario"]: row for row in v15_holdout_rows}

    v17_weights, v17_candidates = select_on_training(
        17,
        base_candidates(args.v17_candidates, seed=225117),
        train_dir,
        train_reference,
        cxx,
        cxxflags,
    )
    v18_weights, v18_candidates = select_on_training(
        18,
        interaction_candidates(args.v18_candidates, seed=225118, learned_base=v17_weights),
        train_dir,
        train_reference,
        cxx,
        cxxflags,
    )

    selected_report: dict[str, Any] = {}
    for level, weights in ((17, v17_weights), (18, v18_weights)):
        name = f"v{level}-selected"
        executable = compile_policy(name, level, weights, cxx, cxxflags)
        train_rows = evaluate(f"{name}-train-final", executable, train_dir)
        holdout_rows = evaluate(f"{name}-holdout", executable, holdout_dir)
        suite_rows = evaluate(f"{name}-suite", executable, ROOT / "scenarios")
        selected_report[f"v{level}"] = {
            "weights": weights,
            "train": summarize(train_rows, train_reference),
            "holdout": summarize(holdout_rows, holdout_reference),
            "suite": {
                "mean_score": statistics.mean(row["score"] for row in suite_rows),
                "legal_runs": sum(bool(row["legal"]) for row in suite_rows),
                "scenario_count": len(suite_rows),
                "scheduler_cpu_seconds": sum(
                    row["scheduler_cpu_seconds"] for row in suite_rows
                ),
            },
        }

    report = {
        "schema_version": 1,
        "selection_rule": (
            "maximize train mean score delta minus 0.35 mean regression and 0.05 worst "
            "regression; holdout is evaluated only after selection"
        ),
        "generator": {
            "script": "tools/generate_grouping_scenarios.py",
            "train_count": args.train_count,
            "holdout_count": args.holdout_count,
            "regimes": [
                "balanced",
                "edge_amortized",
                "cloud_amortized",
                "slow_link",
                "post_hostile",
                "latency_heavy",
            ],
        },
        "v15_reference": {
            "train_mean_score": statistics.mean(row["score"] for row in v15_train_rows),
            "holdout_mean_score": statistics.mean(row["score"] for row in v15_holdout_rows),
        },
        "selected": selected_report,
        "top_training_candidates": {
            "v17": v17_candidates[:10],
            "v18": v18_candidates[:10],
        },
        "caveat": (
            "Generated workloads test policy mechanics and distribution shift; they do not "
            "reveal or estimate the official hidden workload distribution."
        ),
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote tuning report to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
