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
REDACTION_MARKER = "[EM-DASH]"


def main(paths: list[str]) -> int:
    """Return non-zero exit code if any file contains an em-dash.

    Fails closed: a file that cannot be read is treated as a hook failure so
    the commit blocks and the operator can investigate. A silent skip would
    let a real violation slip through whenever the file also has an encoding
    issue.

    Args:
        paths: File paths supplied by pre-commit.

    Returns:
        Exit code: 0 if clean, 1 if any em-dash found, 2 if any file failed
        to read.
    """
    violations: list[tuple[str, int, str]] = []
    read_errors: list[tuple[str, str]] = []

    for p in paths:
        path = Path(p)
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            read_errors.append((p, f"read failed: {exc}"))
            continue
        except UnicodeDecodeError as exc:
            read_errors.append((p, f"not valid UTF-8: {exc}"))
            continue

        for lineno, line in enumerate(content.splitlines(), 1):
            if EM_DASH in line:
                redacted = line.replace(EM_DASH, REDACTION_MARKER).rstrip()
                violations.append((p, lineno, redacted))

    if read_errors:
        print(
            "check_no_em_dash: could not scan one or more files:",
            file=sys.stderr,
        )
        for path_str, reason in read_errors:
            print(f"  {path_str}: {reason}", file=sys.stderr)

    if violations:
        print(
            "Em-dash character (U+2014) is not allowed per global CLAUDE.md.",
            file=sys.stderr,
        )
        print(
            "The offending character has been replaced with "
            f"{REDACTION_MARKER!r} in the output below so this hook's "
            "diagnostics do not themselves contain the forbidden character:",
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

    if read_errors:
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
