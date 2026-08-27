#!/usr/bin/env python3
"""Deterministic local interactor and scorer for Codeforces 2251A.

The simulator follows the public problem statement. It is intentionally independent of the
baseline policy: any legal solver can be passed with --solver and compared on the same JSON
scenarios.
"""

from __future__ import annotations

import argparse
import dataclasses
import heapq
import json
import math
import os
import pathlib
import resource
import select
import subprocess
import sys
import time
from collections import defaultdict
from typing import Any, Iterable


ROOT = pathlib.Path(__file__).resolve().parents[1]


class JudgeError(RuntimeError):
    pass


class SolverTokenReader:
    def __init__(self, stream: Any):
        self.fd = stream.fileno()
        self.buffer = bytearray()

    def read_token(self, timeout_seconds: float) -> str:
        deadline = time.monotonic() + timeout_seconds
        while True:
            while self.buffer and chr(self.buffer[0]).isspace():
                del self.buffer[0]

            for index, byte in enumerate(self.buffer):
                if chr(byte).isspace():
                    token = bytes(self.buffer[:index]).decode()
                    del self.buffer[: index + 1]
                    return token

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise JudgeError("solver timed out while producing a response")

            readable, _, _ = select.select([self.fd], [], [], remaining)
            if not readable:
                raise JudgeError("solver timed out while producing a response")
            chunk = os.read(self.fd, 4096)
            if not chunk:
                if self.buffer:
                    token = self.buffer.decode()
                    self.buffer.clear()
                    return token
                raise JudgeError("solver closed stdout before the interaction ended")
            self.buffer.extend(chunk)


class SolverSession:
    def __init__(self, command: list[str], timeout_seconds: float):
        self.command = command
        self.timeout_seconds = timeout_seconds
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        self.start_cpu_seconds = usage.ru_utime + usage.ru_stime
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.reader = SolverTokenReader(self.process.stdout)

    def send(self, text: str) -> None:
        if self.process.stdin is None:
            raise JudgeError("solver stdin is closed")
        try:
            self.process.stdin.write(text.encode())
            self.process.stdin.flush()
        except BrokenPipeError as error:
            raise JudgeError("solver exited before the interaction ended") from error

    def token(self) -> str:
        return self.reader.read_token(self.timeout_seconds)

    def finish(self) -> tuple[int, str, float]:
        if self.process.stdin is not None:
            self.process.stdin.close()
            self.process.stdin = None
        try:
            return_code = self.process.wait(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
            raise JudgeError("solver did not exit after END")
        assert self.process.stderr is not None
        stderr = self.process.stderr.read().decode(errors="replace")
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu_seconds = usage.ru_utime + usage.ru_stime - self.start_cpu_seconds
        return return_code, stderr, cpu_seconds

    def abort(self) -> str:
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()
        assert self.process.stderr is not None
        return self.process.stderr.read().decode(errors="replace")


@dataclasses.dataclass
class Request:
    request_id: int
    arrival: float
    input_length: int
    output_length: int
    state: str = "NOT_ARRIVED"
    cloud: int = -1
    next_prefill_layer: int = 0
    produced_tokens: int = 0
    prefill_ready_time: float | None = None
    token_times: list[float] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Task:
    server: str
    family: str
    step: str
    task_spec: str
    members: list[int]
    duration: float
    remote: int | None = None
    layer_start: int | None = None
    layer_end: int | None = None


@dataclasses.dataclass
class Transfer:
    direction: str
    remote: int
    size_bytes: int
    phase: str
    members: list[int]


@dataclasses.dataclass(order=True)
class Event:
    timestamp: float
    order: int
    kind: str = dataclasses.field(compare=False)
    payload: Any = dataclasses.field(compare=False)


@dataclasses.dataclass
class Assignment:
    server: str
    family: str
    step: str
    remote: int | None
    members: list[int]
    marker: int | None = None
    layer_start: int | None = None
    layer_end: int | None = None


class ScenarioJudge:
    def __init__(
        self,
        scenario_path: pathlib.Path,
        solver_command: list[str],
        timeout: float,
        trace_assignments: bool = False,
    ):
        self.path = scenario_path
        self.data = json.loads(scenario_path.read_text())
        self.name = self.data.get("name", scenario_path.stem)
        self.description = self.data.get("description", "")
        self.system = self.data["system"]
        self.scoring = self.data["scoring"]
        if "task_times" in self.data:
            self.rows = self.data["task_times"]
        else:
            profile_path = scenario_path.parent / self.data["task_times_file"]
            profile_data = json.loads(profile_path.read_text())
            self.rows = profile_data["task_times"]
        self.solver_command = solver_command
        self.timeout = timeout
        self.trace_assignments = trace_assignments
        self.assignment_trace: list[dict[str, Any]] = []

        self.k = int(self.system["K"])
        self.schedule_cost = float(self.system["S"])
        self.latency = float(self.system["latency_in_ms"])
        self.bandwidth = float(self.system["bandwidth_gbps"])
        self.bytes_per_token = int(self.system["bytes_per_token"])
        self.num_layers = int(self.system["num_layers"])

        self.requests = [
            Request(
                request_id=index,
                arrival=float(raw["arrival"]),
                input_length=int(raw["input_length"]),
                output_length=int(raw["output_length"]),
            )
            for index, raw in enumerate(self.data["requests"])
        ]

        self.edge_task: Task | None = None
        self.cloud_tasks: list[Task | None] = [None] * self.k
        self.link_available = {"UP": 0.0, "DOWN": 0.0}
        self.events: list[Event] = []
        self.next_event_order = 0
        self.frame_count = 0
        self.current_time = 0.0

        self.duration_curves = self._build_duration_curves()
        self._validate_scenario()
        for request in self.requests:
            self._schedule_event(request.arrival, "ARR", request.request_id)

    def _validate_scenario(self) -> None:
        if not 1 <= self.k <= 8:
            raise JudgeError(f"{self.name}: K must be in [1, 8]")
        if not self.requests:
            raise JudgeError(f"{self.name}: at least one request is required")
        arrivals = [request.arrival for request in self.requests]
        if arrivals != sorted(arrivals):
            raise JudgeError(f"{self.name}: requests must be in nondecreasing arrival order")
        if sum(request.output_length for request in self.requests) > 200_000:
            raise JudgeError(f"{self.name}: total output length exceeds the official limit")
        for request in self.requests:
            if request.input_length < 1 or request.output_length < 1:
                raise JudgeError(f"{self.name}: request lengths must be positive")

    def _build_duration_curves(self) -> dict[str, list[tuple[int, float]]]:
        names = [
            "prefill_pre",
            "prefill_proc",
            "prefill_post",
            "decode_pre",
            "decode_proc",
            "decode_post",
        ]
        curves: dict[str, list[tuple[int, float]]] = {}
        for name in names:
            points = sorted(
                (int(row["batch_size"]), float(row[name]))
                for row in self.rows
                if float(row[name]) >= 0
            )
            if not points:
                raise JudgeError(f"{self.name}: task-time column {name} has no values")
            curves[name] = points
        return curves

    def duration(self, column: str, size: int) -> float:
        points = self.duration_curves[column]
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
        raise AssertionError("duration interpolation fell through")

    def _schedule_event(self, timestamp: float, kind: str, payload: Any) -> None:
        self.next_event_order += 1
        heapq.heappush(
            self.events,
            Event(timestamp=timestamp, order=self.next_event_order, kind=kind, payload=payload),
        )

    def _startup_text(self) -> str:
        lines = [
            (
                f"{self.k} {self.schedule_cost:.9f} {self.latency:.9f} "
                f"{self.bandwidth:.9f} {self.bytes_per_token} {self.num_layers}"
            ),
            (
                f"{float(self.scoring['SLO1']):.9f} {float(self.scoring['SLO2']):.9f} "
                f"{float(self.scoring['tp_UB']):.9f} "
                f"{float(self.scoring['tp_base']):.9f} "
                f"{float(self.scoring['dist_base']):.9f} "
                f"{float(self.scoring['w_tp']):.9f} {float(self.scoring['w_c']):.9f}"
            ),
            str(len(self.rows)),
        ]
        for row in self.rows:
            lines.append(
                " ".join(
                    [str(int(row["batch_size"]))]
                    + [
                        f"{float(row[name]):.9f}"
                        for name in (
                            "prefill_pre",
                            "prefill_proc",
                            "prefill_post",
                            "decode_pre",
                            "decode_proc",
                            "decode_post",
                        )
                    ]
                )
            )
        return "\n".join(lines) + "\n"

    def _enqueue_transfer(
        self,
        timestamp: float,
        direction: str,
        remote: int,
        length: int,
        phase: str,
        members: list[int],
    ) -> None:
        size_bytes = length * self.bytes_per_token
        transfer_duration = self.latency + 8.0 * size_bytes / (self.bandwidth * 1_000_000.0)
        start = max(timestamp, self.link_available[direction])
        finish = start + transfer_duration
        self.link_available[direction] = finish
        self._schedule_event(
            finish,
            "XDN",
            Transfer(direction, remote, size_bytes, phase, list(members)),
        )

    def _process_task_done(self, task: Task, timestamp: float) -> str:
        if task.server == "E":
            if self.edge_task is not task:
                raise JudgeError("internal edge completion mismatch")
            self.edge_task = None
        else:
            cloud = int(task.server[1:])
            if self.cloud_tasks[cloud] is not task:
                raise JudgeError("internal cloud completion mismatch")
            self.cloud_tasks[cloud] = None

        if task.family == "P" and task.step == "PRE":
            request = self.requests[task.members[0]]
            request.state = "WAIT_PREFILL_UP"
            self._enqueue_transfer(
                timestamp,
                "UP",
                request.cloud,
                request.input_length,
                "PRE",
                [request.request_id],
            )
        elif task.family == "P" and task.step == "PROC":
            request = self.requests[task.members[0]]
            assert task.layer_end is not None
            request.next_prefill_layer = task.layer_end
            if task.layer_end == self.num_layers:
                request.state = "WAIT_PREFILL_DOWN"
                self._enqueue_transfer(
                    timestamp,
                    "DOWN",
                    request.cloud,
                    request.input_length,
                    "PRE",
                    [request.request_id],
                )
            else:
                request.state = "READY_P_PROC"
        elif task.family == "P" and task.step == "POST":
            request = self.requests[task.members[0]]
            request.state = "READY_D_PRE"
            request.prefill_ready_time = timestamp
        elif task.family == "D" and task.step == "PRE":
            by_cloud: dict[int, list[int]] = defaultdict(list)
            for request_id in task.members:
                request = self.requests[request_id]
                request.state = "WAIT_DECODE_UP"
                by_cloud[request.cloud].append(request_id)
            for cloud in sorted(by_cloud):
                members = by_cloud[cloud]
                self._enqueue_transfer(
                    timestamp, "UP", cloud, len(members), "DEC", members
                )
        elif task.family == "D" and task.step == "PROC":
            assert task.remote is not None
            for request_id in task.members:
                self.requests[request_id].state = "WAIT_DECODE_DOWN"
            self._enqueue_transfer(
                timestamp,
                "DOWN",
                task.remote,
                len(task.members),
                "DEC",
                task.members,
            )
        elif task.family == "D" and task.step == "POST":
            for request_id in task.members:
                request = self.requests[request_id]
                request.produced_tokens += 1
                request.token_times.append(timestamp)
                if request.produced_tokens == request.output_length:
                    request.state = "FINISHED"
                    self._schedule_event(timestamp, "FIN", request_id)
                else:
                    request.state = "READY_D_PRE"
        else:
            raise JudgeError(f"unknown completed task {task.family} {task.step}")

        return f"TDN {task.server} {task.task_spec} {task.duration:.9f}"

    def _process_event(self, event: Event) -> str:
        if event.kind == "ARR":
            request = self.requests[int(event.payload)]
            if request.state != "NOT_ARRIVED":
                raise JudgeError("duplicate local ARR")
            request.state = "READY_P_PRE"
            return f"ARR {request.request_id} {request.input_length}"

        if event.kind == "TASK_DONE":
            return self._process_task_done(event.payload, event.timestamp)

        if event.kind == "XDN":
            transfer: Transfer = event.payload
            for request_id in transfer.members:
                request = self.requests[request_id]
                if transfer.phase == "PRE" and transfer.direction == "UP":
                    self._expect_state(request, "WAIT_PREFILL_UP", "prefill UP completion")
                    request.state = "READY_P_PROC"
                elif transfer.phase == "PRE" and transfer.direction == "DOWN":
                    self._expect_state(request, "WAIT_PREFILL_DOWN", "prefill DOWN completion")
                    request.state = "READY_P_POST"
                elif transfer.phase == "DEC" and transfer.direction == "UP":
                    self._expect_state(request, "WAIT_DECODE_UP", "decode UP completion")
                    request.state = "READY_D_PROC"
                elif transfer.phase == "DEC" and transfer.direction == "DOWN":
                    self._expect_state(request, "WAIT_DECODE_DOWN", "decode DOWN completion")
                    request.state = "READY_D_POST"
                else:
                    raise JudgeError("invalid local transfer event")
            ids = " ".join(str(request_id) for request_id in transfer.members)
            return (
                f"XDN {transfer.direction} {transfer.remote} {transfer.size_bytes} "
                f"{transfer.phase} {len(transfer.members)} {ids}"
            )

        if event.kind == "FIN":
            return f"FIN {int(event.payload)}"

        raise JudgeError(f"unknown local event kind {event.kind}")

    def _expect_state(self, request: Request, expected: str, action: str) -> None:
        if request.state != expected:
            raise JudgeError(
                f"t={self.current_time:.9f}: {action} requires request {request.request_id} "
                f"in {expected}, found {request.state}"
            )

    @staticmethod
    def _parse_int(token: str, context: str) -> int:
        try:
            return int(token)
        except ValueError as error:
            raise JudgeError(f"expected integer for {context}, received {token!r}") from error

    def _read_assignment(self, solver: SolverSession) -> Assignment:
        server = solver.token()
        family = solver.token()
        step = solver.token()

        if family == "P" and step == "PRE":
            remote = self._parse_int(solver.token(), "P PRE remote")
            request_id = self._parse_int(solver.token(), "P PRE request")
            return Assignment(server, family, step, remote, [request_id])

        if family == "P" and step == "PROC":
            layer_start = self._parse_int(solver.token(), "P PROC layer start")
            layer_end = self._parse_int(solver.token(), "P PROC layer end")
            remote = self._parse_int(solver.token(), "P PROC remote")
            request_id = self._parse_int(solver.token(), "P PROC request")
            return Assignment(
                server,
                family,
                step,
                remote,
                [request_id],
                layer_start=layer_start,
                layer_end=layer_end,
            )

        if family == "P" and step == "POST":
            remote = self._parse_int(solver.token(), "P POST remote")
            request_id = self._parse_int(solver.token(), "P POST request")
            return Assignment(server, family, step, remote, [request_id])

        if family == "D" and step in {"PRE", "POST"}:
            marker = self._parse_int(solver.token(), f"D {step} marker")
            member_count = self._parse_int(solver.token(), f"D {step} member count")
            members = [
                self._parse_int(solver.token(), f"D {step} request")
                for _ in range(member_count)
            ]
            return Assignment(server, family, step, None, members, marker=marker)

        if family == "D" and step == "PROC":
            remote = self._parse_int(solver.token(), "D PROC remote")
            member_count = self._parse_int(solver.token(), "D PROC member count")
            members = [
                self._parse_int(solver.token(), "D PROC request")
                for _ in range(member_count)
            ]
            return Assignment(server, family, step, remote, members)

        raise JudgeError(f"unknown assignment shape: {server} {family} {step}")

    def _server_index(self, server: str) -> int | None:
        if server == "E":
            return None
        if not server.startswith("C"):
            raise JudgeError(f"invalid server {server!r}")
        try:
            cloud = int(server[1:])
        except ValueError as error:
            raise JudgeError(f"invalid server {server!r}") from error
        if not 0 <= cloud < self.k:
            raise JudgeError(f"server {server!r} is outside [C0, C{self.k - 1}]")
        return cloud

    def _validate_assignment(self, assignment: Assignment) -> None:
        cloud = self._server_index(assignment.server)
        if assignment.family == "P" and assignment.step == "PRE":
            if assignment.server != "E":
                raise JudgeError("P PRE must run on E")
            if assignment.remote is None or not 0 <= assignment.remote < self.k:
                raise JudgeError("P PRE remote is outside the valid range")
            request = self.requests[assignment.members[0]]
            self._expect_state(request, "READY_P_PRE", "P PRE")
            if request.cloud != -1:
                raise JudgeError("P PRE attempted to reassign a request")
            return

        if assignment.family == "P" and assignment.step == "PROC":
            if cloud is None or assignment.remote != cloud:
                raise JudgeError("P PROC server and remote must name the same cloud")
            request = self.requests[assignment.members[0]]
            self._expect_state(request, "READY_P_PROC", "P PROC")
            if request.cloud != cloud:
                raise JudgeError("P PROC used the wrong assigned cloud")
            if (
                assignment.layer_start != request.next_prefill_layer
                or assignment.layer_end is None
                or assignment.layer_start is None
                or assignment.layer_end <= assignment.layer_start
                or assignment.layer_end > self.num_layers
            ):
                raise JudgeError("P PROC piece is not ascending, nonempty, and gap-free")
            return

        if assignment.family == "P" and assignment.step == "POST":
            if assignment.server != "E":
                raise JudgeError("P POST must run on E")
            request = self.requests[assignment.members[0]]
            self._expect_state(request, "READY_P_POST", "P POST")
            if request.cloud != assignment.remote:
                raise JudgeError("P POST echoed the wrong assigned cloud")
            return

        if assignment.family == "D" and assignment.step in {"PRE", "POST"}:
            if assignment.server != "E":
                raise JudgeError(f"D {assignment.step} must run on E")
            if assignment.marker != -1:
                raise JudgeError(f"D {assignment.step} requires the -1 marker")
            expected = "READY_D_PRE" if assignment.step == "PRE" else "READY_D_POST"
            self._validate_group(assignment.members, expected, f"D {assignment.step}")
            return

        if assignment.family == "D" and assignment.step == "PROC":
            if cloud is None or assignment.remote != cloud:
                raise JudgeError("D PROC server and remote must name the same cloud")
            self._validate_group(assignment.members, "READY_D_PROC", "D PROC")
            if any(self.requests[request_id].cloud != cloud for request_id in assignment.members):
                raise JudgeError("D PROC group contains a request assigned to another cloud")
            return

        raise JudgeError(
            f"invalid assignment {assignment.server} {assignment.family} {assignment.step}"
        )

    def _validate_group(self, members: list[int], expected: str, action: str) -> None:
        if not members:
            raise JudgeError(f"{action} group must be nonempty")
        if len(members) != len(set(members)):
            raise JudgeError(f"{action} group contains duplicate request IDs")
        for request_id in members:
            if not 0 <= request_id < len(self.requests):
                raise JudgeError(f"{action} references unknown request {request_id}")
            self._expect_state(self.requests[request_id], expected, action)

    def _resource_is_busy(self, server: str) -> bool:
        cloud = self._server_index(server)
        return self.edge_task is not None if cloud is None else self.cloud_tasks[cloud] is not None

    def _task_duration(self, assignment: Assignment) -> float:
        if assignment.family == "P":
            request = self.requests[assignment.members[0]]
            column = f"prefill_{assignment.step.lower()}"
            duration = self.duration(column, request.input_length)
            if assignment.step == "PROC":
                assert assignment.layer_start is not None and assignment.layer_end is not None
                duration *= (assignment.layer_end - assignment.layer_start) / self.num_layers
            return duration

        column = f"decode_{assignment.step.lower()}"
        return self.duration(column, len(assignment.members))

    def _apply_assignment(self, assignment: Assignment) -> None:
        duration = self._task_duration(assignment)
        members = assignment.members
        remote = assignment.remote

        if assignment.family == "P" and assignment.step == "PRE":
            request = self.requests[members[0]]
            assert remote is not None
            request.cloud = remote
            request.state = "RUNNING_P_PRE"
            task_spec = f"P PRE {remote} {request.request_id}"
        elif assignment.family == "P" and assignment.step == "PROC":
            request = self.requests[members[0]]
            request.state = "RUNNING_P_PROC"
            task_spec = (
                f"P PROC {assignment.layer_start} {assignment.layer_end} "
                f"{remote} {request.request_id}"
            )
        elif assignment.family == "P" and assignment.step == "POST":
            request = self.requests[members[0]]
            request.state = "RUNNING_P_POST"
            task_spec = f"P POST {remote} {request.request_id}"
        elif assignment.family == "D" and assignment.step == "PRE":
            for request_id in members:
                self.requests[request_id].state = "RUNNING_D_PRE"
            task_spec = f"D PRE -1 {len(members)} " + " ".join(map(str, members))
        elif assignment.family == "D" and assignment.step == "PROC":
            for request_id in members:
                self.requests[request_id].state = "RUNNING_D_PROC"
            task_spec = f"D PROC {remote} {len(members)} " + " ".join(map(str, members))
        elif assignment.family == "D" and assignment.step == "POST":
            for request_id in members:
                self.requests[request_id].state = "RUNNING_D_POST"
            task_spec = f"D POST -1 {len(members)} " + " ".join(map(str, members))
        else:
            raise AssertionError("assignment application fell through")

        task = Task(
            server=assignment.server,
            family=assignment.family,
            step=assignment.step,
            task_spec=task_spec,
            members=list(members),
            duration=duration,
            remote=remote,
            layer_start=assignment.layer_start,
            layer_end=assignment.layer_end,
        )
        cloud = self._server_index(assignment.server)
        if cloud is None:
            self.edge_task = task
        else:
            self.cloud_tasks[cloud] = task
        self._schedule_event(self.current_time + self.schedule_cost + duration, "TASK_DONE", task)

    def _read_and_apply_response(self, solver: SolverSession) -> None:
        count = self._parse_int(solver.token(), "assignment count")
        if not 0 <= count <= self.k + 1:
            raise JudgeError(f"assignment count {count} is outside [0, {self.k + 1}]")
        assignments = [self._read_assignment(solver) for _ in range(count)]

        used_servers: set[str] = set()
        used_requests: set[int] = set()
        for assignment in assignments:
            if assignment.server in used_servers:
                raise JudgeError(f"two assignments use server {assignment.server} in one response")
            used_servers.add(assignment.server)
            if self._resource_is_busy(assignment.server):
                raise JudgeError(f"assignment uses busy server {assignment.server}")
            overlap = used_requests.intersection(assignment.members)
            if overlap:
                raise JudgeError(f"requests scheduled twice in one response: {sorted(overlap)}")
            used_requests.update(assignment.members)
            self._validate_assignment(assignment)

        # Apply only after validating the complete response: assignments at one timestamp cannot
        # depend on state changes caused by another assignment in that response.
        for assignment in assignments:
            self._apply_assignment(assignment)
        if self.trace_assignments and assignments:
            self.assignment_trace.append(
                {
                    "time": self.current_time,
                    "assignments": [
                        {
                            "server": assignment.server,
                            "family": assignment.family,
                            "step": assignment.step,
                            "remote": assignment.remote,
                            "members": assignment.members,
                            "layer_start": assignment.layer_start,
                            "layer_end": assignment.layer_end,
                        }
                        for assignment in assignments
                    ],
                }
            )

    def _all_finished(self) -> bool:
        return all(request.state == "FINISHED" for request in self.requests)

    def _score(self) -> dict[str, float | int]:
        token_count = sum(request.output_length for request in self.requests)
        first_arrival = min(request.arrival for request in self.requests)
        latest_token = max(request.token_times[-1] for request in self.requests)
        elapsed = latest_token - first_arrival
        throughput = token_count / elapsed if elapsed > 0 else 0.0

        tdr_values = [
            float(request.prefill_ready_time) - request.arrival for request in self.requests
        ]
        tdr = sum(tdr_values) / len(tdr_values)

        gaps = [
            later - earlier
            for request in self.requests
            for earlier, later in zip(request.token_times, request.token_times[1:])
        ]
        tpot = sum(gaps) / len(gaps) if gaps else 0.0

        slo1 = float(self.scoring["SLO1"])
        slo2 = float(self.scoring["SLO2"])
        excess_tdr = max(0.0, (tdr - slo1) / slo1)
        excess_tpot = max(0.0, (tpot - slo2) / slo2)
        distance = math.hypot(excess_tdr, excess_tpot)

        tp_base = float(self.scoring["tp_base"])
        tp_upper = float(self.scoring["tp_UB"])
        throughput_component = max(
            0.0, min(1.0, (throughput - tp_base) / (tp_upper - tp_base))
        )

        distance_base = float(self.scoring["dist_base"])
        if distance_base > 0:
            waiting_component = max(0.0, 1.0 - distance / distance_base)
        else:
            waiting_component = 1.0 if distance == 0 else 0.0

        normalized = (
            float(self.scoring["w_tp"]) * throughput_component
            + float(self.scoring["w_c"]) * waiting_component
        )
        return {
            "score": 1000.0 * normalized,
            "throughput": throughput,
            "tdr": tdr,
            "tpot": tpot,
            "distance": distance,
            "elapsed": elapsed,
            "tokens": token_count,
            "frames": self.frame_count,
        }

    def run(self) -> dict[str, Any]:
        wall_start = time.perf_counter()
        solver = SolverSession(self.solver_command, self.timeout)
        try:
            solver.send(self._startup_text())
            while True:
                if not self.events:
                    raise JudgeError("unfinished requests remain but no future event exists")

                self.current_time = self.events[0].timestamp
                event_lines: list[str] = []
                while self.events and self.events[0].timestamp == self.current_time:
                    event = heapq.heappop(self.events)
                    event_lines.append(self._process_event(event))

                self.frame_count += 1
                frame = (
                    f"{self.current_time:.9f}\n{len(event_lines)}\n"
                    + "\n".join(event_lines)
                    + "\n"
                )
                solver.send(frame)
                self._read_and_apply_response(solver)

                if self._all_finished():
                    solver.send("END\n")
                    return_code, stderr, scheduler_cpu_seconds = solver.finish()
                    if return_code != 0:
                        raise JudgeError(f"solver exited with code {return_code}: {stderr.strip()}")
                    result: dict[str, Any] = {
                        "scenario": self.name,
                        "description": self.description,
                        "legal": True,
                        **self._score(),
                        "scheduler_cpu_seconds": scheduler_cpu_seconds,
                        "judge_wall_seconds": time.perf_counter() - wall_start,
                    }
                    if self.trace_assignments:
                        result["assignment_trace"] = self.assignment_trace
                    if stderr.strip():
                        result["solver_stderr"] = stderr.strip()
                    return result
        except Exception as error:
            stderr = solver.abort()
            if isinstance(error, JudgeError):
                detail = str(error)
            else:
                detail = f"local judge failure: {error}"
            if stderr.strip():
                detail += f"; solver stderr: {stderr.strip()}"
            return {
                "scenario": self.name,
                "description": self.description,
                "legal": False,
                "error": detail,
            }


def collect_scenarios(arguments: Iterable[str]) -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []
    for argument in arguments:
        path = pathlib.Path(argument)
        if path.is_dir():
            paths.extend(sorted(path.glob("*.json")))
        elif path.is_file():
            paths.append(path)
        else:
            raise JudgeError(f"scenario path does not exist: {argument}")
    unique = sorted({path.resolve() for path in paths})
    if not unique:
        raise JudgeError("no scenario JSON files found")
    return unique


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solver", required=True, help="Path to the scheduler executable")
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=[str(ROOT / "scenarios")],
        help="Scenario JSON files or directories",
    )
    parser.add_argument("--timeout", type=float, default=3.0, help="Seconds per solver response")
    parser.add_argument("--json-out", help="Optional path for the result array")
    parser.add_argument(
        "--trace-assignments",
        action="store_true",
        help="Include the solver's assignment trace in JSON output",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    solver_path = pathlib.Path(args.solver).resolve()
    if not solver_path.is_file():
        print(f"Solver executable does not exist: {solver_path}", file=sys.stderr)
        return 2

    try:
        scenario_paths = collect_scenarios(args.scenarios)
    except JudgeError as error:
        print(error, file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    for scenario_path in scenario_paths:
        judge = ScenarioJudge(
            scenario_path,
            [str(solver_path)],
            args.timeout,
            trace_assignments=args.trace_assignments,
        )
        result = judge.run()
        results.append(result)
        if result["legal"]:
            print(
                f"PASS {result['scenario']:<28} "
                f"score={result['score']:8.3f} "
                f"tp={result['throughput']:.6f} "
                f"tdr={result['tdr']:.3f} "
                f"tpot={result['tpot']:.3f} "
                f"elapsed={result['elapsed']:.3f}"
            )
        else:
            print(f"FAIL {result['scenario']}: {result['error']}")

    if args.json_out:
        output_path = pathlib.Path(args.json_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(results, indent=2) + "\n")

    return 0 if all(result["legal"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
