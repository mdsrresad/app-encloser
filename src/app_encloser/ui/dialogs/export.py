import os
from typing import List, Dict

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

from app_encloser.core.config import REAL_HOME


class ExportSelectiveDialog(Gtk.Window):
    def __init__(self, parent: Gtk.Window, app_folders: List[str], on_export_cb, is_all: bool = False):
        title = "Export All Applications" if is_all else ("Export Application" if len(app_folders) == 1 else "Export Applications")
        super().__init__(title=title, transient_for=parent, modal=True)
        self.set_default_size(520, 320)
        self.on_export_cb = on_export_cb
        self.app_folders = app_folders
        self.is_all = is_all
        self._fc = None

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(20)
        box.set_margin_end(20)

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        exp_icon = Gtk.Image.new_from_icon_name("document-save-symbolic")
        exp_icon.set_pixel_size(32)
        header_box.append(exp_icon)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        count = len(app_folders)
        if is_all:
            t_lbl = Gtk.Label(label=f"<b>Full System Export ({count} Applications)</b>", use_markup=True, xalign=0)
            sub_lbl = Gtk.Label(label="<small>Create a complete relocatable backup of all isolated containers.</small>", use_markup=True, xalign=0)
        elif count == 1:
            t_lbl = Gtk.Label(label=f"<b>Export {GLib.markup_escape_text(app_folders[0])}</b>", use_markup=True, xalign=0)
            sub_lbl = Gtk.Label(label="<small>Create an archive for this application container.</small>", use_markup=True, xalign=0)
        else:
            t_lbl = Gtk.Label(label=f"<b>Export {count} Selected Applications</b>", use_markup=True, xalign=0)
            apps_str = ", ".join(app_folders[:4]) + ("..." if len(app_folders) > 4 else "")
            sub_lbl = Gtk.Label(label=f"<small>Export archive for: <b>{GLib.markup_escape_text(apps_str)}</b></small>", use_markup=True, xalign=0)

        title_box.append(t_lbl)
        title_box.append(sub_lbl)
        header_box.append(title_box)
        box.append(header_box)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("card")
        c_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        c_box.set_margin_top(12)
        c_box.set_margin_bottom(12)
        c_box.set_margin_start(14)
        c_box.set_margin_end(14)

        self.cb_bin = Gtk.CheckButton(label="Application Binaries & System Files (app_files)")
        self.cb_bin.set_active(True)
        c_box.append(self.cb_bin)

        self.cb_usr = Gtk.CheckButton(label="User Data, Configurations & Cache (userdata)")
        self.cb_usr.set_active(True)
        c_box.append(self.cb_usr)

        card.append(c_box)
        box.append(card)

        dest_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        dest_lbl = Gtk.Label(label="Save to:")
        dest_box.append(dest_lbl)

        if is_all:
            default_fn = "all-enclosed-apps-backup.tar.gz"
        elif count == 1:
            default_fn = f"{app_folders[0]}-backup.tar.gz"
        else:
            default_fn = "enclosed-apps-backup.tar.gz"

        default_path = os.path.join(REAL_HOME, default_fn)
        self.dest_entry = Gtk.Entry()
        self.dest_entry.set_text(default_path)
        self.dest_entry.set_hexpand(True)
        dest_box.append(self.dest_entry)

        browse_btn = Gtk.Button(label="Browse...")
        def on_browse_file(_b):
            self._fc = Gtk.FileChooserNative(
                title="Select Export Archive Destination",
                transient_for=self,
                action=Gtk.FileChooserAction.SAVE,
                accept_label="_Save",
                cancel_label="_Cancel"
            )
            self._fc.set_current_name(os.path.basename(self.dest_entry.get_text()))
            def on_resp(dialog, resp):
                try:
                    if resp == Gtk.ResponseType.ACCEPT:
                        gf = dialog.get_file()
                        if gf and gf.get_path():
                            self.dest_entry.set_text(gf.get_path())
                finally:
                    self._fc = None
            self._fc.connect("response", on_resp)
            self._fc.show()
        browse_btn.connect("clicked", on_browse_file)
        dest_box.append(browse_btn)
        box.append(dest_box)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(10)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        btn_box.append(cancel_btn)

        export_btn = Gtk.Button(label="Export Archive")
        export_btn.add_css_class("suggested-action")
        def on_confirm_export(_b):
            out_p = self.dest_entry.get_text().strip()
            if not out_p:
                return
            b_active = self.cb_bin.get_active()
            u_active = self.cb_usr.get_active()
            if not b_active and not u_active:
                return
            selections = {f: {"app_files": b_active, "userdata": u_active} for f in self.app_folders}
            self.close()
            self.on_export_cb(selections, out_p)
        export_btn.connect("clicked", on_confirm_export)
        btn_box.append(export_btn)

        box.append(btn_box)
        self.set_child(box)
