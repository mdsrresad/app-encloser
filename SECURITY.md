# Security Policy & Threat Model

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

Security and isolation integrity are top priorities for App Encloser. If you discover a security vulnerability or sandbox boundary bypass:

1. **Do not open a public issue.** Please disclose responsibly.
2. Use GitHub's **Private Vulnerability Reporting** on this repository to submit confidential details and reproduction steps.
3. Alternatively, report findings directly to the maintainer via GitHub Security Advisories.

---

## Threat Model & Security Architecture

App Encloser provides lightweight application containment on Linux desktops without root daemons. To maintain complete transparency, the table below documents exactly what is confined and what is shared:

### Isolation Matrix

| Subsystem / Resource | Private Application Environment | Strict Sandbox (`bwrap`) | System Integrated |
| :--- | :--- | :--- | :--- |
| **User Home (`$HOME`)** | Redirected to `userdata/home/` | Masked with isolated `tmpfs` + bound `userdata/home/` | Shared directly with host |
| **XDG Paths (`$XDG_*`)** | Isolated in container `userdata/` | Isolated in container `userdata/` | Shared directly with host |
| **Temporary Files (`/tmp`)** | Redirected `$TMPDIR` | Private container `/tmp` (`tmpfs`) | Shared host `/tmp` |
| **Host Root Filesystem** | Writable by user permissions | Strictly read-only (`--ro-bind / /`) | Writable by user permissions |
| **Container Directory** | Read-Write | Read-Write (`--bind` to app dir) | Read-Write |
| **Process Table (PID)** | Shared with host user | Isolated PID namespace (`--unshare-pid`) | Shared with host user |
| **IPC Resources** | Shared with host user | Isolated IPC namespace (`--unshare-ipc`) | Shared with host user |
| **Hostname / Domain (UTS)**| Shared with host user | Isolated UTS namespace (`--unshare-uts`) | Shared with host user |
| **Network Stack** | Shared with host | Shared with host (standard desktop net) | Shared with host |
| **Display Server Socket** | Shared (`WAYLAND_DISPLAY` / X11) | Bound read-only for GUI access | Shared |
| **Audio Subsystem** | Shared (PulseAudio / PipeWire) | Bound read-only socket for audio | Shared |
| **Session D-Bus** | Shared (`DBUS_SESSION_BUS_ADDRESS`)| Passed for desktop portals/notifications | Shared |

---

### Desktop Attack Surfaces & Security Considerations

When evaluating application confinement on Linux desktop systems, several cross-cutting factors must be understood:

1. **Private Application Environment vs. Kernel Sandbox:**
   - **Private Application Environment (Standard):** Provides user configuration and directory separation. It prevents applications from writing config, cache, and state files to `~/.config` or `~/.local`. *It is not an unprivileged kernel security boundary against malicious native binaries.*
   - **Strict Sandbox:** Employs Bubblewrap (`bwrap`) unprivileged user namespaces. Enforces kernel-level read-only root mounts (`--ro-bind / /`), masks the user home, and isolates PIDs. Writes outside the designated container directory are blocked by the kernel.

2. **X11 vs. Wayland Display Isolation:**
   - On legacy **X11** sessions, the X server protocol does not enforce window isolation between clients. Any client connected to the X11 display socket can theoretically inspect windows or capture input events from other clients.
   - For applications requiring strict window and input isolation, running under a modern **Wayland** compositor is strongly recommended.

3. **Session D-Bus & Desktop Portals:**
   - Enclosed GUI applications are granted access to the user session D-Bus to enable desktop notifications, file pickers (via XDG Desktop Portals), and system theming. Untrusted applications requiring total D-Bus isolation should be run without GUI forwarding.

4. **Kernel Namespace Requirements:**
   - Strict Sandbox requires unprivileged user namespaces supported and enabled by the host Linux kernel (`CLONE_NEWUSER`). On systems with hardened AppArmor profiles or disabled user namespaces (e.g., `sysctl kernel.apparmor_restrict_unprivileged_userns=1` without an exception profile), App Encloser detects the restriction and issues a diagnostic advisory.

---

## Security Remediation & Advisory History

App Encloser documents all security fixes openly and transparently:

### Version 1.0.3 (2026-11-09)
- **Eliminated Host Daemon Spawning:** Removed legacy host-side background monitoring loop from container initialization.
- **Passive AppImage Extraction:** Replaced live `--appimage-extract` execution on host with static SquashFS tools (`unsquashfs`, `7z`), falling back to an unprivileged sandboxed container when required.
- **Cryptographic Update Verification:** Added mandatory `SHA256SUMS.txt` validation before applying in-place auto-updates.
- **Truthful Status Reporting:** Replaced mock return codes in rootless APT shims with accurate subprocess exit status propagation.

### Version 1.0.2 (2026-11-09)
- **Shell Argument Injection Remediation:** Sanitized and single-quoted binary execution paths inside container `launch.sh` scripts, preventing command injection via malformed package file names.
- **Sandbox Root Read-Only Enforcement:** Replaced development `--dev-bind / /` fallback with strict `--ro-bind / /` in Bubblewrap invocation.
- **APT GPG Policy Hardening:** Removed `Acquire::AllowInsecureRepositories=true` from in-container APT configuration to ensure cryptographic repository signature verification.

### Version 1.0.1 (2026-11-09)
- **GPG Shim Return Code Fidelity:** Fixed rootless GPG shim to faithfully propagate real subprocess exit codes instead of returning zero unconditionally.
- **Multi-Distribution Compatibility:** Expanded multiarch dynamic linker detection across Ubuntu 22.04, 24.04, 26.04+, and Debian 12+.
