import os
import shutil
import subprocess
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, GLib

from app_encloser.core.config import LOCAL_BIN
from app_encloser.core.diagnostic import analyze_container_incompatibility
from app_encloser.core.security import scan_app_security


class DiagnosticReportDialog(Adw.Window):
    def __init__(self, parent: Gtk.Window, app: dict, on_terminal_cb=None, on_open_dir_cb=None):
        title = f"{app['name']} — Diagnostic Report"
        super().__init__(title=title, transient_for=parent, modal=True)
        self.set_default_size(620, 560)
        self.app = app
        self.on_terminal_cb = on_terminal_cb
        self.on_open_dir_cb = on_open_dir_cb

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", lambda _c, val, _k, _s: (self.close(), True)[1] if val == Gdk.KEY_Escape else False)
        self.add_controller(key_ctrl)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)
        main_box.append(header)

        diag = analyze_container_incompatibility(app["folder"])
        sec = scan_app_security(app["folder"])

        page = Adw.PreferencesPage()

        grp_summary = Adw.PreferencesGroup()
        grp_summary.set_title("Runtime & Compatibility Analysis")

        st_row = Adw.ActionRow(
            title="Runtime Status",
            subtitle=f"{diag['status']} • Exit Code: {diag['exit_code'] if diag['exit_code'] is not None else 'None'}"
        )
        st_icon = "dialog-error-symbolic" if diag["has_error"] else "emblem-ok-symbolic"
        st_row.set_icon_name(st_icon)
        grp_summary.add(st_row)

        arch_row = Adw.ActionRow(
            title="Binary Architecture",
            subtitle=f"Target: {diag['binary_arch']} • Host: {diag['host_arch']}"
        )
        arch_row.set_icon_name("application-x-executable-symbolic")
        grp_summary.add(arch_row)

        if diag.get("missing_libraries"):
            libs_row = Adw.ActionRow(
                title="Missing Shared Libraries",
                subtitle=", ".join(diag["missing_libraries"])
            )
            libs_row.set_icon_name("system-software-install-symbolic")
            grp_summary.add(libs_row)

        if diag.get("recommendation"):
            rec_row = Adw.ActionRow(
                title="Recommendation",
                subtitle=diag["recommendation"]
            )
            rec_row.set_icon_name("dialog-information-symbolic")
            grp_summary.add(rec_row)

        page.add(grp_summary)

        grp_sec = Adw.PreferencesGroup()
        grp_sec.set_title("Security & Telemetry Audit")

        sec_sub = f"Grade {sec['grade']} ({sec['score']}/100) • {sec['status']}"
        sec_row = Adw.ActionRow(title="Security Assessment", subtitle=sec_sub)
        sec_row.set_icon_name("security-high-symbolic")
        grp_sec.add(sec_row)

        trk_desc = f"{len(sec['trackers'])} tracker domain(s) detected" if sec["trackers"] else "Zero trackers detected"
        trk_row = Adw.ActionRow(title="Telemetry & Analytics", subtitle=trk_desc)
        trk_row.set_icon_name("network-wired-symbolic")
        grp_sec.add(trk_row)
        page.add(grp_sec)

        grp_log = Adw.PreferencesGroup()
        grp_log.set_title("Recent Runtime Log (last_run.log)")

        log_content = diag.get("log_excerpt") or diag.get("full_log") or "No output written yet."
        txt_view = Gtk.TextView()
        txt_view.set_editable(False)
        txt_view.set_cursor_visible(False)
        txt_view.set_monospace(True)
        txt_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        txt_view.get_buffer().set_text(log_content)
        txt_view.set_margin_top(8)
        txt_view.set_margin_bottom(8)
        txt_view.set_margin_start(10)
        txt_view.set_margin_end(10)

        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(140)
        scroll.set_max_content_height(200)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(txt_view)
        grp_log.add(scroll)
        page.add(grp_log)

        main_box.append(page)

        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom_bar.set_margin_top(10)
        bottom_bar.set_margin_bottom(12)
        bottom_bar.set_margin_start(16)
        bottom_bar.set_margin_end(16)

        btn_term = Gtk.Button(label="Open Terminal Shell")
        btn_term.set_icon_name("utilities-terminal-symbolic")
        def on_term(_b):
            if self.on_terminal_cb:
                self.on_terminal_cb(self.app)
            else:
                exe = shutil.which("app-encloser") or os.path.join(LOCAL_BIN, "app-encloser")
                for term in ("gnome-terminal", "kgx", "x-terminal-emulator", "xterm"):
                    if shutil.which(term):
                        flag = "--" if term == "gnome-terminal" else "-e"
                        subprocess.Popen([term, flag, exe, "shell", self.app["folder"]])
                        break
        btn_term.connect("clicked", on_term)
        bottom_bar.append(btn_term)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        bottom_bar.append(spacer)

        btn_copy = Gtk.Button(label="Copy Report")
        btn_copy.set_icon_name("edit-copy-symbolic")
        def on_copy(_b):
            from app_encloser.core.diagnostic import generate_diagnostic_report
            text = generate_diagnostic_report(self.app["folder"])
            disp = Gdk.Display.get_default()
            if disp:
                disp.get_clipboard().set(text)
            btn_copy.set_label("Copied!")
        btn_copy.connect("clicked", on_copy)
        bottom_bar.append(btn_copy)

        btn_close = Gtk.Button(label="Close")
        btn_close.add_css_class("suggested-action")
        btn_close.connect("clicked", lambda _: self.close())
        bottom_bar.append(btn_close)

        main_box.append(bottom_bar)
        self.set_content(main_box)
