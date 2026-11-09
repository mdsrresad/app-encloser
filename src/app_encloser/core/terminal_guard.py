import os
import sys
import subprocess
from typing import Optional

from app_encloser.core.config import CONFIG_DIR, REAL_HOME, get_setting, update_setting

SOURCE_LINE = '[ -f "$HOME/.config/app-encloser/shell_guard.sh" ] && . "$HOME/.config/app-encloser/shell_guard.sh"'


def generate_shell_guard_script() -> str:
    lines = [
        'if [[ -z "$APP_ENCLOSER_BYPASS" ]]; then',
        '    sudo() {',
        '        if [[ "$1" == "apt" || "$1" == "apt-get" ]] && [[ "$2" == "install" ]]; then',
        '            command app-encloser --intercept-cmd "sudo $*"',
        '        else',
        '            command sudo "$@"',
        '        fi',
        '    }',
        '    apt() {',
        '        if [[ "$1" == "install" ]]; then',
        '            command app-encloser --intercept-cmd "apt $*"',
        '        else',
        '            command apt "$@"',
        '        fi',
        '    }',
        '    apt-get() {',
        '        if [[ "$1" == "install" ]]; then',
        '            command app-encloser --intercept-cmd "apt-get $*"',
        '        else',
        '            command apt-get "$@"',
        '        fi',
        '    }',
        '    npm() {',
        '        if [[ "$1" == "install" || "$1" == "i" ]] && [[ " $* " =~ " -g " || " $* " =~ " --global " ]]; then',
        '            command app-encloser --intercept-cmd "npm $*"',
        '        else',
        '            command npm "$@"',
        '        fi',
        '    }',
        '    pip() {',
        '        if [[ "$1" == "install" ]]; then',
        '            command app-encloser --intercept-cmd "pip $*"',
        '        else',
        '            command pip "$@"',
        '        fi',
        '    }',
        '    pip3() {',
        '        if [[ "$1" == "install" ]]; then',
        '            command app-encloser --intercept-cmd "pip3 $*"',
        '        else',
        '            command pip3 "$@"',
        '        fi',
        '    }',
        '    uv() {',
        '        if [[ "$1" == "tool" && "$2" == "install" ]] || [[ "$1" == "pip" && "$2" == "install" ]]; then',
        '            command app-encloser --intercept-cmd "uv $*"',
        '        else',
        '            command uv "$@"',
        '        fi',
        '    }',
        '    cargo() {',
        '        if [[ "$1" == "install" ]]; then',
        '            command app-encloser --intercept-cmd "cargo $*"',
        '        else',
        '            command cargo "$@"',
        '        fi',
        '    }',
        '    brew() {',
        '        if [[ "$1" == "install" ]]; then',
        '            command app-encloser --intercept-cmd "brew $*"',
        '        else',
        '            command brew "$@"',
        '        fi',
        '    }',
        'fi'
    ]
    return "\n".join(lines) + "\n"


def is_terminal_guard_active() -> bool:
    bashrc = os.path.join(REAL_HOME, ".bashrc")
    if not os.path.isfile(bashrc):
        return False
    try:
        with open(bashrc, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            return "app-encloser/shell_guard.sh" in content
    except Exception:
        return False


def set_terminal_guard_active(active: bool) -> bool:
    try:
        update_setting("terminal_guard_enabled", active)
        guard_script = os.path.join(CONFIG_DIR, "shell_guard.sh")
        if active:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(guard_script, "w", encoding="utf-8") as f:
                f.write(generate_shell_guard_script())
            os.chmod(guard_script, 0o755)

        rc_paths = [
            os.path.join(REAL_HOME, ".bashrc"),
            os.path.join(REAL_HOME, ".zshrc")
        ]
        for rc in rc_paths:
            if not os.path.exists(rc) and not rc.endswith(".bashrc"):
                continue
            lines = []
            if os.path.isfile(rc):
                with open(rc, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [ln.rstrip("\r\n") for ln in f]

            filtered = [ln for ln in lines if "app-encloser/shell_guard.sh" not in ln]
            if active:
                filtered.append(SOURCE_LINE)

            with open(rc, "w", encoding="utf-8") as f:
                for ln in filtered:
                    f.write(ln + "\n")
        return True
    except Exception:
        return False


def sync_terminal_guard() -> None:
    enabled = get_setting("terminal_guard_enabled", False)
    set_terminal_guard_active(enabled)


def _run_encloser_install(target: str, level: str = "strict"):
    from app_encloser.core.lifecycle import install_any_package, install_from_url_or_repo
    from app_encloser.core.container import set_enclosing_level, find_container_folder
    scope = "strict" if level == "strict" else ("integrated" if level == "integrated" else "isolated")
    if os.path.isfile(target):
        ok, msg = install_any_package(target, scope=scope)
    else:
        ok, msg = install_from_url_or_repo(target, scope=scope)
    if not ok:
        return False, msg
    folder = None
    if "~/EnclosedApps/" in msg:
        folder = msg.split("~/EnclosedApps/")[-1].strip()
    elif "'" in msg:
        m = re.search(r"'([^']+)'", msg)
        if m:
            folder = m.group(1)
    if folder:
        clean = find_container_folder(folder) or folder
        set_enclosing_level(clean, level)
        return True, clean
    return True, target


def handle_intercept_cmd(full_cmd: str) -> int:
    ai_env_vars = (
        "CLAUDECODE", "CLAUDE_CODE", "CODING_AGENT",
        "CURSOR_TRACE_ID", "AIDER", "CODEX", "MCP_SERVER", "AI_AGENT"
    )
    is_ai = (not sys.stdin.isatty()) or any(os.environ.get(k) for k in ai_env_vars)
    if is_ai:
        msg = (
            "[App Encloser Guard] AI Agent / Automated Terminal Tool Install Detected:\n"
            f"Command: {full_cmd}\n\n"
            "To keep this system 100% clean and avoid polluting the Host OS, please choose how to proceed:\n"
            "1. Complete Encloser (Recommended for maximum isolation):\n"
            f"   app-encloser install \"{full_cmd}\" --mode=strict\n"
            "2. Directory Encloser (Standard isolated ~/EnclosedApps environment):\n"
            f"   app-encloser install \"{full_cmd}\" --mode=standard\n"
            "3. Directly on Host OS (Bypass isolation):\n"
            f"   APP_ENCLOSER_BYPASS=1 {full_cmd}\n"
        )
        sys.stderr.write(msg)
        sys.exit(2)

    print("=" * 63)
    print("[App Encloser Guard] Terminal Package Installation Intercepted")
    print(f"Command: {full_cmd}")
    print("=" * 63)
    print("How would you like to install this software?")
    print("[1] Complete Encloser (Kernel strict sandbox, zero host pollution) [Recommended]")
    print("[2] Standard Directory Encloser (Isolated into ~/EnclosedApps)")
    print("[3] System Integrated Encloser (Isolated container with host system services)")
    print("[4] Directly on Host OS (Global host installation)")
    print("[c] Cancel installation")
    try:
        choice = input("Selection [1/2/3/4/c]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return 1

    if choice == "1":
        print("\nInstalling into Complete Encloser (Strict Sandbox)...")
        success, name_or_err = _run_encloser_install(full_cmd, level="strict")
        if success:
            print(f"Successfully enclosed '{name_or_err}' in Strict Sandbox universe.")
            return 0
        else:
            print(f"Installation failed: {name_or_err}")
            return 1
    elif choice == "2":
        print("\nInstalling into Standard Directory Encloser...")
        success, name_or_err = _run_encloser_install(full_cmd, level="standard")
        if success:
            print(f"Successfully enclosed '{name_or_err}' in ~/EnclosedApps.")
            return 0
        else:
            print(f"Installation failed: {name_or_err}")
            return 1
    elif choice == "3":
        print("\nInstalling into System Integrated Encloser...")
        success, name_or_err = _run_encloser_install(full_cmd, level="integrated")
        if success:
            print(f"Successfully enclosed '{name_or_err}' with System Integration.")
            return 0
        else:
            print(f"Installation failed: {name_or_err}")
            return 1
    elif choice == "4":
        print("\nBypassing App Encloser; installing directly on Host OS...")
        env = os.environ.copy()
        env["APP_ENCLOSER_BYPASS"] = "1"
        return subprocess.run(full_cmd, shell=True, env=env).returncode
    else:
        print("Installation cancelled.")
        return 1
