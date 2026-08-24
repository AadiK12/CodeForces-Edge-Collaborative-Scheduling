# %% [markdown]
# # Edge–Cloud Collaborative Scheduling Lab
#
# This notebook is a runnable companion to the
# [Codeforces 2251A problem](https://codeforces.com/contest/2251/problem/A).
# It keeps four activities in one place:
#
# 1. understand the system and interactive protocol;
# 2. connect those concepts to both the frozen baseline and the current layered scheduler;
# 3. run the policy against deterministic scenarios; and
# 4. add optimizations one at a time and measure what actually improves.
#
# The repository remains the source of truth. The notebook reads the checked-in C++ source,
# scenarios, task-time table, local judge, and baseline benchmark instead of copying them into
# a disconnected toy implementation.

# %% [markdown]
# ## Goal
#
# By the end of this lab, we should be able to answer:
#
# - What work runs on the edge, in a cloud, and on the shared links?
# - What does one request do from `ARR` to `FIN`?
# - What does an assignment such as `E D PRE -1 3 7 12 19` mean?
# - Why is the frozen baseline correct but intentionally inefficient?
# - When does decode grouping help, and when can waiting for a group hurt?
# - Which scenario should expose each optimization?
# - Did a code change remain legal, and did it improve score, throughput, TDR, or TPOT?
#
# **Notebook mode:** tutorial + experiment log.  
# **Reader:** someone learning the problem while implementing a contest scheduler.  
# **Handoff:** a top-to-bottom executable notebook tied to the current repository.

# %% [markdown]
# ## Setup

# %%
from __future__ import annotations

import html
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

from IPython.display import Code, HTML, Markdown, display


def find_repo_root(start: Path | None = None) -> Path:
    """Find the repository whether Jupyter starts in the root or notebooks/ directory."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "main.cpp").is_file() and (candidate / "tools/local_judge.py").is_file():
            return candidate
    raise FileNotFoundError("Could not find main.cpp and tools/local_judge.py above the working directory")


REPO_ROOT = find_repo_root()
BUILD_DIR = REPO_ROOT / "build"
BASELINE_SOLVER = BUILD_DIR / "v0-baseline"
WORKING_SOLVER = BUILD_DIR / "scheduler"
SCENARIO_DIR = REPO_ROOT / "scenarios"
BASELINE_SNAPSHOT = REPO_ROOT / "benchmarks/baseline-v0.json"
REGISTRY_PATH = REPO_ROOT / "scheduler_versions/registry.json"

print(f"Repository: {REPO_ROOT}")
print(f"Frozen v0:  {BASELINE_SOLVER}")
print(f"Current v7: {WORKING_SOLVER}")

# %%
def run_checked(command: list[str], timeout_seconds: float = 120.0) -> subprocess.CompletedProcess[str]:
    """Run a bounded command in the repository and show concise output."""
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )
    if completed.stdout.strip():
        print(completed.stdout.rstrip())
    if completed.returncode != 0:
        if completed.stderr.strip():
            print(completed.stderr.rstrip())
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {' '.join(command)}")
    return completed


run_checked(["make", "build/v0-baseline", "build/scheduler"])
assert BASELINE_SOLVER.is_file(), "The frozen baseline executable was not created"
assert WORKING_SOLVER.is_file(), "The current scheduler executable was not created"

# %%
def display_table(rows: Iterable[dict[str, Any]], columns: list[tuple[str, str]] | None = None) -> None:
    """Render a small list of dictionaries without requiring pandas."""
    bounded_rows = list(rows)
    if not bounded_rows:
        display(Markdown("_No rows._"))
        return
    if columns is None:
        columns = [(key, key) for key in bounded_rows[0]]
    header = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
    body = []
    for row in bounded_rows:
        cells = "".join(
            f"<td>{html.escape(str(row.get(key, '')))}</td>" for key, _ in columns
        )
        body.append(f"<tr>{cells}</tr>")
    display(
        HTML(
            "<table><thead><tr>"
            + header
            + "</tr></thead><tbody>"
            + "".join(body)
            + "</tbody></table>"
        )
    )

# %% [markdown]
# ## 1. Build the mental model
#
# Each request has a **prefill phase** followed by one or more **decode iterations**.
#
# ```text
# ARR
#   │
#   ▼
# Edge:  P PRE ──UP──▶ Cloud: P PROC ──DOWN──▶ Edge: P POST
#                                                    │
#                                                    ▼
# Edge:  D PRE ──UP──▶ Cloud: D PROC ──DOWN──▶ Edge: D POST
#          ▲                                           │
#          └──────── next token if not FIN ────────────┘
# ```
#
# Resource constraints:
#
# - There is one edge compute server, `E`.
# - There are `K` cloud compute servers, `C0 ... C(K-1)`.
# - Every server can run at most one task at a time.
# - All clouds collectively share one FIFO `UP` transfer queue and one FIFO `DOWN` queue.
# - Transfers do not occupy edge or cloud compute, but competing transfers queue on their link.
# - A request is assigned to a cloud by its `P PRE` task and keeps that cloud association.

# %% [markdown]
# ### Prefill versus decode grouping
#
# | Family | Edge stage | Cloud stage | Groupable? |
# |---|---|---|---|
# | Prefill (`P`) | `P PRE`, `P POST` | `P PROC` | No: each assignment names one request |
# | Decode (`D`) | `D PRE`, `D POST` | `D PROC` | Yes: assignments carry a list of request IDs |
#
# Grouping is therefore **not cloud-only**. Decode preprocessing and postprocessing can be
# grouped on the edge, while decode processing can be grouped on a cloud. A `D PROC` group
# must contain requests assigned to that same cloud.
#
# A group is also **not permanent**. It represents one stage of one decode iteration. After
# `D POST`, unfinished requests become eligible for their next token and may be regrouped.
# A request that reaches its hidden output length emits `FIN` and is absent from future groups.

# %% [markdown]
# ### Reading one assignment
#
# ```text
# E D PRE -1 3 7 12 19
# │ │  │   │ │ └────── request IDs in this group
# │ │  │   │ └──────── group size = 3
# │ │  │   └────────── required placeholder for edge decode work
# │ │  └────────────── preprocessing stage
# │ └───────────────── decode family
# └─────────────────── run on the edge server
# ```
#
# This starts one grouped decode-preprocessing task for requests `7`, `12`, and `19`.
# It does not mean “run from time 7 to time 19,” and `-1` is not a cloud ID.

# %% [markdown]
# ## 2. Inspect the workload suite
#
# Scenario JSON includes system parameters, scoring weights, a task-time table, and requests.
# `output_length` is judge-only truth: the local judge uses it to decide when to emit `FIN`,
# but the scheduler only sees `ARR request_id input_length`.

# %%
scenario_paths = sorted(SCENARIO_DIR.glob("*.json"))
scenarios = {path.stem: json.loads(path.read_text()) for path in scenario_paths}

pressure_by_name = {
    "official_worked_example": "calibration",
    "single_sanity": "one-request lifecycle",
    "two_cloud_parallel": "parallelism / reservations",
    "output_length_skew": "hidden output skew",
    "batch_friendly_burst": "decode grouping",
    "latency_sensitive_stream": "throughput vs latency",
    "link_bottleneck": "shared UP/DOWN queues",
    "prefill_preemption": "prefill layer chunking",
    "degenerate_one_layer": "minimum legal mechanics",
    "interpolation_missing_values": "task-time interpolation",
    "single_cloud_prefill_interleave": "adaptive prefill chunking",
    "slo_priority_collision": "SLO-aware urgency",
    "latency_weighted_slow_link": "latency-weighted link policy",
    "nonmonotonic_batch_table": "table-aware group size",
}

scenario_summary = []
for path in scenario_paths:
    data = scenarios[path.stem]
    requests = data["requests"]
    scenario_summary.append(
        {
            "scenario": data["name"],
            "K": data["system"]["K"],
            "S": data["system"]["S"],
            "requests": len(requests),
            "tokens": sum(request["output_length"] for request in requests),
            "w_tp": data["scoring"]["w_tp"],
            "w_c": data["scoring"]["w_c"],
            "pressure": pressure_by_name.get(data["name"], "general policy behavior"),
        }
    )

display_table(
    scenario_summary,
    [
        ("scenario", "Scenario"),
        ("K", "Clouds"),
        ("S", "Schedule cost"),
        ("requests", "Requests"),
        ("tokens", "Hidden output tokens"),
        ("w_tp", "Throughput weight"),
        ("w_c", "Latency weight"),
        ("pressure", "Designed to expose"),
    ],
)

# %% [markdown]
# ### Choose a scenario to study
#
# Change `SELECTED_SCENARIO_FILE`, rerun this cell, and then rerun the experiment cells below.

# %%
SELECTED_SCENARIO_FILE = "04_batch_friendly_burst.json"

selected_path = SCENARIO_DIR / SELECTED_SCENARIO_FILE
selected = json.loads(selected_path.read_text())

display(Markdown(f"### `{selected['name']}`\n\n{selected['description']}"))
display(Code(json.dumps({"system": selected["system"], "scoring": selected["scoring"]}, indent=2), language="json"))

request_preview = []
for request_id, request in enumerate(selected["requests"][:12]):
    request_preview.append(
        {
            "request_id": request_id,
            "arrival": request["arrival"],
            "input_length (visible)": request["input_length"],
            "output_length (hidden)": request["output_length"],
        }
    )
display_table(request_preview)
if len(selected["requests"]) > len(request_preview):
    print(f"Showing {len(request_preview)} of {len(selected['requests'])} requests.")

# %% [markdown]
# ## 3. Connect the model to the code
#
# We keep two distinct artifacts:
#
# - `scheduler_versions/v0_baseline.cpp` is the frozen, deliberately simple reference;
# - `main.cpp` is the current layer-7 submission and is identical to
#   `scheduler_versions/layered_scheduler.cpp` with its default `OPT_LEVEL=7`.
#
# The frozen baseline is a state machine plus three FIFO structures:
#
# - `pending_requests_`: arrived requests that do not yet have a cloud reservation;
# - `edge_ready_`: legal edge tasks ordered by when they became ready; and
# - `cloud_ready_[cloud]`: legal cloud tasks for each cloud.
#
# It adds one deliberate restriction: it reserves an entire cloud for a request
# from `P PRE` until `FIN`. The contest does not require that restriction. It makes the first
# implementation easy to reason about, but it leaves clouds idle while their reserved request
# is on the edge or waiting for a transfer.

# %%
baseline_source = (REPO_ROOT / "scheduler_versions/v0_baseline.cpp").read_text()
layered_source = (REPO_ROOT / "scheduler_versions/layered_scheduler.cpp").read_text()


def source_between(
    source: str, start_marker: str, end_marker: str, max_lines: int = 180
) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    snippet = source[start:end].rstrip()
    lines = snippet.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["// ... bounded notebook preview ..."]
    return "\n".join(lines)


display(Markdown("### Request states"))
display(
    Code(
        source_between(baseline_source, "enum class RequestState", "enum class TaskKind"),
        language="cpp",
    )
)

# %%
display(Markdown("### Baseline admission and edge dispatch"))
display(
    Code(
        source_between(
            baseline_source, "string dispatch_admission()", "string dispatch_cloud_task"
        ),
        language="cpp",
    )
)

# %%
display(Markdown("### The central dispatch decision"))
display(
    Code(
        source_between(
            baseline_source, "vector<string> dispatch_ready_work()", "void print_response"
        ),
        language="cpp",
    )
)

# %% [markdown]
# ### What makes this a baseline?
#
# The frozen v0 code intentionally does **none** of the following:
#
# - multiple active requests on one cloud;
# - load-aware cloud selection;
# - grouped decode tasks;
# - task-time-table-based batch selection;
# - SLO-aware task priority;
# - controlled waiting to form a better group;
# - layer-chunked prefill; or
# - indirect link-aware scheduling.
#
# That is useful experimentally: every later layer has one primary mechanism and a scenario
# designed to make that mechanism visible. The layered engine uses compile-time feature gates,
# so `OPT_LEVEL=4` contains layers 1 through 4 but none of layers 5 through 7.

# %% [markdown]
# ## 4. Understand the task-time table
#
# For prefill columns, the lookup size is the request's input length. For decode columns, it
# is the decode group size. Missing values (`-1`) are ignored and intermediate sizes are
# linearly interpolated by the local judge.

# %%
def task_rows_for(scenario_path: Path, scenario: dict[str, Any]) -> list[dict[str, float]]:
    if "task_times" in scenario:
        return scenario["task_times"]
    profile_path = scenario_path.parent / scenario["task_times_file"]
    return json.loads(profile_path.read_text())["task_times"]


task_rows = task_rows_for(selected_path, selected)
display_table(task_rows[:8])

# %%
TASK_COLUMNS = (
    "prefill_pre",
    "prefill_proc",
    "prefill_post",
    "decode_pre",
    "decode_proc",
    "decode_post",
)


def interpolate_duration(rows: list[dict[str, float]], column: str, size: int) -> float:
    points = sorted(
        (int(row["batch_size"]), float(row[column]))
        for row in rows
        if float(row[column]) >= 0
    )
    if not points:
        raise ValueError(f"No usable values for {column}")
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
    raise AssertionError("Interpolation should have returned")


interpolation_demo = [
    {
        "size": size,
        **{column: round(interpolate_duration(task_rows, column, size), 4) for column in TASK_COLUMNS},
    }
    for size in (1, 2, 4, 6, 8, 16)
]
display_table(interpolation_demo)

# %% [markdown]
# ### A first grouping estimate
#
# The following is a **local service-cost estimate**, not a complete scheduler simulation.
# For a decode group of size `b`, it adds:
#
# 1. the scheduling cost `S` for each of `D PRE`, `D PROC`, and `D POST`;
# 2. the interpolated task time for those three stages; and
# 3. one upload and one download for `b` decode items.
#
# It deliberately ignores queueing, overlap with other resources, and time spent waiting for
# requests to become group-compatible. Those effects are why we still need the dynamic judge.

# %%
def transfer_time_ms(system: dict[str, Any], item_count: int) -> float:
    size_bytes = item_count * int(system["bytes_per_token"])
    return float(system["latency_in_ms"]) + 8.0 * size_bytes / (
        float(system["bandwidth_gbps"]) * 1_000_000.0
    )


def estimated_decode_cycle_ms(
    system: dict[str, Any], rows: list[dict[str, float]], group_size: int
) -> float:
    compute = sum(
        float(system["S"]) + interpolate_duration(rows, column, group_size)
        for column in ("decode_pre", "decode_proc", "decode_post")
    )
    transfers = 2.0 * transfer_time_ms(system, group_size)
    return compute + transfers


candidate_sizes = [size for size in (1, 2, 4, 8, 16) if size <= len(selected["requests"])]
singleton_cycle = estimated_decode_cycle_ms(selected["system"], task_rows, 1)
group_estimates = []
for size in candidate_sizes:
    group_cycle = estimated_decode_cycle_ms(selected["system"], task_rows, size)
    group_estimates.append(
        {
            "group_size": size,
            "estimated cycle ms": round(group_cycle, 4),
            "ms per request": round(group_cycle / size, 4),
            "idealized throughput gain": f"{size * singleton_cycle / group_cycle:.2f}x",
        }
    )
display_table(group_estimates)

# %% [markdown]
# The largest currently ready group often minimizes service time per request, but that does
# **not** prove we should always wait for the largest possible group:
#
# - compatible requests may not be ready yet;
# - `D PROC` members must belong to the same cloud;
# - waiting increases request age and can violate TDR/TPOT targets;
# - a larger group consumes a resource for longer and may block urgent work;
# - shared-link queueing can dominate the isolated estimate; and
# - the task-time table itself may show weak or negative scaling at larger sizes.
#
# The correct loop is therefore: use the table to form a hypothesis, then use the dynamic
# judge to measure the complete policy.

# %% [markdown]
# ## 5. Run the baseline on one case
#
# The local judge sends startup data and event frames to the actual C++ executable. It accepts
# any legal policy decision and generates the resulting `TDN`, `XDN`, and `FIN` events. This is
# different from replaying one fixed transcript.

# %%
selected_result_path = BUILD_DIR / "notebook-selected-result.json"
run_checked(
    [
        "python3",
        "tools/local_judge.py",
        "--solver",
        str(BASELINE_SOLVER),
        "--scenarios",
        str(selected_path),
        "--json-out",
        str(selected_result_path),
    ]
)
selected_result = json.loads(selected_result_path.read_text())[0]
display_table([selected_result])

# %% [markdown]
# ### Reconstruct the score
#
# The score combines normalized throughput with an SLO-compliance component. Higher score and
# throughput are better; lower TDR, TPOT, distance, and elapsed time are better.

# %%
def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def reconstruct_score(result: dict[str, Any], scoring: dict[str, Any]) -> dict[str, float]:
    excess_tdr = max(0.0, (result["tdr"] - scoring["SLO1"]) / scoring["SLO1"])
    excess_tpot = max(0.0, (result["tpot"] - scoring["SLO2"]) / scoring["SLO2"])
    distance = math.hypot(excess_tdr, excess_tpot)
    throughput_component = clamp01(
        (result["throughput"] - scoring["tp_base"])
        / (scoring["tp_UB"] - scoring["tp_base"])
    )
    distance_base = scoring["dist_base"]
    waiting_component = (
        max(0.0, 1.0 - distance / distance_base)
        if distance_base > 0
        else (1.0 if distance == 0 else 0.0)
    )
    score = 1000.0 * (
        scoring["w_tp"] * throughput_component + scoring["w_c"] * waiting_component
    )
    return {
        "throughput component": throughput_component,
        "SLO distance": distance,
        "SLO component": waiting_component,
        "reconstructed score": score,
    }


score_parts = reconstruct_score(selected_result, selected["scoring"])
display_table([{key: round(value, 6) for key, value in score_parts.items()}])
assert math.isclose(
    score_parts["reconstructed score"], selected_result["score"], rel_tol=0, abs_tol=1e-7
)

# %% [markdown]
# ## 6. Run the complete scenario suite

# %%
suite_result_path = BUILD_DIR / "notebook-baseline-results.json"
run_checked(
    [
        "python3",
        "tools/local_judge.py",
        "--solver",
        str(BASELINE_SOLVER),
        "--scenarios",
        str(SCENARIO_DIR),
        "--json-out",
        str(suite_result_path),
    ]
)
suite_results = json.loads(suite_result_path.read_text())

display_table(
    [
        {
            "scenario": row["scenario"],
            "score": f"{row['score']:.3f}",
            "throughput": f"{row['throughput']:.6f}",
            "TDR": f"{row['tdr']:.3f}",
            "TPOT": f"{row['tpot']:.3f}",
            "elapsed": f"{row['elapsed']:.3f}",
        }
        for row in suite_results
    ]
)

# %% [markdown]
# ### Check reproducibility against the saved baseline

# %%
saved_baseline = {row["scenario"]: row for row in json.loads(BASELINE_SNAPSHOT.read_text())}
current_baseline = {row["scenario"]: row for row in suite_results}

comparison_rows = []
maximum_score_delta = 0.0
for scenario_name, expected in saved_baseline.items():
    actual = current_baseline[scenario_name]
    score_delta = actual["score"] - expected["score"]
    maximum_score_delta = max(maximum_score_delta, abs(score_delta))
    comparison_rows.append(
        {
            "scenario": scenario_name,
            "legal": actual["legal"],
            "score delta": f"{score_delta:+.9f}",
            "throughput delta": f"{actual['throughput'] - expected['throughput']:+.9f}",
        }
    )

display_table(comparison_rows)
assert all(row["legal"] for row in suite_results)
assert maximum_score_delta < 1e-6
print("Reproducibility check passed: frozen v0 results match baseline-v0.json.")

# %% [markdown]
# ## 7. Optimization ladder
#
# The current scheduler implements these changes cumulatively. Each registered version builds
# the same layered engine with a different `OPT_LEVEL`, which keeps every comparison attributable
# to one newly enabled policy layer.
#
# | Step | Implemented change | Primary scenarios | Expected signal |
# |---:|---|---|---|
# | 0 | FIFO singleton baseline | all | legal reference point |
# | 1 | Allow multiple unfinished requests per cloud | `two_cloud_parallel`, `output_length_skew` | less cloud idle time, lower elapsed time |
# | 2 | Assign new requests using current cloud load | `output_length_skew` | less reservation/load imbalance |
# | 3 | Group decode-ready work immediately | `batch_friendly_burst` | higher throughput and score |
# | 4 | Select group sizes from the task-time table | `nonmonotonic_batch_table`, interpolation | avoid groups whose per-item service rate is worse |
# | 5 | Add conservative SLO urgency and bounded waiting | `slo_priority_collision`, `latency_sensitive_stream` | protect aged requests without destroying throughput |
# | 6 | Split long `P PROC` work into layer pieces | `single_cloud_prefill_interleave` | let ready decode work interleave between pieces |
# | 7 | Add score- and link-aware ordering/group cost | `latency_weighted_slow_link` | improve TDR when latency dominates the score |
#
# The benchmark workbench measures both each version versus v0 and each layer versus the layer
# immediately before it. That second comparison is the cleanest local evidence for the effect
# of one feature gate.

# %%
registry = json.loads(REGISTRY_PATH.read_text())
display_table(
    [
        {
            "layer": version.get("layer", 0),
            "version": version["name"],
            "compile gate": ", ".join(version.get("compile_defines", [])) or "standalone",
            "description": version["description"],
        }
        for version in registry["versions"]
        if version["name"] != "working-tree"
    ]
)

# %% [markdown]
# ### Where the optimization decisions live
#
# These bounded excerpts are the decision points—not copies of the whole scheduler. Rerunning
# the notebook always reads the checked-in C++.

# %%
optimization_excerpts = [
    ("Load-aware cloud selection (layer 2)", "int choose_cloud()", "int best_group_size"),
    ("Table-aware group size (layer 4)", "int best_group_size", "bool should_wait_for_group"),
    ("Request urgency (layer 5)", "double request_urgency", "int edge_stage_rank"),
    ("Bounded waiting (layer 5)", "bool should_wait_for_group", "bool should_defer_prefill_admission"),
    ("Adaptive prefill chunks (layer 6)", "int choose_prefill_piece_end", "vector<Candidate> cloud_candidates"),
    ("Latency-weighted prefill ordering (layer 7)", "int take_link_aware_prefill_request", "double cloud_load_score"),
]
for title, start_marker, end_marker in optimization_excerpts:
    display(Markdown(f"#### {title}"))
    display(Code(source_between(layered_source, start_marker, end_marker, max_lines=90), language="cpp"))

# %% [markdown]
# ### Optimization experiment worksheet
#
# Copy this template into a new Markdown cell for each change:
#
# ```text
# Optimization:
# Hypothesis:
# Code path changed:
# Correctness invariant at risk:
# Primary scenario:
# Expected metric movement:
# Observed result:
# Interpretation:
# Keep, revise, or revert:
# ```

# %% [markdown]
# ## 8. Compare the current layer-7 scheduler with v0
#
# This compact comparison answers “did the accumulated policy help?” The companion benchmark
# notebook performs the more diagnostic v0 → v1 → ... → v7 comparison.

# %%
def safe_label(label: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", label).strip("-")


def run_policy_suite(label: str, executable: Path) -> list[dict[str, Any]]:
    executable = executable.resolve()
    if not executable.is_file():
        raise FileNotFoundError(executable)
    result_path = BUILD_DIR / f"notebook-{safe_label(label)}-results.json"
    run_checked(
        [
            "python3",
            "tools/local_judge.py",
            "--solver",
            str(executable),
            "--scenarios",
            str(SCENARIO_DIR),
            "--json-out",
            str(result_path),
        ]
    )
    return json.loads(result_path.read_text())


policy_results: dict[str, list[dict[str, Any]]] = {
    "baseline-v0": suite_results,
    "current-v7": run_policy_suite("current-v7", WORKING_SOLVER),
}

print("Loaded policies:", ", ".join(policy_results))

# %%
def comparison_against_baseline(
    baseline_rows: list[dict[str, Any]], candidate_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    baseline_map = {row["scenario"]: row for row in baseline_rows}
    candidate_map = {row["scenario"]: row for row in candidate_rows}
    rows = []
    for scenario_name, old in baseline_map.items():
        new = candidate_map[scenario_name]
        if not new.get("legal", False):
            rows.append({"scenario": scenario_name, "status": "ILLEGAL"})
            continue
        rows.append(
            {
                "scenario": scenario_name,
                "status": "legal",
                "score delta": f"{new['score'] - old['score']:+.3f}",
                "throughput %": f"{100 * (new['throughput'] / old['throughput'] - 1):+.1f}%",
                "TDR %": f"{100 * (new['tdr'] / old['tdr'] - 1):+.1f}%" if old["tdr"] else "n/a",
                "TPOT %": f"{100 * (new['tpot'] / old['tpot'] - 1):+.1f}%" if old["tpot"] else "n/a",
                "elapsed %": f"{100 * (new['elapsed'] / old['elapsed'] - 1):+.1f}%",
            }
        )
    return rows


for policy_name, results in policy_results.items():
    if policy_name == "baseline-v0":
        continue
    display(Markdown(f"### {policy_name} vs baseline-v0"))
    display_table(comparison_against_baseline(suite_results, results))

# %% [markdown]
# ## Checks
#
# These assertions verify the lab itself:
#
# - every registered scenario was discovered;
# - every baseline and current-policy interaction was legal;
# - the official calibration case reproduces 45 ms elapsed and TDR 30 ms;
# - the score formula reconstruction matched the judge; and
# - frozen v0 results matched the saved `baseline-v0` snapshot.

# %%
assert len(scenario_paths) >= 14
assert all(row["legal"] for row in suite_results)
assert all(row["legal"] for row in policy_results["current-v7"])
assert set(current_baseline) == set(saved_baseline)

official = current_baseline["official_worked_example"]
assert math.isclose(official["elapsed"], 45.0, abs_tol=1e-9)
assert math.isclose(official["tdr"], 30.0, abs_tol=1e-9)
assert math.isclose(official["tpot"], 0.0, abs_tol=1e-9)

run_checked(["make", "transcript-test"])
print("All notebook checks passed.")

# %% [markdown]
# ## Next steps
#
# Open `scheduler_benchmark_workbench.ipynb` next. Its incremental table tells us which exact
# layer moved which exact scenario. Use that evidence to tune one feature gate at a time:
#
# 1. inspect the target scenario and its score components;
# 2. review any scenario-level regression, even when the suite mean rose;
# 3. change one threshold or policy rule;
# 4. rerun both legality validation and the full version workbench; and
# 5. keep the change only when its tradeoff matches the supplied scoring weights.
#
# The local scenarios are deterministic mechanism tests, not a model of the official hidden
# workload distribution. A local win is evidence that a mechanism works under those inputs;
# it is not a guarantee of leaderboard improvement.
