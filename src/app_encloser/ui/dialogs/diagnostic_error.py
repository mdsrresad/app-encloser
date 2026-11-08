import os
import shutil
import subprocess
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, GLib

from app_encloser.core.config import LOCAL_BIN


class ErrorIncompatibilityDialog(Adw.Window):
    def __init__(self, parent: Gtk.Window, app: dict, diagnosis: dict, on_terminal_cb=None, on_resolve_cb=None, on_retry_cb=None, on_level_cb=None):
        title = f"{app['name']} — Error / Incompatibility"
        super().__init__(title=title, transient_for=parent, modal=True)
        self.set_default_size(600, 520)
        self.app = app
        self.diagnosis = diagnosis
        self.on_terminal_cb = on_terminal_cb
        self.on_resolve_cb = on_resolve_cb
        self.on_retry_cb = on_retry_cb
        self.on_level_cb = on_level_cb

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", lambda _c, val, _k, _s: (self.close(), True)[1] if val == Gdk.KEY_Escape else False)
        self.add_controller(key_ctrl)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)
        main_box.append(header)

        page = Adw.PreferencesPage()

        grp_header = Adw.PreferencesGroup()
        h_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        h_box.set_margin_top(10)
        h_box.set_margin_bottom(10)
        h_box.set_margin_start(14)
        h_box.set_margin_end(14)

        ic_name = "dialog-error-symbolic" if diagnosis.get("category") in ("crash_segfault", "architecture_mismatch", "missing_library") else "dialog-warning-symbolic"
        err_icon = Gtk.Image.new_from_icon_name(ic_name)
        err_icon.set_pixel_size(48)
        h_box.append(err_icon)

        t_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        t_col.set_hexpand(True)

        st_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        st_lbl = Gtk.Label(label=f"<b><big>{GLib.markup_escape_text(app['name'])}</big></b>", use_markup=True, xalign=0)
        st_row.append(st_lbl)

        status_text = diagnosis.get("status", "Error")
        badge = Gtk.Label(label=status_text)
        badge.add_css_class("badge-format")
        badge.add_css_class("destructive-action")
        st_row.append(badge)
        t_col.append(st_row)

        summary_text = diagnosis.get("summary", "An unexpected runtime failure occurred.")
        sum_lbl = Gtk.Label(label=f"<small>{GLib.markup_escape_text(summary_text)}</small>", use_markup=True, xalign=0, wrap=True)
        t_col.append(sum_lbl)
        h_box.append(t_col)
        grp_header.add(h_box)
        page.add(grp_header)

        if diagnosis.get("missing_libraries"):
            grp_libs = Adw.PreferencesGroup()
            grp_libs.set_title("Missing Shared Dependencies (.so)")
            for lib in diagnosis["missing_libraries"]:
                row = Adw.ActionRow(title=lib, subtitle="Shared library required by application binary but not found.")
                row.set_icon_name("system-software-install-symbolic")
                grp_libs.add(row)
            page.add(grp_libs)

        if diagnosis.get("suggested_level"):
            s_lvl = diagnosis["suggested_level"]
            s_title = diagnosis.get("suggested_level_title") or s_lvl.capitalize()
            cur_lvl = diagnosis.get("current_level", "unknown")
            grp_level = Adw.PreferencesGroup()
            grp_level.set_title("Suggested Isolation Adjustment")
            level_row = Adw.ActionRow(
                title=f"Lower Isolation to {s_title}",
                subtitle=f"Currently running at '{cur_lvl}' level. Lowering isolation to '{s_lvl}' grants required system and network capabilities and may resolve this failure."
            )
            level_row.set_icon_name("security-low-symbolic")

            btn_switch_retry = Gtk.Button(label=f"Switch to {s_title} & Retry")
            btn_switch_retry.add_css_class("suggested-action")
            btn_switch_retry.set_valign(Gtk.Align.CENTER)
            def on_switch_and_retry(_b):
                from app_encloser.core.container import set_enclosing_level
                set_enclosing_level(self.app["folder"], s_lvl)
                self.close()
                if self.on_retry_cb:
                    self.on_retry_cb(self.app)
            btn_switch_retry.connect("clicked", on_switch_and_retry)
            level_row.add_suffix(btn_switch_retry)
            grp_level.add(level_row)
            page.add(grp_level)

        if diagnosis.get("recommendation"):
            grp_rec = Adw.PreferencesGroup()
            grp_rec.set_title("Recommended Action")
            rec_row = Adw.ActionRow(
                title="Troubleshooting Recommendation",
                subtitle=diagnosis["recommendation"]
            )
            rec_row.set_icon_name("dialog-information-symbolic")
            grp_rec.add(rec_row)
            page.add(grp_rec)

        grp_log = Adw.PreferencesGroup()
        grp_log.set_title("Execution Log / Terminal Output")

        log_content = diagnosis.get("log_excerpt") or diagnosis.get("full_log") or "No output was written to last_run.log."
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
        scroll.set_min_content_height(160)
        scroll.set_max_content_height(240)
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

        btn_copy = Gtk.Button(label="Copy Error Details")
        btn_copy.set_icon_name("edit-copy-symbolic")
        def on_copy(_b):
            text = (
                f"Application: {self.app['name']}\n"
                f"Status: {diagnosis.get('status')}\n"
                f"Exit Code: {diagnosis.get('exit_code')}\n"
                f"Summary: {diagnosis.get('summary')}\n"
                f"Recommendation: {diagnosis.get('recommendation')}\n"
                f"Missing Libraries: {', '.join(diagnosis.get('missing_libraries', []))}\n\n"
                f"Log Excerpt:\n{diagnosis.get('log_excerpt')}\n"
            )
            disp = Gdk.Display.get_default()
            if disp:
                disp.get_clipboard().set(text)
            btn_copy.set_label("Copied!")
        btn_copy.connect("clicked", on_copy)
        bottom_bar.append(btn_copy)

        if self.on_level_cb:
            btn_level = Gtk.Button(label="Isolation Level...")
            btn_level.set_icon_name("security-high-symbolic")
            def on_open_level(_b):
                self.close()
                self.on_level_cb(self.app)
            btn_level.connect("clicked", on_open_level)
            bottom_bar.append(btn_level)

        btn_close = Gtk.Button(label="Close")
        btn_close.connect("clicked", lambda _: self.close())
        bottom_bar.append(btn_close)

        if self.on_resolve_cb:
            btn_resolve = Gtk.Button(label="Resolve Dependencies...")
            btn_resolve.set_icon_name("system-software-update-symbolic")
            btn_resolve.add_css_class("suggested-action")
            def on_resolve(_b):
                from app_encloser.ui.dialogs.dependency_dialog import DependencyResolutionConfirmationDialog
                def do_confirmed(target_app):
                    self.close()
                    self.on_resolve_cb(target_app)
                DependencyResolutionConfirmationDialog(self, self.app, self.diagnosis, on_confirm_cb=do_confirmed).present()
            btn_resolve.connect("clicked", on_resolve)
            bottom_bar.append(btn_resolve)

        main_box.append(bottom_bar)
        self.set_content(main_box)
