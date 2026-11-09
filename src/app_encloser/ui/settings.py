import os
import shutil
import subprocess

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, GLib

from app_encloser import __version__
from app_encloser.core.config import (
    ENCLOSED_DIR, CACHE_DIR, get_setting, update_setting,
    invalidate_dir_size_cache, LOCAL_BIN
)


class SettingsWindow(Adw.PreferencesWindow):
    def __init__(self, parent: Gtk.Window):
        super().__init__()
        self.set_title("Preferences")
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(600, 480)
        self.parent_win = parent

        page_ui = Adw.PreferencesPage()
        page_ui.set_title("Appearance")
        page_ui.set_icon_name("preferences-desktop-theme-symbolic")

        grp_style = Adw.PreferencesGroup()
        grp_style.set_title("Interface & Controls")
        grp_style.set_description("Customize how buttons, menus, and actions look and behave.")
        page_ui.add(grp_style)

        row_btn_style = Adw.ComboRow()
        row_btn_style.set_title("Button Display Style")
        row_btn_style.set_subtitle("Show clean vector icons only or include text labels")
        btn_model = Gtk.StringList.new([
            "Icons Only (Compact & Clean)",
            "Icons and Text Labels"
        ])
        row_btn_style.set_model(btn_model)
        cur_btn_style = get_setting("button_style", "icons_only")
        row_btn_style.set_selected(1 if cur_btn_style != "icons_only" else 0)

        def on_btn_style_changed(_row, _pspec):
            sel = row_btn_style.get_selected()
            val = "icons_and_text" if sel == 1 else "icons_only"
            update_setting("button_style", val)
            if hasattr(self.parent_win, "apply_button_style"):
                self.parent_win.apply_button_style()
        row_btn_style.connect("notify::selected", on_btn_style_changed)
        grp_style.add(row_btn_style)

        row_grab = Adw.SwitchRow()
        row_grab.set_title("Allow Screenshots with Menus Open")
        row_grab.set_subtitle("Disable exclusive pointer grabs so screenshot tools work while dropdown menus are open")
        row_grab.set_active(get_setting("non_grabbing_menus", True))
        row_grab.connect("notify::active", lambda r, _: update_setting("non_grabbing_menus", r.get_active()))
        grp_style.add(row_grab)

        self.add(page_ui)

        page_install = Adw.PreferencesPage()
        page_install.set_title("Installation")
        page_install.set_icon_name("system-software-install-symbolic")

        grp_scope = Adw.PreferencesGroup()
        grp_scope.set_title("Container Settings")
        grp_scope.set_description("Control isolated application storage and options.")
        page_install.add(grp_scope)

        row_dir = Adw.ActionRow()
        row_dir.set_title("Container Directory")
        row_dir.set_subtitle(ENCLOSED_DIR)
        open_dir_btn = Gtk.Button(label="Open Folder")
        open_dir_btn.set_valign(Gtk.Align.CENTER)
        open_dir_btn.connect("clicked", lambda _: subprocess.Popen(["xdg-open", ENCLOSED_DIR]))
        row_dir.add_suffix(open_dir_btn)
        grp_scope.add(row_dir)

        row_scope = Adw.ComboRow()
        row_scope.set_title("Default Installation Target")
        row_scope.set_subtitle("Choose isolated container or global system installation")
        scope_model = Gtk.StringList.new([
            "Isolated Container (~/EnclosedApps)",
            "Global System (/usr via APT)",
            "Always Ask Before Installing"
        ])
        row_scope.set_model(scope_model)
        cur_scope = get_setting("install_scope", "isolated")
        if cur_scope == "global":
            row_scope.set_selected(1)
        elif cur_scope == "ask":
            row_scope.set_selected(2)
        else:
            row_scope.set_selected(0)

        def on_scope_changed(_row, _pspec):
            sel = row_scope.get_selected()
            val = "isolated" if sel == 0 else ("global" if sel == 1 else "ask")
            update_setting("install_scope", val)
            if hasattr(self.parent_win, "show_toast"):
                self.parent_win.show_toast(f"Target set to: {val}")
        row_scope.connect("notify::selected", on_scope_changed)
        grp_scope.add(row_scope)

        grp_guard = Adw.PreferencesGroup()
        grp_guard.set_title("Terminal & AI Guard")
        grp_guard.set_description("Intercept laptop terminal install commands to protect your Host OS from pollution.")
        page_install.add(grp_guard)

        row_guard = Adw.SwitchRow()
        row_guard.set_title("Terminal Install Interceptor (Human & AI Guard)")
        row_guard.set_subtitle("Intercept apt, npm, pip, uv, cargo, and brew installs in terminal to ask for Complete Encloser, Directory Encloser, or Host OS")
        row_guard.set_active(get_setting("terminal_guard_enabled", True))
        def on_guard_toggled(r, _):
            val = r.get_active()
            from app_encloser.core.terminal_guard import set_terminal_guard_active
            set_terminal_guard_active(val)
            if hasattr(self.parent_win, "show_toast"):
                self.parent_win.show_toast(f"Terminal Guard {'enabled' if val else 'disabled'}")
        row_guard.connect("notify::active", on_guard_toggled)
        grp_guard.add(row_guard)

        grp_baseline = Adw.PreferencesGroup()
        grp_baseline.set_title("Host OS Baseline")
        grp_baseline.set_description("Manage clean operating system package baseline snapshots.")
        page_install.add(grp_baseline)

        row_baseline = Adw.ActionRow()
        row_baseline.set_title("Host OS Baseline Snapshot")
        row_baseline.set_subtitle("Lock currently installed host packages as your clean OS baseline so only future additions appear in Host System")

        box_baseline_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box_baseline_btns.set_valign(Gtk.Align.CENTER)

        btn_lock = Gtk.Button(label="Lock Baseline")
        btn_lock.add_css_class("suggested-action")
        def do_lock(_btn):
            from app_encloser.core.history import lock_current_os_baseline
            ok, msg = lock_current_os_baseline()
            if hasattr(self.parent_win, "show_toast"):
                self.parent_win.show_toast(msg)
            if hasattr(self.parent_win, "load_apps"):
                self.parent_win.load_apps(force_reload=True)
                self.parent_win.refresh_list()
        btn_lock.connect("clicked", do_lock)
        box_baseline_btns.append(btn_lock)

        btn_reset = Gtk.Button(label="Reset")
        def do_reset(_btn):
            from app_encloser.core.history import reset_os_baseline
            ok, msg = reset_os_baseline()
            if hasattr(self.parent_win, "show_toast"):
                self.parent_win.show_toast(msg)
            if hasattr(self.parent_win, "load_apps"):
                self.parent_win.load_apps(force_reload=True)
                self.parent_win.refresh_list()
        btn_reset.connect("clicked", do_reset)
        box_baseline_btns.append(btn_reset)

        row_baseline.add_suffix(box_baseline_btns)
        grp_baseline.add(row_baseline)

        self.add(page_install)

        page_desk = Adw.PreferencesPage()
        page_desk.set_title("Desktop & Storage")
        page_desk.set_icon_name("preferences-desktop-display-symbolic")

        grp_desk = Adw.PreferencesGroup()
        grp_desk.set_title("Desktop Integration")
        page_desk.add(grp_desk)

        row_zero_dup = Adw.SwitchRow()
        row_zero_dup.set_title("Purge Duplicate Launchers")
        row_zero_dup.set_subtitle("Automatically remove obsolete or dead desktop launcher entries")
        row_zero_dup.set_active(get_setting("zero_duplicate_icons", True))
        row_zero_dup.connect("notify::active", lambda r, _: update_setting("zero_duplicate_icons", r.get_active()))
        grp_desk.add(row_zero_dup)

        row_notif = Adw.SwitchRow()
        row_notif.set_title("Launch Notifications")
        row_notif.set_subtitle("Display notification banner when an application is launched")
        row_notif.set_active(get_setting("show_launch_notifications", True))
        row_notif.connect("notify::active", lambda r, _: update_setting("show_launch_notifications", r.get_active()))
        grp_desk.add(row_notif)

        grp_maint = Adw.PreferencesGroup()
        grp_maint.set_title("Maintenance & Backup")
        page_desk.add(grp_maint)

        row_exp_all = Adw.ActionRow()
        row_exp_all.set_title("Export All Applications")
        row_exp_all.set_subtitle("Create a complete archive of all enclosed applications")
        exp_all_btn = Gtk.Button(label="Export All...")
        exp_all_btn.set_valign(Gtk.Align.CENTER)
        def on_exp_all_click(_b):
            self.close()
            if hasattr(self.parent_win, "on_export_all_apps"):
                self.parent_win.on_export_all_apps()
        exp_all_btn.connect("clicked", on_exp_all_click)
        row_exp_all.add_suffix(exp_all_btn)
        grp_maint.add(row_exp_all)

        row_repair = Adw.ActionRow()
        row_repair.set_title("Repair Desktop Launchers")
        row_repair.set_subtitle("Re-verify icons, desktop shortcuts, and launch scripts")
        repair_btn = Gtk.Button(label="Repair All")
        repair_btn.set_valign(Gtk.Align.CENTER)
        def on_repair_click(_b):
            self.close()
            if hasattr(self.parent_win, "on_repair_all"):
                self.parent_win.on_repair_all()
        repair_btn.connect("clicked", on_repair_click)
        row_repair.add_suffix(repair_btn)
        grp_maint.add(row_repair)

        row_clr_cache = Adw.ActionRow()
        row_clr_cache.set_title("Clear Temporary Cache")
        row_clr_cache.set_subtitle("Free disk space by wiping temporary files in cache directory")
        clr_cache_btn = Gtk.Button(label="Clear Cache")
        clr_cache_btn.set_valign(Gtk.Align.CENTER)
        def on_clear_cache_click(_b):
            invalidate_dir_size_cache()
            if os.path.isdir(CACHE_DIR):
                shutil.rmtree(CACHE_DIR, ignore_errors=True)
                os.makedirs(CACHE_DIR, exist_ok=True)
            if hasattr(self.parent_win, "show_toast"):
                self.parent_win.show_toast("Cache cleared successfully")
        clr_cache_btn.connect("clicked", on_clear_cache_click)
        row_clr_cache.add_suffix(clr_cache_btn)
        grp_maint.add(row_clr_cache)

        grp_danger = Adw.PreferencesGroup()
        grp_danger.set_title("Self-Uninstall")
        grp_danger.set_description("Completely remove App Encloser from your system.")
        page_desk.add(grp_danger)

        row_self_un = Adw.ActionRow()
        row_self_un.set_title("Uninstall App Encloser")
        row_self_un.set_subtitle("Remove App Encloser binary, desktop shortcuts, and configuration")
        self_un_btn = Gtk.Button(label="Uninstall...")
        self_un_btn.add_css_class("destructive-action")
        self_un_btn.set_valign(Gtk.Align.CENTER)
        def on_self_un_click(_b):
            self.close()
            if hasattr(self.parent_win, "open_self_uninstall_dialog"):
                self.parent_win.open_self_uninstall_dialog()
        self_un_btn.connect("clicked", on_self_un_click)
        row_self_un.add_suffix(self_un_btn)
        grp_danger.add(row_self_un)

        self.add(page_desk)

        page_ai = Adw.PreferencesPage()
        page_ai.set_title("AI & MCP")
        page_ai.set_icon_name("network-server-symbolic")

        grp_mcp = Adw.PreferencesGroup()
        grp_mcp.set_title("Model Context Protocol (MCP)")
        grp_mcp.set_description("Connect AI coding assistants (Claude Desktop, Cursor, Aider, VS Code) to inspect, execute, and manage enclosed containers.")
        page_ai.add(grp_mcp)

        row_mcp_toggle = Adw.SwitchRow()
        row_mcp_toggle.set_title("Enable MCP Server")
        row_mcp_toggle.set_subtitle("Allow external AI agents to invoke container tools via 'app-encloser --mcp'")
        row_mcp_toggle.set_active(get_setting("mcp_enabled", True))
        row_mcp_toggle.connect("notify::active", lambda r, _: update_setting("mcp_enabled", r.get_active()))
        grp_mcp.add(row_mcp_toggle)

        row_mcp_cfg = Adw.ActionRow()
        row_mcp_cfg.set_title("Claude Desktop / Cursor Configuration")
        row_mcp_cfg.set_subtitle("Copy the JSON configuration snippet to clipboard")
        btn_copy_cfg = Gtk.Button(label="Copy JSON")
        btn_copy_cfg.set_valign(Gtk.Align.CENTER)
        def on_copy_mcp_json(_b):
            exe_p = shutil.which("app-encloser") or os.path.join(LOCAL_BIN, "app-encloser")
            cfg_snippet = f'{{\n  "mcpServers": {{\n    "app-encloser": {{\n      "command": "{exe_p}",\n      "args": ["--mcp"]\n    }}\n  }}\n}}'
            disp = Gdk.Display.get_default()
            if disp:
                disp.get_clipboard().set(cfg_snippet)
            if hasattr(self.parent_win, "show_toast"):
                self.parent_win.show_toast("Copied MCP JSON configuration to clipboard")
            btn_copy_cfg.set_label("Copied!")
        btn_copy_cfg.connect("clicked", on_copy_mcp_json)
        row_mcp_cfg.add_suffix(btn_copy_cfg)
        grp_mcp.add(row_mcp_cfg)

        self.add(page_ai)

        page_about = Adw.PreferencesPage()
        page_about.set_title("About")
        page_about.set_icon_name("help-about-symbolic")

        grp_about = Adw.PreferencesGroup()
        grp_about.set_title("Project Information")
        page_about.add(grp_about)

        row_ver = Adw.ActionRow()
        row_ver.set_title("App Encloser")
        row_ver.set_subtitle(f"Version {__version__} (Open Source Project)")
        grp_about.add(row_ver)

        row_update = Adw.ActionRow()
        row_update.set_title("Check for Updates")
        row_update.set_subtitle("Check GitHub Releases for the latest version")
        btn_update = Gtk.Button(label="Check Now")
        btn_update.set_valign(Gtk.Align.CENTER)

        def on_check_clicked(_btn):
            btn_update.set_sensitive(False)
            btn_update.set_label("Checking...")
            import threading
            from app_encloser.core.updater import check_for_updates
            def worker():
                has_update, new_ver, details = check_for_updates()
                def on_done():
                    btn_update.set_sensitive(True)
                    btn_update.set_label("Check Now")
                    if has_update and new_ver and details:
                        row_update.set_subtitle(f"Update available: v{new_ver}! Visit {details.get('html_url')}")
                    elif details:
                        row_update.set_subtitle(f"Up to date (v{__version__})")
                    else:
                        row_update.set_subtitle("Unable to check (offline or rate limited)")
                GLib.idle_add(on_done)
            threading.Thread(target=worker, daemon=True).start()

        btn_update.connect("clicked", on_check_clicked)
        row_update.add_suffix(btn_update)
        grp_about.add(row_update)

        row_warn = Adw.ActionRow()
        row_warn.set_title("Disclaimer & Project Status")
        row_warn.set_subtitle("Standalone personal project provided as-is without warranty or maintenance guarantee. Use at your own risk.")
        grp_about.add(row_warn)

        self.add(page_about)
