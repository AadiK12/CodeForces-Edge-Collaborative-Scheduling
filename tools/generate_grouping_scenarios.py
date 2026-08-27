#!/usr/bin/env python3
"""Generate deterministic train/holdout workloads for grouping-policy calibration.

The generated files live under build/ by default. They deliberately span several workload
families instead of perturbing one hand-written isolation case. Hidden output lengths are used
only by the local interactor; they are never exposed to the scheduler.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import random
import shutil
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
BATCH_SIZES = [1, 2, 4, 8, 16, 32, 64, 256, 4096]
REGIMES = (
    "balanced",
    "edge_amortized",
    "cloud_amortized",
    "slow_link",
    "post_hostile",
    "latency_heavy",
)


def log_uniform(rng: random.Random, low: float, high: float) -> float:
    return math.exp(rng.uniform(math.log(low), math.log(high)))


def stage_curve(
    rng: random.Random,
    base: float,
    exponent: float,
    fixed_fraction: float,
) -> list[float]:
    values: list[float] = []
    for size in BATCH_SIZES:
        scale = fixed_fraction + (1.0 - fixed_fraction) * size**exponent
        values.append(max(0.001, base * scale))
    return values


def task_table(rng: random.Random, regime: str) -> list[dict[str, float | int]]:
    prefill_pre = stage_curve(rng, log_uniform(rng, 0.15, 2.5), rng.uniform(0.45, 0.9), 0.55)
    prefill_proc = stage_curve(rng, log_uniform(rng, 1.0, 12.0), rng.uniform(0.45, 0.9), 0.25)
    prefill_post = stage_curve(rng, log_uniform(rng, 0.15, 2.0), rng.uniform(0.45, 0.9), 0.55)

    edge_exponent = rng.uniform(0.35, 0.8)
    cloud_exponent = rng.uniform(0.35, 0.85)
    if regime == "edge_amortized":
        edge_exponent = rng.uniform(0.2, 0.45)
    if regime == "cloud_amortized":
        cloud_exponent = rng.uniform(0.2, 0.45)

    decode_pre = stage_curve(rng, log_uniform(rng, 0.2, 5.0), edge_exponent, 0.7)
    decode_proc = stage_curve(rng, log_uniform(rng, 1.0, 20.0), cloud_exponent, 0.35)
    decode_post = stage_curve(rng, log_uniform(rng, 0.2, 5.0), edge_exponent, 0.7)

    if regime == "post_hostile":
        hostile_index = rng.choice([2, 3, 4])
        multiplier = rng.uniform(4.0, 14.0)
        for index in range(hostile_index, min(hostile_index + 2, len(decode_post))):
            decode_post[index] *= multiplier

    columns = {
        "prefill_pre": prefill_pre,
        "prefill_proc": prefill_proc,
        "prefill_post": prefill_post,
        "decode_pre": decode_pre,
        "decode_proc": decode_proc,
        "decode_post": decode_post,
    }
    rows: list[dict[str, float | int]] = []
    for index, size in enumerate(BATCH_SIZES):
        row: dict[str, float | int] = {"batch_size": size}
        for column, values in columns.items():
            row[column] = round(values[index], 9)
        rows.append(row)
    return rows


def interpolate(rows: list[dict[str, Any]], column: str, size: int) -> float:
    points = [(int(row["batch_size"]), float(row[column])) for row in rows]
    if size <= points[0][0]:
        return points[0][1]
    if size >= points[-1][0]:
        return points[-1][1]
    for (left_size, left_value), (right_size, right_value) in zip(points, points[1:]):
        if size == left_size:
            return left_value
        if left_size < size < right_size:
            fraction = (size - left_size) / (right_size - left_size)
            return left_value + fraction * (right_value - left_value)
    raise AssertionError("interpolation fell through")


def scenario(seed: int, split: str, index: int) -> dict[str, Any]:
    rng = random.Random(seed)
    regime = REGIMES[index % len(REGIMES)]
    cloud_count = rng.randint(1, 4)
    request_count = rng.choice([8, 12, 16, 24, 32])
    schedule_cost = rng.uniform(1.0, 10.0)
    latency = log_uniform(rng, 0.02, 35.0)
    bandwidth = log_uniform(rng, 0.03, 100.0)
    bytes_per_token = int(log_uniform(rng, 64.0, 800_000.0))
    layer_count = rng.choice([4, 8, 16, 32, 64])
    if regime == "slow_link":
        latency = rng.uniform(8.0, 45.0)
        bandwidth = log_uniform(rng, 0.01, 0.2)
        bytes_per_token = rng.randint(100_000, 1_000_000)

    rows = task_table(rng, regime)
    arrivals: list[float] = []
    if rng.random() < 0.55:
        arrivals = [0.0] * request_count
    else:
        wave_size = rng.choice([2, 4, 8])
        wave_gap = rng.uniform(0.1, 30.0)
        arrivals = [wave_gap * (request // wave_size) for request in range(request_count)]

    requests = []
    for request_id in range(request_count):
        input_length = rng.choice([1, 2, 4, 8, 16, 32, 64, 128])
        if rng.random() < 0.7:
            output_length = rng.choice([2, 4, 8, 12, 16, 24])
        else:
            output_length = rng.choice([1, 32, 48, 64])
        requests.append(
            {
                "arrival": round(arrivals[request_id], 9),
                "input_length": input_length,
                "output_length": output_length,
            }
        )

    candidate_sizes = [size for size in (1, 2, 4, 8, 16, 32) if size <= request_count]
    edge_capacity = max(
        size / (schedule_cost + interpolate(rows, "decode_pre", size))
        for size in candidate_sizes
    )
    cloud_capacity = cloud_count * max(
        size / (schedule_cost + interpolate(rows, "decode_proc", size))
        for size in candidate_sizes
    )
    post_capacity = max(
        size / (schedule_cost + interpolate(rows, "decode_post", size))
        for size in candidate_sizes
    )
    link_capacity = bandwidth * 1_000_000.0 / max(8.0 * bytes_per_token, 1.0)
    estimated_capacity = max(
        1e-7,
        min(edge_capacity, cloud_capacity, post_capacity, link_capacity),
    )
    throughput_base = 0.08 * estimated_capacity
    throughput_upper = 0.72 * estimated_capacity

    singleton_path = (
        3.0 * schedule_cost
        + interpolate(rows, "decode_pre", 1)
        + interpolate(rows, "decode_proc", 1)
        + interpolate(rows, "decode_post", 1)
        + 2.0 * (latency + 8.0 * bytes_per_token / (bandwidth * 1_000_000.0))
    )
    slo2 = singleton_path * rng.uniform(1.2, 4.5)
    slo1 = max(10.0, singleton_path * rng.uniform(4.0, 16.0))
    throughput_weight = rng.choice([0.25, 0.5, 0.75, 0.95, 1.0])
    if regime == "latency_heavy":
        throughput_weight = rng.choice([0.0, 0.1, 0.25])

    return {
        "name": f"learned_{split}_{index:02d}_{regime}",
        "description": (
            f"Deterministic {split} workload for grouping-policy calibration; "
            f"family={regime}, seed={seed}."
        ),
        "system": {
            "K": cloud_count,
            "S": round(schedule_cost, 9),
            "latency_in_ms": round(latency, 9),
            "bandwidth_gbps": round(bandwidth, 9),
            "bytes_per_token": bytes_per_token,
            "num_layers": layer_count,
        },
        "scoring": {
            "SLO1": round(slo1, 9),
            "SLO2": round(slo2, 9),
            "tp_UB": round(max(throughput_upper, throughput_base + 1e-9), 12),
            "tp_base": round(throughput_base, 12),
            "dist_base": round(rng.uniform(0.5, 5.0), 9),
            "w_tp": throughput_weight,
            "w_c": round(1.0 - throughput_weight, 9),
        },
        "task_times": rows,
        "requests": requests,
    }


def generate(output_dir: pathlib.Path, train_count: int, holdout_count: int) -> None:
    output_dir = output_dir.resolve()
    build_root = (ROOT / "build").resolve()
    if build_root not in output_dir.parents:
        raise ValueError(f"refusing to replace generated data outside {build_root}")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    for split, count, seed_base in (
        ("train", train_count, 17_000),
        ("holdout", holdout_count, 91_000),
    ):
        split_dir = output_dir / split
        split_dir.mkdir(parents=True, exist_ok=True)
        for index in range(count):
            data = scenario(seed_base + 997 * index, split, index)
            path = split_dir / f"{index:02d}_{REGIMES[index % len(REGIMES)]}.json"
            path.write_text(json.dumps(data, indent=2) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=ROOT / "build" / "learned-grouping" / "scenarios",
    )
    parser.add_argument("--train-count", type=int, default=18)
    parser.add_argument("--holdout-count", type=int, default=12)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.train_count < 1 or args.holdout_count < 1:
        raise SystemExit("train and holdout counts must be positive")
    generate(args.output_dir, args.train_count, args.holdout_count)
    print(
        f"Generated {args.train_count} train and {args.holdout_count} holdout scenarios "
        f"under {args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
