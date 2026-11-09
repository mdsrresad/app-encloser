import os
import re
import shutil
import subprocess
from typing import Dict, Tuple, Optional

from app_encloser.core.config import APPS_DIR, ENCLOSED_DIR, ICONS_DIR, LOCAL_BIN


def parse_desktop_file(path: str) -> Dict[str, str]:
    info = {}
    in_entry = False
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("["):
                    in_entry = (line == "[Desktop Entry]")
                    continue
                if in_entry and "=" in line:
                    k, v = line.split("=", 1)
                    info[k.strip()] = v.strip()
    except Exception:
        pass
    return info


def find_best_desktop_file(app_files: str, package_name: str = "") -> Tuple[str, Dict[str, str]]:
    candidates = []
    if os.path.isdir(app_files):
        for root, _, files in os.walk(app_files):
            for f in files:
                if f.endswith(".desktop"):
                    candidates.append(os.path.join(root, f))

    if not candidates:
        return "", {}

    scored = []
    for p in candidates:
        base = os.path.basename(p)
        low_b = base.lower()
        score = 100

        if any(h in low_b for h in ("-url-handler", "urlhandler", "url_handler", "scheme-handler")):
            score -= 1000

        info = parse_desktop_file(p)
        if info.get("NoDisplay", "").lower() == "true":
            score -= 600

        name = info.get("Name", "")
        if "url handler" in name.lower():
            score -= 1000

        if package_name and package_name.lower() in low_b:
            score += 150

        cats = info.get("Categories", "")
        if any(c in cats for c in ("Development", "Utility", "Network", "Graphics", "Office")):
            score += 50

        scored.append((score, p, info))

    scored.sort(key=lambda s: s[0], reverse=True)
    best_score, best_path, best_info = scored[0]
    return best_path, best_info


def update_desktop_files_for_app(app_dir: str, folder_name: str, display_name: str, wm_class: str, icon_path: str, orig_id: str = ""):
    display_name = display_name.replace("\r", "").replace("\n", "").strip() or folder_name
    wm_class = wm_class.replace("\r", "").replace("\n", "").strip() or folder_name
    icon_path = icon_path.replace("\r", "").replace("\n", "").strip()

    desk_file = os.path.join(app_dir, f"{folder_name}.desktop")
    launch_sh = os.path.join(app_dir, "launch.sh")

    app_files_dir = os.path.join(app_dir, "app_files")
    _, desk_info = find_best_desktop_file(app_files_dir, folder_name)
    cats = desk_info.get("Categories", "Utility;Application;")
    orig_exec = desk_info.get("Exec", "")
    arg = "%F" if "%F" in orig_exec else ("%f" if "%f" in orig_exec else "%U")

    desk_content = (
        f"[Desktop Entry]\n"
        f"Version=1.0\n"
        f"Name={display_name}\n"
        f"Exec={launch_sh} {arg}\n"
        f"StartupNotify=true\n"
        f"Terminal=false\n"
        f"Icon={icon_path}\n"
        f"Type=Application\n"
        f"Categories={cats}\n"
        f"StartupWMClass={wm_class}\n"
    )
    with open(desk_file, "w", encoding="utf-8") as f:
        f.write(desk_content)

    main_link = os.path.join(APPS_DIR, f"{folder_name}.desktop")
    if os.path.lexists(main_link):
        os.remove(main_link)
    os.symlink(desk_file, main_link)

    if os.path.isdir(APPS_DIR):
        for fn in os.listdir(APPS_DIR):
            if fn in (f"{folder_name}.desktop", "AppEncloser.desktop", "io.ubuntu.AppEncloser.desktop"):
                continue
            fp = os.path.join(APPS_DIR, fn)
            if os.path.isfile(fp) and not os.path.islink(fp):
                try:
                    with open(fp, "r", errors="ignore") as f:
                        c = f.read()
                        if f"/EnclosedApps/{folder_name}/" in c and "NoDisplay=true" in c:
                            os.remove(fp)
                except Exception:
                    pass


def ensure_clean_desktop_environment():
    sys_legacy = "/usr/share/applications/AppEncloser.desktop"
    user_legacy = os.path.join(APPS_DIR, "AppEncloser.desktop")
    if os.path.isfile(sys_legacy):
        with open(user_legacy, "w", encoding="utf-8") as f:
            legacy_exec = os.path.join(LOCAL_BIN, "app-encloser")
            f.write(f"[Desktop Entry]\nVersion=1.0\nName=App Encloser (Legacy)\nExec={legacy_exec} %f\nIcon=app-encloser\nTerminal=false\nType=Application\nNoDisplay=true\n")

    if os.path.isdir(APPS_DIR):
        for fn in os.listdir(APPS_DIR):
            fp = os.path.join(APPS_DIR, fn)
            if os.path.islink(fp) and not os.path.exists(fp):
                try:
                    target = os.readlink(fp)
                    if ENCLOSED_DIR in target or "/EnclosedApps/" in target:
                        os.remove(fp)
                except Exception:
                    pass

    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", APPS_DIR], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
