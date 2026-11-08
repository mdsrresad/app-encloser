import os
from typing import Dict, Any, Optional
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, GLib

from app_encloser.core.container import (
    get_enclosing_level, get_enclosing_level_details, set_enclosing_level
)


class EnclosingLevelDialog(Adw.Window):
    def __init__(self, parent: Gtk.Window, app: dict, on_level_changed_cb=None):
        title = f"Enclosing Level — {app['name']}"
        super().__init__(title=title, transient_for=parent, modal=True)
        self.set_default_size(540, 520)
        self.app = app
        self.folder = app["folder"]
        self.on_level_changed_cb = on_level_changed_cb

        current_level = app.get("enclosing_level") or get_enclosing_level(self.folder)
        self.selected_level = current_level

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", lambda _c, val, _k, _s: (self.close(), True)[1] if val == Gdk.KEY_Escape else False)
        self.add_controller(key_ctrl)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)

        help_btn = Gtk.Button(icon_name="help-browser-symbolic")
        help_btn.set_tooltip_text("Open Architecture & User Guide")
        def open_guide(_btn):
            from app_encloser.ui.dialogs.guide_dialog import UserGuideDialog
            UserGuideDialog(self).present()
        help_btn.connect("clicked", open_guide)
        header.pack_end(help_btn)

        main_box.append(header)

        page = Adw.PreferencesPage()

        grp_head = Adw.PreferencesGroup()
        h_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        h_box.set_margin_top(8)
        h_box.set_margin_bottom(8)
        h_box.set_margin_start(12)
        h_box.set_margin_end(12)

        icon = Gtk.Image.new_from_icon_name("security-high-symbolic")
        icon.set_pixel_size(48)
        h_box.append(icon)

        t_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        t_col.set_hexpand(True)

        st_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        st_lbl = Gtk.Label(label=f"<b><big>{GLib.markup_escape_text(app['name'])}</big></b>", use_markup=True, xalign=0)
        st_row.append(st_lbl)

        cur_info = get_enclosing_level_details(current_level)
        badge = Gtk.Label(label=cur_info["badge"])
        badge.add_css_class("badge-format")
        if cur_info.get("badge_css"):
            badge.add_css_class(cur_info["badge_css"])
        st_row.append(badge)
        t_col.append(st_row)

        desc_lbl = Gtk.Label(
            label="<small>Select the enclosing isolation level for this container. Isolation boundaries dictate file visibility, process sandboxing, and service connectivity.</small>",
            use_markup=True,
            xalign=0,
            wrap=True
        )
        t_col.append(desc_lbl)
        h_box.append(t_col)
        grp_head.add(h_box)
        page.add(grp_head)

        grp_levels = Adw.PreferencesGroup()
        grp_levels.set_title("Isolation Profiles")

        self.rb_standard = Gtk.CheckButton()
        self.rb_standard.set_active(current_level == "standard")
        self.rb_standard.connect("toggled", lambda b: self._on_radio_toggled("standard", b.get_active()))

        row_standard = Adw.ActionRow(
            title="Standard Isolated (Recommended)",
            subtitle="Dedicated $HOME, $XDG config/data/cache, and isolated filesystem inside container. Zero host pollution without kernel namespace virtualization."
        )
        row_standard.set_icon_name("folder-symbolic")
        row_standard.add_suffix(self.rb_standard)
        row_standard.set_activatable_widget(self.rb_standard)
        grp_levels.add(row_standard)

        self.rb_strict = Gtk.CheckButton()
        self.rb_strict.set_group(self.rb_standard)
        self.rb_strict.set_active(current_level == "strict")
        self.rb_strict.connect("toggled", lambda b: self._on_radio_toggled("strict", b.get_active()))

        row_strict = Adw.ActionRow(
            title="Strict Sandbox (Bubblewrap)",
            subtitle="Kernel namespace virtualization via bwrap. Complete host filesystem and home directory tmpfs masking. Zero leak guarantee into or out of container."
        )
        row_strict.set_icon_name("security-high-symbolic")
        row_strict.add_suffix(self.rb_strict)
        row_strict.set_activatable_widget(self.rb_strict)
        grp_levels.add(row_strict)

        self.rb_integrated = Gtk.CheckButton()
        self.rb_integrated.set_group(self.rb_standard)
        self.rb_integrated.set_active(current_level == "integrated")
        self.rb_integrated.connect("toggled", lambda b: self._on_radio_toggled("integrated", b.get_active()))

        row_integrated = Adw.ActionRow(
            title="System Integrated (Service / Daemon)",
            subtitle="Binaries and userdata stay enclosed in ~/EnclosedApps, with direct network and service access for background daemons, VPNs, and system-level sockets."
        )
        row_integrated.set_icon_name("network-wired-symbolic")
        row_integrated.add_suffix(self.rb_integrated)
        row_integrated.set_activatable_widget(self.rb_integrated)
        grp_levels.add(row_integrated)

        page.add(grp_levels)

        grp_note = Adw.PreferencesGroup()
        note_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        note_box.set_margin_top(6)
        note_box.set_margin_bottom(6)
        note_box.set_margin_start(12)
        note_box.set_margin_end(12)
        note_icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic")
        note_box.append(note_icon)
        note_lbl = Gtk.Label(
            label="<small>Applying changes will immediately rebuild the container launch script and profile flags. Running instances must be stopped and relaunched to apply new boundaries.</small>",
            use_markup=True,
            xalign=0,
            wrap=True
        )
        note_lbl.set_hexpand(True)
        note_box.append(note_lbl)
        grp_note.add(note_box)
        page.add(grp_note)

        main_box.append(page)

        action_bar = Gtk.ActionBar()
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.add_css_class("flat")
        cancel_btn.connect("clicked", lambda _: self.close())
        action_bar.pack_start(cancel_btn)

        apply_btn = Gtk.Button(label="Apply Enclosing Level")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self._on_apply_clicked)
        action_bar.pack_end(apply_btn)

        main_box.append(action_bar)
        self.set_content(main_box)

    def _on_radio_toggled(self, level: str, is_active: bool):
        if is_active:
            self.selected_level = level

    def _on_apply_clicked(self, _btn):
        ok = set_enclosing_level(self.folder, self.selected_level)
        if ok and self.on_level_changed_cb:
            self.on_level_changed_cb(self.selected_level)
        self.close()
