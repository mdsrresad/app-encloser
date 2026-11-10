import os
from typing import List

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib


class ConfirmUninstallDialog(Gtk.Window):
    def __init__(self, parent: Gtk.Window, folders: List[str], on_confirm_cb):
        super().__init__(title="Confirm Uninstall", transient_for=parent, modal=True)
        self.set_default_size(440, 180)
        self.folders = folders
        self.on_confirm_cb = on_confirm_cb

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(18)
        box.set_margin_end(18)

        lbl = Gtk.Label(
            label=f"Completely remove <b>{len(folders)}</b> application{'s' if len(folders) > 1 else ''}?\n\n"
                  f"<small>Apps: {GLib.markup_escape_text(', '.join(folders))}</small>\n\n"
                  "This permanently removes all binaries, data, and desktop shortcuts cleanly.",
            use_markup=True,
            wrap=True,
            xalign=0
        )
        box.append(lbl)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        btn_box.append(cancel_btn)

        del_btn = Gtk.Button(label=f"Wipe {len(folders)} App{'s' if len(folders) > 1 else ''}")
        del_btn.add_css_class("destructive-action")
        def on_confirm(_b):
            self.close()
            self.on_confirm_cb(self.folders)
        del_btn.connect("clicked", on_confirm)
        btn_box.append(del_btn)

        box.append(btn_box)
        self.set_child(box)


class SelfUninstallDialog(Gtk.Window):
    def __init__(self, parent: Gtk.Window, on_confirm_cb):
        super().__init__(title="Self-Uninstall App Encloser", transient_for=parent, modal=True)
        self.set_default_size(460, 220)
        self.on_confirm_cb = on_confirm_cb

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)

        h_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        trash_icon = Gtk.Image.new_from_icon_name("user-trash-symbolic")
        trash_icon.set_pixel_size(32)
        h_box.append(trash_icon)

        t_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        t_lbl = Gtk.Label(label="<b>Completely Uninstall App Encloser?</b>", use_markup=True, xalign=0)
        d_lbl = Gtk.Label(
            label="This will permanently delete the App Encloser binary, application shortcuts, icons, and configuration from this system.",
            wrap=True,
            xalign=0
        )
        t_box.append(t_lbl)
        t_box.append(d_lbl)
        h_box.append(t_box)
        box.append(h_box)

        self.cb_purge = Gtk.CheckButton(label="Also delete all enclosed applications and user data (~/EnclosedApps)")
        self.cb_purge.set_active(True)
        box.append(self.cb_purge)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(8)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        btn_box.append(cancel_btn)

        confirm_btn = Gtk.Button(label="Completely Uninstall")
        confirm_btn.add_css_class("destructive-action")
        def on_confirm(_b):
            purge = self.cb_purge.get_active()
            self.close()
            self.on_confirm_cb(purge)
        confirm_btn.connect("clicked", on_confirm)
        btn_box.append(confirm_btn)
        box.append(btn_box)

        self.set_child(box)


class ClearCacheOptionsDialog(Gtk.Window):
    def __init__(self, parent: Gtk.Window, folders: List[str], on_confirm_cb):
        super().__init__(title="Clear Cache & Data", transient_for=parent, modal=True)
        self.set_default_size(480, 290)
        self.folders = folders
        self.on_confirm_cb = on_confirm_cb

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)

        h_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        ic = Gtk.Image.new_from_icon_name("edit-clear-symbolic")
        ic.set_pixel_size(32)
        h_box.append(ic)

        t_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        t_lbl = Gtk.Label(
            label=f"<b>Clear Cache for {len(folders)} Application{'s' if len(folders) > 1 else ''}?</b>",
            use_markup=True,
            xalign=0
        )
        d_lbl = Gtk.Label(
            label=f"Apps: {GLib.markup_escape_text(', '.join(folders))}\nChoose which components to clean:",
            wrap=True,
            xalign=0
        )
        t_box.append(t_lbl)
        t_box.append(d_lbl)
        h_box.append(t_box)
        box.append(h_box)

        self.cb_cache = Gtk.CheckButton(label="Temporary cache and downloads (cache/, tmp/)")
        self.cb_cache.set_active(True)
        box.append(self.cb_cache)

        self.cb_logs = Gtk.CheckButton(label="Runtime logs and process state (last_run.log, state/)")
        self.cb_logs.set_active(True)
        box.append(self.cb_logs)

        self.cb_userdata = Gtk.CheckButton(label="Reset user configurations and profiles (home/, config/)")
        self.cb_userdata.set_active(False)
        box.append(self.cb_userdata)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(8)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        btn_box.append(cancel_btn)

        confirm_btn = Gtk.Button(label="Clear Selected Data")
        confirm_btn.add_css_class("suggested-action")
        def on_confirm(_b):
            c_cache = self.cb_cache.get_active()
            c_logs = self.cb_logs.get_active()
            c_user = self.cb_userdata.get_active()
            self.close()
            self.on_confirm_cb(self.folders, c_cache, c_logs, c_user)
        confirm_btn.connect("clicked", on_confirm)
        btn_box.append(confirm_btn)

        box.append(btn_box)
        self.set_child(box)
