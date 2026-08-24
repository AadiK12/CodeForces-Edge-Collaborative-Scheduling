# Layered Edge–Cloud Collaborative Scheduler

Runnable learning and optimization workspace for Codeforces 2251A, **Edge–Cloud
Collaborative Scheduling**.

`main.cpp` is the current layer-7 GNU++17 submission. The deliberately naive policy is frozen
separately as `scheduler_versions/v0_baseline.cpp`, so later experiments never rewrite their
reference point.

## Implemented policy layers

Every `vN` contains all earlier layers. Versions 1–7 compile the same
`scheduler_versions/layered_scheduler.cpp` source with `OPT_LEVEL=N`.

| Layer | Policy added | Isolation scenario |
|---:|---|---|
| 0 | FIFO singleton baseline with one reserved request per cloud | reference |
| 1 | Multiple unfinished singleton requests per cloud | `two_cloud_parallel` |
| 2 | Estimated-load-aware cloud assignment | `output_length_skew` |
| 3 | Immediate grouping of ready decode tasks | `batch_friendly_burst` |
| 4 | Task-table-aware group-size selection | `nonmonotonic_batch_table` |
| 5 | Conservative SLO urgency and bounded group waiting | `slo_priority_collision` |
| 6 | Adaptive, gap-free prefill processing chunks | `single_cloud_prefill_interleave` |
| 7 | Score- and shared-link-aware ordering/group cost | `latency_weighted_slow_link` |

The feature gates change policy decisions, not protocol legality. The dynamic local judge
validates every emitted assignment before any score comparison is interpreted.

## Build and validate

```bash
make                         # build current layer-7 scheduler
make test                    # frozen-v0 transcript tests + current dynamic suite
make sanitize                # undefined-behavior builds and legal runs
make benchmark               # current scheduler versus frozen-v0 snapshot
make notebooks-check         # regenerate and execute both notebooks
```

The main executable is `build/scheduler`; the frozen reference is `build/v0-baseline`.
`main.cpp` remains a self-contained Codeforces submission.

Exact transcript tests belong only to v0 because optimized policies can produce different
but equally legal schedules. All versions are instead checked with `tools/local_judge.py`, a
policy-independent local interactor that creates `TDN`, `XDN`, and `FIN` events from the
scheduler's legal choices and computes throughput, TDR, TPOT, elapsed time, and score.

## Notebooks

- `notebooks/edge_cloud_scheduling_lab.ipynb` teaches the model and protocol, connects the
  frozen and optimized C++ implementations, reconstructs the score, and compares v0 with v7.
- `notebooks/scheduler_benchmark_workbench.ipynb` compiles all registered layers, runs the
  same scenarios, validates legality and calculations, and shows absolute and incremental
  layer effects, target-scenario evidence, and regressions.

Generate or execute them with:

```bash
make notebook
make notebook-check
make benchmark-notebook
make benchmark-notebook-check
```

The Jupytext `.py` files beside the notebooks are the editable source of truth. Executed
`.ipynb` files are checked in as reader-facing results.

## Scenario suite and interpretation

The 14 deterministic cases under `scenarios/` cover the official worked example, basic
lifecycle legality, cloud parallelism, hidden output skew, batch-friendly work, latency-heavy
streams, collective-link pressure, prefill interleaving, a one-layer edge case, missing table
values/interpolation, an SLO-priority collision, slow-link latency pressure, and a deliberately
nonmonotonic batch table.

`benchmarks/baseline-v0.json` records v0's reference metrics. These local cases isolate
mechanisms; their unweighted mean is not an estimate of the official hidden-test distribution.
A layer is evaluated through its scenario-level score components and regressions, not only
through one aggregate number.

## Preserving another iteration

`scheduler_versions/registry.json` is the benchmark manifest. To snapshot a future
standalone `main.cpp` before changing it again:

```bash
python3 tools/register_scheduler.py \
  --name v8-experiment-name \
  --description "One-sentence policy description"
```

The registration tool refuses to overwrite an existing version.
