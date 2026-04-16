# Security Policy

## Supported versions

Security fixes are currently provided on a best-effort basis for:

- the latest commit on `main`
- the latest public GitHub release

Older snapshots may not receive backported fixes.

## Reporting a vulnerability

Please do **not** disclose security-sensitive issues in a public GitHub issue with full exploit details.

Preferred reporting path:

1. Use GitHub **Private Vulnerability Reporting** for this repository if it is enabled.
2. If that option is not available, contact the maintainer privately first through the contact information exposed on the GitHub profile or ORCID-linked academic profile.
3. If neither is possible, open a minimal public issue that only states a private security contact is needed and do not include exploit instructions, sample payloads, or sensitive files.

## What to include in a report

Please include:

- affected version or commit
- impact and attack scenario
- steps to reproduce
- proof of concept if necessary
- whether the issue can expose files, credentials, arbitrary code execution, or silent data corruption

## Response expectations

Best-effort targets:

- initial acknowledgement within 7 business days
- severity triage after reproduction
- public disclosure only after a fix or mitigation is available, when practical

## Scope notes

This project is a local desktop application, so the most relevant security risks are:

- unsafe parsing of untrusted input files
- arbitrary file overwrite or unintended path traversal
- code execution through external tools or malformed file formats
- silent corruption of scientific output caused by unsafe edge-case handling

Reports limited to general dependency age or hypothetical issues without a plausible impact path may be deprioritized.
