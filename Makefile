CXX ?= g++
CXXFLAGS ?= -std=c++17 -O2 -pipe -Wall -Wextra -Wpedantic
TARGET := build/scheduler
FROZEN_BASELINE_TARGET := build/v0-baseline
NOTEBOOK_SOURCE := notebooks/edge_cloud_scheduling_lab.py
NOTEBOOK := notebooks/edge_cloud_scheduling_lab.ipynb
BENCHMARK_NOTEBOOK_SOURCE := notebooks/scheduler_benchmark_workbench.py
BENCHMARK_NOTEBOOK := notebooks/scheduler_benchmark_workbench.ipynb

.PHONY: all test transcript-test scenario-test benchmark sanitize notebook notebook-check \
	benchmark-notebook benchmark-notebook-check notebooks-check clean

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

notebooks-check: notebook-check benchmark-notebook-check

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
		build/v0-baseline-sanitize build/latest-results.json \
		build/notebook-*-result.json build/notebook-*-results.json
