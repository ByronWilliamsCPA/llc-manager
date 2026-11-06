---
title: "Known Vulnerabilities"
schema_type: common
status: published
owner: core-maintainer
purpose: "Log of accepted unfixed CVEs with 60-day reassessment commitment per global CLAUDE.md policy."
tags:
  - security
  - compliance
---

Every `pip-audit` or `safety` finding that cannot be immediately resolved must
be recorded here with a mandatory 60-day reassessment. Each entry tracks both
the original `Introduced` date (when the risk was first accepted) and
`Last reassessed` (when the acceptance rationale was most recently reviewed);
`Reassess by` is always within 60 days of `Last reassessed`. The OpenSSF
release gate blocks releases for any entry whose `Last reassessed` date is
older than 60 days (see global `~/.claude/CLAUDE.md` section on unfixed CVEs).

## Format

```markdown
### CVE-ID - Package (reassessment date YYYY-MM-DD)

| Field | Value |
|-------|-------|
| **CVE** | CVE-YYYY-NNNNN |
| **Package** | package-name<=version |
| **Severity** | Low / Medium / High / Critical (CVSS X.X) |
| **Status** | Accepted risk |
| **Introduced** | YYYY-MM-DD |
| **Last reassessed** | YYYY-MM-DD |
| **Reassess by** | YYYY-MM-DD (within 60 days of Last reassessed) |

**Description**: what the vulnerability is.

**Rationale for accepting**: why this is safe in our context (platform, usage pattern, transitive-only, etc).

**Mitigation in place**: compensating controls, if any.

**Resolution path**: what will unblock a fix (upstream patch, removal of transitive dep, etc).

**Tracking**: link to issue or PR.
```

---

## Active Entries

### CVE-2025-53000 - nbconvert (reassess by 2026-06-19)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2025-53000 |
| **GHSA** | GHSA-xm59-rqc7-hhvf |
| **Package** | nbconvert<=7.16.6 (transitive dep of `jupyter`) |
| **Severity** | High (CVSS 8.5) |
| **Status** | Accepted risk |
| **Introduced** | 2026-01-18 |
| **Last reassessed** | 2026-04-20 |
| **Reassess by** | 2026-06-19 |

**Description**: Uncontrolled search-path vulnerability on Windows allowing
code execution via a malicious `inkscape.bat` file when converting notebooks
with SVG to PDF.

**Rationale for accepting**: Vulnerability is Windows-specific. Project
development and CI run on Linux; no production code path touches nbconvert.
The package is pulled in transitively by `jupyter`, which is only used for
local notebook exploration, not runtime.

**Mitigation in place**:

- CI runs exclusively on Linux runners.
- Production Docker image uses the Python 3.12 slim base (Linux), so the
  vulnerable Windows path is not reachable.
- Dependabot and `pip-audit` monitor for an upstream fix.

**Resolution path**: await upstream fix or drop the `jupyter` dev dependency
if no fix lands before the reassessment date.

**Tracking**: GHSA-xm59-rqc7-hhvf upstream advisory.
See the project `SECURITY.md` for the full risk assessment summary.

---

### CVE-2026-3219 - pip (reassess by 2026-06-27)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-3219 |
| **Package** | pip==26.0.1 (no patched version released as of 2026-04-28) |
| **Severity** | Medium |
| **Status** | Accepted risk |
| **Introduced** | 2026-04-28 |
| **Last reassessed** | 2026-04-28 |
| **Reassess by** | 2026-06-27 |

**Description**: Interpretation conflict in pip's archive handling: concatenated
tar and ZIP files are processed as ZIP files, allowing a crafted package to
execute unexpected code during installation.

**Rationale for accepting**: Production deployments use Docker with pre-built
layers; pip is not invoked against untrusted sources at runtime. In CI, package
installs come from PyPI via `uv`, which uses its own resolver and does not
delegate to pip for the vulnerable archive-extraction path. pip is present only
as a transitive tool dependency.

**Mitigation in place**:

- `uv` is the primary installer; it does not use pip's archive-extraction code.
- All PyPI packages are integrity-checked via SHA-256 hashes in `uv.lock`.
- No untrusted package feeds are configured in CI or production.

**Resolution path**: upgrade pip automatically when a patched release is
published. Monitor <https://github.com/pypa/pip/security/advisories> and
Dependabot alert #31.

**Tracking**: Dependabot alert #31; upstream advisory pending.

---

### CVE-2025-69720 - ncurses base image packages (reassess by 2027-01-05)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2025-69720 |
| **Package** | libncursesw6, libtinfo6, ncurses-base, ncurses-bin 6.5+20250216-2+dhi4 (Debian 13 packages in the hardened Python base image) |
| **Severity** | High |
| **Status** | Accepted risk |
| **Introduced** | 2026-04-29 |
| **Last reassessed** | 2026-11-06 |
| **Reassess by** | 2027-01-05 (within 60 days of Last reassessed) |

**Description**: Buffer overflow vulnerability in ncurses that may lead to arbitrary code
execution or denial of service.

**Rationale for accepting**: These packages ship as part of `python:3.12-slim` and Debian 13
has not released a patched version as of 2026-04-29. The ncurses libraries are used for
terminal handling; our FastAPI application does not expose ncurses functionality to any
network-accessible code path. Exploitability requires local access or a code path that
uses ncurses terminal APIs, neither of which is present in the runtime container.

**Mitigation in place**:

- Container runs as non-root user (`appuser`, UID 1000).
- No terminal emulation in the runtime code path.
- `.trivyignore.yaml` entry prevents CI failure until Debian releases a patch.

**Resolution path**: upgrade the base image when Debian 13 releases a patched ncurses
package. Monitor the Debian security tracker and re-run `trivy image` monthly.

**Reassessment 2026-11-06**: The earlier reassess-by date (2026-06-28) had passed.
The image built from `main` was scanned with Trivy 0.52.2 (vulnerability DB
updated 2026-11-06) with no ignore file and still reports CVE-2025-69720 against
the four packages above with a blank Fixed Version. The Debian security tracker
lists ncurses as `vulnerable` in trixie (6.5+20250216-2) and fixed only in
forky and sid (6.6+20260608-2), so the acceptance stands.

**Tracking**: Debian security tracker; no trixie patch available as of 2026-11-06.

---

### CVE-2026-66046 and four more - libexpat1 base image package (reassess by 2026-12-14)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-66046, CVE-2026-76956, CVE-2026-76957, CVE-2026-77214, CVE-2026-93990 |
| **Package** | libexpat1 2.8.3-1~deb13u1+dhi5 (Debian 13 package in the hardened Python runtime base image) |
| **Severity** | High |
| **Status** | Accepted risk |
| **Introduced** | 2026-10-15 |
| **Last reassessed** | 2026-10-15 |
| **Reassess by** | 2026-12-14 (within 60 days of Last reassessed) |

**Description**: Expat flaws reported against libexpat: quadratic complexity in
attribute processing and hash-flooding denial of service, a memory corruption
issue, a heap over-read in `XML_ParseBuffer`, and XML injection via malformed
UTF-16 input. All five are triggered by parsing attacker-supplied XML.

**Rationale for accepting**: No patched package exists. On 2026-10-15 the newest
`3.12-debian13` tag (the Dockerfile's runtime base, already rebuilt at `+dhi5`)
was scanned with Trivy 0.52.2 and still reports all five as `affected` with no
fixed version, so moving to a newer base image digest does not clear them.
`libexpat1` is required by the interpreter's `pyexpat` module and cannot be
removed from the image. The application parses no XML: the source tree has no XML
parsing, its API exchanges JSON and serves stored files read-only, and the
runtime image installs only the `api` extra (no spreadsheet or XML libraries).

**Mitigation in place**:

- No application code path passes untrusted input to an XML parser.
- The runtime image is distroless (no shell, no package manager) and runs as
  non-root UID 65532.
- `.trivyignore.yaml` entries keep the scheduled scan focused on new findings.

**Resolution path**: take the next base image digest that carries a fixed
expat and remove the `.trivyignore.yaml` entries in the same change. Re-run
`trivy image` against the `3.12-debian13` tag at each reassessment.

**Update 2026-11-06 (not a reassessment)**: A scan with the current Trivy
database now lists a fixed version, `2.9.0-1~deb13u1`, for all five of these CVEs,
and the Debian security tracker shows it in trixie-security (DSA-6566-1). The fix
is not yet in the pinned hardened base image (libexpat1 2.8.3-1~deb13u1+dhi4), so
the ignore is still needed to keep the scan green. Take the next base image
digest that carries 2.9.0-1~deb13u1 or later and remove these entries; do not
extend them past the 2026-12-14 reassess-by date.

**Tracking**: Debian security tracker; no fixed version available in the base
image as of 2026-10-15.

---

### CVE-2026-76642 and three more - libuuid1 base image package (reassess by 2026-12-14)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410 |
| **Package** | libuuid1 2.41.5-0+deb13u1+dhi3 (Debian 13 package, built from `util-linux`, in the hardened Python runtime base image) |
| **Severity** | High |
| **Status** | Accepted risk |
| **Introduced** | 2026-10-15 |
| **Last reassessed** | 2026-10-15 |
| **Reassess by** | 2026-12-14 (within 60 days of Last reassessed) |

**Description**: Flaws in `util-linux` programs: a failed external mount helper
that is still used, `nsenter --join-cgroup` leaking root, `X-mount.subdir`
handling with detached trees, and restricted bind mounts that are not pinned.
Trivy attributes them to `libuuid1` because the library is built from the
`util-linux` source package.

**Rationale for accepting**: No patched package exists (no fixed version on
2026-10-15, including in the newest `3.12-debian13` tag). The vulnerable code
lives in `mount` and `nsenter`; the distroless runtime image ships only the
`libuuid` shared library, and a listing of the image on 2026-10-15 found no
`mount` or `nsenter` binary. The container has no shell or package manager, so
no one can reach those programs from inside it.

**Mitigation in place**:

- The vulnerable programs are not present in the runtime image.
- The runtime image is distroless and runs as non-root UID 65532.
- `.trivyignore.yaml` entries keep the scheduled scan focused on new findings.

**Resolution path**: take the next base image digest that carries a fixed
`util-linux` and remove the `.trivyignore.yaml` entries in the same change.

**Tracking**: Debian security tracker; no fixed version available as of
2026-10-15.

---

### CVE-2026-113351 and three more - libexpat1 base image package, second batch (reassess by 2027-01-05)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-113351, CVE-2026-115506, CVE-2026-117610, CVE-2026-118370 |
| **Package** | libexpat1 2.8.3-1~deb13u1+dhi4 (Debian 13 package in the pinned hardened Python runtime base image) |
| **Severity** | High |
| **Status** | Accepted risk |
| **Introduced** | 2026-11-04 |
| **Last reassessed** | 2026-11-06 |
| **Reassess by** | 2027-01-05 (within 60 days of Last reassessed) |

**Description**: Four more Expat denial-of-service flaws: improper memory
tracking in `XML_ParserReset`, delayed entity amplification detection, a NULL
pointer dereference in external entity parsing, and an integer overflow during
XML attribute parsing. All four are triggered by parsing attacker-supplied XML.
This entry is separate from the earlier libexpat1 entry (five CVEs, reassess by
2026-12-14).

**Rationale for accepting**: Trivy 0.52.2 reports all four as `affected` with no
fixed version in Debian trixie; the fixes exist only in sid and forky. The
runtime base digest is pinned in the Dockerfile and is not changed by this
entry. `libexpat1` is required by the interpreter's `pyexpat` module and cannot
be removed from the image. The application parses no XML: `src/` contains no XML
parsing code, the API exchanges JSON and HTML fragments over HTTP, and the
runtime image installs only the `api` extra (no spreadsheet or XML libraries).

**Mitigation in place**:

- No application code path passes untrusted input to an XML parser.
- The runtime image is distroless (no shell, no package manager) and runs as
  non-root UID 65532.
- `.trivyignore.yaml` entries keep the scheduled scan focused on new findings.

**Resolution path**: take the next base image digest that carries a fixed
expat (or a Debian trixie security update reaching it) and remove the
`.trivyignore.yaml` entries in the same change. Reassess when a new `dhi-python`
base digest lands.

**Tracking**: Debian security tracker; no fixed version in trixie as of
2026-11-06.

---

### CVE-2026-119373 and two more - libsqlite3-0 base image package, second batch (reassess by 2027-01-05)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-119373, CVE-2026-119374, CVE-2026-119379 |
| **Package** | libsqlite3-0 3.46.1-7+deb13u2+dhi1 (Debian 13 package in the pinned hardened Python runtime base image) |
| **Severity** | High |
| **Status** | Accepted risk |
| **Introduced** | 2026-11-04 |
| **Last reassessed** | 2026-11-06 |
| **Reassess by** | 2027-01-05 (within 60 days of Last reassessed) |

**Description**: SQLite flaws: a heap-based buffer overflow in FTS5 (denial of
service), arbitrary code execution via a corrupted FTS5 index, and arbitrary
code execution via crafted session changesets. Each requires SQLite to open or
process attacker-controlled database content. This entry is separate from the
earlier libsqlite3-0 entry (CVE-2026-11822 and CVE-2026-11824).

**Rationale for accepting**: Trivy 0.52.2 reports all three as `affected` with
no fixed version in Debian trixie; the fixes exist only in sid and forky. The
runtime base digest is pinned in the Dockerfile and is not changed by this
entry. `libsqlite3-0` is a shared library shipped with the interpreter (for its
`sqlite3` module). LLC Manager persists all data in PostgreSQL: the database
URLs in `src/llc_manager/core/config.py` use `postgresql+asyncpg` and
`postgresql+psycopg`, and `src/` never imports `sqlite3`. No code path opens a
SQLite database, FTS5 index, or session changeset.

**Mitigation in place**:

- The application does not open or process SQLite data.
- The runtime image is distroless (no shell, no package manager) and runs as
  non-root UID 65532.
- `.trivyignore.yaml` entries keep the scheduled scan focused on new findings.

**Resolution path**: take the next base image digest that carries a fixed
SQLite (or a Debian trixie security update reaching it) and remove the
`.trivyignore.yaml` entries in the same change. Reassess when a new `dhi-python`
base digest lands.

**Tracking**: Debian security tracker; no fixed version in trixie as of
2026-11-06.

---

### CVE-2026-85091 and one more - zlib1g base image package (reassess by 2027-01-05)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-85091, CVE-2026-76844 |
| **Package** | zlib1g 1:1.3.dfsg+really1.3.1-1+dhi4 (Debian 13 package in the pinned hardened Python runtime base image) |
| **Severity** | High |
| **Status** | Accepted risk |
| **Introduced** | 2026-11-04 |
| **Last reassessed** | 2026-11-06 |
| **Reassess by** | 2027-01-05 (within 60 days of Last reassessed) |

**Description**: CVE-2026-85091 is a heap buffer overflow in `gz_vacate()` in
zlib's `gz*` file API that allows arbitrary code execution. CVE-2026-76844 is
titled by Trivy as a `webpack-dev-middleware` path traversal information
disclosure; Trivy attributes it to `zlib1g`, but that advisory concerns a Node.js
package, not zlib.

**Rationale for accepting**: Trivy 0.52.2 reports both as `affected` with no
fixed version in Debian trixie; the fix for CVE-2026-85091 exists only in sid
and forky. The runtime base digest is pinned in the Dockerfile and is not
changed by this entry. `zlib1g` is required by the interpreter and cannot be
removed from the image. `src/` imports neither `gzip` nor `zlib` and does not
call the `gz*` file API, and the application registers no response compression
middleware. For CVE-2026-76844, the Trivy scan of the image found no Node.js
packages (only Python packages), and the project uses no Node.js or webpack at
runtime (Tailwind CSS is built with a standalone binary), so the
`webpack-dev-middleware` flaw has no component to act on.

**Mitigation in place**:

- No application code path calls the zlib `gz*` file API.
- The runtime image is distroless (no shell, no package manager) and runs as
  non-root UID 65532.
- `.trivyignore.yaml` entries keep the scheduled scan focused on new findings.

**Resolution path**: take the next base image digest that carries a fixed
zlib (or a Debian trixie security update reaching it) and remove the
`.trivyignore.yaml` entries in the same change. Reassess when a new `dhi-python`
base digest lands. Re-check whether the Trivy database still attributes
CVE-2026-76844 to `zlib1g`; if the mapping is corrected, drop that ignore entry.

**Tracking**: Debian security tracker; no fixed version in trixie as of
2026-11-06.

---

## Archive

### PYSEC-2022-42969 - py (resolved 2026-11-06)

| Field | Value |
|-------|-------|
| **ID** | PYSEC-2022-42969 |
| **CVE** | CVE-2022-42969 |
| **GHSA** | GHSA-w596-4wvx-j9j6 |
| **Package** | py==1.11.0 (unmaintained; transitive dep of interrogate) |
| **Severity** | Medium |
| **Status** | Resolved (advisory withdrawn upstream) |
| **Introduced** | 2026-01-18 |
| **Last reassessed** | 2026-04-20 |
| **Resolved** | 2026-11-06 |

**Description**: ReDoS in `py.path.svnwc.SvnWCCommandPath` when processing
malicious SVN output. See <https://github.com/pytest-dev/py/issues/287>.

**Rationale for accepting (historical)**: We do not use Subversion anywhere in
the codebase or CI. The vulnerable code path is `py.path.svnwc.SvnWCCommandPath`,
which only executes when `py.path` is used to inspect an SVN working copy. Our
project uses git exclusively.

**Resolution**: Resolved 2026-11-06 because the advisories were withdrawn, not
because the package changed (`py==1.11.0` is still locked). OSV withdrew
PYSEC-2022-42969 on 2026-06-09 and GHSA-w596-4wvx-j9j6 on 2025-08-01. With the
advisories withdrawn, OSV-Scanner no longer matches this finding, so the
`CVE-2022-42969` ignore in `osv-scanner.toml` became an unused ignore, which
OSV-Scanner reports as an error (exit code 1). The ignore was removed and this
entry retired. The reassess-by date of 2026-06-19 had passed without
reassessment, which this retirement also closes out.

**Evidence**:

- <https://api.osv.dev/v1/vulns/PYSEC-2022-42969> (`withdrawn`: 2026-06-09)
- <https://api.osv.dev/v1/vulns/GHSA-w596-4wvx-j9j6> (`withdrawn`: 2025-08-01)

---

### CVE-2026-27135 - libnghttp2-14 base image package (resolved 2026-11-06)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-27135 |
| **Package** | libnghttp2-14 |
| **Severity** | High |
| **Status** | Resolved (no longer reported by Trivy) |
| **Introduced** | 2026-04-29 |
| **Last reassessed** | 2026-04-29 |
| **Resolved** | 2026-11-06 |

**Resolution**: The entry's reassess-by date had passed. On 2026-11-06 the image
built from `main` was scanned with Trivy 0.52.2 (vulnerability DB updated
2026-11-06) with no ignore file, and none of CVE-2026-27135 is reported: Debian trixie lists nghttp2 fixed in 1.64.0-1.1+deb13u1 (DSA-6266-1). The
`.trivyignore.yaml` entry was removed when the ignore file was converted to the
YAML format with expiry dates.

---

### CVE-2026-4878 - libcap2 base image package (resolved 2026-11-06)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-4878 |
| **Package** | libcap2 |
| **Severity** | High |
| **Status** | Resolved (no longer reported by Trivy) |
| **Introduced** | 2026-05-07 |
| **Last reassessed** | 2026-05-07 |
| **Resolved** | 2026-11-06 |

**Resolution**: The entry's reassess-by date had passed. On 2026-11-06 the image
built from `main` was scanned with Trivy 0.52.2 (vulnerability DB updated
2026-11-06) with no ignore file, and none of CVE-2026-4878 is reported: Debian trixie lists libcap2 fixed in 1:2.75-10+deb13u1. The
`.trivyignore.yaml` entry was removed when the ignore file was converted to the
YAML format with expiry dates.

---

### CVE-2026-29111 - systemd base image packages (resolved 2026-11-06)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-29111 |
| **Package** | systemd (libsystemd0, libudev1) |
| **Severity** | High |
| **Status** | Resolved (no longer reported by Trivy) |
| **Introduced** | 2026-04-29 |
| **Last reassessed** | 2026-04-29 |
| **Resolved** | 2026-11-06 |

**Resolution**: The entry's reassess-by date had passed. On 2026-11-06 the image
built from `main` was scanned with Trivy 0.52.2 (vulnerability DB updated
2026-11-06) with no ignore file, and none of CVE-2026-29111 is reported: Debian trixie lists systemd fixed in 257.13-1~deb13u1. The
`.trivyignore.yaml` entry was removed when the ignore file was converted to the
YAML format with expiry dates.

---

### CVE-2026-5773 - libcurl SMB transfer (resolved 2026-11-06)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-5773 |
| **Package** | curl, libcurl4t64 |
| **Severity** | High |
| **Status** | Resolved (no longer reported by Trivy) |
| **Introduced** | 2026-05-25 |
| **Last reassessed** | 2026-05-25 |
| **Resolved** | 2026-11-06 |

**Resolution**: The entry's reassess-by date had passed. On 2026-11-06 the image
built from `main` was scanned with Trivy 0.52.2 (vulnerability DB updated
2026-11-06) with no ignore file, and none of CVE-2026-5773 is reported: Debian trixie lists curl fixed in 8.14.1-2+deb13u5; the hardened runtime image has no curl. The
`.trivyignore.yaml` entry was removed when the ignore file was converted to the
YAML format with expiry dates.

---

### CVE-2026-6276 - libcurl cookie leak (resolved 2026-11-06)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-6276 |
| **Package** | curl, libcurl4t64 |
| **Severity** | High |
| **Status** | Resolved (no longer reported by Trivy) |
| **Introduced** | 2026-05-25 |
| **Last reassessed** | 2026-05-25 |
| **Resolved** | 2026-11-06 |

**Resolution**: The entry's reassess-by date had passed. On 2026-11-06 the image
built from `main` was scanned with Trivy 0.52.2 (vulnerability DB updated
2026-11-06) with no ignore file, and none of CVE-2026-6276 is reported: Debian trixie lists curl fixed in 8.14.1-2+deb13u5; the hardened runtime image has no curl. The
`.trivyignore.yaml` entry was removed when the ignore file was converted to the
YAML format with expiry dates.

---

### CVE-2026-40356 - krb5 integer overflow DoS (resolved 2026-11-06)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-40356 |
| **Package** | libgssapi-krb5-2 |
| **Severity** | High |
| **Status** | Resolved (no longer reported by Trivy) |
| **Introduced** | 2026-05-25 |
| **Last reassessed** | 2026-05-25 |
| **Resolved** | 2026-11-06 |

**Resolution**: The entry's reassess-by date had passed. On 2026-11-06 the image
built from `main` was scanned with Trivy 0.52.2 (vulnerability DB updated
2026-11-06) with no ignore file, and none of CVE-2026-40356 is reported: Debian trixie lists krb5 fixed in 1.21.3-5+deb13u1 (DSA-6293-1). The
`.trivyignore.yaml` entry was removed when the ignore file was converted to the
YAML format with expiry dates.

---

### CVE-2026-7598 - libssh2 integer overflow (resolved 2026-11-06)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-7598 |
| **Package** | libssh2-1t64 |
| **Severity** | High |
| **Status** | Resolved (no longer reported by Trivy) |
| **Introduced** | 2026-05-25 |
| **Last reassessed** | 2026-05-25 |
| **Resolved** | 2026-11-06 |

**Resolution**: The entry's reassess-by date had passed. On 2026-11-06 the image
built from `main` was scanned with Trivy 0.52.2 (vulnerability DB updated
2026-11-06) with no ignore file, and none of CVE-2026-7598 is reported: Debian trixie lists libssh2 fixed in 1.11.1-1+deb13u1 (DSA-6365-1). The
`.trivyignore.yaml` entry was removed when the ignore file was converted to the
YAML format with expiry dates.

---

### CVE-2026-11822, CVE-2026-11824 - libsqlite3-0 base image package (resolved 2026-11-06)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-11822, CVE-2026-11824 |
| **Package** | libsqlite3-0 |
| **Severity** | High |
| **Status** | Resolved (no longer reported by Trivy) |
| **Introduced** | 2026-06-18 |
| **Last reassessed** | 2026-06-18 |
| **Resolved** | 2026-11-06 |

**Resolution**: The entry's reassess-by date had passed. On 2026-11-06 the image
built from `main` was scanned with Trivy 0.52.2 (vulnerability DB updated
2026-11-06) with no ignore file, and none of CVE-2026-11822, CVE-2026-11824 is reported: the installed libsqlite3-0 3.46.1-7+deb13u2 is the Debian trixie version that carries the fix for both CVEs. The
`.trivyignore.yaml` entry was removed when the ignore file was converted to the
YAML format with expiry dates.

---

### CVE-2026-48962 - perl-base IO::Compress (resolved 2026-11-06)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-48962 |
| **Package** | perl-base (IO::Compress) |
| **Severity** | High |
| **Status** | Resolved (no longer reported by Trivy) |
| **Introduced** | 2026-06-18 |
| **Last reassessed** | 2026-06-18 |
| **Resolved** | 2026-11-06 |

**Resolution**: The entry's reassess-by date had passed. On 2026-11-06 the image
built from `main` was scanned with Trivy 0.52.2 (vulnerability DB updated
2026-11-06) with no ignore file, and none of CVE-2026-48962 is reported: the hardened runtime image has no perl-base package; Debian trixie lists libio-compress-perl fixed in 2.213-1+deb13u1. The
`.trivyignore.yaml` entry was removed when the ignore file was converted to the
YAML format with expiry dates.

---

### perl-base bundled Perl and Archive::Tar CVEs (resolved 2026-11-06)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-42496, CVE-2026-8376, CVE-2026-42497, CVE-2026-9538 |
| **Package** | perl-base (Perl and Archive::Tar CVEs) |
| **Severity** | Critical (CVE-2026-42496, CVE-2026-8376), High (CVE-2026-42497, CVE-2026-9538) |
| **Status** | Resolved (no longer reported by Trivy) |
| **Introduced** | 2026-05-28 |
| **Last reassessed** | 2026-05-28 |
| **Resolved** | 2026-11-06 |

**Resolution**: The entry's reassess-by date had passed. On 2026-11-06 the image
built from `main` was scanned with Trivy 0.52.2 (vulnerability DB updated
2026-11-06) with no ignore file, and none of CVE-2026-42496, CVE-2026-8376, CVE-2026-42497, CVE-2026-9538 is reported. The hardened
runtime image has no perl-base package (checked with a full Trivy package
listing). Debian trixie lists perl fixed in 5.40.1-6+deb13u1 for CVE-2026-42496,
CVE-2026-8376 and CVE-2026-42497, and CVE-2026-9538 is not applicable without
Perl in the image. The `.trivyignore.yaml` entries were removed when the ignore
file was converted to the YAML format with expiry dates.
