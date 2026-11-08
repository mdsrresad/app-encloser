import os
from typing import Dict, Any, List, Optional
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, GLib


class DependencyResolutionConfirmationDialog(Adw.Window):
    def __init__(self, parent: Gtk.Window, app: dict, diagnosis: dict, on_confirm_cb):
        title = f"Resolve Dependencies — {app['name']}"
        super().__init__(title=title, transient_for=parent, modal=True)
        self.set_default_size(560, 480)
        self.app = app
        self.diagnosis = diagnosis
        self.on_confirm_cb = on_confirm_cb

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", lambda _c, val, _k, _s: (self.close(), True)[1] if val == Gdk.KEY_Escape else False)
        self.add_controller(key_ctrl)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)
        main_box.append(header)

        page = Adw.PreferencesPage()

        grp_head = Adw.PreferencesGroup()
        h_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        h_box.set_margin_top(8)
        h_box.set_margin_bottom(8)
        h_box.set_margin_start(12)
        h_box.set_margin_end(12)

        icon = Gtk.Image.new_from_icon_name("system-software-update-symbolic")
        icon.set_pixel_size(48)
        h_box.append(icon)

        t_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        t_col.set_hexpand(True)

        st_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        st_lbl = Gtk.Label(label=f"<b><big>{GLib.markup_escape_text(app['name'])}</big></b>", use_markup=True, xalign=0)
        st_row.append(st_lbl)

        badge = Gtk.Label(label="Resolution Plan")
        badge.add_css_class("badge-format")
        badge.add_css_class("accent")
        st_row.append(badge)
        t_col.append(st_row)

        desc_lbl = Gtk.Label(
            label="<small>Review the automated resolution plan below. No changes will be applied without your confirmation.</small>",
            use_markup=True,
            xalign=0,
            wrap=True
        )
        t_col.append(desc_lbl)
        h_box.append(t_col)
        grp_head.add(h_box)
        page.add(grp_head)

        missing_libs = diagnosis.get("missing_libraries", [])
        if missing_libs:
            grp_issues = Adw.PreferencesGroup()
            grp_issues.set_title(f"Detected Missing Shared Dependencies ({len(missing_libs)})")
            for lib in missing_libs[:15]:
                row = Adw.ActionRow(
                    title=lib,
                    subtitle="Will be scanned in container subdirectories or imported into container"
                )
                row.set_icon_name("software-properties-symbolic")
                grp_issues.add(row)
            if len(missing_libs) > 15:
                row_more = Adw.ActionRow(title=f"... and {len(missing_libs) - 15} more libraries")
                grp_issues.add(row_more)
            page.add(grp_issues)

        grp_actions = Adw.PreferencesGroup()
        grp_actions.set_title("Automated Resolution Actions")

        act1 = Adw.ActionRow(
            title="Discover & Link Internal Libraries",
            subtitle="Scans all container subdirectories (app_files/...) and updates library search paths"
        )
        act1.set_icon_name("folder-saved-search-symbolic")
        grp_actions.add(act1)

        act2 = Adw.ActionRow(
            title="Import or Download Missing Dependencies",
            subtitle="Imports required .so binaries from host or downloads packages into container"
        )
        act2.set_icon_name("system-software-install-symbolic")
        grp_actions.add(act2)

        act3 = Adw.ActionRow(
            title="Audit Symlinks & Rebuild Launch Script",
            subtitle="Repairs Debian UsrMerge symlinks, installs shims, and re-generates launch.sh"
        )
        act3.set_icon_name("utilities-terminal-symbolic")
        grp_actions.add(act3)

        page.add(grp_actions)

        grp_scope = Adw.PreferencesGroup()
        scope_row = Adw.ActionRow(
            title="Isolation Guarantee",
            subtitle=f"All repairs are strictly confined to ~/EnclosedApps/{app['folder']}/ with zero host modifications."
        )
        scope_row.set_icon_name("security-high-symbolic")
        grp_scope.add(scope_row)
        page.add(grp_scope)

        main_box.append(page)

        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom_bar.set_margin_top(10)
        bottom_bar.set_margin_bottom(12)
        bottom_bar.set_margin_start(16)
        bottom_bar.set_margin_end(16)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        bottom_bar.append(spacer)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        bottom_bar.append(cancel_btn)

        confirm_btn = Gtk.Button(label="Confirm & Resolve Dependencies")
        confirm_btn.add_css_class("suggested-action")
        confirm_btn.add_css_class("pill")

        def on_click(_b):
            self.close()
            self.on_confirm_cb(self.app)

        confirm_btn.connect("clicked", on_click)
        bottom_bar.append(confirm_btn)

        main_box.append(bottom_bar)
        self.set_content(main_box)
