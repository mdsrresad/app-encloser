import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from app_encloser.core.config import get_setting


class BatchActionBar(Gtk.Box):
    def __init__(self, on_toggle_all, on_launch, on_clear_cache, on_export, on_uninstall, on_done):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.add_css_class("toolbar")
        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_bottom(12)
        self.set_margin_top(4)

        self.on_toggle_all = on_toggle_all
        self.on_launch = on_launch
        self.on_clear_cache = on_clear_cache
        self.on_export = on_export
        self.on_uninstall = on_uninstall
        self.on_done = on_done

        left_batch = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.batch_lbl = Gtk.Label(label="", xalign=0)
        left_batch.append(self.batch_lbl)

        self.toggle_all_btn = Gtk.Button(label="Select All")
        self.toggle_all_btn.connect("clicked", lambda _: self.on_toggle_all())
        left_batch.append(self.toggle_all_btn)
        self.append(left_batch)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        self.append(spacer)

        self.right_batch = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(self.right_batch)

        self.rebuild_buttons()
        self.set_visible(False)

    def rebuild_buttons(self):
        while True:
            child = self.right_batch.get_first_child()
            if not child:
                break
            self.right_batch.remove(child)

        show_text = (get_setting("button_style", "icons_only") != "icons_only")

        def make_btn(icon_name, tooltip, text, on_click, destructive=False, suggested=False):
            btn = Gtk.Button()
            btn.set_tooltip_text(tooltip)
            if destructive:
                btn.add_css_class("destructive-action")
            elif suggested:
                btn.add_css_class("suggested-action")

            if show_text:
                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                box.append(Gtk.Image.new_from_icon_name(icon_name))
                box.append(Gtk.Label(label=text))
                btn.set_child(box)
            else:
                btn.set_icon_name(icon_name)

            btn.connect("clicked", lambda _: on_click())
            return btn

        self.right_batch.append(make_btn("media-playback-start-symbolic", "Launch Selected Applications", "Launch", self.on_launch))
        self.right_batch.append(make_btn("edit-clear-symbolic", "Clear Cache for Selected", "Clear Cache", self.on_clear_cache))
        self.right_batch.append(make_btn("document-save-symbolic", "Export Selected Applications", "Export", self.on_export))
        self.right_batch.append(make_btn("user-trash-symbolic", "Uninstall Selected Applications", "Uninstall", self.on_uninstall, destructive=True))
        self.right_batch.append(make_btn("emblem-ok-symbolic", "Done Selection", "Done", self.on_done, suggested=True))

    def update_state(self, sel_count: int, total_count: int, edit_mode: bool):
        if sel_count > 0 or edit_mode:
            self.set_visible(True)
            self.batch_lbl.set_text(f"{sel_count} of {total_count} selected")
            self.toggle_all_btn.set_label("Deselect All" if sel_count == total_count and total_count > 0 else "Select All")
        else:
            self.set_visible(False)
