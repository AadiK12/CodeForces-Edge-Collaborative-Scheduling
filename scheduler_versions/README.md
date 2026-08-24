# Scheduler versions

This directory contains frozen, runnable scheduler sources used by the benchmark workbench.
`registry.json` defines the display name, source path, description, and whether a version is
frozen. `main.cpp` is separately registered as `working-tree` so it can be compared before it
is archived.

Before starting the next optimization, preserve the current `main.cpp` with:

```bash
python3 tools/register_scheduler.py \
  --name v1-multi-active \
  --description "Multiple active singleton requests per cloud"
```

The command refuses to overwrite an existing source or registry entry. After registration,
the benchmark notebook automatically discovers and runs the new version.
