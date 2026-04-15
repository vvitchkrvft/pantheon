"""Thin CLI entrypoint for Pantheon."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Sequence

from pantheon.db import create_group, list_groups


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pantheon")
    parser.add_argument("--db", type=Path, default=Path("pantheon.db"))

    subparsers = parser.add_subparsers(dest="command")

    group_parser = subparsers.add_parser("group")
    group_subparsers = group_parser.add_subparsers(dest="group_command", required=True)

    group_init_parser = group_subparsers.add_parser("init")
    group_init_parser.add_argument("name")

    group_subparsers.add_parser("list")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "group":
        return _handle_group_command(args)

    print(
        "Pantheon scaffold initialized. Read spec/PANTHEON_DOCTRINE.md and spec/PANTHEON_V1_BRIEF.md."
    )
    return 0


def _handle_group_command(args: argparse.Namespace) -> int:
    try:
        if args.group_command == "init":
            group = create_group(args.db, args.name)
            print(f"created group {group.id} {group.name}")
            return 0

        if args.group_command == "list":
            print("id\tname\tcreated_at\tupdated_at")
            for group in list_groups(args.db):
                print(
                    f"{group.id}\t{group.name}\t{group.created_at}\t{group.updated_at}"
                )
            return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except sqlite3.IntegrityError as exc:
        print(_format_integrity_error(exc), file=sys.stderr)
        return 1

    parser = build_parser()
    parser.print_usage(sys.stderr)
    return 1


def _format_integrity_error(error: sqlite3.IntegrityError) -> str:
    message = str(error)
    if "groups.name" in message:
        return "group name already exists"
    return "database write failed"


if __name__ == "__main__":
    raise SystemExit(main())
