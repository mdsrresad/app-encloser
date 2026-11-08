# Changelog

All notable changes to **App Encloser** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-11-09 — Initial Public Release

### Features & Capabilities

#### Core Enclosing & Sandboxing
- **Arbitrary Package Ingestion:** Direct encapsulation of `.deb`, `.AppImage`, `.tar.gz`, `.zip`, `.rpm`, `.jar`, and arbitrary multi-line bash install scripts into `~/EnclosedApps/<AppName>/`.
- **Three Isolation Levels:**
  - **Standard Isolated:** Private `$HOME`, `$XDG_CONFIG_HOME`, `$XDG_DATA_HOME`, `$XDG_CACHE_HOME`, and `$TMPDIR`.
  - **Strict Sandbox:** Kernel namespace virtualization via Bubblewrap (`bwrap`) with read-only root mounts and tmpfs home shielding. Zero leaks outside container.
  - **System Integrated:** Direct host network and service access enabled for background daemons, CLI tools, and VPNs.
- **100% Zero-Residual Wipe:** Total deletion of application directory leaves zero residual files in `~/.config`, `~/.cache`, or `/var`.
- **Native Wayland & Hardware Acceleration:** Direct pass-through for Wayland display sockets and PipeWire/PulseAudio without socket-forwarding daemons or performance degradation.

#### Container Universe Experience
- **Interactive Container Shell:** Dedicated interactive shell via `app-encloser shell <app>` with styled prompt `[Universe: <app>] ~$`.
- **Protected Shim Architecture:** Shims (`apt`, `apt-get`, `gpg`, `curl`, `wget`, `tee`, `sudo`, `nft`, `encloser-install`, `encloser-python`, `encloser-brew`) located in `userdata/shims/`, completely immune to package overwrites.
- **Rootless APT & Keyring Redirection:** Intercepts APT keyrings and repository lists, redirecting write operations to `userdata/keyrings/` and `userdata/etc_apt/`.
- **Multi-Version Runtime Isolation:** `encloser-python <version>` downloads and manages isolated Python versions per container. Containerized Homebrew support via `encloser-brew` inside `userdata/linuxbrew/`.

#### Host Package Protection & Safeguards
- **System Binary Immunity:** Strict protection blocking identification or deletion of core system binaries (`/usr/bin/install`, `/usr/bin/bash`, `/bin/sh`, etc.).
- **Reverse-Dependency Safety Engine:** Batched `apt-cache rdepends --installed` queries with caching, preventing accidental removal of host packages required by other applications.
- **Deep Footprint Discovery:** Discovers and audits terminal-installed packages, user CLIs (`~/.local/bin`, `~/.npm-global/bin`, `~/.cargo/bin`), Ollama, Claude CLI, and Homebrew.
- **Bidirectional Migration:** Easily migrate packages between Host System and Isolated Containers.

#### Safety, AI Agent Interceptor & MCP Server
- **Terminal & AI Agent Guard:** Intercepts `sudo apt install`, `pip install`, `npm -g`, and `curl | bash`. Halts autonomous AI agents (Claude Code, Cursor, Aider) with **Exit Code 2** and explicit instructions to enclose cleanly.
- **Model Context Protocol (MCP) Server:** Built-in JSON-RPC 2.0 MCP server (`app-encloser --mcp`) providing 16 tools for AI coding assistants.

#### Automated Diagnostics & Self-Healing
- **Automated Anomaly Detection:** Proactively audits containers for missing or non-executable shims, permissions, broken launch scripts, and dead PIDs.
- **Self-Healing Engine (`app-encloser doctor`):** Automatically repairs detected anomalies, restores shims, fixes permissions, and recovers from corrupted JSON configurations without throwing unhandled exceptions.

#### Modern GTK4 / Libadwaita Interface
- Dark mode interface styled with Libadwaita components.
- Live RAM metrics, responsive search filtering, scope tabs (All, Enclosed, Host, Recent, Heavy).
- Direct container universe row buttons: Play, Terminal, Files, Install Inside, and Force Stop.
- Audit & Installation History dialog with clear uninstalled records management and instant refresh feedback.
