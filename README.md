# Edge–Cloud Collaborative Scheduling

Correctness-first GNU++17 baseline for Codeforces 2251A, **Edge–Cloud Collaborative
Scheduling**.

## Baseline policy

This version intentionally avoids every scoring optimization:

- Requests wait in arrival-order FIFO.
- Each cloud reserves at most one unfinished request.
- The oldest waiting request is assigned to the first cloud reservation that becomes free.
- A reservation lasts from `P PRE` dispatch through `FIN`.
- Prefill uses one complete piece: `[0, num_layers)`.
- Every decode task is a singleton group.
- The edge and each cloud dispatch legal work in FIFO-ready order.
- No task duration, score parameter, future timestamp, or future request is predicted.
- Transfers are never scheduled by the participant; state advances on `XDN`.

This is more restrictive than the contest model. A cloud may be computationally idle while
its reserved request is using the edge or a shared transfer queue. That wasted capacity is
deliberate and gives later policies a clear improvement target.

## Request state machine

```text
ARR / waiting for a cloud
  -> P PRE running
  -> waiting for prefill UP
  -> P PROC ready/running
  -> waiting for prefill DOWN
  -> P POST ready/running
  -> D PRE ready/running
  -> waiting for decode UP
  -> D PROC ready/running
  -> waiting for decode DOWN
  -> D POST ready/running
  -> FIN, or the next D PRE
```

The scheduler reads an entire event frame before dispatching. A server is marked free only
by its `TDN`. The final `D POST` transition is resolved after all events in the frame so
`FIN` and `TDN` are safe in either line order.

## FIFO behavior

The edge has one FIFO-ready stream containing `P POST`, `D PRE`, and `D POST` work. An
arrived request waiting for admission competes using its arrival-ready sequence when a cloud
reservation is available. There is no stage priority.

Each cloud has a FIFO-ready stream containing `P PROC` and `D PROC`. Because the baseline
reserves one request per cloud, it normally contains at most one ready task.

## Build and test

```bash
make
make test
make sanitize
make benchmark
```

The executable is written to `build/baseline`. `main.cpp` is a self-contained Codeforces
submission.

## Learning notebook

`notebooks/edge_cloud_scheduling_lab.ipynb` is a runnable tutorial and experiment log tied to
the real scheduler, scenarios, local judge, and benchmark snapshot. It explains the protocol,
shows bounded excerpts from `main.cpp`, models the decode-grouping tradeoff, executes the
baseline, reconstructs the score, and provides a comparison harness for future policies.

Regenerate the notebook from its Jupytext source or execute it top-to-bottom with:

```bash
make notebook
make notebook-check
```

The `uv` commands in those targets use isolated notebook tooling; the scheduler itself keeps
its existing GNU++17 and Python-standard-library requirements.

`notebooks/scheduler_benchmark_workbench.ipynb` is the companion version-comparison notebook.
It rebuilds every entry in `scheduler_versions/registry.json`, runs the same dynamic scenarios,
validates the metrics, and shows suite summaries, per-scenario scores, deltas, and regression
alerts. Generate or execute it with:

```bash
make benchmark-notebook
make benchmark-notebook-check
```

Preserve the current `main.cpp` as a named iteration with `tools/register_scheduler.py`; the
script refuses to overwrite an existing version.

The transcript harness currently checks:

- the official one-request worked example; and
- a two-cloud flow covering FIFO admission, concurrent edge/cloud dispatch, reuse only after
  `FIN`, a third waiting request, and reversed `FIN`/`TDN` line order.

These tests verify deterministic protocol output and state transitions. They are not a
replacement for the official interactor or preliminary tests.

## Policy-independent scenario suite

`tools/local_judge.py` is a dynamic local interactor. Unlike a fixed transcript, it accepts
whatever legal decisions a scheduler makes, generates the resulting future events, validates
the protocol, and calculates throughput, TDR, TPOT, elapsed time, and the normalized score.

Run every scenario against a scheduler with:

```bash
python3 tools/local_judge.py --solver build/baseline --scenarios scenarios
```

The checked-in scenarios cover:

- exact reproduction of the official worked example;
- a single-request lifecycle sanity check;
- two-cloud parallel execution and FIFO reservation;
- hidden output-length skew;
- a high-overhead, batch-friendly burst;
- a latency-sensitive arrival stream;
- a collective-link bottleneck;
- long-prefill preemption pressure;
- `K=1` and `num_layers=1` degeneracy; and
- unsorted task rows, interpolation, and `-1` missing values.

`benchmarks/baseline-v0.json` records this policy's reference metrics. `make benchmark` runs
the current scheduler and prints score and metric deltas against that snapshot. Throughput
increases are good; TDR, TPOT, and elapsed-time decreases are good.

## Planned optimization path

1. Allow multiple unfinished requests to be assigned to each cloud.
2. Keep otherwise-idle clouds busy with per-cloud FIFO work.
3. Add load-aware cloud assignment.
4. Add immediate decode grouping.
5. Derive batch sizes from the supplied task-time table.
6. Add SLO-aware priorities and controlled waiting.
7. Add prefill chunking.
