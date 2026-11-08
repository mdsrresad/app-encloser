import os
import re
import shlex
import stat
from typing import Dict, Any, List

from app_encloser.core.config import ENCLOSED_DIR, clean_folder_name
from app_encloser.core.container import is_strict_sandbox

KNOWN_TRACKER_DOMAINS = [
    "google-analytics.com", "analytics.google.com", "googletagmanager.com",
    "telemetry.", "vortex.data.microsoft.com", "browser.pipe.aria.microsoft.com",
    "dc.services.visualstudio.com", "sentry.io", "browser-intake-datadoghq.com",
    "segment.io", "api.segment.io", "mixpanel.com", "api.mixpanel.com",
    "app.posthog.com", "us.i.posthog.com", "eu.i.posthog.com", "heapanalytics.com",
    "amplitude.com", "api.amplitude.com", "hotjar.com", "bugsnag.com",
    "fullstory.com", "clarity.ms", "loggly.com", "raygun.io", "rollbar.com"
]

TRACKER_CATALOG_BYTES = [(d.encode("utf-8"), d, f"{d} (Telemetry/Analytics)") for d in KNOWN_TRACKER_DOMAINS]

SUSPICIOUS_PATTERNS = [
    (re.compile(r"/bin/(?:ba)?sh\s+-i\s+>&?\s*/dev/tcp/", re.I), "Reverse TCP shell pattern"),
    (re.compile(r"nc\s+(?:-e|-c)\s+/bin/(?:ba)?sh", re.I), "Netcat executable shell execution"),
    (re.compile(r"chmod\s+[0-7]?[4-7][0-7]{2}\s+", re.I), "Explicit SUID chmod escalation in script"),
    (re.compile(r"pkexec\s+", re.I), "Privileged pkexec invocation pattern"),
    (re.compile(r"curl\s+[^|\n]+\|\s*(?:ba)?sh", re.I), "Unsafe curl-pipe-to-shell pattern")
]


def scan_app_security(folder_name: str) -> Dict[str, Any]:
    folder_clean = clean_folder_name(folder_name)
    app_dir = os.path.join(ENCLOSED_DIR, folder_clean)
    if not os.path.isdir(app_dir):
        return {
            "folder": folder_name,
            "status": "NOT_FOUND",
            "score": 0,
            "grade": "F",
            "findings": ["Directory does not exist"],
            "trackers": [],
            "suid_binaries": [],
            "world_writable": [],
            "recommendations": []
        }

    strict = is_strict_sandbox(app_dir)
    app_files = os.path.join(app_dir, "app_files")

    detected_trackers = {}
    suid_binaries = []
    world_writable = []
    suspicious_patterns = []
    scanned_files_count = 0

    EXCLUDE_DIRS = {".git", "locale", "locales", "translations", "man", "doc", "fonts"}

    if os.path.isdir(app_files):
        for root, dirs, files in os.walk(app_files):
            dirs[:] = [d for d in dirs if d.lower() not in EXCLUDE_DIRS]
            for f in files:
                scanned_files_count += 1
                full_p = os.path.join(root, f)
                rel_p = os.path.relpath(full_p, app_files)

                try:
                    st = os.stat(full_p)
                    if st.st_mode & 0o4000:
                        if "chrome-sandbox" in f:
                            suid_binaries.append({"file": rel_p, "type": "Chromium Sandbox Helper", "safe": True})
                        else:
                            suid_binaries.append({"file": rel_p, "type": "Custom SUID Binary", "safe": False})
                    if (st.st_mode & 0o002) and (st.st_mode & 0o111):
                        world_writable.append(rel_p)
                except Exception:
                    pass

                low_f = f.lower()
                is_scannable = (
                    low_f.endswith((".js", ".json", ".html", ".sh", ".py", ".yml", ".txt", ".conf", ".cfg"))
                    or low_f == folder_clean.lower()
                )

                if is_scannable:
                    try:
                        with open(full_p, "rb") as fp:
                            data = fp.read(128 * 1024)
                            data_text = data.decode("utf-8", errors="ignore")

                            for dom_bytes, dom, desc in TRACKER_CATALOG_BYTES:
                                if dom_bytes in data:
                                    detected_trackers[dom] = desc

                            for pattern, desc in SUSPICIOUS_PATTERNS:
                                if pattern.search(data_text):
                                    suspicious_patterns.append({"file": rel_p, "finding": desc})
                    except Exception:
                        pass

    score = 100
    if not strict:
        score -= 20
    if detected_trackers:
        score -= min(25, len(detected_trackers) * 5)
    unsafe_suid = [s for s in suid_binaries if not s.get("safe", False)]
    if unsafe_suid:
        score -= min(30, len(unsafe_suid) * 15)
    if world_writable:
        score -= min(15, len(world_writable) * 5)
    if suspicious_patterns:
        score -= min(30, len(suspicious_patterns) * 10)

    score = max(0, min(100, score))
    if score >= 90:
        grade = "A"
        status = "SAFE"
    elif score >= 75:
        grade = "B"
        status = "MODERATE"
    elif score >= 60:
        grade = "C"
        status = "SUSPICIOUS"
    else:
        grade = "D"
        status = "HIGH_RISK"

    recommendations = []
    if not strict:
        recommendations.append("Enable Strict Bubblewrap Sandbox to mask host home directory with tmpfs.")
    if detected_trackers:
        recommendations.append(f"Block telemetry domains at network layer: {', '.join(list(detected_trackers.keys())[:3])}")
    if unsafe_suid:
        recommendations.append("Remove SUID bits on custom binaries inside app_files.")

    return {
        "folder": folder_clean,
        "status": status,
        "score": score,
        "grade": grade,
        "strict_sandbox": strict,
        "files_scanned": scanned_files_count,
        "trackers": [{"domain": k, "type": v} for k, v in detected_trackers.items()],
        "suid_binaries": suid_binaries,
        "world_writable": world_writable,
        "suspicious_patterns": suspicious_patterns,
        "recommendations": recommendations
    }


def batch_security_scan(folders: List[str]) -> List[Dict[str, Any]]:
    return [scan_app_security(f) for f in folders]
