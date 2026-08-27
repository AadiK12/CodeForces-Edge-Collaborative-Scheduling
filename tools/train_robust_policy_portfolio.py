#!/usr/bin/env python3
"""Train a public-state policy against hidden-world lower-confidence targets."""

from __future__ import annotations

import argparse
import json
import pathlib
from collections import defaultdict
from typing import Any

import numpy as np

from train_neural_policy import Model, serialize, train


ROOT = pathlib.Path(__file__).resolve().parents[1]


def grouped_arrays(
    data: dict[str, Any], split: str, action_names: list[str], risk: float
) -> tuple[np.ndarray, np.ndarray, list[np.ndarray], list[str]]:
    groups: dict[tuple[float, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in data["splits"][split]["rows"]:
        signature = tuple(round(float(value), 9) for value in row["features"])
        groups[signature].append(row)
    features = []
    targets = []
    worlds = []
    names = []
    for group_index, (signature, rows) in enumerate(sorted(groups.items())):
        name = f"{split}-{group_index:05d}"
        feature = np.asarray(rows[0]["features"], dtype=np.float64)
        for row in rows[1:]:
            if not np.allclose(feature, row["features"], atol=1e-9, rtol=0.0):
                raise RuntimeError(f"public state {signature} has inconsistent features")
        deltas = np.asarray(
            [[row["deltas"][action] for action in action_names] for row in rows],
            dtype=np.float64,
        )
        robust = deltas.mean(axis=0) - risk * deltas.std(axis=0)
        features.append(feature)
        targets.append(robust)
        worlds.append(deltas)
        names.append(name)
    return np.asarray(features), np.asarray(targets), worlds, names


def world_metrics(
    prediction: np.ndarray,
    worlds: list[np.ndarray],
    margin: float,
) -> dict[str, Any]:
    best = prediction.argmax(axis=1)
    confidence = prediction[np.arange(len(prediction)), best]
    chosen = np.where(confidence > margin, best, -1)
    deltas = []
    group_deltas = []
    for action, group_worlds in zip(chosen, worlds):
        actual = (
            np.zeros(group_worlds.shape[0])
            if action < 0
            else group_worlds[:, action]
        )
        deltas.extend(actual.tolist())
        group_deltas.append(float(actual.mean()))
    values = np.asarray(deltas, dtype=np.float64)
    groups = np.asarray(group_deltas, dtype=np.float64)
    return {
        "mean_delta": float(values.mean()),
        "mean_group_delta": float(groups.mean()),
        "wins": int((values > 1e-8).sum()),
        "ties": int((np.abs(values) <= 1e-8).sum()),
        "losses": int((values < -1e-8).sum()),
        "worst_delta": float(values.min(initial=0.0)),
        "chosen_groups": int((chosen >= 0).sum()),
        "chosen_actions": [int(value) for value in chosen],
    }


def select_margin(
    train_prediction: np.ndarray,
    train_worlds: list[np.ndarray],
    validation_prediction: np.ndarray,
    validation_worlds: list[np.ndarray],
) -> tuple[float, dict[str, Any], dict[str, Any]]:
    candidates = []
    for margin in np.linspace(-0.10, 0.95, 211):
        training = world_metrics(train_prediction, train_worlds, float(margin))
        validation = world_metrics(validation_prediction, validation_worlds, float(margin))
        candidates.append((float(margin), training, validation))
    no_loss = [
        entry for entry in candidates
        if entry[1]["losses"] == 0 and entry[2]["losses"] == 0
    ]
    validation_safe = [entry for entry in candidates if entry[2]["losses"] == 0]
    pool = no_loss if no_loss else validation_safe if validation_safe else candidates
    return max(
        pool,
        key=lambda entry: (
            entry[2]["mean_delta"] + 0.2 * entry[1]["mean_delta"] +
            0.05 * (entry[1]["worst_delta"] + entry[2]["worst_delta"]),
            entry[2]["wins"] + entry[1]["wins"],
            -entry[1]["losses"] - entry[2]["losses"],
            entry[0],
        ),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=pathlib.Path,
        default=ROOT / "build" / "neural-policy" / "dataset-development.json",
    )
    parser.add_argument(
        "--json-out",
        type=pathlib.Path,
        default=ROOT / "build" / "neural-policy" / "robust-portfolio-model.json",
    )
    parser.add_argument("--epochs", type=int, default=3500)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data = json.loads(args.dataset.read_text())
    action_names = [action["name"] for action in data["actions"][:6]]
    candidates = []
    for risk in (0.5, 1.0, 1.5, 2.0):
        train_x, train_target, train_worlds, train_names = grouped_arrays(
            data, "train", action_names, risk
        )
        validation_x, validation_target, validation_worlds, validation_names = grouped_arrays(
            data, "validation", action_names, risk
        )
        for hidden in (4, 8):
            for negative_weight in (8.0, 16.0):
                for regularization in (0.0005, 0.002):
                    for seed in range(6):
                        model = train(
                            train_x,
                            train_target,
                            hidden,
                            seed,
                            negative_weight,
                            regularization,
                            args.epochs,
                        )
                        training_prediction = model.predict(train_x)
                        validation_prediction = model.predict(validation_x)
                        margin, training, validation = select_margin(
                            training_prediction,
                            train_worlds,
                            validation_prediction,
                            validation_worlds,
                        )
                        robust_value = (
                            validation["mean_delta"] +
                            0.2 * training["mean_delta"] +
                            0.1 * validation["worst_delta"]
                        )
                        if validation["losses"]:
                            robust_value -= 25.0 * validation["losses"]
                        candidates.append(
                            {
                                "risk": risk,
                                "hidden": hidden,
                                "negative_weight": negative_weight,
                                "regularization": regularization,
                                "seed": seed,
                                "margin": margin,
                                "robust_selection_value": robust_value,
                                "train": training,
                                "validation": validation,
                                "train_groups": train_names,
                                "validation_groups": validation_names,
                                "model": model,
                            }
                        )
    candidates.sort(key=lambda row: row["robust_selection_value"], reverse=True)
    selected = candidates[0]
    report = {
        "schema_version": 1,
        "dataset": args.dataset.resolve().relative_to(ROOT).as_posix(),
        "feature_names": data["feature_names"],
        "actions": data["actions"][:6],
        "target": "public-group mean delta minus risk times hidden-world standard deviation",
        "architecture": f"18-relu-{selected['hidden']}-6",
        "selection": {key: value for key, value in selected.items() if key != "model"},
        "model": serialize(selected["model"]),
        "top_candidates": [
            {key: value for key, value in candidate.items() if key not in {"model", "train_groups", "validation_groups"}}
            for candidate in candidates[:12]
        ],
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"selected {report['architecture']} risk={selected['risk']:.1f} "
        f"margin={selected['margin']:.3f} "
        f"train W/T/L={selected['train']['wins']}/{selected['train']['ties']}/{selected['train']['losses']} "
        f"validation W/T/L={selected['validation']['wins']}/{selected['validation']['ties']}/{selected['validation']['losses']}"
    )
    print(f"Wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
