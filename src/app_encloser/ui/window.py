import os
import sys
import shlex
import shutil
import threading
import subprocess
from typing import Optional, List, Set, Dict, Any

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib, Gdk, Pango

from app_encloser import __version__
from app_encloser.core.config import (
    ENCLOSED_DIR, LOCAL_BIN, is_supported_file, get_setting, update_setting
)
from app_encloser.core.lifecycle import (
    list_enclosed_apps, install_any_package, install_from_url_or_repo,
    repair_all_apps, batch_uninstall, batch_clear_cache, install_into_container,
    uninstall_host_package, get_purge_command_str
)
from app_encloser.core.backup import batch_export, export_all_apps
from app_encloser.core.self_uninstall import self_uninstall

from app_encloser.ui.app_row import AppRow
from app_encloser.ui.action_bar import BatchActionBar
from app_encloser.ui.settings import SettingsWindow
from app_encloser.ui.dialogs import (
    TerminalCommandInstallDialog, InstallIntoContainerDialog, ExportSelectiveDialog,
    ConfirmUninstallDialog, SelfUninstallDialog, DiagnosticReportDialog, AppInfoDialog,
    CreateContainerDialog, ClearCacheOptionsDialog, ErrorIncompatibilityDialog,
    EnclosingLevelDialog
)
from app_encloser.core.container import kill_app_processes, is_app_running, get_running_app_pids, get_pids_ram_mb
from app_encloser.core.diagnostic import analyze_container_incompatibility, resolve_container_dependencies


class AppEncloserWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application, initial_pkg: Optional[str] = None):
        super().__init__(application=application, title="App Encloser")
        self.set_icon_name("app-encloser")
        self.set_size_request(380, 420)
        saved_w = get_setting("window_width", 800)
        saved_h = get_setting("window_height", 560)
        self.set_default_size(saved_w, saved_h)
        self.connect("close-request", self.on_close_requested)
        self._active_file_chooser = None

        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        self._load_custom_css()

        self.selected_apps: Set[str] = set()
        self.cached_apps: List[Dict[str, Any]] = []
        self.edit_mode: bool = False
        self.search_filter = ""

        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_overlay.set_child(main_box)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key_ctrl)

        header = Adw.HeaderBar()
        main_box.append(header)

        self.install_btn = Gtk.MenuButton()
        self.install_btn.add_css_class("suggested-action")
        self.install_btn.set_tooltip_text("Install Packages or Create Container")
        self.install_popover = self.build_install_popover()
        self.install_btn.set_popover(self.install_popover)
        header.pack_start(self.install_btn)

        self.menu_btn = Gtk.MenuButton()
        self.menu_btn.set_icon_name("view-more-symbolic")
        self.menu_btn.add_css_class("flat")
        self.menu_btn.set_tooltip_text("Options")
        self.main_popover = self.build_global_popover()
        self.menu_btn.set_popover(self.main_popover)
        header.pack_end(self.menu_btn)

        self.settings_btn = Gtk.Button()
        self.settings_btn.set_icon_name("emblem-system-symbolic")
        self.settings_btn.set_tooltip_text("Preferences")
        self.settings_btn.connect("clicked", lambda _: self.open_settings())
        header.pack_end(self.settings_btn)

        self.help_guide_btn = Gtk.Button()
        self.help_guide_btn.set_icon_name("help-browser-symbolic")
        self.help_guide_btn.set_tooltip_text("Architecture & User Guide")
        self.help_guide_btn.connect("clicked", lambda _: self.open_guide_dialog())
        header.pack_end(self.help_guide_btn)

        self.select_mode_btn = Gtk.Button()
        self.select_mode_btn.set_tooltip_text("Toggle Multi-Select Mode")
        self.select_mode_btn.connect("clicked", self.on_toggle_edit_mode)
        header.pack_end(self.select_mode_btn)

        self.refresh_btn = Gtk.Button()
        self.refresh_btn.set_icon_name("view-refresh-symbolic")
        self.refresh_btn.set_tooltip_text("Refresh Application List (Ctrl+R / F5)")
        self.refresh_btn.connect("clicked", lambda _: self.trigger_user_refresh())
        header.pack_end(self.refresh_btn)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Filter apps...")
        self.search_entry.set_hexpand(False)
        self.search_entry.set_max_width_chars(25)
        self.search_entry.connect("search-changed", self.on_search_changed)
        header.pack_end(self.search_entry)

        self.apply_button_style()

        self.status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.status_bar.set_margin_start(16)
        self.status_bar.set_margin_end(16)
        self.status_bar.set_margin_top(8)
        self.status_bar.set_margin_bottom(4)
        self.status_bar.add_css_class("card")

        self.status_spinner = Gtk.Spinner()
        self.status_spinner.set_size_request(20, 20)
        self.status_bar.append(self.status_spinner)

        self.status_lbl = Gtk.Label(label="", xalign=0)
        self.status_lbl.set_use_markup(True)
        self.status_lbl.set_hexpand(True)
        self.status_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        self.status_lbl.set_wrap(False)
        self.status_lbl.set_width_chars(20)
        self.status_lbl.set_max_width_chars(50)
        self.status_bar.append(self.status_lbl)

        self.status_progress = Gtk.ProgressBar()
        self.status_progress.set_valign(Gtk.Align.CENTER)
        self.status_progress.set_size_request(160, 6)
        self.status_bar.append(self.status_progress)

        self.status_bar.set_visible(False)
        main_box.append(self.status_bar)

        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.stack.set_hexpand(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        main_box.append(self.stack)

        self.empty_page = Adw.StatusPage()
        self.empty_page.set_icon_name("package-x-generic-symbolic")
        self.empty_page.set_title("No Isolated Applications")
        self.empty_page.set_description("Install packages into isolated portable containers or create an isolated environment.")

        empty_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        empty_box.set_halign(Gtk.Align.CENTER)

        btn_file = Gtk.Button(label="Install Package File...")
        btn_file.add_css_class("suggested-action")
        btn_file.add_css_class("pill")
        btn_file.connect("clicked", self.on_direct_install_clicked)
        empty_box.append(btn_file)

        btn_cmd = Gtk.Button(label="Install via Command...")
        btn_cmd.add_css_class("pill")
        btn_cmd.connect("clicked", lambda _: self.open_term_dialog())
        empty_box.append(btn_cmd)

        btn_create = Gtk.Button(label="Create Container...")
        btn_create.add_css_class("pill")
        btn_create.connect("clicked", lambda _: self.open_create_container_dialog())
        empty_box.append(btn_create)

        self.empty_page.set_child(empty_box)

        empty_scroll = Gtk.ScrolledWindow()
        empty_scroll.set_vexpand(True)
        empty_scroll.set_hexpand(True)
        empty_scroll.set_child(self.empty_page)
        self.stack.add_named(empty_scroll, "empty")

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)

        content_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content_inner.set_margin_start(16)
        content_inner.set_margin_end(16)
        content_inner.set_margin_top(12)
        content_inner.set_margin_bottom(12)
        scroll.set_child(content_inner)

        self.current_scope_filter = "all"
        self.scope_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.scope_bar.set_halign(Gtk.Align.START)
        self.scope_bar.set_margin_bottom(4)

        self.btn_scope_all = Gtk.Button(label="All")
        self.btn_scope_all.add_css_class("pill")
        self.btn_scope_all.add_css_class("suggested-action")
        self.btn_scope_all.connect("clicked", lambda _: self.set_scope_filter("all"))
        self.scope_bar.append(self.btn_scope_all)

        self.btn_scope_isolated = Gtk.Button(label="Enclosed")
        self.btn_scope_isolated.add_css_class("pill")
        self.btn_scope_isolated.connect("clicked", lambda _: self.set_scope_filter("isolated"))
        self.scope_bar.append(self.btn_scope_isolated)

        self.btn_scope_host = Gtk.Button(label="Host System")
        self.btn_scope_host.add_css_class("pill")
        self.btn_scope_host.connect("clicked", lambda _: self.set_scope_filter("host"))
        self.scope_bar.append(self.btn_scope_host)

        self.btn_scope_recent = Gtk.Button(label="Recent")
        self.btn_scope_recent.add_css_class("pill")
        self.btn_scope_recent.connect("clicked", lambda _: self.set_scope_filter("recent"))
        self.scope_bar.append(self.btn_scope_recent)

        self.btn_scope_heavy = Gtk.Button(label="Heavy")
        self.btn_scope_heavy.add_css_class("pill")
        self.btn_scope_heavy.connect("clicked", lambda _: self.set_scope_filter("heavy"))
        self.scope_bar.append(self.btn_scope_heavy)

        content_inner.append(self.scope_bar)

        self.list_box = Gtk.ListBox()
        self.list_box.add_css_class("boxed-list")
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        content_inner.append(self.list_box)
        self.stack.add_named(scroll, "list")

        self.batch_bar = BatchActionBar(
            on_toggle_all=self.on_toggle_all_clicked,
            on_launch=self.on_batch_launch,
            on_clear_cache=self.on_batch_clear_cache,
            on_export=self.on_batch_export_dialog,
            on_uninstall=self.on_batch_uninstall,
            on_done=lambda: self.set_edit_mode(False)
        )
        main_box.append(self.batch_bar)

        drop_target = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop_target.connect("drop", self.on_file_dropped)
        self.add_controller(drop_target)

        self.refresh_list()
        self._poll_timer_id = GLib.timeout_add(3000, self._poll_running_status)

        if initial_pkg and is_supported_file(initial_pkg):
            GLib.timeout_add(300, lambda: self.run_task(
                f"Installing {os.path.basename(initial_pkg)}...",
                lambda cb: install_any_package(initial_pkg, cb)
            ))

    def show_toast(self, text: str, timeout: int = 3):
        toast = Adw.Toast.new(text)
        toast.set_timeout(timeout)
        self.toast_overlay.add_toast(toast)

    def open_settings(self):
        win = SettingsWindow(self)
        win.present()

    def open_guide_dialog(self):
        from app_encloser.ui.dialogs.guide_dialog import UserGuideDialog
        UserGuideDialog(self).present()

    def on_migrate_app(self, app_data: dict, to_host: bool):
        from app_encloser.core.lifecycle import migrate_host_to_isolated, migrate_isolated_to_host
        name = app_data.get("name", "app")
        folder = app_data.get("folder", "")
        if to_host:
            def do_migrate(status_cb):
                status_cb(f"Migrating '{name}' to host system...")
                ok, msg = migrate_isolated_to_host(folder, status_cb=status_cb)
                if ok:
                    GLib.idle_add(lambda: self.load_apps(force_reload=True))
                    GLib.idle_add(self.refresh_list)
                return ok, msg
            self.run_task(f"Migrating {name} to Host...", do_migrate)
        else:
            def do_migrate(status_cb):
                status_cb(f"Enclosing '{name}' into container...")
                ok, msg = migrate_host_to_isolated(app_data, status_cb=status_cb)
                if ok:
                    GLib.idle_add(lambda: self.load_apps(force_reload=True))
                    GLib.idle_add(self.refresh_list)
                return ok, msg
            self.run_task(f"Enclosing {name}...", do_migrate)

    def apply_button_style(self):
        show_text = (get_setting("button_style", "icons_only") != "icons_only")

        if show_text:
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            box.append(Gtk.Image.new_from_icon_name("list-add-symbolic"))
            box.append(Gtk.Label(label="Install"))
            box.append(Gtk.Image.new_from_icon_name("pan-down-symbolic"))
            self.install_btn.set_child(box)
        else:
            self.install_btn.set_child(Gtk.Image.new_from_icon_name("list-add-symbolic"))

        if self.edit_mode:
            self.select_mode_btn.set_label("Done")
            self.select_mode_btn.add_css_class("suggested-action")
        else:
            if show_text:
                self.select_mode_btn.set_label("Select")
            else:
                self.select_mode_btn.set_icon_name("selection-mode-symbolic")
            self.select_mode_btn.remove_css_class("suggested-action")

        if hasattr(self, "batch_bar"):
            self.batch_bar.rebuild_buttons()

    def on_key_pressed(self, _ctrl, keyval, _keycode, state):
        if (state & Gdk.ModifierType.CONTROL_MASK) and keyval == Gdk.KEY_comma:
            self.open_settings()
            return True
        if keyval == Gdk.KEY_Escape:
            if self.search_entry.get_text():
                self.search_entry.set_text("")
                return True
            if self.edit_mode:
                self.set_edit_mode(False)
                return True
        if (state & Gdk.ModifierType.CONTROL_MASK) and keyval in (Gdk.KEY_f, Gdk.KEY_F):
            self.search_entry.grab_focus()
            return True
        if ((state & Gdk.ModifierType.CONTROL_MASK) and keyval in (Gdk.KEY_r, Gdk.KEY_R)) or keyval == Gdk.KEY_F5:
            self.trigger_user_refresh()
            return True
        return False

    def trigger_user_refresh(self):
        if hasattr(self, "refresh_btn"):
            self.refresh_btn.set_sensitive(False)
        from app_encloser.core.history import invalidate_host_discovery_cache
        invalidate_host_discovery_cache()
        self.refresh_list(force_reload=True, keep_selection=True)
        all_apps = self.load_apps(force_reload=False)
        n_iso = sum(1 for a in all_apps if not a.get("is_host_app"))
        n_host = sum(1 for a in all_apps if a.get("is_host_app"))
        self.show_toast(f"App list refreshed ({n_iso} enclosed, {n_host} host apps)")
        if hasattr(self, "refresh_btn"):
            GLib.timeout_add(300, lambda: self.refresh_btn.set_sensitive(True))

    def set_scope_filter(self, scope: str):
        self.current_scope_filter = scope
        for btn, name in (
            (self.btn_scope_all, "all"),
            (self.btn_scope_isolated, "isolated"),
            (self.btn_scope_host, "host"),
            (self.btn_scope_recent, "recent"),
            (self.btn_scope_heavy, "heavy")
        ):
            if name == scope:
                btn.add_css_class("suggested-action")
            else:
                btn.remove_css_class("suggested-action")
        self.refresh_list(force_reload=False, keep_selection=True)

    def load_apps(self, force_reload: bool = False) -> List[Dict[str, Any]]:
        if force_reload or not self.cached_apps:
            from app_encloser.core.diagnostic import self_heal_all_containers
            self_heal_all_containers()
            enclosed = list_enclosed_apps()
            from app_encloser.core.history import audit_all_installations
            audit_items = audit_all_installations()
            host_apps = []
            seen = {a["folder"].lower() for a in enclosed}
            for it in audit_items:
                if it.get("host_present") and not it.get("container_present"):
                    a_name = it.get("app_name", "")
                    if a_name.lower() in seen:
                        continue
                    seen.add(a_name.lower())
                    host_apps.append({
                        "folder": a_name,
                        "name": a_name,
                        "format": "HOST",
                        "is_host_app": True,
                        "command": it.get("command", ""),
                        "host_info": it.get("host_info", it),
                        "enclosing_level": "host",
                        "total_size": it.get("total_size", "Host"),
                        "app_size": it.get("total_size", "Host"),
                        "user_size": "0 B",
                        "size_bytes": it.get("size_bytes", 0),
                        "installed_ts": it.get("installed_ts", 0.0),
                        "installed_date": it.get("installed_date", ""),
                        "safety_badge": it.get("safety_badge", "Safe to Remove"),
                        "safe_to_remove": it.get("safe_to_remove", True),
                        "rdeps": it.get("rdeps", []),
                        "ram_mb": it.get("ram_mb", 0.0),
                        "icon": None,
                        "pids": []
                    })
            self.cached_apps = enclosed + host_apps
        return self.cached_apps

    def _load_custom_css(self):
        css = b"""
        .badge-format {
            background-color: rgba(255, 255, 255, 0.08);
            color: rgb(222, 221, 218);
            border-radius: 6px;
            padding: 2px 6px;
            font-size: 0.75rem;
            font-weight: bold;
        }
        .badge-level-strict {
            background-color: rgba(230, 97, 0, 0.2);
            color: #ffaa55;
            border: 1px solid rgba(230, 97, 0, 0.4);
            border-radius: 6px;
            padding: 2px 8px;
            font-size: 0.75rem;
            font-weight: bold;
        }
        .badge-level-standard {
            background-color: rgba(53, 132, 228, 0.2);
            color: #78aeed;
            border: 1px solid rgba(53, 132, 228, 0.4);
            border-radius: 6px;
            padding: 2px 8px;
            font-size: 0.75rem;
            font-weight: bold;
        }
        .badge-level-integrated {
            background-color: rgba(46, 194, 126, 0.2);
            color: #57e389;
            border: 1px solid rgba(46, 194, 126, 0.4);
            border-radius: 6px;
            padding: 2px 8px;
            font-size: 0.75rem;
            font-weight: bold;
        }
        .badge-host {
            background-color: rgba(220, 138, 22, 0.2);
            color: #f6d32d;
            border: 1px solid rgba(220, 138, 22, 0.4);
            border-radius: 6px;
            padding: 2px 8px;
            font-size: 0.75rem;
            font-weight: bold;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def on_toggle_edit_mode(self, _btn):
        self.set_edit_mode(not self.edit_mode)

    def set_edit_mode(self, enabled: bool):
        self.edit_mode = enabled
        self.apply_button_style()
        if not self.edit_mode:
            self.selected_apps.clear()
        all_apps = self.load_apps()
        self.batch_bar.update_state(len(self.selected_apps), len(all_apps), self.edit_mode)
        self.refresh_list(force_reload=False, keep_selection=True)

    def on_toggle_all_clicked(self):
        all_apps = [a["folder"] for a in self.load_apps()]
        if len(self.selected_apps) == len(all_apps):
            self.selected_apps.clear()
        else:
            self.selected_apps = set(all_apps)
        self.batch_bar.update_state(len(self.selected_apps), len(all_apps), self.edit_mode)
        self.refresh_list(force_reload=False, keep_selection=True)

    def on_direct_install_clicked(self, _btn):
        self._active_file_chooser = Gtk.FileChooserNative(
            title="Select Application Package",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
            accept_label="_Open",
            cancel_label="_Cancel"
        )
        def on_resp(dialog, resp):
            try:
                if resp == Gtk.ResponseType.ACCEPT:
                    gf = dialog.get_file()
                    if gf:
                        p = gf.get_path()
                        if p and is_supported_file(p):
                            self.run_task(f"Installing {os.path.basename(p)}...", lambda cb: install_any_package(p, cb))
            finally:
                self._active_file_chooser = None
        self._active_file_chooser.connect("response", on_resp)
        self._active_file_chooser.show()

    def build_global_popover(self) -> Gtk.Popover:
        pop = Gtk.Popover()
        if get_setting("non_grabbing_menus", True):
            pop.set_autohide(False)

        pop_key = Gtk.EventControllerKey()
        pop_key.connect("key-pressed", lambda _ctrl, val, _code, _st: (pop.popdown(), True)[1] if val == Gdk.KEY_Escape else False)
        pop.add_controller(pop_key)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)

        def make_item(label, ic_name, cb, destructive=False):
            b = Gtk.Button()
            b.add_css_class("flat")
            if destructive:
                b.add_css_class("destructive-action")
            ib = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            ib.append(Gtk.Image.new_from_icon_name(ic_name))
            ib.append(Gtk.Label(label=label))
            b.set_child(ib)
            b.connect("clicked", lambda _b, fn=cb: (pop.popdown(), fn()))
            return b

        box.append(make_item("Export Applications...", "document-save-symbolic", self.on_export_all_apps))
        box.append(make_item("Import Backup Archive...", "document-open-symbolic", self.on_import_clicked))
        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        box.append(make_item("Create Enclosed Container...", "folder-new-symbolic", self.open_create_container_dialog))
        box.append(make_item("Install via Command...", "utilities-terminal-symbolic", self.open_term_dialog))
        box.append(make_item("Refresh App List", "view-refresh-symbolic", self.trigger_user_refresh))
        box.append(make_item("Repair Launchers", "system-software-update-symbolic", self.on_repair_all))
        box.append(make_item("Installation History & Audit...", "view-list-symbolic", self.open_history_dialog))
        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        box.append(make_item("Preferences", "emblem-system-symbolic", self.open_settings))
        box.append(make_item("Architecture & User Guide...", "help-browser-symbolic", self.open_guide_dialog))
        box.append(make_item("About App Encloser", "help-about-symbolic", self.on_about_clicked))
        box.append(make_item("Uninstall App Encloser...", "user-trash-symbolic", self.open_self_uninstall_dialog, destructive=True))

        if get_setting("non_grabbing_menus", True):
            close_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            close_row.set_halign(Gtk.Align.END)
            close_b = Gtk.Button(label="Close")
            close_b.add_css_class("flat")
            close_b.connect("clicked", lambda _: pop.popdown())
            close_row.append(close_b)
            box.append(close_row)

        pop.set_child(box)
        return pop

    def open_term_dialog(self):
        TerminalCommandInstallDialog(
            self,
            on_install_cmd_cb=lambda q: self.run_task(f"Installing {q}...", lambda cb: install_from_url_or_repo(q, cb))
        ).show()

    def open_history_dialog(self):
        from app_encloser.ui.dialogs.history_dialog import AuditHistoryDialog
        AuditHistoryDialog(self, on_terminal_cb=self.on_open_terminal_shell).present()

    def build_install_popover(self) -> Gtk.Popover:
        pop = Gtk.Popover()
        if get_setting("non_grabbing_menus", True):
            pop.set_autohide(False)

        pop_key = Gtk.EventControllerKey()
        pop_key.connect("key-pressed", lambda _ctrl, val, _code, _st: (pop.popdown(), True)[1] if val == Gdk.KEY_Escape else False)
        pop.add_controller(pop_key)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)

        def make_action_item(label, ic_name, cb):
            b = Gtk.Button()
            b.add_css_class("flat")
            ib = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            ib.append(Gtk.Image.new_from_icon_name(ic_name))
            ib.append(Gtk.Label(label=label))
            b.set_child(ib)
            b.connect("clicked", lambda _b, fn=cb: (pop.popdown(), fn()))
            return b

        box.append(make_action_item("Install Package File...", "package-x-generic-symbolic", lambda: self.on_direct_install_clicked(None)))
        box.append(make_action_item("Install via Command...", "utilities-terminal-symbolic", self.open_term_dialog))
        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        box.append(make_action_item("Create Empty Container...", "folder-new-symbolic", self.open_create_container_dialog))

        if get_setting("non_grabbing_menus", True):
            close_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            close_row.set_halign(Gtk.Align.END)
            close_b = Gtk.Button(label="Close")
            close_b.add_css_class("flat")
            close_b.connect("clicked", lambda _: pop.popdown())
            close_row.append(close_b)
            box.append(close_row)

        pop.set_child(box)
        return pop

    def on_close_requested(self, _win):
        if getattr(self, "_poll_timer_id", None):
            try:
                GLib.source_remove(self._poll_timer_id)
            except Exception:
                pass
            self._poll_timer_id = None
        w = self.get_width() or self.get_default_size()[0]
        h = self.get_height() or self.get_default_size()[1]
        if w > 0 and h > 0:
            update_setting("window_width", w)
            update_setting("window_height", h)
        return False

    def on_batch_launch(self):
        if not self.selected_apps:
            return
        count = 0
        for f in list(self.selected_apps):
            app_dir = os.path.join(ENCLOSED_DIR, f)
            launch_sh = os.path.join(app_dir, "launch.sh")
            if os.path.isfile(launch_sh):
                subprocess.Popen([launch_sh])
                count += 1
        if count:
            self.show_toast(f"Launched {count} application(s)")

    def open_create_container_dialog(self):
        def on_created(ok, msg, name):
            if ok:
                self.refresh_list(force_reload=True)
                self.show_toast(f"Created container '{name}'")
                app_info = next((a for a in self.load_apps(force_reload=True) if a["folder"] == name), None)
                if app_info:
                    self.on_open_terminal_shell(app_info)
            else:
                self.show_toast(f"Error: {msg}")
        CreateContainerDialog(self, on_created_cb=on_created).show()

    def on_install_into_container(self, app: dict):
        folder = app["folder"]
        def on_confirmed(target: str):
            self.run_task(
                f"Installing into {folder}...",
                lambda cb: install_into_container(folder, target, cb)
            )
        InstallIntoContainerDialog(self, folder, on_confirmed).show()

    def on_open_terminal_shell(self, app: dict):
        if app.get("is_host_app"):
            if shutil.which("gnome-terminal"):
                subprocess.Popen(["gnome-terminal"])
            elif shutil.which("kgx"):
                subprocess.Popen(["kgx"])
            elif shutil.which("x-terminal-emulator"):
                subprocess.Popen(["x-terminal-emulator"])
            else:
                subprocess.Popen(["xterm"])
            self.show_toast(f"Opened terminal on host for {app['name']}")
            return

        folder = app["folder"]
        exe_path = shutil.which("app-encloser") or os.path.join(LOCAL_BIN, "app-encloser")
        if shutil.which("gnome-terminal"):
            subprocess.Popen(["gnome-terminal", "--", exe_path, "shell", folder])
        elif shutil.which("kgx"):
            subprocess.Popen(["kgx", "-e", f"{shlex.quote(exe_path)} shell {shlex.quote(folder)}"])
        elif shutil.which("x-terminal-emulator"):
            subprocess.Popen(["x-terminal-emulator", "-e", f"{shlex.quote(exe_path)} shell {shlex.quote(folder)}"])
        else:
            subprocess.Popen(["xterm", "-e", f"{shlex.quote(exe_path)} shell {shlex.quote(folder)}"])
        self.show_toast(f"Opened terminal shell for {app['name']}")

    def on_export_all_apps(self):
        all_apps = [a["folder"] for a in self.load_apps()]
        if not all_apps:
            self.show_toast("No applications currently installed to export")
            return
        ExportSelectiveDialog(
            self,
            all_apps,
            on_export_cb=lambda sels, out_p: self.run_task(
                f"Exporting all {len(sels)} application(s)...",
                lambda cb: batch_export(sels, out_p)
            ),
            is_all=True
        ).show()

    def on_batch_export_dialog(self):
        if not self.selected_apps:
            return
        ExportSelectiveDialog(
            self,
            list(self.selected_apps),
            on_export_cb=lambda sels, out_p: self.run_task(
                f"Exporting {len(sels)} app(s)...",
                lambda cb: batch_export(sels, out_p)
            )
        ).show()

    def on_export_single_app(self, app: dict):
        ExportSelectiveDialog(
            self,
            [app["folder"]],
            on_export_cb=lambda sels, out_p: self.run_task(
                f"Exporting {app['name']}...",
                lambda cb: batch_export(sels, out_p)
            )
        ).show()

    def on_search_changed(self, entry):
        self.search_filter = entry.get_text().strip().lower()
        self.refresh_list(force_reload=False, keep_selection=True)

    def refresh_list(self, force_reload: bool = False, keep_selection: bool = False):
        while True:
            child = self.list_box.get_first_child()
            if not child:
                break
            self.list_box.remove(child)

        all_apps = self.load_apps(force_reload=force_reload)
        n_iso = sum(1 for a in all_apps if not a.get("is_host_app"))
        n_host = sum(1 for a in all_apps if a.get("is_host_app"))
        if hasattr(self, "btn_scope_all"):
            self.btn_scope_all.set_label(f"All ({len(all_apps)})")
            self.btn_scope_isolated.set_label(f"Enclosed ({n_iso})")
            self.btn_scope_host.set_label(f"Host System ({n_host})")
            if hasattr(self, "btn_scope_recent"):
                self.btn_scope_recent.set_label("Recent")
            if hasattr(self, "btn_scope_heavy"):
                self.btn_scope_heavy.set_label("Heavy")

        scoped_apps = all_apps
        cur_filter = getattr(self, "current_scope_filter", "all")
        if cur_filter == "isolated":
            scoped_apps = [a for a in all_apps if not a.get("is_host_app")]
        elif cur_filter == "host":
            scoped_apps = [a for a in all_apps if a.get("is_host_app")]
        elif cur_filter == "recent":
            scoped_apps = sorted(all_apps, key=lambda a: a.get("installed_ts", 0.0), reverse=True)
        elif cur_filter == "heavy":
            scoped_apps = sorted(all_apps, key=lambda a: (a.get("ram_mb", 0.0), a.get("size_bytes", 0)), reverse=True)

        valid_folders = {a["folder"] for a in scoped_apps}
        self.selected_apps = self.selected_apps.intersection(valid_folders)
        self.batch_bar.update_state(len(self.selected_apps), len(scoped_apps), self.edit_mode)

        filtered_apps = scoped_apps
        if self.search_filter:
            filtered_apps = [
                a for a in scoped_apps
                if self.search_filter in a["name"].lower() or self.search_filter in a["folder"].lower()
            ]

        if not filtered_apps:
            if self.search_filter:
                self.empty_page.set_icon_name("system-search-symbolic")
                self.empty_page.set_title("No Applications Found")
                self.empty_page.set_description(f"No applications match '{self.search_filter}'")
            elif cur_filter == "host":
                self.empty_page.set_icon_name("emblem-system-symbolic")
                self.empty_page.set_title("No Host Applications Tracked")
                self.empty_page.set_description("Applications installed globally on host system are tracked and displayed here.")
            elif cur_filter == "recent":
                self.empty_page.set_icon_name("document-open-recent-symbolic")
                self.empty_page.set_title("No Recent Applications")
                self.empty_page.set_description("Recently installed applications will appear here.")
            elif cur_filter == "heavy":
                self.empty_page.set_icon_name("drive-harddisk-symbolic")
                self.empty_page.set_title("No Heavy Applications")
                self.empty_page.set_description("Applications consuming significant disk or memory will appear here.")
            else:
                self.empty_page.set_icon_name("package-x-generic-symbolic")
                self.empty_page.set_title("No Isolated Applications")
                self.empty_page.set_description("Install .deb, .AppImage, or .tar.gz packages into portable isolated containers.")
            self.stack.set_visible_child_name("empty")
            return

        self.stack.set_visible_child_name("list")

        for app in filtered_apps:
            fldr = app["folder"]
            is_checked = (fldr in self.selected_apps)

            def on_sel(f, active):
                if active:
                    self.selected_apps.add(f)
                else:
                    self.selected_apps.discard(f)
                self.batch_bar.update_state(len(self.selected_apps), len(all_apps), self.edit_mode)

            row = AppRow(
                app=app,
                edit_mode=self.edit_mode,
                is_checked=is_checked,
                on_select_cb=on_sel,
                on_launch_cb=self.launch_app,
                on_open_dir_cb=lambda a: subprocess.Popen(["xdg-open", a.get("path") or "/usr/share/applications"]),
                on_terminal_cb=self.on_open_terminal_shell,
                on_export_cb=self.on_export_single_app,
                on_info_cb=self.on_show_app_info,
                on_clear_cache_cb=self.on_clear_cache,
                on_uninstall_cb=self.on_uninstall_single_app,
                on_kill_cb=self.on_kill_app,
                on_diagnostic_cb=self.on_show_diagnostic_report,
                on_install_into_cb=self.on_install_into_container,
                on_resolve_deps_cb=self.on_resolve_dependencies,
                on_change_level_cb=self.on_change_enclosing_level,
                on_migrate_cb=self.on_migrate_app
            )
            self.list_box.append(row)

    def show_error_dialog(self, title: str, message: str):
        if hasattr(Adw, "MessageDialog"):
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading=title,
                body=str(message)
            )
            dialog.add_response("ok", "OK")
            dialog.set_default_response("ok")
            dialog.present()
        else:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text=title
            )
            dialog.format_secondary_text(str(message))
            dialog.connect("response", lambda d, r: d.destroy())
            dialog.present()

    def show_confirm_dialog(self, title: str, message: str, on_confirm_cb):
        if hasattr(Adw, "MessageDialog"):
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading=title,
                body=str(message)
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("confirm", "Uninstall")
            dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_default_response("confirm")
            def on_resp(_d, resp):
                if resp == "confirm":
                    on_confirm_cb()
            dialog.connect("response", on_resp)
            dialog.present()
        else:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK_CANCEL,
                text=title
            )
            dialog.format_secondary_text(str(message))
            def on_resp(d, resp):
                if resp in (Gtk.ResponseType.OK, Gtk.ResponseType.YES):
                    on_confirm_cb()
                d.destroy()
            dialog.connect("response", on_resp)
            dialog.present()

    def launch_app(self, app: dict):
        if app.get("is_host_app"):
            target_bin = shutil.which(app["name"].lower()) or shutil.which(app["folder"].lower())
            if not target_bin and app.get("host_info", {}).get("target"):
                target_bin = shutil.which(app["host_info"]["target"])
            if target_bin:
                try:
                    subprocess.Popen([target_bin])
                    self.show_toast(f"Launching {app['name']} on host...")
                except Exception as e:
                    self.show_error_dialog("Launch Failure", f"Failed to execute host binary {target_bin}:\n{e}")
            else:
                self.on_open_terminal_shell(app)
            return

        if app.get("is_cli"):
            self.on_open_terminal_shell(app)
            return
        p = app.get("launch_sh")
        if not p or not os.path.isfile(p):
            self.show_error_dialog("Launch Error", f"Launch script missing for {app['name']}")
            return
        try:
            proc = subprocess.Popen([p])
        except Exception as e:
            self.show_error_dialog("Launch Failure", f"Failed to execute {p}:\n{e}")
            return
        if get_setting("show_launch_notifications", True):
            self.show_toast(f"Launching {app['name']}...")

        checks = [0]
        def check_proc():
            checks[0] += 1
            try:
                ret = proc.poll()
                if ret is not None and ret != 0:
                    diag = analyze_container_incompatibility(app["folder"])
                    ErrorIncompatibilityDialog(
                        self,
                        app,
                        diag,
                        on_terminal_cb=self.on_open_terminal_shell,
                        on_resolve_cb=self.on_resolve_dependencies,
                        on_retry_cb=self.launch_app,
                        on_level_cb=self.on_change_enclosing_level
                    ).present()
                    self.refresh_list(keep_selection=True)
                    return False
            except Exception:
                pass
            return checks[0] < 8
        GLib.timeout_add(500, check_proc)

    def on_batch_clear_cache(self):
        folders = list(self.selected_apps)
        if not folders:
            return
        def do_clear(fldrs, c_cache, c_logs, c_user):
            self.run_task(
                f"Cleaning data for {len(fldrs)} app(s)...",
                lambda cb: (batch_clear_cache(fldrs, c_cache, c_logs, c_user), f"Cleared selected data for {len(fldrs)} application(s)")
            )
        ClearCacheOptionsDialog(self, folders, on_confirm_cb=do_clear).present()

    def on_batch_uninstall(self):
        folders = list(self.selected_apps)
        if not folders:
            return
        def on_confirm(fldrs):
            batch_uninstall(fldrs)
            self.selected_apps.clear()
            self.refresh_list(force_reload=True)
            self.show_toast(f"Removed {len(fldrs)} application(s)")
        ConfirmUninstallDialog(self, folders, on_confirm).show()

    def on_uninstall_single_app(self, app: dict):
        if app.get("is_host_app"):
            h_info = app.get("host_info", {})
            cmd_str = get_purge_command_str(h_info)
            def do_host_uninstall():
                def run_action(cb):
                    ok, msg = uninstall_host_package(h_info, cb)
                    GLib.idle_add(lambda: self.refresh_list(force_reload=True))
                    return ok, msg
                self.run_task(
                    f"Purging {app['name']} from host system...",
                    run_action
                )
            self.show_confirm_dialog(
                f"Purge {app['name']} from Host System?",
                f"This will remove the package and all its configs completely from your host OS.\n\nCommand: {cmd_str}",
                do_host_uninstall
            )
            return
        self.selected_apps = {app["folder"]}
        self.on_batch_uninstall()

    def on_clear_cache(self, app: dict):
        def do_clear(fldrs, c_cache, c_logs, c_user):
            self.run_task(
                f"Cleaning data for {app['name']}...",
                lambda cb: (batch_clear_cache(fldrs, c_cache, c_logs, c_user), f"Cleared selected data for {app['name']}")
            )
        ClearCacheOptionsDialog(self, [app["folder"]], on_confirm_cb=do_clear).present()

    def _poll_running_status(self):
        try:
            row = self.list_box.get_first_child()
            while row is not None:
                if isinstance(row, AppRow):
                    if row.app.get("is_host_app"):
                        row = row.get_next_sibling()
                        continue
                    pids = get_running_app_pids(row.folder, fast_check=True)
                    running = len(pids) > 0
                    ram_mb = get_pids_ram_mb(pids) if running else 0.0
                    row.app["ram_mb"] = ram_mb
                    if running or running != row.is_running:
                        row.set_running_state(running, pids, ram_mb=ram_mb)
                row = row.get_next_sibling()
        except Exception:
            pass
        return True

    def on_kill_app(self, app: dict):
        folder = app["folder"]
        ok, msg, count = kill_app_processes(folder)
        if count > 0:
            self.show_toast(f"Force stopped {count} process(es) for {app['name']}")
        else:
            self.show_toast(f"No active processes running for {app['name']}")
        self._poll_running_status()

    def on_show_app_info(self, app: dict):
        AppInfoDialog(
            self,
            app,
            on_terminal_cb=self.on_open_terminal_shell,
            on_open_dir_cb=lambda a: subprocess.Popen(["xdg-open", a["path"]])
        ).present()

    def on_show_diagnostic_report(self, app: dict):
        diag = analyze_container_incompatibility(app["folder"])
        if diag.get("has_error"):
            ErrorIncompatibilityDialog(
                self,
                app,
                diag,
                on_terminal_cb=self.on_open_terminal_shell,
                on_resolve_cb=self.on_resolve_dependencies,
                on_retry_cb=self.launch_app,
                on_level_cb=self.on_change_enclosing_level
            ).present()
        else:
            DiagnosticReportDialog(
                self,
                app,
                on_terminal_cb=self.on_open_terminal_shell,
                on_open_dir_cb=lambda a: subprocess.Popen(["xdg-open", a["path"]])
            ).present()

    def on_resolve_dependencies(self, app: dict):
        diag = analyze_container_incompatibility(app["folder"])
        from app_encloser.ui.dialogs.dependency_dialog import DependencyResolutionConfirmationDialog
        def do_resolve(target_app):
            self.run_task(
                f"Resolving dependencies for {target_app['name']}...",
                lambda cb: self._execute_resolve_dependencies(target_app, cb)
            )
        DependencyResolutionConfirmationDialog(self, app, diag, on_confirm_cb=do_resolve).present()

    def _execute_resolve_dependencies(self, app: dict, cb):
        ok, msg, actions = resolve_container_dependencies(app["folder"], cb)
        if ok:
            return True, f"Resolved dependencies for {app['name']}"
        else:
            return False, msg

    def on_change_enclosing_level(self, app: dict):
        def on_changed(new_level):
            self.show_toast(f"Enclosing level for {app['name']} changed to {new_level.capitalize()}.")
            self.refresh_list(force_reload=True)

        dlg = EnclosingLevelDialog(self, app, on_level_changed_cb=on_changed)
        dlg.present()

    def on_repair_all(self):
        self.run_task("Repairing desktop launchers...", lambda cb: (repair_all_apps(), "Repaired all applications"))

    def on_import_clicked(self):
        self._active_file_chooser = Gtk.FileChooserNative(
            title="Select Backup Archive",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
            accept_label="_Open",
            cancel_label="_Cancel"
        )
        def on_resp(dialog, resp):
            try:
                if resp == Gtk.ResponseType.ACCEPT:
                    gf = dialog.get_file()
                    if gf:
                        path = gf.get_path()
                        if path and (path.endswith(".tar.gz") or path.endswith(".tgz")):
                            from app_encloser.core.backup import inspect_backup_archive, import_selective
                            found = inspect_backup_archive(path)
                            if found:
                                selections = {f: {"app_files": "app_files" in parts, "userdata": "userdata" in parts} for f, parts in found.items()}
                                self.run_task(f"Restoring backup...", lambda cb: import_selective(path, selections))
            finally:
                self._active_file_chooser = None
        self._active_file_chooser.connect("response", on_resp)
        self._active_file_chooser.show()

    def on_file_dropped(self, _target, value, _x, _y):
        if value:
            path = value.get_path()
            if path and is_supported_file(path):
                self.run_task(
                    f"Installing {os.path.basename(path)}...",
                    lambda cb: install_any_package(path, cb)
                )
                return True
        return False

    def on_about_clicked(self):
        win = Gtk.Window(title="About App Encloser", transient_for=self, modal=True)
        win.set_default_size(420, 260)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)

        title_lbl = Gtk.Label(label=f"<big><b>App Encloser v{__version__}</b></big>", use_markup=True)
        box.append(title_lbl)

        desc_lbl = Gtk.Label(
            label="Standalone Portable Application Encloser for Linux.\n\n"
                  "Runs applications in isolated user directories with private configurations.\n\n"
                  "Open-source personal project provided as-is without warranty.\n"
                  "Leaves zero residual files on uninstallation.",
            justify=Gtk.Justification.CENTER,
            wrap=True
        )
        box.append(desc_lbl)

        close_btn = Gtk.Button(label="Close")
        close_btn.set_halign(Gtk.Align.CENTER)
        close_btn.connect("clicked", lambda _: win.close())
        box.append(close_btn)

        win.set_child(box)
        win.show()

    def open_self_uninstall_dialog(self):
        def on_confirm(purge):
            self_uninstall(purge_apps=purge)
            app = self.get_application()
            if app:
                app.quit()
            else:
                sys.exit(0)
        SelfUninstallDialog(self, on_confirm).show()

    def run_task(self, msg: str, fn):
        safe_msg = GLib.markup_escape_text(msg)
        self.status_lbl.set_markup(f"<b>{safe_msg}</b>")
        self.status_spinner.start()
        self.status_progress.set_fraction(0.0)
        self.status_bar.set_visible(True)

        pulse_box = [True]
        def do_pulse():
            if pulse_box[0]:
                self.status_progress.pulse()
                return True
            return False
        GLib.timeout_add(250, do_pulse)

        def worker():
            def cb(m):
                safe_m = GLib.markup_escape_text(m)
                GLib.idle_add(lambda: self.status_lbl.set_markup(f"<b>{safe_m}</b>"))
            try:
                res = fn(cb)
                if isinstance(res, tuple) and len(res) == 2:
                    ok, res_msg = res
                    if ok:
                        GLib.idle_add(lambda m=res_msg: self.show_toast(f"{m}"))
                    else:
                        GLib.idle_add(lambda m=res_msg: self.show_error_dialog("Operation Failed", str(m)))
            except Exception as e:
                err_str = str(e)
                print(f"Error in background task: {err_str}", file=sys.stderr)
                GLib.idle_add(lambda m=err_str: self.show_error_dialog("Task Error", str(m)))
            finally:
                pulse_box[0] = False
                GLib.idle_add(lambda: (
                    self.status_spinner.stop(),
                    self.status_bar.set_visible(False),
                    self.refresh_list(force_reload=True, keep_selection=True)
                ))

        threading.Thread(target=worker, daemon=True).start()
