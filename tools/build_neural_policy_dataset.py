#!/usr/bin/env python3
"""Collect first-disagreement public states and whole-run policy counterfactuals."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scheduler_versions" / "layered_scheduler.cpp"
JUDGE = ROOT / "tools" / "local_judge.py"
WORK = ROOT / "build" / "neural-policy"
FEATURE_NAMES = (
    "log_group_size",
    "cloud_fanout_fraction",
    "largest_cloud_fraction",
    "smallest_to_largest_cloud_cohort",
    "schedule_to_merged_post",
    "post_savings_to_merged_post",
    "group_transfer_to_savings",
    "ready_dispersion_to_savings",
    "dpre_group_efficiency",
    "dproc_group_efficiency",
    "dpost_group_efficiency",
    "token_transfer_to_schedule",
    "pending_up_per_member",
    "pending_down_per_member",
    "log_observed_tokens",
    "observed_token_cv",
    "oldest_ready_age_to_tpot",
    "throughput_target_span",
)
ACTIONS = (
    {"name": "wide_015", "ratio": 0.15, "max_group": 256},
    {"name": "wide_025", "ratio": 0.25, "max_group": 256},
    {"name": "wide_040", "ratio": 0.40, "max_group": 256},
    {"name": "wide_050", "ratio": 0.50, "max_group": 256},
    {"name": "wide_075", "ratio": 0.75, "max_group": 256},
    {"name": "wide_100", "ratio": 1.00, "max_group": 256},
    {"name": "wide_200", "ratio": 2.00, "max_group": 256},
)


def run(command: list[str], timeout: float = 900.0) -> subprocess.CompletedProcess[str]:
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


def compile_solver(name: str, ratio: float, max_group: int, trace: bool = False) -> pathlib.Path:
    binary = WORK / "bin" / name
    binary.parent.mkdir(parents=True, exist_ok=True)
    cxx = os.environ.get("CXX", "g++")
    flags = shlex.split(
        os.environ.get("CXXFLAGS", "-std=c++17 -O2 -pipe -Wall -Wextra -Wpedantic")
    )
    defines = [
        "-DOPT_LEVEL=20",
        "-DDYNAMIC_COHERENT_DPOST=1",
        f"-DDYNAMIC_COHERENT_DISPERSION_RATIO={ratio:.12g}",
        f"-DDYNAMIC_COHERENT_MAX_GROUP={max_group}",
    ]
    if trace:
        defines.append("-DLEARNED_POLICY_TRACE=1")
    run([cxx, *flags, *defines, str(SOURCE), "-o", str(binary)])
    return binary


def evaluate(name: str, solver: pathlib.Path, scenarios: pathlib.Path, split: str) -> list[dict[str, Any]]:
    output = WORK / "results" / split / f"{name}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            sys.executable,
            str(JUDGE),
            "--solver",
            str(solver),
            "--scenarios",
            str(scenarios),
            "--json-out",
            str(output),
        ]
    )
    rows = json.loads(output.read_text())
    if not rows or not all(row.get("legal") for row in rows):
        raise RuntimeError(f"{name} produced an illegal run on {split}")
    return rows


def parse_features(stderr: str) -> list[float] | None:
    lines = [line for line in stderr.splitlines() if line.startswith("LP1 ")]
    if not lines:
        return None
    if len(lines) != 1:
        raise RuntimeError("probe emitted more than one learned-policy state")
    values = [float(value) for value in lines[0].split()[1:]]
    if len(values) != len(FEATURE_NAMES):
        raise RuntimeError(f"expected {len(FEATURE_NAMES)} features, received {len(values)}")
    return values


def scenario_index(directory: pathlib.Path) -> dict[str, pathlib.Path]:
    result: dict[str, pathlib.Path] = {}
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text())
        result[str(data["name"])] = path
    return result


def prepare_eligible(split: str, source_dir: pathlib.Path, names: set[str]) -> pathlib.Path:
    target = WORK / "eligible" / split
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    paths = scenario_index(source_dir)
    for index, name in enumerate(sorted(names)):
        shutil.copy2(paths[name], target / f"{index:05d}.json")
    return target


def collect_split(split: str, scenario_dir: pathlib.Path, solvers: dict[str, pathlib.Path]) -> dict[str, Any]:
    probe_rows = evaluate("probe", solvers["probe"], scenario_dir, split)
    features = {
        row["scenario"]: parse_features(str(row.get("solver_stderr", "")))
        for row in probe_rows
    }
    eligible_names = {name for name, values in features.items() if values is not None}
    eligible_dir = prepare_eligible(split, scenario_dir, eligible_names)
    if not eligible_names:
        return {"split": split, "rows": [], "probe_scenarios": len(probe_rows)}

    action_rows: dict[str, list[dict[str, Any]]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(ACTIONS))) as executor:
        futures = {
            executor.submit(evaluate, action["name"], solvers[action["name"]], eligible_dir, split): action["name"]
            for action in ACTIONS
        }
        for future in concurrent.futures.as_completed(futures):
            action_rows[futures[future]] = future.result()

    probe_by_name = {row["scenario"]: row for row in probe_rows}
    action_by_name = {
        action: {row["scenario"]: row for row in rows}
        for action, rows in action_rows.items()
    }
    paths = scenario_index(scenario_dir)
    rows = []
    for name in sorted(eligible_names):
        scenario_data = json.loads(paths[name].read_text())
        baseline_score = float(probe_by_name[name]["score"])
        scores = {action["name"]: float(action_by_name[action["name"]][name]["score"]) for action in ACTIONS}
        rows.append(
            {
                "scenario": name,
                "public_group": scenario_data["policy_metadata"]["public_group"],
                "world": scenario_data["policy_metadata"]["world"],
                "features": features[name],
                "baseline_score": baseline_score,
                "scores": scores,
                "deltas": {key: value - baseline_score for key, value in scores.items()},
            }
        )
    return {"split": split, "rows": rows, "probe_scenarios": len(probe_rows)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario-root",
        type=pathlib.Path,
        default=WORK / "scenarios",
    )
    parser.add_argument(
        "--splits",
        nargs="+",
        choices=("train", "validation", "holdout"),
        default=("train", "validation"),
    )
    parser.add_argument(
        "--json-out",
        type=pathlib.Path,
        default=WORK / "dataset-development.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scenario_root = args.scenario_root.resolve()
    solvers = {
        "probe": compile_solver("probe", ratio=0.15, max_group=8, trace=True),
    }
    for action in ACTIONS:
        solvers[action["name"]] = compile_solver(
            action["name"], float(action["ratio"]), int(action["max_group"])
        )
    splits = [collect_split(split, scenario_root / split, solvers) for split in args.splits]
    output = {
        "schema_version": 1,
        "feature_names": FEATURE_NAMES,
        "fallback": {"ratio": 0.15, "max_group": 8},
        "actions": ACTIONS,
        "splits": {entry["split"]: entry for entry in splits},
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(output, indent=2) + "\n")
    for entry in splits:
        changed = sum(
            any(abs(delta) > 1e-8 for delta in row["deltas"].values())
            for row in entry["rows"]
        )
        print(
            f"{entry['split']}: probed={entry['probe_scenarios']} "
            f"eligible={len(entry['rows'])} changed={changed}"
        )
    print(f"Wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
