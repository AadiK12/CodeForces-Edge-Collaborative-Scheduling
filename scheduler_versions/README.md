# Scheduler versions

`registry.json` is the manifest consumed by the benchmark notebook.

- `v0_baseline.cpp` is the frozen standalone FIFO singleton reference.
- `layered_scheduler.cpp` contains cumulative compile-time gates `OPT_LEVEL=1...7`.
- `main.cpp` at the repository root is the current layer-7 submission.
- `working-tree` in the registry lets the current submission be compared with frozen entries.

Registry `compile_defines` are part of a version's identity and source hash. The workbench
compiles each entry independently with otherwise identical flags.

To preserve a future standalone `main.cpp` checkpoint:

```bash
python3 tools/register_scheduler.py \
  --name v8-experiment-name \
  --description "One-sentence policy description"
```

The command refuses to overwrite an existing source or registry entry. Feature-gated versions
should instead be added to the manifest with the corresponding `OPT_LEVEL` definition.
