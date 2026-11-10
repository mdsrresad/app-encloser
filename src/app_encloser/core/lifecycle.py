import os
import sys
import re
import shutil
import urllib.request
import subprocess
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional

from app_encloser.core.config import (
    REAL_HOME, LOCAL_BIN, ENCLOSED_DIR, APPS_DIR, ICONS_DIR, CACHE_DIR,
    clean_folder_name, get_dir_size, get_dir_size_bytes, invalidate_dir_size_cache,
    is_supported_file, get_setting
)
from app_encloser.core.desktop import (
    parse_desktop_file, find_best_desktop_file,
    update_desktop_files_for_app
)
from app_encloser.core.icons import extract_or_generate_icon
from app_encloser.core.container import (
    write_launch_script, resolve_executable,
    is_strict_sandbox, set_strict_sandbox, get_running_app_pids, get_pids_ram_mb,
    kill_app_processes, get_enclosing_level, get_enclosing_level_details,
    set_enclosing_level, run_in_container
)
from app_encloser.core.extractor import unpack_archive


def fix_usrmerge_symlinks(dest_dir: str):
    usr_lib = os.path.join(dest_dir, "usr", "lib")
    lib = os.path.join(dest_dir, "lib")
    if os.path.isdir(usr_lib):
        os.makedirs(lib, exist_ok=True)
        for item in os.listdir(usr_lib):
            target = os.path.join(lib, item)
            source = os.path.join(usr_lib, item)
            if not os.path.exists(target):
                try:
                    rel = os.path.relpath(source, lib)
                    os.symlink(rel, target)
                except Exception:
                    pass
    usr_bin = os.path.join(dest_dir, "usr", "bin")
    b_dir = os.path.join(dest_dir, "bin")
    if os.path.isdir(b_dir) and os.path.isdir(usr_bin):
        for item in os.listdir(b_dir):
            target = os.path.join(usr_bin, item)
            source = os.path.join(b_dir, item)
            if not os.path.exists(target):
                try:
                    rel = os.path.relpath(source, usr_bin)
                    os.symlink(rel, target)
                except Exception:
                    pass


def install_container_helpers(app_dir: str):
    bin_dir = os.path.join(app_dir, "userdata", "shims")
    os.makedirs(bin_dir, exist_ok=True)

    old_bin_dir = os.path.join(app_dir, "app_files", "usr", "bin")
    if os.path.isdir(old_bin_dir):
        for s in ("apt", "apt-get", "gpg", "tee", "sudo", "nft", "curl", "wget", "encloser-install", "encloser-python", "encloser-brew"):
            old_s = os.path.join(old_bin_dir, s)
            if os.path.isfile(old_s) or os.path.islink(old_s):
                try:
                    os.remove(old_s)
                except Exception:
                    pass

    gpg_py = os.path.join(bin_dir, "gpg")
    gpg_code = """#!/usr/bin/env python3
import os
import sys
import subprocess

app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
app_files = os.path.join(app_dir, "app_files")
keyrings_dir = os.path.join(app_dir, "userdata", "keyrings")
os.makedirs(keyrings_dir, exist_ok=True)

new_args = []
i = 1
out_file = None
while i < len(sys.argv):
    arg = sys.argv[i]
    if arg in ("--output", "-o") and i + 1 < len(sys.argv):
        target = sys.argv[i + 1]
        fn = os.path.basename(target)
        out_file = os.path.join(keyrings_dir, fn)
        new_args.extend([arg, out_file])
        i += 2
    elif arg.startswith("--output="):
        target = arg.split("=", 1)[1]
        fn = os.path.basename(target)
        out_file = os.path.join(keyrings_dir, fn)
        new_args.append(f"--output={out_file}")
        i += 1
    else:
        new_args.append(arg)
        i += 1

stdin_data = None
if not sys.stdin.isatty():
    stdin_data = sys.stdin.buffer.read()

real_gpg = "/usr/bin/gpg"
if not os.path.isfile(real_gpg):
    real_gpg = "/bin/gpg"

child_env = os.environ.copy()
cur_shims = os.path.dirname(os.path.abspath(__file__))
p_parts = [p for p in child_env.get("PATH", "").split(":") if p and p != cur_shims]
child_env["PATH"] = ":".join(p_parts)

if os.path.isfile(real_gpg):
    p = subprocess.Popen([real_gpg] + new_args, stdin=subprocess.PIPE if stdin_data is not None else None, env=child_env)
    p.communicate(input=stdin_data)
    sys.exit(p.returncode)
sys.exit(1)
"""
    with open(gpg_py, "w", encoding="utf-8") as f:
        f.write(gpg_code)
    os.chmod(gpg_py, 0o755)

    curl_py = os.path.join(bin_dir, "curl")
    curl_code = """#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil

app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
app_files = os.path.join(app_dir, "app_files")
keyrings_dir = os.path.join(app_dir, "userdata", "keyrings")
etc_apt = os.path.join(app_dir, "userdata", "etc_apt", "sources.list.d")
os.makedirs(keyrings_dir, exist_ok=True)
os.makedirs(etc_apt, exist_ok=True)

real_curl = "/usr/bin/curl"
if not os.path.isfile(real_curl):
    for c in ("/bin/curl", "/usr/local/bin/curl"):
        if os.path.isfile(c):
            real_curl = c
            break

child_env = os.environ.copy()
cur_shims = os.path.dirname(os.path.abspath(__file__))
p_parts = [p for p in child_env.get("PATH", "").split(":") if p and p != cur_shims]
child_env["PATH"] = ":".join(p_parts)

args = sys.argv[1:]
new_args = []
downloaded_files = []

i = 0
while i < len(args):
    arg = args[i]
    if arg in ("-o", "--output") and i + 1 < len(args):
        val = args[i + 1]
        fn = os.path.basename(val)
        if "/usr/share/keyrings" in val or "/etc/apt/keyrings" in val:
            target_path = os.path.join(keyrings_dir, fn)
            new_args.extend([arg, target_path])
            downloaded_files.append(("keyring", target_path))
            i += 2
            continue
        elif "/etc/apt/sources.list.d" in val:
            target_path = os.path.join(etc_apt, fn)
            new_args.extend([arg, target_path])
            downloaded_files.append(("repo", target_path))
            i += 2
            continue
    elif arg.startswith("--output="):
        val = arg.split("=", 1)[1]
        fn = os.path.basename(val)
        if "/usr/share/keyrings" in val or "/etc/apt/keyrings" in val:
            target_path = os.path.join(keyrings_dir, fn)
            new_args.append(f"--output={target_path}")
            downloaded_files.append(("keyring", target_path))
            i += 1
            continue
        elif "/etc/apt/sources.list.d" in val:
            target_path = os.path.join(etc_apt, fn)
            new_args.append(f"--output={target_path}")
            downloaded_files.append(("repo", target_path))
            i += 1
            continue
    elif arg.startswith("-") and not arg.startswith("--") and arg.endswith("o") and i + 1 < len(args):
        val = args[i + 1]
        fn = os.path.basename(val)
        if "/usr/share/keyrings" in val or "/etc/apt/keyrings" in val:
            target_path = os.path.join(keyrings_dir, fn)
            new_args.extend([arg, target_path])
            downloaded_files.append(("keyring", target_path))
            i += 2
            continue
        elif "/etc/apt/sources.list.d" in val:
            target_path = os.path.join(etc_apt, fn)
            new_args.extend([arg, target_path])
            downloaded_files.append(("repo", target_path))
            i += 2
            continue
    new_args.append(arg)
    i += 1

res = subprocess.run([real_curl] + new_args, env=child_env)

for ftype, fpath in downloaded_files:
    if ftype == "repo" and os.path.isfile(fpath):
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if "/usr/share/keyrings" in content or "/etc/apt/keyrings" in content:
                content = content.replace("/usr/share/keyrings/", keyrings_dir.rstrip("/") + "/")
                content = content.replace("/etc/apt/keyrings/", keyrings_dir.rstrip("/") + "/")
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(content)
        except Exception:
            pass

sys.exit(res.returncode)
"""
    with open(curl_py, "w", encoding="utf-8") as f:
        f.write(curl_code)
    os.chmod(curl_py, 0o755)

    wget_py = os.path.join(bin_dir, "wget")
    wget_code = """#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil

app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
app_files = os.path.join(app_dir, "app_files")
keyrings_dir = os.path.join(app_dir, "userdata", "keyrings")
etc_apt = os.path.join(app_dir, "userdata", "etc_apt", "sources.list.d")
os.makedirs(keyrings_dir, exist_ok=True)
os.makedirs(etc_apt, exist_ok=True)

real_wget = "/usr/bin/wget"
if not os.path.isfile(real_wget):
    for c in ("/bin/wget", "/usr/local/bin/wget"):
        if os.path.isfile(c):
            real_wget = c
            break

child_env = os.environ.copy()
cur_shims = os.path.dirname(os.path.abspath(__file__))
p_parts = [p for p in child_env.get("PATH", "").split(":") if p and p != cur_shims]
child_env["PATH"] = ":".join(p_parts)

args = sys.argv[1:]
new_args = []
downloaded_files = []

i = 0
while i < len(args):
    arg = args[i]
    if arg in ("-O", "--output-document") and i + 1 < len(args):
        val = args[i + 1]
        fn = os.path.basename(val)
        if "/usr/share/keyrings" in val or "/etc/apt/keyrings" in val:
            target_path = os.path.join(keyrings_dir, fn)
            new_args.extend([arg, target_path])
            downloaded_files.append(("keyring", target_path))
            i += 2
            continue
        elif "/etc/apt/sources.list.d" in val:
            target_path = os.path.join(etc_apt, fn)
            new_args.extend([arg, target_path])
            downloaded_files.append(("repo", target_path))
            i += 2
            continue
    elif arg.startswith("--output-document="):
        val = arg.split("=", 1)[1]
        fn = os.path.basename(val)
        if "/usr/share/keyrings" in val or "/etc/apt/keyrings" in val:
            target_path = os.path.join(keyrings_dir, fn)
            new_args.append(f"--output-document={target_path}")
            downloaded_files.append(("keyring", target_path))
            i += 1
            continue
        elif "/etc/apt/sources.list.d" in val:
            target_path = os.path.join(etc_apt, fn)
            new_args.append(f"--output-document={target_path}")
            downloaded_files.append(("repo", target_path))
            i += 1
            continue
    elif arg.startswith("-") and not arg.startswith("--") and arg.endswith("O") and i + 1 < len(args):
        val = args[i + 1]
        fn = os.path.basename(val)
        if "/usr/share/keyrings" in val or "/etc/apt/keyrings" in val:
            target_path = os.path.join(keyrings_dir, fn)
            new_args.extend([arg, target_path])
            downloaded_files.append(("keyring", target_path))
            i += 2
            continue
        elif "/etc/apt/sources.list.d" in val:
            target_path = os.path.join(etc_apt, fn)
            new_args.extend([arg, target_path])
            downloaded_files.append(("repo", target_path))
            i += 2
            continue
    new_args.append(arg)
    i += 1

res = subprocess.run([real_wget] + new_args, env=child_env)

for ftype, fpath in downloaded_files:
    if ftype == "repo" and os.path.isfile(fpath):
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if "/usr/share/keyrings" in content or "/etc/apt/keyrings" in content:
                content = content.replace("/usr/share/keyrings/", keyrings_dir.rstrip("/") + "/")
                content = content.replace("/etc/apt/keyrings/", keyrings_dir.rstrip("/") + "/")
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(content)
        except Exception:
            pass

sys.exit(res.returncode)
"""
    with open(wget_py, "w", encoding="utf-8") as f:
        f.write(wget_code)
    os.chmod(wget_py, 0o755)

    tee_py = os.path.join(bin_dir, "tee")
    tee_code = """#!/usr/bin/env python3
import os
import sys

app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
app_files = os.path.join(app_dir, "app_files")
etc_apt = os.path.join(app_dir, "userdata", "etc_apt", "sources.list.d")
keyrings_dir = os.path.join(app_dir, "userdata", "keyrings")
os.makedirs(etc_apt, exist_ok=True)
os.makedirs(keyrings_dir, exist_ok=True)

append_mode = False
target_files = []

for arg in sys.argv[1:]:
    if arg in ("-a", "--append"):
        append_mode = True
    elif arg.startswith("-"):
        continue
    else:
        fn = os.path.basename(arg)
        if "/etc/apt/" in arg or arg.endswith(".list") or arg.endswith(".sources"):
            target_files.append(os.path.join(etc_apt, fn))
        else:
            try:
                d = os.path.dirname(arg)
                if d and not os.path.exists(d):
                    os.makedirs(d, exist_ok=True)
                target_files.append(arg)
            except Exception:
                target_files.append(os.path.join(etc_apt, fn))

data = sys.stdin.buffer.read()
sys.stdout.buffer.write(data)
sys.stdout.buffer.flush()

mode = "ab" if append_mode else "wb"
for tf in target_files:
    try:
        write_data = data
        if tf.startswith(etc_apt):
            try:
                text_content = data.decode("utf-8", errors="ignore")
                if "/usr/share/keyrings" in text_content or "/etc/apt/keyrings" in text_content:
                    text_content = text_content.replace("/usr/share/keyrings/", keyrings_dir.rstrip("/") + "/")
                    text_content = text_content.replace("/etc/apt/keyrings/", keyrings_dir.rstrip("/") + "/")
                    write_data = text_content.encode("utf-8")
            except Exception:
                pass
        with open(tf, mode) as f:
            f.write(write_data)
    except Exception as e:
        sys.stderr.write(f"tee: {tf}: {e}\\n")
"""
    with open(tee_py, "w", encoding="utf-8") as f:
        f.write(tee_code)
    os.chmod(tee_py, 0o755)

    sudo_sh = os.path.join(bin_dir, "sudo")
    sudo_code = """#!/usr/bin/env bash
while [[ $# -gt 0 ]]; do
    case "$1" in
        -u|-g)
            echo "[App Encloser sudo] User/group switching ($1) is not supported in rootless containers." >&2
            exit 1
            ;;
        -p)
            shift 2
            ;;
        -E|-h|-k|-K|-v|-V|-s|-i)
            shift
            ;;
        --)
            shift
            break
            ;;
        *)
            break
            ;;
    esac
done
exec "$@"
"""
    with open(sudo_sh, "w", encoding="utf-8") as f:
        f.write(sudo_code)
    os.chmod(sudo_sh, 0o755)

    apt_sh = os.path.join(bin_dir, "apt")
    apt_code = """#!/usr/bin/env bash
app_dir="$(dirname "$(dirname "$(dirname "$(readlink -f "${0}")")")")"
app_files="$app_dir/app_files"
etc_apt="$app_dir/userdata/etc_apt/sources.list.d"
lists_dir="$app_dir/userdata/var_lib_apt_lists"
cache_dir="$app_dir/userdata/cache/apt"
keyrings_dir="$app_dir/userdata/keyrings"

if [[ "$1" == "upgrade" || "$1" == "full-upgrade" || "$1" == "dist-upgrade" ]]; then
    echo "[Container APT] Full system upgrade is not supported inside an isolated container. Manage individual container packages via 'install' or 'remove'." >&2
    exit 1
fi

if [[ "$1" == "update" ]]; then
    mkdir -p "$lists_dir/partial"
    mkdir -p "$cache_dir"
    mkdir -p "$keyrings_dir"
    if [[ -d "$etc_apt" && $(ls -A "$etc_apt" 2>/dev/null) ]]; then
        /usr/bin/apt-get \
            -o Dir::Etc::sourcelist=/etc/apt/sources.list \
            -o Dir::Etc::sourceparts="$etc_apt" \
            -o Dir::Etc::trustedparts="$keyrings_dir" \
            -o Dir::State::lists="$lists_dir" \
            -o Dir::Cache="$cache_dir" \
            -o Debug::NoLocking=1 update
        EC=$?
        if [[ $EC -ne 0 ]]; then
            echo "[Container APT] Package index update failed with exit code $EC." >&2
            exit $EC
        fi
        echo "[Container APT] Isolated package metadata is synchronized."
        exit 0
    else
        echo "[Container APT] No isolated sources configured; using host package index."
        exit 0
    fi
fi

if [[ "$1" == "install" ]]; then
    shift
    PKGS=()
    for arg in "$@"; do
        if [[ "$arg" != -* ]]; then
            PKGS+=("$arg")
        fi
    done
    if [[ ${#PKGS[@]} -eq 0 ]]; then
        echo "Error: No package specified to install."
        exit 1
    fi
    for p in "${PKGS[@]}"; do
        encloser-install "$p"
    done
    exit $?
fi

if [[ "$1" == "remove" || "$1" == "purge" ]]; then
    shift
    PKGS=()
    for arg in "$@"; do
        if [[ "$arg" != -* ]]; then
            PKGS+=("$arg")
        fi
    done
    if [[ ${#PKGS[@]} -eq 0 ]]; then
        echo "Error: No package specified to remove."
        exit 1
    fi
    for p in "${PKGS[@]}"; do
        encloser-install --remove "$p"
    done
    exit $?
fi

if [[ -x /usr/bin/apt ]]; then
    exec /usr/bin/apt "$@"
fi
"""
    with open(apt_sh, "w", encoding="utf-8") as f:
        f.write(apt_code)
    os.chmod(apt_sh, 0o755)

    apt_get_sh = os.path.join(bin_dir, "apt-get")
    with open(apt_get_sh, "w", encoding="utf-8") as f:
        f.write(apt_code)
    os.chmod(apt_get_sh, 0o755)

    helper_py = os.path.join(bin_dir, "encloser-install")
    helper_code = """#!/usr/bin/env python3
import os
import sys
import re
import json
import shutil
import subprocess
import urllib.request

def download_deb(url: str, dest_path: str) -> bool:
    if shutil.which("curl"):
        res = subprocess.run(["curl", "-sSL", "--fail", "-o", dest_path, url])
        if res.returncode == 0 and os.path.isfile(dest_path) and os.path.getsize(dest_path) > 0:
            return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(dest_path, "wb") as out_f:
            shutil.copyfileobj(resp, out_f)
        return True
    except Exception:
        return False

def fix_links(dest_dir: str):
    usr_lib = os.path.join(dest_dir, "usr", "lib")
    lib = os.path.join(dest_dir, "lib")
    if os.path.isdir(usr_lib):
        os.makedirs(lib, exist_ok=True)
        for item in os.listdir(usr_lib):
            t = os.path.join(lib, item)
            s = os.path.join(usr_lib, item)
            if not os.path.exists(t):
                try:
                    os.symlink(os.path.relpath(s, lib), t)
                except Exception:
                    pass
    usr_bin = os.path.join(dest_dir, "usr", "bin")
    b_dir = os.path.join(dest_dir, "bin")
    if os.path.isdir(b_dir) and os.path.isdir(usr_bin):
        for item in os.listdir(b_dir):
            t = os.path.join(usr_bin, item)
            s = os.path.join(b_dir, item)
            if not os.path.exists(t):
                try:
                    os.symlink(os.path.relpath(s, usr_bin), t)
                except Exception:
                    pass
            if os.path.isfile(t):
                try:
                    os.chmod(t, 0o755)
                except Exception:
                    pass

def is_safe_exec(p: str) -> bool:
    if not p or not isinstance(p, str):
        return False
    bad_chars = (';', '&', '|', '`', '$', '(', ')', '<', '>', '\\n', '\\r', '\\\\', '"')
    if any(c in p for c in bad_chars):
        return False
    clean = p.strip()
    if clean.startswith("/") or clean.startswith("-") or ".." in clean.split("/"):
        return False
    return True

def resolve_exec(app_f: str) -> str:
    cand_dirs = [os.path.join(app_f, "usr", "bin"), os.path.join(app_f, "bin"), os.path.join(app_f, "usr", "games"), os.path.join(app_f, "opt")]
    for cd in cand_dirs:
        if os.path.isdir(cd):
            for root, _, files in os.walk(cd):
                for fn in sorted(files):
                    fp = os.path.join(root, fn)
                    if os.access(fp, os.X_OK) and not fn.endswith((".so", ".a", ".png", ".desktop", ".xml", ".svg")):
                        rel = os.path.relpath(fp, app_f)
                        if is_safe_exec(rel):
                            return rel
    return ""

def main():
    if len(sys.argv) < 2:
        print("Usage: encloser-install <package_name|deb_file|url> OR encloser-install --remove <package_name>")
        sys.exit(1)
    target = sys.argv[1].strip()
    app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    app_files = os.path.join(app_dir, "app_files")
    folder_name = os.path.basename(app_dir)
    dl_dir = os.path.join(app_dir, "userdata", "cache")
    os.makedirs(dl_dir, exist_ok=True)
    manifest_file = os.path.join(app_dir, "userdata", "installed_pkgs.json")
    keyrings_dir = os.path.join(app_dir, "userdata", "keyrings")
    os.makedirs(keyrings_dir, exist_ok=True)

    prereqs = {"curl", "wget", "gpg", "gnupg", "ca-certificates", "apt-transport-https", "software-properties-common", "lsb-release"}
    if target.lower() in prereqs:
        check_cmd = ["dpkg-query", "-W", "-f=${Status}", target.lower()]
        res = subprocess.run(check_cmd, capture_output=True, text=True)
        if res.returncode == 0 and "install ok installed" in res.stdout:
            print(f"[Container APT] Prerequisite '{target}' is already available on host OS. Skipping container override.")
            sys.exit(0)
        if shutil.which(target.lower()):
            print(f"[Container APT] Prerequisite '{target}' is already available in PATH. Skipping container override.")
            sys.exit(0)

    if target in ("--remove", "remove", "--purge", "purge"):
        if len(sys.argv) < 3:
            print("Error: No package specified to remove.")
            sys.exit(1)
        pkg_to_remove = sys.argv[2].strip()
        installed_data = {}
        if os.path.isfile(manifest_file):
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    installed_data = json.load(f)
            except Exception:
                pass

        matched_key = None
        for k in installed_data:
            if k.lower() == pkg_to_remove.lower():
                matched_key = k
                break

        if matched_key:
            rec = installed_data.pop(matched_key)
            removed_count = 0
            for rel_f in rec.get("files", []):
                full_f = os.path.join(app_files, rel_f.lstrip("/"))
                if os.path.isfile(full_f) or os.path.islink(full_f):
                    try:
                        os.remove(full_f)
                        removed_count += 1
                    except Exception:
                        pass
            try:
                with open(manifest_file, "w", encoding="utf-8") as f:
                    json.dump(installed_data, f, indent=2)
            except Exception:
                pass
            print(f"[Container APT] Removed container override for '{pkg_to_remove}' ({removed_count} files removed). Host OS version will be used if present.")
            sys.exit(0)
        else:
            print(f"[Container APT] Package '{pkg_to_remove}' not found in container overlay.")
            sys.exit(0)

    target_deb = target

    if target.startswith(("http://", "https://")):
        print(f"[*] Downloading {target}...")
        fn = os.path.basename(target.split("?")[0]) or "package.deb"
        dl_path = os.path.join(dl_dir, fn)
        if not download_deb(target, dl_path):
            print(f"Error: Failed to download from {target}")
            sys.exit(1)
        target_deb = dl_path
    elif not os.path.isfile(target):
        pkg = target
        print(f"[*] Fetching {pkg} via APT...")
        etc_apt_dir = os.path.join(app_dir, "userdata", "etc_apt", "sources.list.d")
        lists_dir = os.path.join(app_dir, "userdata", "var_lib_apt_lists")
        cache_dir = os.path.join(app_dir, "userdata", "cache", "apt")
        apt_cmd = [
            "apt-get",
            "-o", f"Dir::Etc::trustedparts={keyrings_dir}",
        ]
        if os.path.isdir(etc_apt_dir) and os.listdir(etc_apt_dir):
            os.makedirs(os.path.join(lists_dir, "partial"), exist_ok=True)
            os.makedirs(cache_dir, exist_ok=True)
            apt_cmd.extend([
                "-o", "Dir::Etc::sourcelist=/etc/apt/sources.list",
                "-o", f"Dir::Etc::sourceparts={etc_apt_dir}",
                "-o", f"Dir::State::lists={lists_dir}",
                "-o", f"Dir::Cache={cache_dir}",
                "-o", "Debug::NoLocking=1"
            ])
        apt_cmd.extend(["download", pkg])
        res = subprocess.run(apt_cmd, cwd=dl_dir)
        if res.returncode != 0:
            res = subprocess.run(["apt-get", "-o", f"Dir::Etc::trustedparts={keyrings_dir}", "download", pkg], cwd=dl_dir)
        if res.returncode != 0:
            print(f"Error: Could not download {pkg}")
            sys.exit(1)
        pkg_base = pkg.split("=")[0]
        debs = [f for f in os.listdir(dl_dir) if f.endswith(".deb") and pkg_base in f]
        if not debs:
            debs = [f for f in os.listdir(dl_dir) if f.endswith(".deb")]
        if not debs:
            print("Error: No package archive retrieved.")
            sys.exit(1)
        debs.sort(key=lambda fn: os.path.getmtime(os.path.join(dl_dir, fn)), reverse=True)
        target_deb = os.path.join(dl_dir, debs[0])

    extracted_files = []
    try:
        cnt = subprocess.run(["dpkg-deb", "--contents", target_deb], capture_output=True, text=True)
        if cnt.returncode == 0:
            for line in cnt.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 6:
                    rel_p = parts[5].lstrip("./")
                    if rel_p and not rel_p.endswith("/"):
                        extracted_files.append(rel_p)
    except Exception:
        pass

    pkg_key = target.split("=")[0] if not target.startswith(("http://", "https://")) and not os.path.isfile(target) else os.path.basename(target_deb).split("_")[0]
    installed_data = {}
    if os.path.isfile(manifest_file):
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                installed_data = json.load(f)
        except Exception:
            pass

    if pkg_key in installed_data and installed_data[pkg_key].get("files"):
        for old_f in installed_data[pkg_key]["files"]:
            full_old = os.path.join(app_files, old_f.lstrip("/"))
            if os.path.isfile(full_old) or os.path.islink(full_old):
                try:
                    os.remove(full_old)
                except Exception:
                    pass

    installed_data[pkg_key] = {
        "deb": os.path.basename(target_deb),
        "files": extracted_files
    }
    try:
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(installed_data, f, indent=2)
    except Exception:
        pass

    print(f"[*] Unpacking {os.path.basename(target_deb)} into container environment...")
    res = subprocess.run(["dpkg-deb", "-x", target_deb, app_files], check=False)
    if res.returncode != 0:
        subprocess.run(["dpkg", "-x", target_deb, app_files], check=False)

    fix_links(app_files)

    with open(os.path.join(app_dir, ".pkg_format"), "w", encoding="utf-8") as f:
        f.write("DEB")

    apps_dir = os.path.join(app_files, "usr", "share", "applications")
    found_desk = None
    target_bin = None
    display_name = folder_name
    wm_class = folder_name
    icon_source = None

    if os.path.isdir(apps_dir):
        desks = [f for f in os.listdir(apps_dir) if f.endswith(".desktop")]
        for df in desks:
            dp = os.path.join(apps_dir, df)
            try:
                with open(dp, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("Name=") and (not display_name or display_name == folder_name):
                            display_name = line.split("=", 1)[1].strip()
                        elif line.startswith("Exec=") and not target_bin:
                            raw = line.split("=", 1)[1].strip()
                            clean = re.sub(r" %[a-zA-Z]", "", raw).split()[0].lstrip("/")
                            if is_safe_exec(clean):
                                target_bin = clean
                        elif line.startswith("StartupWMClass="):
                            wm_class = line.split("=", 1)[1].strip()
                        elif line.startswith("Icon=") and not icon_source:
                            icon_source = line.split("=", 1)[1].strip()
                found_desk = dp
                if target_bin:
                    break
            except Exception:
                pass

    if not target_bin:
        target_bin = resolve_exec(app_files)

    if target_bin and is_safe_exec(target_bin):
        safe_bin = target_bin.replace("'", "'\\''")
        with open(os.path.join(app_dir, ".target_exec"), "w", encoding="utf-8") as f:
            f.write(safe_bin)
        launch_sh = os.path.join(app_dir, "launch.sh")
        if os.path.isfile(launch_sh):
            try:
                with open(launch_sh, "r", encoding="utf-8") as lf:
                    lcontent = lf.read()
                new_lcontent = re.sub(r"REL_EXEC='[^']*'", f"REL_EXEC='{safe_bin}'", lcontent)
                new_lcontent = re.sub(r'TARGET_BIN="\\$HERE/app_files/[^"]*"', f'TARGET_BIN="$HERE/app_files/{safe_bin}"', new_lcontent)
                with open(launch_sh, "w", encoding="utf-8") as lf:
                    lf.write(new_lcontent)
            except Exception:
                pass

    icon_copied = False
    icon_targets = []
    if icon_source:
        icon_targets.append(icon_source.lower())
    icon_targets.append(folder_name.lower())
    if found_desk:
        d_stem = os.path.splitext(os.path.basename(found_desk))[0].lower()
        if d_stem not in icon_targets:
            icon_targets.append(d_stem)

    for cand_name in icon_targets:
        for root, _, files in os.walk(app_files):
            for file in files:
                if cand_name in file.lower() and file.endswith((".png", ".svg")):
                    dest_icon = os.path.join(app_dir, "icon.png" if file.endswith(".png") else "icon.svg")
                    try:
                        shutil.copyfile(os.path.join(root, file), dest_icon)
                        icon_copied = True
                        break
                    except Exception:
                        pass
            if icon_copied:
                break
        if icon_copied:
            break

    desk_file = os.path.join(app_dir, f"{folder_name}.desktop")
    launch_sh = os.path.join(app_dir, "launch.sh")
    resolved_icon = os.path.join(app_dir, "icon.png" if os.path.isfile(os.path.join(app_dir, "icon.png")) else "icon.svg")
    with open(desk_file, "w", encoding="utf-8") as f:
        f.write(f"[Desktop Entry]\\nVersion=1.0\\nType=Application\\nName={display_name}\\nExec={launch_sh} %f\\nIcon={resolved_icon}\\nStartupWMClass={wm_class}\\nCategories=Utility;\\nTerminal=false\\n")

    print(f"[+] Successfully installed {display_name} into container environment!")
    print(f"[+] Isolated binary target: {target_bin}")

if __name__ == "__main__":
    main()
"""
    with open(helper_py, "w", encoding="utf-8") as f:
        f.write(helper_code)
    os.chmod(helper_py, 0o755)

    py_sh = os.path.join(bin_dir, "encloser-python")
    py_code = """#!/usr/bin/env bash
set -e

if [[ $# -eq 0 ]]; then
    echo "Usage: encloser-python <version> [uv python install options...]"
    echo "Example: encloser-python 3.11"
    echo "Example: encloser-python 3.13"
    exit 1
fi

TARGET_VER="$1"
app_dir="$(dirname "$(dirname "$(dirname "$(readlink -f "${0}")")")")"
HERE="$app_dir"

export UV_CACHE_DIR="$HERE/userdata/cache/uv"
export UV_PYTHON_INSTALL_DIR="$HERE/userdata/local_share/uv/python"
export UV_TOOL_DIR="$HERE/userdata/local_share/uv/tools"
export UV_TOOL_BIN_DIR="$HERE/userdata/bin"
export PIP_CACHE_DIR="$HERE/userdata/cache/pip"
export PYTHONUSERBASE="$HERE/userdata/home/.local"
export PATH="$HERE/userdata/bin:$HERE/userdata/home/.local/bin:$HERE/userdata/local_share/uv/python:$PATH"

if ! command -v uv >/dev/null 2>&1; then
    echo "Error: 'uv' is required to manage isolated Python versions."
    exit 1
fi

echo "[*] Installing Python $TARGET_VER via uv..."
uv python install "$@"
echo "[*] Creating isolated virtualenv at $HERE/userdata/venv with Python $TARGET_VER..."
uv venv --python "$1" "$HERE/userdata/venv"
echo "[+] Isolated Python $TARGET_VER environment ready at $HERE/userdata/venv"
echo "[+] Container launch.sh will automatically activate this environment."
"""
    with open(py_sh, "w", encoding="utf-8") as f:
        f.write(py_code)
    os.chmod(py_sh, 0o755)

    brew_sh = os.path.join(bin_dir, "encloser-brew")
    brew_code = """#!/usr/bin/env bash
set -e
app_dir="$(dirname "$(dirname "$(dirname "$(readlink -f "${0}")")")")"
brew_home="$app_dir/userdata/linuxbrew"
export HOMEBREW_PREFIX="$brew_home"
export HOMEBREW_CELLAR="$brew_home/Cellar"
export HOMEBREW_REPOSITORY="$brew_home/Homebrew"
export PATH="$brew_home/bin:$brew_home/sbin:$PATH"
export HOMEBREW_CACHE="$app_dir/userdata/cache/homebrew"
export HOMEBREW_LOGS="$app_dir/userdata/logs/homebrew"
export HOMEBREW_TEMP="$app_dir/userdata/tmp"
if [[ ! -x "$brew_home/bin/brew" ]]; then
    echo "[*] Initializing isolated container Homebrew in $brew_home..."
    mkdir -p "$brew_home/bin" "$brew_home/Cellar" "$brew_home/etc" "$brew_home/var"
    if [[ -x /home/linuxbrew/.linuxbrew/bin/brew ]]; then
        echo "[*] Linking base Homebrew binaries from host system..."
        ln -sf /home/linuxbrew/.linuxbrew/bin/* "$brew_home/bin/" 2>/dev/null || true
    else
        echo "[*] Cloning Homebrew core into container universe..."
        git clone --depth=1 https://github.com/Homebrew/brew "$brew_home/Homebrew" 2>/dev/null || true
        ln -sf "$brew_home/Homebrew/bin/brew" "$brew_home/bin/brew" 2>/dev/null || true
    fi
fi
if [[ ! -x "$brew_home/bin/brew" ]]; then
    echo "Error: Homebrew binary could not be found or initialized."
    exit 1
fi
exec "$brew_home/bin/brew" "$@"
"""
    with open(brew_sh, "w", encoding="utf-8") as f:
        f.write(brew_code)
    os.chmod(brew_sh, 0o755)

    nft_sh = os.path.join(bin_dir, "nft")
    with open(nft_sh, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\nif [ -p /dev/stdin ]; then\n    cat >/dev/null 2>&1 || true\nfi\nexit 0\n")
    os.chmod(nft_sh, 0o755)

    lib_dir = os.path.join(app_dir, "app_files", "lib")
    os.makedirs(lib_dir, exist_ok=True)
    shim_dest = os.path.join(lib_dir, "libencloser_shim.so")

    shim_candidates = [
        "/usr/lib/app-encloser/libencloser_shim.so",
        "/usr/local/lib/app-encloser/libencloser_shim.so",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "libencloser_shim.so"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "libencloser_shim.so"),
    ]
    shim_found = False
    for cand in shim_candidates:
        if os.path.isfile(cand):
            try:
                shutil.copyfile(cand, shim_dest)
                os.chmod(shim_dest, 0o755)
                shim_found = True
                break
            except Exception:
                pass

    if not shim_found and shutil.which("gcc"):
        c_src = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "libencloser_shim.c")
        if os.path.isfile(c_src):
            try:
                subprocess.run(
                    ["gcc", "-fPIC", "-shared", "-O2", c_src, "-o", shim_dest, "-ldl"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                if os.path.isfile(shim_dest):
                    os.chmod(shim_dest, 0o755)
            except Exception:
                pass


def list_enclosed_apps() -> List[Dict[str, Any]]:
    apps = []
    if not os.path.isdir(ENCLOSED_DIR):
        return apps

    for entry in sorted(os.listdir(ENCLOSED_DIR)):
        if entry.startswith("."):
            continue
        d = os.path.join(ENCLOSED_DIR, entry)
        if not os.path.isdir(d):
            continue

        launch_sh = os.path.join(d, "launch.sh")
        if os.path.isfile(launch_sh) and not os.access(launch_sh, os.X_OK):
            try:
                os.chmod(launch_sh, 0o755)
            except Exception:
                pass

        desk = os.path.join(d, f"{entry}.desktop")
        name = entry
        if os.path.isfile(desk):
            info = parse_desktop_file(desk)
            if info.get("Name"):
                name = info["Name"]

        icon_p = os.path.join(d, "icon.png")
        if not os.path.isfile(icon_p):
            icon_s = os.path.join(d, "icon.svg")
            if os.path.isfile(icon_s):
                try:
                    with open(icon_s, "r", encoding="utf-8", errors="ignore") as f_icon:
                        svg_txt = f_icon.read()
                    if '<text x="128" y="162"' in svg_txt or "SVG Monogram" in svg_txt:
                        desk_icon = None
                        if os.path.isfile(desk):
                            desk_info = parse_desktop_file(desk)
                            desk_icon = desk_info.get("Icon")
                        new_icon = extract_or_generate_icon(d, entry, desk_icon)
                        icon_p = new_icon if os.path.isfile(new_icon) else icon_s
                    else:
                        icon_p = icon_s
                except Exception:
                    icon_p = icon_s
            else:
                icon_p = None
        if not icon_p or not os.path.isfile(icon_p):
            icon_p = None

        fmt_f = os.path.join(d, ".pkg_format")
        fmt = "DEB"
        if os.path.isfile(fmt_f):
            try:
                with open(fmt_f, "r", encoding="utf-8") as f_fmt:
                    fmt = f_fmt.read().strip().upper() or "DEB"
            except Exception:
                pass

        pids = get_running_app_pids(entry)
        ram_mb = get_pids_ram_mb(pids)
        installed_ts = os.path.getctime(d) if os.path.exists(d) else 0.0
        installed_date = datetime.fromtimestamp(installed_ts).strftime("%Y-%m-%d %H:%M") if installed_ts > 0 else ""
        size_bytes = get_dir_size_bytes(d)

        t_file = os.path.join(d, ".target_exec")
        target_exec = ""
        if os.path.isfile(t_file):
            try:
                with open(t_file, "r", encoding="utf-8") as f_tgt:
                    target_exec = f_tgt.read().strip()
            except Exception:
                pass
        c_file = os.path.join(d, ".install_cmd")
        install_cmd = ""
        if os.path.isfile(c_file):
            try:
                with open(c_file, "r", encoding="utf-8") as f_cmd:
                    install_cmd = f_cmd.read().strip()
            except Exception:
                pass
        is_cli = target_exec.startswith("userdata/bin") or fmt == "CLI"
        if os.path.isfile(desk):
            info = parse_desktop_file(desk)
            if info.get("Terminal") == "true":
                is_cli = True

        apps.append({
            "folder": entry,
            "name": name,
            "format": fmt,
            "path": d,
            "icon": icon_p,
            "target_exec": target_exec,
            "install_cmd": install_cmd,
            "is_cli": is_cli,
            "app_size": get_dir_size(os.path.join(d, "app_files")),
            "user_size": get_dir_size(os.path.join(d, "userdata")),
            "total_size": get_dir_size(d),
            "size_bytes": size_bytes,
            "installed_ts": installed_ts,
            "installed_date": installed_date,
            "ram_mb": ram_mb,
            "strict_sandbox": is_strict_sandbox(d),
            "enclosing_level": get_enclosing_level(d),
            "enclosing_details": get_enclosing_level_details(get_enclosing_level(d)),
            "launch_sh": os.path.join(d, "launch.sh"),
            "is_running": len(pids) > 0,
            "running_pids": pids,
        })

    return apps


def repair_app(folder_name: str) -> Tuple[bool, str]:
    app_dir = os.path.join(ENCLOSED_DIR, folder_name)
    if not os.path.isdir(app_dir):
        return False, f"Folder {folder_name} does not exist"

    app_files = os.path.join(app_dir, "app_files")
    if not os.path.isdir(app_files):
        return False, f"No app_files directory found in {folder_name}"

    fmt_f = os.path.join(app_dir, ".pkg_format")
    pkg_format = "deb"
    if os.path.isfile(fmt_f):
        try:
            with open(fmt_f, "r", encoding="utf-8") as f_fmt:
                pkg_format = f_fmt.read().strip() or "deb"
        except Exception:
            pass

    desk_path, desk_info = find_best_desktop_file(app_files, folder_name)

    orig_exec = desk_info.get("Exec", "")
    if orig_exec:
        orig_exec = re.sub(r" %[a-zA-Z]", "", orig_exec).strip().split()[0]

    t_file = os.path.join(app_dir, ".target_exec")
    user_bin = os.path.join(app_dir, "userdata", "bin")
    cand_user = os.path.join(user_bin, folder_name.lower())
    cand_local = os.path.join(app_dir, "userdata", "home", ".local", "bin", folder_name.lower())
    rel_exec = None

    SHIMS = {"apt", "apt-get", "gpg", "tee", "sudo", "nft", "curl", "wget", "encloser-install", "encloser-python", "encloser-brew"}
    if orig_exec:
        cand_desk = resolve_executable(app_files, orig_exec)
        if cand_desk and os.path.basename(cand_desk) not in SHIMS:
            rel_exec = cand_desk

    if not rel_exec and os.path.isfile(cand_user) and os.access(cand_user, os.X_OK):
        rel_exec = f"userdata/bin/{folder_name.lower()}"
    elif not rel_exec and os.path.isfile(cand_local) and os.access(cand_local, os.X_OK):
        rel_exec = f"userdata/home/.local/bin/{folder_name.lower()}"
    elif not rel_exec and os.path.isfile(t_file):
        try:
            with open(t_file, "r", encoding="utf-8") as f_ex:
                existing = f_ex.read().strip()
            if os.path.basename(existing) not in SHIMS:
                full_cand = os.path.join(app_dir, existing)
                full_cand_af = os.path.join(app_files, existing.lstrip("/"))
                if os.path.isfile(full_cand) or os.path.isfile(full_cand_af):
                    rel_exec = existing
        except Exception:
            pass

    if not rel_exec:
        if os.path.isdir(user_bin):
            for fn in sorted(os.listdir(user_bin)):
                if fn not in SHIMS and not fn.endswith((".sh", ".env")):
                    fp = os.path.join(user_bin, fn)
                    if os.path.isfile(fp) and os.access(fp, os.X_OK):
                        rel_exec = f"userdata/bin/{fn}"
                        break
        if not rel_exec:
            rel_exec = resolve_executable(app_files, orig_exec or folder_name.lower())
        if not rel_exec:
            rel_exec = resolve_executable(app_files, "")

    if rel_exec:
        with open(t_file, "w", encoding="utf-8") as f:
            f.write(rel_exec)

    if not rel_exec:
        return False, f"Could not determine target executable for {folder_name}"

    display_name = desk_info.get("Name", "").strip()
    if not display_name:
        display_name = folder_name

    wm_class = desk_info.get("StartupWMClass", "").strip()
    if not wm_class:
        wm_class = os.path.basename(rel_exec)

    orig_id = os.path.splitext(os.path.basename(desk_path))[0] if desk_path else ""
    if any(h in orig_id.lower() for h in ("urlhandler", "url-handler")):
        orig_id = ""

    with open(os.path.join(app_dir, ".wayland_id"), "w", encoding="utf-8") as f:
        f.write(wm_class)

    desktop_icon = desk_info.get("Icon")
    icon_path = extract_or_generate_icon(app_dir, folder_name, desktop_icon)

    install_container_helpers(app_dir)
    write_launch_script(app_dir, rel_exec, pkg_format)
    update_desktop_files_for_app(app_dir, folder_name, display_name, wm_class, icon_path, orig_id)

    return True, f"Repaired {folder_name} -> {display_name}"


def repair_all_apps() -> List[Dict[str, Any]]:
    results = []
    invalidate_dir_size_cache()
    if not os.path.isdir(ENCLOSED_DIR):
        return results

    for entry in sorted(os.listdir(ENCLOSED_DIR)):
        if entry.startswith("."):
            continue
        p = os.path.join(ENCLOSED_DIR, entry)
        if os.path.isdir(p):
            ok, msg = repair_app(entry)
            results.append({"folder": entry, "success": ok, "message": msg})

    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", APPS_DIR], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    if shutil.which("gtk-update-icon-cache"):
        subprocess.run(["gtk-update-icon-cache", "-q", "-t", "-f", ICONS_DIR], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

    return results


def uninstall_enclosed_app(folder_name: str):
    import time
    kill_app_processes(folder_name)
    for _ in range(5):
        rem = get_running_app_pids(folder_name, fast_check=False)
        if not rem:
            break
        kill_app_processes(folder_name)
        time.sleep(0.1)
    app_dir = os.path.join(ENCLOSED_DIR, folder_name)
    invalidate_dir_size_cache(app_dir)

    app_dir_path = os.path.abspath(app_dir)
    desk = os.path.join(app_dir, f"{folder_name}.desktop")
    display_name = ""
    wm_class = ""
    if os.path.isfile(desk):
        info = parse_desktop_file(desk)
        display_name = info.get("Name", "")
        wm_class = info.get("StartupWMClass", "")

    if os.path.isdir(APPS_DIR):
        norm_fldr = folder_name.lower().replace("-", "").replace("_", "")
        norm_disp = display_name.lower().replace(" ", "").replace("-", "").replace("_", "") if display_name else ""
        norm_wm = wm_class.lower().replace(" ", "").replace("-", "").replace("_", "") if wm_class else ""

        for fn in os.listdir(APPS_DIR):
            fp = os.path.join(APPS_DIR, fn)
            should_remove = False

            if os.path.islink(fp):
                try:
                    tgt = os.path.realpath(fp)
                    if app_dir_path in tgt or (f"/EnclosedApps/{folder_name}" in tgt and not os.path.exists(tgt)):
                        should_remove = True
                except Exception:
                    pass
            elif os.path.isfile(fp):
                try:
                    with open(fp, "r", errors="ignore") as f:
                        c = f.read()
                        if app_dir_path in c or f"/EnclosedApps/{folder_name}/" in c or f"/EnclosedApps/{folder_name}" in c:
                            should_remove = True
                except Exception:
                    pass

            if fn in (f"{folder_name}.desktop", f"app.encloser.{folder_name}.desktop"):
                should_remove = True

            if should_remove:
                try:
                    os.remove(fp)
                except Exception:
                    pass

    if os.path.isdir(app_dir):
        try:
            shutil.rmtree(app_dir, ignore_errors=True)
        except Exception:
            pass
        if os.path.isdir(app_dir):
            subprocess.run(["rm", "-rf", app_dir], stderr=subprocess.DEVNULL)

    from app_encloser.core.history import mark_as_uninstalled, is_protected_system_package
    mark_as_uninstalled(folder_name)

    if os.path.isdir(ICONS_DIR):
        target_icon_names = {
            f"{folder_name}.png", f"{folder_name}.svg",
            f"{folder_name.lower()}.png", f"{folder_name.lower()}.svg",
            f"app-encloser-{folder_name.lower()}.png", f"app-encloser-{folder_name.lower()}.svg"
        }
        for root_d, _, files in os.walk(ICONS_DIR):
            for fn in files:
                if fn in target_icon_names:
                    try:
                        os.remove(os.path.join(root_d, fn))
                    except Exception:
                        pass

    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", APPS_DIR], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    if shutil.which("gtk-update-icon-cache"):
        subprocess.run(["gtk-update-icon-cache", "-q", "-t", "-f", ICONS_DIR], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)


def batch_uninstall(folders: List[str]) -> List[Dict[str, Any]]:
    results = []
    for f in folders:
        uninstall_enclosed_app(f)
        results.append({"folder": f, "success": True})
    return results


def batch_clear_cache(folders: List[str], clear_cache: bool = True, clear_logs: bool = True, clear_userdata: bool = False) -> List[Dict[str, Any]]:
    results = []
    for f in folders:
        app_dir = os.path.join(ENCLOSED_DIR, f)
        ud = os.path.join(app_dir, "userdata")
        targets = [ud, app_dir]
        if clear_cache:
            for root in targets:
                for sub in ("cache", "tmp"):
                    p = os.path.join(root, sub)
                    if os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                        os.makedirs(p, exist_ok=True)
        if clear_logs:
            for root in targets:
                for fn in ("last_run.log", "last_exit_code"):
                    fp = os.path.join(root, fn)
                    if os.path.isfile(fp):
                        try:
                            os.remove(fp)
                        except Exception:
                            pass
                state_d = os.path.join(root, "state")
                if os.path.isdir(state_d):
                    shutil.rmtree(state_d, ignore_errors=True)
                    os.makedirs(state_d, exist_ok=True)
        if clear_userdata:
            for root in targets:
                for sub in ("home", "config", "local_share"):
                    p = os.path.join(root, sub)
                    if os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                        os.makedirs(p, exist_ok=True)
        invalidate_dir_size_cache(app_dir)
        results.append({"folder": f, "success": True})
    return results


def uninstall_host_package(target_info: Dict[str, Any], status_cb=None) -> Tuple[bool, str]:
    if not isinstance(target_info, dict):
        target_info = {"target": str(target_info)}

    t_type = target_info.get("type", "apt_package")
    target = target_info.get("target") or target_info.get("app_name") or target_info.get("name") or ""
    path = target_info.get("path", "")
    folder_or_name = target_info.get("folder_name") or target_info.get("app_name") or target

    if not target and not path:
        return False, "No target package or binary specified for host uninstallation."

    from app_encloser.core.history import mark_as_uninstalled, is_protected_system_package, invalidate_host_discovery_cache

    if path:
        norm_p = os.path.realpath(path)
        forbidden_dirs = ("/usr/bin", "/bin", "/sbin", "/usr/sbin", "/lib", "/usr/lib")
        if any(norm_p == fd or norm_p.startswith(fd + "/") for fd in forbidden_dirs):
            return False, f"Blocked: System binary at '{path}' cannot be deleted."
        if norm_p.startswith("/usr/local/bin/") and norm_p != "/usr/local/bin/ollama":
            return False, f"Blocked: System binary at '{path}' cannot be deleted."

    if t_type == "ollama_host":
        if status_cb:
            status_cb("Stopping and removing Ollama host service...")
        sh_cmd = "systemctl stop ollama 2>/dev/null || true; systemctl disable ollama 2>/dev/null || true; rm -f /etc/systemd/system/ollama.service /usr/local/bin/ollama; rm -rf /usr/share/ollama"
        has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        if shutil.which("pkexec") and has_display:
            subprocess.run(["pkexec", "sh", "-c", sh_cmd], capture_output=True, text=True)
        elif shutil.which("sudo"):
            subprocess.run(["sudo", "sh", "-c", sh_cmd], capture_output=True, text=True)
        else:
            subprocess.run(["sh", "-c", sh_cmd], capture_output=True, text=True)
        ollama_home = os.path.expanduser("~/.ollama")
        if os.path.isdir(ollama_home):
            shutil.rmtree(ollama_home, ignore_errors=True)
        mark_as_uninstalled(folder_or_name)
        invalidate_host_discovery_cache()
        if status_cb:
            status_cb("Purged Ollama host installation.")
        return True, "Purged Ollama service, binaries, and models from host."

    elif t_type == "claude_cli":
        if status_cb:
            status_cb("Uninstalling Claude Code CLI from host...")
        if shutil.which("npm"):
            subprocess.run(["npm", "uninstall", "-g", "@anthropic-ai/claude-code"], capture_output=True, text=True)
        for cand_f in (
            os.path.join(REAL_HOME, ".local", "bin", "claude"),
            os.path.join(REAL_HOME, ".npm-global", "bin", "claude"),
            "/usr/local/bin/claude",
            os.path.expanduser("~/.local/bin/claude"),
            os.path.expanduser("~/.npm-global/bin/claude"),
        ):
            if os.path.isfile(cand_f) or os.path.islink(cand_f):
                try:
                    os.remove(cand_f)
                except Exception:
                    pass
        for cfg_f in (
            os.path.join(REAL_HOME, ".claude.json"),
            os.path.expanduser("~/.claude.json"),
        ):
            if os.path.isfile(cfg_f):
                try:
                    shutil.copyfile(cfg_f, f"{cfg_f}.bak")
                except Exception:
                    pass
        mark_as_uninstalled(folder_or_name)
        invalidate_host_discovery_cache()
        if status_cb:
            status_cb("Purged Claude Code CLI from host.")
        return True, "Purged Claude Code CLI and configuration from host."

    elif t_type == "homebrew":
        if target.lower() in ("homebrew", "brew"):
            removed = False
            for br in ("/home/linuxbrew/.linuxbrew", os.path.expanduser("~/.linuxbrew")):
                if os.path.isdir(br):
                    shutil.rmtree(br, ignore_errors=True)
                    removed = True
            mark_as_uninstalled(folder_or_name)
            invalidate_host_discovery_cache()
            if status_cb:
                status_cb("Removed Homebrew installation from host.")
            return True, "Removed Homebrew installation from host." if removed else "Homebrew directory not found."
        else:
            brew_bin = "/home/linuxbrew/.linuxbrew/bin/brew"
            if not os.path.isfile(brew_bin):
                brew_bin = shutil.which("brew") or os.path.expanduser("~/.linuxbrew/bin/brew")
            if os.path.isfile(brew_bin):
                if status_cb:
                    status_cb(f"Purging {target} via brew uninstall --zap...")
                proc = subprocess.run([brew_bin, "uninstall", "--zap", target], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if proc.returncode == 0:
                    mark_as_uninstalled(folder_or_name)
                    invalidate_host_discovery_cache()
                    return True, f"Uninstalled {target} via brew zap."
                return False, f"Brew uninstall failed: {proc.stderr.strip()[:150]}"
            return False, "Homebrew binary not found."

    elif t_type == "uv_tool":
        uv_bin = shutil.which("uv") or "uv"
        if status_cb:
            status_cb(f"Uninstalling {target} via uv tool uninstall...")
        proc = subprocess.run([uv_bin, "tool", "uninstall", target], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode == 0:
            mark_as_uninstalled(folder_or_name)
            invalidate_host_discovery_cache()
            return True, f"Uninstalled {target} via uv."
        return False, f"uv uninstall failed: {proc.stderr.strip()[:150]}"

    elif t_type == "pip_user":
        if status_cb:
            status_cb(f"Uninstalling {target} via pip...")
        proc = subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", target], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode == 0:
            mark_as_uninstalled(folder_or_name)
            invalidate_host_discovery_cache()
            return True, f"Uninstalled {target} via pip."
        return False, f"pip uninstall failed: {proc.stderr.strip()[:150]}"

    elif t_type in ("local_bin", "cargo_bin", "binary"):
        bin_path = path
        if not bin_path:
            if t_type == "cargo_bin":
                bin_path = os.path.join(REAL_HOME, ".cargo", "bin", target)
            else:
                bin_path = os.path.join(LOCAL_BIN, target)
        norm_bp = os.path.realpath(bin_path)
        forbidden_dirs = ("/usr/bin", "/bin", "/sbin", "/usr/sbin", "/lib", "/usr/lib")
        if any(norm_bp == fd or norm_bp.startswith(fd + "/") for fd in forbidden_dirs):
            return False, f"Blocked: System binary at '{bin_path}' cannot be deleted."
        if norm_bp.startswith("/usr/local/bin/") and norm_bp != "/usr/local/bin/ollama":
            return False, f"Blocked: System binary at '{bin_path}' cannot be deleted."
        if os.path.isfile(bin_path):
            try:
                os.remove(bin_path)
                mark_as_uninstalled(folder_or_name)
                invalidate_host_discovery_cache()
                if status_cb:
                    status_cb(f"Removed binary {bin_path}")
                return True, f"Removed binary {bin_path}"
            except Exception as e:
                return False, f"Failed to delete {bin_path}: {e}"
        return False, f"Binary {bin_path} not found."

    elif t_type == "npm_global":
        if status_cb:
            status_cb(f"Uninstalling global npm package {target}...")
        proc = subprocess.run(["npm", "uninstall", "-g", target], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode == 0:
            mark_as_uninstalled(folder_or_name)
            invalidate_host_discovery_cache()
            return True, f"Uninstalled {target} via npm."
        return False, f"npm uninstall failed: {proc.stderr.strip()[:150]}"

    else:
        pkg = target
        if is_protected_system_package(pkg):
            return False, f"Blocked: '{pkg}' is a protected system package and cannot be uninstalled."

        dry_run = subprocess.run(["apt-get", "-s", "autoremove", "--purge", pkg], capture_output=True, text=True)
        critical_patterns = ("ubuntu-desktop", "gnome-shell", "python3-gi", "systemd", "grub-", "linux-image")
        remv_lines = [l for l in dry_run.stdout.splitlines() if l.strip().startswith("Remv ") or l.strip().startswith("Purg ")]
        if len(remv_lines) > 15 or any(any(cp in line for cp in critical_patterns) for line in remv_lines):
            return False, "Blocked: Uninstalling this package would remove critical Ubuntu desktop or system components."

        if status_cb:
            status_cb(f"Purging {pkg} from host system...")
        has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        if shutil.which("pkexec") and has_display:
            cmd = ["pkexec", "apt-get", "autoremove", "--purge", "-y", pkg]
        elif shutil.which("sudo"):
            cmd = ["sudo", "apt-get", "autoremove", "--purge", "-y", pkg]
        else:
            cmd = ["apt-get", "autoremove", "--purge", "-y", pkg]

        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if proc.returncode == 0:
                mark_as_uninstalled(folder_or_name)
                invalidate_host_discovery_cache()
                return True, f"Purged {pkg} and all configuration files from host system."
            return False, f"APT purge failed: {proc.stderr.strip()[:150]}"
        except Exception as e:
            return False, str(e)


def get_purge_command_str(target_info: Dict[str, Any]) -> str:
    if not isinstance(target_info, dict):
        return f"sudo apt-get autoremove --purge -y {target_info}"
    t_type = target_info.get("type", "apt_package")
    target = target_info.get("target") or target_info.get("app_name") or target_info.get("name") or ""
    path = target_info.get("path", "")
    if t_type == "homebrew":
        if target.lower() in ("homebrew", "brew"):
            return "rm -rf /home/linuxbrew/.linuxbrew"
        return f"brew uninstall --zap {target}"
    elif t_type == "uv_tool":
        return f"uv tool uninstall {target}"
    elif t_type == "pip_user":
        return f"pip uninstall -y {target}"
    elif t_type == "cargo_bin":
        return f"rm -f ~/.cargo/bin/{target}"
    elif t_type in ("local_bin", "binary"):
        return f"rm -f {path or ('~/.local/bin/' + target)}"
    elif t_type == "npm_global":
        return f"npm uninstall -g {target}"
    return f"sudo apt-get autoremove --purge -y {target}"


def install_globally(pkg_path: str, status_cb=None) -> Tuple[bool, str]:
    target = os.path.abspath(pkg_path) if os.path.isfile(pkg_path) else pkg_path.strip()
    target_name = os.path.basename(pkg_path)
    if status_cb:
        status_cb(f"Installing {target_name} globally on host...")
    cmd = []
    if shutil.which("pkexec"):
        cmd = ["pkexec", "apt-get", "install", "-y", target]
    elif shutil.which("sudo"):
        cmd = ["sudo", "apt-get", "install", "-y", target]
    else:
        return False, "Neither pkexec nor sudo available for global system installation."

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode == 0:
            try:
                from app_encloser.core.history import record_install_event
                c_name = os.path.splitext(target_name)[0].split("_")[0]
                record_install_event(
                    folder_name="",
                    app_name=c_name.capitalize(),
                    command=" ".join(cmd),
                    install_type="host"
                )
            except Exception:
                pass
            return True, f"Installed {target_name} globally to system."
        return False, f"Global install failed: {proc.stderr.strip()[:100]}"
    except Exception as e:
        return False, str(e)


def install_any_package(pkg_path: str, status_cb=None, scope: Optional[str] = None) -> Tuple[bool, str]:
    if not os.path.isfile(pkg_path) or not is_supported_file(pkg_path):
        return False, "Unsupported package format."

    target_scope = scope or get_setting("install_scope", "isolated")
    if target_scope == "global":
        return install_globally(pkg_path, status_cb)

    base = os.path.basename(pkg_path)
    if "_" in base:
        stem = base.split("_")[0]
    else:
        stem = re.sub(r"[-_](?:amd64|x86_64|i386|all|linux|x64|bin)?$", "", os.path.splitext(base)[0], flags=re.I)
    folder_name = clean_folder_name(stem)

    app_dir = os.path.join(ENCLOSED_DIR, folder_name)
    app_files = os.path.join(app_dir, "app_files")
    userdata = os.path.join(app_dir, "userdata")

    if status_cb:
        status_cb(f"Extracting {base}...")

    os.makedirs(app_files, exist_ok=True)
    os.makedirs(os.path.join(userdata, "home"), exist_ok=True)
    os.makedirs(os.path.join(userdata, "config"), exist_ok=True)
    os.makedirs(os.path.join(userdata, "cache"), exist_ok=True)
    os.makedirs(os.path.join(userdata, "local_share"), exist_ok=True)
    os.makedirs(os.path.join(userdata, "tmp"), exist_ok=True)

    ok, fmt = unpack_archive(pkg_path, app_files)
    if not ok:
        shutil.rmtree(app_dir, ignore_errors=True)
        return False, fmt

    fix_usrmerge_symlinks(app_files)
    install_container_helpers(app_dir)

    with open(os.path.join(app_dir, ".pkg_format"), "w", encoding="utf-8") as f:
        f.write(fmt)

    desk_path, desk_info = find_best_desktop_file(app_files, folder_name)
    orig_exec = desk_info.get("Exec", "")
    if orig_exec:
        orig_exec = re.sub(r" %[a-zA-Z]", "", orig_exec).strip().split()[0]

    rel_exec = resolve_executable(app_files, orig_exec)
    if not rel_exec:
        shutil.rmtree(app_dir, ignore_errors=True)
        return False, f"Could not find an executable binary in {base}"

    with open(os.path.join(app_dir, ".target_exec"), "w", encoding="utf-8") as f:
        f.write(rel_exec)

    display_name = desk_info.get("Name", "").strip() or folder_name
    wm_class = desk_info.get("StartupWMClass", "").strip() or os.path.basename(rel_exec)
    orig_id = os.path.splitext(os.path.basename(desk_path))[0] if desk_path else ""

    with open(os.path.join(app_dir, ".wayland_id"), "w", encoding="utf-8") as f:
        f.write(wm_class)

    from app_encloser.core.container import set_enclosing_level
    default_strict = get_setting("strict_sandbox_by_default", True)
    set_enclosing_level(folder_name, "strict" if default_strict else "standard")

    write_launch_script(app_dir, rel_exec, fmt)
    desktop_icon = desk_info.get("Icon")
    icon_path = extract_or_generate_icon(app_dir, folder_name, desktop_icon)
    update_desktop_files_for_app(app_dir, folder_name, display_name, wm_class, icon_path, orig_id)

    invalidate_dir_size_cache(app_dir)
    return True, f"{display_name} successfully enclosed in ~/EnclosedApps/{folder_name}"


def detect_command_or_script(text: str) -> bool:
    s = text.strip()
    if "\n" in s or "|" in s or "&&" in s or ";" in s or ">" in s or "<" in s:
        return True
    if s.startswith("#") or s.startswith("sudo ") or s.startswith("curl ") or s.startswith("wget "):
        return True
    tokens = s.split()
    if not tokens:
        return False
    first = tokens[0].lower()
    if first in ("curl", "wget", "bash", "sh", "python", "python3", "uv", "pip", "pip3", "cargo", "npm", "git", "source", "echo", "export"):
        return True
    if len(tokens) > 1 and any(t.startswith("-") for t in tokens[1:]):
        return True
    return False


def install_from_url_or_repo(target: str, status_cb=None, scope: Optional[str] = None) -> Tuple[bool, str]:
    if target.startswith(("http://", "https://")):
        if status_cb:
            status_cb(f"Downloading from {target}...")
        parsed_fn = os.path.basename(target.split("?")[0])
        if not parsed_fn or "." not in parsed_fn:
            parsed_fn = "downloaded_package.deb"
        dl_path = os.path.join(CACHE_DIR, parsed_fn)
        try:
            from app_encloser import __version__
            req = urllib.request.Request(target, headers={"User-Agent": f"AppEncloser/{__version__}"})
            with urllib.request.urlopen(req) as resp, open(dl_path, "wb") as out_f:
                shutil.copyfileobj(resp, out_f)
            return install_any_package(dl_path, status_cb, scope=scope)
        except Exception as e:
            return False, f"Download failed: {e}"

    if detect_command_or_script(target):
        PREREQ_PKGS = {"curl", "wget", "gpg", "gnupg", "apt-transport-https", "ca-certificates", "software-properties-common", "lsb-release"}
        cname = "Custom-App"
        found_pkg = None
        lines = [l.strip() for l in target.splitlines() if l.strip() and not l.strip().startswith("#")]

        for line in reversed(lines):
            words = line.split()
            if len(words) >= 3 and words[0] in ("uv", "pip", "pip3") and words[1] in ("tool", "install"):
                found_pkg = words[-1]
                cname = clean_folder_name(found_pkg.title())
                break
            if len(words) >= 2 and words[0] in ("cargo", "npm", "gem", "go") and words[1] == "install":
                found_pkg = words[-1]
                cname = clean_folder_name(found_pkg.title())
                break
            if "install" in words:
                idx = words.index("install")
                for w in words[idx + 1:]:
                    if not w.startswith("-") and w.lower() not in PREREQ_PKGS:
                        found_pkg = w
                        cname = clean_folder_name(w.title())
                        break
                if found_pkg:
                    break

        inferred_from_repo = None
        if not found_pkg:
            matches = re.findall(r'[\w\-\.]+\.(?:sources|list|gpg)', target)
            for m in matches:
                base = os.path.basename(m)
                base = re.sub(r'\.(?:sources|list|gpg)$', '', base, flags=re.IGNORECASE)
                for sfx in ("-release", "-archive-keyring", "-archive", "-keyring", "-apt"):
                    if base.endswith(sfx):
                        base = base[:-len(sfx)]
                base = base.strip(".-_")
                if base and base.lower() not in PREREQ_PKGS:
                    inferred_from_repo = base
                    break

            if inferred_from_repo:
                found_pkg = inferred_from_repo
                cname = clean_folder_name(found_pkg.title())
                target = target.rstrip() + f"\nsudo apt-get install -y {found_pkg}\n"

        if cname == "Custom-App":
            for line in lines:
                first_w = line.split()[0]
                if first_w.lower() not in ("sudo", "export", "echo", "set", "cd"):
                    cname = clean_folder_name(first_w.title())
                    break

        from app_encloser.core.container import create_empty_container, is_bwrap_supported
        app_dir = os.path.join(ENCLOSED_DIR, cname)
        was_created = False
        target_strict = False
        if scope == "strict" or (scope != "standard" and scope != "integrated" and get_setting("strict_sandbox_by_default", True) and is_bwrap_supported()):
            target_strict = True
        if not os.path.isdir(app_dir):
            ok, msg = create_empty_container(cname, strict=target_strict)
            if not ok:
                return False, f"Failed to create container for script: {msg}"
            was_created = True
        ok_i, msg_i = install_into_container(cname, target, status_cb, scope=scope)
        if ok_i:
            from app_encloser.core.history import record_install_event
            record_install_event(cname, cname, target, "command_script")
        else:
            if was_created:
                uninstall_enclosed_app(cname)
        return ok_i, msg_i

    pkg_name = target.strip()
    if any(prefix in pkg_name for prefix in ("apt install", "apt-get install")):
        parts = pkg_name.split()
        idx = parts.index("install")
        pkg_name = parts[idx + 1] if len(parts) > idx + 1 else ""

    if not pkg_name:
        return False, "No valid package specified."

    target_scope = scope or get_setting("install_scope", "isolated")
    if target_scope == "global":
        return install_globally(pkg_name, status_cb)

    if status_cb:
        status_cb(f"Downloading {pkg_name} via APT...")

    pkg_cache = os.path.join(CACHE_DIR, "apt_downloads")
    os.makedirs(pkg_cache, exist_ok=True)
    res = subprocess.run(["apt-get", "download", pkg_name], cwd=pkg_cache, capture_output=True, text=True)
    if res.returncode != 0:
        return False, f"Failed to download package '{pkg_name}' via APT: {res.stderr.strip()[:100]}"

    deb_files = [f for f in os.listdir(pkg_cache) if f.endswith(".deb") and pkg_name in f]
    if not deb_files:
        deb_files = [f for f in os.listdir(pkg_cache) if f.endswith(".deb")]
    if not deb_files:
        return False, f"No .deb downloaded for {pkg_name}"

    deb_files.sort(key=lambda fn: os.path.getmtime(os.path.join(pkg_cache, fn)), reverse=True)
    target_deb = os.path.join(pkg_cache, deb_files[0])
    return install_any_package(target_deb, status_cb, scope=scope)


def install_into_container(folder_name: str, pkg_or_url_or_file: str, status_cb=None, scope: Optional[str] = None) -> Tuple[bool, str]:
    app_dir = os.path.join(ENCLOSED_DIR, folder_name)
    if not os.path.isdir(app_dir):
        return False, f"Container '{folder_name}' does not exist."

    app_files = os.path.join(app_dir, "app_files")
    userdata = os.path.join(app_dir, "userdata")
    os.makedirs(app_files, exist_ok=True)
    os.makedirs(os.path.join(userdata, "home"), exist_ok=True)
    os.makedirs(os.path.join(userdata, "config"), exist_ok=True)
    os.makedirs(os.path.join(userdata, "cache"), exist_ok=True)
    os.makedirs(os.path.join(userdata, "local_share"), exist_ok=True)
    os.makedirs(os.path.join(userdata, "tmp"), exist_ok=True)

    target = pkg_or_url_or_file.strip()
    target_deb = None

    if target.startswith(("http://", "https://")):
        if status_cb:
            status_cb(f"Downloading {target}...")
        parsed_fn = os.path.basename(target.split("?")[0]) or "downloaded_package.deb"
        dl_path = os.path.join(CACHE_DIR, parsed_fn)
        try:
            from app_encloser import __version__
            req = urllib.request.Request(target, headers={"User-Agent": f"AppEncloser/{__version__}"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(dl_path, "wb") as out_f:
                shutil.copyfileobj(resp, out_f)
            target_deb = dl_path
        except Exception as e:
            return False, f"Download failed: {e}"
    elif os.path.isfile(target):
        target_deb = os.path.abspath(target)
    elif detect_command_or_script(target):
        install_container_helpers(app_dir)
        os.makedirs(os.path.join(userdata, "bin"), exist_ok=True)
        os.makedirs(os.path.join(userdata, "home", ".local", "bin"), exist_ok=True)
        script_file = os.path.join(userdata, "tmp", "container_install.sh")
        with open(script_file, "w", encoding="utf-8") as f:
            f.write("#!/usr/bin/env bash\n")
            f.write('export PATH="$HERE/userdata/bin:$HERE/userdata/home/.local/bin:$HERE/userdata/home/.cargo/bin:$HERE/app_files/usr/bin:$HERE/app_files/bin:$PATH"\n')
            f.write(target + "\n")
        os.chmod(script_file, 0o755)

        if status_cb:
            status_cb(f"Executing script inside container '{folder_name}'...")

        rc = run_in_container(folder_name, ["/bin/bash", script_file])
        post_exec = None
        user_bin = os.path.join(userdata, "bin")
        user_local_bin = os.path.join(userdata, "home", ".local", "bin")

        for cand_dir in (user_bin, user_local_bin):
            if os.path.isdir(cand_dir):
                target_cand = os.path.join(cand_dir, folder_name.lower())
                if os.path.isfile(target_cand) and os.access(target_cand, os.X_OK):
                    post_exec = os.path.relpath(target_cand, app_dir)
                    break
                for fn in sorted(os.listdir(cand_dir)):
                    fp = os.path.join(cand_dir, fn)
                    if os.path.isfile(fp) and os.access(fp, os.X_OK) and not fn.endswith((".sh", ".env")):
                        post_exec = os.path.relpath(fp, app_dir)
                        break
            if post_exec:
                break

        if not post_exec:
            desk_path, desk_info = find_best_desktop_file(app_files, folder_name)
            d_exec = desk_info.get("Exec", "")
            if d_exec:
                d_exec = re.sub(r" %[a-zA-Z]", "", d_exec).strip().split()[0]
                post_exec = resolve_executable(app_files, d_exec)
        if not post_exec:
            cand_files = resolve_executable(app_files, folder_name.lower())
            if cand_files:
                post_exec = cand_files
        if not post_exec:
            post_exec = resolve_executable(app_files, "")

        from app_encloser.core.container import set_enclosing_level
        if scope:
            set_enclosing_level(folder_name, scope)
        elif not os.path.isfile(os.path.join(app_dir, ".enclosing_level")):
            default_strict = get_setting("strict_sandbox_by_default", True)
            set_enclosing_level(folder_name, "strict" if default_strict else "standard")

        if post_exec:
            with open(os.path.join(app_dir, ".target_exec"), "w", encoding="utf-8") as f:
                f.write(post_exec)
            repair_app(folder_name)
            return True, f"Successfully executed commands and configured '{folder_name}' ({post_exec})."

        if rc == 0:
            repair_app(folder_name)
            return True, f"Commands executed successfully in '{folder_name}'."
        return False, f"Script execution in '{folder_name}' exited with code {rc}."
    else:
        pkg_name = target
        if any(prefix in pkg_name for prefix in ("apt install", "apt-get install")):
            parts = pkg_name.split()
            idx = parts.index("install")
            pkg_name = parts[idx + 1] if len(parts) > idx + 1 else ""

        if not pkg_name:
            return False, "No valid package specified."

        if status_cb:
            status_cb(f"Resolving {pkg_name}...")

        pkg_cache = os.path.join(CACHE_DIR, "apt_downloads")
        os.makedirs(pkg_cache, exist_ok=True)

        res = subprocess.run(["apt-get", "download", pkg_name], cwd=pkg_cache, capture_output=True, text=True)
        if res.returncode != 0:
            return False, f"Failed to download package '{pkg_name}' via APT: {res.stderr.strip()[:100]}"
        deb_files = [f for f in os.listdir(pkg_cache) if f.endswith(".deb") and pkg_name in f]
        if not deb_files:
            deb_files = [f for f in os.listdir(pkg_cache) if f.endswith(".deb")]
        if not deb_files:
            return False, f"No .deb downloaded for {pkg_name}"
        deb_files.sort(key=lambda fn: os.path.getmtime(os.path.join(pkg_cache, fn)), reverse=True)
        target_deb = os.path.join(pkg_cache, deb_files[0])

    if not target_deb or not os.path.isfile(target_deb):
        return False, "Package file not found."

    if status_cb:
        status_cb(f"Extracting {os.path.basename(target_deb)} into container '{folder_name}'...")

    ok, fmt = unpack_archive(target_deb, app_files)
    if not ok:
        return False, f"Extraction failed: {fmt}"

    fix_usrmerge_symlinks(app_files)

    with open(os.path.join(app_dir, ".pkg_format"), "w", encoding="utf-8") as f:
        f.write(fmt)

    desk_path, desk_info = find_best_desktop_file(app_files, folder_name)
    orig_exec = desk_info.get("Exec", "")
    if orig_exec:
        orig_exec = re.sub(r" %[a-zA-Z]", "", orig_exec).strip().split()[0]

    rel_exec = resolve_executable(app_files, orig_exec)
    if not rel_exec:
        rel_exec = resolve_executable(app_files, "")

    if rel_exec:
        with open(os.path.join(app_dir, ".target_exec"), "w", encoding="utf-8") as f:
            f.write(rel_exec)

    display_name = desk_info.get("Name", "").strip() or folder_name
    wm_class = desk_info.get("StartupWMClass", "").strip() or (os.path.basename(rel_exec) if rel_exec else folder_name)
    orig_id = os.path.splitext(os.path.basename(desk_path))[0] if desk_path else ""

    with open(os.path.join(app_dir, ".wayland_id"), "w", encoding="utf-8") as f:
        f.write(wm_class)

    write_launch_script(app_dir, rel_exec or f"usr/bin/{folder_name.lower()}", fmt)
    desktop_icon = desk_info.get("Icon")
    icon_path = extract_or_generate_icon(app_dir, folder_name, desktop_icon)
    update_desktop_files_for_app(app_dir, folder_name, display_name, wm_class, icon_path, orig_id)
    install_container_helpers(app_dir)
    from app_encloser.core.history import record_install_event
    record_install_event(display_name, folder_name, f"Package file: {os.path.basename(target_deb)}", "package_file")

    invalidate_dir_size_cache(app_dir)
    return True, f"Successfully installed {display_name} into container '{folder_name}'"


def migrate_host_to_isolated(app_dict: Dict[str, Any], status_cb=None) -> Tuple[bool, str]:
    from app_encloser.core.container import create_empty_container, run_in_container
    from app_encloser.core.history import invalidate_host_discovery_cache

    app_name = app_dict.get("name") or app_dict.get("app_name") or ""
    if not app_name:
        return False, "No application name provided for migration."

    h_info = app_dict.get("host_info", {})
    t_type = h_info.get("type") or app_dict.get("install_type", "apt_package")
    cname = clean_folder_name(app_name.title() if len(app_name) <= 20 else app_name[:20].title())

    if status_cb:
        status_cb(f"Creating isolated container '{cname}'...")

    strict_sbox = (t_type == "apt_package")
    ok, msg = create_empty_container(cname, strict=strict_sbox)
    if not ok:
        return False, f"Failed to create container: {msg}"

    app_dir = os.path.join(ENCLOSED_DIR, cname)

    if t_type == "apt_package":
        if status_cb:
            status_cb(f"Installing '{app_name}' inside isolated container...")
        ok_i, msg_i = install_into_container(cname, app_name, status_cb)
        if not ok_i:
            uninstall_enclosed_app(cname)
            return False, f"Failed to isolate {app_name}: {msg_i}"

    elif t_type == "ollama_host":
        if status_cb:
            status_cb("Moving Ollama binary and models into container...")
        user_bin = os.path.join(app_dir, "userdata", "bin")
        os.makedirs(user_bin, exist_ok=True)
        dest_bin = os.path.join(user_bin, "ollama")
        host_bin = h_info.get("path") or shutil.which("ollama") or "/usr/local/bin/ollama"
        if os.path.isfile(host_bin):
            shutil.copyfile(host_bin, dest_bin)
            os.chmod(dest_bin, 0o755)
        ollama_home = os.path.expanduser("~/.ollama")
        if os.path.isdir(ollama_home):
            dest_home = os.path.join(app_dir, "userdata", "home", ".ollama")
            os.makedirs(os.path.dirname(dest_home), exist_ok=True)
            if not os.path.isdir(dest_home):
                shutil.copytree(ollama_home, dest_home, dirs_exist_ok=True)
        with open(os.path.join(app_dir, ".target_exec"), "w", encoding="utf-8") as f:
            f.write("userdata/bin/ollama")

    elif t_type == "claude_cli":
        if status_cb:
            status_cb("Isolating Claude Code CLI into container...")
        npm_prefix = os.path.join(app_dir, "userdata", "home", ".npm-global")
        os.makedirs(npm_prefix, exist_ok=True)
        if shutil.which("npm"):
            env = os.environ.copy()
            env["NPM_CONFIG_PREFIX"] = npm_prefix
            subprocess.run(["npm", "install", "-g", "@anthropic-ai/claude-code"], env=env, capture_output=True, text=True)
        claude_home = os.path.expanduser("~/.claude")
        if os.path.isdir(claude_home):
            dest_chome = os.path.join(app_dir, "userdata", "home", ".claude")
            os.makedirs(os.path.dirname(dest_chome), exist_ok=True)
            if not os.path.isdir(dest_chome):
                shutil.copytree(claude_home, dest_chome, dirs_exist_ok=True)
        cfg_f = os.path.expanduser("~/.claude.json")
        if os.path.isfile(cfg_f):
            dest_cfg = os.path.join(app_dir, "userdata", "home", ".claude.json")
            try:
                shutil.copyfile(cfg_f, dest_cfg)
            except Exception:
                pass
        with open(os.path.join(app_dir, ".target_exec"), "w", encoding="utf-8") as f:
            f.write("userdata/home/.npm-global/bin/claude")

    elif t_type in ("uv_tool", "local_bin", "cargo_bin", "binary"):
        if status_cb:
            status_cb(f"Copying {app_name} into container...")
        user_bin = os.path.join(app_dir, "userdata", "bin")
        os.makedirs(user_bin, exist_ok=True)
        dest_bin = os.path.join(user_bin, app_name)
        host_bin = h_info.get("path")
        if not host_bin:
            host_bin = os.path.join(LOCAL_BIN, app_name) if t_type != "cargo_bin" else os.path.join(REAL_HOME, ".cargo", "bin", app_name)
        if os.path.isfile(host_bin):
            shutil.copyfile(host_bin, dest_bin)
            os.chmod(dest_bin, 0o755)
        with open(os.path.join(app_dir, ".target_exec"), "w", encoding="utf-8") as f:
            f.write(f"userdata/bin/{app_name}")

    elif t_type == "homebrew":
        if status_cb:
            status_cb(f"Installing {app_name} inside container Homebrew...")
        run_in_container(cname, ["encloser-brew", "install", app_name])

    repair_app(cname)
    from app_encloser.core.history import record_install_event
    record_install_event(cname, cname, f"migrated from host: {app_name}", "container")

    if status_cb:
        status_cb(f"Purging {app_name} from host system...")
    uninstall_host_package(app_dict, status_cb)
    invalidate_host_discovery_cache()

    if status_cb:
        status_cb(f"Successfully migrated '{app_name}' to isolated container '{cname}'.")
    return True, f"Successfully migrated '{app_name}' to isolated container '{cname}'."


def migrate_isolated_to_host(folder_name: str, status_cb=None) -> Tuple[bool, str]:
    from app_encloser.core.history import invalidate_host_discovery_cache
    app_dir = os.path.join(ENCLOSED_DIR, folder_name)
    if not os.path.isdir(app_dir):
        return False, f"Container '{folder_name}' does not exist."

    pkg_name = folder_name.lower()
    c_file = os.path.join(app_dir, ".install_cmd")
    if os.path.isfile(c_file):
        try:
            with open(c_file, "r", encoding="utf-8") as f_cmd_c:
                cmd_c = f_cmd_c.read().strip()
            if "install" in cmd_c:
                parts = cmd_c.split()
                idx = parts.index("install")
                if len(parts) > idx + 1:
                    cand = parts[idx + 1]
                    if not cand.startswith("-"):
                        pkg_name = cand
        except Exception:
            pass

    if status_cb:
        status_cb(f"Installing '{pkg_name}' globally onto host system...")
    ok, msg = install_globally(pkg_name, status_cb)
    if not ok:
        return False, f"Failed to install package on host: {msg}"

    if status_cb:
        status_cb(f"Removing isolated container '{folder_name}'...")
    uninstall_enclosed_app(folder_name)
    invalidate_host_discovery_cache()

    if status_cb:
        status_cb(f"Successfully migrated container '{folder_name}' to global host system.")
    return True, f"Successfully migrated container '{folder_name}' to global host system."

