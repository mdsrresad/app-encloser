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
                        tgt = os.path.realpath(fp)
                        if "/EnclosedApps/" in tgt or not os.path.exists(tgt):
                            remove_it = True
                    except Exception:
                        remove_it = True
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
        os.path.join(REAL_HOME, ".local", "lib", cur_py, "site-packages", "usercustomize.py"),
        os.path.join(REAL_HOME, ".config", "app-encloser"),
        os.path.join(REAL_HOME, ".cache", "app-encloser"),
    ]

    py_lib_base = os.path.join(REAL_HOME, ".local", "lib")
    if os.path.isdir(py_lib_base):
        for entry in os.listdir(py_lib_base):
            if entry.startswith("python3."):
                targets_to_remove.append(os.path.join(py_lib_base, entry, "site-packages", "app_encloser"))
                targets_to_remove.append(os.path.join(py_lib_base, entry, "site-packages", "usercustomize.py"))

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

    return True, "App Encloser and enclosed applications have been completely uninstalled."
