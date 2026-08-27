#!/usr/bin/env python3
"""Build a compact submission containing only features active at one policy level."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "main.cpp"
DEFAULT_OUTPUT = ROOT / "submission.cpp"
MAX_CODEFORCES_CHARACTERS = 65_535
IDENTIFIER_RENAMES = {
    "TaskKind": "Q0",
    "RequestState": "Q1",
    "DurationColumn": "Q2",
    "request_id": "q0",
    "schedule_cost_": "z0",
    "current_time_": "z1",
    "cloud_count_": "z2",
    "group_size": "z3",
    "throughput_weight_": "z4",
    "latency_weight_": "z5",
    "bytes_per_token_": "z6",
    "duration_curves_": "z7",
    "predicted_up_tail_": "z8",
    "predicted_down_tail_": "z9",
    "throughput_upper_bound_": "za",
    "throughput_baseline_": "zb",
    "pending_up_transfers_": "zc",
    "pending_down_transfers_": "zd",
    "learned_policy_action_": "ze",
    "learned_policy_action": "zf",
    "ready_dispersion": "zg",
    "learned_policy_features": "zh",
    "requests_": "zi",
    "pending_prefill_work_": "zj",
    "active_requests_": "zk",
    "active_decode_requests_": "zl",
    "total_active_decode_requests_": "zm",
    "cloud_busy_": "zn",
    "cloud_busy_until_": "zo",
    "edge_busy_": "zp",
    "edge_busy_until_": "zq",
    "p_pre_ready_": "zr",
    "d_pre_ready_": "zs",
    "d_post_ready_": "zt",
}
MARKER = re.compile(
    r"^\s*//\s*SUBMISSION_FEATURE_(BEGIN|END)\s+([a-z0-9_]+)\s*$"
)


def enabled_features(level: int) -> set[str]:
    features: set[str] = set()
    if level < 20:
        features.add("pre20_only")
    if level < 11:
        features.add("legacy_priority")
    if 16 <= level <= 18:
        features.add("experimental_grouping")
    if level >= 19:
        features.add("terminal_dpost")
    if level >= 20:
        features.add("terminal_dproc")
        features.add("cohort_dpost")
        features.add("ppost_cohort_seed")
        features.add("dynamic_coherent_dpost")
        features.add("initial_decode_barrier")
        features.add("learned_policy")
    return features


def strip_inactive_features(source: str, features: set[str]) -> str:
    output: list[str] = []
    feature_stack: list[tuple[str, bool]] = []
    keep = True
    for line_number, line in enumerate(source.splitlines(keepends=True), start=1):
        match = MARKER.match(line.rstrip("\n"))
        if match:
            action, feature = match.groups()
            if action == "BEGIN":
                feature_stack.append((feature, keep))
                keep = keep and feature in features
            else:
                if not feature_stack or feature_stack[-1][0] != feature:
                    raise ValueError(
                        f"mismatched submission feature end at line {line_number}: {feature}"
                    )
                _, keep = feature_stack.pop()
            continue
        if keep:
            output.append(line)
    if feature_stack:
        raise ValueError(f"unterminated submission feature: {feature_stack[-1][0]}")
    return "".join(output)


def remove_comments(source: str) -> str:
    output: list[str] = []
    index = 0
    state = "code"
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if char == '"':
                state = "string"
                output.append(char)
            elif char == "'":
                state = "char"
                output.append(char)
            elif char == "/" and following == "/":
                state = "line_comment"
                index += 1
            elif char == "/" and following == "*":
                state = "block_comment"
                index += 1
            else:
                output.append(char)
        elif state == "string":
            output.append(char)
            if char == "\\" and following:
                output.append(following)
                index += 1
            elif char == '"':
                state = "code"
        elif state == "char":
            output.append(char)
            if char == "\\" and following:
                output.append(following)
                index += 1
            elif char == "'":
                state = "code"
        elif state == "line_comment":
            if char == "\n":
                output.append(char)
                state = "code"
        else:
            if char == "*" and following == "/":
                state = "code"
                index += 1
            elif char == "\n":
                output.append(char)
        index += 1
    if state in {"string", "char", "block_comment"}:
        raise ValueError(f"unterminated C++ lexical state: {state}")
    return "".join(output)


def compact_code(code: str) -> str:
    literals: list[str] = []

    def protect_literal(match: re.Match[str]) -> str:
        placeholder = f"__CODEX_LITERAL_{len(literals)}__"
        literals.append(match.group())
        return placeholder

    code = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', protect_literal, code)
    for original, compact in IDENTIFIER_RENAMES.items():
        code = re.sub(rf"\b{re.escape(original)}\b", compact, code)
    code = re.sub(r"\s+", " ", code).strip()
    code = re.sub(r"\s*([{}()\[\];,?])\s*", r"\1", code)
    code = re.sub(r"\s*(::|->)\s*", r"\1", code)
    code = re.sub(
        r"\s*(==|!=|<=|>=|\+=|-=|\*=|/=|&&|\|\||=|<|>)\s*",
        r"\1",
        code,
    )
    code = re.sub(r"\s*([+\-*/%&|^!:])\s*", r"\1", code)
    for index, literal in enumerate(literals):
        code = code.replace(f"__CODEX_LITERAL_{index}__", literal)
    return code


def minify(source: str) -> str:
    source = remove_comments(source)
    output: list[str] = []
    code_lines: list[str] = []

    def flush_code() -> None:
        if not code_lines:
            return
        compacted = compact_code("\n".join(code_lines))
        if compacted:
            output.append(compacted + "\n")
        code_lines.clear()

    for line in source.splitlines():
        if line.lstrip().startswith("#"):
            flush_code()
            output.append(line.strip() + "\n")
        else:
            code_lines.append(line)
    flush_code()
    return "".join(output)


def set_default_level(source: str, level: int) -> str:
    pattern = re.compile(
        r"(#ifndef\s+OPT_LEVEL\s*\n#define\s+OPT_LEVEL\s+)\d+(\s*\n#endif)"
    )
    updated, count = pattern.subn(rf"\g<1>{level}\g<2>", source, count=1)
    if count != 1:
        raise ValueError("could not locate the default OPT_LEVEL block")
    return updated


def build(source_path: pathlib.Path, level: int, minified: bool) -> str:
    source = source_path.read_text()
    source = set_default_level(source, level)
    source = strip_inactive_features(source, enabled_features(level))
    return minify(source) if minified else source


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=pathlib.Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--opt-level", type=int, default=15)
    parser.add_argument("--max-characters", type=int, default=MAX_CODEFORCES_CHARACTERS)
    parser.add_argument("--no-minify", action="store_true")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the output is stale instead of rewriting it",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.opt_level <= 20:
        raise SystemExit("--opt-level must be in [1, 20]")
    source_path = args.source.resolve()
    output_path = args.output.resolve()
    generated = build(source_path, args.opt_level, not args.no_minify)
    character_count = len(generated)
    byte_count = len(generated.encode())
    if character_count > args.max_characters:
        print(
            f"generated source has {character_count} characters; "
            f"limit is {args.max_characters}",
            file=sys.stderr,
        )
        return 1
    if args.check:
        if not output_path.is_file() or output_path.read_text() != generated:
            print(f"stale generated submission: {output_path}", file=sys.stderr)
            return 1
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(generated)
    print(
        f"submission level {args.opt_level}: {character_count} characters, "
        f"{byte_count} bytes, {args.max_characters - character_count} remaining"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
