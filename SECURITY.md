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

App Encloser enforces isolation using unprivileged Bubblewrap (`bwrap`) user namespaces and user-space environment sandboxing:

- **Strict Sandbox Virtualization (`bwrap`):**
  - Mounts the host root filesystem strictly read-only (`--ro-bind / /`), protecting system binaries (`/usr`, `/bin`, `/lib`, `/etc`) from unauthorized modification.
  - Masks the host user home directory with an isolated `tmpfs` layer.
  - Mounts a private `/tmp` filesystem to prevent cross-application `/tmp` scraping.
  - Provides native desktop integration by passing Wayland/X11 display and PulseAudio/PipeWire audio sockets.
  - Explicit warning notifications are emitted to stderr and container logs if the host environment restricts unprivileged user namespaces.

- **Standard Directory Isolation:**
  - Isolates application execution into `~/EnclosedApps/<AppName>/userdata/` by redirecting `$HOME`, `$XDG_CONFIG_HOME`, `$XDG_DATA_HOME`, `$XDG_CACHE_HOME`, `$XDG_STATE_HOME`, and `$TMPDIR`.
  - Zero modifications to host home configuration or dotfiles.

- **Terminal & AI Agent Guard:**
  - Disabled by default (opt-in via Settings or `app-encloser guard enable`) to ensure complete user consent.
  - Detects automated AI agent environments and halts unauthorized host modifications with Exit Code 2.

- **Rootless Operation:**
  - All container management, extraction, and shim redirection operate entirely in user space with zero root privileges and zero background daemons.

Thank you for helping keep App Encloser secure for everyone.
