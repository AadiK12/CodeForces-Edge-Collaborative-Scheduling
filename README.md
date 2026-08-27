# Layered Edge–Cloud Collaborative Scheduler

Runnable learning and optimization workspace for Codeforces 2251A, **Edge–Cloud
Collaborative Scheduling**.

`main.cpp` is the validated layer-20 GNU++17 engine plus the promoted v25, v27, v33, v41, v43,
v53, v69, and v83 safety revisions. Rejected counterfactual and learned policies remain preserved as layers 16–18, while
every post-layer-20 change was promoted only after broad, adversarial, and sealed-holdout evidence.
The naive policy is frozen as
`scheduler_versions/v0_baseline.cpp`, so later experiments never rewrite their reference point.

## Implemented policy layers

Versions 1–18 are cumulative. Version 19 deliberately returns to the promoted v15 lineage; version
20 extends that branch through the preceding cloud stage. All compile from
`scheduler_versions/layered_scheduler.cpp` with `OPT_LEVEL=N`.

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
| 8 | Exact virtual resource/link timelines and event-bounded waits | `exact_wait_horizon` |
| 9 | Fanout- and decode-cohort-aware group formation | `cross_cloud_fanout` |
| 10 | Conservative batch-aware cloud placement | `batch_aware_placement` |
| 11 | Predicted TDR/next-token slack and marginal progress | `predicted_deadline_slack` |
| 12 | Event- and deadline-aware prefill chunks | `chunk_deadline_collision` |
| 13 | Attained-service scheduling with online output survival estimates | `attained_service_tail` |
| 14 | Collective-link backpressure | `downstream_backpressure` |
| 15 | Bounded one-token downstream lookahead | `one_token_lookahead` |
| 16 | Bounded counterfactual grouping with a v15 fallback | `counterfactual_grouping` |
| 17 | Offline-fitted conservative group ranker | `learned_grouping_recovery` |
| 18 | Optional nonlinear ranker interactions; selected as zero | `nonlinear_ranker_holdout` |
| 19 | Remainder-aware terminal D POST enlargement with a v15 fallback | `terminal_dpost_remainder`, `terminal_dpost_future_arrival` |
| 20 | Stage-correct D PROC → DOWN → D POST clearance with a v19 fallback | `terminal_dproc_clearance` |

Post-layer revisions keep `OPT_LEVEL=20` and change only narrowly modeled decisions:

- v25 lets an older, latency-sensitive **resumed** `P PROC` chunk run before `D PROC` only under
  measured link pressure and a four-to-one prefill/decode service imbalance.
- v27 lowers the terminal D POST modeled-score margin to 0.1 while retaining a 0.5% clearance
  improvement requirement. Latency-dominated tests keep the older 0.98/0.5 thresholds.
- v33 hardens v29's known-cohort wait: it counts only members available at the earliest public
  wake-up, prices the group size reachable at that event, rejects curve cliffs, and spends at most
  0.1% of modeled batching savings on waiting.
- v38 preserves one D PRE cohort through its parallel cloud work and reunites exactly that cohort
  for D POST. The barrier is enabled only with at least two clouds, latency-dominant scoring,
  scheduling overhead no smaller than the three singleton decode-stage times combined, and a
  one-token transfer no larger than 10% of scheduling overhead.
- v41 widens only that last transfer cap to 30%. A 40% candidate lost 7.054 points on training;
  the frozen 30% candidate added one validation win and two wins on a new 256-case audit, with no
  losses.
- v43 lets one ready P POST complete a known initial decode cohort before D PRE only when public
  D PRE table costs show at least a 2% edge-clearance improvement. It added one validation win and
  one win on a new 256-case audit, with no losses.
- v53 seals a dynamic coherent D POST cohort only when one D PRE group contains every known
  unfinished request, every member becomes an active decode request, public tables predict positive
  launch-amortization savings at least as large as transfer cost and at least half the merged D POST
  cost, and predicted ready-time dispersion is
  no more than 15% of those savings. This avoids assuming any hidden output length: the predicted
  dispersion is only a public one-token clearance bound, while the exact cohort membership is checked
  again before D POST is emitted.
- v69 adds a sparse initial-decode barrier only for high-latency, multi-cloud, monotonic public
  decode tables when the initial known cohort is still almost entirely waiting at D PRE.
- v83 uses an offline-trained, quantized 18→8→6 residual network at the first state where a wider
  coherent-DPOST policy can disagree with v69. It sees only public queue, table, link, cohort, and
  observed-progress features. If its predicted advantage is at most 0.60, it emits the exact v69
  action; otherwise it selects a public ready-dispersion threshold between 0.15 and 1.0.

The feature gates change policy decisions, not protocol legality. The dynamic local judge
validates every emitted assignment before any score comparison is interpreted.

## Build and validate

```bash
make                         # build current layer-20 scheduler
make test                    # frozen-v0 transcript tests + current dynamic suite
make sanitize                # undefined-behavior builds and legal runs
make benchmark               # current scheduler versus frozen-v0 snapshot
make notebooks-check         # regenerate and execute all notebooks
make grouping-scenarios      # regenerate deterministic train/holdout workloads under build/
make broad-scenarios         # regenerate the 256/128/128 broad train/validation/holdout corpus
make grouping-tune           # rerun offline policy search and holdout audit
make submission-check        # strip level 20 and prove exact trace equivalence
make adversarial-dpost-search # regenerate/search deterministic D POST counterexamples
make adversarial-dpost-audit  # explicitly open the separately seeded holdout split
make adversarial-dproc-search # search D PROC-to-D POST disagreement cases
make adversarial-dproc-audit  # explicitly open its separately seeded holdout split
make adversarial-dpre-search  # search the unpromoted v21 full-path D PRE experiment
make adversarial-dpre-audit   # audit the frozen v21 experiment on its sealed holdout
```

The neural development pipeline is reproducible with
`tools/generate_neural_policy_scenarios.py`, `tools/build_neural_policy_dataset.py`, and
`tools/train_neural_policy.py`. Training requires Python with NumPy; the submitted C++ policy does not.

The main executable is `build/scheduler`; the frozen reference is `build/v0-baseline`.
`tools/build_submission.py` emits `submission.cpp` with inactive experimental, legacy-priority,
pre-v20, and revision-specific code removed. This keeps the readable research engine intact while
enforcing the 65,535-character submission limit. It also performs deterministic, token-aware
identifier compaction after protecting string literals. The current v83 artifact is 65,372
characters, leaving 163 characters of headroom. Its compact artifact matched all 29 standard
scenario traces and all 38 learned-policy-changing traces from the final independent audit.

Exact transcript tests belong only to v0 because optimized policies can produce different
but equally legal schedules. All versions are instead checked with `tools/local_judge.py`, a
policy-independent local interactor that creates `TDN`, `XDN`, and `FIN` events from the
scheduler's legal choices and computes throughput, TDR, TPOT, elapsed time, and score.

## Notebooks

- `notebooks/edge_cloud_scheduling_lab.ipynb` teaches the model and protocol, connects the
  frozen and optimized C++ implementations, reconstructs the score, and compares v0 with v20.
- `notebooks/scheduler_optimization_guide.ipynb` explains every optimization independently,
  connects intuition to real source, runs each adjacent layer pair on its isolation case, and
  explains why the learned variants remain experimental.
- `notebooks/scheduler_benchmark_workbench.ipynb` compiles all registered layers, runs the
  same scenarios, validates legality and calculations, and shows absolute and incremental
  layer effects, target-scenario evidence, and regressions.

Generate or execute them with:

```bash
make notebook
make notebook-check
make optimization-notebook
make optimization-notebook-check
make benchmark-notebook
make benchmark-notebook-check
```

The Jupytext `.py` files beside the notebooks are the editable source of truth. Executed
`.ipynb` files are checked in as reader-facing results.

## Scenario suite and interpretation

The 29 deterministic cases under `scenarios/` cover the official worked example, basic
lifecycle legality, cloud parallelism, hidden output skew, batch-friendly work, latency-heavy
streams, collective-link pressure, prefill interleaving, a one-layer edge case, missing table
values/interpolation, an SLO-priority collision, slow-link latency pressure, and a deliberately
nonmonotonic batch table, exact wait horizons, cloud fanout, pack-versus-spread placement,
predicted deadline slack, attained-service scheduling, downstream backpressure, and bounded
one-token lookahead, a synchronized 8192-token scheduler-CPU stress burst, counterfactual
grouping, learned-policy recovery, a nonlinear-ranker holdout audit, a terminal D POST remainder,
and a future-arrival regression fixture, plus stage-correct terminal D PROC clearance.

`tools/generate_grouping_scenarios.py` creates 18 training and 12 holdout workloads spanning six
families. `tools/tune_grouping_policy.py` performs deterministic black-box policy search on the
training split, evaluates the selected model only afterward on holdout, and records the audit in
`benchmarks/learned-grouping-policy.json`. The exported v17 policy improved one training case but
regressed one holdout case; v18's selected nonlinear interaction weights were all zero. Therefore
neither learned layer is enabled in the promoted `main.cpp` branch.

`tools/generate_broad_scenarios.py` creates a hash-locked 256-case train split, 128-case visible
validation split, and 128-case sealed holdout spanning arrival shapes, bottleneck stages, curve
families, cloud counts, link regimes, and score weights. The final resumed-prefill guard was neutral
on a 1,024-case search and won one of 512 holdout cases without a loss. The guarded D POST threshold
won one case in each 256-case dedicated split without a loss. The stage-correct cohort wait was
neutral on its 512-case search and won two of 256 holdout cases without a loss. The combined policy
was neutral on the fresh 1,024-case search and won one of 128 formerly sealed broad cases without a
loss. These paired deltas are promotion evidence, not an estimate of the official hidden score.

The v38 coherent-decode gate was neutral on all 256 generated training cases. It won 2 of 128
validation cases and 2 of 128 separately seeded holdout cases, with no losses in either split. On
the frozen 29-case suite it changed one case, improving it by 105.991 points; the other 28 tied.
The frozen-suite mean moved from 674.403 for v33 to 678.057 for v38. These are deterministic local
measurements, not a claim that the official score will exceed 700.

The v41 threshold sweep compared 20%, 30%, and 40% transfer caps on train/validation. The 30% cap
added one +6.031 validation win over v38 without a loss; 40% caused a -7.054 training regression.
After freezing 30%, a new independently seeded 256-case audit produced two wins (+31.942 and
+38.897), 254 ties, and no losses. v41 is therefore the current coherent-decode revision.

The v43 P POST cohort seed was neutral on all 256 training cases, added one +0.030 validation win,
and then produced one +1.872 win with 255 ties on a new independently seeded 256-case audit. It
also improves the frozen batch-placement fixture by 2.711 points. The current frozen-suite mean is
678.151. These small paired gains justify the narrow reorder but do not establish a hidden score.

The first dynamic coherent-DPOST attempts were intentionally not promoted. v50's prefill-cohort
wait reduced the mean, and v51's link-admission fairness caused downstream regressions because
preventing one locally inconvenient transfer could idle the shared FIFO link or delay the request
that unlocks the next stage. A looser v52 coherent-cohort rule also lost 54.230 points on one broad
audit case: its selected D PRE group was not the entire known unfinished workload, so an excluded
request invalidated the predicted downstream clearance order.

v53 adds that missing global-cohort invariant and then freezes the rule before a new audit. Against
v43 it produced 2 wins / 27 ties / 0 losses on the frozen suite, 1 / 255 / 0 on broad training,
1 / 127 / 0 on validation, and 3 / 253 / 0 on a new independently seeded 256-case audit. The frozen
mean moved from 678.151 to 679.836; the changed cases were `batch_aware_placement` (+2.020) and
`nonlinear_ranker_holdout` (+46.836). The first 22 cases average 706.915, but the full 29-case mean
is still below 700. These are local paired measurements, not an official-score estimate.

The v83 residual network was trained from whole-run counterfactual score deltas at the first
observable state where a wider coherent-DPOST rule could disagree with v69. Two less-conservative
models were rejected after independent audits exposed tail losses. The frozen 0.60-margin model
then produced 38 wins, 1,498 ties, and no losses on a new 1,536-scenario audit seeded at
827,703,000, with mean score delta +0.530 and maximum gain +118.606. Scheduler CPU averaged
33.69 ms per scenario for v83 versus 33.70 ms for v69. This supports a locally meaningful candidate,
not a prediction of the official hidden score or workload distribution.

The v84-v88 research branch tests the next structural ideas without silently promoting them.
v84 uses a dynamic program to propose the first group of a whole-ready-queue D POST partition,
but the existing full-path gate could not prevent 2 losses in 256 broad training cases. v85 records
token-age exposure and completion counts and replaces the completed-sample mean with a
Gittins-style completion-probability-per-token index. Its 64-exposure guard produced 1 win, 254
ties, and 1 tiny loss on broad training, then tied all 128 validation cases, so it remains disabled.
The broad v86 three-action SLO-margin rollout and the latency-only v87 guard both regressed the
frozen suite because locally attractive stage orders delayed pipeline unlocks. v88 instead trains
a same-size quantized student against lower-confidence targets formed from identical public states
across hidden-output worlds. After fixing its abstention path to preserve v83 and freezing a 0.50
confidence margin, the end-to-end C++ policy produced 17 wins / 1,519 ties / 0 losses on development
training and 6 / 378 / 0 on validation. A newly seeded, hash-recorded 1,536-world audit then found
24 wins / 1,511 ties / 1 loss, mean delta +0.102 and worst delta -0.990. That one loss rejects v88
under the zero-loss promotion rule, so `main.cpp` and `submission.cpp` remain v83.

`tools/train_robust_policy_portfolio.py` reproduces the v88 lower-confidence training pass. It
groups rows by the exact observable feature vector, penalizes actions whose score varies across
hidden worlds, chooses one confidence margin jointly across train and validation, and exports a
model only after checking every chosen world-level counterfactual. As with v83, that offline check
is a candidate-generation step rather than promotion evidence. Run it with
`make robust-policy-train`; the separate end-to-end evidence is in
`benchmarks/further-optimization-experiments.json`.

`tools/adversarial_dpost_test.py` creates a deterministic search pool plus a separately seeded,
hash-checked holdout pool. The final v19 policy produced two wins and no losses on its 48-case
search pool; the fresh 24-case audit was all ties. That supports legality and conservative
fallback behavior, but did not justify promotion by itself because the fresh audit showed no score
upside. It was later retained as the safe terminal foundation of the positively audited v20 branch.

`tools/adversarial_dproc_test.py` similarly separates implementation-guiding search pools from
hash-checked audit pools. Early v20 candidates exposed multi-cloud and hostile-downstream
regressions. The frozen policy therefore acts only for one-cloud, throughput-dominant workloads
whose local and downstream curves pass conservative safety checks. Its fresh 128-case audit
produced one win worth 12.383 points, 127 ties, and no losses, justifying promotion over v19.

The rejected v21 experiment evaluates D PRE through the complete token path. Its first search found
large gains, but a broader search also found losses up to 28.316 points when identical observable
actions faced different hidden remaining output lengths. Replacing a sum-of-stage-times objective
with the maximum pipelined resource cost fixed a concrete 11.459-point counterexample. The frozen
revision then produced 0 wins, 511 ties, and 1 loss worth 0.526 points on a fresh 512-case holdout.
The v21 source and audit evidence remain separate from the promoted engine and unregistered.

Later unregistered experiments remain isolated for the same reason. Pending-prefill packing in v22
could not observe whether paired streams would overlap long enough; v23's P POST synchronization
retained tail regressions, while its separately isolated D POST wait became v29 and was then
hardened into the stage-correct v33 revision; and v24 recovered a frozen
link-constrained ordering fixture but failed a broader dedicated burst pool. The rejected pieces
remain outside `main.cpp`; only v23's separately audited D POST idea survives in guarded v33 form.
The always-on coherent barrier in v36 also remains rejected because its tail waiting caused broad
regressions; v38 keeps only the narrow public-parameter regime that passed paired validation.

`benchmarks/baseline-v0.json` records v0's reference metrics. These local cases isolate
mechanisms; their unweighted mean is not an estimate of the official hidden-test distribution.
A layer is evaluated through its scenario-level score components and regressions, not only
through one aggregate number.

## Preserving another iteration

`scheduler_versions/registry.json` is the benchmark manifest. To snapshot a future
standalone `main.cpp` before changing it again:

```bash
python3 tools/register_scheduler.py \
  --name v21-experiment-name \
  --description "One-sentence policy description"
```

The registration tool refuses to overwrite an existing version.
