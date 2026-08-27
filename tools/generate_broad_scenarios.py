#!/usr/bin/env python3
"""Generate a deterministic, hash-locked scheduler development corpus.

The corpus deliberately separates policy development from validation.  Hidden output lengths
are written only to scenario files consumed by the local interactor; the solver still receives
exactly the public interactive protocol.  The holdout split should not be evaluated until a
candidate and all of its thresholds have been frozen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import random
import shutil
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
BATCH_SIZES = (1, 2, 4, 8, 16, 32, 64, 256, 4096)
ARRIVAL_FAMILIES = ("burst", "waves", "steady", "poisson", "two_bursts", "accelerating")
BOTTLENECKS = ("balanced", "dpre", "dproc", "dpost", "prefill", "uplink", "downlink")
CURVE_FAMILIES = ("smooth", "flat", "knee", "cliff", "nonmonotonic", "weak_batching")
OUTPUT_FAMILIES = ("uniform_short", "uniform_long", "bimodal", "heavy_tail", "alternating")


def log_uniform(rng: random.Random, low: float, high: float) -> float:
    return math.exp(rng.uniform(math.log(low), math.log(high)))


def curve(
    rng: random.Random,
    base: float,
    family: str,
    stage_scale: float = 1.0,
) -> list[float]:
    exponent = rng.uniform(0.28, 0.78)
    fixed = rng.uniform(0.2, 0.82)
    knee = rng.choice((2, 4, 8, 16, 32))
    values: list[float] = []
    for size in BATCH_SIZES:
        if family == "flat":
            factor = 0.92 + rng.uniform(0.008, 0.04) * size**rng.uniform(0.35, 0.65)
        elif family == "knee":
            factor = fixed + (1.0 - fixed) * min(size, knee) ** exponent
            if size > knee:
                factor += rng.uniform(0.35, 1.6) * (size - knee) / knee
        elif family == "cliff":
            factor = fixed + (1.0 - fixed) * size**exponent
            if size >= knee:
                factor *= rng.uniform(2.0, 8.0)
        elif family == "nonmonotonic":
            factor = fixed + (1.0 - fixed) * size**exponent
            if size in {knee, min(4096, knee * 2)}:
                factor *= rng.uniform(0.35, 0.75)
        elif family == "weak_batching":
            factor = rng.uniform(0.05, 0.25) + rng.uniform(0.75, 1.05) * size ** rng.uniform(0.82, 1.08)
        else:
            factor = fixed + (1.0 - fixed) * size**exponent
        noise = rng.uniform(0.97, 1.03)
        values.append(round(max(0.0001, base * stage_scale * factor * noise), 9))
    return values


def task_table(rng: random.Random, bottleneck: str, curve_family: str) -> list[dict[str, Any]]:
    bases = {
        "prefill_pre": log_uniform(rng, 0.03, 4.0),
        "prefill_proc": log_uniform(rng, 0.15, 18.0),
        "prefill_post": log_uniform(rng, 0.03, 4.0),
        "decode_pre": log_uniform(rng, 0.03, 8.0),
        "decode_proc": log_uniform(rng, 0.15, 28.0),
        "decode_post": log_uniform(rng, 0.03, 8.0),
    }
    scales = {name: 1.0 for name in bases}
    if bottleneck == "dpre":
        scales["decode_pre"] = rng.uniform(4.0, 15.0)
    elif bottleneck == "dproc":
        scales["decode_proc"] = rng.uniform(4.0, 15.0)
    elif bottleneck == "dpost":
        scales["decode_post"] = rng.uniform(4.0, 15.0)
    elif bottleneck == "prefill":
        for name in ("prefill_pre", "prefill_proc", "prefill_post"):
            scales[name] = rng.uniform(3.0, 10.0)

    columns: dict[str, list[float]] = {}
    for name, base in bases.items():
        family = curve_family
        if rng.random() < 0.24:
            family = rng.choice(CURVE_FAMILIES)
        columns[name] = curve(rng, base, family, scales[name])

    rows: list[dict[str, Any]] = []
    for row_index, size in enumerate(BATCH_SIZES):
        row: dict[str, Any] = {"batch_size": size}
        for name, values in columns.items():
            row[name] = values[row_index]
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
            ratio = (size - left_size) / (right_size - left_size)
            return left_value + ratio * (right_value - left_value)
    raise AssertionError("interpolation fell through")


def arrivals(rng: random.Random, family: str, count: int) -> list[float]:
    if family == "burst":
        return [0.0] * count
    if family == "waves":
        wave = rng.choice((2, 3, 4, 8, 12, 16))
        gap = log_uniform(rng, 0.02, 30.0)
        return [gap * (index // wave) for index in range(count)]
    if family == "two_bursts":
        cut = rng.randint(max(1, count // 4), max(1, 3 * count // 4))
        gap = log_uniform(rng, 0.1, 80.0)
        return [0.0 if index < cut else gap for index in range(count)]
    if family == "steady":
        gap = log_uniform(rng, 0.01, 8.0)
        return [gap * index for index in range(count)]
    values = [0.0]
    rate = log_uniform(rng, 0.02, 5.0)
    for index in range(1, count):
        if family == "accelerating":
            mean_gap = rate / (1.0 + 4.0 * index / count)
            gap = rng.expovariate(1.0 / max(1e-9, mean_gap))
        else:
            gap = rng.expovariate(1.0 / rate)
        values.append(values[-1] + gap)
    return values


def output_lengths(rng: random.Random, family: str, count: int) -> list[int]:
    if family == "uniform_short":
        return [rng.choice((1, 2, 3, 4, 6, 8)) for _ in range(count)]
    if family == "uniform_long":
        return [rng.choice((16, 24, 32, 48, 64, 96, 128)) for _ in range(count)]
    if family == "bimodal":
        return [rng.choice((1, 2, 4)) if rng.random() < 0.72 else rng.choice((32, 64, 128, 256)) for _ in range(count)]
    if family == "alternating":
        return [rng.choice((1, 2, 4)) if index % 2 == 0 else rng.choice((24, 48, 96)) for index in range(count)]
    values = []
    for _ in range(count):
        raw = min(384.0, max(1.0, rng.paretovariate(1.55) * 4.0))
        values.append(max(1, int(round(raw))))
    return values


def scenario(seed: int, split: str, index: int) -> dict[str, Any]:
    rng = random.Random(seed)
    arrival_family = ARRIVAL_FAMILIES[index % len(ARRIVAL_FAMILIES)]
    bottleneck = BOTTLENECKS[(index // len(ARRIVAL_FAMILIES)) % len(BOTTLENECKS)]
    curve_family = CURVE_FAMILIES[(index // (len(ARRIVAL_FAMILIES) * len(BOTTLENECKS))) % len(CURVE_FAMILIES)]
    output_family = OUTPUT_FAMILIES[(index * 7 + index // 5) % len(OUTPUT_FAMILIES)]

    cloud_count = rng.randint(1, 8)
    request_count = rng.choice((4, 6, 8, 12, 16, 24, 32, 48, 64, 96))
    schedule_cost = log_uniform(rng, 0.01, 20.0)
    latency = log_uniform(rng, 0.001, 60.0)
    bandwidth = log_uniform(rng, 0.01, 1000.0)
    bytes_per_token = int(round(log_uniform(rng, 16.0, 1_000_000.0)))
    if bottleneck == "uplink":
        latency = log_uniform(rng, 2.0, 80.0)
        bandwidth = log_uniform(rng, 0.005, 0.2)
        bytes_per_token = rng.randint(100_000, 1_000_000)
    elif bottleneck == "downlink":
        latency = log_uniform(rng, 2.0, 80.0)
        bandwidth = log_uniform(rng, 0.005, 0.3)
        bytes_per_token = rng.randint(50_000, 1_000_000)

    rows = task_table(rng, bottleneck, curve_family)
    arrival_values = arrivals(rng, arrival_family, request_count)
    outputs = output_lengths(rng, output_family, request_count)
    total_output = sum(outputs)
    if total_output > 180_000:
        outputs = [max(1, value * 180_000 // total_output) for value in outputs]

    requests = []
    for request_id in range(request_count):
        if rng.random() < 0.72:
            input_length = rng.choice((1, 2, 4, 8, 16, 32, 64, 128, 256))
        else:
            input_length = rng.randint(1, 512)
        requests.append(
            {
                "arrival": round(arrival_values[request_id], 9),
                "input_length": input_length,
                "output_length": outputs[request_id],
            }
        )

    eligible = [size for size in BATCH_SIZES if size <= request_count]
    edge_capacity = max(
        size / (schedule_cost + interpolate(rows, "decode_pre", size))
        for size in eligible
    )
    cloud_capacity = cloud_count * max(
        size / (schedule_cost + interpolate(rows, "decode_proc", size))
        for size in eligible
    )
    post_capacity = max(
        size / (schedule_cost + interpolate(rows, "decode_post", size))
        for size in eligible
    )
    link_capacity = bandwidth * 1_000_000.0 / max(8.0 * bytes_per_token, 1.0)
    estimated_capacity = max(1e-9, min(edge_capacity, cloud_capacity, post_capacity, link_capacity))

    transfer_singleton = latency + 8.0 * bytes_per_token / (bandwidth * 1_000_000.0)
    singleton_decode = (
        3.0 * schedule_cost
        + interpolate(rows, "decode_pre", 1)
        + interpolate(rows, "decode_proc", 1)
        + interpolate(rows, "decode_post", 1)
        + 2.0 * transfer_singleton
    )
    median_input = sorted(request["input_length"] for request in requests)[request_count // 2]
    singleton_prefill = (
        3.0 * schedule_cost
        + interpolate(rows, "prefill_pre", median_input)
        + interpolate(rows, "prefill_proc", median_input)
        + interpolate(rows, "prefill_post", median_input)
        + 2.0 * (latency + 8.0 * median_input * bytes_per_token / (bandwidth * 1_000_000.0))
    )

    throughput_weight = rng.choice((0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0))
    if output_family in {"bimodal", "heavy_tail"} and rng.random() < 0.55:
        throughput_weight = rng.choice((0.0, 0.1, 0.25, 0.5))
    throughput_base = estimated_capacity * rng.uniform(0.015, 0.08)
    throughput_upper = estimated_capacity * rng.uniform(0.55, 0.88)
    if throughput_upper <= throughput_base:
        throughput_upper = throughput_base * 1.01

    return {
        "name": f"broad_{split}_{index:04d}_{arrival_family}_{bottleneck}_{curve_family}_{output_family}",
        "description": (
            "Deterministic broad scheduler corpus case; "
            f"split={split}, seed={seed}, arrival={arrival_family}, bottleneck={bottleneck}, "
            f"curve={curve_family}, outputs={output_family}."
        ),
        "system": {
            "K": cloud_count,
            "S": round(schedule_cost, 9),
            "latency_in_ms": round(latency, 9),
            "bandwidth_gbps": round(bandwidth, 9),
            "bytes_per_token": bytes_per_token,
            "num_layers": rng.choice((1, 2, 4, 8, 16, 32, 64, 96)),
        },
        "scoring": {
            "SLO1": round(max(0.001, singleton_prefill * rng.uniform(0.65, 5.0)), 9),
            "SLO2": round(max(0.001, singleton_decode * rng.uniform(0.55, 4.0)), 9),
            "tp_UB": round(throughput_upper, 12),
            "tp_base": round(throughput_base, 12),
            "dist_base": round(log_uniform(rng, 0.08, 8.0), 9),
            "w_tp": throughput_weight,
            "w_c": round(1.0 - throughput_weight, 9),
        },
        "task_times": rows,
        "requests": requests,
    }


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(output_dir: pathlib.Path, counts: dict[str, int], seed_bases: dict[str, int]) -> None:
    output_dir = output_dir.resolve()
    build_root = (ROOT / "build").resolve()
    if build_root not in output_dir.parents:
        raise ValueError(f"refusing to replace generated data outside {build_root}")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "generator": pathlib.Path(__file__).relative_to(ROOT).as_posix(),
        "splits": {},
    }
    for split in ("train", "validation", "holdout"):
        split_dir = output_dir / split
        split_dir.mkdir(parents=True, exist_ok=True)
        entries = []
        for index in range(counts[split]):
            seed = seed_bases[split] + 10_007 * index
            data = scenario(seed, split, index)
            path = split_dir / f"{index:04d}.json"
            path.write_text(json.dumps(data, indent=2) + "\n")
            entries.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "seed": seed,
                    "sha256": sha256(path),
                }
            )
        manifest["splits"][split] = entries
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"Generated train={counts['train']}, validation={counts['validation']}, "
        f"sealed holdout={counts['holdout']} under {output_dir}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=ROOT / "build" / "broad-corpus" / "scenarios",
    )
    parser.add_argument("--train-count", type=int, default=256)
    parser.add_argument("--validation-count", type=int, default=128)
    parser.add_argument("--holdout-count", type=int, default=128)
    parser.add_argument("--train-seed-base", type=int, default=225_125_000)
    parser.add_argument("--validation-seed-base", type=int, default=225_125_999)
    parser.add_argument("--holdout-seed-base", type=int, default=225_126_999)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    counts = {
        "train": args.train_count,
        "validation": args.validation_count,
        "holdout": args.holdout_count,
    }
    if any(count < 1 for count in counts.values()):
        raise SystemExit("all split counts must be positive")
    generate(
        args.output_dir,
        counts,
        {
            "train": args.train_seed_base,
            "validation": args.validation_seed_base,
            "holdout": args.holdout_seed_base,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
