import os
import re
import struct
import platform
import subprocess
from typing import Dict, Any, List, Tuple, Optional

from app_encloser.core.config import ENCLOSED_DIR
from app_encloser.core.security import scan_app_security
from app_encloser.core.container import find_lib_dirs


def check_elf_architecture(binary_path: str) -> Tuple[bool, str, str]:
    if not os.path.isfile(binary_path):
        return False, "missing", platform.machine()
    try:
        with open(binary_path, "rb") as f:
            magic = f.read(4)
            if magic != b"\x7fELF":
                return True, "non-elf", platform.machine()
            f.seek(4)
            ei_class, ei_data = struct.unpack("BB", f.read(2))
            f.seek(18)
            e_machine = struct.unpack("<H" if ei_data == 1 else ">H", f.read(2))[0]
            arch_map = {
                0x03: "i386",
                0x3E: "x86_64",
                0x28: "arm",
                0xB7: "aarch64",
                0xF3: "riscv",
                0x14: "powerpc"
            }
            b_arch = arch_map.get(e_machine, f"arch-0x{e_machine:x}")
            h_arch = platform.machine()
            if h_arch in ("x86_64", "amd64"):
                is_compat = b_arch in ("x86_64", "i386")
            elif h_arch in ("aarch64", "arm64"):
                is_compat = b_arch in ("aarch64", "arm")
            else:
                is_compat = (b_arch == h_arch)
            return is_compat, b_arch, h_arch
    except Exception as e:
        return True, "unknown", platform.machine()


def check_missing_libraries(binary_path: str, extra_lib_dirs: Optional[List[str]] = None) -> List[str]:
    if not os.path.isfile(binary_path):
        return []
    env = os.environ.copy()
    if extra_lib_dirs:
        env["LD_LIBRARY_PATH"] = ":".join(extra_lib_dirs) + ":" + env.get("LD_LIBRARY_PATH", "")
    try:
        res = subprocess.run(["ldd", binary_path], env=env, capture_output=True, text=True, timeout=5)
        missing = []
        for line in res.stdout.splitlines():
            if "=> not found" in line:
                parts = line.strip().split("=>")
                lib_name = parts[0].strip()
                if lib_name and lib_name not in missing:
                    missing.append(lib_name)
        return missing
    except Exception:
        return []


def attach_isolation_diagnostics(res: Dict[str, Any], folder_name: str, full_log: str) -> Dict[str, Any]:
    if not res.get("has_error"):
        return res
    if res.get("category") in ("cli_usage", "cli_flag_mismatch", "missing_library", "architecture_mismatch", "missing_python_module"):
        return res
    from app_encloser.core.container import get_enclosing_level, get_enclosing_level_details, is_network_or_daemon_app
    cur_lvl = get_enclosing_level(folder_name)
    s_lvl = None
    if cur_lvl == "strict":
        if is_network_or_daemon_app(folder_name) or any(k in full_log.lower() for k in ("socket", "connect", "permission", "daemon", "network", "ipc", "unshare", "bwrap")):
            s_lvl = "integrated"
        else:
            s_lvl = "standard"
    elif cur_lvl == "standard":
        s_lvl = "integrated"

    if s_lvl and s_lvl != cur_lvl:
        info = get_enclosing_level_details(s_lvl)
        res["current_level"] = cur_lvl
        res["suggested_level"] = s_lvl
        res["suggested_level_title"] = info["title"]
        res["level_recommendation"] = f"Lower isolation profile to '{s_lvl}' ({info['title']}) and retry."
        if "Inspect runtime log excerpt" in res.get("recommendation", ""):
            res["recommendation"] = f"{res['level_recommendation']} Or inspect runtime log excerpt below to debug execution."
    return res


def analyze_container_incompatibility(folder_name: str) -> Dict[str, Any]:
    res = _analyze_container_incompatibility_inner(folder_name)
    return attach_isolation_diagnostics(res, folder_name, res.get("full_log", ""))


def _analyze_container_incompatibility_inner(folder_name: str) -> Dict[str, Any]:
    app_dir = os.path.join(ENCLOSED_DIR, folder_name)
    if not os.path.isdir(app_dir):
        return {
            "has_error": True,
            "status": "Container Missing",
            "category": "not_found",
            "summary": f"Container directory '{folder_name}' does not exist on disk.",
            "details": [],
            "missing_libraries": [],
            "exit_code": None,
            "recommendation": "Re-install or re-create this application container.",
            "log_excerpt": "",
            "full_log": "",
            "binary_arch": "unknown",
            "host_arch": platform.machine(),
        }

    app_files = os.path.join(app_dir, "app_files")
    userdata = os.path.join(app_dir, "userdata")
    log_file = os.path.join(userdata, "last_run.log")
    if not os.path.isfile(log_file):
        alt_log = os.path.join(app_dir, "last_run.log")
        if os.path.isfile(alt_log):
            log_file = alt_log

    code_file = os.path.join(userdata, "last_exit_code")
    if not os.path.isfile(code_file):
        alt_code = os.path.join(app_dir, "last_exit_code")
        if os.path.isfile(alt_code):
            code_file = alt_code

    last_exit_code = None
    if os.path.isfile(code_file):
        try:
            with open(code_file, "r", encoding="utf-8") as f:
                c_str = f.read().strip()
                if c_str:
                    last_exit_code = int(c_str)
        except Exception:
            pass

    full_log = ""
    log_lines = []
    if os.path.isfile(log_file):
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                full_log = f.read()
                log_lines = [l.strip() for l in full_log.splitlines() if l.strip()]
        except Exception:
            pass

    logs_dir = os.path.join(userdata, "logs")
    if os.path.isdir(logs_dir):
        for fn in sorted(os.listdir(logs_dir)):
            if fn.endswith((".log", ".txt")):
                fp = os.path.join(logs_dir, fn)
                try:
                    with open(fp, "r", encoding="utf-8", errors="ignore") as lf:
                        lf.seek(0, os.SEEK_END)
                        sz = lf.tell()
                        lf.seek(max(0, sz - 100000), os.SEEK_SET)
                        ext = lf.read()
                        if ext:
                            full_log += "\n" + ext
                            log_lines.extend([l.strip() for l in ext.splitlines() if l.strip()])
                except Exception:
                    pass

    log_excerpt = "\n".join(log_lines[-25:]) if log_lines else ""

    target_exec_file = os.path.join(app_dir, ".target_exec")
    target_rel = ""
    if os.path.isfile(target_exec_file):
        try:
            with open(target_exec_file, "r", encoding="utf-8") as f:
                target_rel = f.read().strip()
        except Exception:
            pass

    desk_file = os.path.join(app_dir, f"{folder_name}.desktop")
    is_cli = False
    if os.path.isfile(desk_file):
        try:
            from app_encloser.core.desktop import parse_desktop_file
            dinfo = parse_desktop_file(desk_file)
            if dinfo.get("Terminal") == "true":
                is_cli = True
        except Exception:
            pass
    if target_rel.startswith("userdata/bin"):
        is_cli = True

    target_bin = os.path.join(app_files, target_rel.lstrip("/")) if target_rel else ""
    if not target_bin or not os.path.isfile(target_bin):
        cand_bins = []
        if os.path.isdir(app_files):
            for root, _, files in os.walk(app_files):
                for fn in files:
                    fp = os.path.join(root, fn)
                    if os.access(fp, os.X_OK) and not fn.endswith((".so", ".a", ".png", ".desktop", ".xml", ".svg")):
                        cand_bins.append(fp)
        if cand_bins:
            target_bin = cand_bins[0]

    compat_arch = True
    b_arch = "unknown"
    h_arch = platform.machine()
    missing_libs = []

    if target_bin and os.path.isfile(target_bin):
        compat_arch, b_arch, h_arch = check_elf_architecture(target_bin)
        lib_dirs = find_lib_dirs(app_files, prefix=app_files)
        if compat_arch and b_arch != "non-elf":
            missing_libs = check_missing_libraries(target_bin, lib_dirs)
            real_missing = []
            for lib in missing_libs:
                found_in_app = False
                for root, _, files in os.walk(app_files):
                    if lib in files:
                        found_in_app = True
                        break
                if not found_in_app:
                    real_missing.append(lib)
            missing_libs = real_missing

    if not compat_arch:
        return {
            "has_error": True,
            "status": "Architecture Incompatible",
            "category": "architecture_mismatch",
            "summary": f"Target binary architecture '{b_arch}' is incompatible with host system '{h_arch}'.",
            "details": [
                f"Binary: {os.path.basename(target_bin) if target_bin else 'unknown'}",
                f"Binary Architecture: {b_arch}",
                f"Host Architecture: {h_arch}"
            ],
            "missing_libraries": [],
            "exit_code": last_exit_code,
            "recommendation": f"Install a package built for {h_arch} (e.g. amd64/x86_64) instead of {b_arch}.",
            "log_excerpt": log_excerpt,
            "full_log": full_log,
            "binary_arch": b_arch,
            "host_arch": h_arch,
        }

    for line in reversed(log_lines):
        m_lib = re.search(r"error while loading shared libraries:\s*([^:]+): cannot open shared object file", line)
        if m_lib:
            lib = m_lib.group(1).strip()
            if lib not in missing_libs:
                missing_libs.append(lib)

    if missing_libs:
        return {
            "has_error": True,
            "status": "Missing Shared Dependencies",
            "category": "missing_library",
            "summary": f"Application requires {len(missing_libs)} missing shared library file(s).",
            "details": [f"Missing: {l}" for l in missing_libs],
            "missing_libraries": missing_libs,
            "exit_code": last_exit_code or 127,
            "recommendation": f"Install missing host package(s) or dependencies (e.g. sudo apt install {missing_libs[0].split('.')[0]}) or copy into container app_files/usr/lib.",
            "log_excerpt": log_excerpt,
            "full_log": full_log,
            "binary_arch": b_arch,
            "host_arch": h_arch,
        }

    for line in log_lines:
        m_glibc = re.search(r"version [`'\"]GLIBC_([0-9.]+)[`'\"] not found", line)
        if m_glibc:
            g_ver = m_glibc.group(1)
            return {
                "has_error": True,
                "status": "GLIBC Incompatibility",
                "category": "glibc_incompatibility",
                "summary": f"Binary was compiled against GLIBC {g_ver}, which is not available on host glibc.",
                "details": [line],
                "missing_libraries": [],
                "exit_code": last_exit_code or 1,
                "recommendation": f"Run application in a container with a newer GLIBC version or install a build targeting your host Linux distribution.",
                "log_excerpt": log_excerpt,
                "full_log": full_log,
                "binary_arch": b_arch,
                "host_arch": h_arch,
            }

        m_py = re.search(r"ModuleNotFoundError: No module named [`'\"]([^`'\"]+)[`'\"]", line)
        if m_py:
            mod = m_py.group(1)
            return {
                "has_error": True,
                "status": "Missing Python Dependency",
                "category": "missing_python_module",
                "summary": f"Application failed because Python module '{mod}' is not installed inside the container.",
                "details": [line],
                "missing_libraries": [],
                "exit_code": last_exit_code or 1,
                "recommendation": f"Open the container terminal shell and install '{mod}' via pip or package manager.",
                "log_excerpt": log_excerpt,
                "full_log": full_log,
                "binary_arch": b_arch,
                "host_arch": h_arch,
            }

        if "bwrap: setting up uid map: Permission denied" in line:
            return {
                "has_error": True,
                "status": "Sandbox Permission Denied",
                "category": "sandbox_permission",
                "summary": "Bubblewrap sandbox cannot create unprivileged user namespaces due to host AppArmor/kernel restriction.",
                "details": [line],
                "missing_libraries": [],
                "exit_code": last_exit_code or 1,
                "recommendation": "Configure host AppArmor user namespace permissions or standard fallback will be used automatically.",
                "log_excerpt": log_excerpt,
                "full_log": full_log,
                "binary_arch": b_arch,
                "host_arch": h_arch,
            }

        if "update source address" in line or ("Operation not permitted" in line and any(k in line.lower() for k in ("connection", "tunnel", "netlink", "routing", "tun", "firewall", "iptables", "nftables"))):
            return {
                "has_error": True,
                "status": "System Network Incompatible (Requires Host Privileges)",
                "category": "root_vpn_incompatible",
                "summary": "Full network routing changes and TUN/TAP device creation require host privileges (CAP_NET_ADMIN) not available in rootless containers.",
                "details": [line],
                "missing_libraries": [],
                "exit_code": last_exit_code,
                "recommendation": "Switch enclosing level to 'System Integrated' (app-encloser level <app> integrated) or install normally on host system.",
                "log_excerpt": log_excerpt,
                "full_log": full_log,
                "binary_arch": b_arch,
                "host_arch": h_arch,
            }

        if any(term in line.lower() for term in ("cannot open display", "could not connect to any x display", "wayland connection failed", "no display specified")):
            return {
                "has_error": True,
                "status": "Display Server Incompatibility",
                "category": "display_error",
                "summary": "Application failed to connect to Wayland or X11 graphical display server.",
                "details": [line],
                "missing_libraries": [],
                "exit_code": last_exit_code or 1,
                "recommendation": "Ensure WAYLAND_DISPLAY or DISPLAY is set and container has access to /tmp/.X11-unix or $XDG_RUNTIME_DIR.",
                "log_excerpt": log_excerpt,
                "full_log": full_log,
                "binary_arch": b_arch,
                "host_arch": h_arch,
            }

    if last_exit_code is not None and last_exit_code != 0:
        if last_exit_code == 139:
            status_desc = "Segmentation Fault (SIGSEGV)"
            cat = "crash_segfault"
            rec = "Application memory access violation. Verify binary compatibility or check driver/GPU requirements."
        elif last_exit_code == 134:
            status_desc = "Abort Signal (SIGABRT)"
            cat = "crash_abort"
            rec = "Application encountered an assertion failure or internal fatal error."
        elif last_exit_code == 132:
            status_desc = "Illegal Instruction (SIGILL)"
            cat = "crash_illegal_instruction"
            rec = "Application binary used CPU instructions unsupported by your processor."
        elif last_exit_code == 127:
            status_desc = "Command Not Found / Dynamic Link Failure"
            cat = "command_not_found"
            rec = "Executable binary or dynamic linker could not locate dependent binaries or libraries."
        elif last_exit_code == 126:
            status_desc = "Permission Denied"
            cat = "permission_denied"
            rec = "Target executable lacks execution permissions. Run 'chmod +x' inside container."
        elif "no such option '--no-sandbox'" in full_log.lower():
            status_desc = "CLI Tool (Unrecognized Flag)"
            cat = "cli_flag_mismatch"
            rec = f"Container launcher passed browser sandbox flags to a non-browser tool. Updated launcher to execute directly."
        elif (last_exit_code in (1, 2) or is_cli) and (any(k in full_log.lower() for k in ("usage:", "command [args]", "[options]", "commands:", "options:", "try '", "--help"))):
            status_desc = "CLI Tool (Subcommand or Arguments Required)"
            cat = "cli_usage"
            rec = f"Application is a command-line tool. Open the container terminal shell to execute subcommands interactively (e.g. '{folder_name.lower()} --help')."
        else:
            status_desc = f"Exited with error code {last_exit_code}"
            cat = "runtime_error"
            rec = "Inspect runtime log excerpt below or open container shell to debug execution."

        last_line = log_lines[-1] if log_lines else f"Exited with code {last_exit_code}"
        return {
            "has_error": True,
            "status": status_desc,
            "category": cat,
            "summary": f"Application terminated abnormally with exit code {last_exit_code}.",
            "details": [last_line],
            "missing_libraries": [],
            "exit_code": last_exit_code,
            "recommendation": rec,
            "log_excerpt": log_excerpt,
            "full_log": full_log,
            "binary_arch": b_arch,
            "host_arch": h_arch,
        }

    return {
        "has_error": False,
        "status": "Healthy",
        "category": "ok",
        "summary": "No runtime errors, crashes, or missing dependencies detected.",
        "details": [],
        "missing_libraries": [],
        "exit_code": last_exit_code or 0,
        "recommendation": "Application container is functioning nominally.",
        "log_excerpt": log_excerpt,
        "full_log": full_log,
        "binary_arch": b_arch,
        "host_arch": h_arch,
    }


def generate_diagnostic_report(folder_name: str) -> str:
    app_dir = os.path.join(ENCLOSED_DIR, folder_name)
    if not os.path.isdir(app_dir):
        return f"Error: Application folder '{folder_name}' does not exist."

    diag = analyze_container_incompatibility(folder_name)
    sec = scan_app_security(folder_name)

    lines = [
        f"=== Diagnostic & Incompatibility Report: {folder_name} ===",
        f"Runtime Status: {diag['status']} (Exit Code: {diag['exit_code'] if diag['exit_code'] is not None else 'None'})",
        f"Binary Architecture: {diag['binary_arch']} (Host: {diag['host_arch']})",
        f"Summary: {diag['summary']}",
    ]
    if diag["missing_libraries"]:
        lines.append(f"Missing Libraries ({len(diag['missing_libraries'])}):")
        for ml in diag["missing_libraries"]:
            lines.append(f"  ✗ {ml}")

    if diag["recommendation"]:
        lines.append(f"Recommendation: {diag['recommendation']}")

    if diag["log_excerpt"]:
        lines.append("\nRecent Execution Log:")
        for ll in diag["log_excerpt"].splitlines()[-10:]:
            lines.append(f"  | {ll}")

    lines.extend([
        "",
        "=== Security & Telemetry Audit ===",
        f"Security Grade: {sec['grade']} ({sec['score']}/100) — Status: {sec['status']}",
        f"Strict Sandbox: {'Enabled' if sec['strict_sandbox'] else 'Disabled'}",
        f"Scanned Files: {sec['files_scanned']}",
    ])
    if sec["trackers"]:
        lines.append("Detected Telemetry & Trackers:")
        for t in sec["trackers"]:
            lines.append(f"  • {t['domain']}: {t['type']}")
    else:
        lines.append("Detected Telemetry & Trackers: None detected.")

    if sec["suid_binaries"]:
        lines.append("SUID Binaries:")
        for s in sec["suid_binaries"]:
            lines.append(f"  • {s['file']} ({s['type']})")

    return "\n".join(lines)


def resolve_container_dependencies(folder_name: str, status_cb=None) -> Tuple[bool, str, List[str]]:
    app_dir = os.path.join(ENCLOSED_DIR, folder_name)
    if not os.path.isdir(app_dir):
        return False, f"Container '{folder_name}' does not exist.", []

    app_files = os.path.join(app_dir, "app_files")
    userdata = os.path.join(app_dir, "userdata")
    actions_taken = []

    if status_cb:
        status_cb("Auditing container structure & library symlinks...")

    from app_encloser.core.lifecycle import fix_usrmerge_symlinks, install_container_helpers, unpack_archive, repair_app
    fix_usrmerge_symlinks(app_files)
    install_container_helpers(app_dir)

    target_exec_file = os.path.join(app_dir, ".target_exec")
    target_rel = ""
    if os.path.isfile(target_exec_file):
        try:
            with open(target_exec_file, "r", encoding="utf-8") as f:
                target_rel = f.read().strip()
        except Exception:
            pass

    desk_file = os.path.join(app_dir, f"{folder_name}.desktop")
    is_cli = False
    if os.path.isfile(desk_file):
        try:
            from app_encloser.core.desktop import parse_desktop_file
            dinfo = parse_desktop_file(desk_file)
            if dinfo.get("Terminal") == "true":
                is_cli = True
        except Exception:
            pass
    if target_rel.startswith("userdata/bin"):
        is_cli = True

    target_bin = os.path.join(app_files, target_rel.lstrip("/")) if target_rel else ""
    if not target_bin or not os.path.isfile(target_bin):
        cand_bins = []
        if os.path.isdir(app_files):
            for root, _, files in os.walk(app_files):
                for fn in files:
                    fp = os.path.join(root, fn)
                    if os.access(fp, os.X_OK) and not fn.endswith((".so", ".a", ".png", ".desktop", ".xml", ".svg")):
                        cand_bins.append(fp)
        if cand_bins:
            target_bin = cand_bins[0]
            with open(target_exec_file, "w", encoding="utf-8") as f:
                f.write(os.path.relpath(target_bin, app_files))
            actions_taken.append(f"Set execution target: {os.path.relpath(target_bin, app_files)}")

    if status_cb:
        status_cb("Discovering internal library directories...")

    lib_dirs = find_lib_dirs(app_files, prefix=app_files)
    for ld in lib_dirs:
        rel = os.path.relpath(ld, app_dir)
        actions_taken.append(f"Linked library directory: {rel}")

    missing_libs = check_missing_libraries(target_bin, lib_dirs) if target_bin else []
    real_missing = []
    for lib in missing_libs:
        found_in_app = False
        for root, _, files in os.walk(app_files):
            if lib in files:
                found_in_app = True
                break
        if not found_in_app:
            real_missing.append(lib)
    missing_libs = real_missing

    if missing_libs:
        if status_cb:
            status_cb(f"Resolving {len(missing_libs)} missing shared dependencies...")

        host_search_dirs = [
            "/usr/lib/x86_64-linux-gnu",
            "/usr/lib",
            "/lib/x86_64-linux-gnu",
            "/lib",
            "/usr/local/lib"
        ]
        dest_lib_dir = os.path.join(app_files, "usr", "lib")
        os.makedirs(dest_lib_dir, exist_ok=True)

        for missing in list(missing_libs):
            host_file = None
            for hsd in host_search_dirs:
                cand = os.path.join(hsd, missing)
                if os.path.isfile(cand):
                    host_file = cand
                    break
            if not host_file:
                for root, _, files in os.walk("/usr/lib"):
                    if missing in files:
                        host_file = os.path.join(root, missing)
                        break

            if host_file:
                try:
                    dest_file = os.path.join(dest_lib_dir, missing)
                    if os.path.islink(host_file):
                        real = os.path.realpath(host_file)
                        real_dest = os.path.join(dest_lib_dir, os.path.basename(real))
                        if not os.path.isfile(real_dest):
                            import shutil
                            shutil.copyfile(real, real_dest)
                            os.chmod(real_dest, 0o755)
                        if not os.path.exists(dest_file):
                            os.symlink(os.path.basename(real), dest_file)
                    else:
                        import shutil
                        shutil.copyfile(host_file, dest_file)
                        os.chmod(dest_file, 0o755)
                    actions_taken.append(f"Imported {missing} from host into container")
                    missing_libs.remove(missing)
                except Exception:
                    pass

        if missing_libs:
            pkg_map = {
                "libfuse.so.2": "libfuse2t64",
                "libfuse2.so": "libfuse2t64",
                "libssl.so.1.1": "libssl1.1",
                "libssl.so.3": "libssl3t64",
                "libcrypto.so.3": "libssl3t64",
                "libasound.so.2": "libasound2t64",
                "libX11.so.6": "libx11-6",
                "libgtk-3.so.0": "libgtk-3-0",
                "libgdk-3.so.0": "libgtk-3-0",
                "libgobject-2.0.so.0": "libglib2.0-0t64",
                "libglib-2.0.so.0": "libglib2.0-0t64",
                "libnotify.so.4": "libnotify4",
            }
            cache_dir = os.path.join(userdata, "cache")
            os.makedirs(cache_dir, exist_ok=True)

            for missing in list(missing_libs):
                pkg = pkg_map.get(missing)
                if not pkg:
                    stem = missing.split(".so")[0]
                    clean_stem = re.sub(r"[0-9_-]+$", "", stem)
                    try:
                        res = subprocess.run(["apt-cache", "search", "--names-only", f"^{clean_stem}"], capture_output=True, text=True, timeout=5)
                        lines = [l.split()[0] for l in res.stdout.splitlines() if l.strip()]
                        if lines:
                            pkg = lines[0]
                    except Exception:
                        pass

                if pkg:
                    if status_cb:
                        status_cb(f"Fetching package {pkg} into container cache...")
                    try:
                        dl = subprocess.run(["apt-get", "download", pkg], cwd=cache_dir, capture_output=True, text=True, timeout=30)
                        if dl.returncode == 0:
                            for fn in os.listdir(cache_dir):
                                if fn.startswith(pkg) and fn.endswith(".deb"):
                                    deb_path = os.path.join(cache_dir, fn)
                                    unpack_archive(deb_path, app_files)
                                    actions_taken.append(f"Downloaded and unpacked {pkg} into container")
                                    missing_libs.remove(missing)
                                    break
                    except Exception:
                        pass

    if status_cb:
        status_cb("Re-generating launch script & verifying...")

    repair_app(folder_name)

    final_lib_dirs = find_lib_dirs(app_files, prefix=app_files)
    final_missing = check_missing_libraries(target_bin, final_lib_dirs) if target_bin else []
    real_final_missing = []
    for lib in final_missing:
        found_in_app = False
        for root, _, files in os.walk(app_files):
            if lib in files:
                found_in_app = True
                break
        if not found_in_app:
            real_final_missing.append(lib)

    if not real_final_missing:
        return True, f"Successfully resolved all dependencies for '{folder_name}'.", actions_taken
    else:
        return False, f"Resolved {len(actions_taken)} components, but still missing: {', '.join(real_final_missing)}", actions_taken


def detect_container_anomalies(folder_name: str) -> List[Dict[str, Any]]:
    app_dir = os.path.join(ENCLOSED_DIR, folder_name)
    anomalies: List[Dict[str, Any]] = []
    if not os.path.isdir(app_dir):
        return [{"type": "missing_container", "item": folder_name, "severity": "critical", "description": f"Container directory not found: {folder_name}"}]

    shims_dir = os.path.join(app_dir, "userdata", "shims")
    expected_shims = {"apt", "apt-get", "gpg", "tee", "sudo", "nft", "curl", "wget", "encloser-install", "encloser-python", "encloser-brew"}
    if not os.path.isdir(shims_dir):
        anomalies.append({"type": "missing_shims_dir", "item": "userdata/shims", "severity": "high", "description": "Shims directory is missing"})
    else:
        for s in expected_shims:
            sp = os.path.join(shims_dir, s)
            if not os.path.isfile(sp):
                anomalies.append({"type": "missing_shim", "item": s, "severity": "medium", "description": f"Missing container shim: {s}"})
            elif not os.access(sp, os.X_OK):
                anomalies.append({"type": "unexecutable_shim", "item": s, "severity": "medium", "description": f"Shim lacks executable permission: {s}"})

    stale_shim_dir = os.path.join(app_dir, "app_files", "usr", "bin")
    if os.path.isdir(stale_shim_dir):
        for s in expected_shims:
            sp = os.path.join(stale_shim_dir, s)
            if os.path.isfile(sp):
                try:
                    c = open(sp, "r", errors="ignore").read(128)
                    if "encloser" in c or "userdata/shims" in c or "APP_ENCLOSER" in c:
                        anomalies.append({"type": "stale_legacy_shim", "item": sp, "severity": "low", "description": f"Stale legacy shim inside app_files: {s}"})
                except Exception:
                    pass

    launch_sh = os.path.join(app_dir, "launch.sh")
    if not os.path.isfile(launch_sh):
        anomalies.append({"type": "missing_launch_script", "item": "launch.sh", "severity": "critical", "description": "launch.sh does not exist"})
    elif os.path.getsize(launch_sh) == 0:
        anomalies.append({"type": "empty_launch_script", "item": "launch.sh", "severity": "critical", "description": "launch.sh is zero bytes"})
    elif not os.access(launch_sh, os.X_OK):
        anomalies.append({"type": "unexecutable_launch_script", "item": "launch.sh", "severity": "high", "description": "launch.sh lacks executable bit"})

    req_dirs = [
        os.path.join(app_dir, "userdata"),
        os.path.join(app_dir, "userdata", "keyrings"),
        os.path.join(app_dir, "userdata", "bin"),
        os.path.join(app_dir, "userdata", "home")
    ]
    for rd in req_dirs:
        if not os.path.isdir(rd):
            anomalies.append({"type": "missing_directory", "item": os.path.relpath(rd, app_dir), "severity": "low", "description": f"Standard directory missing: {os.path.basename(rd)}"})

    from app_encloser.core.config import APPS_DIR
    desk_path = os.path.join(APPS_DIR, f"{folder_name}.desktop")
    if not os.path.isfile(desk_path):
        anomalies.append({"type": "missing_desktop_file", "item": f"{folder_name}.desktop", "severity": "low", "description": "Desktop launcher entry missing in ~/.local/share/applications"})

    pid_file = os.path.join(app_dir, "userdata", "running.pid")
    if os.path.isfile(pid_file):
        dead_pids = []
        try:
            with open(pid_file, "r") as f:
                for line in f:
                    s = line.strip()
                    if s.isdigit():
                        p = int(s)
                        try:
                            os.kill(p, 0)
                        except OSError:
                            dead_pids.append(p)
            if dead_pids:
                anomalies.append({"type": "stale_pids", "item": dead_pids, "severity": "low", "description": f"Stale running PIDs recorded: {dead_pids}"})
        except Exception:
            pass

    return anomalies


def auto_repair_container(folder_name: str) -> Dict[str, Any]:
    from app_encloser.core.lifecycle import install_container_helpers, repair_app
    app_dir = os.path.join(ENCLOSED_DIR, folder_name)
    if not os.path.isdir(app_dir):
        return {"folder": folder_name, "healthy": False, "repaired": False, "anomalies_detected": 1, "repairs_applied": [], "error": "Container directory not found"}

    anomalies = detect_container_anomalies(folder_name)
    repairs_applied: List[str] = []

    if not anomalies:
        return {"folder": folder_name, "healthy": True, "repaired": False, "anomalies_detected": 0, "repairs_applied": []}

    types = {a["type"] for a in anomalies}

    req_dirs = [
        os.path.join(app_dir, "userdata"),
        os.path.join(app_dir, "userdata", "shims"),
        os.path.join(app_dir, "userdata", "keyrings"),
        os.path.join(app_dir, "userdata", "bin"),
        os.path.join(app_dir, "userdata", "home")
    ]
    for rd in req_dirs:
        if not os.path.isdir(rd):
            os.makedirs(rd, exist_ok=True)
            repairs_applied.append(f"Created missing directory {os.path.basename(rd)}")

    if any(t in types for t in ("missing_shims_dir", "missing_shim", "unexecutable_shim")):
        install_container_helpers(app_dir)
        repairs_applied.append("Reinstalled and fixed permissions for container shims")

    shims_dir = os.path.join(app_dir, "userdata", "shims")
    if os.path.isdir(shims_dir):
        for fn in os.listdir(shims_dir):
            fp = os.path.join(shims_dir, fn)
            if os.path.isfile(fp) and not os.access(fp, os.X_OK):
                try:
                    os.chmod(fp, 0o755)
                    repairs_applied.append(f"Restored executable bit for shim {fn}")
                except Exception:
                    pass

    stale_shim_dir = os.path.join(app_dir, "app_files", "usr", "bin")
    if os.path.isdir(stale_shim_dir):
        expected_shims = {"apt", "apt-get", "gpg", "tee", "sudo", "nft", "curl", "wget", "encloser-install", "encloser-python", "encloser-brew"}
        for s in expected_shims:
            sp = os.path.join(stale_shim_dir, s)
            if os.path.isfile(sp):
                try:
                    c = open(sp, "r", errors="ignore").read(128)
                    if "encloser" in c or "userdata/shims" in c or "APP_ENCLOSER" in c:
                        os.remove(sp)
                        repairs_applied.append(f"Removed stale legacy shim from app_files: {s}")
                except Exception:
                    pass

    launch_sh = os.path.join(app_dir, "launch.sh")
    if "unexecutable_launch_script" in types and os.path.isfile(launch_sh):
        try:
            os.chmod(launch_sh, 0o755)
            repairs_applied.append("Restored executable bit for launch.sh")
        except Exception:
            pass

    if any(t in types for t in ("missing_launch_script", "empty_launch_script", "missing_desktop_file")):
        ok, msg = repair_app(folder_name)
        if ok:
            repairs_applied.append(f"Repaired container environment and desktop launcher: {msg}")

    pid_file = os.path.join(app_dir, "userdata", "running.pid")
    if "stale_pids" in types and os.path.isfile(pid_file):
        try:
            alive_pids = []
            with open(pid_file, "r") as f:
                for line in f:
                    s = line.strip()
                    if s.isdigit():
                        p = int(s)
                        try:
                            os.kill(p, 0)
                            alive_pids.append(str(p))
                        except OSError:
                            pass
            if alive_pids:
                with open(pid_file, "w") as f:
                    f.write("\n".join(alive_pids) + "\n")
            else:
                os.remove(pid_file)
            repairs_applied.append("Pruned dead PIDs from running.pid")
        except Exception:
            pass

    return {
        "folder": folder_name,
        "healthy": True,
        "repaired": len(repairs_applied) > 0,
        "anomalies_detected": len(anomalies),
        "repairs_applied": repairs_applied
    }


def self_heal_all_containers() -> List[Dict[str, Any]]:
    reports = []
    if not os.path.isdir(ENCLOSED_DIR):
        return reports
    for entry in sorted(os.listdir(ENCLOSED_DIR)):
        if entry.startswith("."):
            continue
        p = os.path.join(ENCLOSED_DIR, entry)
        if os.path.isdir(p):
            rep = auto_repair_container(entry)
            reports.append(rep)
    return reports
