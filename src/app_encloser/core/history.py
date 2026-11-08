import os
import sys
import json
import time
import gzip
import shutil
import subprocess
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Set

from app_encloser.core.config import CONFIG_DIR, ENCLOSED_DIR, REAL_HOME, LOCAL_BIN

HISTORY_FILE = os.path.join(CONFIG_DIR, "install_history.json")

INITIAL_OS_PACKAGES = set()
_init_status_gz = "/var/log/installer/initial-status.gz"
if os.path.isfile(_init_status_gz):
    try:
        with gzip.open(_init_status_gz, "rt", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("Package:"):
                    INITIAL_OS_PACKAGES.add(line.split(":", 1)[1].strip().lower())
    except Exception:
        pass

SYSTEM_PACKAGE_PREFIXES = (
    "linux-", "grub-", "shim", "efi", "ubuntu-", "gnome-", "lib", "python3",
    "gir1.2-", "systemd", "udev", "dbus", "network-manager", "xserver-",
    "wayland", "mesa-", "x11-", "fonts-", "language-pack-", "wbritish",
    "wamerican", "adwaita-", "gtk", "xdg-", "gvfs", "plymouth", "initramfs",
    "base-", "apt", "dpkg"
)

PROTECTED_CORE_PACKAGES = {
    "bubblewrap", "binutils", "tar", "gzip", "xz-utils", "curl", "wget",
    "git", "gcc", "make", "libc6", "sudo", "pkexec", "policykit-1",
    "polkitd", "ufw", "timeshift", "flatpak", "podman", "distrobox",
    "openssh-client", "ca-certificates", "gnupg", "software-properties-common",
    "app-encloser", "project-extractor", "lsb-release"
}

BASELINE_FILE = os.path.join(CONFIG_DIR, "os_baseline.json")


def load_os_baseline() -> set:
    if not os.path.isfile(BASELINE_FILE):
        return set()
    try:
        with open(BASELINE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("packages", []))
    except Exception:
        return set()


def lock_current_os_baseline() -> Tuple[bool, str]:
    try:
        res = subprocess.run(["dpkg-query", "-W", "-f=${binary:Package}\n"], capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            return False, "Failed to query installed system packages via dpkg-query."
        pkgs = sorted(list(set(l.strip().lower() for l in res.stdout.splitlines() if l.strip())))
        os.makedirs(CONFIG_DIR, exist_ok=True)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(BASELINE_FILE, "w", encoding="utf-8") as f:
            json.dump({"timestamp": now_str, "packages": pkgs}, f, indent=2)
        return True, f"Locked OS baseline snapshot ({len(pkgs)} packages at {now_str})."
    except Exception as e:
        return False, str(e)


def reset_os_baseline() -> Tuple[bool, str]:
    if os.path.isfile(BASELINE_FILE):
        try:
            os.remove(BASELINE_FILE)
            return True, "OS baseline snapshot has been reset."
        except Exception as e:
            return False, str(e)
    return True, "No active OS baseline snapshot to reset."


_RDEPS_CACHE: Dict[str, Dict[str, Any]] = {}


def analyze_host_packages_safety_batch(pkg_names: List[str]) -> Dict[str, Dict[str, Any]]:
    global _RDEPS_CACHE
    res_map: Dict[str, Dict[str, Any]] = {}
    to_query: List[str] = []
    for p in pkg_names:
        clean = p.split(":")[0].strip().lower()
        if not clean:
            continue
        if clean in _RDEPS_CACHE:
            res_map[clean] = _RDEPS_CACHE[clean]
        else:
            to_query.append(clean)

    if not to_query:
        return res_map

    rdeps_by_pkg: Dict[str, List[str]] = {p: [] for p in to_query}
    try:
        cmd = ["apt-cache", "rdepends", "--installed"] + to_query
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if proc.returncode == 0:
            current_pkg = None
            for line in proc.stdout.splitlines():
                line_s = line.strip()
                if not line.startswith(" ") and not line.startswith("\t") and not line.startswith("|"):
                    if line_s and not line_s.startswith("Reverse Depends:"):
                        current_pkg = line_s.split(":")[0].strip().lower()
                        if current_pkg not in rdeps_by_pkg:
                            rdeps_by_pkg[current_pkg] = []
                elif current_pkg and "Reverse Depends:" not in line:
                    item = line_s.lstrip("|").strip().split(":")[0].strip().lower()
                    if item and item != current_pkg and not item.startswith(current_pkg + "-") and not current_pkg.startswith(item + "-"):
                        if item not in rdeps_by_pkg[current_pkg]:
                            rdeps_by_pkg[current_pkg].append(item)
    except Exception:
        pass

    for p in to_query:
        rd = rdeps_by_pkg.get(p, [])
        safe = (len(rd) == 0)
        badge = "Safe to Remove" if safe else f"Used by {len(rd)} pkg(s)"
        info = {
            "safe_to_remove": safe,
            "rdeps": rd,
            "safety_badge": badge
        }
        _RDEPS_CACHE[p] = info
        res_map[p] = info

    return res_map


def analyze_host_package_safety(pkg_name: str) -> Dict[str, Any]:
    global _RDEPS_CACHE
    clean_pkg = pkg_name.split(":")[0].strip().lower()
    if not clean_pkg:
        return {"safe_to_remove": True, "rdeps": [], "safety_badge": "Safe to Remove"}
    if clean_pkg in _RDEPS_CACHE:
        return _RDEPS_CACHE[clean_pkg]
    batch_res = analyze_host_packages_safety_batch([clean_pkg])
    return batch_res.get(clean_pkg, {"safe_to_remove": True, "rdeps": [], "safety_badge": "Safe to Remove"})


def is_protected_system_package(pkg: str) -> bool:
    if not pkg:
        return False
    low = pkg.split(":")[0].strip().lower()
    if not low:
        return False
    if low in {"install", "bash", "sh", "sudo", "pkexec", "env", "systemd", "dpkg", "apt", "coreutils"}:
        return True
    if low in INITIAL_OS_PACKAGES or low in PROTECTED_CORE_PACKAGES:
        return True
    if any(low.startswith(p) for p in SYSTEM_PACKAGE_PREFIXES):
        return True
    return False


def load_install_history() -> List[Dict[str, Any]]:
    if not os.path.isfile(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    try:
        if os.path.isfile(HISTORY_FILE):
            import time
            bak = f"{HISTORY_FILE}.corrupt.{int(time.time())}"
            os.rename(HISTORY_FILE, bak)
            save_install_history([])
    except Exception:
        pass
    return []


def save_install_history(records: List[Dict[str, Any]]) -> bool:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
        return True
    except Exception:
        return False


def record_install_event(
    app_name: str,
    folder_name: str,
    command: str,
    install_type: str = "command"
) -> Dict[str, Any]:
    records = load_install_history()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    app_dir = os.path.join(ENCLOSED_DIR, folder_name)
    if os.path.isdir(app_dir) and command:
        cmd_file = os.path.join(app_dir, ".install_cmd")
        try:
            with open(cmd_file, "w", encoding="utf-8") as f:
                f.write(command.strip())
        except Exception:
            pass

    for rec in records:
        if rec.get("folder_name") == folder_name:
            rec["app_name"] = app_name
            rec["command"] = command.strip()
            rec["install_type"] = install_type
            rec["updated_at"] = now_str
            rec["status"] = "installed"
            save_install_history(records)
            return rec

    new_rec = {
        "id": f"inst_{int(time.time())}_{folder_name.lower()}",
        "app_name": app_name,
        "folder_name": folder_name,
        "command": command.strip(),
        "install_type": install_type,
        "installed_at": now_str,
        "updated_at": now_str,
        "status": "installed"
    }
    records.insert(0, new_rec)
    save_install_history(records)
    return new_rec


def mark_as_uninstalled(folder_or_name: str) -> bool:
    records = load_install_history()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated = False
    for rec in records:
        if (
            rec.get("folder_name") == folder_or_name
            or rec.get("app_name") == folder_or_name
            or rec.get("folder_name", "").lower() == folder_or_name.lower()
            or rec.get("app_name", "").lower() == folder_or_name.lower()
        ):
            rec["status"] = "uninstalled"
            rec["uninstalled_at"] = now_str
            updated = True
    if updated:
        save_install_history(records)
    return updated


def delete_history_record(identifier: str) -> bool:
    records = load_install_history()
    low = identifier.strip().lower()
    new_records = [
        rec for rec in records
        if rec.get("id", "").lower() != low
        and rec.get("folder_name", "").lower() != low
        and rec.get("app_name", "").lower() != low
    ]
    if len(new_records) != len(records):
        save_install_history(new_records)
        return True
    return False


def clear_uninstalled_history_records() -> int:
    records = load_install_history()
    new_records = [rec for rec in records if rec.get("status") != "uninstalled"]
    pruned = len(records) - len(new_records)
    if pruned > 0:
        save_install_history(new_records)
    return pruned


_HOST_DISCOVERY_CACHE = {"timestamp": 0.0, "items": []}


def invalidate_host_discovery_cache():
    _HOST_DISCOVERY_CACHE["timestamp"] = 0.0
    _HOST_DISCOVERY_CACHE["items"] = []


def clean_corrupt_history_records() -> int:
    records = load_install_history()
    cleaned = []
    removed_count = 0
    forbidden_system_names = {"install", "bash", "sh", "sudo", "pkexec", "env", "systemd", "dpkg", "apt"}
    for rec in records:
        folder = rec.get("folder_name", "")
        app_name = rec.get("app_name", "")
        app_dir = os.path.join(ENCLOSED_DIR, folder) if folder else ""
        container_exists = bool(app_dir and os.path.isdir(app_dir))

        if (app_name.lower() in forbidden_system_names or folder.lower() in forbidden_system_names) and not container_exists:
            removed_count += 1
            continue

        if rec.get("status") == "installed" and rec.get("install_type") in ("container", "package_file") and not container_exists:
            rec["status"] = "uninstalled"
            rec["uninstalled_at"] = "orphaned"
            removed_count += 1

        cleaned.append(rec)
    if removed_count > 0:
        save_install_history(cleaned)
    return removed_count


def check_host_package_status(pkg_or_bin: str) -> Optional[Dict[str, Any]]:
    low = pkg_or_bin.lower().strip()
    if not low:
        return None

    clean_target = os.path.basename(low)
    if clean_target.endswith(".deb"):
        clean_target = clean_target[:-4]
    clean_target = clean_target.split("_")[0]

    forbidden_system_names = {"install", "bash", "sh", "sudo", "pkexec", "env", "systemd", "dpkg", "apt"}
    if clean_target in forbidden_system_names:
        return None

    dpkg_targets = [clean_target]
    if "-" in clean_target:
        dpkg_targets.append(clean_target.replace("-", "_"))
    if "_" in clean_target:
        dpkg_targets.append(clean_target.replace("_", "-"))

    for target in dpkg_targets:
        try:
            res = subprocess.run(["dpkg-query", "-W", "-f=${Status}\t${Version}\n", target], capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and "install ok installed" in res.stdout:
                parts = res.stdout.strip().split("\t")
                ver = parts[1].strip() if len(parts) > 1 else ""
                return {
                    "installed": True,
                    "target": target,
                    "version": ver,
                    "type": "apt_package"
                }
        except Exception:
            pass

    for b in dpkg_targets:
        if b == "ollama":
            ollama_p = "/usr/local/bin/ollama"
            if os.path.isfile(ollama_p) and os.access(ollama_p, os.X_OK):
                return {
                    "installed": True,
                    "target": b,
                    "path": ollama_p,
                    "type": "ollama_host"
                }

        user_paths = [
            (os.path.join(REAL_HOME, ".npm-global", "bin", b), "claude_cli" if b == "claude" else "npm_global"),
            (os.path.join(REAL_HOME, ".cargo", "bin", b), "cargo_bin"),
            (os.path.join(LOCAL_BIN, b), "local_bin"),
        ]
        for upath, utype in user_paths:
            if os.path.isfile(upath) and os.access(upath, os.X_OK):
                return {
                    "installed": True,
                    "target": b,
                    "path": upath,
                    "type": utype
                }

    return None


def discover_host_terminal_installations() -> List[Dict[str, Any]]:
    now = time.time()
    if now - _HOST_DISCOVERY_CACHE["timestamp"] < 60.0 and _HOST_DISCOVERY_CACHE["items"]:
        return list(_HOST_DISCOVERY_CACHE["items"])

    items: List[Dict[str, Any]] = []
    seen: set = set()
    baseline_pkgs = load_os_baseline()

    apt_log = "/var/log/apt/history.log"
    cand_pkgs = []
    if os.path.isfile(apt_log):
        try:
            with open(apt_log, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if not line.startswith("Commandline:"):
                        continue
                    cmd = line.split(":", 1)[1].strip()
                    if "install" not in cmd:
                        continue
                    if "download" in cmd or "--reinstall" in cmd or "AutoInstall=yes" in cmd or "--fix-policy" in cmd or "role='install-files'" in cmd:
                        continue
                    if any(x in cmd for x in ("--force-confold", "Dpkg::Options", "subiquity", "curtin")):
                        continue
                    tokens = cmd.split()
                    try:
                        idx = tokens.index("install")
                    except ValueError:
                        continue
                    for token in tokens[idx + 1:]:
                        if token.startswith("-") or token.startswith("/"):
                            continue
                        if "=" in token:
                            token = token.split("=")[0]
                        pkg = token.split(":")[0].strip().lower()
                        if not pkg or pkg in seen or is_protected_system_package(pkg) or pkg in baseline_pkgs:
                            continue
                        seen.add(pkg)
                        cand_pkgs.append(pkg)
        except Exception:
            pass

    if cand_pkgs:
        analyze_host_packages_safety_batch(cand_pkgs)
        try:
            res = subprocess.run(
                ["dpkg-query", "-W", "-f=${Package}\t${Status}\t${Version}\t${Installed-Size}\n"] + cand_pkgs,
                capture_output=True, text=True, timeout=5
            )
            for line in res.stdout.splitlines():
                parts = line.strip().split("\t")
                if len(parts) >= 2 and "install ok installed" in parts[1]:
                    pkg = parts[0].strip().lower()
                    ver = parts[2].strip() if len(parts) >= 3 else ""
                    size_kb_str = parts[3].strip() if len(parts) >= 4 else "0"
                    size_kb = int(size_kb_str) if size_kb_str.isdigit() else 0
                    size_bytes = size_kb * 1024
                    if size_kb >= 1048576:
                        size_fmt = f"{size_kb / 1048576:.1f} GB"
                    elif size_kb >= 1024:
                        size_fmt = f"{size_kb / 1024:.1f} MB"
                    else:
                        size_fmt = f"{size_kb} KB"
                    safety = analyze_host_package_safety(pkg)
                    info_list = f"/var/lib/dpkg/info/{pkg}.list"
                    if not os.path.isfile(info_list):
                        info_list = f"/var/lib/dpkg/info/{pkg}:amd64.list"
                    installed_ts = os.path.getmtime(info_list) if os.path.isfile(info_list) else 0.0
                    installed_date = datetime.fromtimestamp(installed_ts).strftime("%Y-%m-%d %H:%M") if installed_ts > 0 else "Host System"
                    items.append({
                        "app_name": pkg,
                        "folder_name": "",
                        "command": f"apt install {pkg}",
                        "install_type": "apt_package",
                        "timestamp": installed_date,
                        "installed_ts": installed_ts,
                        "installed_date": installed_date,
                        "total_size": size_fmt,
                        "size_bytes": size_bytes,
                        "ram_mb": 0.0,
                        "container_present": False,
                        "host_present": True,
                        "host_info": {
                            "installed": True,
                            "target": pkg,
                            "version": ver,
                            "type": "apt_package",
                            "safety_badge": safety["safety_badge"],
                            "safe_to_remove": safety["safe_to_remove"],
                            "rdeps": safety["rdeps"],
                            "installed_size": size_fmt,
                            "size_bytes": size_bytes
                        },
                        "badge": "Host System (APT)",
                        "badge_css": "accent",
                        "status_text": f"Installed on Host System (APT, v{ver})" if ver else "Installed on Host System (APT)",
                        "path": None
                    })
        except Exception:
            pass

    ollama_cands = ["/usr/local/bin/ollama", os.path.join(REAL_HOME, ".local", "bin", "ollama")]
    ollama_bin = next((b for b in ollama_cands if os.path.isfile(b) and os.access(b, os.X_OK)), None)
    if not ollama_bin:
        cand_w = shutil.which("ollama")
        if cand_w and not cand_w.startswith(ENCLOSED_DIR):
            ollama_bin = cand_w
    if ollama_bin:
        ollama_home = os.path.join(REAL_HOME, ".ollama")
        ollama_share = "/usr/share/ollama"
        ollama_bytes = os.path.getsize(ollama_bin) if os.path.isfile(ollama_bin) else 0
        for d in (ollama_home, ollama_share):
            if os.path.isdir(d):
                for root, _, files in os.walk(d):
                    for f in files:
                        try:
                            ollama_bytes += os.path.getsize(os.path.join(root, f))
                        except Exception:
                            pass
        if ollama_bytes >= 1073741824:
            ollama_size_fmt = f"{ollama_bytes / 1073741824:.1f} GB"
        elif ollama_bytes >= 1048576:
            ollama_size_fmt = f"{ollama_bytes / 1048576:.1f} MB"
        else:
            ollama_size_fmt = f"{ollama_bytes / 1024:.1f} KB"
        items.append({
            "app_name": "ollama",
            "folder_name": "",
            "command": "ollama",
            "install_type": "ollama_host",
            "timestamp": "Host System",
            "installed_ts": os.path.getmtime(ollama_bin) if os.path.isfile(ollama_bin) else 0.0,
            "installed_date": "Host System",
            "total_size": ollama_size_fmt,
            "size_bytes": ollama_bytes,
            "ram_mb": 0.0,
            "container_present": False,
            "host_present": True,
            "host_info": {
                "installed": True,
                "target": "ollama",
                "version": "active",
                "type": "ollama_host",
                "path": ollama_bin,
                "safety_badge": "Safe to Remove",
                "safe_to_remove": True,
                "rdeps": [],
                "installed_size": ollama_size_fmt,
                "size_bytes": ollama_bytes
            },
            "badge": "Host System (Ollama)",
            "badge_css": "accent",
            "status_text": "Ollama LLM Runner & Service (Host System)",
            "path": ollama_bin
        })

    claude_cands = [
        os.path.join(REAL_HOME, ".npm-global", "bin", "claude"),
        os.path.join(REAL_HOME, ".local", "bin", "claude"),
        "/usr/local/bin/claude"
    ]
    claude_bin = next((b for b in claude_cands if os.path.isfile(b) and os.access(b, os.X_OK)), None)
    if not claude_bin:
        cand_w = shutil.which("claude")
        if cand_w and not cand_w.startswith(ENCLOSED_DIR):
            claude_bin = cand_w
    if claude_bin:
        claude_bytes = os.path.getsize(claude_bin) if os.path.isfile(claude_bin) else 0
        claude_home = os.path.join(REAL_HOME, ".claude")
        if os.path.isdir(claude_home):
            for root, _, files in os.walk(claude_home):
                for f in files:
                    try:
                        claude_bytes += os.path.getsize(os.path.join(root, f))
                    except Exception:
                        pass
        claude_size_fmt = f"{claude_bytes / 1048576:.1f} MB" if claude_bytes >= 1048576 else f"{claude_bytes / 1024:.1f} KB"
        items.append({
            "app_name": "claude",
            "folder_name": "",
            "command": "npm install -g @anthropic-ai/claude-code",
            "install_type": "claude_cli",
            "timestamp": "Host System",
            "installed_ts": os.path.getmtime(claude_bin) if os.path.isfile(claude_bin) else 0.0,
            "installed_date": "Host System",
            "total_size": claude_size_fmt,
            "size_bytes": claude_bytes,
            "ram_mb": 0.0,
            "container_present": False,
            "host_present": True,
            "host_info": {
                "installed": True,
                "target": "claude",
                "version": "active",
                "type": "claude_cli",
                "path": claude_bin,
                "safety_badge": "Safe to Remove",
                "safe_to_remove": True,
                "rdeps": [],
                "installed_size": claude_size_fmt,
                "size_bytes": claude_bytes
            },
            "badge": "Host System (CLI)",
            "badge_css": "accent",
            "status_text": f"Claude Code AI CLI ({claude_bin})",
            "path": claude_bin
        })

    npm_global_bin = os.path.join(REAL_HOME, ".npm-global", "bin")
    if os.path.isdir(npm_global_bin):
        for fname in sorted(os.listdir(npm_global_bin)):
            fpath = os.path.join(npm_global_bin, fname)
            if fname.startswith(".") or fname == "claude":
                continue
            if os.path.isfile(fpath) and os.access(fpath, os.X_OK):
                installed_ts = os.path.getmtime(fpath)
                installed_date = datetime.fromtimestamp(installed_ts).strftime("%Y-%m-%d %H:%M")
                size_bytes = os.path.getsize(fpath)
                size_fmt = f"{size_bytes / 1048576:.1f} MB" if size_bytes >= 1048576 else f"{size_bytes / 1024:.1f} KB"
                items.append({
                    "app_name": fname,
                    "folder_name": "",
                    "command": f"npm install -g {fname}",
                    "install_type": "npm_global",
                    "timestamp": installed_date,
                    "installed_ts": installed_ts,
                    "installed_date": installed_date,
                    "total_size": size_fmt,
                    "size_bytes": size_bytes,
                    "ram_mb": 0.0,
                    "container_present": False,
                    "host_present": True,
                    "host_info": {
                        "installed": True,
                        "target": fname,
                        "path": fpath,
                        "type": "npm_global",
                        "safety_badge": "Safe to Remove",
                        "safe_to_remove": True,
                        "rdeps": [],
                        "installed_size": size_fmt,
                        "size_bytes": size_bytes
                    },
                    "badge": "Host System (NPM)",
                    "badge_css": "accent",
                    "status_text": f"Global NPM Package ({fpath})",
                    "path": fpath
                })

    brew_cands = ["/home/linuxbrew/.linuxbrew/bin/brew", os.path.join(REAL_HOME, ".linuxbrew", "bin", "brew")]
    brew_bin = next((b for b in brew_cands if os.path.isfile(b)), shutil.which("brew"))
    if brew_bin:
        items.append({
            "app_name": "Homebrew",
            "folder_name": "",
            "command": "brew",
            "install_type": "homebrew",
            "timestamp": "Host System",
            "container_present": False,
            "host_present": True,
            "host_info": {
                "installed": True,
                "target": "homebrew",
                "version": "active",
                "type": "homebrew",
                "path": brew_bin
            },
            "badge": "Host System (Brew)",
            "badge_css": "accent",
            "status_text": "Homebrew Package Manager (Host System)",
            "path": None
        })
        cellar_dirs = ["/home/linuxbrew/.linuxbrew/Cellar", os.path.join(REAL_HOME, ".linuxbrew", "Cellar")]
        found_cellar = next((c for c in cellar_dirs if os.path.isdir(c)), None)
        if found_cellar:
            for formula in sorted(os.listdir(found_cellar)):
                fpath = os.path.join(found_cellar, formula)
                if os.path.isdir(fpath) and not formula.startswith("."):
                    ver_entries = sorted(os.listdir(fpath))
                    ver = ver_entries[-1] if ver_entries else ""
                    items.append({
                        "app_name": formula,
                        "folder_name": "",
                        "command": f"brew install {formula}",
                        "install_type": "homebrew",
                        "timestamp": "Host System",
                        "container_present": False,
                        "host_present": True,
                        "host_info": {
                            "installed": True,
                            "target": formula,
                            "version": ver,
                            "type": "homebrew"
                        },
                        "badge": "Host System (Brew)",
                        "badge_css": "accent",
                        "status_text": f"Installed via Homebrew ({ver})" if ver else "Installed via Homebrew",
                        "path": None
                    })
        elif shutil.which("brew"):
            try:
                res = subprocess.run([brew_bin, "leaves"], capture_output=True, text=True, timeout=3)
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        frm = line.strip()
                        if frm:
                            items.append({
                                "app_name": frm,
                                "folder_name": "",
                                "command": f"brew install {frm}",
                                "install_type": "homebrew",
                                "timestamp": "Host System",
                                "container_present": False,
                                "host_present": True,
                                "host_info": {
                                    "installed": True,
                                    "target": frm,
                                    "version": "",
                                    "type": "homebrew"
                                },
                                "badge": "Host System (Brew)",
                                "badge_css": "accent",
                                "status_text": "Installed via Homebrew",
                                "path": None
                            })
            except Exception:
                pass

    ignored_local_bins = {"app-encloser", "project-extractor", "pextract", "dir-extract"}

    uv_tools = set()
    if shutil.which("uv"):
        try:
            res = subprocess.run(["uv", "tool", "list"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    tname = line.strip().split()[0] if line.strip() else ""
                    if tname:
                        uv_tools.add(tname.lower())
        except Exception:
            pass

    if os.path.isdir(LOCAL_BIN):
        for fname in sorted(os.listdir(LOCAL_BIN)):
            fpath = os.path.join(LOCAL_BIN, fname)
            if fname in ignored_local_bins or fname.startswith("."):
                continue
            if os.path.isfile(fpath) and os.access(fpath, os.X_OK):
                is_uv = fname.lower() in uv_tools
                b_type = "uv_tool" if is_uv else "local_bin"
                installed_ts = os.path.getmtime(fpath)
                installed_date = datetime.fromtimestamp(installed_ts).strftime("%Y-%m-%d %H:%M")
                size_bytes = os.path.getsize(fpath)
                size_fmt = f"{size_bytes / 1048576:.1f} MB" if size_bytes >= 1048576 else (f"{size_bytes / 1024:.1f} KB" if size_bytes >= 1024 else f"{size_bytes} B")
                items.append({
                    "app_name": fname,
                    "folder_name": "",
                    "command": f"uv tool install {fname}" if is_uv else fname,
                    "install_type": b_type,
                    "timestamp": installed_date,
                    "installed_ts": installed_ts,
                    "installed_date": installed_date,
                    "total_size": size_fmt,
                    "size_bytes": size_bytes,
                    "ram_mb": 0.0,
                    "container_present": False,
                    "host_present": True,
                    "host_info": {
                        "installed": True,
                        "target": fname,
                        "path": fpath,
                        "type": b_type,
                        "safety_badge": "Safe to Remove",
                        "safe_to_remove": True,
                        "rdeps": [],
                        "installed_size": size_fmt,
                        "size_bytes": size_bytes
                    },
                    "badge": "Host System (User CLI)",
                    "badge_css": "accent",
                    "status_text": f"User CLI Tool (~/.local/bin/{fname})",
                    "path": fpath
                })

    cargo_bin_dir = os.path.join(REAL_HOME, ".cargo", "bin")
    if os.path.isdir(cargo_bin_dir):
        for fname in sorted(os.listdir(cargo_bin_dir)):
            fpath = os.path.join(cargo_bin_dir, fname)
            if fname.startswith("."):
                continue
            if os.path.isfile(fpath) and os.access(fpath, os.X_OK):
                installed_ts = os.path.getmtime(fpath)
                installed_date = datetime.fromtimestamp(installed_ts).strftime("%Y-%m-%d %H:%M")
                size_bytes = os.path.getsize(fpath)
                size_fmt = f"{size_bytes / 1048576:.1f} MB" if size_bytes >= 1048576 else (f"{size_bytes / 1024:.1f} KB" if size_bytes >= 1024 else f"{size_bytes} B")
                items.append({
                    "app_name": fname,
                    "folder_name": "",
                    "command": f"cargo install {fname}",
                    "install_type": "cargo_bin",
                    "timestamp": installed_date,
                    "installed_ts": installed_ts,
                    "installed_date": installed_date,
                    "total_size": size_fmt,
                    "size_bytes": size_bytes,
                    "ram_mb": 0.0,
                    "container_present": False,
                    "host_present": True,
                    "host_info": {
                        "installed": True,
                        "target": fname,
                        "path": fpath,
                        "type": "cargo_bin",
                        "safety_badge": "Safe to Remove",
                        "safe_to_remove": True,
                        "rdeps": [],
                        "installed_size": size_fmt,
                        "size_bytes": size_bytes
                    },
                    "badge": "Host System (User CLI)",
                    "badge_css": "accent",
                    "status_text": f"User CLI Tool (~/.cargo/bin/{fname})",
                    "path": fpath
                })

    _HOST_DISCOVERY_CACHE["timestamp"] = now
    _HOST_DISCOVERY_CACHE["items"] = list(items)
    return items


def audit_all_installations() -> List[Dict[str, Any]]:
    clean_corrupt_history_records()
    records = load_install_history()
    seen_folders = set()
    audit_list: List[Dict[str, Any]] = []

    for rec in records:
        folder = rec.get("folder_name", "")
        app_dir = os.path.join(ENCLOSED_DIR, folder) if folder else ""
        container_exists = bool(app_dir and os.path.isdir(app_dir))

        low_name = rec.get("app_name", "").strip().lower()
        if low_name in {"install", "bash", "sh", "sudo", "pkexec", "env", "systemd", "dpkg", "apt"}:
            continue
        if rec.get("status") != "uninstalled" and rec.get("install_type") in ("command_script", "container", "package_file") and not container_exists:
            continue

        seen_folders.add(folder)
        host_info = check_host_package_status(rec.get("app_name", folder))

        if container_exists and host_info:
            badge = "Enclosed + Host"
            badge_css = "warning"
            status_text = f"Installed in container and also active on Host ({host_info.get('type')})"
        elif container_exists:
            badge = "Enclosed"
            badge_css = "success"
            status_text = "Isolated inside container (~/EnclosedApps)"
        elif host_info:
            badge = "Host Only"
            badge_css = "accent"
            status_text = f"Installed on Host System ({host_info.get('type')})"
        else:
            badge = "Removed"
            badge_css = "dim"
            status_text = f"Uninstalled ({rec.get('uninstalled_at', 'previously')})"

        cmd_val = rec.get("command", "")
        if not cmd_val and container_exists:
            cmd_file = os.path.join(app_dir, ".install_cmd")
            if os.path.isfile(cmd_file):
                try:
                    with open(cmd_file, "r", encoding="utf-8") as cf:
                        cmd_val = cf.read().strip()
                        rec["command"] = cmd_val
                except Exception:
                    pass

        audit_list.append({
            "app_name": rec.get("app_name", folder),
            "folder_name": folder,
            "command": cmd_val or "Direct Package Ingestion",
            "install_type": rec.get("install_type", "command"),
            "timestamp": rec.get("installed_at") or rec.get("updated_at") or "Unknown",
            "container_present": container_exists,
            "host_present": bool(host_info),
            "host_info": host_info,
            "badge": badge,
            "badge_css": badge_css,
            "status_text": status_text,
            "path": app_dir if container_exists else None
        })

    if os.path.isdir(ENCLOSED_DIR):
        for entry in sorted(os.listdir(ENCLOSED_DIR)):
            if entry.startswith(".") or entry in seen_folders:
                continue
            app_dir = os.path.join(ENCLOSED_DIR, entry)
            if not os.path.isdir(app_dir):
                continue
            seen_folders.add(entry)
            cmd_file = os.path.join(app_dir, ".install_cmd")
            cmd_val = ""
            if os.path.isfile(cmd_file):
                try:
                    with open(cmd_file, "r", encoding="utf-8") as cf:
                        cmd_val = cf.read().strip()
                except Exception:
                    pass

            host_info = check_host_package_status(entry)
            badge = "Enclosed + Host" if host_info else "Enclosed"
            badge_css = "warning" if host_info else "success"
            status_text = "Installed in container and on Host" if host_info else "Isolated inside container"

            record_install_event(entry, entry, cmd_val, "container")
            audit_list.append({
                "app_name": entry,
                "folder_name": entry,
                "command": cmd_val or "Container Ingestion",
                "install_type": "container",
                "timestamp": datetime.fromtimestamp(os.path.getctime(app_dir)).strftime("%Y-%m-%d %H:%M:%S"),
                "container_present": True,
                "host_present": bool(host_info),
                "host_info": host_info,
                "badge": badge,
                "badge_css": badge_css,
                "status_text": status_text,
                "path": app_dir
            })

    discovered = discover_host_terminal_installations()
    for disc in discovered:
        target_name = disc["host_info"].get("target", disc["app_name"]).lower()
        if is_protected_system_package(target_name) or is_protected_system_package(disc["app_name"]):
            continue
        matched = False
        for it in audit_list:
            it_name = it.get("app_name", "").lower()
            it_target = it.get("host_info", {}).get("target", "").lower() if it.get("host_info") else ""
            if it_name == target_name or (it_target and it_target == target_name):
                matched = True
                it["host_present"] = True
                if not it.get("host_info"):
                    it["host_info"] = disc["host_info"]
                if it["container_present"]:
                    it["badge"] = "Enclosed + Host"
                    it["badge_css"] = "warning"
                    it["status_text"] = "Installed in container and on Host"
                break
        if not matched:
            audit_list.append(disc)

    filtered_list = []
    for it in audit_list:
        if it.get("container_present"):
            filtered_list.append(it)
        else:
            app_n = it.get("app_name", "")
            target_n = it.get("host_info", {}).get("target", "") if it.get("host_info") else ""
            if not is_protected_system_package(app_n) and not is_protected_system_package(target_n):
                filtered_list.append(it)

    return filtered_list


def format_audit_report() -> str:
    items = audit_all_installations()
    if not items:
        return "No installation history recorded."

    lines = [
        "=== App Encloser — Installation & Environment Audit ===",
        f"Total Tracked Items: {len(items)}",
        ""
    ]
    for it in items:
        status_line = f"[{it['badge']}] {it['app_name']}"
        lines.append(status_line)
        lines.append(f"  Status:    {it['status_text']}")
        lines.append(f"  Command:   {it['command']}")
        lines.append(f"  Timestamp: {it['timestamp']}")
        if it.get("path"):
            lines.append(f"  Directory: {it['path']}")
        if it.get("host_info"):
            h = it["host_info"]
            lines.append(f"  Host Info: {h.get('target')} (Version: {h.get('version', 'unknown')})")
        lines.append("")

    return "\n".join(lines).strip()
