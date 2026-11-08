# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

Security and isolation integrity are top priorities for App Encloser. If you discover a security vulnerability or sandbox bypass:

1. **Do not open a public issue.** Please disclose responsibly.
2. Use GitHub's **Private Vulnerability Reporting** on this repository to submit confidential details and reproduction steps.
3. Alternatively, report the findings to the maintainer via GitHub security advisories.

## Security Architecture

App Encloser enforces isolation using unprivileged Bubblewrap (`bwrap`) user namespaces:
- Host user home directory is masked with ephemeral tmpfs in strict sandbox mode.
- System binary paths (`/usr/bin`, `/bin`, `/lib`) are protected from host modification.
- Shims in `userdata/shims` redirect keyrings and repositories without host root access.

Thank you for helping keep App Encloser secure for everyone.
