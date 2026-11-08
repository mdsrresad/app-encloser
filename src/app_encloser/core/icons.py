import os
import re
import json
import struct
import shutil
from typing import Optional, Tuple, Any


def get_png_dimensions(path: str) -> Tuple[int, int]:
    try:
        with open(path, "rb") as f:
            magic = f.read(8)
            if magic != b"\x89PNG\r\n\x1a\n":
                return (0, 0)
            f.seek(16)
            w, h = struct.unpack(">II", f.read(8))
            return (w, h)
    except Exception:
        return (0, 0)


def generate_monogram_svg(dest_path: str, app_name: str):
    words = re.findall(r"[A-Za-z0-9]+", app_name)
    if len(words) >= 2:
        initials = (words[0][0] + words[1][0]).upper()
    elif words:
        initials = words[0][:2].upper()
    else:
        initials = "AE"

    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#4f46e5"/>
      <stop offset="100%" stop-color="#1e1b4b"/>
    </linearGradient>
  </defs>
  <rect width="232" height="232" x="12" y="12" rx="48" fill="url(#bg)"/>
  <rect width="208" height="208" x="24" y="24" rx="40" fill="none" stroke="#ffffff" stroke-opacity="0.3" stroke-width="4"/>
  <text x="128" y="162" font-family="system-ui, -apple-system, sans-serif" font-size="92" font-weight="700" fill="#ffffff" text-anchor="middle">{initials}</text>
</svg>"""
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(svg_content)


def extract_icon_from_asar(asar_path: str, dest_icon_path: str) -> bool:
    try:
        with open(asar_path, "rb") as f:
            u1, header_size, u3, json_len = struct.unpack("<IIII", f.read(16))
            header_bytes = f.read(json_len)
            header = json.loads(header_bytes.decode("utf-8"))
            payload_base = 16 + json_len

            candidates = []

            def walk(node: Any, rel_path: str = ""):
                if isinstance(node, dict) and "files" in node:
                    for k, v in node["files"].items():
                        sub = f"{rel_path}/{k}" if rel_path else k
                        walk(v, sub)
                elif isinstance(node, dict) and "offset" in node:
                    low = rel_path.lower()
                    if any(low.endswith(x) for x in (".png", ".svg")):
                        if "node_modules/" in low or "extensions/" in low:
                            return
                        score = 0
                        base = os.path.basename(low)
                        if base in ("icon.png", "app.png", "logo.png"):
                            score += 100
                        elif "icon" in low or "logo" in low:
                            score += 50
                        if "tray" in low:
                            score -= 60
                        if "status" in low or "badge" in low:
                            score -= 40
                        sz = int(node.get("size", 0))
                        offset = int(node.get("offset", 0))
                        candidates.append((score, sz, offset, rel_path))

            walk(header)
            if not candidates:
                return False

            candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
            best = candidates[0]
            offset = best[2]
            sz = best[1]

            f.seek(payload_base + offset)
            data = f.read(sz)
            if data.startswith(b"\x89PNG\r\n\x1a\n") or b"<svg" in data[:128]:
                with open(dest_icon_path, "wb") as out_f:
                    out_f.write(data)
                return True
    except Exception:
        pass
    return False


def extract_or_generate_icon(app_dir: str, app_name: str, desktop_icon_name: Optional[str] = None) -> str:
    app_files = os.path.join(app_dir, "app_files")
    icon_png = os.path.join(app_dir, "icon.png")
    icon_svg = os.path.join(app_dir, "icon.svg")

    icon_base = os.path.splitext(os.path.basename(desktop_icon_name))[0] if desktop_icon_name else ""

    if icon_base:
        for ext in (".png", ".svg"):
            pix = os.path.join(app_files, "usr", "share", "pixmaps", f"{icon_base}{ext}")
            if os.path.isfile(pix):
                target = icon_png if ext == ".png" else icon_svg
                shutil.copy2(pix, target)
                if ext == ".png" and os.path.isfile(icon_svg):
                    try:
                        os.remove(icon_svg)
                    except Exception:
                        pass
                return target

        hicolor_dir = os.path.join(app_files, "usr", "share", "icons", "hicolor")
        if os.path.isdir(hicolor_dir):
            hicolor_matches = []
            for root, _, files in os.walk(hicolor_dir):
                for f in files:
                    if f in (f"{icon_base}.png", f"{icon_base}.svg"):
                        p = os.path.join(root, f)
                        dim = 0
                        if f.endswith(".png"):
                            w, _ = get_png_dimensions(p)
                            dim = w
                        elif f.endswith(".svg"):
                            dim = 1024
                        hicolor_matches.append((dim, p))
            if hicolor_matches:
                hicolor_matches.sort(key=lambda m: m[0], reverse=True)
                best_icon = hicolor_matches[0][1]
                target = icon_png if best_icon.endswith(".png") else icon_svg
                shutil.copy2(best_icon, target)
                if target == icon_png and os.path.isfile(icon_svg):
                    try:
                        os.remove(icon_svg)
                    except Exception:
                        pass
                return target

    if os.path.isdir(app_files):
        asar_files = []
        for root, dirs, files in os.walk(app_files):
            dirs[:] = [d for d in dirs if d not in {"node_modules", "locales", "doc", "man", "include"}]
            for f in files:
                if f == "app.asar":
                    asar_files.append(os.path.join(root, f))
        for asar_p in asar_files:
            if extract_icon_from_asar(asar_p, icon_png):
                if os.path.isfile(icon_svg):
                    try:
                        os.remove(icon_svg)
                    except Exception:
                        pass
                return icon_png

    if os.path.isdir(app_files):
        skip_dirs = {"node_modules", "locales", "doc", "man", "include"}
        candidates = []
        low_base = icon_base.lower() if icon_base else ""
        low_app = app_name.lower()

        for root, dirs, files in os.walk(app_files):
            dirs[:] = [d for d in dirs if d.lower() not in skip_dirs]
            for file in files:
                if not file.lower().endswith(".png"):
                    continue
                fpath = os.path.join(root, file)
                low_path = fpath.lower()
                if any(x in low_path for x in ("tray", "status", "symbolic", "badge", "notification", "panel", "disabled")):
                    continue
                w, h = get_png_dimensions(fpath)
                if w < 32 or h < 32:
                    continue

                score = 0
                fn_stem = os.path.splitext(file)[0].lower()
                if (low_base and fn_stem == low_base) or fn_stem == low_app:
                    score += 1000
                if "product_logo" in fn_stem:
                    score += 500
                elif "logo" in fn_stem:
                    score += 300
                if "app" in fn_stem or "icon" in fn_stem:
                    score += 200

                score += min(w, 512)
                candidates.append((score, w, fpath))

        if candidates:
            candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
            best_png = candidates[0][2]
            shutil.copy2(best_png, icon_png)
            if os.path.isfile(icon_svg):
                try:
                    os.remove(icon_svg)
                except Exception:
                    pass
            return icon_png

    generate_monogram_svg(icon_svg, app_name)
    if os.path.isfile(icon_png):
        try:
            os.remove(icon_png)
        except Exception:
            pass
    return icon_svg
