# %% [markdown]
# # Scheduler Version Benchmark Workbench
#
# This notebook builds every registered scheduler version, runs each one against the same
# policy-independent scenario suite, and compares legality and performance. It is the
# experiment dashboard for the optimization sequence developed in the companion
# `edge_cloud_scheduling_lab.ipynb` notebook.

# %% [markdown]
# ## Goal
#
# Use one repeatable loop for every scheduler iteration:
#
# 1. freeze a named source version;
# 2. compile all selected versions with the same flags;
# 3. run the same selected scenarios through the dynamic local judge;
# 4. reject illegal policies before interpreting performance;
# 5. compare scenario-level score, throughput, TDR, TPOT, and elapsed time; and
# 6. save an optional durable experiment record.
#
# **Decision rule:** score is the primary local outcome, but a policy should not be accepted
# until its scenario-level tradeoffs are understood. An unweighted suite mean is a convenient
# summary, not a substitute for the official hidden tests.

# %% [markdown]
# ## Setup

# %%
from __future__ import annotations

import hashlib
import html
import json
import math
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Iterable

from IPython.display import HTML, Markdown, display


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "main.cpp").is_file() and (candidate / "tools/local_judge.py").is_file():
            return candidate
    raise FileNotFoundError("Could not find the scheduler repository")


REPO_ROOT = find_repo_root()
REGISTRY_PATH = REPO_ROOT / "scheduler_versions/registry.json"
SCENARIO_DIR = REPO_ROOT / "scenarios"
REFERENCE_RESULTS_PATH = REPO_ROOT / "benchmarks/baseline-v0.json"
RUN_DIR = REPO_ROOT / "build/benchmark-runs"
BIN_DIR = REPO_ROOT / "build/scheduler-versions"

RUN_DIR.mkdir(parents=True, exist_ok=True)
BIN_DIR.mkdir(parents=True, exist_ok=True)

print(f"Repository: {REPO_ROOT}")
print(f"Registry:   {REGISTRY_PATH.relative_to(REPO_ROOT)}")

# %%
def display_table(
    rows: Iterable[dict[str, Any]],
    columns: list[tuple[str, str]] | None = None,
    cell_style: Any | None = None,
) -> None:
    bounded_rows = list(rows)
    if not bounded_rows:
        display(Markdown("_No rows._"))
        return
    if columns is None:
        columns = [(key, key) for key in bounded_rows[0]]
    header = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
    body = []
    for row in bounded_rows:
        cells = []
        for key, _ in columns:
            style = cell_style(row, key) if cell_style else ""
            cells.append(
                f'<td style="{html.escape(style)}">{html.escape(str(row.get(key, "")))}</td>'
            )
        body.append("<tr>" + "".join(cells) + "</tr>")
    display(
        HTML(
            "<table><thead><tr>"
            + header
            + "</tr></thead><tbody>"
            + "".join(body)
            + "</tbody></table>"
        )
    )


def run_command(command: list[str], timeout_seconds: float = 180.0) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(command)}\n{detail}")
    return completed

# %% [markdown]
# ## 1. Select versions and scenarios
#
# `all` is the normal comparison. Replace it with a list of names for a faster focused run.
# The benchmark is deterministic, so repeated runs are a reproducibility check rather than a
# statistical sample.

# %%
VERSIONS_TO_RUN: str | list[str] = "all"
SCENARIOS_TO_RUN: str | list[str] = "all"
REFERENCE_VERSION = "v0-baseline"
FOCUS_SCENARIO = "batch_friendly_burst"

# Optional durable save. The normal outputs under build/ are disposable and ignored by Git.
SAVE_DURABLE_RUN = False
DURABLE_RUN_LABEL = "replace-with-experiment-name"

# Display-only thresholds. They flag tradeoffs but do not fail the notebook.
SCORE_REGRESSION_ALERT = -1.0
THROUGHPUT_REGRESSION_ALERT_PERCENT = -5.0
LATENCY_REGRESSION_ALERT_PERCENT = 10.0

# %%
registry = json.loads(REGISTRY_PATH.read_text())
assert registry["schema_version"] == 1
registered_versions = registry["versions"]

version_names = [version["name"] for version in registered_versions]
assert len(version_names) == len(set(version_names)), "Scheduler names must be unique"
assert REFERENCE_VERSION in version_names

if VERSIONS_TO_RUN == "all":
    selected_versions = registered_versions
else:
    requested_versions = set(VERSIONS_TO_RUN)
    unknown_versions = requested_versions.difference(version_names)
    assert not unknown_versions, f"Unknown versions: {sorted(unknown_versions)}"
    selected_versions = [
        version for version in registered_versions if version["name"] in requested_versions
    ]
    if REFERENCE_VERSION not in requested_versions:
        selected_versions.insert(
            0, next(version for version in registered_versions if version["name"] == REFERENCE_VERSION)
        )

version_rows = []
for version in selected_versions:
    source_path = REPO_ROOT / version["source"]
    assert source_path.is_file(), f"Missing source: {source_path}"
    compile_defines = version.get("compile_defines", [])
    hash_input = source_path.read_bytes() + json.dumps(compile_defines, sort_keys=True).encode()
    source_hash = hashlib.sha256(hash_input).hexdigest()
    version_rows.append(
        {
            "version": version["name"],
            "layer": version.get("layer", 0),
            "source": version["source"],
            "defines": ", ".join(compile_defines) or "none",
            "frozen": version["frozen"],
            "sha256": source_hash[:12],
            "description": version["description"],
        }
    )

display_table(version_rows)

# %%
all_scenario_paths = sorted(SCENARIO_DIR.glob("*.json"))
scenario_data = {json.loads(path.read_text())["name"]: json.loads(path.read_text()) for path in all_scenario_paths}
scenario_path_by_name = {
    json.loads(path.read_text())["name"]: path for path in all_scenario_paths
}

if SCENARIOS_TO_RUN == "all":
    selected_scenario_names = list(scenario_path_by_name)
else:
    selected_scenario_names = list(SCENARIOS_TO_RUN)
    unknown_scenarios = set(selected_scenario_names).difference(scenario_path_by_name)
    assert not unknown_scenarios, f"Unknown scenarios: {sorted(unknown_scenarios)}"

display_table(
    [
        {
            "scenario": name,
            "requests": len(scenario_data[name]["requests"]),
            "tokens": sum(request["output_length"] for request in scenario_data[name]["requests"]),
            "throughput weight": scenario_data[name]["scoring"]["w_tp"],
            "latency weight": scenario_data[name]["scoring"]["w_c"],
        }
        for name in selected_scenario_names
    ]
)

# %% [markdown]
# ## 2. Build every selected version
#
# Every source is compiled independently with identical base flags. The displayed fingerprint
# hashes both source bytes and compile definitions, so two feature levels remain distinguishable
# even though they use the same C++ file.

# %%
CXX = os.environ.get("CXX", "g++")
CXXFLAGS = shlex.split(
    os.environ.get("CXXFLAGS", "-std=c++17 -O2 -pipe -Wall -Wextra -Wpedantic")
)

executables: dict[str, Path] = {}
build_rows = []
for version in selected_versions:
    name = version["name"]
    source_path = REPO_ROOT / version["source"]
    executable = BIN_DIR / name
    define_flags = [f"-D{define}" for define in version.get("compile_defines", [])]
    completed = run_command(
        [CXX, *CXXFLAGS, *define_flags, str(source_path), "-o", str(executable)]
    )
    executables[name] = executable
    build_rows.append(
        {
            "version": name,
            "status": "PASS",
            "compiler": CXX,
            "warnings": len([line for line in completed.stderr.splitlines() if "warning:" in line]),
            "executable": executable.relative_to(REPO_ROOT),
        }
    )

display_table(build_rows)

# %% [markdown]
# The fixed transcript tests assert the baseline's exact output order. A future optimization
# may produce a different but legal transcript, so those tests are **not** used as a universal
# policy gate. The dynamic local judge below validates legal decisions regardless of policy.

# %% [markdown]
# ## 3. Benchmark every version

# %%
scenario_arguments = [str(scenario_path_by_name[name]) for name in selected_scenario_names]
results_by_version: dict[str, list[dict[str, Any]]] = {}
run_rows = []

for version in selected_versions:
    name = version["name"]
    output_path = RUN_DIR / f"{name}.json"
    command = [
        "python3",
        "tools/local_judge.py",
        "--solver",
        str(executables[name]),
        "--scenarios",
        *scenario_arguments,
        "--json-out",
        str(output_path),
    ]
    completed = run_command(command)
    results = json.loads(output_path.read_text())
    results_by_version[name] = results
    run_rows.append(
        {
            "version": name,
            "legal scenarios": sum(bool(row.get("legal")) for row in results),
            "scenario count": len(results),
            "status": "PASS" if all(row.get("legal") for row in results) else "ILLEGAL",
        }
    )

display_table(run_rows)

# %% [markdown]
# ## 4. Validate the benchmark inputs and calculations
#
# Validation is performed before rankings are displayed:
#
# - each version must return one result for every selected scenario;
# - local-judge legality is mandatory;
# - token counts must match scenario truth;
# - score components are recomputed independently; and
# - the frozen `v0-baseline` source must reproduce `baseline-v0.json` on the full suite.

# %%
def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def recompute_score(result: dict[str, Any], scoring: dict[str, Any]) -> float:
    excess_tdr = max(0.0, (result["tdr"] - scoring["SLO1"]) / scoring["SLO1"])
    excess_tpot = max(0.0, (result["tpot"] - scoring["SLO2"]) / scoring["SLO2"])
    distance = math.hypot(excess_tdr, excess_tpot)
    throughput_component = clamp01(
        (result["throughput"] - scoring["tp_base"])
        / (scoring["tp_UB"] - scoring["tp_base"])
    )
    distance_base = scoring["dist_base"]
    latency_component = (
        max(0.0, 1.0 - distance / distance_base)
        if distance_base > 0
        else (1.0 if distance == 0 else 0.0)
    )
    return 1000.0 * (
        scoring["w_tp"] * throughput_component + scoring["w_c"] * latency_component
    )


validation_rows = []
for version_name, results in results_by_version.items():
    result_names = [result["scenario"] for result in results]
    assert len(result_names) == len(set(result_names))
    assert set(result_names) == set(selected_scenario_names)
    assert all(result.get("legal") for result in results), f"{version_name} produced an illegal schedule"

    maximum_score_error = 0.0
    for result in results:
        scenario = scenario_data[result["scenario"]]
        expected_tokens = sum(request["output_length"] for request in scenario["requests"])
        assert result["tokens"] == expected_tokens
        recalculated = recompute_score(result, scenario["scoring"])
        maximum_score_error = max(maximum_score_error, abs(recalculated - result["score"]))
        assert 0.0 <= result["score"] <= 1000.0
        assert result["throughput"] > 0.0 and result["elapsed"] > 0.0
        assert result["tdr"] >= 0.0 and result["tpot"] >= 0.0
    assert maximum_score_error < 1e-7
    validation_rows.append(
        {
            "version": version_name,
            "coverage": f"{len(results)}/{len(selected_scenario_names)}",
            "legal": "yes",
            "token counts": "verified",
            "max score error": f"{maximum_score_error:.2e}",
        }
    )

display_table(validation_rows)

# %%
if set(selected_scenario_names) == set(scenario_path_by_name):
    expected_baseline = {
        row["scenario"]: row for row in json.loads(REFERENCE_RESULTS_PATH.read_text())
    }
    observed_baseline = {
        row["scenario"]: row for row in results_by_version[REFERENCE_VERSION]
    }
    maximum_snapshot_delta = max(
        abs(observed_baseline[name][metric] - expected[metric])
        for name, expected in expected_baseline.items()
        for metric in ("score", "throughput", "tdr", "tpot", "elapsed")
    )
    assert maximum_snapshot_delta < 1e-6
    print(f"Frozen baseline reproduced baseline-v0.json; max metric delta={maximum_snapshot_delta:.2e}")
else:
    maximum_snapshot_delta = None
    print("Baseline snapshot check skipped because this is a filtered scenario run.")

# %% [markdown]
# ## 5. Suite results
#
# The summary treats every selected scenario equally. Relative throughput, latency, and elapsed
# columns are geometric means of per-scenario ratios to the reference. This avoids pretending
# that raw throughput values from different workloads share one denominator.

# %%
def result_map(version_name: str) -> dict[str, dict[str, Any]]:
    return {row["scenario"]: row for row in results_by_version[version_name]}


reference_map = result_map(REFERENCE_VERSION)


def geometric_mean_ratio(ratios: list[float]) -> float:
    assert ratios and all(ratio > 0 for ratio in ratios)
    return math.exp(sum(math.log(ratio) for ratio in ratios) / len(ratios))


def format_geometric_change(ratios: list[float]) -> str:
    if not ratios:
        return "n/a"
    return f"{100 * (geometric_mean_ratio(ratios) - 1):+.1f}%"


summary_rows = []
for version in selected_versions:
    name = version["name"]
    current = result_map(name)
    scores = [current[scenario]["score"] for scenario in selected_scenario_names]
    score_deltas = [
        current[scenario]["score"] - reference_map[scenario]["score"]
        for scenario in selected_scenario_names
    ]
    tp_ratios = [
        current[scenario]["throughput"] / reference_map[scenario]["throughput"]
        for scenario in selected_scenario_names
    ]
    tdr_ratios = [
        current[scenario]["tdr"] / reference_map[scenario]["tdr"]
        for scenario in selected_scenario_names
        if reference_map[scenario]["tdr"] > 0 and current[scenario]["tdr"] > 0
    ]
    tpot_ratios = [
        current[scenario]["tpot"] / reference_map[scenario]["tpot"]
        for scenario in selected_scenario_names
        if reference_map[scenario]["tpot"] > 0 and current[scenario]["tpot"] > 0
    ]
    elapsed_ratios = [
        current[scenario]["elapsed"] / reference_map[scenario]["elapsed"]
        for scenario in selected_scenario_names
    ]
    summary_rows.append(
        {
            "version": name,
            "mean score": f"{sum(scores) / len(scores):.3f}",
            "mean score delta": f"{sum(score_deltas) / len(score_deltas):+.3f}",
            "wins / ties / losses": (
                f"{sum(delta > 1e-9 for delta in score_deltas)} / "
                f"{sum(abs(delta) <= 1e-9 for delta in score_deltas)} / "
                f"{sum(delta < -1e-9 for delta in score_deltas)}"
            ),
            "throughput geo %": format_geometric_change(tp_ratios),
            "TDR geo %": format_geometric_change(tdr_ratios),
            "TPOT geo %": format_geometric_change(tpot_ratios),
            "elapsed geo %": format_geometric_change(elapsed_ratios),
        }
    )

display_table(summary_rows)

# %% [markdown]
# ### Scenario score matrix
#
# Green marks the best score observed for that scenario in this run. Ties are all highlighted.

# %%
score_matrix_rows = []
for scenario_name in selected_scenario_names:
    row: dict[str, Any] = {"scenario": scenario_name}
    for version in selected_versions:
        name = version["name"]
        row[name] = f"{result_map(name)[scenario_name]['score']:.3f}"
    score_matrix_rows.append(row)


def best_score_style(row: dict[str, Any], key: str) -> str:
    if key == "scenario":
        return "font-weight: 600"
    numeric_scores = [float(row[version["name"]]) for version in selected_versions]
    return "background: #d9f2df; font-weight: 600" if math.isclose(float(row[key]), max(numeric_scores), abs_tol=5e-4) else ""


display_table(
    score_matrix_rows,
    [("scenario", "Scenario")] + [(version["name"], version["name"]) for version in selected_versions],
    cell_style=best_score_style,
)

# %% [markdown]
# ### Score deltas from the frozen baseline

# %%
delta_rows = []
for scenario_name in selected_scenario_names:
    row = {"scenario": scenario_name}
    for version in selected_versions:
        name = version["name"]
        delta = result_map(name)[scenario_name]["score"] - reference_map[scenario_name]["score"]
        row[name] = f"{delta:+.3f}"
    delta_rows.append(row)


def delta_style(row: dict[str, Any], key: str) -> str:
    if key == "scenario":
        return "font-weight: 600"
    value = float(row[key])
    if value > 1e-9:
        intensity = min(0.35, 0.08 + abs(value) / 500.0)
        return f"background: rgba(40, 167, 69, {intensity:.3f})"
    if value < -1e-9:
        intensity = min(0.35, 0.08 + abs(value) / 500.0)
        return f"background: rgba(220, 53, 69, {intensity:.3f})"
    return "background: #f3f4f6"


display_table(
    delta_rows,
    [("scenario", "Scenario")] + [(version["name"], version["name"]) for version in selected_versions],
    cell_style=delta_style,
)

# %% [markdown]
# ## 6. Isolate the effect of each layer
#
# Every `vN` binary contains layers `1...N`. Comparing it with `v(N-1)` therefore isolates
# the newly enabled feature gate while keeping source, compiler flags, and scenarios fixed.
# These are deterministic local workload results—not statistical estimates and not a claim
# about the official hidden-test distribution.

# %%
frozen_layers = sorted(
    (
        version
        for version in selected_versions
        if version.get("frozen") and version["name"].startswith("v")
    ),
    key=lambda version: version.get("layer", 0),
)
adjacent_layer_pairs = [
    (previous, current)
    for previous, current in zip(frozen_layers, frozen_layers[1:])
    if current.get("layer", 0) == previous.get("layer", 0) + 1
]

incremental_rows = []
for previous_version, current_version in adjacent_layer_pairs:
    previous_name = previous_version["name"]
    current_name = current_version["name"]
    previous_results = result_map(previous_name)
    current_results = result_map(current_name)
    deltas = {
        scenario_name: (
            current_results[scenario_name]["score"]
            - previous_results[scenario_name]["score"]
        )
        for scenario_name in selected_scenario_names
    }
    best_scenario = max(deltas, key=deltas.get)
    worst_scenario = min(deltas, key=deltas.get)
    mean_previous = sum(
        previous_results[name]["score"] for name in selected_scenario_names
    ) / len(selected_scenario_names)
    mean_current = sum(
        current_results[name]["score"] for name in selected_scenario_names
    ) / len(selected_scenario_names)
    incremental_rows.append(
        {
            "transition": f"{previous_name} → {current_name}",
            "new policy": current_version["description"],
            "mean score": f"{mean_current:.3f}",
            "incremental mean": f"{mean_current - mean_previous:+.3f}",
            "wins / ties / losses": (
                f"{sum(delta > 1e-9 for delta in deltas.values())} / "
                f"{sum(abs(delta) <= 1e-9 for delta in deltas.values())} / "
                f"{sum(delta < -1e-9 for delta in deltas.values())}"
            ),
            "largest gain": f"{best_scenario} ({deltas[best_scenario]:+.3f})",
            "largest regression": f"{worst_scenario} ({deltas[worst_scenario]:+.3f})",
        }
    )

if incremental_rows:
    display_table(incremental_rows)
else:
    display(Markdown("_Select adjacent frozen layers to populate this table._"))

# %% [markdown]
# ### Did each mechanism move its isolation scenario?
#
# These scenarios were written to make one scheduling pressure conspicuous. A positive delta
# supports the narrow statement that the newly enabled mechanism helped on that constructed
# input. A zero or negative result is equally useful: it tells us the heuristic did not buy
# anything under that pressure or traded away a more valuable metric.

# %%
layer_targets = {
    "v1-multi-active": ["two_cloud_parallel"],
    "v2-load-aware": ["output_length_skew"],
    "v3-immediate-groups": ["batch_friendly_burst"],
    "v4-table-groups": ["nonmonotonic_batch_table"],
    "v5-slo-aware": ["slo_priority_collision"],
    "v6-prefill-chunks": ["single_cloud_prefill_interleave"],
    "v7-link-aware": ["latency_weighted_slow_link"],
}

target_rows = []
for previous_version, current_version in adjacent_layer_pairs:
    previous_name = previous_version["name"]
    current_name = current_version["name"]
    for scenario_name in layer_targets.get(current_name, []):
        if scenario_name not in selected_scenario_names:
            continue
        old = result_map(previous_name)[scenario_name]
        new = result_map(current_name)[scenario_name]
        target_rows.append(
            {
                "layer": current_name,
                "isolation scenario": scenario_name,
                "score before": f"{old['score']:.3f}",
                "score after": f"{new['score']:.3f}",
                "score delta": f"{new['score'] - old['score']:+.3f}",
                "throughput delta %": f"{100 * (new['throughput'] / old['throughput'] - 1):+.1f}%",
                "TDR delta %": f"{100 * (new['tdr'] / old['tdr'] - 1):+.1f}%" if old["tdr"] else "n/a",
                "TPOT delta %": f"{100 * (new['tpot'] / old['tpot'] - 1):+.1f}%" if old["tpot"] else "n/a",
            }
        )

display_table(target_rows)

# %% [markdown]
# ## 7. Focus on one scenario
#
# Change `FOCUS_SCENARIO` in the parameter cell to inspect a different workload.

# %%
active_focus_scenario = (
    FOCUS_SCENARIO if FOCUS_SCENARIO in selected_scenario_names else selected_scenario_names[0]
)
if active_focus_scenario != FOCUS_SCENARIO:
    print(
        f"Configured focus scenario {FOCUS_SCENARIO!r} was filtered out; "
        f"showing {active_focus_scenario!r} instead."
    )
focus_rows = []
for version in selected_versions:
    name = version["name"]
    result = result_map(name)[active_focus_scenario]
    focus_rows.append(
        {
            "version": name,
            "score": f"{result['score']:.3f}",
            "score delta": f"{result['score'] - reference_map[active_focus_scenario]['score']:+.3f}",
            "throughput": f"{result['throughput']:.6f}",
            "TDR ms": f"{result['tdr']:.3f}",
            "TPOT ms": f"{result['tpot']:.3f}",
            "elapsed ms": f"{result['elapsed']:.3f}",
            "frames": result["frames"],
        }
    )

display(
    Markdown(
        f"### `{active_focus_scenario}`\n\n"
        f"{scenario_data[active_focus_scenario]['description']}"
    )
)
display_table(focus_rows)

# %% [markdown]
# ## 8. Regression alerts
#
# These alerts surface tradeoffs for review. They are not blanket rejection rules because a
# throughput-oriented policy can rationally trade latency in one scenario for a larger score
# gain elsewhere, depending on the supplied weights.

# %%
alert_rows = []
for version in selected_versions:
    name = version["name"]
    if name == REFERENCE_VERSION:
        continue
    current = result_map(name)
    for scenario_name in selected_scenario_names:
        old = reference_map[scenario_name]
        new = current[scenario_name]
        score_delta = new["score"] - old["score"]
        throughput_percent = 100.0 * (new["throughput"] / old["throughput"] - 1.0)
        tdr_percent = 100.0 * (new["tdr"] / old["tdr"] - 1.0) if old["tdr"] else 0.0
        tpot_percent = 100.0 * (new["tpot"] / old["tpot"] - 1.0) if old["tpot"] else 0.0
        reasons = []
        if score_delta < SCORE_REGRESSION_ALERT:
            reasons.append(f"score {score_delta:+.3f}")
        if throughput_percent < THROUGHPUT_REGRESSION_ALERT_PERCENT:
            reasons.append(f"throughput {throughput_percent:+.1f}%")
        if tdr_percent > LATENCY_REGRESSION_ALERT_PERCENT:
            reasons.append(f"TDR {tdr_percent:+.1f}%")
        if tpot_percent > LATENCY_REGRESSION_ALERT_PERCENT:
            reasons.append(f"TPOT {tpot_percent:+.1f}%")
        if reasons:
            alert_rows.append(
                {"version": name, "scenario": scenario_name, "review": ", ".join(reasons)}
            )

if alert_rows:
    display_table(alert_rows)
else:
    display(Markdown("_No configured regression thresholds were crossed._"))

# %% [markdown]
# ## 9. Save or export this run
#
# Disposable per-version JSON is always written to `build/benchmark-runs/`. Set
# `SAVE_DURABLE_RUN = True` only when the experiment is worth preserving in
# `benchmarks/runs/`; existing run labels are never overwritten.

# %%
combined_run = {
    "schema_version": 1,
    "reference_version": REFERENCE_VERSION,
    "scenario_names": selected_scenario_names,
    "versions": version_rows,
    "results": results_by_version,
    "summary": summary_rows,
    "incremental_layers": incremental_rows,
    "isolation_scenarios": target_rows,
    "validation": {
        "all_legal": all(row["status"] == "PASS" for row in run_rows),
        "score_recomputed": True,
        "baseline_snapshot_max_delta": maximum_snapshot_delta,
    },
}

latest_path = RUN_DIR / "latest-combined.json"
latest_path.write_text(json.dumps(combined_run, indent=2) + "\n")
print(f"Wrote disposable combined result: {latest_path.relative_to(REPO_ROOT)}")

if SAVE_DURABLE_RUN:
    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", DURABLE_RUN_LABEL)
    durable_dir = REPO_ROOT / "benchmarks/runs"
    durable_dir.mkdir(parents=True, exist_ok=True)
    durable_path = durable_dir / f"{DURABLE_RUN_LABEL}.json"
    if durable_path.exists():
        raise FileExistsError(f"Refusing to overwrite {durable_path}")
    durable_path.write_text(json.dumps(combined_run, indent=2) + "\n")
    print(f"Saved durable run: {durable_path.relative_to(REPO_ROOT)}")
else:
    print("Durable save disabled; set SAVE_DURABLE_RUN=True to preserve a named experiment.")

# %% [markdown]
# ## Checks

# %%
assert all(row["status"] == "PASS" for row in build_rows)
assert all(row["status"] == "PASS" for row in run_rows)
assert all(row["token counts"] == "verified" for row in validation_rows)
assert latest_path.is_file()
if VERSIONS_TO_RUN == "all" and SCENARIOS_TO_RUN == "all":
    assert len(incremental_rows) == 7
    assert len(target_rows) == 7
print("Benchmark workbench checks passed.")

# %% [markdown]
# ## Next steps
#
# Use the isolation table to choose the next experiment. Tune only one layer at a time, rerun
# the complete workbench, and inspect both its target-scenario gain and its worst regression.
# If a future policy becomes a meaningful checkpoint, preserve it with
# `tools/register_scheduler.py` before continuing so the comparison remains reproducible.
