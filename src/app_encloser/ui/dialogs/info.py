import os
import shutil
import subprocess
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, GLib

from app_encloser.core.config import ENCLOSED_DIR, APPS_DIR, LOCAL_BIN
from app_encloser.core.container import is_strict_sandbox, inspect_container_contents, kill_app_processes
from app_encloser.core.lifecycle import get_purge_command_str


class AppInfoDialog(Adw.Window):
    def __init__(self, parent: Gtk.Window, app: dict, on_terminal_cb=None, on_open_dir_cb=None):
        super().__init__(title=f"{app['name']} — Details", transient_for=parent, modal=False)
        self.set_default_size(560, 480)
        self.app = app
        self.on_terminal_cb = on_terminal_cb
        self.on_open_dir_cb = on_open_dir_cb

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", lambda _c, val, _k, _s: (self.close(), True)[1] if val == Gdk.KEY_Escape else False)
        self.add_controller(key_ctrl)

        is_host = bool(app.get("is_host_app"))
        h_info = app.get("host_info", {})
        if not isinstance(h_info, dict):
            h_info = {}

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)
        main_box.append(header)

        page = Adw.PreferencesPage()

        grp_summary = Adw.PreferencesGroup()
        summary_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        summary_row.set_margin_top(12)
        summary_row.set_margin_bottom(12)
        summary_row.set_margin_start(16)
        summary_row.set_margin_end(16)

        img = Gtk.Image()
        if app.get("icon") and os.path.isfile(app["icon"]):
            img.set_from_file(app["icon"])
        else:
            img.set_from_icon_name("package-x-generic-symbolic")
        img.set_pixel_size(56)
        summary_row.append(img)

        info_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_col.set_hexpand(True)
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_name = Gtk.Label(label=f"<b><big>{GLib.markup_escape_text(app['name'])}</big></b>", use_markup=True, xalign=0)
        title_box.append(lbl_name)

        fmt_badge = Gtk.Label(label="HOST" if is_host else app.get("format", "DEB"))
        fmt_badge.add_css_class("badge-format")
        title_box.append(fmt_badge)

        if is_host:
            safety_txt = app.get("safety_badge") or ("Safe to Remove" if app.get("safe_to_remove", True) else "Protected System Package")
            safety_lbl = Gtk.Label(label=safety_txt)
            safety_cls = "badge-level-integrated" if app.get("safe_to_remove", True) else "badge-level-strict"
            safety_lbl.add_css_class(safety_cls)
            title_box.append(safety_lbl)

        info_col.append(title_box)

        sub_txt = f"<small>Host Installation • {app.get('command') or h_info.get('type', 'apt_package')}</small>" if is_host else f"<small>Container: {app['folder']}</small>"
        lbl_folder = Gtk.Label(label=sub_txt, use_markup=True, xalign=0)
        info_col.append(lbl_folder)
        summary_row.append(info_col)
        grp_summary.add(summary_row)
        page.add(grp_summary)

        if is_host:
            grp_host = Adw.PreferencesGroup()
            grp_host.set_title("Host Package Summary")

            row_pname = Adw.ActionRow(title="Package Name", subtitle=app["name"])
            row_pname.set_icon_name("package-x-generic-symbolic")
            grp_host.add(row_pname)

            ver = h_info.get("version") or ""
            if not ver and shutil.which("dpkg-query"):
                try:
                    res_v = subprocess.run(["dpkg-query", "-W", "-f=${Version}", app["name"]], capture_output=True, text=True, timeout=2)
                    if res_v.returncode == 0 and res_v.stdout.strip():
                        ver = res_v.stdout.strip()
                except Exception:
                    pass
            if not ver:
                ver = "Host Installed"
            row_ver = Adw.ActionRow(title="Installed Version", subtitle=ver)
            row_ver.set_icon_name("software-properties-symbolic")
            grp_host.add(row_ver)

            src_type = h_info.get("type") or app.get("install_type", "apt_package")
            src_labels = {
                "apt_package": "APT System Package",
                "uv_tool": "UV Global Tool",
                "pip_user": "Pip User Package",
                "cargo_bin": "Cargo Binary (~/.cargo/bin)",
                "local_bin": "Local Binary (~/.local/bin)",
                "homebrew": "Homebrew Package",
                "npm_global": "NPM Global Package",
            }
            row_src = Adw.ActionRow(title="Installation Source", subtitle=src_labels.get(src_type, str(src_type).replace("_", " ").title()))
            row_src.set_icon_name("system-software-install-symbolic")
            grp_host.add(row_src)

            safety_sub = "No reverse dependencies detected" if app.get("safe_to_remove", True) else "System components depend on this package"
            row_safe = Adw.ActionRow(title="Safety Status", subtitle=f"{app.get('safety_badge', 'Safe to Remove')} • {safety_sub}")
            row_safe.set_icon_name("security-high-symbolic")
            grp_host.add(row_safe)

            page.add(grp_host)

            grp_dep = Adw.PreferencesGroup()
            grp_dep.set_title("Dependency & Removal Analysis")

            rdeps = app.get("rdeps", [])
            if not rdeps:
                rdeps_str = "None (Safe to remove, no other packages depend on this)"
            else:
                rdeps_str = f"{len(rdeps)} package(s): " + ", ".join(rdeps[:5])
                if len(rdeps) > 5:
                    rdeps_str += f" (+{len(rdeps) - 5} more)"
            row_rdeps = Adw.ActionRow(title="Reverse Dependencies", subtitle=rdeps_str)
            row_rdeps.set_icon_name("network-wired-symbolic")
            grp_dep.add(row_rdeps)

            row_hsize = Adw.ActionRow(title="Total Disk Footprint", subtitle=app.get("total_size", "Unknown"))
            row_hsize.set_icon_name("drive-harddisk-symbolic")
            grp_dep.add(row_hsize)

            purge_cmd = get_purge_command_str(h_info if h_info else app)
            row_purge = Adw.ActionRow(title="Purge Command", subtitle=purge_cmd)
            row_purge.set_icon_name("utilities-terminal-symbolic")
            grp_dep.add(row_purge)

            page.add(grp_dep)

        else:
            grp_loc = Adw.PreferencesGroup()
            grp_loc.set_title("Container and Paths")

            app_dir = app.get("path") or os.path.join(ENCLOSED_DIR, app["folder"])
            row_dir = Adw.ActionRow(title="Container Directory", subtitle=app_dir)
            row_dir.set_icon_name("folder-symbolic")
            grp_loc.add(row_dir)

            t_file = os.path.join(app_dir, ".target_exec")
            target_exec = open(t_file, encoding="utf-8").read().strip() if os.path.isfile(t_file) else "Default package launcher"
            row_exec = Adw.ActionRow(title="Target Executable", subtitle=target_exec)
            row_exec.set_icon_name("application-x-executable-symbolic")
            grp_loc.add(row_exec)

            desk_file = os.path.join(APPS_DIR, f"{app['folder']}.desktop")
            desk_stat = "Registered in desktop app grid" if os.path.lexists(desk_file) else "Desktop launcher not registered"
            row_desk = Adw.ActionRow(title="Desktop Integration", subtitle=desk_stat)
            row_desk.set_icon_name("preferences-desktop-display-symbolic")
            grp_loc.add(row_desk)
            page.add(grp_loc)

            grp_storage = Adw.PreferencesGroup()
            grp_storage.set_title("Disk Storage Footprint")

            row_total = Adw.ActionRow(title="Total Disk Space", subtitle=app.get("total_size", "Unknown"))
            row_total.set_icon_name("drive-harddisk-symbolic")
            grp_storage.add(row_total)

            row_bin = Adw.ActionRow(title="Application Binaries (app_files)", subtitle=app.get("app_size", "Unknown"))
            row_bin.set_icon_name("package-x-generic-symbolic")
            grp_storage.add(row_bin)

            row_user = Adw.ActionRow(title="User Data and Cache (userdata)", subtitle=app.get("user_size", "Unknown"))
            row_user.set_icon_name("user-home-symbolic")
            grp_storage.add(row_user)
            page.add(grp_storage)

            grp_sbox = Adw.PreferencesGroup()
            grp_sbox.set_title("Sandbox and Security Isolation")

            is_strict = is_strict_sandbox(app_dir)
            sbox_title = "Bubblewrap Strict Sandbox" if is_strict else "Standard Bubblewrap Sandbox"
            sbox_sub = "Host /home masked with tmpfs • Isolated container userdata"
            row_sbox = Adw.ActionRow(title=sbox_title, subtitle=sbox_sub)
            row_sbox.set_icon_name("security-high-symbolic")
            grp_sbox.add(row_sbox)
            page.add(grp_sbox)

            insp = inspect_container_contents(app["folder"])

            grp_contents = Adw.PreferencesGroup()
            grp_contents.set_title("Container Binaries & Dependencies")

            bin_list = ", ".join(insp["binaries"][:6]) if insp["binaries"] else "Default launcher"
            if insp["total_binaries"] > 6:
                bin_list += f" (+{insp['total_binaries'] - 6} more)"
            row_bins = Adw.ActionRow(title="Installed Binaries", subtitle=bin_list)
            row_bins.set_icon_name("application-x-executable-symbolic")
            grp_contents.add(row_bins)

            row_libs = Adw.ActionRow(title="Shared Dependencies", subtitle=f"{insp['total_libraries']} isolated library files (.so)")
            row_libs.set_icon_name("system-software-install-symbolic")
            grp_contents.add(row_libs)
            page.add(grp_contents)

            grp_env = Adw.PreferencesGroup()
            grp_env.set_title("Container Environment")
            row_home = Adw.ActionRow(title="Isolated $HOME", subtitle=os.path.join(app_dir, "userdata", "home"))
            row_home.set_icon_name("user-home-symbolic")
            grp_env.add(row_home)

            row_path = Adw.ActionRow(title="Binary $PATH", subtitle=f"{app_dir}/app_files/usr/bin:...:$PATH")
            row_path.set_icon_name("utilities-terminal-symbolic")
            grp_env.add(row_path)
            page.add(grp_env)

        main_box.append(page)

        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom_bar.set_margin_top(10)
        bottom_bar.set_margin_bottom(12)
        bottom_bar.set_margin_start(16)
        bottom_bar.set_margin_end(16)

        if is_host:
            host_path = app.get("path") or h_info.get("path")
            if not host_path:
                which_p = shutil.which(app["name"].lower()) or shutil.which(app["folder"].lower())
                if which_p and os.path.exists(which_p):
                    host_path = which_p
            if host_path and os.path.exists(host_path):
                folder_target = host_path if os.path.isdir(host_path) else os.path.dirname(host_path)
                if os.path.isdir(folder_target):
                    btn_folder = Gtk.Button(label="Open Folder")
                    btn_folder.set_icon_name("folder-open-symbolic")
                    btn_folder.connect("clicked", lambda _: subprocess.Popen(["xdg-open", folder_target]))
                    bottom_bar.append(btn_folder)

            btn_term = Gtk.Button(label="Terminal")
            btn_term.set_icon_name("utilities-terminal-symbolic")
            def on_host_term_click(_b):
                if self.on_terminal_cb:
                    self.on_terminal_cb(self.app)
                else:
                    if shutil.which("gnome-terminal"):
                        subprocess.Popen(["gnome-terminal"])
                    elif shutil.which("kgx"):
                        subprocess.Popen(["kgx"])
                    elif shutil.which("x-terminal-emulator"):
                        subprocess.Popen(["x-terminal-emulator"])
                    else:
                        subprocess.Popen(["xterm"])
            btn_term.connect("clicked", on_host_term_click)
            bottom_bar.append(btn_term)

            spacer = Gtk.Box()
            spacer.set_hexpand(True)
            bottom_bar.append(spacer)

            btn_copy = Gtk.Button(label="Copy Details")
            btn_copy.set_icon_name("edit-copy-symbolic")
            def on_host_copy_click(_b):
                text = (
                    f"Host Package: {app['name']}\n"
                    f"Version: {ver}\n"
                    f"Source: {src_labels.get(src_type, src_type)}\n"
                    f"Safety: {app.get('safety_badge', 'Safe to Remove')}\n"
                    f"Dependencies: {rdeps_str}\n"
                    f"Disk Footprint: {app.get('total_size', 'Unknown')}\n"
                    f"Purge Command: {purge_cmd}\n"
                )
                disp = Gdk.Display.get_default()
                if disp:
                    disp.get_clipboard().set(text)
                btn_copy.set_label("Copied!")
            btn_copy.connect("clicked", on_host_copy_click)
            bottom_bar.append(btn_copy)

            btn_close = Gtk.Button(label="Close")
            btn_close.connect("clicked", lambda _: self.close())
            bottom_bar.append(btn_close)

        else:
            btn_folder = Gtk.Button(label="Open Folder")
            btn_folder.set_icon_name("folder-open-symbolic")
            def on_folder_click(_b):
                if self.on_open_dir_cb:
                    self.on_open_dir_cb(self.app)
                else:
                    subprocess.Popen(["xdg-open", app_dir])
            btn_folder.connect("clicked", on_folder_click)
            bottom_bar.append(btn_folder)

            btn_term = Gtk.Button(label="Terminal Shell")
            btn_term.set_icon_name("utilities-terminal-symbolic")
            def on_term_click(_b):
                if self.on_terminal_cb:
                    self.on_terminal_cb(self.app)
                else:
                    exe = shutil.which("app-encloser") or os.path.join(LOCAL_BIN, "app-encloser")
                    if shutil.which("gnome-terminal"):
                        subprocess.Popen(["gnome-terminal", "--", exe, "shell", app["folder"]])
                    elif shutil.which("kgx"):
                        subprocess.Popen(["kgx", "-e", f"{exe} shell {app['folder']}"])
                    elif shutil.which("x-terminal-emulator"):
                        subprocess.Popen(["x-terminal-emulator", "-e", f"{exe} shell {app['folder']}"])
                    else:
                        subprocess.Popen(["xterm", "-e", f"{exe} shell {app['folder']}"])
            btn_term.connect("clicked", on_term_click)
            bottom_bar.append(btn_term)

            if insp["running"]:
                btn_stop = Gtk.Button(label=f"Force Stop ({len(insp['pids'])})")
                btn_stop.add_css_class("destructive-action")
                btn_stop.set_icon_name("process-stop-symbolic")
                def on_stop_click(_b):
                    kill_app_processes(app["folder"])
                    btn_stop.set_label("Stopped")
                    btn_stop.set_sensitive(False)
                btn_stop.connect("clicked", on_stop_click)
                bottom_bar.append(btn_stop)

            spacer = Gtk.Box()
            spacer.set_hexpand(True)
            bottom_bar.append(spacer)

            btn_copy = Gtk.Button(label="Copy Details")
            btn_copy.set_icon_name("edit-copy-symbolic")
            def on_copy_click(_b):
                text = (
                    f"Application: {app['name']}\n"
                    f"Container: {app['folder']}\n"
                    f"Format: {app.get('format', 'DEB')}\n"
                    f"Container Path: {app_dir}\n"
                    f"Target Executable: {target_exec}\n"
                    f"Total Size: {app.get('total_size', 'Unknown')}\n"
                    f"App Binaries: {app.get('app_size', 'Unknown')}\n"
                    f"User Data: {app.get('user_size', 'Unknown')}\n"
                    f"Sandbox: {sbox_title}\n"
                )
                disp = Gdk.Display.get_default()
                if disp:
                    disp.get_clipboard().set(text)
                btn_copy.set_label("Copied!")
            btn_copy.connect("clicked", on_copy_click)
            bottom_bar.append(btn_copy)

            btn_close = Gtk.Button(label="Close")
            btn_close.connect("clicked", lambda _: self.close())
            bottom_bar.append(btn_close)

        main_box.append(bottom_bar)
        self.set_content(main_box)
