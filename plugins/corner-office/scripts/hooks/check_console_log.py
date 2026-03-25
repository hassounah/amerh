#!/usr/bin/env python3

"""
Stop Hook: Check for console.log statements in modified files

This hook runs after each response and checks if any modified
JavaScript/TypeScript files contain console.log statements.
It provides warnings to help developers remember to remove
debug statements before committing.
"""

import os
import subprocess
import sys


def main():
    # Read all stdin first
    data = sys.stdin.read()

    try:
        # Check if we're in a git repository
        try:
            subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Not in a git repo, just pass through the data
            print(data, end="")
            return

        # Get list of modified files
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
        )
        files = [
            f
            for f in result.stdout.strip().split("\n")
            if f
            and f.endswith((".ts", ".tsx", ".js", ".jsx"))
            and os.path.exists(f)
        ]

        has_console = False

        # Check each file for console.log
        for file in files:
            try:
                with open(file, "r", encoding="utf-8") as fh:
                    content = fh.read()
                if "console.log" in content:
                    print(
                        f"[Hook] WARNING: console.log found in {file}",
                        file=sys.stderr,
                    )
                    has_console = True
            except OSError:
                continue

        if has_console:
            print(
                "[Hook] Remove console.log statements before committing",
                file=sys.stderr,
            )
    except Exception:
        # Silently ignore errors (git might not be available, etc.)
        pass

    # Always output the original data
    print(data, end="")


if __name__ == "__main__":
    main()
