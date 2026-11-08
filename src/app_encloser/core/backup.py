import os
import shutil
import tarfile
import subprocess
from typing import Dict, List, Tuple

from app_encloser.core.config import ENCLOSED_DIR, APPS_DIR, ICONS_DIR, invalidate_dir_size_cache
from app_encloser.core.lifecycle import repair_app


def export_selective(dest_tar: str, selections: Dict[str, Dict[str, bool]]) -> Tuple[bool, str]:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(dest_tar)), exist_ok=True)
        with tarfile.open(dest_tar, "w:gz") as tf:
            for folder, opts in selections.items():
                app_dir = os.path.join(ENCLOSED_DIR, folder)
                if not os.path.isdir(app_dir):
                    continue

                for fn in os.listdir(app_dir):
                    fp = os.path.join(app_dir, fn)
                    arc_p = f"{folder}/{fn}"
                    if fn == "app_files" and not opts.get("app_files", True):
                        continue
                    if fn == "userdata" and not opts.get("userdata", True):
                        continue
                    tf.add(fp, arcname=arc_p)

        sz = os.path.getsize(dest_tar)
        return True, f"Exported {len(selections)} app(s) to {os.path.basename(dest_tar)} ({sz // 1024} KB)"
    except Exception as e:
        return False, str(e)


def batch_export(selections: Dict[str, Dict[str, bool]], dest_tar: str) -> Tuple[bool, str]:
    return export_selective(dest_tar, selections)


def export_all_apps(dest_tar: str, include_bins: bool = True, include_userdata: bool = True) -> Tuple[bool, str]:
    if not os.path.isdir(ENCLOSED_DIR):
        return False, "No enclosed applications found to export."
    folders = [f for f in os.listdir(ENCLOSED_DIR) if os.path.isdir(os.path.join(ENCLOSED_DIR, f)) and not f.startswith(".")]
    if not folders:
        return False, "No applications currently installed."
    selections = {f: {"app_files": include_bins, "userdata": include_userdata} for f in folders}
    return export_selective(dest_tar, selections)


def inspect_backup_archive(tar_path: str) -> Dict[str, List[str]]:
    found = {}
    try:
        with tarfile.open(tar_path, "r:*") as tf:
            for member in tf.getmembers():
                parts = member.name.strip("/").split("/")
                if parts and parts[0]:
                    top = parts[0]
                    sub = parts[1] if len(parts) > 1 else ""
                    if top not in found:
                        found[top] = set()
                    if sub in ("app_files", "userdata"):
                        found[top].add(sub)
        return {k: sorted(list(v)) for k, v in found.items()}
    except Exception:
        return {}


def import_selective(tar_path: str, selections: Dict[str, Dict[str, bool]]) -> Tuple[bool, str]:
    try:
        with tarfile.open(tar_path, "r:*") as tf:
            for member in tf.getmembers():
                parts = member.name.strip("/").split("/")
                if not parts or parts[0] not in selections:
                    continue
                top = parts[0]
                if len(parts) > 1:
                    if parts[1] == "app_files" and not selections[top].get("app_files", True):
                        continue
                    if parts[1] == "userdata" and not selections[top].get("userdata", True):
                        continue

                dest_p = os.path.abspath(os.path.join(ENCLOSED_DIR, member.name))
                if not dest_p.startswith(os.path.abspath(ENCLOSED_DIR) + os.sep) and dest_p != os.path.abspath(ENCLOSED_DIR):
                    continue

                if hasattr(tarfile, "data_filter"):
                    tf.extract(member, ENCLOSED_DIR, filter="data")
                else:
                    tf.extract(member, ENCLOSED_DIR)

        invalidate_dir_size_cache()

        for folder in selections:
            repair_app(folder)

        if shutil.which("update-desktop-database"):
            subprocess.run(["update-desktop-database", APPS_DIR], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        if shutil.which("gtk-update-icon-cache"):
            subprocess.run(["gtk-update-icon-cache", "-q", "-t", "-f", ICONS_DIR], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

        return True, "Backup successfully restored."
    except Exception as e:
        return False, str(e)
