import os
import sys
import shutil
import subprocess
from typing import Tuple

from app_encloser.core.config import (
    ENCLOSED_DIR, APPS_DIR, LOCAL_BIN, REAL_HOME
)
from app_encloser.core.lifecycle import uninstall_enclosed_app


def self_uninstall(purge_apps: bool = True) -> Tuple[bool, str]:
    try:
        from app_encloser.core.terminal_guard import disable_terminal_guard
        disable_terminal_guard()
    except Exception:
        pass

    for rc_name in (".bashrc", ".zshrc"):
        rc_path = os.path.join(REAL_HOME, rc_name)
        if os.path.isfile(rc_path):
            try:
                with open(rc_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [ln for ln in f if "shell_guard.sh" not in ln]
                with open(rc_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
            except Exception:
                pass

    if purge_apps and os.path.isdir(ENCLOSED_DIR):
        app_folders = [
            f for f in os.listdir(ENCLOSED_DIR)
            if os.path.isdir(os.path.join(ENCLOSED_DIR, f)) and not f.startswith(".")
        ]
        for f in app_folders:
            try:
                uninstall_enclosed_app(f)
            except Exception:
                pass

        if os.path.isdir(APPS_DIR):
            for fn in os.listdir(APPS_DIR):
                fp = os.path.join(APPS_DIR, fn)
                remove_it = False
                if os.path.islink(fp):
                    try:
                        raw_link = os.readlink(fp)
                        if "/EnclosedApps/" in raw_link or "app-encloser" in raw_link or "app.encloser" in raw_link or fn.startswith("app.encloser."):
                            remove_it = True
                    except Exception:
                        pass
                elif os.path.isfile(fp):
                    try:
                        with open(fp, "r", errors="ignore") as file_obj:
                            content = file_obj.read()
                            if "/EnclosedApps/" in content:
                                remove_it = True
                    except Exception:
                        pass
                if remove_it:
                    try:
                        os.remove(fp)
                    except Exception:
                        pass

        try:
            shutil.rmtree(ENCLOSED_DIR, ignore_errors=True)
        except Exception:
            pass
        if os.path.isdir(ENCLOSED_DIR):
            subprocess.run(["rm", "-rf", ENCLOSED_DIR], stderr=subprocess.DEVNULL)

    cur_py = f"python{sys.version_info.major}.{sys.version_info.minor}"
    targets_to_remove = [
        os.path.join(LOCAL_BIN, "app-encloser"),
        os.path.join(APPS_DIR, "io.ubuntu.AppEncloser.desktop"),
        os.path.join(APPS_DIR, "app.encloser.desktop"),
        os.path.join(APPS_DIR, "AppEncloser.desktop"),
        os.path.join(REAL_HOME, ".local", "lib", cur_py, "site-packages", "app_encloser"),
        os.path.join(REAL_HOME, ".config", "app-encloser"),
        os.path.join(REAL_HOME, ".cache", "app-encloser"),
    ]

    py_lib_base = os.path.join(REAL_HOME, ".local", "lib")
    if os.path.isdir(py_lib_base):
        for entry in os.listdir(py_lib_base):
            if entry.startswith("python3."):
                targets_to_remove.append(os.path.join(py_lib_base, entry, "site-packages", "app_encloser"))

    for t in targets_to_remove:
        try:
            if os.path.islink(t) or os.path.isfile(t):
                os.remove(t)
            elif os.path.isdir(t):
                shutil.rmtree(t, ignore_errors=True)
        except Exception:
            pass

    sys_desktop = "/usr/share/applications/AppEncloser.desktop"
    local_desktop = os.path.join(APPS_DIR, "AppEncloser.desktop")
    if os.path.isfile(sys_desktop) and not os.access(sys_desktop, os.W_OK):
        try:
            with open(local_desktop, "w", encoding="utf-8") as f:
                f.write("[Desktop Entry]\nType=Application\nName=App Encloser\nNoDisplay=true\n")
        except Exception:
            pass
    else:
        if os.path.isfile(local_desktop):
            try:
                os.remove(local_desktop)
            except Exception:
                pass

    icons_dir = os.path.join(REAL_HOME, ".local", "share", "icons")
    if os.path.isdir(icons_dir):
        for root, _, files in os.walk(icons_dir):
            for f in files:
                low_f = f.lower()
                if "app-encloser" in low_f or "appencloser" in low_f:
                    try:
                        os.remove(os.path.join(root, f))
                    except Exception:
                        pass

    for sys_target in ("/usr/bin/app-encloser", "/usr/share/applications/AppEncloser.desktop"):
        if os.path.isfile(sys_target) and os.access(sys_target, os.W_OK):
            try:
                os.remove(sys_target)
            except Exception:
                pass

    try:
        subprocess.run(["update-desktop-database", APPS_DIR], capture_output=True, timeout=5)
    except Exception:
        pass

    try:
        subprocess.run(
            ["gtk-update-icon-cache", "-f", os.path.join(REAL_HOME, ".local", "share", "icons", "hicolor")],
            capture_output=True, timeout=5
        )
    except Exception:
        pass

    is_dpkg_pkg = False
    try:
        chk = subprocess.run(["dpkg", "-s", "app-encloser"], capture_output=True, text=True)
        if chk.returncode == 0 and "Status: install ok installed" in chk.stdout:
            is_dpkg_pkg = True
    except Exception:
        pass

    if is_dpkg_pkg:
        has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        purged = False
        if os.environ.get("APP_ENCLOSER_TEST_MODE") == "1":
            purged = False
        elif shutil.which("pkexec") and has_display:
            try:
                res = subprocess.run(["pkexec", "dpkg", "--purge", "app-encloser"], capture_output=True)
                purged = (res.returncode == 0)
            except Exception:
                pass
        elif os.getuid() == 0:
            try:
                res = subprocess.run(["dpkg", "--purge", "app-encloser"], capture_output=True)
                purged = (res.returncode == 0)
            except Exception:
                pass
        if not purged:
            return True, "App Encloser uninstalled. Note: Debian package registration remains in system database. Run 'sudo dpkg -P app-encloser' to purge it completely."

    return True, "App Encloser and enclosed applications have been completely uninstalled."
