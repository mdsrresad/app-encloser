import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk

from app_encloser.core.container import create_empty_container


class CreateContainerDialog(Gtk.Window):
    def __init__(self, parent: Gtk.Window, on_created_cb=None):
        super().__init__(title="Create Enclosed Container", transient_for=parent, modal=True)
        self.set_default_size(440, 240)
        self.set_resizable(False)
        self.on_created_cb = on_created_cb

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", lambda _c, val, _k, _s: (self.close(), True)[1] if val == Gdk.KEY_Escape else False)
        self.add_controller(key_ctrl)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)

        head_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        icon = Gtk.Image.new_from_icon_name("folder-new-symbolic")
        icon.set_pixel_size(28)
        head_box.append(icon)

        title_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lbl_t = Gtk.Label(label="<b>Create Isolated Container</b>", use_markup=True, xalign=0)
        lbl_s = Gtk.Label(label="Set up a portable isolated container for custom apps, tools or environments", xalign=0)
        lbl_s.add_css_class("dim-label")
        title_col.append(lbl_t)
        title_col.append(lbl_s)
        head_box.append(title_col)
        box.append(head_box)

        self.name_entry = Gtk.Entry()
        self.name_entry.set_placeholder_text("Enter container name...")
        self.name_entry.connect("activate", lambda _: self.do_create())
        box.append(self.name_entry)

        self.chk_strict = Gtk.CheckButton(label="Strict Bubblewrap Sandbox Isolation")
        self.chk_strict.set_active(True)
        box.append(self.chk_strict)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(6)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        btn_box.append(cancel_btn)

        create_btn = Gtk.Button(label="Create Container")
        create_btn.add_css_class("suggested-action")
        create_btn.connect("clicked", lambda _: self.do_create())
        btn_box.append(create_btn)

        box.append(btn_box)
        self.set_child(box)

    def do_create(self):
        name = self.name_entry.get_text().strip()
        if not name:
            return
        strict = self.chk_strict.get_active()
        ok, msg = create_empty_container(name, strict=strict)
        self.close()
        if self.on_created_cb:
            self.on_created_cb(ok, msg, name)
