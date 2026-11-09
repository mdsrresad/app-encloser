import os
import sys
import json
from typing import Optional

src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from app_encloser import __version__
from app_encloser.core import (
    ENCLOSED_DIR, list_enclosed_apps, install_any_package, install_globally,
    install_from_url_or_repo, install_into_container, run_in_container, open_container_shell,
    create_empty_container, scan_app_security, batch_security_scan,
    repair_all_apps, generate_diagnostic_report, self_uninstall,
    load_settings, get_setting, update_setting, is_supported_file,
    run_mcp_server, batch_export, export_all_apps,
    kill_app_processes, inspect_container_contents,
    resolve_container_dependencies, analyze_container_incompatibility,
    get_enclosing_level, set_enclosing_level, get_enclosing_level_details,
    find_container_folder, format_audit_report, handle_intercept_cmd,
    sync_terminal_guard, uninstall_enclosed_app, uninstall_host_package
)


def run_gui(initial_pkg: Optional[str] = None):
    sync_terminal_guard()
    try:
        from app_encloser.core.diagnostic import self_heal_all_containers
        self_heal_all_containers()
    except Exception:
        pass
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk, Gio, GLib
    from app_encloser.ui.window import AppEncloserWindow

    GLib.set_prgname("app.encloser")
    GLib.set_application_name("App Encloser")
    Gtk.Window.set_default_icon_name("app-encloser")

    app = Adw.Application(
        application_id="app.encloser",
        flags=Gio.ApplicationFlags.NON_UNIQUE
    )

    def on_activate(application):
        win = AppEncloserWindow(application=application, initial_pkg=initial_pkg)
        win.set_icon_name("app-encloser")
        win.present()

    app.connect("activate", on_activate)
    return app.run([])


def print_help():
    help_text = f"""App Encloser v{__version__} — Native Isolated Application & Package Manager

Usage:
  app-encloser                           Launch GTK4 / Libadwaita graphical interface
  app-encloser install <pkg> [--container <name>] Isolate package, URL, or install into existing container
  app-encloser install-into <name> <pkg> Shortcut to install package into an existing container
  app-encloser sudo apt[-get] install    APT Proxy: isolate packages without system modifications
  app-encloser run <app_name> <cmd...>   Execute command inside an isolated container
  app-encloser shell <app_name>          Open an interactive shell inside an isolated container
  app-encloser kill <app_name>           Force stop running processes inside container
  app-encloser inspect <app_name>        Inspect isolated container contents, binaries & state
  app-encloser resolve-deps <app> [--yes] Automatically resolve dependencies & library paths with confirmation
  app-encloser level <app> [level]       Get or set container enclosing level (standard, strict, integrated)
  app-encloser uninstall <app_name>      Completely wipe an enclosed container or package
  app-encloser create <name> [--strict]  Create a clean isolated container environment
  app-encloser export <app_name> [path]  Export an application container to archive
  app-encloser export-all [dest_path]    Export all application containers to archive
  app-encloser scan [app_name|ALL]       Run container security, permission & tracker audit
  app-encloser list                      List all enclosed applications in JSON format
  app-encloser repair, doctor            Self-heal, audit & repair container shims, desktop files & state
  app-encloser settings [list|get|set]   Inspect or configure installation & security preferences
  app-encloser report <app_name>         View zero-noise runtime diagnostic report
  app-encloser self-uninstall [--purge]  Completely remove App Encloser from system
  app-encloser --mcp                     Launch Model Context Protocol (MCP) server
  app-encloser --version, -v             Display version information
  app-encloser --help, -h                Display this help message
"""
    print(help_text.strip())


def main() -> int:
    argv = sys.argv[1:]

    if not argv:
        return run_gui()

    if argv[0] in ("--version", "-v", "version"):
        print(f"App Encloser v{__version__}")
        return 0

    if argv[0] in ("--help", "-h", "help"):
        print_help()
        return 0

    if argv[0] == "--intercept-cmd":
        if len(argv) < 2:
            print("Usage: app-encloser --intercept-cmd \"<command>\"")
            return 1
        full_cmd = " ".join(argv[1:])
        return handle_intercept_cmd(full_cmd)

    if "--mcp" in argv:
        run_mcp_server()
        return 0

    if argv[0] == "sudo":
        argv = argv[1:]
        if not argv:
            print("Usage: app-encloser sudo apt-get install <package>")
            return 1

    cmd = argv[0]

    if cmd in ("apt", "apt-get"):
        sub = argv[1:]
        if "install" in sub:
            idx = sub.index("install")
            raw_tokens = sub[idx+1:]
            pkgs = [p for p in raw_tokens if not p.startswith("-") and p != "&&"]
            if not pkgs:
                print("Error: No package name specified to install.")
                return 1

            scope = None
            if "--global" in raw_tokens:
                scope = "global"
            elif "--isolated" in raw_tokens:
                scope = "isolated"

            ret = 0
            for pkg in pkgs:
                pref_scope = scope or get_setting("install_scope", "isolated")
                if pref_scope == "global":
                    print(f"[*] App Encloser APT Proxy: Installing '{pkg}' globally to host system...")
                    ok, msg = install_globally(pkg, status_cb=lambda s: print(f"    -> {s}"))
                else:
                    print(f"[*] App Encloser APT Proxy: Isolating package '{pkg}'...")
                    ok, msg = install_from_url_or_repo(pkg, status_cb=lambda s: print(f"    -> {s}"), scope=scope)
                status = "SUCCESS" if ok else "ERROR"
                print(f"[{status}] {msg}")
                if not ok:
                    ret = 1
            return ret
        elif "update" in sub:
            print("[*] App Encloser APT Proxy: System repositories and metadata ready.")
            return 0
        else:
            print(f"[*] App Encloser APT Proxy: Unknown apt command '{' '.join(sub)}'")
            return 0

    if cmd in ("install", "install-into"):
        scope = None
        mode_level = None
        container = None
        targets = []
        if cmd == "install-into":
            if len(argv) < 3:
                print("Usage: app-encloser install-into <container_name> <file.deb | url | package_name>")
                return 1
            container = argv[1]
            targets = [argv[2]]
        else:
            i = 1
            while i < len(argv):
                a = argv[i]
                if a == "--global":
                    scope = "global"
                    i += 1
                elif a == "--isolated":
                    scope = "isolated"
                    i += 1
                elif a.startswith("--mode="):
                    m_val = a.split("=", 1)[1].strip().lower()
                    if m_val == "global":
                        scope = "global"
                    else:
                        scope = "isolated"
                        mode_level = m_val
                    i += 1
                elif a == "--mode" and i + 1 < len(argv):
                    m_val = argv[i + 1].strip().lower()
                    if m_val == "global":
                        scope = "global"
                    else:
                        scope = "isolated"
                        mode_level = m_val
                    i += 2
                elif a in ("--container", "-c") and i + 1 < len(argv):
                    container = argv[i + 1]
                    i += 2
                else:
                    targets.append(a)
                    i += 1

        if not targets:
            print("Usage: app-encloser install [--container <name>] [--mode=strict|standard|integrated|global] <file.deb | url | package_name>")
            return 1

        target = targets[0]
        if container:
            print(f"[*] Installing '{target}' into container '{container}'...")
            ok, msg = install_into_container(container, target, status_cb=lambda s: print(f"    -> {s}"))
            status = "SUCCESS" if ok else "ERROR"
            print(f"[{status}] {msg}")
            return 0 if ok else 1

        pref_scope = scope or get_setting("install_scope", "isolated")
        if pref_scope == "global":
            print(f"[*] Installing '{target}' globally to host system...")
            ok, msg = install_globally(target, status_cb=lambda s: print(f"    -> {s}"))
        elif os.path.isfile(target) and is_supported_file(target):
            ok, msg = install_any_package(target, status_cb=lambda s: print(f"    -> {s}"))
        else:
            ok, msg = install_from_url_or_repo(target, status_cb=lambda s: print(f"    -> {s}"), scope=scope)
        if ok and pref_scope != "global" and mode_level:
            set_enclosing_level(msg, mode_level)
        status = "SUCCESS" if ok else "ERROR"
        print(f"[{status}] {msg}")
        return 0 if ok else 1

    if cmd in ("uninstall", "remove", "delete", "purge"):
        if len(argv) < 2:
            print("Usage: app-encloser uninstall <app_name>")
            return 1
        raw_name = argv[1]
        resolved = find_container_folder(raw_name)
        if resolved:
            print(f"[*] Stopping processes and removing enclosed container '{resolved}'...")
            uninstall_enclosed_app(resolved)
            print(f"[SUCCESS] Successfully uninstalled container '{resolved}'.")
            return 0
        from app_encloser.core.history import check_host_package_status
        h_info = check_host_package_status(raw_name)
        if h_info:
            print(f"[*] Removing host-installed package '{raw_name}'...")
            ok, msg = uninstall_host_package(h_info, status_cb=lambda s: print(f"    -> {s}"))
            status = "SUCCESS" if ok else "ERROR"
            print(f"[{status}] {msg}")
            return 0 if ok else 1
        print(f"[ERROR] Application or container '{raw_name}' not found in ~/EnclosedApps or tracked history.")
        return 1

    if cmd in ("run", "launch", "open"):
        if len(argv) < 2:
            print("Usage: app-encloser run <app_name> [command or args...]")
            return 1
        app_name = argv[1]
        cmd_args = argv[2:]
        return run_in_container(app_name, cmd_args)

    if cmd == "shell":
        if len(argv) < 2:
            print("Usage: app-encloser shell <app_name>")
            return 1
        app_name = argv[1]
        return open_container_shell(app_name)

    if cmd in ("kill", "stop", "force-stop"):
        if len(argv) < 2:
            print("Usage: app-encloser kill <app_name>")
            return 1
        app_name = argv[1]
        ok, msg, count = kill_app_processes(app_name)
        status = "SUCCESS" if ok else "ERROR"
        print(f"[{status}] {msg}")
        return 0 if ok else 1

    if cmd == "inspect":
        if len(argv) < 2:
            print("Usage: app-encloser inspect <app_name>")
            return 1
        app_name = argv[1]
        info = inspect_container_contents(app_name)
        print(json.dumps(info, indent=2))
        return 0

    if cmd in ("resolve-deps", "resolve", "fix"):
        if len(argv) < 2:
            print("Usage: app-encloser resolve-deps <app_name> [--yes]")
            return 1
        app_name = argv[1]
        auto_yes = "--yes" in argv or "-y" in argv
        diag = analyze_container_incompatibility(app_name)
        missing = diag.get("missing_libraries", [])
        print(f"Container: {app_name}")
        print(f"Current Status: {diag.get('status')}")
        if missing:
            print(f"Detected Missing Dependencies ({len(missing)}):")
            for m in missing:
                print(f"  • {m}")
        print("Proposed Resolution Plan:")
        print("  • Link internal container library directories")
        print("  • Ingest missing shared libraries into container app_files")
        print("  • Rebuild launch script & library path configurations")
        if not auto_yes:
            try:
                ans = input("Proceed with automated dependency resolution? [y/N]: ").strip().lower()
                if ans not in ("y", "yes"):
                    print("Resolution cancelled.")
                    return 0
            except (KeyboardInterrupt, EOFError):
                print("\nResolution cancelled.")
                return 0
        print("Executing automated resolution...")
        ok, msg, actions = resolve_container_dependencies(app_name, lambda s: print(f"  -> {s}"))
        for a in actions:
            print(f"  [+] {a}")
        status = "SUCCESS" if ok else "ERROR"
        print(f"[{status}] {msg}")
        return 0 if ok else 1

    if cmd in ("level", "enclosing-level", "isolation"):
        if len(argv) < 2:
            print("Usage: app-encloser level <app_name> [standard|strict|integrated]")
            return 1
        raw_name = argv[1]
        resolved = find_container_folder(raw_name)
        if not resolved:
            from app_encloser.core.history import check_host_package_status
            h_info = check_host_package_status(raw_name)
            if h_info:
                print(f"[INFO] '{raw_name}' is installed directly on the Host System ({h_info.get('target', raw_name)}), not inside an enclosed container.")
                print("Host applications run with full system access without container isolation boundaries.")
                print(f"To enclose it in an isolated container, run: app-encloser install {raw_name}")
                return 1
            print(f"[ERROR] Container '{raw_name}' does not exist in ~/EnclosedApps/.")
            apps = [d for d in os.listdir(ENCLOSED_DIR) if os.path.isdir(os.path.join(ENCLOSED_DIR, d))] if os.path.isdir(ENCLOSED_DIR) else []
            if apps:
                print(f"Available containers: {', '.join(sorted(apps))}")
            return 1
        app_name = resolved
        if len(argv) >= 3:
            target_level = argv[2].strip().lower()
            if target_level not in ("standard", "strict", "integrated"):
                print("Error: Invalid level. Must be 'standard', 'strict', or 'integrated'.")
                return 1
            ok = set_enclosing_level(app_name, target_level)
            if ok:
                info = get_enclosing_level_details(target_level)
                print(f"[SUCCESS] Enclosing level for {app_name} updated to: {target_level} ({info['title']})")
                return 0
            else:
                print(f"[ERROR] Failed to set enclosing level for {app_name}")
                return 1
        else:
            cur = get_enclosing_level(app_name)
            info = get_enclosing_level_details(cur)
            print(f"Container: {app_name}")
            print(f"Current Enclosing Level: {cur} ({info['title']})")
            print(f"Description: {info['description']}")
            return 0

    if cmd in ("history", "audit", "--history", "--audit"):
        print(format_audit_report())
        return 0

    if cmd == "create":
        if len(argv) < 2:
            print("Usage: app-encloser create <container_name> [--strict]")
            return 1
        cname = argv[1]
        strict = "--strict" in argv or "-s" in argv
        ok, msg = create_empty_container(cname, strict=strict)
        status = "SUCCESS" if ok else "ERROR"
        print(f"[{status}] {msg}")
        return 0 if ok else 1

    if cmd in ("export", "--export"):
        if len(argv) < 2:
            print("Usage: app-encloser export <app_name> [dest_archive.tar.gz]")
            return 1
        app_name = argv[1]
        dest = argv[2] if len(argv) > 2 else f"{app_name}-backup.tar.gz"
        ok, msg = batch_export({app_name: {"app_files": True, "userdata": True}}, dest)
        status = "SUCCESS" if ok else "ERROR"
        print(f"[{status}] {msg}")
        return 0 if ok else 1

    if cmd in ("export-all", "--export-all"):
        dest = argv[1] if len(argv) > 1 else "all-enclosed-apps.tar.gz"
        ok, msg = export_all_apps(dest)
        status = "SUCCESS" if ok else "ERROR"
        print(f"[{status}] {msg}")
        return 0 if ok else 1

    if cmd in ("scan", "--scan"):
        target = argv[1] if len(argv) > 1 else "ALL"
        if target.upper() == "ALL":
            all_apps = [a["folder"] for a in list_enclosed_apps()]
            reports = batch_security_scan(all_apps)
            print(json.dumps(reports, indent=2))
        else:
            report = scan_app_security(target)
            print(json.dumps(report, indent=2))
        return 0

    if cmd in ("list", "--list", "ls"):
        if "--json" in argv:
            apps = list_enclosed_apps()
            print(json.dumps(apps, indent=2))
            return 0
        from app_encloser.core.history import audit_all_installations
        audit_items = audit_all_installations()
        enclosed_items = [it for it in audit_items if it.get("container_present")]
        host_items = [it for it in audit_items if it.get("host_present") and not it.get("container_present")]

        print("=== Isolated Containers ===")
        if enclosed_items:
            for it in enclosed_items:
                print(f"  • {it['app_name']} [{it.get('badge', 'Isolated')}] - {it.get('path', '')}")
        else:
            print("  (No isolated containers currently installed)")

        print("\n=== Host System Applications ===")
        if host_items:
            for it in host_items:
                print(f"  • {it['app_name']} [{it.get('badge', 'Host System')}] - {it.get('command', '')}")
        else:
            print("  (No host applications tracked)")
        return 0

    if cmd in ("repair", "--repair", "doctor", "--doctor"):
        print("Self-healing and repairing all enclosed containers...")
        from app_encloser.core.diagnostic import self_heal_all_containers
        heal_results = self_heal_all_containers()
        results = repair_all_apps()
        for h in heal_results:
            if h.get("repairs_applied"):
                print(f"[HEALED] {h['folder']}: {', '.join(h['repairs_applied'])}")
        for r in results:
            status = "✓ OK" if r["success"] else "✗ FAILED"
            print(f"[{status}] {r['folder']}: {r['message']}")
        return 0

    if cmd in ("report", "--report"):
        if len(argv) < 2:
            print("Usage: app-encloser report <app_name>")
            return 1
        print(generate_diagnostic_report(argv[1]))
        return 0

    if cmd in ("self-uninstall", "uninstall-self"):
        purge = "--purge-apps" in argv or "-p" in argv or "--purge" in argv
        yes = "--yes" in argv or "-y" in argv
        if not yes:
            try:
                ans = input("Completely uninstall App Encloser from your system? [y/N]: ").strip().lower()
                if ans not in ("y", "yes"):
                    print("Aborted.")
                    return 0
                if not purge:
                    ans_p = input("Also delete all enclosed applications and user data in ~/EnclosedApps? [y/N]: ").strip().lower()
                    purge = (ans_p in ("y", "yes"))
            except (KeyboardInterrupt, EOFError):
                print("\nAborted.")
                return 0
        ok, msg = self_uninstall(purge_apps=purge)
        status = "SUCCESS" if ok else "ERROR"
        print(f"[{status}] {msg}")
        return 0 if ok else 1

    if cmd in ("settings", "config"):
        sub = argv[1:] if len(argv) > 1 else ["list"]
        subcmd = sub[0].lower()
        if subcmd in ("list", "show"):
            print(json.dumps(load_settings(), indent=2))
            return 0
        elif subcmd == "get":
            if len(sub) < 2:
                print("Usage: app-encloser settings get <key>")
                return 1
            k = sub[1]
            print(get_setting(k, "null"))
            return 0
        elif subcmd == "set":
            if len(sub) < 3:
                print("Usage: app-encloser settings set <key> <value>")
                return 1
            k, v_raw = sub[1], sub[2]
            v = True if v_raw.lower() in ("true", "1", "yes") else (False if v_raw.lower() in ("false", "0", "no") else v_raw)
            update_setting(k, v)
            print(f"Setting '{k}' updated to: {v}")
            return 0
        else:
            print(f"Unknown settings command '{subcmd}'. Available: list, get, set")
            return 1

    if os.path.isfile(argv[0]) and is_supported_file(argv[0]):
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            ok, msg = install_any_package(argv[0])
            status = "SUCCESS" if ok else "ERROR"
            print(f"[{status}] {msg}")
            return 0 if ok else 1
        return run_gui(initial_pkg=argv[0])

    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
