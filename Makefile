CXX ?= g++
CXXFLAGS ?= -std=c++17 -O2 -pipe -Wall -Wextra -Wpedantic
TARGET := build/scheduler
FROZEN_BASELINE_TARGET := build/v0-baseline
NOTEBOOK_SOURCE := notebooks/edge_cloud_scheduling_lab.py
NOTEBOOK := notebooks/edge_cloud_scheduling_lab.ipynb
BENCHMARK_NOTEBOOK_SOURCE := notebooks/scheduler_benchmark_workbench.py
BENCHMARK_NOTEBOOK := notebooks/scheduler_benchmark_workbench.ipynb
OPTIMIZATION_NOTEBOOK_SOURCE := notebooks/scheduler_optimization_guide.py
OPTIMIZATION_NOTEBOOK := notebooks/scheduler_optimization_guide.ipynb
SUBMISSION_OPT_LEVEL ?= 20
SUBMISSION_SOURCE := submission.cpp
SUBMISSION_TARGET := build/submission

.PHONY: all test transcript-test scenario-test benchmark sanitize notebook notebook-check \
	benchmark-notebook benchmark-notebook-check optimization-notebook \
	optimization-notebook-check notebooks-check grouping-scenarios grouping-tune \
	broad-scenarios robust-policy-train \
	submission submission-check adversarial-dpost-search adversarial-dpost-audit \
	adversarial-dproc-search adversarial-dproc-audit adversarial-dpre-search \
	adversarial-dpre-audit adversarial-placement-search \
	adversarial-cohort-sync-search adversarial-burst-fifo-search clean

all: $(TARGET)

$(TARGET): main.cpp
	mkdir -p build
	$(CXX) $(CXXFLAGS) $< -o $@

$(FROZEN_BASELINE_TARGET): scheduler_versions/v0_baseline.cpp
	mkdir -p build
	$(CXX) $(CXXFLAGS) $< -o $@

test: transcript-test scenario-test

transcript-test: $(FROZEN_BASELINE_TARGET)
	python3 tests/run_transcript_tests.py $(FROZEN_BASELINE_TARGET)

scenario-test: $(TARGET)
	python3 tools/local_judge.py --solver $(TARGET) --scenarios scenarios

benchmark: $(TARGET)
	python3 tools/local_judge.py --solver $(TARGET) --scenarios scenarios \
		--json-out build/latest-results.json
	python3 tools/compare_benchmarks.py benchmarks/baseline-v0.json build/latest-results.json

notebook: $(NOTEBOOK)

$(NOTEBOOK): $(NOTEBOOK_SOURCE)
	uv run --with jupytext --with nbformat \
		jupytext --to ipynb --output $(NOTEBOOK) $(NOTEBOOK_SOURCE)

notebook-check: notebook $(TARGET)
	uv run --with nbconvert --with nbclient --with ipykernel --with nbformat \
		jupyter nbconvert --execute --to notebook --inplace $(NOTEBOOK) \
		--ExecutePreprocessor.timeout=180

benchmark-notebook: $(BENCHMARK_NOTEBOOK)

$(BENCHMARK_NOTEBOOK): $(BENCHMARK_NOTEBOOK_SOURCE)
	uv run --with jupytext --with nbformat \
		jupytext --to ipynb --output $(BENCHMARK_NOTEBOOK) $(BENCHMARK_NOTEBOOK_SOURCE)

benchmark-notebook-check: benchmark-notebook
	uv run --with nbconvert --with nbclient --with ipykernel --with nbformat \
		jupyter nbconvert --execute --to notebook --inplace $(BENCHMARK_NOTEBOOK) \
		--ExecutePreprocessor.timeout=180

optimization-notebook: $(OPTIMIZATION_NOTEBOOK)

$(OPTIMIZATION_NOTEBOOK): $(OPTIMIZATION_NOTEBOOK_SOURCE)
	uv run --with jupytext --with nbformat \
		jupytext --to ipynb --output $(OPTIMIZATION_NOTEBOOK) $(OPTIMIZATION_NOTEBOOK_SOURCE)

optimization-notebook-check: optimization-notebook
	uv run --with nbconvert --with nbclient --with ipykernel --with nbformat \
		jupyter nbconvert --execute --to notebook --inplace $(OPTIMIZATION_NOTEBOOK) \
		--ExecutePreprocessor.timeout=180

notebooks-check: notebook-check optimization-notebook-check benchmark-notebook-check

grouping-scenarios:
	python3 tools/generate_grouping_scenarios.py

broad-scenarios:
	python3 tools/generate_broad_scenarios.py

grouping-tune:
	python3 tools/tune_grouping_policy.py

robust-policy-train:
	uv run --with numpy python tools/train_robust_policy_portfolio.py

submission:
	python3 tools/build_submission.py --opt-level $(SUBMISSION_OPT_LEVEL) \
		--output $(SUBMISSION_SOURCE)

submission-check: submission
	python3 tools/verify_submission.py --opt-level $(SUBMISSION_OPT_LEVEL)
	$(CXX) $(CXXFLAGS) $(SUBMISSION_SOURCE) -o $(SUBMISSION_TARGET)

adversarial-dpost-search:
	python3 tools/adversarial_dpost_test.py --phase search

adversarial-dpost-audit:
	python3 tools/adversarial_dpost_test.py --phase holdout

adversarial-dproc-search:
	python3 tools/adversarial_dproc_test.py --phase search

adversarial-dproc-audit:
	python3 tools/adversarial_dproc_test.py --phase holdout

adversarial-dpre-search:
	python3 tools/adversarial_dpre_test.py --phase search

adversarial-dpre-audit:
	python3 tools/adversarial_dpre_test.py --phase holdout

adversarial-placement-search:
	python3 tools/adversarial_placement_test.py --phase search

adversarial-cohort-sync-search:
	python3 tools/adversarial_cohort_sync_test.py --phase search

adversarial-burst-fifo-search:
	python3 tools/adversarial_burst_fifo_test.py --phase search

sanitize:
	mkdir -p build
	$(CXX) -std=c++17 -O1 -g -Wall -Wextra -Wpedantic \
		-fsanitize=undefined -fno-omit-frame-pointer main.cpp -o build/scheduler-sanitize
	python3 tools/local_judge.py --solver build/scheduler-sanitize --scenarios scenarios
	$(CXX) -std=c++17 -O1 -g -Wall -Wextra -Wpedantic \
		-fsanitize=undefined -fno-omit-frame-pointer scheduler_versions/v0_baseline.cpp \
		-o build/v0-baseline-sanitize
	python3 tests/run_transcript_tests.py build/v0-baseline-sanitize

clean:
	rm -f build/scheduler build/v0-baseline build/scheduler-sanitize \
		build/v0-baseline-sanitize build/submission build/latest-results.json \
		build/notebook-*-result.json build/notebook-*-results.json
