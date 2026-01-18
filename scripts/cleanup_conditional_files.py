#!/usr/bin/env python3
"""Clean up conditional files based on .cruft.json context.

This script reads the cookiecutter context from .cruft.json and removes
files that should not exist based on the feature flags configured during
project generation.

IMPORTANT: Run this script after `cruft update` to ensure conditional files
are properly removed. Cruft updates only sync file contents - it does NOT
re-run post-generation hooks that clean up conditional files.

Usage:
    python scripts/cleanup_conditional_files.py [--dry-run]

Options:
    --dry-run    Show what would be removed without actually removing

Example:
    # After running cruft update
    cruft update
    python scripts/cleanup_conditional_files.py

    # Preview what would be removed
    python scripts/cleanup_conditional_files.py --dry-run
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def get_cruft_context() -> dict[str, str]:
    """Read cookiecutter context from .cruft.json.

    Returns:
        Dictionary of cookiecutter context values.

    Raises:
        FileNotFoundError: If .cruft.json doesn't exist.
        json.JSONDecodeError: If .cruft.json is invalid JSON.
    """
    cruft_file = Path(".cruft.json")
    if not cruft_file.exists():
        msg = ".cruft.json not found. Is this a cruft-managed project?"
        raise FileNotFoundError(msg)

    cruft_data = json.loads(cruft_file.read_text())
    return cruft_data.get("context", {}).get("cookiecutter", {})


def remove_file(filepath: Path, dry_run: bool = False) -> bool:
    """Remove a file if it exists.

    Args:
        filepath: Path to the file to remove.
        dry_run: If True, only report what would be removed.

    Returns:
        True if file was removed (or would be), False if file didn't exist.
    """
    if filepath.exists():
        if dry_run:
            print(f"  [DRY RUN] Would remove: {filepath}")
        else:
            filepath.unlink()
            print(f"  ✓ Removed: {filepath}")
        return True
    return False


def remove_dir(dirpath: Path, dry_run: bool = False) -> bool:
    """Remove a directory if it exists.

    Args:
        dirpath: Path to the directory to remove.
        dry_run: If True, only report what would be removed.

    Returns:
        True if directory was removed (or would be), False if it didn't exist.
    """
    if dirpath.exists():
        if dry_run:
            print(f"  [DRY RUN] Would remove: {dirpath}/")
        else:
            shutil.rmtree(dirpath)
            print(f"  ✓ Removed: {dirpath}/")
        return True
    return False


def get_project_slug(context: dict) -> str:
    """Extract project_slug from context.

    Args:
        context: Cookiecutter context dictionary.

    Returns:
        Project slug string.
    """
    return context.get("project_slug", "")


def cleanup_conditional_files(context: dict, dry_run: bool = False) -> int:
    """Remove files based on cookiecutter context settings.

    Args:
        context: Cookiecutter context from .cruft.json.
        dry_run: If True, only report what would be removed.

    Returns:
        Number of files/directories removed.
    """
    project_slug = get_project_slug(context)
    if not project_slug:
        print("❌ Could not determine project_slug from .cruft.json")
        return 0

    removed_count = 0
    src_dir = Path(f"src/{project_slug}")

    print("\n🧹 Cleaning up conditional files...")

    # CLI
    if context.get("include_cli") == "no":
        if remove_file(src_dir / "cli.py", dry_run):
            removed_count += 1

    # MkDocs
    if context.get("use_mkdocs") == "no":
        if remove_file(Path("mkdocs.yml"), dry_run):
            removed_count += 1
        if remove_dir(Path("docs"), dry_run):
            removed_count += 1
        if remove_file(Path("tools/validate_front_matter.py"), dry_run):
            removed_count += 1
        if remove_dir(Path("tools/frontmatter_contract"), dry_run):
            removed_count += 1

    # Nox
    if context.get("include_nox") == "no":
        if remove_file(Path("noxfile.py"), dry_run):
            removed_count += 1

    # Pre-commit
    if context.get("use_pre_commit") == "no":
        if remove_file(Path(".pre-commit-config.yaml"), dry_run):
            removed_count += 1

    # Code of Conduct
    if context.get("include_code_of_conduct") == "no":
        if remove_file(Path("CODE_OF_CONDUCT.md"), dry_run):
            removed_count += 1

    # Security Policy
    if context.get("include_security_policy") == "no":
        if remove_file(Path("SECURITY.md"), dry_run):
            removed_count += 1

    # Contributing Guide
    if context.get("include_contributing_guide") == "no":
        if remove_file(Path("CONTRIBUTING.md"), dry_run):
            removed_count += 1

    # Codecov
    if context.get("include_codecov") == "no":
        if remove_file(Path("codecov.yml"), dry_run):
            removed_count += 1
        if remove_file(Path(".github/workflows/codecov.yml"), dry_run):
            removed_count += 1

    # SonarCloud
    if context.get("include_sonarcloud") == "no":
        if remove_file(Path("sonar-project.properties"), dry_run):
            removed_count += 1
        if remove_file(Path(".github/workflows/sonarcloud.yml"), dry_run):
            removed_count += 1

    # Renovate
    if context.get("include_renovate") == "no":
        if remove_file(Path("renovate.json"), dry_run):
            removed_count += 1

    # CodeRabbit
    if context.get("include_coderabbit") == "no":
        if remove_file(Path(".coderabbit.yaml"), dry_run):
            removed_count += 1

    # Semantic Release
    if context.get("include_semantic_release") == "no":
        if remove_file(Path(".github/workflows/release.yml"), dry_run):
            removed_count += 1

    # REUSE Licensing
    if context.get("use_reuse_licensing") == "no":
        if remove_file(Path("REUSE.toml"), dry_run):
            removed_count += 1
        if remove_dir(Path("LICENSES"), dry_run):
            removed_count += 1
        if remove_file(Path(".github/workflows/reuse.yml"), dry_run):
            removed_count += 1

    # Docker
    if context.get("include_docker") == "no":
        if remove_file(Path("Dockerfile"), dry_run):
            removed_count += 1
        if remove_file(Path("docker-compose.yml"), dry_run):
            removed_count += 1
        if remove_file(Path("docker-compose.prod.yml"), dry_run):
            removed_count += 1
        if remove_file(Path(".dockerignore"), dry_run):
            removed_count += 1
        if remove_file(Path(".github/workflows/container-security.yml"), dry_run):
            removed_count += 1

    # API Framework / Health Checks
    if context.get("include_api_framework") == "no":
        api_dir = src_dir / "api"
        if remove_dir(api_dir, dry_run):
            removed_count += 1
        if remove_file(src_dir / "middleware" / "security.py", dry_run):
            removed_count += 1
        if remove_file(src_dir / "middleware" / "correlation.py", dry_run):
            removed_count += 1
        # Remove middleware dir if empty
        middleware_dir = src_dir / "middleware"
        if middleware_dir.exists() and not any(
            f
            for f in middleware_dir.iterdir()
            if f.name not in ("__pycache__", "__init__.py")
        ):
            if remove_dir(middleware_dir, dry_run):
                removed_count += 1
    elif context.get("include_health_checks") == "no":
        # Only health checks disabled but API framework enabled
        if remove_file(src_dir / "api" / "health.py", dry_run):
            removed_count += 1

    # Sentry
    if context.get("include_sentry") == "no":
        if remove_file(src_dir / "core" / "sentry.py", dry_run):
            removed_count += 1

    # Background Jobs
    if context.get("include_background_jobs") == "no":
        if remove_dir(src_dir / "jobs", dry_run):
            removed_count += 1

    # Caching
    if context.get("include_caching") == "no":
        if remove_file(src_dir / "core" / "cache.py", dry_run):
            removed_count += 1

    # Load Testing
    if context.get("include_load_testing") == "no":
        if remove_dir(Path("tests/load"), dry_run):
            removed_count += 1

    # Fuzzing
    if context.get("include_fuzzing") == "no":
        if remove_file(Path(".github/workflows/cifuzzy.yml"), dry_run):
            removed_count += 1
        if remove_dir(Path(".clusterfuzzlite"), dry_run):
            removed_count += 1
        if remove_dir(Path("fuzz"), dry_run):
            removed_count += 1

    # GitHub Actions
    if context.get("include_github_actions") == "no":
        if remove_dir(Path(".github"), dry_run):
            removed_count += 1

    # MkDocs workflow (separate from MkDocs files)
    if context.get("use_mkdocs") == "no":
        if remove_file(Path(".github/workflows/docs.yml"), dry_run):
            removed_count += 1

    return removed_count


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("🔍 Running in dry-run mode (no files will be removed)")

    try:
        context = get_cruft_context()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in .cruft.json: {e}")
        return 1

    removed_count = cleanup_conditional_files(context, dry_run)

    if removed_count > 0:
        action = "would be removed" if dry_run else "removed"
        print(f"\n✅ {removed_count} file(s)/directory(ies) {action}")
    else:
        print("\n✅ No orphaned files found - project is clean!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
