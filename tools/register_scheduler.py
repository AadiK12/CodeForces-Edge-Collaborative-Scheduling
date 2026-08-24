#!/usr/bin/env python3
"""Freeze main.cpp as a named scheduler version and add it to the registry."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "scheduler_versions/registry.json"
NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="Stable version name, such as v1-multi-active")
    parser.add_argument("--description", required=True, help="One-line policy description")
    parser.add_argument(
        "--source",
        type=pathlib.Path,
        default=pathlib.Path("main.cpp"),
        help="Repository-relative C++ source to freeze (default: main.cpp)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and print without writing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not NAME_PATTERN.fullmatch(args.name):
        print("--name must contain only letters, digits, underscores, and hyphens", file=sys.stderr)
        return 2
    if not args.description.strip():
        print("--description must not be empty", file=sys.stderr)
        return 2

    source_path = (ROOT / args.source).resolve()
    try:
        source_path.relative_to(ROOT)
    except ValueError:
        print("--source must resolve inside the repository", file=sys.stderr)
        return 2
    if not source_path.is_file():
        print(f"Source does not exist: {source_path}", file=sys.stderr)
        return 2

    registry = json.loads(REGISTRY_PATH.read_text())
    versions = registry["versions"]
    if any(version["name"] == args.name for version in versions):
        print(f"Registry already contains version {args.name!r}", file=sys.stderr)
        return 2

    target_relative = pathlib.Path("scheduler_versions") / f"{args.name}.cpp"
    target_path = ROOT / target_relative
    if target_path.exists():
        print(f"Target already exists: {target_path}", file=sys.stderr)
        return 2

    new_entry = {
        "name": args.name,
        "source": target_relative.as_posix(),
        "description": args.description.strip(),
        "frozen": True,
    }
    if args.dry_run:
        print(json.dumps(new_entry, indent=2))
        print(f"Would copy {source_path.relative_to(ROOT)} to {target_relative}")
        return 0

    target_path.write_text(source_path.read_text())
    versions.insert(max(0, len(versions) - 1), new_entry)
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2) + "\n")
    print(f"Registered {args.name}: {target_relative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
