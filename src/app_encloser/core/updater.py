import os
import sys
import json
import urllib.request
import subprocess
import shutil
from typing import Tuple, Optional, Dict, Any

from app_encloser import __version__

GITHUB_REPO = "mdsrresad/app-encloser"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def parse_version_tuple(v_str: str) -> Tuple[int, ...]:
    clean = v_str.lstrip("v").strip()
    parts = []
    for p in clean.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts) or (0,)


def check_for_updates() -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    try:
        req = urllib.request.Request(
            API_URL,
            headers={
                "User-Agent": f"AppEncloser/{__version__} (Linux)",
                "Accept": "application/vnd.github.v3+json"
            }
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status != 200:
                return False, None, None
            data = json.loads(resp.read().decode("utf-8"))

        raw_tag = data.get("tag_name", "")
        remote_ver_str = raw_tag.lstrip("v").strip()
        if not remote_ver_str:
            return False, None, None

        current_tup = parse_version_tuple(__version__)
        remote_tup = parse_version_tuple(remote_ver_str)

        assets = data.get("assets", [])
        deb_url = None
        deb_name = None
        tar_url = None
        tar_name = None

        for a in assets:
            name = a.get("name", "")
            download_url = a.get("browser_download_url", "")
            if name.endswith(".deb"):
                deb_url = download_url
                deb_name = name
            elif name.endswith(".tar.gz") and "universal" in name:
                tar_url = download_url
                tar_name = name

        details = {
            "tag_name": raw_tag,
            "version": remote_ver_str,
            "release_name": data.get("name") or raw_tag,
            "html_url": data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases"),
            "body": data.get("body", ""),
            "deb_url": deb_url,
            "deb_name": deb_name,
            "tar_url": tar_url,
            "tar_name": tar_name,
            "published_at": data.get("published_at", "")
        }

        has_update = remote_tup > current_tup
        return has_update, remote_ver_str, details
    except Exception:
        return False, None, None


def perform_cli_update(download_only: bool = False) -> Tuple[bool, str]:
    print(f"[*] Checking for updates (current version: v{__version__})...")
    has_update, new_ver, details = check_for_updates()
    if not details:
        return False, "Could not check for updates. Please check your internet connection or try again later."

    if not has_update:
        return True, f"App Encloser is already up to date (v{__version__})."

    print(f"[!] New version available: v{new_ver} (Current: v{__version__})")
    print(f"    Release: {details.get('release_name', new_ver)}")
    print(f"    Release Notes: {details.get('html_url')}")

    body = details.get("body", "").strip()
    if body:
        print("\n--- Release Notes Snippet ---")
        for line in body.splitlines()[:10]:
            print(f"  {line}")
        print("-----------------------------\n")

    is_deb_installed = False
    if shutil.which("dpkg"):
        check_dpkg = subprocess.run(["dpkg", "-s", "app-encloser"], capture_output=True, text=True)
        if check_dpkg.returncode == 0 and "Status: install ok" in check_dpkg.stdout:
            is_deb_installed = True

    if is_deb_installed and details.get("deb_url"):
        deb_url = details["deb_url"]
        deb_file = f"/tmp/{details.get('deb_name') or f'app-encloser_{new_ver}_all.deb'}"
        print(f"[*] Downloading Debian package: {deb_url} -> {deb_file}...")
        try:
            req = urllib.request.Request(deb_url, headers={"User-Agent": f"AppEncloser/{__version__}"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(deb_file, "wb") as out_f:
                shutil.copyfileobj(resp, out_f)
        except Exception as e:
            return False, f"Failed to download update package: {e}"

        if download_only:
            return True, f"Package downloaded to {deb_file}. To install, run: sudo dpkg -i {deb_file}"

        print(f"[*] Installing update via dpkg: {deb_file}...")
        res = subprocess.run(["sudo", "dpkg", "-i", deb_file])
        if res.returncode == 0:
            return True, f"App Encloser successfully upgraded to v{new_ver}!"
        else:
            return False, f"dpkg installation exited with code {res.returncode}. You can manually run: sudo dpkg -i {deb_file}"

    elif details.get("tar_url"):
        tar_url = details["tar_url"]
        tar_file = f"/tmp/{details.get('tar_name') or f'app-encloser-{new_ver}-linux-universal.tar.gz'}"
        print(f"[*] Downloading standalone tarball: {tar_url} -> {tar_file}...")
        try:
            req = urllib.request.Request(tar_url, headers={"User-Agent": f"AppEncloser/{__version__}"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(tar_file, "wb") as out_f:
                shutil.copyfileobj(resp, out_f)
        except Exception as e:
            return False, f"Failed to download update archive: {e}"

        return True, f"Universal update archive downloaded to {tar_file}. Extract and run: ./install.sh"

    return True, f"Visit {details.get('html_url')} to download the latest release."
