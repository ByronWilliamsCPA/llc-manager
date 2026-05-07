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

### PYSEC-2022-42969 - py (reassess by 2026-06-19)

| Field | Value |
|-------|-------|
| **ID** | PYSEC-2022-42969 |
| **Package** | py==1.11.0 (unmaintained; transitive dep of pytest plugins) |
| **Severity** | Medium |
| **Status** | Accepted risk |
| **Introduced** | 2026-01-18 |
| **Last reassessed** | 2026-04-20 |
| **Reassess by** | 2026-06-19 |

**Description**: ReDoS in `py.path.svnwc.SvnWCCommandPath` when processing
malicious SVN output. See <https://github.com/pytest-dev/py/issues/287>.

**Rationale for accepting**: We do not use Subversion anywhere in the codebase
or CI. The vulnerable code path is `py.path.svnwc.SvnWCCommandPath`, which
only executes when `py.path` is used to inspect an SVN working copy. Our
project uses git exclusively.

**Mitigation in place**:

- No SVN tooling in the project; `py.path.svnwc` is never imported.
- `py` is only retained transitively by pytest-era plugins; removing it
  is blocked on upstream maintainers migrating off `py`.

**Resolution path**: monitor pytest and its plugin ecosystem for migration
off `py`. Re-run `pip-audit` monthly; the entry is cleared automatically when
the dep is dropped.

**Tracking**: upstream issue <https://github.com/pytest-dev/py/issues/287>.

---

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

### CVE-2025-69720 - ncurses base image packages (reassess by 2026-06-28)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2025-69720 |
| **Package** | libncursesw6, libtinfo6, ncurses-base (Debian 13 packages in `python:3.12-slim`) |
| **Severity** | High |
| **Status** | Accepted risk |
| **Introduced** | 2026-04-29 |
| **Last reassessed** | 2026-04-29 |
| **Reassess by** | 2026-06-28 |

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
- `.trivyignore` entry prevents CI failure until Debian releases a patch.

**Resolution path**: upgrade the base image when Debian 13 releases a patched ncurses
package. Monitor the Debian security tracker and re-run `trivy image` monthly.

**Tracking**: Debian security tracker; no upstream patch available as of 2026-04-29.

---

### CVE-2026-27135 - libnghttp2-14 base image package (reassess by 2026-06-28)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-27135 |
| **Package** | libnghttp2-14 1.64.0-1.1 (Debian 13 package in `python:3.12-slim`) |
| **Severity** | High |
| **Status** | Accepted risk |
| **Introduced** | 2026-04-29 |
| **Last reassessed** | 2026-04-29 |
| **Reassess by** | 2026-06-28 |

**Description**: Denial of service in nghttp2 via malformed HTTP/2 frames.

**Rationale for accepting**: No Debian patch is available as of 2026-04-29. Our application
uses HTTP/1.1 between clients and the FastAPI server (via uvicorn); `libnghttp2-14` is a
transitive dependency of `curl` installed in the runtime image for the health check probe.
HTTP/2 frame processing is not invoked by our application.

**Mitigation in place**:

- uvicorn serves HTTP/1.1 by default; no HTTP/2 listener is configured.
- Container runs as non-root user.
- `.trivyignore` entry prevents CI failure until Debian releases a patch.

**Resolution path**: upgrade the base image when Debian 13 releases a patched nghttp2
package, or replace the health check `curl` with a minimal alternative that does not
pull in nghttp2.

**Tracking**: Debian security tracker; no upstream patch available as of 2026-04-29.

---

### CVE-2026-4878 - libcap2 base image package (reassess by 2026-07-06)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-4878 |
| **Package** | libcap2 1:2.75-10+b8 (Debian 13 package in `python:3.12-slim`) |
| **Severity** | High |
| **Status** | Accepted risk |
| **Introduced** | 2026-05-07 |
| **Last reassessed** | 2026-05-07 |
| **Reassess by** | 2026-07-06 |

**Description**: Privilege escalation via TOCTOU race condition in `cap_set_file()` in
libcap. An attacker who can race file operations may escalate privileges.

**Rationale for accepting**: No Debian patch is available as of 2026-05-07. The
vulnerability requires local access to race `cap_set_file()` calls. Our application never
invokes capability-setting functions and runs as non-root user (`appuser`, UID 1000). There
is no code path in the FastAPI application that calls into libcap's file capability APIs.

**Mitigation in place**:

- Container runs as non-root user (`appuser`, UID 1000), limiting exploitability.
- No capability-setting calls in the application code path.
- `.trivyignore` entry prevents CI failure until Debian releases a patch.

**Resolution path**: upgrade the base image when Debian 13 releases a patched libcap2
package. Monitor the Debian security tracker and re-run `trivy image` monthly.

**Tracking**: Debian security tracker; no upstream patch available as of 2026-05-07.

---

### CVE-2026-29111 - systemd base image packages (reassess by 2026-06-28)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-29111 |
| **Package** | libsystemd0, libudev1 257.9-1~deb13u1 (Debian 13 packages in `python:3.12-slim`) |
| **Severity** | High |
| **Status** | Accepted risk |
| **Introduced** | 2026-04-29 |
| **Last reassessed** | 2026-04-29 |
| **Reassess by** | 2026-06-28 |

**Description**: Arbitrary code execution or denial of service in systemd.

**Rationale for accepting**: No Debian patch is available as of 2026-04-29. These are
shared library packages (`libsystemd0`, `libudev1`) included in the base image; the
container does not run systemd as PID 1 (it runs uvicorn). The vulnerabilities require
interaction with systemd's IPC mechanisms, which are not accessible inside the container.

**Mitigation in place**:

- Container uses uvicorn as PID 1, not systemd.
- Systemd socket and D-Bus interfaces are not mounted into the container.
- Container runs as non-root user.
- `.trivyignore` entry prevents CI failure until Debian releases a patch.

**Resolution path**: upgrade the base image when Debian 13 releases a patched systemd
package. Monitor the Debian security tracker and re-run `trivy image` monthly.

**Tracking**: Debian security tracker; no upstream patch available as of 2026-04-29.

---

### CVE-2026-5773 - libcurl SMB transfer (reassess by 2026-07-24)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-5773 |
| **Package** | curl, libcurl4t64 8.14.1-2+deb13u3 (Debian 13 packages installed in runtime stage of `Dockerfile`) |
| **Severity** | High |
| **Status** | Accepted risk |
| **Introduced** | 2026-05-25 |
| **Last reassessed** | 2026-05-25 |
| **Reassess by** | 2026-07-24 |

**Description**: Wrong file transfer in libcurl when processing SMB URLs, which may
cause unintended file content to be transferred.

**Rationale for accepting**: `curl` is installed in the runtime stage of the
`Dockerfile` solely for the container `HEALTHCHECK` probe against
`http://localhost:8000/...`. SMB URLs are never used; only loopback HTTP. Curl
is not exposed to untrusted input or external URLs from inside the container.
No Debian patch is available as of 2026-05-25.

**Mitigation in place**:

- Curl invocations are limited to `http://localhost:...` for the HEALTHCHECK probe;
  no SMB protocol code path is reached.
- Container runs as non-root user (`appuser`, UID 1000).
- `.trivyignore` entry prevents CI failure until Debian releases a patch.
- `apt-get upgrade -y` runs in the runtime stage so any future Debian backport
  is picked up automatically on the next image rebuild.

**Resolution path**: upgrade the base image or replace `curl` with a smaller
healthcheck client (`wget --spider`, busybox-equivalent) when Debian 13 ships a
patched libcurl. Monitor the Debian security tracker and re-run `trivy image`
monthly.

**Tracking**: Debian security tracker; no upstream patch available as of 2026-05-25.

---

### CVE-2026-6276 - libcurl cookie leak (reassess by 2026-07-24)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-6276 |
| **Package** | curl, libcurl4t64 8.14.1-2+deb13u3 (Debian 13 packages installed in runtime stage of `Dockerfile`) |
| **Severity** | High |
| **Status** | Accepted risk |
| **Introduced** | 2026-05-25 |
| **Last reassessed** | 2026-05-25 |
| **Reassess by** | 2026-07-24 |

**Description**: Information disclosure in libcurl due to cookies leaking across
unrelated request scopes.

**Rationale for accepting**: As above for CVE-2026-5773, `curl` is invoked only
for the HEALTHCHECK probe against `http://localhost:8000/...`. No cookies are
set, no cross-origin requests are made, and no authentication state passes
through the affected code path. No Debian patch is available as of 2026-05-25.

**Mitigation in place**:

- Curl invocations are limited to a single loopback URL with no cookies.
- Container runs as non-root user (`appuser`, UID 1000).
- `.trivyignore` entry prevents CI failure until Debian releases a patch.
- `apt-get upgrade -y` runs in the runtime stage so any future Debian backport
  is picked up automatically on the next image rebuild.

**Resolution path**: upgrade the base image or replace `curl` with a smaller
healthcheck client when Debian 13 ships a patched libcurl. Monitor the Debian
security tracker and re-run `trivy image` monthly.

**Tracking**: Debian security tracker; no upstream patch available as of 2026-05-25.

---

### CVE-2026-40356 - krb5 integer overflow DoS (reassess by 2026-07-24)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-40356 |
| **Package** | libgssapi-krb5-2 1.21.3-5+deb13u1 (Debian 13 package in `python:3.12-slim`) |
| **Severity** | High |
| **Status** | Accepted risk |
| **Introduced** | 2026-05-25 |
| **Last reassessed** | 2026-05-25 |
| **Reassess by** | 2026-07-24 |

**Description**: MIT Kerberos 5 (krb5) denial of service via integer overflow
in the GSSAPI layer.

**Rationale for accepting**: `libgssapi-krb5-2` is a transitive shared library
present in the `python:3.12-slim` base image. The LLC Manager runtime does not
use Kerberos for authentication or any GSSAPI-secured RPC; no application code
path invokes the affected krb5 entry points. No Debian patch is available as
of 2026-05-25.

**Mitigation in place**:

- No Kerberos authentication is configured in the FastAPI app or its
  dependencies.
- Container runs as non-root user; no privileged process can call into krb5.
- `.trivyignore` entry prevents CI failure until Debian releases a patch.

**Resolution path**: upgrade the base image when Debian 13 ships a patched
krb5. Monitor the Debian security tracker and re-run `trivy image` monthly.

**Tracking**: Debian security tracker; no upstream patch available as of 2026-05-25.

---

### CVE-2026-7598 - libssh2 integer overflow (reassess by 2026-07-24)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-7598 |
| **Package** | libssh2-1t64 1.11.1-1 (Debian 13 package in `python:3.12-slim`) |
| **Severity** | High |
| **Status** | Accepted risk |
| **Introduced** | 2026-05-25 |
| **Last reassessed** | 2026-05-25 |
| **Reassess by** | 2026-07-24 |

**Description**: Integer overflow in libssh2 when processing a username or
password whose length exceeds the expected bounds.

**Rationale for accepting**: `libssh2-1t64` is a transitive shared library in
the `python:3.12-slim` base image. The LLC Manager runtime does not invoke SSH
or SFTP from the container; no application code path uses libssh2. The library
is unreachable from the FastAPI request path. No Debian patch is available as
of 2026-05-25.

**Mitigation in place**:

- No SSH or SFTP client code in the application or its dependencies.
- Container runs as non-root user; outbound SSH would also be blocked by
  default network policy in production.
- `.trivyignore` entry prevents CI failure until Debian releases a patch.

**Resolution path**: upgrade the base image when Debian 13 ships a patched
libssh2. Monitor the Debian security tracker and re-run `trivy image` monthly.

**Tracking**: Debian security tracker; no upstream patch available as of 2026-05-25.

---

### perl-base bundled Perl and Archive::Tar CVEs (reassess by 2026-07-27)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2026-42496, CVE-2026-8376, CVE-2026-42497, CVE-2026-9538 |
| **Package** | perl-base 5.40.1-6 (Debian 13 package in `python:3.12-slim`) |
| **Severity** | Critical (CVE-2026-42496, CVE-2026-8376), High (CVE-2026-42497, CVE-2026-9538) |
| **Status** | Accepted risk |
| **Introduced** | 2026-05-28 |
| **Last reassessed** | 2026-05-28 |
| **Reassess by** | 2026-07-27 |

**Description**: Four vulnerabilities in the Perl interpreter and its bundled
`Archive::Tar` module shipped in Debian 13's `perl-base`:

- CVE-2026-42496 (Critical): `Archive::Tar` before 3.08 extracts symbolic links
  outside the intended target directory.
- CVE-2026-8376 (Critical): a heap buffer overflow in Perl through 5.43.10.
- CVE-2026-42497 (High): `Archive::Tar` before 3.08 extracts hard links outside
  the intended target directory.
- CVE-2026-9538 (High): a memory-handling issue in `Archive::Tar` before 3.10.

**Rationale for accepting**: `perl-base` is an `Essential` Debian package present
transitively in the `python:3.12-slim` base image; it cannot be removed without
breaking `dpkg`. The LLC Manager runtime is a Python/FastAPI application that
never invokes the Perl interpreter and never calls `Archive::Tar`. No application
code path, dependency, or container entrypoint executes Perl, and the service
processes no untrusted tar archives through Perl. The vulnerable code is
unreachable from the request path. No Debian patch is available as of 2026-05-28
(the Trivy `Fixed Version` column is empty for all four), and CVE-2026-8376
affects every Perl release through 5.43.10, so no base-image version bump
resolves it.

**Mitigation in place**:

- No Perl is invoked by the application, its dependencies, or the container
  `CMD`/`HEALTHCHECK` (both use Python and `curl`, not Perl).
- Container runs as a non-root user (`appuser`); no privileged Perl process runs.
- `.trivyignore` entries prevent CI failure until Debian ships patched packages.

**Resolution path**: upgrade the base image when Debian 13 ships a patched
`perl-base`, or migrate to a Perl-free base image (for example a distroless or
Alpine Python image). Monitor the Debian security tracker and re-run
`trivy image` monthly.

**Tracking**: Debian security tracker; no upstream patch available as of 2026-05-28.

---

## Archive

No resolved entries yet.
