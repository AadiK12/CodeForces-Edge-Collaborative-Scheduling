# Scheduler versions

`registry.json` is the manifest consumed by the benchmark notebook.

- `v0_baseline.cpp` is the frozen standalone FIFO singleton reference.
- `layered_scheduler.cpp` contains registered gates `OPT_LEVEL=1...20`.
- `v21_dpre_experiment.cpp` preserves the unpromoted full-path D PRE experiment separately;
  its frozen revision failed a fresh 512-case holdout with one loss and no wins.
- `v22_placement_experiment.cpp` preserves the pending-prefill placement experiment; targeted
  search found 116 losses in 256 cases before the backlog guard and 35 afterward.
- `v23_cohort_sync_experiment.cpp` preserves predicted-DOWN D POST waiting and cohort-completion
  experiments; the combined search remained positive on average but retained regressions.
- `v24_burst_fifo_experiment.cpp` preserves the link-constrained burst-ordering experiment; its
  dedicated 512-case search rejected the frozen-fixture gain with 250 losses.
- `v25_backpressure_experiment.cpp`, `v27_dpost_threshold_experiment.cpp`, and
  `v29_cohort_dpost_experiment.cpp` record the initial post-layer-20 mechanisms. The current
  `v33_guarded_dpost.cpp` combines their holdout-safe forms.
- `v36_coherent_decode_experiment.cpp` preserves the rejected always-on cohort barrier;
  `v38_gated_coherent_decode.cpp` records the first public-parameter gate, while v40-v42 record
  the 20%/30%/40% transfer-cap sweep. The 30% v41 candidate passed a fresh 256-case audit.
- `v43_ppost_cohort_seed_experiment.cpp` records the fresh-audited P POST reorder that completes a
  known D PRE cohort only when public table costs predict lower edge clearance.
- `v50_prefill_cohort_wait_experiment.cpp` and `v51_link_admission_fairness_experiment.cpp` preserve
  rejected attempts to synchronize prefill admission and reserve the shared links. Both reduced
  score in paired testing and remain disabled.
- `v52_dynamic_coherent_dpost_experiment.cpp` records the first dynamic coherent-DPOST gate.
  `v53_sealed_global_cohort.cpp` adds the safety invariant that the seed D PRE group must contain
  every known unfinished request; the final independent 256-case audit had 3 wins and no losses.
- `v69_sparse_initial_decode_barrier.cpp` preserves the last all-hand-written promoted reference.
- `v83_conservative_neural_policy.cpp` preserves the quantized 18→8→6 residual policy. It can only
  widen the sealed coherent-DPOST dispersion threshold after a 0.60-confidence gate; otherwise it
  exactly falls back to v69.
- `v84_exact_dpost_partition.cpp` preserves the rejected whole-ready-queue D POST partition
  experiment. Its rollout-safe proposal still produced 1 win and 2 losses on 256 broad training
  cases, showing that a D POST-only optimum can lose after the next decode cycle.
- `v85_censored_completion_index.cpp` preserves a 64-exposure, right-censored token-age hazard
  estimator and Gittins-style completion index. It was mixed on training and neutral on validation,
  so it is not enabled by the working tree.
- `v86_objective_margin_rollout.cpp` and `v87_guarded_objective_margin_rollout.cpp` preserve broad
  and latency-only three-action resource-sequence rollouts. Both regressed, demonstrating that
  public milestone margins still omit pipeline-unlock value.
- `v88_robust_portfolio_policy.cpp` preserves the quantized selector trained on lower-confidence
  hidden-world targets for identical public feature states. Its 0.50-margin development runs were
  lossless, but a sealed 1,536-world audit found 24 wins and one loss, so it remains rejected.
  End-to-end C++ evidence is kept in `benchmarks/further-optimization-experiments.json` rather than
  inferred from training metrics.
- `main.cpp` at the repository root is the current layer-20 engine with promoted revision v83.
- Layers 16–18 are experimental counterfactual/learned grouping policies. They stay registered
  for reproducible comparison even though the holdout audit did not justify promotion.
- Layer 19 returns to the promoted v15 lineage and adds only the terminal D POST optimizer;
  it does not inherit the rejected layer-16–18 grouping decisions.
- Layer 20 extends that safe branch with a narrowly gated D PROC-to-D POST rollout. It was
  promoted after a positive 128-case fresh audit with no losses.
- Revision v25 resumes an already-started P PROC under severe link pressure; v27 widens terminal
  D POST rollout outside latency-dominated scoring; v33 makes v29's cohort wait stage-correct by
  modeling only the earliest reachable cohort. Revisions v38-v41 reunite an exact D PRE cohort at
  D POST only when fixed scheduling overhead dominates, transfer is at most 30% of that overhead,
  and at least two clouds can execute the cohort in parallel. Revision v43 adds its bounded P POST
  cohort seed. Revision v53 dynamically extends cohort preservation to throughput-dominant global
  D PRE groups only when public transfer, D PROC, and D POST tables bound the predicted tail tightly
  enough. Revision v69 adds the sparse public initial-decode barrier. Revision v83 adds the
  conservative learned residual selector; its final fresh 1,536-case audit had 38 wins and no
  losses. These are local promotion results rather than an official-score estimate.
- `working-tree` in the registry lets the current submission be compared with frozen entries.

Registry `compile_defines` are part of a version's identity and source hash. The workbench
compiles each entry independently with otherwise identical flags.

To preserve a future standalone `main.cpp` checkpoint:

```bash
python3 tools/register_scheduler.py \
  --name v21-experiment-name \
  --description "One-sentence policy description"
```

The command refuses to overwrite an existing source or registry entry. Feature-gated versions
should instead be added to the manifest with the corresponding `OPT_LEVEL` definition.
