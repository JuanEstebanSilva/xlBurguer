"""Main Entry Point for XL Burguer POS System.
Implements the Single-Window Frame Switcher architecture with CustomTkinter,
robust file logging to app_debug.log, and global exception trapping.
"""

import faulthandler
import logging
import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox
import traceback
from typing import Optional
import customtkinter as ctk
from PIL import Image

# Ensure root directory is in sys.path
_PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Set Windows taskbar AppUserModelID early before any UI window is created
if sys.platform.startswith("win"):
    import ctypes
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("xlburguer.pos.1.0")
    except Exception:
        pass

from database.connection import get_resource_path, get_writable_path, initialize_database
from models.user import User
from utils.asset_manager import ensure_assets, get_asset_path, get_ctk_icon, set_window_icon
from utils.navbar_animator import NavbarAnimator
from utils.theme import DarkTheme
from views.about_modal import AboutModal
from views.inventory_frame import InventoryFrame
from views.login_frame import LoginFrame
from views.pos_frame import POSFrame
from views.stats_frame import StatsFrame
from views.users_frame import UsersFrame

# Configure persistent file logging for production diagnostics
_LOG_FILE = get_writable_path("app_debug.log")
logging.basicConfig(
    filename=_LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

# In windowed mode (GUI without console), ensure stdout and stderr do not raise errors on print
class _SafeStreamWriter:
    def __init__(self, level):
        self.level = level
        self.encoding = "utf-8"
        self.errors = "replace"

    def write(self, message):
        msg = str(message).strip()
        if msg:
            logging.log(self.level, msg)

    def flush(self):
        pass

    def isatty(self):
        return False

if sys.stdout is None:
    sys.stdout = _SafeStreamWriter(logging.INFO)
if sys.stderr is None:
    sys.stderr = _SafeStreamWriter(logging.ERROR)

# Enable low-level fault handler: writes native stack trace on low-level crash / segfault.
# In windowed mode (PyInstaller console=False), sys.stderr is None, so direct fault output
# to an open file descriptor.
_fault_handler_file = None
try:
    if sys.stderr is not None and hasattr(sys.stderr, "fileno"):
        faulthandler.enable(file=sys.stderr)
    else:
        _crash_log_path = get_writable_path("app_crash.log")
        _fault_handler_file = open(_crash_log_path, "a", encoding="utf-8")
        faulthandler.enable(file=_fault_handler_file)
except Exception as _fh_exc:
    logging.debug("No se pudo habilitar faulthandler: %s", _fh_exc)



def _patch_customtkinter_windows_titlebar() -> None:
    """Monkey-patch CustomTkinter's Windows titlebar color handlers to prevent TclError.

    In CustomTkinter on Windows, changing titlebar colors captures focus_get() and schedules
    a focus restoration after 10ms (CTkToplevel) or 1ms (CTk). If the focused widget (or its
    parent modal) is destroyed during this interval, calling .focus() on a deleted Tcl widget
    raises: _tkinter.TclError: invalid command name '...!ctkcanvas'.
    """
    if not sys.platform.startswith("win"):
        return

    import ctypes

    orig_toplevel_titlebar = getattr(ctk.CTkToplevel, "_windows_set_titlebar_color", None)
    if orig_toplevel_titlebar:
        def safe_toplevel_titlebar(self, color_mode: str):
            if sys.platform.startswith("win") and not getattr(self, "_deactivate_windows_window_header_manipulation", False):
                self._state_before_windows_set_titlebar_color = self.state()
                try:
                    self.focused_widget_before_widthdraw = self.focus_get()
                except Exception:
                    self.focused_widget_before_widthdraw = None

                super(ctk.CTkToplevel, self).withdraw()
                super(ctk.CTkToplevel, self).update()

                if color_mode.lower() == "dark":
                    val = 1
                elif color_mode.lower() == "light":
                    val = 0
                else:
                    return

                try:
                    hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
                    if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(val)), 4) != 0:
                        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(ctypes.c_int(val)), 4)
                except Exception:
                    pass

                self._windows_set_titlebar_color_called = True
                self.after(5, self._revert_withdraw_after_windows_set_titlebar_color)

                target = self.focused_widget_before_widthdraw
                self.focused_widget_before_widthdraw = None
                if target is not None:
                    def safe_focus():
                        try:
                            if target and getattr(target, "winfo_exists", lambda: False)():
                                target.focus()
                        except Exception:
                            pass
                    self.after(10, safe_focus)

        ctk.CTkToplevel._windows_set_titlebar_color = safe_toplevel_titlebar

    orig_ctk_titlebar = getattr(ctk.CTk, "_windows_set_titlebar_color", None)
    if orig_ctk_titlebar:
        def safe_ctk_titlebar(self, color_mode: str):
            if sys.platform.startswith("win") and not getattr(self, "_deactivate_windows_window_header_manipulation", False):
                if getattr(self, "_window_exists", False):
                    self._state_before_windows_set_titlebar_color = self.state()
                    if self._state_before_windows_set_titlebar_color not in ("iconic", "withdrawn"):
                        try:
                            self.focused_widget_before_widthdraw = self.focus_get()
                        except Exception:
                            self.focused_widget_before_widthdraw = None
                        super(ctk.CTk, self).withdraw()
                else:
                    self._state_before_windows_set_titlebar_color = self.state()
                    try:
                        self.focused_widget_before_widthdraw = self.focus_get()
                    except Exception:
                        self.focused_widget_before_widthdraw = None
                    super(ctk.CTk, self).withdraw()
                    super(ctk.CTk, self).update()

                if color_mode.lower() == "dark":
                    val = 1
                elif color_mode.lower() == "light":
                    val = 0
                else:
                    return

                try:
                    hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
                    if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(val)), 4) != 0:
                        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(ctypes.c_int(val)), 4)
                except Exception:
                    pass

                if getattr(self, "_window_exists", False) or True:
                    if self._state_before_windows_set_titlebar_color == "normal":
                        self.deiconify()
                    elif self._state_before_windows_set_titlebar_color == "iconic":
                        self.iconify()
                    elif self._state_before_windows_set_titlebar_color == "zoomed":
                        self.deiconify()
                        self.state("zoomed")
                    else:
                        self.state(self._state_before_windows_set_titlebar_color)

                target = self.focused_widget_before_widthdraw
                self.focused_widget_before_widthdraw = None
                if target is not None:
                    def safe_focus():
                        try:
                            if target and getattr(target, "winfo_exists", lambda: False)():
                                target.focus()
                        except Exception:
                            pass
                    self.after(1, safe_focus)

        ctk.CTk._windows_set_titlebar_color = safe_ctk_titlebar


_patch_customtkinter_windows_titlebar()


def global_exception_handler(exctype, value, tb):
    """Trap all unhandled exceptions, write traceback to app_debug.log, and show modal alert."""
    err_str = str(value)
    # Ignore benign TclError when a delayed callback fires on an already destroyed widget
    if issubclass(exctype, tk.TclError) and ("invalid command name" in err_str or "can't invoke" in err_str):
        logging.warning("Ignorando TclError de ciclo de vida en widget destruido: %s", err_str)
        return

    err_msg = "".join(traceback.format_exception(exctype, value, tb))
    logging.critical("Excepción no capturada en el sistema:\n%s", err_msg)
    print("Excepción no capturada:\n", err_msg, file=sys.stderr)
    try:
        messagebox.showerror(
            "Error Inesperado del Sistema",
            f"Ocurrió un error inesperado:\n{value}\n\nLos detalles han sido registrados en 'app_debug.log'."
        )
    except Exception:
        pass


class App(ctk.CTk):
    """Single root window controller managing frame switching without destroying Tcl roots."""

    def __init__(self):
        super().__init__()
        logging.info("Inicializando aplicación XL Burguer (Single-Window Frame Switcher)...")

        # Set Windows taskbar AppUserModelID for taskbar icon grouping
        if sys.platform.startswith("win"):
            import ctypes
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("xlburguer.pos.1.0")
            except Exception:
                pass

        # Set title and visual themes
        self.title("XL Burguer - Sistema POS & Gestión")
        self.configure(fg_color=DarkTheme.BG_ROOT)
        self.minsize(1000, 620)

        # Set official OS window icon
        set_window_icon(self)

        # Hook Tkinter callback exceptions — use INSTANCE assignment so it
        # only affects this CTk window (class-level patch is not reliable across
        # CTk versions and can cause recursion in some edge cases).
        self.report_callback_exception = self._on_tk_callback_exception

        # Session and views state
        self.current_user: Optional[User] = None
        self.frames = {}
        self.nav_buttons = {}
        self._dirty_frames = {"pos", "inventory", "stats", "users"}

        # Build UI layout
        self._build_layout()

        # Maximize or adjust window immediately so login and application open in full screen
        try:
            self.state("zoomed")
        except Exception:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            self.geometry(f"{screen_w-20}x{screen_h-60}+0+0")

        # Show initial login frame in full screen
        self.show_frame("login")

        # F11 shortcut to toggle true fullscreen mode
        self.bind("<F11>", self._toggle_fullscreen)

        # Clean window close handler
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        logging.info("App.__init__() completado exitosamente.")

    def mark_dirty(self, *frame_names: str) -> None:
        """Mark one or more frames as requiring data reload on next view switch."""
        for name in frame_names:
            self._dirty_frames.add(name)

    def _on_tk_callback_exception(self, exctype, value, tb):
        """Intercept unhandled Tkinter event callback exceptions."""
        global_exception_handler(exctype, value, tb)

    def _set_responsive_geometry(self, target_w: int, target_h: int) -> None:
        """Center the window properly taking screen resolution into account."""
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        w = min(target_w, screen_w - 40)
        h = min(target_h, screen_h - 70)
        x = max(10, (screen_w - w) // 2)
        y = max(10, (screen_h - h) // 2 - 25)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_layout(self) -> None:
        # Master horizontal layout container
        self.master_container = ctk.CTkFrame(self, fg_color=DarkTheme.BG_ROOT, corner_radius=0)
        self.master_container.pack(fill="both", expand=True)

        # Unmapped sidebar compatibility placeholder (kept unmapped so legacy tests do not raise AttributeError)
        self.sidebar = ctk.CTkFrame(self.master_container, width=0, height=0)

        # Main Content Container
        self.content_container = ctk.CTkFrame(self.master_container, fg_color=DarkTheme.BG_CONTENT, corner_radius=0)
        self.content_container.pack(fill="both", expand=True)

        # Initialize Navbar Animator for fluid transitions & micro-interactions
        self.navbar_animator = NavbarAnimator(self)

        # Top Navbar (Height 68 for enlarged, comfortable touch targets & modern aesthetics)
        self.top_navbar = ctk.CTkFrame(
            self.content_container,
            fg_color=DarkTheme.BG_NAVBAR,
            border_width=0,
            height=NavbarAnimator.NAVBAR_HEIGHT,
            corner_radius=0
        )
        self.top_navbar.pack_propagate(False)

        # ── Left Side: Logo & Navigation Tabs ──────────────────────────────────
        letters_path = get_asset_path("logoHorizontal.png")
        if not os.path.exists(letters_path):
            letters_path = get_asset_path("XL_Burguer_logo.png")
        if os.path.exists(letters_path):
            try:
                pil_let = Image.open(letters_path).convert("RGBA")
                # Enlarged high-definition logo (aspect ratio ~2.47:1 -> 148x58)
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
        # Inactive: icon only (width 52). Active: icon + module name (width 135).
        self.nav_items_meta = {
            "pos": ("cart_plus", "Ventas"),
            "inventory": ("cube", "Inventario"),
            "stats": ("stats", "Estadísticas"),
            "users": ("users", "Usuarios"),
        }

        for view_key, (icon_key, _name) in self.nav_items_meta.items():
            icon_img = get_ctk_icon(f"{icon_key}_slate", size=(18, 18))
            btn = ctk.CTkButton(
                self.top_navbar,
                text="",
                image=icon_img,
                width=NavbarAnimator.BTN_COLLAPSED_WIDTH,
                height=NavbarAnimator.ITEM_HEIGHT,
                fg_color="#111624",
                border_color="#283347",
                border_width=1,
                hover_color="#182033",
                corner_radius=9,
                command=lambda k=view_key: self.show_frame(k)
            )
            btn.pack(side="left", padx=4, pady=13)
            self.navbar_animator.attach_button_hover(btn, view_key)
            self.nav_buttons[view_key] = btn

        # ── Right Side: Logout, Sound & User Badge ────────────────────────────
        # 1. Far Right: Logout Button in dark red container with red exit icon
        logout_img = get_ctk_icon("logout_red", size=(18, 18))
        self.logout_btn = ctk.CTkButton(
            self.top_navbar,
            text="",
            image=logout_img,
            width=NavbarAnimator.LOGOUT_WIDTH,
            height=NavbarAnimator.ITEM_HEIGHT,
            fg_color="#220D11",
            border_color="#DC2626",
            border_width=1.5,
            hover_color="#381419",
            corner_radius=9,
            command=self.logout
        )
        self.logout_btn.pack(side="right", padx=(4, 16), pady=13)
        self.navbar_animator.attach_logout_hover(self.logout_btn, self.logout)

        # 2. Sound Mute / Unmute Toggle Button (Electric cyan volume icon)
        from utils.sound_manager import sound_manager
        vol_img = get_ctk_icon("volume_cyan" if sound_manager.enabled else "volume_muted", size=(18, 18))
        self.sound_btn = ctk.CTkButton(
            self.top_navbar,
            text="",
            image=vol_img,
            width=38,
            height=NavbarAnimator.ITEM_HEIGHT,
            fg_color="#111724",
            border_color="#253147",
            border_width=1,
            hover_color="#182033",
            corner_radius=9,
            command=self._toggle_sound
        )
        self.sound_btn.pack(side="right", padx=(4, 6), pady=13)

        # 3. Logged-in User Badge in dark capsule container (to the left of sound button)
        self.user_badge_frame = ctk.CTkFrame(
            self.top_navbar,
            fg_color="#111724",
            border_color="#253147",
            border_width=1,
            corner_radius=16,
            height=NavbarAnimator.USER_BADGE_HEIGHT
        )
        self.user_badge_frame.pack(side="right", padx=(4, 8), pady=13)

        user_icon_img = get_ctk_icon("circle_user_slate", size=(18, 18))
        self.user_badge_icon = ctk.CTkLabel(
            self.user_badge_frame,
            image=user_icon_img,
            text=""
        )
        self.user_badge_icon.pack(side="left", padx=(10, 0), pady=4)

        self.user_badge_lbl = ctk.CTkLabel(
            self.user_badge_frame,
            text="Administrador",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#CBD5E1"
        )
        self.user_badge_lbl.pack(side="left", padx=(6, 12), pady=7)
        self.navbar_animator.attach_badge_hover(self.user_badge_frame, self.user_badge_lbl)

        # Scale status indicator removed from navbar per user request ("elimina ahi lo de emular la bascula")
        self.scale_box = None
        self.scale_status_lbl = None

        # ── Views Container ──────────────────────────────────────────────────
        self.views_container = ctk.CTkFrame(self.content_container, fg_color=DarkTheme.BG_ROOT, corner_radius=0)

        # Pre-instantiate LoginFrame in content_container
        self.frames["login"] = LoginFrame(
            parent=self.content_container,
            on_login_success=self.on_login_success
        )

    def _toggle_sound(self) -> None:
        """Toggle acoustic feedback on/off."""
        from utils.sound_manager import sound_manager
        is_on = sound_manager.toggle_sound()
        vol_img = get_ctk_icon("volume_cyan" if is_on else "volume_muted", size=(18, 18))
        self.sound_btn.configure(image=vol_img)

    def _update_user_badge(self, user: Optional[User]) -> None:
        """Format display text for logged-in user in top navbar badge."""
        if not user:
            self.user_badge_lbl.configure(text="Administrador")
            return
        if user.full_name and user.full_name.strip():
            display_name = user.full_name.strip()
        else:
            display_name = user.username or "Administrador"
        self.user_badge_lbl.configure(text=display_name)

    def _configure_nav_tabs_for_user(self) -> None:
        """Display or hide navigation tabs according to current user role.
        Administrador: Full access to all panels (pos, inventory, stats, users).
        Cajero POS: Only access to Ventas (pos) and Inventario (inventory).
        """
        is_admin = bool(self.current_user and self.current_user.is_admin)
        for btn in self.nav_buttons.values():
            btn.pack_forget()

        allowed_tabs = ["pos", "inventory"] if not is_admin else ["pos", "inventory", "stats", "users"]
        for k in allowed_tabs:
            btn = self.nav_buttons.get(k)
            if btn:
                btn.pack(side="left", padx=4, pady=13)

    def on_login_success(self, user: User) -> None:
        """Handle successful authentication: show top navigation bar and transition to POS view."""
        logging.info("on_login_success recibido en App para usuario '%s'.", user.username)
        self.current_user = user

        # Update top navbar user badge
        self._update_user_badge(user)

        # Configure visible navigation tabs for user role
        self._configure_nav_tabs_for_user()

        # Update role permissions in InventoryFrame if already instantiated
        if "inventory" in self.frames and hasattr(self.frames["inventory"], "set_current_user"):
            self.frames["inventory"].set_current_user(user)

        # Maximize or adjust window for full POS experience
        try:
            self.state("zoomed")
        except Exception:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            self.geometry(f"{screen_w-20}x{screen_h-60}+0+0")

        # Switch to POS frame
        self.show_frame("pos")

    def show_frame(self, frame_name: str) -> None:
        """Switch active frame cleanly with top navbar and views container."""
        logging.info("Cambiando a frame: '%s'", frame_name)

        # RBAC Check: Cajero POS is strictly forbidden from accessing 'stats' and 'users'
        is_admin = bool(self.current_user and self.current_user.is_admin)
        if frame_name in ("stats", "users") and not is_admin:
            logging.warning("Acceso denegado a '%s': el usuario actual no es Administrador.", frame_name)
            frame_name = "pos"

        # Update top navbar button highlights with fluid morphing and animations
        if hasattr(self, "navbar_animator"):
            self.navbar_animator.animate_tab_switch(self.nav_buttons, self.nav_items_meta, frame_name)

        # Hide all existing frames
        for f in self.frames.values():
            f.pack_forget()

        if frame_name == "login":
            self.top_navbar.pack_forget()
            self.views_container.pack_forget()
            self.content_container.configure(fg_color=DarkTheme.BG_ROOT)
        else:
            self.content_container.configure(fg_color=DarkTheme.BG_ROOT)
            self.top_navbar.pack(side="top", fill="x")
            self.views_container.pack(side="top", fill="both", expand=True)

        if frame_name not in self.frames:
            try:
                target_parent = self.content_container if frame_name == "login" else self.views_container
                if frame_name == "pos":
                    logging.info("Construyendo POSFrame (primera vez)...")
                    self.frames["pos"] = POSFrame(
                        parent=target_parent,
                        current_user=self.current_user
                    )
                    logging.info("POSFrame construido exitosamente.")
                elif frame_name == "inventory":
                    logging.info("Construyendo InventoryFrame (primera vez)...")
                    self.frames["inventory"] = InventoryFrame(
                        parent=target_parent,
                        current_user=self.current_user
                    )
                    logging.info("InventoryFrame construido exitosamente.")
                elif frame_name == "stats":
                    logging.info("Construyendo StatsFrame (primera vez)...")
                    self.frames["stats"] = StatsFrame(parent=target_parent)
                    logging.info("StatsFrame construido exitosamente.")
                elif frame_name == "users":
                    logging.info("Construyendo UsersFrame (primera vez)...")
                    self.frames["users"] = UsersFrame(parent=target_parent)
                    logging.info("UsersFrame construido exitosamente.")
            except Exception as _frame_exc:
                _tb = traceback.format_exc()
                logging.critical(
                    "Error construyendo frame '%s':\n%s", frame_name, _tb
                )
                messagebox.showerror(
                    "Error al cargar vista",
                    f"No se pudo cargar la vista '{frame_name}':\n\n"
                    f"{_frame_exc}\n\n"
                    "Revise 'app_debug.log' para el traceback completo.",
                    parent=self,
                )
                return  # Abort frame switch cleanly; leave login visible

        active_frame = self.frames.get(frame_name)
        if active_frame:
            active_frame.pack(fill="both", expand=True)

            # Trigger view-specific refreshes only when initially loaded or marked dirty
            is_dirty = frame_name in self._dirty_frames
            if frame_name == "login":
                if hasattr(active_frame, "focus_login"):
                    active_frame.focus_login()
            elif frame_name == "pos":
                if hasattr(active_frame, "set_user") and self.current_user:
                    active_frame.set_user(self.current_user)
                if is_dirty or not getattr(active_frame, "_catalog_loaded", False):
                    if hasattr(active_frame, "refresh_catalog"):
                        active_frame.refresh_catalog()
                        active_frame._catalog_loaded = True
                    self._dirty_frames.discard("pos")
                if hasattr(active_frame, "barcode_entry"):
                    active_frame.barcode_entry.focus_set()
            elif frame_name == "inventory":
                if hasattr(active_frame, "set_current_user"):
                    active_frame.set_current_user(self.current_user)
                if is_dirty:
                    if hasattr(active_frame, "load_data"):
                        active_frame.load_data()
                    self._dirty_frames.discard("inventory")
            elif frame_name == "stats":
                if is_dirty:
                    if hasattr(active_frame, "refresh_stats"):
                        active_frame.refresh_stats()
                    self._dirty_frames.discard("stats")
            elif frame_name == "users":
                if is_dirty:
                    if hasattr(active_frame, "load_data"):
                        active_frame.load_data()
                    self._dirty_frames.discard("users")

    def logout(self) -> None:
        """Confirm logout and return cleanly to LoginFrame."""
        if messagebox.askyesno(
            "Cerrar Sesión",
            "¿Está seguro de que desea salir al inicio de sesión?",
            parent=self
        ):
            logging.info("Cerrando sesión de usuario '%s'.", self.current_user.username if self.current_user else "N/A")
            self.current_user = None

            # Reset POS cart if initialized
            if "pos" in self.frames and hasattr(self.frames["pos"], "reset_session"):
                self.frames["pos"].reset_session()

            # Maintain full screen / maximized window for login
            try:
                self.state("zoomed")
            except Exception:
                pass

            # Show login frame and reset credentials fields
            self.show_frame("login")
            if "login" in self.frames:
                self.frames["login"].reset_fields()


    def destroy(self) -> None:
        """Clean teardown of application resources and exit."""
        if hasattr(self, "navbar_animator"):
            try:
                self.navbar_animator.cleanup()
            except Exception:
                pass
        super().destroy()

    def _on_close(self) -> None:
        """Clean teardown of application exit."""
        logging.info("Cerrando aplicación XL Burguer...")
        self.destroy()

    def _toggle_fullscreen(self, event=None) -> None:
        """Toggle true borderless fullscreen mode with F11."""
        is_fullscreen = bool(self.attributes("-fullscreen"))
        self.attributes("-fullscreen", not is_fullscreen)
        if is_fullscreen:
            try:
                self.state("zoomed")
            except Exception:
                pass

    def mainloop(self, *args, **kwargs) -> None:
        """Run main event loop ensuring maximized / full screen state persists on startup."""
        def _apply_maximized():
            try:
                self.state("zoomed")
            except Exception:
                pass

        # Counteract CustomTkinter's internal deiconify() call in CTk.mainloop()
        self.after(10, _apply_maximized)
        self.after(50, _apply_maximized)
        self.after(100, _apply_maximized)
        self.after(200, _apply_maximized)
        super().mainloop(*args, **kwargs)


def main() -> None:
    """Bootstrap application."""
    sys.excepthook = global_exception_handler
    tk.Tk.report_callback_exception = global_exception_handler

    logging.info("=== Iniciando XL Burguer POS ===")

    # 1. Configure CustomTkinter Aesthetics (Dark Gourmet Butcher Edition)
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    # 2. Verify Assets
    try:
        ensure_assets()
        logging.info("Assets visuales verificados.")
    except Exception as e:
        logging.warning("Advertencia generando assets: %s", e)

    # 3. Initialize SQLite Database and Seed Catalog
    try:
        initialize_database()
        logging.info("Base de datos SQLite verificada e inicializada.")
    except Exception as e:
        logging.critical("Fallo al inicializar base de datos: %s", e)
        messagebox.showerror(
            "Error Fatal de Base de Datos",
            f"No se pudo inicializar la base de datos local SQLite:\n{e}\n\nRevise 'app_debug.log' para más detalles."
        )
        sys.exit(1)

    # 4. Start Single Window Application
    app = App()
    app.mainloop()
    logging.info("=== Aplicación finalizada con éxito ===")


if __name__ == "__main__":
    main()
