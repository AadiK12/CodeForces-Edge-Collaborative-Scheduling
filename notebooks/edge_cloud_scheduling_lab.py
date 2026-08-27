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
# - `main.cpp` is the current layer-20 engine with promoted v25/v27/v33/v41/v43/v53 revisions and is identical
#   to `scheduler_versions/layered_scheduler.cpp` with its default `OPT_LEVEL=20`.
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
# so `OPT_LEVEL=4` contains layers 1 through 4 but none of the later gates. The rejected learned
# layers remain reproducible, while the current submission follows the promoted v15 → v19 → v20
# terminal-stage branch.

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
# Versions 1–18 implement these changes cumulatively. Version 19 deliberately branches from v15,
# isolating its terminal-stage experiment from rejected layers 16–18; version 20 extends that branch
# backward through D PROC.
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
# | 8 | Track exact virtual resource/link finish times | `exact_wait_horizon` | avoid event waits that overshoot their budget |
# | 9 | Price D PRE cloud fanout and compatible cohorts | `cross_cloud_fanout` | reduce fixed UP latencies per group |
# | 10 | Add batching affinity to permanent cloud placement | `batch_aware_placement` | choose pack versus spread from the decode curve |
# | 11 | Predict TDR and next-token slack | `predicted_deadline_slack` | advance the most valuable overdue milestone |
# | 12 | Tie prefill pieces to decode events/deadlines | `chunk_deadline_collision` | reduce decode blocking without tiny pieces |
# | 13 | Use attained service and completed-output history | `attained_service_tail` | give likely-short/young streams a bounded opportunity |
# | 14 | Penalize injection into congested links | `downstream_backpressure` | drain downstream work under queue pressure |
# | 15 | Look through a hostile downstream decode curve | `one_token_lookahead` | avoid locally fast but end-to-end slow groups |
# | 16 | Score bounded counterfactual group candidates | `counterfactual_grouping` | compare complete next-token paths with a v15 fallback |
# | 17 | Fit the group-value coefficients offline | `learned_grouping_recovery` | retain only train-selected coefficients and audit holdout |
# | 18 | Test nonlinear group-feature interactions | `nonlinear_ranker_holdout` | accept the selected zero-interaction null result |
# | 19 | Simulate finite D POST queue clearance with known arrivals | `terminal_dpost_remainder`, `terminal_dpost_future_arrival` | enlarge only when modeled clearance and score both improve |
# | 20 | Roll D PROC through FIFO DOWN and finite D POST clearance | `terminal_dproc_clearance` | change only in the one-cloud regime the rollout fully models |
#
# The benchmark workbench measures both each version versus v0 and each layer versus its recorded
# predecessor. That comparison is the cleanest local evidence for the effect of one feature gate.

# %% [markdown]
# ### How the layers fit together
#
# Layers 1–18 are cumulative rather than unrelated schedulers; layer 19 branches from v15 and layer
# 20 extends that branch. At every event frame the scheduler follows the same correctness loop—
# consume all events, update state, identify free resources, and emit only legal work.
#
# | Decision | Layers that affect it | Question being answered |
# |---|---|---|
# | Cloud admission | 1, 2, 7, 10 | Which cloud should own a request, and should admission be deferred? |
# | Ready-task ordering | 5, 7, 8, 11, 14 | Which legal stage should use a free server next? |
# | Decode group formation | 3, 4, 5, 7, 9, 13, 15, 16, 17, 18, 19, 20 | Which members and size should share the next decode task? |
# | Prefill execution granularity | 6, 12 | Should one long `P PROC` run fully or expose deadline-aware interleaving points? |
# | Short-horizon prediction | 8, 11, 14, 15, 16, 19, 20 | What known resource, FIFO-link, and downstream costs follow this action? |
# | Offline policy calibration | 17, 18 | Which observable-feature weights survive train/holdout validation? |
#
# None of these layers predicts the hidden output length. They use only information already
# revealed by the protocol: arrival time, input length, cloud association, request state,
# ready queues, resource busy state, the supplied task-time table, scoring weights/SLOs, and
# known in-flight work.

# %% [markdown]
# ### Layer 0 — frozen FIFO singleton baseline
#
# **Limitation we start with.** The baseline reserves a cloud from one request's `P PRE` until
# that request's final `FIN`. It also sends every decode stage as a singleton group and runs the
# whole prefill-processing range `[0, num_layers)` in one task. This is intentionally stricter
# than the problem.
#
# **Intuition.** It is an excellent correctness reference because ownership is simple: one
# request, one cloud, one lifecycle. But a reserved cloud can sit idle while its request is on
# the edge or a shared transfer link. The remaining layers remove those artificial idle periods
# while preserving the real rule that a server executes at most one task at a time.
#
# **Why keep it forever?** Without a frozen v0, we could see that today's scheduler is “fast”
# but could not reproduce what changed. Exact transcript tests remain attached to this version;
# optimized schedules are checked for legality rather than identical command order.

# %% [markdown]
# ### Layer 1 — multiple active requests per cloud
#
# **Baseline bottleneck.** “One task running on a cloud” and “one unfinished request assigned to
# a cloud” are different constraints. Only the first is real. The baseline incorrectly couples
# them, so cloud compute goes idle whenever its one request moves through edge or transfer work.
#
# **Policy.** A cloud may own many unfinished requests, each with its own state, while its compute
# resource remains protected by one `cloud_busy` flag. New requests are assigned round-robin.
# Cloud-ready `P PROC` and `D PROC` stages wait in per-cloud queues; the cloud still dispatches
# only one assignment in a frame.
#
# **Why it helps.** This creates a pipeline. While request A is uploading or doing edge work,
# the same cloud can process request B. We increase the chance that every free cloud has legal
# work ready, which usually raises throughput and lowers total elapsed time.
#
# **Correctness invariants.** A request keeps the cloud chosen by `P PRE`; every `D PROC` group
# remains single-cloud; and a busy cloud never receives a second concurrent task.
#
# **Tradeoff.** Round-robin balances request counts, not work. Because output lengths are hidden,
# one cloud can accumulate long-lived decode streams while another receives short requests.
# Queueing can also worsen an individual request's TPOT even when total throughput improves.

# %% [markdown]
# ### Layer 2 — observable-load-aware cloud placement
#
# **Layer-1 bottleneck.** Two clouds with three requests each need not have equal work. Input
# lengths are visible, ready queues differ, and one cloud may already be busy. Pure round-robin
# ignores all of that.
#
# **Policy.** Before `P PRE`, estimate each cloud's outstanding work and choose the minimum:
#
# $$
# \text{load}(c) = \text{remaining busy time}
# + \text{known prefill work}
# + \text{ready decode work}
# + 0.35\,\text{active-request proxy}.
# $$
#
# The proxy prices each unfinished request as a fraction of one singleton `D PROC` service cost.
# It is deliberately modest because the true remaining output tokens are unknowable.
#
# **Why it helps.** The first three terms route visible work away from a cloud that cannot serve
# it soon. The active-request term prevents a cloud with little currently-ready work—but many
# requests temporarily on the edge or links—from looking falsely empty.
#
# **Tradeoff.** This is an estimate, not clairvoyance. A request with one hidden token and a
# request with one thousand hidden tokens look the same before `FIN` evidence arrives. The
# coefficient can therefore under- or over-price future decode load, and placement is permanent
# because requests cannot migrate clouds later.

# %% [markdown]
# ### Layer 3 — immediately group compatible decode work
#
# **Singleton bottleneck.** Every task pays scheduling overhead `S`. If eight ready requests run
# as eight singleton `D PROC` tasks, the cloud pays `S` eight times. A group pays it once and may
# also receive a sublinear task duration from the supplied table.
#
# **Policy.** When a decode resource becomes free, group all compatible requests that are ready
# *right now*:
#
# - `D PRE` and `D POST` may combine requests from different clouds because they run on edge `E`;
# - `D PROC` combines only requests assigned to that particular cloud;
# - the group lasts for one stage of one decode iteration—membership is recalculated later.
#
# **Why it helps.** Grouping amortizes `S` and converts many queue operations into one service
# interval. In a synchronized burst this can produce a large throughput gain and much smaller
# token gaps.
#
# **Why “immediate” matters.** This layer does not wait for a hypothetical future member. It
# captures batching efficiency without yet risking deliberate idle time.
#
# **Tradeoff.** “All ready requests” is not automatically the best size. A large group can occupy
# the edge/cloud longer, delay urgent work, and perform poorly if the task-time table becomes
# inefficient at larger batch sizes. That motivates layer 4.

# %% [markdown]
# ### Layer 4 — task-table-aware group size
#
# **Layer-3 bottleneck.** The largest ready group minimizes the number of assignments, but the
# supplied duration curve can be nonmonotonic. If `T(8)` is much more than twice `T(4)`, two
# groups of four can beat one group of eight despite paying `S` twice.
#
# **Policy.** For each decode stage independently, choose the currently available size `b` that
# maximizes local service rate:
#
# $$
# \text{rate}(b) = \frac{b}{S + T_{\text{stage}}(b)}.
# $$
#
# Candidates include size 1, all currently ready members, and task-table breakpoints plus their
# immediate neighbors. Missing `-1` entries are ignored and usable values are interpolated.
# Smaller groups win exact rate ties, limiting unnecessary convoy size.
#
# **Why it helps.** The choice comes from the machine's supplied performance curve rather than
# an assumption that batching always scales. The `nonmonotonic_batch_table` case intentionally
# makes size 8 bad so this layer can demonstrate choosing efficient groups of 4.
#
# **Tradeoff.** This optimizes one stage's local members-per-millisecond, not the complete request
# network. It does not know future arrivals and may leave a remainder group. Queueing, link
# contention, and request SLOs can make the globally best decision differ from the local rate.

# %% [markdown]
# ### Layer 5 — SLO-aware urgency and tightly bounded waiting
#
# This layer addresses two opposite mistakes: always following FIFO when a request is already
# late, and always dispatching immediately when a nearly complete efficient group is about to
# become ready.
#
# **Urgency policy.** Normalize observed age by the relevant target:
#
# $$
# u_{\text{prefill}} = \frac{\text{now} - \text{arrival}}{\text{SLO1}},\qquad
# u_{\text{decode}} = \frac{\text{now} - \text{decode-clock start}}{\text{SLO2}}.
# $$
#
# Under strongly latency-weighted scoring (`w_c > 0.8`), tasks with `u >= 1` may move ahead of
# ordinary FIFO work. Otherwise ready sequence remains the primary order. This conservative gate
# avoids turning every small age difference into priority churn.
#
# **Controlled-wait policy.** Waiting is considered only when throughput weight is at least
# `0.95`, a known future event will wake the scheduler, the desired table-aware group is larger
# than the current group, the oldest member has consumed less than half its TPOT budget, and the
# elapsed wait is inside a small SLO2-derived budget. `D POST` is never held for batching because
# it is already the final step that reveals progress or `FIN`.
#
# **Why it helps.** Urgency protects requests near/over an SLO boundary; bounded waiting can trade
# a little idle time for enough additional members to amortize `S`. The supplied scoring weights
# decide which behavior is even eligible.
#
# **Tradeoff.** The protocol provides event-driven wakeups, not self-set timers. The next event
# can occur later than the nominal wait budget, so waiting must remain narrow. Priority also
# changes who waits rather than eliminating work; improving TPOT for one request can delay another.

# %% [markdown]
# ### Layer 6 — adaptive, gap-free prefill chunks
#
# **Long-task bottleneck.** A legal full `P PROC 0 num_layers` can occupy one cloud for a long
# interval. Tasks cannot be preempted after dispatch, so decode work becoming ready one moment
# later must wait for the entire prefill.
#
# **Policy.** For models with more than eight layers, split `P PROC` into contiguous pieces only
# when the same cloud has competing decode or prefill work. Piece size targets roughly:
#
# $$
# \max\left(4S,\ \min(0.25\,\text{SLO1},\ 0.5\,\text{SLO2})\right)
# $$
#
# milliseconds of processing, converted proportionally into a number of model layers. Every
# piece starts exactly where the previous one ended; the final end is `num_layers`.
#
# **Why it helps.** Chunk boundaries are scheduling opportunities. After one piece completes,
# the cloud can run ready `D PROC` work before resuming prefill, reducing head-of-line blocking
# without violating the no-preemption rule.
#
# **Tradeoff.** Every piece pays `S`. Chunks that are too small destroy throughput; chunks that
# are too large recreate the blocking problem. We therefore keep full prefills for small models
# or when there is no competing work, and require a target of at least `4S`.

# %% [markdown]
# ### Layer 7 — score- and shared-link-aware scheduling
#
# **Compute-only bottleneck.** The clouds are separate compute resources, but all of them share
# collective FIFO `UP` and `DOWN` links. A placement or group that looks efficient on compute can
# inject a large transfer ahead of latency-sensitive traffic and dominate TDR/TPOT.
#
# **Policy components.** This layer is intentionally conditional:
#
# 1. **Transfer-aware group cost.** For `D PRE` and `D PROC`, group-size service cost also includes
#    an estimated transfer time, so compute batching does not appear free on a slow link.
# 2. **Latency-weighted prefill ordering.** When latency weight exceeds throughput weight, inspect
#    a bounded FIFO window and prefer short prefill transfers. Request age subtracts from that
#    cost, preventing large old requests from being ignored forever.
# 3. **Downstream stage preference under link pressure.** On constrained links, edge ordering
#    favors `D POST → P POST → D PRE → P PRE`, while clouds favor ready `D PROC` over new `P PROC`.
#    This tends to finish already-invested work before admitting another large transfer.
# 4. **Narrow admission pacing.** Under strongly latency-weighted scoring, a very young prefill
#    may be deferred when the existing upload backlog already exceeds the TDR target and another
#    known event will wake the scheduler.
#
# When throughput weight dominates, admission preserves FIFO; shortest-transfer-first is not a
# universal rule.
#
# **Why it helps.** TDR-sensitive workloads benefit from completing small/advanced requests before
# a huge upload monopolizes the FIFO link. Incorporating transfer cost also prevents selecting a
# group solely because its compute curve looks fast.
#
# **Tradeoff.** Shortest-transfer-first can postpone large requests, and prioritizing first-token
# readiness can make inter-token gaps worse. The `latency_weighted_slow_link` result demonstrates
# exactly that trade: a large TDR improvement raises score under its weights even though TPOT
# worsens. This is why the layer is gated by scoring emphasis rather than always enabled equally.

# %% [markdown]
# ### The overall intuition in one sentence
#
# Keep every resource doing useful legal work, amortize fixed overhead when compatible work is
# ready, size batches from measured curves, create safe interleaving points around long tasks,
# and spend latency only when the scoring weights say the throughput benefit is worth it.
#
# The policies are heuristics because future arrivals and output lengths are hidden. Their value
# must be judged scenario by scenario, including regressions—not inferred from one aggregate mean.

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
    ("Load-aware cloud selection (layers 2/10)", "double cloud_load_score", "double observed_request_urgency"),
    ("Table-aware group size (layer 4)", "int best_group_size", "bool should_wait_for_group"),
    ("Request urgency (layer 5)", "double request_urgency", "int edge_stage_rank"),
    ("Bounded waiting (layer 5)", "bool should_wait_for_group", "bool should_defer_prefill_admission"),
    ("Adaptive prefill chunks (layer 6)", "int choose_prefill_piece_end", "vector<Candidate> cloud_candidates"),
    ("Latency-weighted prefill ordering (layer 7)", "int take_link_aware_prefill_request", "double cloud_load_score"),
    ("Exact virtual timelines (layer 8)", "void enqueue_transfer", "void complete_transfer"),
    ("Fanout-aware D PRE groups (layer 9)", "vector<int> choose_d_pre_members", "bool should_wait_for_group"),
    ("Predicted path slack (layer 11)", "double estimated_prefill_path", "double action_service_time"),
    ("Attained-service selection (layer 13)", "double expected_remaining_tokens", "double estimated_prefill_path"),
    ("Backpressure and lookahead (layers 14/15)", "double downstream_pressure", "double decode_member_value"),
    ("Counterfactual grouping (layer 16)", "vector<int> bounded_candidate_group_sizes", "vector<int> choose_d_pre_members"),
    ("Learned group value (layers 17/18)", "double counterfactual_group_value", "vector<int> choose_counterfactual_decode_group"),
    ("Finite D POST queue clearance (layer 19)", "vector<int> terminal_dpost_members", "bool should_wait_for_group"),
    ("D PROC-to-D POST clearance (layer 20)", "vector<int> terminal_dproc_members", "vector<int> legacy_d_pre_members"),
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
# ## 8. Compare the current promoted v53 scheduler with v0
#
# This compact comparison answers “did the accumulated policy help?” The companion benchmark
# notebook performs the more diagnostic registered-lineage comparison through v20. Layers 16–18
# remain rejected experiments; this section evaluates the layer-20 terminal branch plus the
# promoted v25 resumed-prefill guard, v27 D POST threshold, v33 stage-correct cohort wait, and
# v41's fresh-audited coherent decode cohort gate, v43's bounded P POST cohort seed, and v53's
# sealed global coherent-DPOST gate. v53 groups the final D POST only when one D PRE group contains
# every known unfinished request and public timing tables bound both transfer cost and predicted
# member-ready dispersion. It never uses hidden output lengths.

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
    "current-v53": run_policy_suite("current-v53", WORKING_SOLVER),
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
assert len(scenario_paths) >= 29
assert all(row["legal"] for row in suite_results)
assert all(row["legal"] for row in policy_results["current-v53"])
assert set(saved_baseline).issubset(current_baseline)

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
