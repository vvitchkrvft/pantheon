"""Thin CLI entrypoint for Pantheon."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Sequence

from pantheon.db import create_agent, create_group, list_groups, submit_goal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pantheon")
    parser.add_argument("--db", type=Path, default=Path("pantheon.db"))

    subparsers = parser.add_subparsers(dest="command")

    group_parser = subparsers.add_parser("group")
    group_subparsers = group_parser.add_subparsers(dest="group_command", required=True)

    group_init_parser = group_subparsers.add_parser("init")
    group_init_parser.add_argument("name")

    group_subparsers.add_parser("list")

    agent_parser = subparsers.add_parser("agent")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command", required=True)

    agent_add_parser = agent_subparsers.add_parser("add")
    agent_add_parser.add_argument("--group", required=True)
    agent_add_parser.add_argument("--name", required=True)
    agent_add_parser.add_argument("--role", required=True, choices=("lead", "worker"))
    agent_add_parser.add_argument("--hermes-home", required=True)
    agent_add_parser.add_argument("--workdir", required=True)
    agent_add_parser.add_argument("--profile-name")
    agent_add_parser.add_argument("--model-override")
    agent_add_parser.add_argument("--provider-override")

    goal_parser = subparsers.add_parser("goal")
    goal_subparsers = goal_parser.add_subparsers(dest="goal_command", required=True)

    goal_submit_parser = goal_subparsers.add_parser("submit")
    goal_submit_parser.add_argument("goal_text")
    goal_submit_parser.add_argument("--group", required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "group":
        return _handle_group_command(args)
    if args.command == "agent":
        return _handle_agent_command(args)
    if args.command == "goal":
        return _handle_goal_command(args)

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


def _handle_agent_command(args: argparse.Namespace) -> int:
    try:
        if args.agent_command == "add":
            agent = create_agent(
                args.db,
                group_name_or_id=args.group,
                name=args.name,
                role=args.role,
                hermes_home=args.hermes_home,
                workdir=args.workdir,
                profile_name=args.profile_name,
                model_override=args.model_override,
                provider_override=args.provider_override,
            )
            print(f"created agent {agent.id} {agent.name}")
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


def _handle_goal_command(args: argparse.Namespace) -> int:
    try:
        if args.goal_command == "submit":
            submission = submit_goal(
                args.db,
                group_name_or_id=args.group,
                goal_text=args.goal_text,
            )
            print(
                f"created goal {submission.goal.id} root_task {submission.root_task.id}"
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
    if "agents.group_id, agents.name" in message:
        return "agent name already exists in group"
    return "database write failed"


if __name__ == "__main__":
    raise SystemExit(main())
