#!/usr/bin/env python3
"""Validate project planning documents for completeness and consistency.

This script checks:
1. Required files exist
2. Documents have required sections
3. No placeholder text remains
4. Cross-references are valid
5. Documents meet length guidelines
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


def count_words(text: str) -> int:
    """Count words in text, excluding code blocks."""
    # Remove code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    return len(text.split())


def check_placeholders(content: str, filepath: Path) -> list[str]:
    """Check for remaining placeholder text."""
    issues = []
    placeholders = [
        r"\[TODO\]",
        r"\[TBD\]",
        r"\[PLACEHOLDER\]",
        r"\[Project Name\]",
        r"\[Date\]",
        r"\[Name\]",
        r"\[Description\]",
        r"\[YYYY-MM-DD\]",
    ]

    for pattern in placeholders:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            issues.append(
                f"{filepath}: Found placeholder '{matches[0]}' ({len(matches)} occurrences)"
            )

    return issues


def check_required_sections(
    content: str, filepath: Path, required: list[str]
) -> list[str]:
    """Check that required sections exist."""
    issues = []
    for section in required:
        # Check for section as H2 or H3
        pattern = rf"^##\s*{re.escape(section)}|^###\s*{re.escape(section)}"
        if not re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
            issues.append(f"{filepath}: Missing required section '{section}'")
    return issues


def check_tldr(content: str, filepath: Path) -> list[str]:
    """Check for TL;DR section."""
    if not re.search(r"##\s*TL;DR|^TL;DR", content, re.MULTILINE | re.IGNORECASE):
        return [f"{filepath}: Missing TL;DR section"]
    return []


def check_cross_references(content: str, filepath: Path, docs_dir: Path) -> list[str]:
    """Check that cross-references point to existing files."""
    issues = []
    # Find markdown links to local files
    links = re.findall(r"\[([^\]]+)\]\(\.?/?([^)]+\.md)\)", content)

    for link_text, link_path in links:
        # Skip external links
        if link_path.startswith("http"):
            continue

        # Resolve relative to docs/planning/
        link_path = link_path.removeprefix("./")

        target = docs_dir / link_path
        if not target.exists():
            issues.append(
                f"{filepath}: Broken link to '{link_path}' (text: '{link_text}')"
            )

    return issues


def _check_common_issues(
    content: str, filepath: Path, required_sections: list[str]
) -> list[str]:
    """Run common validation checks shared by all document types."""
    issues = []
    issues.extend(check_required_sections(content, filepath, required_sections))
    issues.extend(check_tldr(content, filepath))
    issues.extend(check_placeholders(content, filepath))
    return issues


def _check_word_count(content: str, filepath: Path, max_words: int) -> list[str]:
    """Check document word count against maximum."""
    word_count = count_words(content)
    if word_count > max_words:
        return [f"{filepath}: Too long ({word_count} words, max {max_words})"]
    return []


def validate_pvs(content: str, filepath: Path) -> list[str]:
    """Validate Project Vision & Scope document."""
    issues = _check_word_count(content, filepath, max_words=1000)
    required = ["Problem", "Solution", "Scope", "Constraints"]
    issues.extend(_check_common_issues(content, filepath, required))
    return issues


def validate_tech_spec(content: str, filepath: Path) -> list[str]:
    """Validate Technical Specification document."""
    issues = _check_word_count(content, filepath, max_words=2000)
    required = ["Technology Stack", "Architecture", "Data Model"]
    issues.extend(_check_common_issues(content, filepath, required))
    return issues


def validate_roadmap(content: str, filepath: Path) -> list[str]:
    """Validate Development Roadmap document."""
    issues = _check_word_count(content, filepath, max_words=1500)
    required = ["Timeline", "Phase", "Milestone"]
    issues.extend(_check_common_issues(content, filepath, required))
    return issues


def validate_adr(content: str, filepath: Path) -> list[str]:
    """Validate Architecture Decision Record."""
    issues = _check_word_count(content, filepath, max_words=800)
    required = ["Context", "Decision", "Consequences"]
    issues.extend(_check_common_issues(content, filepath, required))

    if not re.search(
        r"Status.*:.*\b(Proposed|Published|Accepted|Deprecated|Superseded)\b",
        content,
        re.IGNORECASE,
    ):
        issues.append(f"{filepath}: Missing or invalid Status field")

    return issues


ValidatorFunc = Callable[[str, Path], list[str]]


@dataclass
class ValidationResult:
    """Container for validation results."""

    issues: list[str] = field(default_factory=list)
    files_checked: int = 0

    def add_issues(self, new_issues: list[str]) -> None:
        """Add issues to the result."""
        self.issues.extend(new_issues)


def _validate_required_files(
    docs_dir: Path,
    required_files: list[tuple[str, ValidatorFunc]],
) -> ValidationResult:
    """Validate required planning documents."""
    result = ValidationResult()

    for filename, validator in required_files:
        filepath = docs_dir / filename
        if not filepath.exists():
            result.add_issues([f"Missing required file: {filepath}"])
            continue

        content = filepath.read_text()
        result.files_checked += 1

        if "Awaiting Generation" in content:
            result.add_issues(
                [f"{filepath}: Document not yet generated (still placeholder)"]
            )
            continue

        result.add_issues(validator(content, filepath))
        result.add_issues(check_cross_references(content, filepath, docs_dir))

    return result


def _validate_adr_files(docs_dir: Path) -> ValidationResult:
    """Validate ADR files in the adr directory."""
    result = ValidationResult()
    adr_dir = docs_dir / "adr"

    if not adr_dir.exists():
        result.add_issues(["Missing ADR directory: docs/planning/adr/"])
        return result

    adr_files = list(adr_dir.glob("adr-*.md"))
    if not adr_files:
        result.add_issues(["No ADR files found in docs/planning/adr/"])
        return result

    for adr_file in adr_files:
        content = adr_file.read_text()
        result.files_checked += 1

        if "Awaiting Generation" in content:
            result.add_issues(
                [f"{adr_file}: ADR not yet generated (still placeholder)"]
            )
            continue

        result.add_issues(validate_adr(content, adr_file))
        result.add_issues(check_cross_references(content, adr_file, docs_dir))

    return result


def _print_report(result: ValidationResult) -> int:
    """Print validation report and return exit code."""
    print(f"\n{'=' * 60}")
    print("Project Planning Documents Validation Report")
    print(f"{'=' * 60}\n")
    print(f"Files checked: {result.files_checked}")

    if result.issues:
        print(f"Issues found: {len(result.issues)}\n")
        for issue in result.issues:
            print(f"  - {issue}")
        print(f"\n{'=' * 60}")
        return 1

    print("Status: All documents valid")
    print(f"\n{'=' * 60}")
    return 0


def main() -> int:
    """Run validation on planning documents."""
    project_root = Path.cwd()
    docs_dir = project_root / "docs" / "planning"

    if not docs_dir.exists():
        print("ERROR: docs/planning/ directory not found")
        return 1

    required_files: list[tuple[str, ValidatorFunc]] = [
        ("project-vision.md", validate_pvs),
        ("tech-spec.md", validate_tech_spec),
        ("roadmap.md", validate_roadmap),
    ]

    file_result = _validate_required_files(docs_dir, required_files)
    adr_result = _validate_adr_files(docs_dir)

    combined = ValidationResult(
        issues=file_result.issues + adr_result.issues,
        files_checked=file_result.files_checked + adr_result.files_checked,
    )

    return _print_report(combined)


if __name__ == "__main__":
    sys.exit(main())
