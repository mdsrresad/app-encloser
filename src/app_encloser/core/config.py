import os
import sys
import json
import time
import subprocess
from typing import Optional, Dict, Any

REAL_HOME = os.path.realpath(os.path.expanduser("~"))
ENCLOSED_DIR = os.environ.get("APP_ENCLOSER_DIR") or os.path.join(REAL_HOME, "EnclosedApps")
APPS_DIR = os.environ.get("APP_ENCLOSER_APPS_DIR") or os.path.join(REAL_HOME, ".local", "share", "applications")
ICONS_DIR = os.environ.get("APP_ENCLOSER_ICONS_DIR") or os.path.join(REAL_HOME, ".local", "share", "icons", "hicolor")
LOCAL_BIN = os.environ.get("APP_ENCLOSER_BIN_DIR") or os.path.join(REAL_HOME, ".local", "bin")
CONFIG_DIR = os.environ.get("APP_ENCLOSER_CONFIG_DIR") or os.path.join(REAL_HOME, ".config", "app-encloser")
CACHE_DIR = os.environ.get("APP_ENCLOSER_CACHE_DIR") or os.path.join(REAL_HOME, ".cache", "app-encloser")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")


def ensure_base_dirs():
    for d in (ENCLOSED_DIR, APPS_DIR, ICONS_DIR, LOCAL_BIN, CONFIG_DIR, CACHE_DIR):
        os.makedirs(d, exist_ok=True)


DEFAULT_SETTINGS: Dict[str, Any] = {
    "install_scope": "isolated",
    "zero_duplicate_icons": True,
    "show_launch_notifications": True,
    "button_style": "icons_only",
    "non_grabbing_menus": True,
    "strict_sandbox_by_default": True,
    "terminal_guard_enabled": False,
    "mcp_enabled": False
}

_DIR_SIZE_CACHE: Dict[str, tuple] = {}


def load_settings() -> Dict[str, Any]:
    if not os.path.isfile(SETTINGS_FILE):
        return dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                merged = dict(DEFAULT_SETTINGS)
                merged.update(data)
                return merged
    except Exception:
        pass
    try:
        if os.path.isfile(SETTINGS_FILE):
            bak = f"{SETTINGS_FILE}.corrupt.{int(time.time())}"
            os.rename(SETTINGS_FILE, bak)
            save_settings(dict(DEFAULT_SETTINGS))
    except Exception:
        pass
    return dict(DEFAULT_SETTINGS)


def save_settings(settings: Dict[str, Any]) -> bool:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception:
        return False


def get_setting(key: str, default: Any = None) -> Any:
    cfg = load_settings()
    return cfg.get(key, DEFAULT_SETTINGS.get(key, default))


def update_setting(key: str, value: Any) -> bool:
    cfg = load_settings()
    if value is None:
        cfg.pop(key, None)
    else:
        cfg[key] = value
    return save_settings(cfg)


def clean_folder_name(name: str) -> str:
    cleaned = "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip("-._")
    if not cleaned:
        cleaned = "App"
    return cleaned[0].upper() + cleaned[1:]


def is_supported_file(path: str) -> bool:
    low = path.lower()
    return any(low.endswith(ext) for ext in (
        ".deb", ".appimage", ".tar.gz", ".tgz", ".tar.xz", ".tar.bz2",
        ".zip", ".rpm", ".snap", ".sh", ".run", ".bin", ".jar"
    ))


def get_dir_size(path: str, max_age_seconds: float = 300.0) -> str:
    if not os.path.exists(path):
        return "0 B"
    cached = _DIR_SIZE_CACHE.get(path)
    now = time.time()
    if cached and (now - cached[1]) < max_age_seconds and cached[2]:
        return cached[2]
    try:
        size_str = subprocess.check_output(
            ["du", "-sh", path], stderr=subprocess.DEVNULL, timeout=1.0
        ).decode().split()[0]
        raw_b = cached[0] if cached else 0
        _DIR_SIZE_CACHE[path] = (raw_b, now, size_str)
        return size_str
    except Exception:
        return cached[2] if cached else "..."


def get_dir_size_bytes(path: str, max_age_seconds: float = 300.0) -> int:
    if not os.path.exists(path):
        return 0
    cached = _DIR_SIZE_CACHE.get(path)
    now = time.time()
    if cached and (now - cached[1]) < max_age_seconds and cached[0] > 0:
        return cached[0]
    try:
        raw_b = int(subprocess.check_output(
            ["du", "-sb", path], stderr=subprocess.DEVNULL, timeout=1.0
        ).decode().split()[0])
        fmt = cached[2] if (cached and cached[2]) else ""
        if not fmt:
            try:
                fmt = subprocess.check_output(
                    ["du", "-sh", path], stderr=subprocess.DEVNULL, timeout=1.0
                ).decode().split()[0]
            except Exception:
                fmt = "..."
        _DIR_SIZE_CACHE[path] = (raw_b, now, fmt)
        return raw_b
    except Exception:
        if cached:
            return cached[0]
        return 0


def invalidate_dir_size_cache(path: Optional[str] = None):
    if path:
        _DIR_SIZE_CACHE.pop(path, None)
        for k in list(_DIR_SIZE_CACHE.keys()):
            if k.startswith(path):
                _DIR_SIZE_CACHE.pop(k, None)
    else:
        _DIR_SIZE_CACHE.clear()
