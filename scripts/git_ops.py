#!/usr/bin/env python3
"""
Git operations script — single entry point for all git commands.
Usage:
    python scripts/git_ops.py status
    python scripts/git_ops.py commit "message"
    python scripts/git_ops.py push
    python scripts/git_ops.py pull
    python scripts/git_ops.py log
    python scripts/git_ops.py branch <name>
    python scripts/git_ops.py checkout <branch>
    python scripts/git_ops.py diff
"""

import subprocess
import sys


def run(cmd: list[str]) -> None:
    """Run a git command and print output."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if result.returncode != 0:
        sys.exit(result.returncode)


def status() -> None:
    """Show git status."""
    run(["git", "status", "--short"])


def commit(message: str, *paths: str) -> None:
    """Commit with message. Stage all by default, or only the given paths."""
    if paths:
        run(["git", "add", "--", *paths])
    else:
        run(["git", "add", "."])
    run(["git", "commit", "-m", message])


def push() -> None:
    """Push to current branch."""
    run(["git", "push"])


def pull() -> None:
    """Pull latest from current branch."""
    run(["git", "pull"])


def log() -> None:
    """Show last 10 commits."""
    run(["git", "log", "--oneline", "-n", "10"])


def branch(name: str) -> None:
    """Create and switch to a new branch."""
    run(["git", "checkout", "-b", name])


def checkout(name: str) -> None:
    """Switch to an existing branch."""
    run(["git", "checkout", name])


def diff() -> None:
    """Show unstaged changes."""
    run(["git", "diff", "--stat"])


COMMANDS = {
    "status": (status, 0),
    "commit": (commit, 1),
    "push": (push, 0),
    "pull": (pull, 0),
    "log": (log, 0),
    "branch": (branch, 1),
    "checkout": (checkout, 1),
    "diff": (diff, 0),
}


def main() -> None:
    """Parse command and execute."""
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Usage: python scripts/git_ops.py <command> [args]")
        print(f"Commands: {', '.join(COMMANDS.keys())}")
        sys.exit(1)

    cmd_name = sys.argv[1]
    func, expected_args = COMMANDS[cmd_name]

    args = sys.argv[2:]
    if len(args) < expected_args:
        print(f"Error: '{cmd_name}' requires {expected_args} argument(s)")
        sys.exit(1)

    # commit accepts extra path arguments beyond the message; others are fixed-arity.
    if cmd_name == "commit":
        func(*args)
    else:
        func(*args[:expected_args])


if __name__ == "__main__":
    main()
