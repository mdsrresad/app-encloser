import os
import stat
import shlex
import shutil
import subprocess
from typing import List, Optional, Tuple, Dict, Any

from app_encloser.core.config import ENCLOSED_DIR, clean_folder_name, validate_container_name


def find_lib_dirs(app_files: str, prefix: str = "$HERE/app_files") -> List[str]:
    lib_dirs = set()
    std_dirs = [
        "usr/lib", "usr/lib64", "usr/lib/x86_64-linux-gnu",
        "lib", "lib64", "lib/x86_64-linux-gnu"
    ]
    for std in std_dirs:
        if os.path.isdir(os.path.join(app_files, std)):
            lib_dirs.add(f"{prefix}/{std}")

    if os.path.isdir(app_files):
        for root, dirs, files in os.walk(app_files):
            if any(f.endswith(".so") or ".so." in f for f in files):
                rel = os.path.relpath(root, app_files)
                if rel != ".":
                    lib_dirs.add(f"{prefix}/{rel}")
    return sorted(lib_dirs)


SHIM_BINARY_NAMES = {"apt", "apt-get", "gpg", "tee", "sudo", "nft", "curl", "wget", "encloser-install", "encloser-python", "encloser-brew", "install"}


def is_valid_app_binary(file_path: str) -> bool:
    if not os.path.isfile(file_path) or not os.access(file_path, os.X_OK):
        return False
    base = os.path.basename(file_path)
    if base in SHIM_BINARY_NAMES:
        return False
    if base.endswith((".sh", ".so", ".a", ".py", ".png", ".desktop", ".xml", ".env", ".fish", ".list")):
        return False
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            header = f.read(128)
            if "Clean container active:" in header:
                return False
    except Exception:
        pass
    return True


def is_network_or_daemon_app(name: str) -> bool:
    app_dir = os.path.join(ENCLOSED_DIR, name) if not os.path.isabs(name) else name
    if not os.path.isdir(app_dir):
        resolved = find_container_folder(name)
        if resolved:
            app_dir = os.path.join(ENCLOSED_DIR, resolved)
    app_files = os.path.join(app_dir, "app_files")
    if os.path.isdir(app_files):
        service_dirs = [
            os.path.join(app_files, "etc", "systemd", "system"),
            os.path.join(app_files, "usr", "lib", "systemd", "system"),
            os.path.join(app_files, "lib", "systemd", "system"),
            os.path.join(app_files, "etc", "init.d")
        ]
        for sdir in service_dirs:
            if os.path.isdir(sdir) and os.listdir(sdir):
                return True
    return False


def is_safe_executable_path(path: str) -> bool:
    import re
    if not path or not isinstance(path, str):
        return False
    if ".." in path:
        return False
    if any(c in path for c in ("$", "`", ";", "&", "|", "(", ")", "{", "}", "<", ">", '"', "'", "\n", "\r", " ", "\t")):
        return False
    return bool(re.match(r"^[a-zA-Z0-9_.\-]+(/[a-zA-Z0-9_.\-]+)*$", path.lstrip("/")))


def resolve_executable(app_files: str, orig_exec: str = "") -> Optional[str]:
    import re
    app_dir = os.path.dirname(app_files)
    folder_name = os.path.basename(app_dir)
    clean_stem = re.sub(r"[\-_]\d+$", "", folder_name).lower()

    targets = [clean_stem, folder_name.lower()]

    desk_dir = ""
    if os.path.isdir(app_files):
        for root, _, files in os.walk(app_files):
            for f in files:
                if f.endswith(".desktop"):
                    desk_path = os.path.join(root, f)
                    desk_dir = root
                    desk_base = f[:-8].lower()
                    if desk_base not in targets:
                        targets.append(desk_base)
                    try:
                        with open(desk_path, "r", encoding="utf-8", errors="ignore") as df:
                            for line in df:
                                if line.startswith("Name="):
                                    nm = line.split("=", 1)[1].strip().lower()
                                    if nm and nm not in targets:
                                        targets.append(nm)
                                    break
                    except Exception:
                        pass
                    break
            if desk_dir:
                break

    if orig_exec:
        clean = orig_exec.lstrip("/")
        tokens = re.findall(r"[\s/\'\"]([a-zA-Z0-9_\-\.]+)(?:[\s\'\"-]|$)", orig_exec)
        for t in tokens:
            t_low = t.lower()
            if t_low not in ("bash", "sh", "env", "sudo", "pkexec", "c") and t_low not in targets:
                targets.insert(0, t_low)

        cand = os.path.join(app_files, clean)
        if is_safe_executable_path(clean) and is_valid_app_binary(cand):
            return clean
        for sub in ("bin", "usr/bin", "usr/local/bin", "opt"):
            sub_cand = os.path.join(app_files, sub, os.path.basename(clean))
            rel = os.path.relpath(sub_cand, app_files)
            if is_safe_executable_path(rel) and is_valid_app_binary(sub_cand):
                return rel

    user_bin = os.path.join(app_dir, "userdata", "bin")
    if os.path.isdir(user_bin):
        user_cands = []
        for f in sorted(os.listdir(user_bin)):
            fp = os.path.join(user_bin, f)
            if is_valid_app_binary(fp):
                user_cands.append(f)
        for t in targets:
            for uc in user_cands:
                if uc.lower() == t:
                    return f"userdata/bin/{uc}"
        if user_cands:
            return f"userdata/bin/{user_cands[0]}"

    user_local_bin = os.path.join(app_dir, "userdata", "home", ".local", "bin")
    if os.path.isdir(user_local_bin):
        local_cands = []
        for f in sorted(os.listdir(user_local_bin)):
            fp = os.path.join(user_local_bin, f)
            if is_valid_app_binary(fp):
                local_cands.append(f)
        for t in targets:
            for lc in local_cands:
                if lc.lower() == t:
                    return f"userdata/home/.local/bin/{lc}"
        if local_cands:
            return f"userdata/home/.local/bin/{local_cands[0]}"

    HELPER_WORDS = (
        "helper", "crash", "updater", "glxtest", "vaapitest",
        "reporter", "minidump", "broker", "worker", "watchdog",
        "shim", "test", "check", "setup", "uninstall", "deinstall"
    )

    scored_cands = []
    if os.path.isdir(app_files):
        for root, _, files in os.walk(app_files):
            for f in files:
                fp = os.path.join(root, f)
                if not is_valid_app_binary(fp):
                    continue
                base = f.lower()
                rel = os.path.relpath(fp, app_files)
                score = 100

                if any(h in base for h in HELPER_WORDS):
                    score -= 600

                for t in targets:
                    if not t:
                        continue
                    if base == t:
                        score += 1200
                    elif base in (f"{t}-bin", f"{t}.bin", f"{t}_bin"):
                        score += 900
                    elif base.startswith(t) or t.startswith(base):
                        score += 500
                    elif t in base:
                        score += 250

                if rel.startswith(("bin/", "usr/bin/", "usr/local/bin/", "opt/")):
                    score += 150

                if desk_dir and root == desk_dir:
                    score += 300

                depth = rel.count(os.sep)
                score -= depth * 15

                scored_cands.append((score, rel))

    if scored_cands:
        scored_cands.sort(key=lambda s: s[0], reverse=True)
        return scored_cands[0][1]

    return None


def is_bwrap_supported() -> bool:
    import shutil
    import subprocess
    if not shutil.which("bwrap"):
        return False
    try:
        res = subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"], capture_output=True, timeout=2)
        return res.returncode == 0
    except Exception:
        return False


def is_strict_sandbox(app_dir: str) -> bool:
    return os.path.isfile(os.path.join(app_dir, ".strict_sandbox"))


def set_strict_sandbox(folder_name: str, enable: bool = True) -> bool:
    valid = validate_container_name(folder_name)
    if not valid:
        return False
    app_dir = os.path.join(ENCLOSED_DIR, valid)
    if not os.path.isdir(app_dir):
        return False
    flag = os.path.join(app_dir, ".strict_sandbox")
    if enable:
        with open(flag, "w", encoding="utf-8") as f:
            f.write("1")
    else:
        if os.path.isfile(flag):
            os.remove(flag)
    return True


def find_container_folder(name: str, exact_only: bool = True) -> Optional[str]:
    valid = validate_container_name(name)
    if not valid or not os.path.isdir(ENCLOSED_DIR):
        return None
    raw = valid
    direct = os.path.join(ENCLOSED_DIR, raw)
    if os.path.isdir(direct):
        return raw
    low = raw.lower()
    entries = sorted(os.listdir(ENCLOSED_DIR))
    for entry in entries:
        if entry.lower() == low and os.path.isdir(os.path.join(ENCLOSED_DIR, entry)):
            return entry
    if not exact_only:
        matches = [entry for entry in entries if entry.lower().startswith(low) and os.path.isdir(os.path.join(ENCLOSED_DIR, entry))]
        if len(matches) == 1:
            return matches[0]
    return None


def get_enclosing_level(folder_or_path: str) -> str:
    resolved = find_container_folder(folder_or_path) if not os.path.isabs(folder_or_path) else None
    target = resolved or folder_or_path
    app_dir = target if os.path.isabs(target) else os.path.join(ENCLOSED_DIR, target)
    level_file = os.path.join(app_dir, ".enclosing_level")
    if os.path.isfile(level_file):
        try:
            with open(level_file, "r", encoding="utf-8") as f:
                val = f.read().strip().lower()
                if val in ("standard", "strict", "integrated"):
                    return val
        except Exception:
            pass
    if is_strict_sandbox(app_dir):
        return "strict"
    return "standard"


def get_enclosing_level_details(level: str) -> Dict[str, str]:
    lvl = level.strip().lower()
    if lvl == "strict":
        return {
            "level": "strict",
            "title": "Strict Sandbox",
            "badge": "Strict Sandbox",
            "description": "Kernel namespace isolation via Bubblewrap (bwrap). Mounts host root read-only, masks host home with private tmpfs, and isolates runtime data.",
            "badge_css": "badge-level-strict"
        }
    elif lvl == "integrated":
        return {
            "level": "integrated",
            "title": "System Integrated",
            "badge": "Integrated",
            "description": "Direct host integration. Application data resides in container directory, but executes without filesystem restrictions or namespace isolation.",
            "badge_css": "badge-level-integrated"
        }
    return {
        "level": "standard",
        "title": "Private Application Environment",
        "badge": "Private Environment",
        "description": "Directory and configuration separation. Redirects $HOME and XDG data inside the container to prevent host clutter (not a kernel security boundary).",
        "badge_css": "badge-level-standard"
    }


def set_enclosing_level(folder_name: str, level: str) -> bool:
    resolved = find_container_folder(folder_name)
    if not resolved:
        valid = validate_container_name(folder_name)
        if not valid:
            return False
        resolved = valid
    app_dir = os.path.join(ENCLOSED_DIR, resolved)
    if not os.path.isdir(app_dir):
        return False
    norm_level = level.strip().lower()
    if norm_level not in ("standard", "strict", "integrated"):
        return False
    level_file = os.path.join(app_dir, ".enclosing_level")
    try:
        with open(level_file, "w", encoding="utf-8") as f:
            f.write(norm_level)
    except Exception:
        return False

    if norm_level == "strict":
        set_strict_sandbox(resolved, True)
    else:
        set_strict_sandbox(resolved, False)

    try:
        from app_encloser.core.lifecycle import repair_app
        repair_app(resolved)
    except Exception:
        pass
    return True


def set_container_option(folder_name: str, option: str, enabled: bool) -> bool:
    resolved = find_container_folder(folder_name)
    if not resolved:
        valid = validate_container_name(folder_name)
        if not valid:
            return False
        resolved = valid
    app_dir = os.path.join(ENCLOSED_DIR, resolved)
    if not os.path.isdir(app_dir):
        return False
    clean_opt = option.lstrip(".")
    if clean_opt not in ("no_net", "no_display", "no_dbus", "no_sound"):
        return False
    opt_file = os.path.join(app_dir, f".{clean_opt}")
    try:
        if enabled:
            with open(opt_file, "w", encoding="utf-8") as f:
                f.write("1")
        else:
            if os.path.exists(opt_file):
                os.remove(opt_file)
        return True
    except Exception:
        return False


def get_container_options(folder_name: str) -> Dict[str, bool]:
    resolved = find_container_folder(folder_name)
    if not resolved:
        valid = validate_container_name(folder_name)
        if not valid:
            return {}
        resolved = valid
    app_dir = os.path.join(ENCLOSED_DIR, resolved)
    if not os.path.isdir(app_dir):
        return {}
    return {
        "no_net": os.path.isfile(os.path.join(app_dir, ".no_net")),
        "no_display": os.path.isfile(os.path.join(app_dir, ".no_display")),
        "no_dbus": os.path.isfile(os.path.join(app_dir, ".no_dbus")),
        "no_sound": os.path.isfile(os.path.join(app_dir, ".no_sound"))
    }


def write_launch_script(app_dir: str, rel_exec: str, pkg_format: str):
    import re
    launch_sh = os.path.join(app_dir, "launch.sh")
    app_files = os.path.join(app_dir, "app_files")
    lib_dirs = find_lib_dirs(app_files)
    ld_path = ":".join(lib_dirs) if lib_dirs else ""

    clean_rel = rel_exec.lstrip('/')
    if not is_safe_executable_path(clean_rel):
        clean_rel = re.sub(r'[^a-zA-Z0-9_\-\./]', '_', clean_rel)
    escaped_rel = clean_rel.replace("'", "'\\''")

    lines = [
        "#!/usr/bin/env bash",
        'export HERE="$(dirname "$(readlink -f "${0}")")"',
        'export PATH="$HERE/userdata/shims:$HERE/userdata/bin:$HERE/userdata/home/.local/bin:$HERE/userdata/home/.npm-global/bin:$HERE/userdata/home/.cargo/bin:$HERE/userdata/local_share/uv/python:$HERE/app_files/usr/bin:$HERE/app_files/usr/local/bin:$HERE/app_files/bin:$HERE/app_files/opt:$PATH"',
        'if [[ -d "$HERE/userdata/linuxbrew/bin" ]]; then',
        '    export PATH="$HERE/userdata/linuxbrew/bin:$HERE/userdata/linuxbrew/sbin:$PATH"',
        'fi',
        'if [[ -d "$HERE/userdata/venv/bin" ]]; then',
        '    export PATH="$HERE/userdata/venv/bin:$PATH"',
        'fi',
    ]
    if ld_path:
        lines.append(f'export LD_LIBRARY_PATH="{ld_path}:$LD_LIBRARY_PATH"')
    lines.append('export XDG_DATA_DIRS="$HERE/app_files/usr/share:$HERE/app_files/usr/local/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"')

    lines.extend([
        'export HOME="$HERE/userdata/home"',
        'export XDG_CONFIG_HOME="$HERE/userdata/config"',
        'export XDG_CACHE_HOME="$HERE/userdata/cache"',
        'export XDG_DATA_HOME="$HERE/userdata/local_share"',
        'export XDG_STATE_HOME="$HERE/userdata/state"',
        'export TMPDIR="$HERE/userdata/tmp"',
        'export STATE_DIRECTORY="$HERE/userdata/state"',
        'export RUNTIME_DIRECTORY="$HERE/userdata/run"',
        'export LOGS_DIRECTORY="$HERE/userdata/logs"',
        'export UV_CACHE_DIR="$HERE/userdata/cache/uv"',
        'export UV_PYTHON_INSTALL_DIR="$HERE/userdata/local_share/uv/python"',
        'export UV_TOOL_DIR="$HERE/userdata/local_share/uv/tools"',
        'export UV_TOOL_BIN_DIR="$HERE/userdata/bin"',
        'export PIP_CACHE_DIR="$HERE/userdata/cache/pip"',
        'export PYTHONUSERBASE="$HERE/userdata/home/.local"',
        'export OLLAMA_MODELS="$HERE/userdata/home/.ollama/models"',
        'export NPM_CONFIG_CACHE="$HERE/userdata/cache/npm"',
        'export NPM_CONFIG_PREFIX="$HERE/userdata/home/.npm-global"',
        'export CARGO_HOME="$HERE/userdata/home/.cargo"',
        'export RUSTUP_HOME="$HERE/userdata/home/.rustup"',
        'export HOMEBREW_CACHE="$HERE/userdata/cache/homebrew"',
        'export HOMEBREW_LOGS="$HERE/userdata/logs/homebrew"',
        'export HOMEBREW_TEMP="$HERE/userdata/tmp"',
        'ENCLOSING_LEVEL="standard"',
        'if [[ -f "$HERE/.enclosing_level" ]]; then',
        '    ENCLOSING_LEVEL="$(cat "$HERE/.enclosing_level" 2>/dev/null | tr -d "[:space:]" | tr "[:upper:]" "[:lower:]")"',
        'elif [[ -f "$HERE/.strict_sandbox" ]]; then',
        '    ENCLOSING_LEVEL="strict"',
        'fi',
        'if [[ "$ENCLOSING_LEVEL" != "strict" && -f "$HERE/app_files/lib/libencloser_shim.so" ]]; then',
        '    export ENCLOSER_NFT_SHIM="$HERE/userdata/shims/nft"',
        '    export LD_PRELOAD="$HERE/app_files/lib/libencloser_shim.so${LD_PRELOAD:+:$LD_PRELOAD}"',
        'fi',
        'unset SSH_AUTH_SOCK GPG_AGENT_INFO KRB5CCNAME',
        'mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" "$XDG_STATE_HOME" "$TMPDIR" "$STATE_DIRECTORY" "$RUNTIME_DIRECTORY" "$LOGS_DIRECTORY" "$HERE/userdata/keyrings" "$HERE/userdata/etc_apt/sources.list.d"',
        'chmod 700 "$HERE/userdata"',
        'LOG_FILE="$HERE/userdata/last_run.log"',
        'STATUS_FILE="$HERE/userdata/last_exit_code"',
        'PID_FILE="$HERE/userdata/running.pid"',
        'DAEMON_PIDS=()',
        'cleanup_pid() { local rc=$?; rm -f "$PID_FILE" 2>/dev/null || true; echo "$rc" > "$STATUS_FILE"; if [[ "$IS_CUSTOM_CMD" -eq 0 && ${#DAEMON_PIDS[@]} -gt 0 ]]; then for dpid in "${DAEMON_PIDS[@]}"; do kill "$dpid" 2>/dev/null || true; done; fi; }',
        'trap cleanup_pid EXIT INT TERM',
        ': > "$LOG_FILE"',
        'if [[ -n "$WAYLAND_DISPLAY" ]]; then',
        '    export WAYLAND_DISPLAY="$WAYLAND_DISPLAY"',
        '    export GDK_BACKEND="wayland,x11"',
        '    export QT_QPA_PLATFORM="wayland;xcb"',
        '    export ELECTRON_OZONE_PLATFORM_HINT="auto"',
        '    export MOZ_ENABLE_WAYLAND="1"',
        'fi',
        'if [[ -n "$DISPLAY" ]]; then',
        '    export DISPLAY="$DISPLAY"',
        'fi',
        'if [[ -n "$XAUTHORITY" && -f "$XAUTHORITY" ]]; then',
        '    export XAUTHORITY="$XAUTHORITY"',
        'fi',
        'if [[ -n "$PULSE_SERVER" ]]; then',
        '    export PULSE_SERVER="$PULSE_SERVER"',
        'fi',
        'HOST_USER_HOME="$(getent passwd "$UID" 2>/dev/null | cut -d: -f6)"',
        'HOST_USER_HOME="${HOST_USER_HOME:-/home/$USER}"',
        f"REL_EXEC='{escaped_rel}'",
        'if [[ "$REL_EXEC" == userdata/* ]]; then',
        '    TARGET_BIN="$HERE/$REL_EXEC"',
        'else',
        '    TARGET_BIN="$HERE/app_files/$REL_EXEC"',
        'fi',
        'BWRAP_CMD=()',
        'SBOX_FLAG=""',
        'TB_NAME="$(basename "$TARGET_BIN" 2>/dev/null)"',
        'if [[ "$TB_NAME" =~ ^(chrome|chromium|google-chrome|brave|msedge|opera|vivaldi|electron)$ ]]; then',
        '    SBOX_FLAG="--no-sandbox"',
        'elif [[ -f "$(dirname "$TARGET_BIN")/chrome-sandbox" ]]; then',
        '    if [[ -x "$TARGET_BIN" ]] && ! head -n 1 "$TARGET_BIN" 2>/dev/null | grep -q "^#!"; then',
        '        SBOX_FLAG="--no-sandbox"',
        '    fi',
        'fi',
        'if [[ -n "$SBOX_FLAG" || -f "$(dirname "$TARGET_BIN")/resources/app.asar" || -f "$(dirname "$TARGET_BIN")/chrome-sandbox" ]]; then',
        '    export ELECTRON_DISABLE_SANDBOX="1"',
        'fi',
        'if [[ "$ENCLOSING_LEVEL" == "strict" ]]; then',
        '    if ! command -v bwrap >/dev/null 2>&1; then',
        '        echo "[App Encloser WARNING] Bubblewrap (bwrap) is not installed on system. Falling back to standard container isolation." >&2',
        '        echo "[App Encloser WARNING] Bubblewrap (bwrap) is not installed on system. Falling back to standard container isolation." >> "$LOG_FILE"',
        '        ENCLOSING_LEVEL="standard"',
        '        BWRAP_CMD=()',
        '    elif ! bwrap --ro-bind / / true 2>/dev/null; then',
        '        echo "[App Encloser WARNING] Bubblewrap user namespaces restricted on host kernel. Falling back to standard container isolation." >&2',
        '        echo "[App Encloser WARNING] Bubblewrap user namespaces restricted on host kernel. Falling back to standard container isolation." >> "$LOG_FILE"',
        '        ENCLOSING_LEVEL="standard"',
        '        BWRAP_CMD=()',
        '    else',
        '        BWRAP_CMD=(bwrap --die-with-parent --new-session --unshare-pid --unshare-ipc --unshare-uts --unshare-cgroup-try --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp --tmpfs /home --tmpfs "$HOST_USER_HOME" --ro-bind "$HERE" "$HERE" --setenv HERE "$HERE" --setenv HOME "$HOME" --setenv PATH "$PATH" --setenv LD_LIBRARY_PATH "${LD_LIBRARY_PATH:-}" --setenv XDG_CONFIG_HOME "$XDG_CONFIG_HOME" --setenv XDG_CACHE_HOME "$XDG_CACHE_HOME" --setenv XDG_DATA_HOME "$XDG_DATA_HOME" --setenv XDG_STATE_HOME "$XDG_STATE_HOME" --setenv TMPDIR "$TMPDIR" --setenv STATE_DIRECTORY "$STATE_DIRECTORY" --setenv RUNTIME_DIRECTORY "$RUNTIME_DIRECTORY" --setenv LOGS_DIRECTORY "$LOGS_DIRECTORY")',
        '        for rw_sub in home config cache local_share state run logs tmp keyrings etc_apt var_lib_apt_lists venv bin; do',
        '            mkdir -p "$HERE/userdata/$rw_sub"',
        '            BWRAP_CMD+=(--bind "$HERE/userdata/$rw_sub" "$HERE/userdata/$rw_sub")',
        '        done',
        '        if [[ -f "$HERE/app_files/lib/libencloser_shim.so" ]]; then',
        '            BWRAP_CMD+=(--setenv ENCLOSER_NFT_SHIM "$HERE/userdata/shims/nft" --setenv LD_PRELOAD "$HERE/app_files/lib/libencloser_shim.so")',
        '        fi',
        '        if [[ -f "$HERE/.no_net" || "$ENCLOSER_NO_NET" == "1" ]]; then',
        '            BWRAP_CMD+=(--unshare-net)',
        '        fi',
        '        if [[ ! -f "$HERE/.no_display" && "$ENCLOSER_NO_DISPLAY" != "1" ]]; then',
        '            if [[ -d "/dev/dri" ]]; then',
        '                BWRAP_CMD+=(--dev-bind /dev/dri /dev/dri)',
        '            fi',
        '            if [[ -d "/tmp/.X11-unix" ]]; then',
        '                BWRAP_CMD+=(--bind /tmp/.X11-unix /tmp/.X11-unix)',
        '            fi',
        '            if [[ -n "$XDG_RUNTIME_DIR" && -d "$XDG_RUNTIME_DIR" ]]; then',
        '                if [[ -n "$WAYLAND_DISPLAY" && -e "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]]; then',
        '                    BWRAP_CMD+=(--bind "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY")',
        '                fi',
        '            fi',
        '            if [[ -n "$XAUTHORITY" && -f "$XAUTHORITY" ]]; then',
        '                BWRAP_CMD+=(--ro-bind "$XAUTHORITY" "$XAUTHORITY")',
        '            fi',
        '        fi',
        '        if [[ ! -f "$HERE/.no_sound" && "$ENCLOSER_NO_SOUND" != "1" ]]; then',
        '            if [[ -d "/dev/snd" ]]; then',
        '                BWRAP_CMD+=(--dev-bind /dev/snd /dev/snd)',
        '            fi',
        '            if [[ -n "$XDG_RUNTIME_DIR" && -e "$XDG_RUNTIME_DIR/pulse" ]]; then',
        '                BWRAP_CMD+=(--bind "$XDG_RUNTIME_DIR/pulse" "$XDG_RUNTIME_DIR/pulse")',
        '            fi',
        '        fi',
        '        if [[ -f "$HERE/.allow_dbus" || "$ENCLOSER_ALLOW_DBUS" == "1" ]]; then',
        '            if [[ -n "$XDG_RUNTIME_DIR" && -e "$XDG_RUNTIME_DIR/bus" ]]; then',
        '                BWRAP_CMD+=(--bind "$XDG_RUNTIME_DIR/bus" "$XDG_RUNTIME_DIR/bus")',
        '            fi',
        '        else',
        '            BWRAP_CMD+=(--unsetenv DBUS_SESSION_BUS_ADDRESS)',
        '        fi',
        '        BWRAP_CMD+=(--tmpfs /dev/shm)',
        '        if [[ -d "$HERE/userdata/linuxbrew" ]]; then',
        '            BWRAP_CMD+=(--bind "$HERE/userdata/linuxbrew" /home/linuxbrew/.linuxbrew)',
        '        fi',
        '        for vld in "$HERE/userdata"/var_lib_*; do',
        '            if [[ -d "$vld" ]]; then',
        '                v_target="/var/lib/$(basename "$vld" | sed "s/^var_lib_//" | tr "_" "-")"',
        '                BWRAP_CMD+=(--bind "$vld" "$v_target")',
        '            fi',
        '        done',
        '    fi',
        'fi',
        'RUN_CMD=()',
        'IS_CUSTOM_CMD=0',
        'if [[ "$1" == "--exec" ]]; then',
        '    shift',
        '    IS_CUSTOM_CMD=1',
        '    RUN_CMD=("$@")',
        'elif [[ "$#" -gt 0 && ( "$1" == "bash" || "$1" == "sh" || "$1" == "/bin/bash" || "$1" == "/bin/sh" ) ]]; then',
        '    IS_CUSTOM_CMD=1',
        '    RUN_CMD=("$@")',
        'else',
        '    RUN_CMD=("$TARGET_BIN" $SBOX_FLAG "$@")',
        'fi',
        'if [[ "$IS_CUSTOM_CMD" -eq 1 ]]; then',
        '    cd "$HOME" 2>/dev/null || cd "$HERE"',
        '    if [[ -t 1 || "$ENCLOSER_STREAM_LOG" == "1" ]]; then',
        '        if [[ ${#BWRAP_CMD[@]} -gt 0 ]]; then',
        '            if [[ "$ENCLOSER_STREAM_LOG" == "1" ]]; then',
        '                "${BWRAP_CMD[@]}" "${RUN_CMD[@]}" 2>&1 | tee "$LOG_FILE"',
        '                EC="${PIPESTATUS[0]}"',
        '            else',
        '                "${BWRAP_CMD[@]}" "${RUN_CMD[@]}"',
        '                EC=$?',
        '            fi',
        '        else',
        '            if [[ "$ENCLOSER_STREAM_LOG" == "1" ]]; then',
        '                "${RUN_CMD[@]}" 2>&1 | tee "$LOG_FILE"',
        '                EC="${PIPESTATUS[0]}"',
        '            else',
        '                "${RUN_CMD[@]}"',
        '                EC=$?',
        '            fi',
        '        fi',
        '    else',
        '        if [[ ${#BWRAP_CMD[@]} -gt 0 ]]; then',
        '            "${BWRAP_CMD[@]}" "${RUN_CMD[@]}" >"$LOG_FILE" 2>&1 &',
        '            C_PID=$!',
        '            echo "$C_PID" > "$PID_FILE"',
        '            wait "$C_PID"',
        '            EC=$?',
        '        else',
        '            "${RUN_CMD[@]}" >"$LOG_FILE" 2>&1 &',
        '            C_PID=$!',
        '            echo "$C_PID" > "$PID_FILE"',
        '            wait "$C_PID"',
        '            EC=$?',
        '        fi',
        '    fi',
        'else',
        '    if [[ ${#BWRAP_CMD[@]} -gt 0 ]]; then',
        '        "${BWRAP_CMD[@]}" "${RUN_CMD[@]}" >"$LOG_FILE" 2>&1 &',
        '        C_PID=$!',
        '        echo "$C_PID" > "$PID_FILE"',
        '        wait "$C_PID"',
        '        EC=$?',
        '    else',
        '        "${RUN_CMD[@]}" >"$LOG_FILE" 2>&1 &',
        '        C_PID=$!',
        '        echo "$C_PID" > "$PID_FILE"',
        '        wait "$C_PID"',
        '        EC=$?',
        '    fi',
        'fi',
        'echo "$EC" > "$STATUS_FILE"',
        'cleanup_pid',
        'exit $EC'
    ])

    with open(launch_sh, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(launch_sh, 0o755)


def run_in_container(folder_name: str, cmd_args: List[str], env_vars: Optional[Dict[str, str]] = None, status_cb: Optional[Any] = None) -> int:
    valid = validate_container_name(folder_name)
    if not valid:
        return 1
    folder_name = valid
    app_dir = os.path.join(ENCLOSED_DIR, folder_name)
    if not os.path.isdir(app_dir):
        return 1
    launch_sh = os.path.join(app_dir, "launch.sh")
    if not os.path.isfile(launch_sh) or not os.access(launch_sh, os.X_OK):
        try:
            from app_encloser.core.diagnostic import auto_repair_container
            auto_repair_container(folder_name)
        except Exception:
            pass
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)
    if os.path.isfile(launch_sh):
        if not os.access(launch_sh, os.X_OK):
            try:
                os.chmod(launch_sh, 0o755)
            except Exception:
                pass
        clean_args = list(cmd_args) if cmd_args else []
        if clean_args and clean_args[0] == "--exec":
            clean_args = clean_args[1:]
        if status_cb:
            env["ENCLOSER_STREAM_LOG"] = "1"
            env["PYTHONUNBUFFERED"] = "1"
            import re
            proc = subprocess.Popen(
                [launch_sh, "--exec"] + clean_args,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0
            )
            buf = b""
            while True:
                chunk = proc.stdout.read(64)
                if not chunk:
                    break
                buf += chunk
                parts = re.split(b'[\r\n]+', buf)
                if len(parts) > 1:
                    for p in parts[:-1]:
                        s = p.decode('utf-8', errors='replace').strip()
                        if s:
                            status_cb(s)
                    buf = parts[-1]
            if buf:
                s = buf.decode('utf-8', errors='replace').strip()
                if s:
                    status_cb(s)
            proc.wait()
            return proc.returncode
        if clean_args:
            return subprocess.run([launch_sh, "--exec"] + clean_args, env=env).returncode
        return subprocess.run([launch_sh], env=env).returncode
    return 1


def open_container_shell(folder_name: str) -> int:
    valid = validate_container_name(folder_name)
    if not valid:
        return 1
    folder_name = valid
    app_dir = os.path.join(ENCLOSED_DIR, folder_name)
    bashrc_path = os.path.join(app_dir, "userdata", ".container_bashrc")
    os.makedirs(os.path.join(app_dir, "userdata"), exist_ok=True)
    content = (
        'if [ -f /etc/bash.bashrc ]; then . /etc/bash.bashrc; fi\n'
        'if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n'
        f'PS1="\\[\\e[1;36m\\][Universe: {folder_name}]\\[\\e[0m\\] \\w\\$ "\n'
        'echo -e "\\033[1;35m===============================================================\\033[0m"\n'
        f'echo -e "\\033[1;32m  App Encloser Container Universe: {folder_name}\\033[0m"\n'
        'echo -e "\\033[1;34m  Commands isolated to this container:\\033[0m"\n'
        'echo -e "    \\033[1;33msudo apt install <pkg>\\033[0m       (or <pkg>=<ver> to swap versions)"\n'
        'echo -e "    \\033[1;33msudo apt remove <pkg>\\033[0m        (remove override & use host)"\n'
        'echo -e "    \\033[1;33mencloser-python <version>\\033[0m    (e.g. encloser-python 3.11)"\n'
        'echo -e "    \\033[1;33mencloser-brew install <pkg>\\033[0m  (isolated Homebrew in container)"\n'
        'echo -e "\\033[1;35m===============================================================\\033[0m"\n'
    )
    with open(bashrc_path, "w", encoding="utf-8") as f:
        f.write(content)
    return run_in_container(folder_name, ["/bin/bash", "--rcfile", bashrc_path, "-i"])


def get_running_app_pids(folder_name: str, fast_check: bool = True) -> List[int]:
    valid = validate_container_name(folder_name)
    if not valid:
        return []
    folder_name = valid
    app_dir = os.path.join(ENCLOSED_DIR, folder_name)
    pids = set()
    my_pid = os.getpid()
    app_real = os.path.realpath(app_dir) if os.path.isdir(app_dir) else ""

    if not app_real:
        return []

    pid_file = os.path.join(app_dir, "userdata", "running.pid")
    if os.path.isfile(pid_file):
        try:
            with open(pid_file, "r") as f:
                for line in f:
                    s = line.strip()
                    if s.isdigit():
                        p = int(s)
                        if p != my_pid:
                            try:
                                os.kill(p, 0)
                                p_exe = ""
                                try:
                                    p_exe = os.path.realpath(f"/proc/{p}/exe")
                                except Exception:
                                    pass
                                if p_exe:
                                    pids.add(p)
                            except OSError:
                                pass
        except Exception:
            pass

    if fast_check:
        return sorted(pids)

    try:
        proc_entries = os.listdir("/proc")
    except Exception:
        proc_entries = []

    for pid_str in proc_entries:
        if not pid_str.isdigit():
            continue
        p = int(pid_str)
        if p == my_pid or p in pids:
            continue
        proc_dir = f"/proc/{pid_str}"
        try:
            exe_link = ""
            try:
                exe_link = os.path.realpath(f"{proc_dir}/exe")
                if exe_link and (exe_link == app_real or exe_link.startswith(app_real + os.sep)):
                    pids.add(p)
                    continue
            except Exception:
                pass

            if exe_link.endswith("/bwrap") or exe_link == "/usr/bin/bwrap":
                try:
                    with open(f"{proc_dir}/cmdline", "rb") as f:
                        cmd = f.read().decode("utf-8", errors="ignore")
                        if app_real in cmd or f"/EnclosedApps/{folder_name}" in cmd:
                            pids.add(p)
                            continue
                except Exception:
                    pass
        except Exception:
            pass

    alive_pids = []
    for p in pids:
        try:
            os.kill(p, 0)
            alive_pids.append(p)
        except OSError:
            pass
    return sorted(alive_pids)


def get_pids_ram_mb(pids: List[int]) -> float:
    if not pids:
        return 0.0
    total_pages = 0
    page_size = 4096
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
    except Exception:
        pass
    for pid in pids:
        try:
            statm = f"/proc/{pid}/statm"
            if os.path.isfile(statm):
                with open(statm, "r", encoding="utf-8") as f:
                    parts = f.read().split()
                    if len(parts) >= 2:
                        total_pages += int(parts[1])
        except Exception:
            pass
    return (total_pages * page_size) / (1024 * 1024)


def is_app_running(folder_name: str) -> bool:
    return len(get_running_app_pids(folder_name)) > 0


def kill_app_processes(folder_name: str) -> Tuple[bool, str, int]:
    import signal
    import time
    valid = validate_container_name(folder_name)
    if not valid:
        return False, f"Invalid container name: '{folder_name}'.", 0
    folder_name = valid
    pids = get_running_app_pids(folder_name, fast_check=False)
    app_dir = os.path.join(ENCLOSED_DIR, folder_name)
    pid_file = os.path.join(app_dir, "userdata", "running.pid")
    if not pids:
        if os.path.isfile(pid_file):
            try:
                os.remove(pid_file)
            except Exception:
                pass
        return True, f"No running processes found for '{folder_name}'.", 0
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    time.sleep(0.15)
    remaining = get_running_app_pids(folder_name, fast_check=False)
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
    if remaining:
        time.sleep(0.08)
    if os.path.isfile(pid_file):
        try:
            os.remove(pid_file)
        except Exception:
            pass
    return True, f"Successfully terminated {len(pids)} process(es) for '{folder_name}'.", len(pids)


def inspect_container_contents(folder_name: str) -> Dict[str, Any]:
    valid = validate_container_name(folder_name)
    if not valid:
        return {}
    folder_name = valid
    app_dir = os.path.join(ENCLOSED_DIR, folder_name)
    app_files = os.path.join(app_dir, "app_files")
    binaries = []
    libraries = []
    if os.path.isdir(app_files):
        for root, _, files in os.walk(app_files):
            for f in files:
                p = os.path.join(root, f)
                if os.access(p, os.X_OK) and not f.endswith((".so", ".a", ".png", ".desktop", ".xml")):
                    binaries.append(os.path.relpath(p, app_files))
                elif ".so" in f:
                    libraries.append(f)
    pids = get_running_app_pids(folder_name, fast_check=False)
    strict = is_strict_sandbox(app_dir)
    level = get_enclosing_level(app_dir)
    details = get_enclosing_level_details(level)
    return {
        "folder": folder_name,
        "app_dir": app_dir,
        "binaries": sorted(binaries)[:15],
        "total_binaries": len(binaries),
        "total_libraries": len(libraries),
        "strict_sandbox": strict,
        "sandbox_level": "strict" if strict else "standard",
        "enclosing_level": level,
        "enclosing_details": details,
        "running": len(pids) > 0,
        "pids": pids,
        "running_pids": pids,
    }


def create_empty_container(folder_name: str, strict: Optional[bool] = None) -> Tuple[bool, str]:
    if strict is None:
        from app_encloser.core.config import get_setting
        strict = get_setting("strict_sandbox_by_default", True) and is_bwrap_supported()
    folder_clean = clean_folder_name(folder_name)
    app_dir = os.path.join(ENCLOSED_DIR, folder_clean)
    if os.path.isdir(app_dir):
        return False, f"Container '{folder_clean}' already exists."

    app_files = os.path.join(app_dir, "app_files")
    userdata = os.path.join(app_dir, "userdata")
    bin_dir = os.path.join(app_files, "usr", "bin")
    os.makedirs(bin_dir, exist_ok=True)
    os.makedirs(os.path.join(userdata, "home"), exist_ok=True)
    os.makedirs(os.path.join(userdata, "config"), exist_ok=True)
    os.makedirs(os.path.join(userdata, "cache"), exist_ok=True)
    os.makedirs(os.path.join(userdata, "local_share"), exist_ok=True)
    os.makedirs(os.path.join(userdata, "tmp"), exist_ok=True)

    dummy_exec = os.path.join(bin_dir, folder_clean.lower())
    with open(dummy_exec, "w", encoding="utf-8") as f:
        f.write("#!/usr/bin/env bash\necho 'Clean container active: " + folder_clean + "'\n")
    os.chmod(dummy_exec, 0o755)

    with open(os.path.join(app_dir, ".pkg_format"), "w", encoding="utf-8") as f:
        f.write("CONTAINER")
    with open(os.path.join(app_dir, ".target_exec"), "w", encoding="utf-8") as f:
        f.write(f"usr/bin/{folder_clean.lower()}")

    if strict:
        set_strict_sandbox(folder_clean, True)
        with open(os.path.join(app_dir, ".enclosing_level"), "w", encoding="utf-8") as f:
            f.write("strict")
    else:
        set_strict_sandbox(folder_clean, False)
        with open(os.path.join(app_dir, ".enclosing_level"), "w", encoding="utf-8") as f:
            f.write("standard")

    from app_encloser.core.icons import extract_or_generate_icon
    from app_encloser.core.desktop import update_desktop_files_for_app

    write_launch_script(app_dir, f"usr/bin/{folder_clean.lower()}", "CONTAINER")
    from app_encloser.core.lifecycle import install_container_helpers
    install_container_helpers(app_dir)
    icon_path = extract_or_generate_icon(app_dir, folder_clean)
    update_desktop_files_for_app(app_dir, folder_clean, folder_clean, folder_clean.lower(), icon_path)

    return True, f"Container '{folder_clean}' created successfully."
