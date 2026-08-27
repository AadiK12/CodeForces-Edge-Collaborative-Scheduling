#!/usr/bin/env python3
"""Generate public-state-matched worlds for conservative policy selection."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import random
import shutil
from typing import Any

from generate_broad_scenarios import output_lengths, scenario


ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT_FAMILIES = ("uniform_short", "uniform_long", "bimodal", "heavy_tail", "alternating")


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_worlds(seed: int, split: str, index: int, worlds: int) -> list[dict[str, Any]]:
    base = scenario(seed, split, index)
    base["system"]["K"] = max(2, int(base["system"]["K"]))
    base["scoring"]["w_tp"] = 1.0
    base["scoring"]["w_c"] = 0.0
    request_count = len(base["requests"])
    family = OUTPUT_FAMILIES[(index * 7 + index // 5) % len(OUTPUT_FAMILIES)]
    result = []
    for world in range(worlds):
        data = json.loads(json.dumps(base))
        rng = random.Random(seed ^ (0x9E3779B9 * (world + 1)))
        outputs = output_lengths(rng, family, request_count)
        total = sum(outputs)
        if total > 180_000:
            outputs = [max(1, value * 180_000 // total) for value in outputs]
        for request, length in zip(data["requests"], outputs):
            request["output_length"] = length
        data["name"] = f"neural_{split}_{index:05d}_w{world}_{family}"
        data["description"] = (
            "Neural policy-selection world with public state shared inside a world group; "
            f"split={split}, public_seed={seed}, public_group={index}, world={world}, "
            f"hidden_output_family={family}."
        )
        data["policy_metadata"] = {
            "public_group": f"{split}-{index:05d}",
            "world": world,
            "hidden_output_family": family,
        }
        result.append(data)
    return result


def generate(
    output_dir: pathlib.Path,
    counts: dict[str, int],
    seed_bases: dict[str, int],
    worlds: int,
) -> None:
    output_dir = output_dir.resolve()
    build_root = (ROOT / "build").resolve()
    if build_root not in output_dir.parents:
        raise ValueError(f"refusing to replace generated data outside {build_root}")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "generator": pathlib.Path(__file__).relative_to(ROOT).as_posix(),
        "worlds_per_public_state": worlds,
        "splits": {},
    }
    for split in ("train", "validation", "holdout"):
        split_dir = output_dir / split
        split_dir.mkdir(parents=True, exist_ok=True)
        entries = []
        for index in range(counts[split]):
            seed = seed_bases[split] + 10_007 * index
            for world, data in enumerate(build_worlds(seed, split, index, worlds)):
                path = split_dir / f"{index:05d}_w{world}.json"
                path.write_text(json.dumps(data, indent=2) + "\n")
                entries.append(
                    {
                        "path": path.relative_to(ROOT).as_posix(),
                        "public_group": f"{split}-{index:05d}",
                        "world": world,
                        "seed": seed,
                        "sha256": sha256(path),
                    }
                )
        manifest["splits"][split] = entries
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        "Generated "
        + ", ".join(f"{split}={counts[split] * worlds}" for split in counts)
        + f" scenarios ({worlds} hidden worlds per public state) under {output_dir}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=ROOT / "build" / "neural-policy" / "scenarios",
    )
    parser.add_argument("--train-count", type=int, default=512)
    parser.add_argument("--validation-count", type=int, default=128)
    parser.add_argument("--holdout-count", type=int, default=256)
    parser.add_argument("--worlds", type=int, default=3)
    parser.add_argument("--train-seed-base", type=int, default=827_101_000)
    parser.add_argument("--validation-seed-base", type=int, default=827_201_000)
    parser.add_argument("--holdout-seed-base", type=int, default=827_301_000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if min(args.train_count, args.validation_count, args.holdout_count, args.worlds) < 1:
        raise SystemExit("counts and worlds must be positive")
    generate(
        args.output_dir,
        {
            "train": args.train_count,
            "validation": args.validation_count,
            "holdout": args.holdout_count,
        },
        {
            "train": args.train_seed_base,
            "validation": args.validation_seed_base,
            "holdout": args.holdout_seed_base,
        },
        args.worlds,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
