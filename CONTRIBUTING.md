# Contributing to App Encloser

Thank you for your interest in contributing to **App Encloser**!

---

## Development Setup

### 1. Prerequisites
- **OS:** Linux (Ubuntu 24.04 LTS or compatible Debian-based distribution)
- **Display Server:** Wayland (default) or X11
- **Python:** 3.10+
- **Core Packages:** `bubblewrap`, `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`, `gcc`

Install dependencies:
```bash
sudo apt update
sudo apt install -y python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 bubblewrap binutils gcc
```

### 2. Building the Project
Run the automated build script:
```bash
./build.sh
```

### 3. Running Automated Tests
Run the test verification suite to ensure all 31 suites pass 100%:
```bash
python3 tests/verify_all.py
```

---

## Code Quality Standards

1. **Self-Doubt & Rigorous Verification:** Never assume a fix works without testing every edge case and verifying both happy and failure paths.
2. **Comment-Free Source Files:** By design, all `.py`, `.sh`, and `.c` files in `src/` maintain zero comment lines (with the exception of line 1 shebangs and C `#include` directives). Code must be clean, self-documenting, and readable through clear naming.
3. **Single Source of Truth:** Edits must be made in `src/app_encloser/`. Never edit files in `debian/usr/` directly; use `./build.sh` to sync and package.
4. **Non-Privileged Execution:** App Encloser runs in unprivileged user space. Never introduce code that requires root permissions for container execution.

---

## Submitting Pull Requests

1. Fork the repository on GitHub.
2. Create a topic branch: `git checkout -b feature/my-new-feature`.
3. Commit your changes: `git commit -am 'feat: add amazing feature'`.
4. Run `./build.sh` and `python3 tests/verify_all.py` to ensure all tests pass.
5. Push to the branch: `git push origin feature/my-new-feature`.
6. Open a Pull Request on GitHub with a clear description of the problem solved.
