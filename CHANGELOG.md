# Changelog

All notable changes to **App Encloser** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.5] - 2026-11-10

### Bug Fixes & Stability (P0 Audit Hardening)
- **Resolved Missing Imports:** Added missing `import sys` in `lifecycle.py`, `import shutil`, `import subprocess`, and `import re` in `main.py`, `import os` in `mcp_server.py`, and `import re` in `terminal_guard.py`.
- **Fixed CLI `--mode` Level Assignment:** Corrected `set_enclosing_level` call during `app-encloser install <pkg> --mode=strict` to parse and apply the level to the resolved container folder rather than the human-readable success text.
- **Fixed Clean-Environment Desktop Shortcut Crash:** Added `ensure_base_dirs()` and `os.makedirs(APPS_DIR, exist_ok=True)` in `desktop.py` to prevent `FileNotFoundError` on fresh user environments lacking `~/.local/share/applications`.
- **Eliminated Fuzzy Process-Kill Footgun:** Restricted container process tracking to executables and working directories whose realpath resides inside the container directory or matches the container's Bubblewrap process tree, dropping substring matches on `cmdline` and `environ`.
- **Sanitized RPM Extraction:** Hardened RPM ingestion in `extractor.py` to inspect archive paths via `cpio -t` before extraction and reject members attempting directory traversal or absolute path writes.
- **Fail-Closed Exact Checksum Matching:** Updated `updater.py` to enforce strict whitespace-delimited equality on checksum filenames, rejecting substring or prefix collisions.
- **Hardened Strict Sandbox `/home` Masking:** Replaced single-user home masking with `--tmpfs /home --dir "$HOST_USER_HOME" --bind "$HERE" "$HERE"`, preventing visibility into other local users' home directories.
- **Selective Self-Uninstall Symlink Purge:** Constrained desktop symlink cleanup to symlinks pointing to `~/EnclosedApps` or `app-encloser`, preserving external applications' dangling symlinks.
- **Scoped AI Agent Interceptor:** Limited automated terminal guard exit-2 interception to explicit AI agent environment variables (`CLAUDE_CODE`, `CURSOR_TRACE_ID`, `AIDER`, `COPILOT`, etc.), allowing standard non-interactive cron jobs and scripts to run normally.

---

## [1.0.4] - 2026-11-10

### Security & Hardening
- **Real PID, IPC, and UTS Namespace Isolation:** Added `--unshare-pid`, `--unshare-ipc`, and `--unshare-uts` flags to Bubblewrap container launches with private `/proc` mounting, preventing enclosed processes from enumerating or signaling host processes.
- **Fail-Closed Cryptographic Verification:** Hardened `updater.py` to enforce strict fail-closed semantics; automated updates strictly abort if `SHA256SUMS.txt` is missing, the asset is unlisted, or checksum verification fails.
- **Pre-Contained Script Ingestion:** Container creation now applies the target isolation level upfront before running installer scripts, ensuring untrusted install scripts run inside Bubblewrap rather than uncontained on the host.
- **Tar Symlink Traversal Defense:** Added comprehensive symlink and hardlink path inspection across all Python versions, safely rejecting members attempting directory escapes.
- **Sudo & APT Shim Semantics:** Updated container `sudo` shim to explicitly reject unsupported user/group switching (`-u`/`-g`) with exit code 1; updated `apt` shim to halt full system upgrades (`upgrade`, `full-upgrade`) inside containers.
- **Packaging Compliance:** Added standard Debian machine-readable copyright specification (DEP-5) and AppStream 1.0 OARS content rating metadata.

### Bug Fixes & Improvements
- **Terminal Guard Menu Level Selection:** Fixed container name resolution in interactive guard menu, ensuring the user's chosen isolation level (Strict, Standard, Integrated) is faithfully applied.
- **Removed Network/Daemon Level Downgrade:** Container creation no longer silently downgrades strict isolation mode for applications with bundled service files.
- **Truthful Socket Documentation:** Documented that display, audio, and D-Bus sockets are bound read-write (`--bind`) as required by Linux domain socket IPC.

---

## [1.0.3] - 2026-11-09

### Security & Hardening
- **Eliminated Host Daemon Execution (P0):** Excised uncontained `systemd` service spawn loop from container launch scripts; bundled background services no longer execute unconfined on the host outside Bubblewrap.
- **Passive Safe AppImage Ingestion (P0):** Replaced direct host execution of untrusted AppImages (`--appimage-extract`) with passive SquashFS extraction via `unsquashfs` and `7z`, with isolated Bubblewrap container containment for any dynamic fallback.
- **Read-Only Xauthority Binding:** Sandboxed containers now mount `$XAUTHORITY` strictly read-only (`--ro-bind`), preventing untrusted containers from modifying or corrupting host X11 authorization data.
- **Cryptographic Updater Verification:** Added mandatory `SHA256SUMS.txt` checksum verification during automated updates; unverified or corrupted packages abort before installation.
- **Preserved User Customizations & Credentials:** Removed destructive deletion of user `usercustomize.py` from build and uninstall scripts; protected user credentials (`~/.claude/`) during host tool management.
- **Accurate Isolation Terminology:** Renamed Standard profile to "Private Application Environment", clearly distinguishing user directory and configuration separation from strict kernel sandbox boundaries.

### Bug Fixes & Functional Correctness
- **Universal Tarball sys.path Fix:** Updated `install.sh` to install to Python's standard user `site-packages` (`site.getusersitepackages()`), resolving `ModuleNotFoundError` on standalone tarball installations.
- **Self-Contained Container Install Helper:** Eliminated external module dependency in `encloser-install`, inlining safe path resolution and executable validation.
- **Truthful APT Reporting:** Replaced simulated success output with honest status reporting in rootless APT shims and CLI proxy, faithfully propagating subprocess exit codes.
- **Accurate Diagnostic Exit Code 126 Mapping:** Corrected diagnostic error categorization to identify Bubblewrap initialization and user namespace failures rather than misdiagnosing as file permissions.
- **Standard-Compliant JSON-RPC MCP Server:** Implemented JSON-RPC 2.0 error specifications (`-32700` parse error, `-32601` method not found) and returned full execution logs for container commands.
- **AppStream Metainfo & Debian Package Polish:** Added AppStream metainfo specification (`app.encloser.metainfo.xml`), standard pixmaps, and updated package control metadata for Ubuntu App Center compatibility.

---

## [1.0.2] - 2026-11-09

### Security & Hardening
- **Host RCE Vulnerability Neutralized:** Added strict executable path validation (`is_safe_executable_path`) and bash single-quoted literal assignment (`REL_EXEC='...'`) in `launch.sh`, eliminating shell command injection via malicious package filenames.
- **Fail-Closed Sandbox Architecture:** Bubblewrap strict sandbox mode now strictly fails closed (exiting with code 126 and clear diagnostic logging) if `bwrap` cannot be initialized, eliminating any silent fallback to unsandboxed host execution.
- **Minimal Private Device Mounts:** Replaced unrestricted `--dev-bind /dev /dev` with a private Bubblewrap `--dev /dev` mount, targeted hardware bindings (`/dev/dri` for GPU, `/dev/snd` for audio, `/dev/shm` for shared memory), and `--die-with-parent` process lifecycle enforcement.
- **Authentic APT & GPG Verification:** Removed `Acquire::AllowInsecureRepositories=true`, ensuring isolated APT repositories must be cryptographically signed and verified; GPG shim now strictly propagates real signature verification exit codes rather than accepting unverified bytes on failure.
- **Safe Container Name Resolution:** Replaced bidirectional substring matching with strict exact and case-insensitive container resolution for destructive commands (`uninstall`, `kill`, `level`), preventing accidental uninstallation of containers matching substrings (e.g. `probe` deleting `IsoProbe`).

### New Features & Enhancements
- **Built-in Update Engine & In-App Checker:** Added `app-encloser check-updates` and `app-encloser update` CLI commands, along with a real-time "Check for Updates" action in Preferences querying the GitHub Releases API.
- **Terminal Guard CLI Interface:** Implemented `app-encloser guard [enable|disable|status|sync]` command for full control over shell installation interception directly from terminal.
- **Active `strict_sandbox_by_default` Setting:** Wired up default isolation preference so newly created containers and apps default to strict Bubblewrap isolation when configured.
- **Dynamic Multi-Python Compatibility:** Upgraded `self_uninstall.py` to dynamically discover site-packages across Python 3.10, 3.11, 3.12, 3.13, and 3.14 (supporting Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, Ubuntu 26.04+, and Debian 12+).
- **Code Quality & Resource Cleanup:** Fixed unclosed file handles across `lifecycle.py`, `diagnostic.py`, `app_row.py`, and `info.py`, and corrected regex escaping in `encloser-install`.
- **Zero-Residue Test Suite:** Updated `build.sh` with `--package-only` flag and added automated pre/post-run test artifact wiping in `tests/verify_all.py` to ensure tests leave zero residual files on the host.

---

## [1.0.1] - 2026-11-09

### Security & Hardening
- **Strict Read-Only Root Filesystem (`--ro-bind / /`):** Strict sandbox mode now mounts the entire host root filesystem strictly read-only, preventing any accidental or malicious modifications to system paths (`/usr`, `/etc`, `/bin`, `/lib`).
- **Graceful Degradation Notifications:** Added explicit warnings to stderr and container runtime logs if Bubblewrap unprivileged user namespaces fail or are restricted on the host, preventing silent uncontained fallback.
- **Opt-In Terminal Guard:** Terminal installation interceptor defaults to disabled (`terminal_guard_enabled: False`), requiring explicit user consent before modifying shell configuration.
- **Basename Matching in C Preload Shim:** Refined binary redirection in `libencloser_shim.c` to exact basename matching for `nft`, eliminating false-positive matches on paths containing substrings (e.g. `connfti`).
- **GPG Shim Truthful Exit Codes:** Updated rootless GPG shim to faithfully propagate subprocess return codes rather than faking exit status 0 on failures.

### Bug Fixes
- **CLI `uninstall` Command Handler:** Added missing CLI handler for `app-encloser uninstall <AppName>` to execute full zero-residual removal directly from terminal.
- **Terminal Guard Menu Exception Fix:** Fixed argument signature and package resolution in interactive menu choices (1-3) of `handle_intercept_cmd`, preventing `TypeError` on terminal interception.
- **Cleaned Legacy Stubs:** Removed unused legacy stubs (`backend.py`, `window.py`) and redundant desktop file definitions.

### Documentation & Verification
- **Realistic Performance Metrics:** Clarified startup benchmarks in comparison matrix (instant native speed for Standard mode; ~20-50 ms for Bubblewrap user namespace initialization).
- **Self-Contained Automated Test Suite:** Enhanced integration test suite to run reliably and order-independently in headless container environments and isolated temporary homes.

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
