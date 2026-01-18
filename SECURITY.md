# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it by:

1. **Email**: Send details to byron@williamscpa.com
2. **GitHub**: Open a security advisory at https://github.com/ByronWilliamsCPA/llc-manager/security/advisories/new

Please include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We aim to respond within 48 hours and provide a fix timeline within 7 days.

## Security Practices

This project follows security best practices:

- **Dependency Scanning**: Automated via Dependabot and Safety
- **Static Analysis**: Bandit for Python security issues
- **Code Review**: All changes require review before merge
- **Signed Commits**: GPG-signed commits required
- **FIPS Compliance**: Code is checked for FIPS 140-2/140-3 compatibility

## Known Vulnerabilities

### CVE-2025-53000 (nbconvert) - Accepted Risk

| Field | Value |
|-------|-------|
| **CVE** | CVE-2025-53000 |
| **GHSA** | GHSA-xm59-rqc7-hhvf |
| **Severity** | High (CVSS 8.5) |
| **Package** | nbconvert <= 7.16.6 |
| **Status** | Accepted Risk |

**Description**: Uncontrolled search path vulnerability on Windows that allows code execution
via a malicious `inkscape.bat` file when converting notebooks with SVG to PDF.

**Risk Assessment**:

- **Platform**: Windows-only (this project is developed and deployed on Linux)
- **Scope**: Development dependency only (not in production)
- **Usage**: Project does not use notebook-to-PDF conversion
- **Upstream Fix**: No patched version available as of 2026-01-18

**Mitigation**: The risk is tolerable for development use. Will upgrade when a fix is released.

## Security Updates

Security updates are applied as follows:

- **Critical/High**: Within 7 days of disclosure
- **Medium**: Within 30 days
- **Low**: Next scheduled release
