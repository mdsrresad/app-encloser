import os
import subprocess
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib

from app_encloser.core.config import get_setting, ENCLOSED_DIR
from app_encloser.core.container import is_app_running, get_running_app_pids


class AppRow(Gtk.ListBoxRow):
    @staticmethod
    def _has_host_desktop_entry(name: str) -> bool:
        if not name:
            return False
        clean_n = name.lower().replace("-", "").replace("_", "")
        search_dirs = [
            "/usr/share/applications",
            "/usr/local/share/applications",
            os.path.expanduser("~/.local/share/applications")
        ]
        for sdir in search_dirs:
            if not os.path.isdir(sdir):
                continue
            try:
                for f in os.listdir(sdir):
                    if not f.endswith(".desktop"):
                        continue
                    clean_f = f[:-8].lower().replace("-", "").replace("_", "")
                    if clean_n == clean_f:
                        return True
                    if len(clean_n) >= 4 and (clean_n in clean_f or clean_f in clean_n):
                        return True
            except Exception:
                pass
        return False

    def __init__(self, app: dict, edit_mode: bool, is_checked: bool, on_select_cb, on_launch_cb, on_open_dir_cb, on_terminal_cb, on_export_cb, on_info_cb, on_clear_cache_cb, on_uninstall_cb, on_kill_cb=None, on_diagnostic_cb=None, on_install_into_cb=None, on_resolve_deps_cb=None, on_change_level_cb=None, on_migrate_cb=None):
        super().__init__()
        self.app = app
        self.folder = app["folder"]
        self.show_text = (get_setting("button_style", "icons_only") != "icons_only")
        self.non_grabbing = get_setting("non_grabbing_menus", True)
        self.pids = app.get("pids") if app.get("pids") is not None else get_running_app_pids(self.folder, fast_check=True)
        self.is_running = len(self.pids) > 0
        self.on_diagnostic_cb = on_diagnostic_cb

        app_path = app.get("path") or os.path.join(ENCLOSED_DIR, self.folder)
        code_file = os.path.join(app_path, "userdata", "last_exit_code")
        self.last_exit_code = None
        if os.path.isfile(code_file):
            try:
                c_txt = open(code_file).read().strip()
                if c_txt:
                    self.last_exit_code = int(c_txt)
            except Exception:
                pass

        card_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card_box.set_margin_top(6)
        card_box.set_margin_bottom(6)
        card_box.set_margin_start(10)
        card_box.set_margin_end(10)

        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        if edit_mode:
            cb_main = Gtk.CheckButton()
            cb_main.set_active(is_checked)
            cb_main.set_valign(Gtk.Align.CENTER)
            cb_main.connect("toggled", lambda b: on_select_cb(self.folder, b.get_active()))
            top_row.append(cb_main)

        img = Gtk.Image()
        if app.get("icon"):
            img.set_from_file(app["icon"])
        else:
            img.set_from_icon_name("package-x-generic-symbolic")
        img.set_pixel_size(44)
        img.set_valign(Gtk.Align.CENTER)
        top_row.append(img)

        info_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        info_col.set_hexpand(True)
        info_col.set_valign(Gtk.Align.CENTER)

        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name_lbl = Gtk.Label(label=f"<b>{GLib.markup_escape_text(app['name'])}</b>", use_markup=True, xalign=0)
        title_row.append(name_lbl)

        is_host = app.get("is_host_app", False)
        fmt_lbl = Gtk.Label(label="HOST" if is_host else app.get("format", "DEB"))
        fmt_lbl.add_css_class("badge-format")
        title_row.append(fmt_lbl)

        lvl = app.get("enclosing_level", "standard")
        lvl_map = {
            "standard": ("Isolated", "badge-level-standard"),
            "strict": ("Strict Sandbox", "badge-level-strict"),
            "integrated": ("Integrated", "badge-level-integrated"),
            "host": ("Host System", "badge-host")
        }
        badge_text, badge_css = lvl_map.get(lvl, ("Host System", "badge-host") if is_host else ("Isolated", "badge-level-standard"))
        level_btn = Gtk.Button(label=badge_text)
        level_btn.add_css_class("badge-format")
        if badge_css:
            level_btn.add_css_class(badge_css)
        level_btn.set_tooltip_text(f"Enclosing Level: {badge_text}. Click to change." if not is_host else "Installed directly on Host System.")
        if on_change_level_cb and not is_host:
            level_btn.connect("clicked", lambda _: on_change_level_cb(self.app))
        title_row.append(level_btn)

        if is_host:
            safety_txt = app.get("safety_badge") or ("Safe to Remove" if app.get("safe_to_remove", True) else "Protected System Package")
            safety_lbl = Gtk.Label(label=safety_txt)
            safety_cls = "badge-level-integrated" if app.get("safe_to_remove", True) else "badge-level-strict"
            safety_lbl.add_css_class("badge-format")
            safety_lbl.add_css_class(safety_cls)
            title_row.append(safety_lbl)

        ram_mb = app.get("ram_mb", 0.0)
        run_txt = f"Running • {ram_mb:.0f} MB RAM" if ram_mb > 0 else "Running"
        self.run_lbl = Gtk.Label(label=run_txt)
        self.run_lbl.add_css_class("badge-format")
        self.run_lbl.set_visible(self.is_running and not is_host)
        title_row.append(self.run_lbl)

        if not is_host and self.last_exit_code is not None and self.last_exit_code != 0:
            err_lbl = Gtk.Label(label=f"Exit {self.last_exit_code}")
            err_lbl.add_css_class("badge-format")
            err_lbl.add_css_class("destructive-action")
            title_row.append(err_lbl)

        info_col.append(title_row)

        if is_host:
            clean_cmd = " ".join(app.get("command", "Installed on Host System").split())[:60]
            sub_text = f"<small>Host System • Command: {GLib.markup_escape_text(clean_cmd)}</small>"
        else:
            sub_text = f"<small>{self.folder} • Total: {app.get('total_size', '0K')} (Binaries: {app.get('app_size', '0K')}, User Data: {app.get('user_size', '0K')})</small>"

        sub_lbl = Gtk.Label(
            label=sub_text,
            use_markup=True,
            xalign=0
        )
        info_col.append(sub_lbl)
        top_row.append(info_col)

        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        actions_box.set_valign(Gtk.Align.CENTER)

        if is_host:
            if on_migrate_cb:
                migrate_btn = Gtk.Button()
                migrate_btn.add_css_class("suggested-action")
                migrate_btn.set_tooltip_text("Enclose into Isolated Container")
                if self.show_text:
                    m_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                    m_box.append(Gtk.Image.new_from_icon_name("package-x-generic-symbolic"))
                    m_box.append(Gtk.Label(label="Enclose"))
                    migrate_btn.set_child(m_box)
                else:
                    migrate_btn.set_icon_name("package-x-generic-symbolic")
                migrate_btn.connect("clicked", lambda _: on_migrate_cb(self.app, to_host=False))
                actions_box.append(migrate_btn)

            purge_btn = Gtk.Button()
            purge_btn.add_css_class("destructive-action")
            purge_btn.set_tooltip_text("Purge from Host System")
            if self.show_text:
                p_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                p_box.append(Gtk.Image.new_from_icon_name("user-trash-symbolic"))
                p_box.append(Gtk.Label(label="Purge"))
                purge_btn.set_child(p_box)
            else:
                purge_btn.set_icon_name("user-trash-symbolic")
            purge_btn.connect("clicked", lambda _: on_uninstall_cb(self.app))
            actions_box.append(purge_btn)
        else:
            is_cli_app = app.get("is_cli", False)
            if not is_cli_app:
                launch_btn = Gtk.Button()
                launch_btn.add_css_class("suggested-action")
                launch_btn.set_tooltip_text("Launch Application")
                if self.show_text:
                    l_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                    l_box.append(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
                    l_box.append(Gtk.Label(label="Launch"))
                    launch_btn.set_child(l_box)
                else:
                    launch_btn.set_icon_name("media-playback-start-symbolic")
                launch_btn.connect("clicked", lambda _: on_launch_cb(self.app))
                actions_box.append(launch_btn)

            term_btn = Gtk.Button()
            term_btn.add_css_class("suggested-action" if is_cli_app else "flat")
            term_btn.set_tooltip_text("Open Container Terminal")
            if self.show_text and is_cli_app:
                t_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                t_box.append(Gtk.Image.new_from_icon_name("utilities-terminal-symbolic"))
                t_box.append(Gtk.Label(label="Terminal"))
                term_btn.set_child(t_box)
            else:
                term_btn.set_icon_name("utilities-terminal-symbolic")
            term_btn.connect("clicked", lambda _: on_terminal_cb(self.app))
            actions_box.append(term_btn)

            files_btn = Gtk.Button()
            files_btn.add_css_class("flat")
            files_btn.set_icon_name("folder-open-symbolic")
            files_btn.set_tooltip_text("Open Container File Manager")
            files_btn.connect("clicked", lambda _: on_open_dir_cb(self.app))
            actions_box.append(files_btn)

            if on_install_into_cb:
                add_btn = Gtk.Button()
                add_btn.add_css_class("flat")
                add_btn.set_icon_name("list-add-symbolic")
                add_btn.set_tooltip_text("Install File or Command into Container")
                add_btn.connect("clicked", lambda _: on_install_into_cb(self.app))
                actions_box.append(add_btn)

            self.stop_btn = Gtk.Button()
            self.stop_btn.add_css_class("destructive-action")
            self.stop_btn.set_icon_name("process-stop-symbolic")
            self.stop_btn.set_tooltip_text("Force Stop (Running)")
            self.stop_btn.set_visible(self.is_running)
            if on_kill_cb:
                self.stop_btn.connect("clicked", lambda _: on_kill_cb(self.app))
            actions_box.append(self.stop_btn)

        dot_btn = Gtk.MenuButton()
        dot_btn.set_icon_name("view-more-symbolic")
        dot_btn.add_css_class("flat")
        dot_btn.set_tooltip_text("Options")

        popover = Gtk.Popover()
        if self.non_grabbing:
            popover.set_autohide(False)

        pop_key = Gtk.EventControllerKey()
        pop_key.connect("key-pressed", lambda _ctrl, val, _code, _st: (popover.popdown(), True)[1] if val == Gdk.KEY_Escape else False)
        popover.add_controller(pop_key)

        pop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        pop_box.set_margin_top(6)
        pop_box.set_margin_bottom(6)
        pop_box.set_margin_start(6)
        pop_box.set_margin_end(6)

        def make_pop_item(label, ic_name, cb, destructive=False):
            b = Gtk.Button()
            b.add_css_class("flat")
            if destructive:
                b.add_css_class("destructive-action")
            ib = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            ib.append(Gtk.Image.new_from_icon_name(ic_name))
            ib.append(Gtk.Label(label=label))
            b.set_child(ib)
            b.connect("clicked", lambda _b: (popover.popdown(), cb()))
            return b

        if is_host:
            pop_box.append(make_pop_item("App Details & Info...", "dialog-information-symbolic", lambda: on_info_cb(self.app)))
            if on_migrate_cb:
                pop_box.append(make_pop_item("Move to Isolated Container...", "package-x-generic-symbolic", lambda: on_migrate_cb(self.app, to_host=False)))
            pop_box.append(make_pop_item("Open Terminal on Host", "utilities-terminal-symbolic", lambda: on_terminal_cb(self.app)))
            pop_box.append(make_pop_item("Uninstall from Host", "user-trash-symbolic", lambda: on_uninstall_cb(self.app), destructive=True))
        else:
            pop_box.append(make_pop_item("App Details & Info...", "dialog-information-symbolic", lambda: on_info_cb(self.app)))
            if on_change_level_cb:
                pop_box.append(make_pop_item("Change Enclosing Level...", "security-high-symbolic", lambda: on_change_level_cb(self.app)))
            if on_migrate_cb:
                pop_box.append(make_pop_item("Move to Host System (Global)...", "package-x-generic-symbolic", lambda: on_migrate_cb(self.app, to_host=True)))
            if on_diagnostic_cb:
                diag_label = "View Error / Incompatibility..." if (self.last_exit_code is not None and self.last_exit_code != 0) else "Diagnostic Report..."
                diag_icon = "dialog-warning-symbolic" if (self.last_exit_code is not None and self.last_exit_code != 0) else "emblem-documents-symbolic"
                pop_box.append(make_pop_item(diag_label, diag_icon, lambda: on_diagnostic_cb(self.app)))
            if on_resolve_deps_cb:
                pop_box.append(make_pop_item("Resolve Dependencies...", "system-software-update-symbolic", lambda: on_resolve_deps_cb(self.app)))
            pop_box.append(make_pop_item("Open Terminal in Container", "utilities-terminal-symbolic", lambda: on_terminal_cb(self.app)))
            if on_install_into_cb:
                pop_box.append(make_pop_item("Install into this Container...", "list-add-symbolic", lambda: on_install_into_cb(self.app)))
            pop_box.append(make_pop_item("Open Container Folder", "folder-open-symbolic", lambda: on_open_dir_cb(self.app)))
            pop_box.append(make_pop_item("Export Application...", "document-save-symbolic", lambda: on_export_cb(self.app)))
            pop_box.append(make_pop_item("Clear Cache & Data...", "edit-clear-symbolic", lambda: on_clear_cache_cb(self.app)))

            self.kill_pop_item = make_pop_item("Force Stop / Kill", "process-stop-symbolic", lambda: on_kill_cb(self.app) if on_kill_cb else None, destructive=True)
            self.kill_pop_item.set_visible(self.is_running)
            pop_box.append(self.kill_pop_item)

            pop_box.append(make_pop_item("Uninstall & Wipe", "user-trash-symbolic", lambda: on_uninstall_cb(self.app), destructive=True))

        if self.non_grabbing:
            close_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            close_row.set_halign(Gtk.Align.END)
            close_b = Gtk.Button(label="Close")
            close_b.add_css_class("flat")
            close_b.connect("clicked", lambda _: popover.popdown())
            close_row.append(close_b)
            pop_box.append(close_row)

        popover.set_child(pop_box)
        dot_btn.set_popover(popover)
        actions_box.append(dot_btn)

        top_row.append(actions_box)
        card_box.append(top_row)
        self.set_child(card_box)

    def set_running_state(self, is_running: bool, pids: list, ram_mb: float = 0.0):
        self.is_running = is_running
        self.pids = pids
        if is_running:
            if ram_mb > 0:
                self.run_lbl.set_label(f"Running • {ram_mb:.0f} MB RAM")
            else:
                self.run_lbl.set_label("Running")
        self.run_lbl.set_visible(is_running and not self.app.get("is_host_app", False))
        if hasattr(self, "stop_btn"):
            self.stop_btn.set_visible(is_running)
        if hasattr(self, "kill_pop_item"):
            self.kill_pop_item.set_visible(is_running)
