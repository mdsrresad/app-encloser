import os
import shutil
import subprocess
from typing import Optional
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, GLib

from app_encloser.core.history import (
    audit_all_installations, mark_as_uninstalled, invalidate_host_discovery_cache,
    delete_history_record, clear_uninstalled_history_records
)
from app_encloser.core.config import LOCAL_BIN


class AuditHistoryDialog(Adw.Window):
    def __init__(self, parent: Gtk.Window, on_terminal_cb=None):
        super().__init__(title="Installation History & Audit", transient_for=parent, modal=True)
        self.set_default_size(680, 560)
        self.on_terminal_cb = on_terminal_cb

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", lambda _c, val, _k, _s: (self.close(), True)[1] if val == Gdk.KEY_Escape else False)
        self.add_controller(key_ctrl)

        self.toast_overlay = Adw.ToastOverlay()

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)
        main_box.append(header)

        self.page = Adw.PreferencesPage()

        grp_info = Adw.PreferencesGroup()
        grp_info.set_title("Software Environment and Command Audit")
        grp_info.set_description("Track every application installed into isolated containers and detected on your host system, along with the exact commands used.")
        self.page.add(grp_info)

        self.grp_list = Adw.PreferencesGroup()
        self.grp_list.set_title("Tracked Installations")
        self.page.add(self.grp_list)

        main_box.append(self.page)

        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom_bar.set_margin_top(10)
        bottom_bar.set_margin_bottom(12)
        bottom_bar.set_margin_start(16)
        bottom_bar.set_margin_end(16)

        self.btn_refresh = Gtk.Button(label="Refresh Audit")
        self.btn_refresh.set_icon_name("view-refresh-symbolic")
        self.btn_refresh.set_tooltip_text("Re-scan system and refresh audit history")
        self.btn_refresh.connect("clicked", self.on_refresh_clicked)
        bottom_bar.append(self.btn_refresh)

        self.btn_clear_removed = Gtk.Button(label="Clear Removed")
        self.btn_clear_removed.set_icon_name("user-trash-symbolic")
        self.btn_clear_removed.set_tooltip_text("Clear all uninstalled application records from history")
        self.btn_clear_removed.connect("clicked", self.on_clear_removed_clicked)
        bottom_bar.append(self.btn_clear_removed)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        bottom_bar.append(spacer)

        btn_close = Gtk.Button(label="Close")
        btn_close.connect("clicked", lambda _: self.close())
        bottom_bar.append(btn_close)

        main_box.append(bottom_bar)
        self.toast_overlay.set_child(main_box)
        self.set_content(self.toast_overlay)

        self.populate_list()

    def show_toast(self, text: str):
        toast = Adw.Toast.new(text)
        toast.set_timeout(3)
        self.toast_overlay.add_toast(toast)

    def on_refresh_clicked(self, _btn=None):
        self.btn_refresh.set_sensitive(False)
        invalidate_host_discovery_cache()
        items = self.populate_list()
        self.show_toast(f"Audit history refreshed ({len(items)} items)")
        GLib.timeout_add(300, lambda: self.btn_refresh.set_sensitive(True))

    def on_clear_removed_clicked(self, _btn=None):
        pruned = clear_uninstalled_history_records()
        self.populate_list()
        if pruned > 0:
            self.show_toast(f"Cleared {pruned} uninstalled record(s) from history")
        else:
            self.show_toast("No uninstalled records to clear")

    def populate_list(self):
        items = audit_all_installations()

        new_grp = Adw.PreferencesGroup()
        new_grp.set_title(f"Tracked Installations ({len(items)})")

        if not items:
            row_empty = Adw.ActionRow(title="No Installations Recorded", subtitle="Install applications via packages or terminal commands to track them.")
            new_grp.add(row_empty)
        else:
            for item in items:
                row = self._create_item_row(item)
                new_grp.add(row)

        if hasattr(self, "page") and self.grp_list is not None:
            self.page.remove(self.grp_list)
            self.grp_list = new_grp
            self.page.add(self.grp_list)

        return items

    def _create_item_row(self, item: dict) -> Adw.ActionRow:
        title = GLib.markup_escape_text(item["app_name"])
        sub_parts = []
        if item.get("status_text"):
            sub_parts.append(item["status_text"])
        if item.get("timestamp"):
            sub_parts.append(f"Recorded: {item['timestamp']}")
        if item.get("command"):
            cmd_preview = item["command"].replace("\n", " && ")
            if len(cmd_preview) > 90:
                cmd_preview = cmd_preview[:87] + "..."
            sub_parts.append(f"Command: {cmd_preview}")

        subtitle_text = GLib.markup_escape_text("\n".join(sub_parts))
        row = Adw.ActionRow(
            title=title,
            subtitle=subtitle_text
        )

        badge_lbl = Gtk.Label(label=item["badge"])
        badge_lbl.add_css_class("badge-format")
        if item.get("badge_css") == "warning":
            badge_lbl.add_css_class("badge-level-strict")
        elif item.get("badge_css") == "success":
            badge_lbl.add_css_class("badge-level-integrated")
        elif item.get("badge_css") == "accent":
            badge_lbl.add_css_class("badge-level-standard")
        row.add_suffix(badge_lbl)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.set_valign(Gtk.Align.CENTER)

        if item.get("command"):
            btn_copy = Gtk.Button()
            btn_copy.set_icon_name("edit-copy-symbolic")
            btn_copy.set_tooltip_text("Copy Install Command")
            cmd_text = item["command"]
            def do_copy(_b, t=cmd_text, b=btn_copy):
                disp = Gdk.Display.get_default()
                if disp:
                    disp.get_clipboard().set(t)
                b.set_icon_name("emblem-ok-symbolic")
                self.show_toast("Command copied to clipboard")
                GLib.timeout_add(1500, lambda: b.set_icon_name("edit-copy-symbolic"))
            btn_copy.connect("clicked", do_copy)
            btn_box.append(btn_copy)

        if item.get("container_present") and item.get("path"):
            btn_open = Gtk.Button()
            btn_open.set_icon_name("folder-open-symbolic")
            btn_open.set_tooltip_text("Open Container Folder")
            p = item["path"]
            btn_open.connect("clicked", lambda _b, path=p: subprocess.Popen(["xdg-open", path]))
            btn_box.append(btn_open)

            if self.on_terminal_cb:
                btn_term = Gtk.Button()
                btn_term.set_icon_name("utilities-terminal-symbolic")
                btn_term.set_tooltip_text("Open Terminal Shell")
                fldr = item["folder_name"]
                btn_term.connect("clicked", lambda _b, f=fldr: self.on_terminal_cb({"folder": f, "name": title}))
                btn_box.append(btn_term)

        if not item.get("container_present") and not item.get("host_present"):
            btn_del = Gtk.Button()
            btn_del.set_icon_name("user-trash-symbolic")
            btn_del.set_tooltip_text("Remove this record from history")
            btn_del.add_css_class("flat")
            def do_delete(_b, it=item):
                target_id = it.get("app_name") or it.get("folder_name", "")
                delete_history_record(target_id)
                self.populate_list()
                self.show_toast(f"Removed '{target_id}' from history")
            btn_del.connect("clicked", do_delete)
            btn_box.append(btn_del)

        row.add_suffix(btn_box)
        return row
