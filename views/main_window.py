"""Main Application Window compatibility shim for Carnicería San Diego.
Hosts navigation sidebar and switches between POSFrame, InventoryFrame, and StatsFrame.
Maintained for test suites and standalone window invocation.
"""

import os
import sys
from tkinter import messagebox
from typing import Optional
import customtkinter as ctk
from PIL import Image

from hardware.scale_service import SerialScaleDriver
from models.user import User
from utils.asset_manager import get_asset_path, set_window_icon
from utils.navbar_animator import NavbarAnimator
from utils.theme import DarkTheme
from views.about_modal import AboutModal
from views.inventory_frame import InventoryFrame
from views.pos_frame import POSFrame
from views.stats_frame import StatsFrame
from views.users_frame import UsersFrame


class MainWindow(ctk.CTk):
    """Primary application frame and navigation container (Dark Theme)."""

    def __init__(self, current_user: User, on_logout_callback):
        super().__init__()
        self.current_user = current_user
        self.on_logout_callback = on_logout_callback

        # Set Windows taskbar AppUserModelID for taskbar icon grouping
        if sys.platform.startswith("win"):
            import ctypes
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("carniceria.sandiego.pos.1.0")
            except Exception:
                pass

        # Window settings
        self.title("Sistema POS & Gestión")
        self.configure(fg_color=DarkTheme.BG_ROOT)
        self.minsize(980, 620)

        # Set official OS window icon
        set_window_icon(self)

        # Maximize or set default dimensions
        try:
            self.state("zoomed")
        except Exception:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            self.geometry(f"{screen_w-20}x{screen_h-60}+0+0")

        # Hardware drivers (non-blocking)
        self.scale_driver = SerialScaleDriver()

        # View instances cache
        self.current_view_name = "pos"
        self.views = {}
        self.nav_buttons = {}

        self._build_ui()
        self._show_view("pos")

        # Background pre-warm views after initial POS view is rendered
        self._prewarm_job = self.after(500, self._prewarm_views)

        # Protocol for clean window exit
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        # Unmapped compatibility placeholder for sidebar
        self.sidebar = ctk.CTkFrame(self, width=0, height=0)

        # Content area
        self.content_container = ctk.CTkFrame(self, fg_color=DarkTheme.BG_CONTENT, corner_radius=0)
        self.content_container.pack(fill="both", expand=True)

        # Initialize Navbar Animator for fluid transitions & micro-interactions
        self.navbar_animator = NavbarAnimator(self)

        # Top Navbar with typographic brand ('logoHorizontal.png')
        self.top_navbar = ctk.CTkFrame(
            self.content_container,
            fg_color=DarkTheme.BG_NAVBAR,
            border_width=0,
            height=NavbarAnimator.NAVBAR_HEIGHT,
            corner_radius=0
        )
        self.top_navbar.pack(side="top", fill="x")
        self.top_navbar.pack_propagate(False)

        # ── Left Side: Logo & Navigation Tabs ──────────────────────────────────
        letters_path = get_asset_path("logoHorizontal.png")
        if not os.path.exists(letters_path):
            letters_path = get_asset_path("icono San Diego")
        if os.path.exists(letters_path):
            try:
                pil_let = Image.open(letters_path).convert("RGBA")
                ctk_let = ctk.CTkImage(
                    light_image=pil_let,
                    dark_image=pil_let,
                    size=(NavbarAnimator.LOGO_WIDTH, NavbarAnimator.LOGO_HEIGHT)
                )
                lbl_let = ctk.CTkLabel(self.top_navbar, image=ctk_let, text="")
                lbl_let.pack(side="left", padx=(16, 12), pady=5)
                # Logo click interaction: opens corporate AboutModal
                self.navbar_animator.attach_logo_interaction(lbl_let, lambda: AboutModal(self))
            except Exception:
                pass

        # Thin vertical separator
        ctk.CTkFrame(
            self.top_navbar,
            fg_color=DarkTheme.BORDER_SUBTLE,
            width=1,
            height=36
        ).pack(side="left", padx=(0, 12))

        # Horizontal Navigation Tabs (Ventas, Inventario, Estadísticas, Usuarios)
        # Inactive: icon only. Active: icon + module name.
        self.nav_items_meta = {
            "pos": ("🛒", "Ventas"),
            "inventory": ("📦", "Inventario"),
            "stats": ("📊", "Estadísticas"),
            "users": ("👤", "Usuarios"),
        }

        for view_key, (icon, _name) in self.nav_items_meta.items():
            btn = ctk.CTkButton(
                self.top_navbar,
                text=icon,
                width=NavbarAnimator.BTN_COLLAPSED_WIDTH,
                height=NavbarAnimator.ITEM_HEIGHT,
                fg_color="transparent",
                hover_color=DarkTheme.BG_CARD_ELEVATED,
                text_color=DarkTheme.TEXT_SECONDARY,
                font=ctk.CTkFont(family="Segoe UI", size=17),
                corner_radius=9,
                command=lambda k=view_key: self._show_view(k)
            )
            btn.pack(side="left", padx=4, pady=13)
            self.navbar_animator.attach_button_hover(btn, view_key)
            self.nav_buttons[view_key] = btn

        self._configure_nav_tabs_for_user()

        # ── Right Side: Logout & User Badge ───────────────────────────────────
        # 1. Far Right: Logout Button in dark red container with clear exit icon
        logout_icon_path = get_asset_path("logout_icon.png")
        logout_img = None
        if os.path.exists(logout_icon_path):
            try:
                pil_logout = Image.open(logout_icon_path).convert("RGBA")
                logout_img = ctk.CTkImage(light_image=pil_logout, dark_image=pil_logout, size=(22, 22))
            except Exception:
                pass

        self.logout_btn = ctk.CTkButton(
            self.top_navbar,
            text="" if logout_img else "🚪",
            image=logout_img,
            width=NavbarAnimator.LOGOUT_WIDTH,
            height=NavbarAnimator.ITEM_HEIGHT,
            fg_color=DarkTheme.DANGER_BG,
            border_color=DarkTheme.DANGER_BORDER,
            border_width=1,
            hover_color=DarkTheme.DANGER_PRIMARY,
            text_color=DarkTheme.DANGER_TEXT,
            corner_radius=9,
            command=self._do_logout
        )
        self.logout_btn.pack(side="right", padx=(4, 16), pady=13)
        self.navbar_animator.attach_logout_hover(self.logout_btn, self._do_logout)

        # 2. Logged-in User Badge in obsidian / gold container
        self.user_badge_frame = ctk.CTkFrame(
            self.top_navbar,
            fg_color=DarkTheme.BG_CARD_ELEVATED,
            border_color=DarkTheme.BORDER_FOCUS,
            border_width=1,
            corner_radius=9,
            height=NavbarAnimator.USER_BADGE_HEIGHT
        )
        self.user_badge_frame.pack(side="right", padx=(4, 8), pady=13)

        badge_txt = (self.current_user.role if self.current_user and self.current_user.role else "Administrador").upper()
        self.user_badge_lbl = ctk.CTkLabel(
            self.user_badge_frame,
            text=f"{badge_txt}",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=DarkTheme.ACCENT_GOLD
        )
        self.user_badge_lbl.pack(padx=14, pady=7)
        self.navbar_animator.attach_badge_hover(self.user_badge_frame, self.user_badge_lbl)

        # 3. Sound Mute / Unmute Toggle Button
        from utils.sound_manager import sound_manager
        self.sound_btn = ctk.CTkButton(
            self.top_navbar,
            text="🔊" if sound_manager.enabled else "🔇",
            width=38,
            height=NavbarAnimator.ITEM_HEIGHT,
            fg_color=DarkTheme.BG_CARD_ELEVATED,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            hover_color=DarkTheme.BG_CARD_HOVER,
            text_color=DarkTheme.ACCENT_GOLD if sound_manager.enabled else DarkTheme.TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            corner_radius=9,
            command=self._toggle_sound
        )
        self.sound_btn.pack(side="right", padx=(4, 6), pady=13)

        # Scale status indicator removed from navbar per user request ("elimina ahi lo de emular la bascula")
        self.scale_box = None
        self.scale_status_lbl = None

        # Views container
        self.views_container = ctk.CTkFrame(self.content_container, fg_color=DarkTheme.BG_ROOT, corner_radius=0)
        self.views_container.pack(side="top", fill="both", expand=True)

    def _configure_nav_tabs_for_user(self) -> None:
        """Display or hide navigation tabs according to current user role."""
        is_admin = bool(self.current_user and self.current_user.is_admin)
        for btn in self.nav_buttons.values():
            btn.pack_forget()

        allowed_tabs = ["pos", "inventory"] if not is_admin else ["pos", "inventory", "stats", "users"]
        for k in allowed_tabs:
            btn = self.nav_buttons.get(k)
            if btn:
                btn.pack(side="left", padx=4, pady=13)

    def refresh_user_badge(self) -> None:
        """Refresh current user and role badge in topbar and synchronize child views."""
        if hasattr(self, "current_user") and self.current_user:
            try:
                from database.connection import get_db_connection
                from models.user import UserModel
                with get_db_connection() as conn:
                    fresh = UserModel.get_by_id(conn, self.current_user.id)
                    if fresh:
                        self.current_user = fresh
            except Exception:
                pass
        self._configure_nav_tabs_for_user()
        role_txt = (self.current_user.role if self.current_user and self.current_user.role else "Administrador").upper()
        if hasattr(self, "user_badge_lbl") and self.user_badge_lbl.winfo_exists():
            self.user_badge_lbl.configure(text=role_txt)
        if "pos" in self.views and hasattr(self.views["pos"], "current_user"):
            self.views["pos"].current_user = self.current_user
        if "inventory" in self.views and hasattr(self.views["inventory"], "set_current_user"):
            self.views["inventory"].set_current_user(self.current_user)

    def _toggle_sound(self) -> None:
        """Toggle acoustic feedback on/off."""
        from utils.sound_manager import sound_manager
        is_on = sound_manager.toggle_sound()
        self.sound_btn.configure(
            text="🔊" if is_on else "🔇",
            text_color=DarkTheme.ACCENT_GOLD if is_on else DarkTheme.TEXT_MUTED
        )

    def _show_view(self, view_name: str) -> None:
        is_admin = bool(self.current_user and self.current_user.is_admin)
        if view_name in ("stats", "users") and not is_admin:
            view_name = "pos"

        self.current_view_name = view_name
        self.refresh_user_badge()

        if hasattr(self, "navbar_animator"):
            self.navbar_animator.animate_tab_switch(self.nav_buttons, self.nav_items_meta, view_name)

        for v in self.views.values():
            v.pack_forget()

        is_first_load = (view_name not in self.views)
        if is_first_load:
            if view_name == "pos":
                self.views["pos"] = POSFrame(
                    parent=self.views_container,
                    current_user=self.current_user,
                    scale_driver=self.scale_driver
                )
            elif view_name == "inventory":
                self.views["inventory"] = InventoryFrame(
                    parent=self.views_container,
                    current_user=self.current_user
                )
            elif view_name == "stats":
                self.views["stats"] = StatsFrame(parent=self.views_container)
            elif view_name == "users":
                self.views["users"] = UsersFrame(parent=self.views_container)

        active_frame = self.views[view_name]
        active_frame.pack(fill="both", expand=True)

        if is_first_load:
            if view_name == "pos":
                active_frame.barcode_entry.focus_set()
            elif view_name == "inventory" and hasattr(active_frame, "set_current_user"):
                active_frame.set_current_user(self.current_user)
        else:
            if view_name == "pos" and hasattr(active_frame, "refresh_catalog"):
                active_frame.refresh_catalog()
                active_frame.barcode_entry.focus_set()
            elif view_name == "inventory":
                if hasattr(active_frame, "set_current_user"):
                    active_frame.set_current_user(self.current_user)
                if hasattr(active_frame, "load_data"):
                    active_frame.load_data()
            elif view_name == "stats" and hasattr(active_frame, "refresh_stats"):
                active_frame.refresh_stats()
            elif view_name == "users" and hasattr(active_frame, "load_data"):
                active_frame.load_data()

    def _prewarm_views(self) -> None:
        """Pre-instantiate other modules in the background so opening them is instantaneous."""
        try:
            if not self.winfo_exists():
                return
            is_admin = bool(self.current_user and self.current_user.is_admin)
            if "inventory" not in self.views:
                self.views["inventory"] = InventoryFrame(
                    parent=self.views_container,
                    current_user=self.current_user
                )
            if is_admin:
                if "stats" not in self.views:
                    self.views["stats"] = StatsFrame(parent=self.views_container)
                if "users" not in self.views:
                    self.views["users"] = UsersFrame(parent=self.views_container)
        except Exception:
            pass

    def _do_logout(self) -> None:
        if messagebox.askyesno(
            "Cerrar Sesión",
            "¿Está seguro de que desea salir al inicio de sesión?",
            parent=self
        ):
            self.destroy()
            if callable(self.on_logout_callback):
                self.on_logout_callback()

    def destroy(self) -> None:
        if getattr(self, "_prewarm_job", None):
            try:
                self.after_cancel(self._prewarm_job)
            except Exception:
                pass
            self._prewarm_job = None
        if hasattr(self, "navbar_animator"):
            try:
                self.navbar_animator.cleanup()
            except Exception:
                pass
        if hasattr(self, "scale_driver"):
            try:
                self.scale_driver.close()
            except Exception:
                pass
        super().destroy()

    def _on_close(self) -> None:
        self.destroy()

