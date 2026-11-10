import os
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


class TerminalCommandInstallDialog(Gtk.Window):
    def __init__(self, parent: Gtk.Window, on_install_cmd_cb):
        super().__init__(title="Install via Command", transient_for=parent, modal=True)
        self.set_default_size(560, 400)
        self.on_install_cmd_cb = on_install_cmd_cb

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(20)
        box.set_margin_end(20)

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        term_icon = Gtk.Image.new_from_icon_name("utilities-terminal-symbolic")
        term_icon.set_pixel_size(32)
        header_box.append(term_icon)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_lbl = Gtk.Label(label="<b>Install via Command or Package Name</b>", use_markup=True, xalign=0)
        sub_lbl = Gtk.Label(
            label="<small>Paste an APT package, shell commands, or multi-line install script.</small>",
            use_markup=True,
            xalign=0
        )
        title_box.append(title_lbl)
        title_box.append(sub_lbl)
        header_box.append(title_box)
        box.append(header_box)

        entry_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        entry_lbl = Gtk.Label(label="<b>Command, Script, or Package Name:</b>", use_markup=True, xalign=0)
        entry_box.append(entry_lbl)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(140)
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)

        self.text_view = Gtk.TextView()
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.set_monospace(True)
        self.text_view.set_top_margin(8)
        self.text_view.set_bottom_margin(8)
        self.text_view.set_left_margin(8)
        self.text_view.set_right_margin(8)
        scroll.set_child(self.text_view)
        entry_box.append(scroll)
        box.append(entry_box)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(12)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        btn_box.append(cancel_btn)

        run_btn = Gtk.Button(label="Install")
        run_btn.add_css_class("suggested-action")
        def on_run(_b):
            buf = self.text_view.get_buffer()
            val = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True).strip()
            if val:
                self.close()
                self.on_install_cmd_cb(val)
        run_btn.connect("clicked", on_run)
        btn_box.append(run_btn)

        box.append(btn_box)
        self.set_child(box)


class InstallIntoContainerDialog(Gtk.Window):
    def __init__(self, parent: Gtk.Window, container_name: str, on_install_cb):
        super().__init__(title=f"Install into {container_name}", transient_for=parent, modal=True)
        self.set_default_size(580, 420)
        self.container_name = container_name
        self.on_install_cb = on_install_cb

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(20)
        box.set_margin_end(20)

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box_icon = Gtk.Image.new_from_icon_name("package-x-generic-symbolic")
        box_icon.set_pixel_size(32)
        header_box.append(box_icon)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_lbl = Gtk.Label(
            label=f"<b>Install into Container: {container_name}</b>",
            use_markup=True,
            xalign=0
        )
        sub_lbl = Gtk.Label(
            label="<small>Install a .deb, package, URL, or paste commands/scripts to run inside container.</small>",
            use_markup=True,
            xalign=0
        )
        title_box.append(title_lbl)
        title_box.append(sub_lbl)
        header_box.append(title_box)
        box.append(header_box)

        entry_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        entry_lbl = Gtk.Label(label="<b>Package Name, URL, Script, or Local File:</b>", use_markup=True, xalign=0)
        entry_box.append(entry_lbl)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(130)
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)

        self.text_view = Gtk.TextView()
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.set_monospace(True)
        self.text_view.set_top_margin(8)
        self.text_view.set_bottom_margin(8)
        self.text_view.set_left_margin(8)
        self.text_view.set_right_margin(8)
        scroll.set_child(self.text_view)
        entry_box.append(scroll)

        browse_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        browse_box.set_halign(Gtk.Align.END)
        browse_btn = Gtk.Button(label="Browse Local File...")
        browse_btn.set_tooltip_text("Select local .deb, .AppImage, or archive")
        browse_btn.connect("clicked", self.on_browse_file)
        browse_box.append(browse_btn)
        entry_box.append(browse_box)

        box.append(entry_box)

        info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        info_icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic")
        info_box.append(info_icon)
        info_lbl = Gtk.Label(
            label=f"<small>Target: <b>~/EnclosedApps/{container_name}/app_files</b> (completely isolated, rootless)</small>",
            use_markup=True,
            xalign=0
        )
        info_box.append(info_lbl)
        box.append(info_box)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(12)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        btn_box.append(cancel_btn)

        run_btn = Gtk.Button(label="Install into Container")
        run_btn.add_css_class("suggested-action")
        def on_run(_b):
            buf = self.text_view.get_buffer()
            val = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True).strip()
            if val:
                self.close()
                self.on_install_cb(val)
        run_btn.connect("clicked", on_run)
        btn_box.append(run_btn)

        box.append(btn_box)
        self.set_child(box)

    def on_browse_file(self, _btn):
        dialog = Gtk.FileDialog()
        dialog.set_title(f"Select Package to Install into {self.container_name}")
        filter_all = Gtk.FileFilter()
        filter_all.set_name("Supported Packages (*.deb, *.AppImage, *.tar.*, *.zip)")
        filter_all.add_pattern("*.deb")
        filter_all.add_pattern("*.AppImage")
        filter_all.add_pattern("*.tar.*")
        filter_all.add_pattern("*.tar")
        filter_all.add_pattern("*.zip")
        filter_all.add_pattern("*.rpm")
        dialog.set_default_filter(filter_all)

        def on_open_finish(source, result):
            try:
                gfile = source.open_finish(result)
                if gfile:
                    buf = self.text_view.get_buffer()
                    buf.set_text(gfile.get_path())
            except Exception:
                pass
        dialog.open(self, None, on_open_finish)

