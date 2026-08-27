#!/usr/bin/env python3
"""Train a tiny conservative residual policy from counterfactual score deltas."""

from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import dataclass
from typing import Any

import numpy as np


ROOT = pathlib.Path(__file__).resolve().parents[1]


@dataclass
class Model:
    mean: np.ndarray
    scale: np.ndarray
    w1: np.ndarray
    b1: np.ndarray
    w2: np.ndarray
    b2: np.ndarray

    def predict(self, values: np.ndarray) -> np.ndarray:
        normalized = (values - self.mean) / self.scale
        hidden = np.maximum(0.0, normalized @ self.w1 + self.b1)
        return hidden @ self.w2 + self.b2


def arrays(data: dict[str, Any], split: str, action_names: list[str]) -> tuple[np.ndarray, np.ndarray]:
    rows = data["splits"][split]["rows"]
    x = np.asarray([row["features"] for row in rows], dtype=np.float64)
    y = np.asarray(
        [[row["deltas"][action] for action in action_names] for row in rows],
        dtype=np.float64,
    )
    return x, y


def train(
    x: np.ndarray,
    deltas: np.ndarray,
    hidden: int,
    seed: int,
    negative_weight: float,
    regularization: float,
    epochs: int,
) -> Model:
    rng = np.random.default_rng(seed)
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale < 1e-6] = 1.0
    normalized = (x - mean) / scale
    target = np.tanh(deltas / 20.0)
    weights = np.where(deltas < -1e-8, negative_weight, np.where(deltas > 1e-8, 1.0, 0.15))

    w1 = rng.normal(0.0, np.sqrt(2.0 / x.shape[1]), size=(x.shape[1], hidden))
    b1 = np.zeros(hidden)
    w2 = rng.normal(0.0, 0.08, size=(hidden, deltas.shape[1]))
    b2 = np.zeros(deltas.shape[1])
    parameters = [w1, b1, w2, b2]
    first = [np.zeros_like(parameter) for parameter in parameters]
    second = [np.zeros_like(parameter) for parameter in parameters]
    beta1 = 0.9
    beta2 = 0.999
    learning_rate = 0.012

    for epoch in range(1, epochs + 1):
        z1 = normalized @ w1 + b1
        hidden_values = np.maximum(0.0, z1)
        prediction = hidden_values @ w2 + b2
        difference = prediction - target
        clipped = np.clip(difference, -1.0, 1.0)
        gradient_output = weights * clipped / weights.sum()
        gradients = [
            normalized.T @ ((gradient_output @ w2.T) * (z1 > 0)) + regularization * w1,
            ((gradient_output @ w2.T) * (z1 > 0)).sum(axis=0),
            hidden_values.T @ gradient_output + regularization * w2,
            gradient_output.sum(axis=0),
        ]
        for index, (parameter, gradient) in enumerate(zip(parameters, gradients)):
            first[index] = beta1 * first[index] + (1.0 - beta1) * gradient
            second[index] = beta2 * second[index] + (1.0 - beta2) * gradient * gradient
            corrected_first = first[index] / (1.0 - beta1**epoch)
            corrected_second = second[index] / (1.0 - beta2**epoch)
            parameter -= learning_rate * corrected_first / (np.sqrt(corrected_second) + 1e-8)
        if epoch in {2000, 3500}:
            learning_rate *= 0.35
    return Model(mean, scale, w1, b1, w2, b2)


def metrics(prediction: np.ndarray, deltas: np.ndarray, margin: float) -> dict[str, Any]:
    best = prediction.argmax(axis=1)
    best_prediction = prediction[np.arange(len(prediction)), best]
    chosen = np.where(best_prediction > margin, best, -1)
    actual = np.asarray(
        [0.0 if action < 0 else deltas[index, action] for index, action in enumerate(chosen)]
    )
    losses = actual[actual < -1e-8]
    return {
        "mean_delta": float(actual.mean()),
        "wins": int((actual > 1e-8).sum()),
        "ties": int((np.abs(actual) <= 1e-8).sum()),
        "losses": int((actual < -1e-8).sum()),
        "worst_delta": float(actual.min(initial=0.0)),
        "mean_loss": float((-losses).mean()) if len(losses) else 0.0,
        "chosen_actions": [int(value) for value in chosen],
    }


def select_margin(prediction: np.ndarray, deltas: np.ndarray) -> tuple[float, dict[str, Any]]:
    candidates = []
    for margin in np.linspace(-0.10, 0.90, 201):
        result = metrics(prediction, deltas, float(margin))
        candidates.append((float(margin), result))
    no_loss = [entry for entry in candidates if entry[1]["losses"] == 0]
    pool = no_loss if no_loss else candidates
    return max(
        pool,
        key=lambda entry: (
            entry[1]["mean_delta"] - 0.5 * entry[1]["mean_loss"] + 0.1 * entry[1]["worst_delta"],
            entry[1]["wins"],
            entry[0],
        ),
    )


def serialize(model: Model) -> dict[str, Any]:
    return {
        "mean": model.mean.tolist(),
        "scale": model.scale.tolist(),
        "w1": model.w1.tolist(),
        "b1": model.b1.tolist(),
        "w2": model.w2.tolist(),
        "b2": model.b2.tolist(),
    }


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
        default=ROOT / "build" / "neural-policy" / "trained-model.json",
    )
    parser.add_argument("--epochs", type=int, default=4500)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data = json.loads(args.dataset.read_text())
    action_names = [action["name"] for action in data["actions"]]
    train_x, train_y = arrays(data, "train", action_names)
    validation_x, validation_y = arrays(data, "validation", action_names)
    if min(len(train_x), len(validation_x)) < 1:
        raise RuntimeError("training and validation must both contain eligible states")

    candidates = []
    for hidden in (4, 8):
        for negative_weight in (4.0, 8.0, 16.0):
            for regularization in (0.0001, 0.001, 0.01):
                for seed in range(8):
                    model = train(
                        train_x,
                        train_y,
                        hidden,
                        seed,
                        negative_weight,
                        regularization,
                        args.epochs,
                    )
                    validation_prediction = model.predict(validation_x)
                    margin, validation_metrics = select_margin(validation_prediction, validation_y)
                    train_metrics = metrics(model.predict(train_x), train_y, margin)
                    robust = (
                        validation_metrics["mean_delta"]
                        + 0.25 * train_metrics["mean_delta"]
                        - 0.75 * train_metrics["mean_loss"]
                        + 0.10 * train_metrics["worst_delta"]
                    )
                    if validation_metrics["losses"]:
                        robust -= 20.0 * validation_metrics["losses"]
                    candidates.append(
                        {
                            "hidden": hidden,
                            "negative_weight": negative_weight,
                            "regularization": regularization,
                            "seed": seed,
                            "margin": margin,
                            "robust_selection_value": robust,
                            "train": train_metrics,
                            "validation": validation_metrics,
                            "model": model,
                        }
                    )
    candidates.sort(key=lambda row: row["robust_selection_value"], reverse=True)
    selected = candidates[0]
    report = {
        "schema_version": 1,
        "dataset": args.dataset.resolve().relative_to(ROOT).as_posix(),
        "feature_names": data["feature_names"],
        "actions": data["actions"],
        "target_transform": "tanh(score_delta / 20)",
        "architecture": f"{train_x.shape[1]}-relu-{selected['hidden']}-{len(action_names)}",
        "selection": {
            key: value
            for key, value in selected.items()
            if key != "model"
        },
        "model": serialize(selected["model"]),
        "top_candidates": [
            {key: value for key, value in candidate.items() if key != "model"}
            for candidate in candidates[:10]
        ],
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"selected {report['architecture']} margin={selected['margin']:.3f} "
        f"train={selected['train']['mean_delta']:+.3f} "
        f"W/T/L={selected['train']['wins']}/{selected['train']['ties']}/{selected['train']['losses']} "
        f"validation={selected['validation']['mean_delta']:+.3f} "
        f"W/T/L={selected['validation']['wins']}/{selected['validation']['ties']}/{selected['validation']['losses']}"
    )
    print(f"Wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
