---
title: "Consolidation and Standards Alignment Plan"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Executable plan for consolidating two divergent local clones into the dashed copy and aligning with global standards."
tags:
  - planning
  - project_management
  - scope
component: Context
source: "Local clone divergence audit 2026-04-19"
---

> **Target**: `/home/byron/dev/llc-manager/` (dashed clone, authoritative)
> **Source**: `/home/byron/dev/llc_manager/` (underscore clone, to be deleted after migration)
> **Supersedes**: `/home/byron/dev/llc-manager/MIGRATION-PLAN.md` (kept for provenance, corrected here)
> **Created**: 2026-04-20

---

## Context

Two local clones of `ByronWilliamsCPA/llc-manager` have diverged:

- **Dashed** (`llc-manager/`): on `feat/phase-0-foundation`, 15 commits including real Phase 0 implementation, expanded `tech-spec.md` (453 lines), real ADR-001, `PROJECT-PLAN.md`, and `SECURITY.md`. **Authoritative target**.
- **Underscore** (`llc_manager/`): on `main`, only 2 commits (abandoned early fork), but contains a few files the dashed copy lacks.

The existing `MIGRATION-PLAN.md` at the repo root was drafted from two audit agents that inspected the wrong folder on several checks. Exploration confirmed the corrections below. This plan is a corrected, executable replacement.

Goal: one branch off `feat/phase-0-foundation` that (a) imports the handful of files unique to underscore, (b) reconciles per-file drift with defensive diff review, (c) cleans tracked build artifacts, (d) fixes hard-rule blockers, (e) closes the standards-alignment gaps from global `CLAUDE.md` v1.4.0. Then delete the underscore folder.

---

## Corrections to the prior plan (verified against disk)

| Prior plan claim | Verified reality |
|---|---|
| `.claude/commands/plan.md` exists in underscore | **Missing in both** - do not copy |
| `.claude/skills/project-planning/` is a full skill with templates and scripts | **Only `SKILL.md`** in underscore - evaluate whether it's worth importing |
| `docs/ADRs/` in underscore is distinct content | **Only `README.md` + `adr-template.md`** - process scaffolding, not decisions. Dashed's `docs/planning/adr/` is the real ADR home and already has ADR-001 and a template. **Skip the import.** |
| `docs/planning/tech-spec.md` is 62 lines in dashed, 453 in underscore - take underscore | **Reversed**: dashed is 453 lines, underscore is 59 lines - **keep dashed** |
| Underscore has an extra merge commit `91170ba` merging PR #3 that must be rebased | Underscore `main` is only 2 commits; no merge commit is unique. Remote state is unchanged. |
| Build artifacts (`coverage.xml`, `htmlcov/`, `site/`, `.pytest_cache/`, `.sonarlint/`) are just on disk | **Tracked in git** despite being in `.gitignore`. Requires `git rm --cached -r`, not just `rm`. |
| `.coverage` is tracked | Not present - ignore that row |

Files that still hold unique value in underscore (verified):

- `CLAUDE.md` (25,836 bytes vs dashed's 5,477 - dashed is the truncated one)
- `docs/PROJECT_SETUP.md`
- `.github/workflows/sonarcloud.yml`
- `docs/planning/project-plan-template.md`
- `LICENSES/Apache-2.0.txt`, `BSD-3-Clause.txt`, `GPL-3.0-or-later.txt`
- `.claude/skills/project-planning/SKILL.md` (evaluate before importing)

---

## Strategy

One long-lived branch, executed in ordered phases. Per-file drift review (user-selected) means every file in Phase B gets a `diff -u` before the direction is accepted. Commits are grouped by phase so the PR is reviewable.

Branch name: `chore/consolidate-with-underscore-clone`
Base: `feat/phase-0-foundation`
PR target: `feat/phase-0-foundation` (not `main` - Phase 0 PR is still the integration path)

---

## Phase A: Branch setup

```bash
cd /home/byron/dev/llc-manager
git checkout feat/phase-0-foundation
git pull --ff-only
git checkout -b chore/consolidate-with-underscore-clone
```

Verify working tree clean except for `MIGRATION-PLAN.md` (untracked); leave that file in place for now - it is replaced by this document at commit time.

---

## Phase B: Per-file drift reconciliation

For every file in the table below, execute:

```bash
SRC=/home/byron/dev/llc_manager
DST=/home/byron/dev/llc-manager
diff -u "$DST/<path>" "$SRC/<path>" | less
```

Then apply the direction in the `Action` column. Commit each logical group separately.

### B.1 - Documentation and project guidance

| Path | Action | Rationale |
|---|---|---|
| `CLAUDE.md` | Take underscore | 25.8 KB vs 5.5 KB; dashed is truncated. Re-add any dashed-only project-specific blocks by diff. |
| `README.md` | Diff-and-merge | Sizes are similar; merge any underscore-only sections, keep dashed's markdown fixes |
| `docs/planning/README.md` | Diff and choose newer | Not analyzed previously |
| `docs/planning/adr/README.md` | Diff and choose newer | Not analyzed previously |
| `docs/planning/project-vision.md` | Diff and choose newer | Not analyzed previously |
| `docs/planning/roadmap.md` | Diff and choose newer | Not analyzed previously |
| `docs/planning/tech-spec.md` | **Take dashed** | Dashed is 453 lines (richer) - **prior plan had direction reversed** |
| `docs/api-reference.md` | Diff and choose newer | Not analyzed previously |

### B.2 - Configuration files

| Path | Action | Verify before accepting |
|---|---|---|
| `pyproject.toml` | Take dashed | Compare dependency versions; if underscore has newer, cherry-pick specific bumps |
| `.pre-commit-config.yaml` | Take dashed | Better exclusions; check for underscore-only hooks |
| `.gitignore` | Take dashed | Merge any underscore-only patterns |
| `REUSE.toml` | Merge | Dashed refines per-directory SPDX; underscore references extra LICENSES files |
| `.markdownlint.json` | Take dashed | Visual confirm only |
| `.cruft.json` | Take dashed | Confirm template version |
| `docker-compose.yml` | Take dashed | Confirm no underscore-only services |
| `alembic.ini` | Take dashed | UV-compatible path |
| `alembic/env.py` | Diff | Not previously analyzed |
| `.github/workflows/fips-compatibility.yml` | Take dashed | Verify permission scoping |

### B.3 - Source code (dashed is authoritative: has Phase 0 refactors)

| Path | Action |
|---|---|
| `src/llc_manager/core/cache.py` | Take dashed |
| `src/llc_manager/core/exceptions.py` | Take dashed (`details` dict refactor) |
| `src/llc_manager/core/sentry.py` | Take dashed (`@dataclass SentryConfig`) |
| `src/llc_manager/middleware/__init__.py` | Take dashed |
| `src/llc_manager/middleware/correlation.py` | Take dashed |
| `src/llc_manager/middleware/security.py` | Take dashed |
| `src/llc_manager/models/entity.py` | Take dashed (`foreign_keys=...` fix) |
| `frontend/src/components/ApiStatus.tsx` | Take dashed |
| `scripts/check_fips_compatibility.py` | Take dashed |
| `scripts/check_type_hints.py` | Diff |
| `tests/test_example.py` | Take dashed |
| `tests/unit/test_exceptions.py` | Take dashed |

Commit suggestion: `chore(consolidate): reconcile drift files from underscore clone`

---

## Phase C: Import missing files from underscore

```bash
SRC=/home/byron/dev/llc_manager
DST=/home/byron/dev/llc-manager

cp "$SRC/docs/PROJECT_SETUP.md" "$DST/docs/"
cp "$SRC/docs/planning/project-plan-template.md" "$DST/docs/planning/"
cp "$SRC/.github/workflows/sonarcloud.yml" "$DST/.github/workflows/"

# LICENSES - only the three dashed is missing
cp "$SRC/LICENSES/Apache-2.0.txt" "$DST/LICENSES/"
cp "$SRC/LICENSES/BSD-3-Clause.txt" "$DST/LICENSES/"
cp "$SRC/LICENSES/GPL-3.0-or-later.txt" "$DST/LICENSES/"

# Optional: project-planning skill stub (only if SKILL.md content is useful to the project)
# cp "$SRC/.claude/skills/project-planning/SKILL.md" "$DST/.claude/skills/project-planning/"
```

Explicitly **skip**:

- `docs/ADRs/` (underscore has only template scaffolding; dashed already has the real ADR home at `docs/planning/adr/`)
- `.claude/commands/plan.md` (does not exist in underscore either)

Commit suggestion: `feat(consolidate): import project setup guide, sonarcloud workflow, SPDX license texts`

---

## Phase D: Clean tracked build artifacts and binary

Critical correction from the prior plan: several of these are **tracked in git**, not just on disk. They need `git rm --cached` followed by a commit, then also physical removal.

```bash
cd /home/byron/dev/llc-manager

# Remove from git index (they're gitignored but currently tracked)
git rm -r --cached coverage.xml htmlcov site .pytest_cache .sonarlint 2>/dev/null || true

# Physical removal of untracked artifacts
rm -f tailwindcss .coverage
rm -rf .qlty/out .qlty/logs .qlty/plugin_cachedir .qlty/results

# Verify every path is now either ignored or absent
for p in tailwindcss coverage.xml htmlcov site .pytest_cache .sonarlint .coverage; do
  git check-ignore -q "$p" && echo "ignored: $p" || echo "MISSING-OR-NOT-IGNORED: $p"
done
```

Commit suggestion: `chore(consolidate): untrack generated build artifacts`

---

## Phase E: Fix hard-rule blockers

### E.1 - Em-dash in source

`tools/validate_front_matter.py:212` contains the em-dash character (U+2014) in the error-message format string. Global CLAUDE.md forbids this character in any output.

```bash
sed -i $'s/\u2014/-/g' tools/validate_front_matter.py
```

Then grep the whole repo for stray em-dashes and fix any others found:

```bash
grep -rn $'\u2014' --include="*.py" --include="*.md" --include="*.yml" --include="*.yaml" .
```

### E.2 - Create `docs/known-vulnerabilities.md`

Required by global CLAUDE.md (unfixed-CVE policy). Create an empty entry file; do not leave missing:

```bash
cat > docs/known-vulnerabilities.md <<'EOF'
# Known Vulnerabilities

No accepted unfixed CVEs as of 2026-04-20. See global CLAUDE.md for entry
format and the 60-day reassessment requirement. Every `pip-audit` finding
that is not immediately resolved must be recorded here before the suppression
is merged.
EOF
```

### E.3 - Suppressions audit

Grep `src/` for suppressions without ticket references and either fix or annotate:

```bash
grep -rnE "# (noqa|type: ignore)(?!.*#\d)" src/
grep -rn "pytest.mark.skip" tests/
grep -rn "\-\-no-verify" .pre-commit-config.yaml .github/ scripts/
```

Each hit must either be removed (fix the underlying cause) or paired with a tracking comment like `# noqa: E501 - tracked in #ISSUE-NUM`.

Commit suggestion: `fix(consolidate): resolve hard-rule blockers (em-dash, known-vulns, suppressions)`

---

## Phase F: Standards alignment

### F.1 - Ruff sweep

```bash
uv run ruff format .
uv run ruff check . --fix
uv run ruff check .   # address remaining, especially DTZ011, INP001
```

Common residual fixes:

- `date.today()` → `datetime.now(UTC).date()` (DTZ011)
- Missing `__init__.py` in Python packages (INP001) - verify `alembic/` and `alembic/versions/` still have theirs after the migration

### F.2 - BasedPyright strict sweep

```bash
uv run basedpyright src/
```

Address all errors; warnings may be triaged in follow-ups but must be at zero before merging the PR. Start with unused imports (e.g., unused `UUID` import in `entity.py`) and explicit type annotations for `Any` usages.

### F.3 - Codecov tiers

Open `codecov.yml` and confirm all four tiers are defined:

- Line coverage: 80% project target
- Branch coverage: 70%
- Critical-path coverage: 90% (flag `critical` or component equivalent)
- Patch coverage: 90%

If any tier is missing, add it per `~/.claude/standards/packages.md` guidance.

### F.4 - RAD assumption tags

Add `#CRITICAL`, `#ASSUME`, `#EDGE`, `#VERIFY` markers per `docs/response-aware-development.md` (global reference) to these priority files:

- `src/llc_manager/db/session.py` - async session lifecycle, connection pool assumptions
- `src/llc_manager/core/sentry.py` - Sentry SDK init timing and DSN fallback
- `src/llc_manager/middleware/security.py` - SSRF protection assumptions
- `src/llc_manager/middleware/correlation.py` - async-context propagation

Focus on timing, external resources, data integrity, concurrency, and security paths. Pair each assumption tag with a `#VERIFY` instruction so the next reader knows how to confirm it.

### F.5 - Pre-commit em-dash hook

Add a local em-dash detection hook to `.pre-commit-config.yaml`:

```yaml
- repo: local
  hooks:
    - id: no-em-dash
      name: Reject em-dash characters
      entry: bash -c 'grep -rn $'"'"'\u2014'"'"' --include="*.py" --include="*.md" --include="*.yml" --include="*.yaml" --include="*.toml" . && exit 1 || exit 0'
      language: system
      pass_filenames: false
```

Commit suggestion: `chore(consolidate): align with global standards (ruff, types, codecov, RAD)`

---

## Phase G: Gate run and push

```bash
uv sync --all-extras
uv run ruff format .
uv run ruff check .
uv run basedpyright src/
uv run pytest --cov=src --cov-fail-under=80
uv run bandit -r src
uv run pip-audit
pre-commit run --all-files
```

All gates must pass with no suppressions introduced. If `pip-audit` flags a CVE, add an entry to `docs/known-vulnerabilities.md` before committing.

Delete `MIGRATION-PLAN.md` at the repo root (superseded by this plan):

```bash
git rm MIGRATION-PLAN.md
```

Final commit and push:

```bash
git add -A
git status        # sanity check
git commit -m "chore: consolidate divergent clones and align with global standards"
git push -u origin chore/consolidate-with-underscore-clone
```

Open a PR against `feat/phase-0-foundation`. The PR description should reference this plan file path.

---

## Phase H: Verify and delete underscore clone

After the PR merges:

```bash
# Compare working trees to catch anything that slipped past the migration
diff -rq /home/byron/dev/llc-manager /home/byron/dev/llc_manager \
  | grep -v -E '\.git/|\.worktrees/|node_modules/|\.venv/|htmlcov/|site/' \
  > /tmp/final-diff-check.txt
less /tmp/final-diff-check.txt
```

Expected leftover differences after migration: only ephemeral state (caches, coverage outputs) and files legitimately excluded (tailwindcss, build directories).

Once satisfied:

```bash
rm -rf /home/byron/dev/llc_manager
```

---

## Verification checklist (end-to-end)

Run this checklist before marking the consolidation done:

- [ ] `git log --oneline feat/phase-0-foundation..chore/consolidate-with-underscore-clone` shows one commit per phase, no fixup noise
- [ ] `git ls-files | grep -E '(coverage\.xml|htmlcov/|site/|\.pytest_cache/|\.sonarlint/|tailwindcss$)'` returns empty
- [ ] `diff <(wc -c < CLAUDE.md) <(echo 25836)` closes on the merged CLAUDE.md size (or larger, if dashed-only content was preserved)
- [ ] `ls docs/PROJECT_SETUP.md .github/workflows/sonarcloud.yml docs/planning/project-plan-template.md LICENSES/Apache-2.0.txt LICENSES/BSD-3-Clause.txt LICENSES/GPL-3.0-or-later.txt` all exist
- [ ] `grep -c $'\u2014' tools/validate_front_matter.py` returns 0
- [ ] `test -f docs/known-vulnerabilities.md`
- [ ] `uv run ruff check .` exits 0
- [ ] `uv run basedpyright src/` exits 0 errors
- [ ] `uv run pytest --cov=src --cov-fail-under=80` passes
- [ ] `pre-commit run --all-files` passes, including the new em-dash hook
- [ ] RAD tags are present in the four priority files
- [ ] `/home/byron/dev/llc_manager/` no longer exists

---

## Critical files referenced

- `/home/byron/dev/llc-manager/MIGRATION-PLAN.md` - prior plan, to be deleted by this work
- `/home/byron/dev/llc-manager/tools/validate_front_matter.py` - em-dash fix at line 212
- `/home/byron/dev/llc-manager/CLAUDE.md` - target of cross-clone merge
- `/home/byron/dev/llc-manager/.pre-commit-config.yaml` - add em-dash hook here
- `/home/byron/dev/llc-manager/.gitignore` - verify it still covers everything being untracked
- `/home/byron/dev/llc-manager/codecov.yml` - verify four-tier coverage
- `/home/byron/.claude/CLAUDE.md` v1.4.0 - global standards source of truth
- `/home/byron/dev/llc-manager/docs/response-aware-development.md` - RAD tagging syntax (if present; otherwise fall back to global reference)

---

## Open items for the maintainer (carry-overs)

1. `.claude/skills/project-planning/SKILL.md` in underscore - import only if the skill content is relevant to this project; otherwise drop
2. `.vscode/` - decide whether to gitignore (currently committed in dashed)
3. `LICENSES/` - confirm Apache-2.0, BSD-3-Clause, GPL-3.0-or-later are genuinely required by source headers; if not, do not import
