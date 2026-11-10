import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, GLib


class UserGuideDialog(Adw.Window):
    def __init__(self, parent: Gtk.Window):
        super().__init__(title="Architecture & User Guide", transient_for=parent, modal=True)
        self.set_default_size(700, 640)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", lambda _c, val, _k, _s: (self.close(), True)[1] if val == Gdk.KEY_Escape else False)
        self.add_controller(key_ctrl)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)
        main_box.append(header)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content_box.set_margin_top(16)
        content_box.set_margin_bottom(24)
        content_box.set_margin_start(20)
        content_box.set_margin_end(20)

        intro_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        intro_icon = Gtk.Image.new_from_icon_name("help-browser-symbolic")
        intro_icon.set_pixel_size(48)
        intro_box.append(intro_icon)

        intro_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        intro_title = Gtk.Label(label="<b><big>App Encloser Core Architecture</big></b>", use_markup=True, xalign=0)
        intro_desc = Gtk.Label(
            label="App Encloser provides lightweight, native application and package isolation on Linux (Ubuntu 24.04 LTS & Debian). Below are the five foundational concepts powering your enclosed environments.",
            xalign=0,
            wrap=True
        )
        intro_text.append(intro_title)
        intro_text.append(intro_desc)
        intro_box.append(intro_text)
        content_box.append(intro_box)

        cards = [
            {
                "title": "1. Complete Encloser (Strict Sandbox)",
                "badge": "Strict Sandbox",
                "badge_css": "badge-level-strict",
                "icon": "security-high-symbolic",
                "summary": "Kernel namespace virtualization via Bubblewrap (bwrap). Masks the host home directory with tmpfs and mounts isolated /tmp.",
                "details": [
                    "• Full process and filesystem isolation guarantees zero host clutter.",
                    "• Applications cannot see or modify your real personal files or SSH/GPG keys.",
                    "• Ideal for web browsers, untrusted binaries, and proprietary software."
                ]
            },
            {
                "title": "2. Directory Encloser (Standard Isolation)",
                "badge": "Standard Isolated",
                "badge_css": "badge-level-standard",
                "icon": "folder-symbolic",
                "summary": "Dedicated self-contained container directory inside ~/EnclosedApps/<app>/ with its own userdata/ tree.",
                "details": [
                    "• Redirects HOME, XDG_CONFIG_HOME, XDG_DATA_HOME, and cache directories.",
                    "• Complete zero-residue uninstallation: removing the app folder removes 100% of data.",
                    "• Fast, lightweight startup with zero virtualization overhead."
                ]
            },
            {
                "title": "3. System Integrated Encloser",
                "badge": "System Integrated",
                "badge_css": "badge-level-integrated",
                "icon": "network-transmit-receive-symbolic",
                "summary": "Isolated container storage combined with direct host system service and device access.",
                "details": [
                    "• Binaries and packages stay enclosed inside ~/EnclosedApps.",
                    "• Permits direct network interfaces, hardware devices, and background daemons.",
                    "• Ideal for VPN clients, Ollama LLM daemons, and system network utilities."
                ]
            },
            {
                "title": "4. Separate Container Universe",
                "badge": "Container Universe",
                "badge_css": "badge-format",
                "icon": "utilities-terminal-symbolic",
                "summary": "Every container acts as an independent Linux distribution universe with built-in tools.",
                "details": [
                    "• Built-in Terminal (>_), File Manager (📁), and Package Installer (+) buttons.",
                    "• Run 'sudo apt install <pkg>' inside the container to override or swap package versions without root.",
                    "• Manage isolated runtimes: 'encloser-python <version>' and 'encloser-brew install <pkg>'."
                ]
            },
            {
                "title": "5. Laptop Terminal Interceptor & AI Agent Guard",
                "badge": "Host Guard",
                "badge_css": "badge-level-strict",
                "icon": "dialog-password-symbolic",
                "summary": "Intercepts terminal install commands to protect your Host OS from pollution by humans and AI coding agents.",
                "details": [
                    "• Traps apt, apt-get, npm -g, pip, pip3, uv, cargo, and brew commands.",
                    "• Interactive terminal prompt asks you where to enclose the package.",
                    "• AI agents (Claude Code, Cursor, Aider) are automatically guided to use safe isolated enclosers."
                ]
            }
        ]

        for card_data in cards:
            frame = Gtk.Frame()
            frame.add_css_class("card")

            card_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            card_box.set_margin_top(12)
            card_box.set_margin_bottom(12)
            card_box.set_margin_start(14)
            card_box.set_margin_end(14)

            header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            c_icon = Gtk.Image.new_from_icon_name(card_data["icon"])
            c_icon.set_pixel_size(24)
            header_row.append(c_icon)

            c_title = Gtk.Label(label=f"<b>{GLib.markup_escape_text(card_data['title'])}</b>", use_markup=True, xalign=0)
            c_title.set_hexpand(True)
            header_row.append(c_title)

            c_badge = Gtk.Label(label=card_data["badge"])
            c_badge.add_css_class("badge-format")
            if card_data.get("badge_css"):
                c_badge.add_css_class(card_data["badge_css"])
            header_row.append(c_badge)
            card_box.append(header_row)

            c_sum = Gtk.Label(label=f"<i>{GLib.markup_escape_text(card_data['summary'])}</i>", use_markup=True, xalign=0, wrap=True)
            card_box.append(c_sum)

            details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            details_box.set_margin_start(6)
            for dline in card_data["details"]:
                dlbl = Gtk.Label(label=f"<small>{GLib.markup_escape_text(dline)}</small>", use_markup=True, xalign=0, wrap=True)
                details_box.append(dlbl)
            card_box.append(details_box)

            frame.set_child(card_box)
            content_box.append(frame)

        scrolled.set_child(content_box)
        main_box.append(scrolled)

        action_bar = Gtk.ActionBar()
        close_btn = Gtk.Button(label="Close Guide")
        close_btn.add_css_class("suggested-action")
        close_btn.connect("clicked", lambda _: self.close())
        action_bar.pack_end(close_btn)
        main_box.append(action_bar)

        self.set_content(main_box)
