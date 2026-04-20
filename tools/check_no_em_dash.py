#!/usr/bin/env python3
"""Pre-commit hook: reject em-dash characters (U+2014) in text files.

Global CLAUDE.md forbids the em-dash character in any output. This script
is invoked by a pre-commit hook over the files being committed and exits
non-zero with a report of any em-dash occurrences found.

Usage:
    python tools/check_no_em_dash.py FILE [FILE ...]

Notes:
    The em-dash character is referenced via its Unicode escape in this script
    to keep the source free of the character itself while still enforcing the
    rule against it.
"""

from __future__ import annotations

import sys
from pathlib import Path

EM_DASH = "\u2014"


def main(paths: list[str]) -> int:
    """Return non-zero exit code if any file contains an em-dash.

    Args:
        paths: File paths supplied by pre-commit.

    Returns:
        Exit code: 0 if clean, 1 if any em-dash found or a file failed to read.
    """
    violations: list[tuple[str, int, str]] = []
    for p in paths:
        path = Path(p)
        try:
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                if EM_DASH in line:
                    violations.append((p, lineno, line.rstrip()))
        except (OSError, UnicodeDecodeError):
            # Binary or unreadable files are silently skipped; types_or
            # filter in .pre-commit-config.yaml limits us to text files.
            continue

    if violations:
        print(
            "Em-dash character (U+2014) is not allowed per global CLAUDE.md:",
            file=sys.stderr,
        )
        for path_str, lineno, text in violations:
            print(f"  {path_str}:{lineno}: {text}", file=sys.stderr)
        print(
            "Replace with a hyphen, comma, semicolon, colon, "
            "or restructure the sentence.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
