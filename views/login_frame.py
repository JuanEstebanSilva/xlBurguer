"""Login Frame for XL Burguer.
High-end visual GUI authentication presentation.
Split 50/50 desktop presentation:
- Left panel: Ultra-dark charcoal (#0D0E12) with centered balanced form (370px),
  official high-contrast brand emblem ('XL_Burguer_completo.png'),
  dark interactive input fields with iconography, focus highlights, password visibility
  toggle, and golden-amber action button.
- Right panel: High-definition gourmet fast-food art ('fondoLogin.jpg')
  in edge-to-edge cover mode without borders or margins.
Responsive behavior gracefully collapses right panel on mobile/narrow viewports.
"""

import logging
import os
import sys
from typing import Optional
import customtkinter as ctk
from PIL import Image, ImageChops, ImageDraw, ImageOps

from database.connection import get_db_connection
from models.user import User, UserModel
from utils.asset_manager import get_asset_path, set_window_icon
from utils.sound_manager import sound_manager
from utils.theme import DarkTheme


class LoginFrame(ctk.CTkFrame):
    """High-end GUI split-panel login frame for POS terminal operation."""

    def __init__(self, parent, on_login_success):
        super().__init__(parent, fg_color=DarkTheme.BG_ROOT, corner_radius=0)
        self.on_login_success = on_login_success
        self._pwd_visible = False
        self._last_rendered_size = (0, 0)
        self._last_logo_size = (0, 0)
        self._meat_pil = None
        self._hunzaia_pil = None
        self._logo_pil = None
        self._logo_lbl = None
        self._right_ctk_img = None
        self._flame_on_img = None
        self._flame_off_img = None
        self._user_icon_img = None
        self._resize_job: Optional[str] = None

        self._build_ui()

    def _build_ui(self) -> None:
        # ── 1. Create Left & Right Panels ────────────────────────────────────
        self.left_panel = ctk.CTkFrame(self, fg_color=DarkTheme.BG_ROOT, corner_radius=0)
        self.right_panel = ctk.CTkFrame(self, fg_color=DarkTheme.BG_ROOT, corner_radius=0)

        # Initial layout: desktop 50/50 split
        self.left_panel.place(relx=0.0, rely=0.0, relwidth=0.5, relheight=1.0)
        self.right_panel.place(relx=0.5, rely=0.0, relwidth=0.5, relheight=1.0)

        # ── 2. Pre-load Assets ────────────────────────────────────────────────
        # Pre-load background image for right panel
        bg_path = get_asset_path("fondo login.png")
        if not os.path.exists(bg_path):
            bg_path = get_asset_path("fondo login.jpg")
        if not os.path.exists(bg_path):
            bg_path = get_asset_path("fondoLogin.png")
        if not os.path.exists(bg_path):
            bg_path = get_asset_path("fondoLogin.jpg")

        if os.path.exists(bg_path):
            try:
                self._meat_pil = Image.open(bg_path).convert("RGB")
                init_w, init_h = 550, 700
                initial_img = self._render_right_image(init_w, init_h)
                if initial_img:
                    self._right_ctk_img = initial_img
                    self._right_lbl = ctk.CTkLabel(self.right_panel, image=self._right_ctk_img, text="")
                    self._right_lbl.place(relx=0.5, rely=0.5, anchor="center")
            except Exception as e:
                logging.warning("No se pudo cargar la imagen de fondo: %s", e)

        # Bind resize for responsive layout and image dynamic scaling
        self.bind("<Configure>", self._on_resize)

        # Pre-load user icon for username field
        user_icon_path = get_asset_path("user-solid-full.png")
        if not os.path.exists(user_icon_path):
            user_icon_path = get_asset_path("user_icon.png")
        if os.path.exists(user_icon_path):
            try:
                pil_user = Image.open(user_icon_path).convert("RGBA")
                self._user_icon_img = ctk.CTkImage(light_image=pil_user, dark_image=pil_user, size=(22, 22))
            except Exception as e:
                logging.warning("No se pudo cargar el icono de usuario: %s", e)

        # Pre-load flame icons for password visibility toggle
        flame_on_p = get_asset_path("flame_active.png")
        flame_off_p = get_asset_path("flame_inactive.png")
        if os.path.exists(flame_on_p) and os.path.exists(flame_off_p):
            try:
                pil_on = Image.open(flame_on_p).convert("RGBA")
                pil_off = Image.open(flame_off_p).convert("RGBA")
                self._flame_on_img = ctk.CTkImage(light_image=pil_on, dark_image=pil_on, size=(22, 22))
                self._flame_off_img = ctk.CTkImage(light_image=pil_off, dark_image=pil_off, size=(22, 22))
            except Exception as e:
                logging.warning("No se pudieron cargar los iconos de llama: %s", e)

        # ── 3. Left Panel: Centered Form Container (Balanced ~370px width) ──
        FORM_WIDTH = 370
        self.form_container = ctk.CTkFrame(
            self.left_panel,
            fg_color="transparent",
            width=FORM_WIDTH,
        )
        self.form_container.place(relx=0.5, rely=0.5, anchor="center")

        # ── 4. Official Brand Emblem ('logoCompleto.png') ──────────────────────
        logo_path = get_asset_path("logoCompleto.png")
        if not os.path.exists(logo_path):
            logo_path = get_asset_path("isotipoBlanco.png")
        if not os.path.exists(logo_path):
            logo_path = get_asset_path("icono principal BN")
        if not os.path.exists(logo_path):
            logo_path = get_asset_path("logo.png")

        if os.path.exists(logo_path):
            try:
                self._logo_pil = Image.open(logo_path).convert("RGBA")
                logo_w = 260
                logo_h = max(50, int(logo_w / (self._logo_pil.width / self._logo_pil.height)))
                self._last_logo_size = (logo_w, logo_h)
                ctk_logo = ctk.CTkImage(light_image=self._logo_pil, dark_image=self._logo_pil, size=(logo_w, logo_h))
                self._logo_lbl = ctk.CTkLabel(self.form_container, image=ctk_logo, text="")
                self._logo_lbl.pack(pady=(0, 22))
            except Exception as e:
                logging.warning("No se pudo cargar el logo oficial de login: %s", e)

        # ── 5. Username Field (Usuario) ───────────────────────────────────────
        ctk.CTkLabel(
            self.form_container,
            text="Usuario",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="normal"),
            text_color="#94A3B8"
        ).pack(anchor="w", pady=(0, 6))

        user_box = ctk.CTkFrame(
            self.form_container,
            width=FORM_WIDTH,
            height=48,
            fg_color="#14161E",
            border_color="#262B3D",
            border_width=1,
            corner_radius=8
        )
        user_box.pack(fill="x", pady=(0, 14))
        user_box.pack_propagate(False)

        self.user_entry = ctk.CTkEntry(
            user_box,
            height=38,
            font=ctk.CTkFont(family="Segoe UI", size=15),
            fg_color="transparent",
            border_width=0,
            text_color="#F8FAFC",
            placeholder_text="Usuario",
            placeholder_text_color="#4B5563"
        )
        self.user_entry.pack(side="left", fill="both", expand=True, padx=(14, 4), pady=4)

        if self._user_icon_img:
            user_icon_lbl = ctk.CTkLabel(user_box, image=self._user_icon_img, text="")
            user_icon_lbl.pack(side="right", padx=(0, 14), pady=4)
            user_icon_lbl.bind("<Button-1>", lambda e: self.user_entry.focus_set())

        self.user_entry.bind("<FocusIn>", lambda e: user_box.configure(border_color="#3A4055"))
        self.user_entry.bind("<FocusOut>", lambda e: user_box.configure(border_color="#262B3D"))
        user_box.bind("<Button-1>", lambda e: self.user_entry.focus_set())

        # ── 6. Password Field (Contraseña) ───────────────────────────────────
        ctk.CTkLabel(
            self.form_container,
            text="Contraseña",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="normal"),
            text_color="#94A3B8"
        ).pack(anchor="w", pady=(0, 6))

        self.pass_box = ctk.CTkFrame(
            self.form_container,
            width=FORM_WIDTH,
            height=48,
            fg_color="#14161E",
            border_color="#262B3D",
            border_width=1,
            corner_radius=8
        )
        self.pass_box.pack(fill="x", pady=(0, 4))
        self.pass_box.pack_propagate(False)

        self.pass_entry = ctk.CTkEntry(
            self.pass_box,
            height=38,
            show="●",
            font=ctk.CTkFont(family="Segoe UI", size=15),
            fg_color="transparent",
            border_width=0,
            text_color="#F8FAFC",
            placeholder_text="••••••",
            placeholder_text_color="#4B5563"
        )
        self.pass_entry.pack(side="left", fill="both", expand=True, padx=(14, 4), pady=4)

        # Password visibility toggle button with flame icon
        btn_kwargs = {
            "width": 36,
            "height": 36,
            "fg_color": "transparent",
            "hover_color": "#1E212B",
            "corner_radius": 6,
            "command": self._toggle_password_visibility,
        }
        if self._flame_off_img:
            self.eye_btn = ctk.CTkButton(
                self.pass_box,
                text="",
                image=self._flame_off_img,
                **btn_kwargs
            )
        else:
            self.eye_btn = ctk.CTkButton(
                self.pass_box,
                text="🔥",
                font=ctk.CTkFont(size=16),
                text_color=DarkTheme.TEXT_MUTED,
                **btn_kwargs
            )
        self.eye_btn.pack(side="right", padx=(0, 8), pady=4)

        self.pass_entry.bind("<FocusIn>", lambda e: self.pass_box.configure(border_color="#3A4055"))
        self.pass_entry.bind("<FocusOut>", lambda e: self.pass_box.configure(border_color="#262B3D"))
        self.pass_box.bind("<Button-1>", lambda e: self.pass_entry.focus_set())

        # ── 7. Error Notification Badge ──────────────────────────────────────
        self.error_container = ctk.CTkFrame(
            self.form_container,
            fg_color="transparent",
            width=FORM_WIDTH,
            height=22
        )
        self.error_container.pack(fill="x", pady=(3, 5))
        self.error_container.pack_propagate(False)

        self.error_lbl = ctk.CTkLabel(
            self.error_container,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=DarkTheme.DANGER_TEXT
        )
        self.error_lbl.pack(anchor="w")

        # ── 8. Action Button ("INICIAR MI TURNO →") ──────────────────────────
        self.login_btn = ctk.CTkButton(
            self.form_container,
            text="INICIAR MI TURNO →",
            width=FORM_WIDTH,
            height=48,
            fg_color="#281F0E",
            border_color="#90763E",
            border_width=1.2,
            hover_color="#382B14",
            text_color="#FFDC8D",
            text_color_disabled="#90763E",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            corner_radius=8,
            command=self._do_login
        )
        self.login_btn.pack(fill="x", pady=(6, 0))

        # Keyboard Navigation bindings
        self.user_entry.bind("<Return>", lambda e: self.pass_entry.focus_set())
        self.pass_entry.bind("<Return>", lambda e: self._do_login())
        self.user_entry.bind("<Tab>", lambda e: (self.pass_entry.focus_set(), "break")[1])
        self.pass_entry.bind("<Tab>", lambda e: (self.login_btn.focus_set(), "break")[1])
        self.pass_entry.bind("<Shift-Tab>", lambda e: (self.user_entry.focus_set(), "break")[1])
        self.login_btn.bind("<Tab>", lambda e: (self.user_entry.focus_set(), "break")[1])
        self.login_btn.bind("<Shift-Tab>", lambda e: (self.pass_entry.focus_set(), "break")[1])

        # Focus username entry immediately so user can start typing
        self.focus_login()

    # ── Background Art Scaling & Composition ──────────────────────────────────
    def _render_right_image(self, w: int, h: int) -> Optional[ctk.CTkImage]:
        """Scale and center gourmet background art, applying a smooth
        gradient fade on the left seam to blend organically into DarkTheme.BG_ROOT (#0D0E12).
        """
        if self._meat_pil is None or w <= 0 or h <= 0:
            return None

        orig_w, orig_h = self._meat_pil.width, self._meat_pil.height
        scale = max(w / orig_w, h / orig_h)
        scaled_w = max(10, int(orig_w * scale))
        scaled_h = max(10, int(orig_h * scale))

        bg_rgba = self._meat_pil.convert("RGBA")
        resized = bg_rgba.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

        # Full panel canvas matching DarkTheme.BG_ROOT (#0D0E12)
        bg = Image.new("RGBA", (w, h), (13, 14, 18, 255))

        # Center horizontally and vertically
        paste_x = (w - scaled_w) // 2
        paste_y = (h - scaled_h) // 2

        bg.paste(resized, (paste_x, paste_y), resized)

        # Smooth cubic gradient fade (desvanecido) on the left seam towards DarkTheme.BG_ROOT (#0D0E12).
        fade_w = max(100, min(260, int(w * 0.28)))
        if fade_w > 0:
            left_grad = Image.new("RGBA", (fade_w, 1))
            for x in range(fade_w):
                t = x / fade_w
                factor = 1.0 - (3.0 * t * t - 2.0 * t * t * t)
                alpha = int(255 * factor)
                left_grad.putpixel((x, 0), (13, 14, 18, alpha))
            grad_strip = left_grad.resize((fade_w, h), Image.Resampling.BILINEAR)
            bg.alpha_composite(grad_strip, (0, 0))

        final_rgb = bg.convert("RGB")
        return ctk.CTkImage(light_image=final_rgb, dark_image=final_rgb, size=(w, h))

    def _on_resize(self, event) -> None:
        """Handle window resizing: debounced responsive layout adaptation and smooth image rescaling."""
        if event.widget not in (self, getattr(self, "_canvas", None)):
            return
        if getattr(self, "_resize_job", None):
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(50, self._do_resize)

    def _do_resize(self) -> None:
        self._resize_job = None
        if not self.winfo_exists():
            return
        w, h = self.winfo_width(), self.winfo_height()
        if w < 100 or h < 100:
            return

        # Responsive layout: Desktop >= 720 split 50/50; Mobile/Narrow < 720 collapses right panel
        if w >= 720:
            self.left_panel.place(relx=0.0, rely=0.0, relwidth=0.5, relheight=1.0)
            self.right_panel.place(relx=0.5, rely=0.0, relwidth=0.5, relheight=1.0)
            right_w = max(50, int(w * 0.5))
            right_h = h
        else:
            self.left_panel.place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)
            self.right_panel.place_forget()
            return

        # Gracefully adapt logo size only when vertical space is constrained (e.g. h < 720)
        if self._logo_pil and self._logo_lbl and self._logo_lbl.winfo_exists():
            target_w = max(140, min(260, int(h * 0.26))) if h < 720 else 260
            target_h = max(40, int(target_w / (self._logo_pil.width / self._logo_pil.height)))
            curr_size = getattr(self, "_last_logo_size", (0, 0))
            if abs(target_w - curr_size[0]) > 8:
                self._last_logo_size = (target_w, target_h)
                new_logo_img = ctk.CTkImage(light_image=self._logo_pil, dark_image=self._logo_pil, size=(target_w, target_h))
                self._logo_lbl.configure(image=new_logo_img)

        # Avoid redundant re-rendering if dimensions have barely changed (< 12px)
        lw, lh = self._last_rendered_size
        if abs(right_w - lw) < 12 and abs(right_h - lh) < 12:
            return

        self._last_rendered_size = (right_w, right_h)
        try:
            new_img = self._render_right_image(right_w, right_h)
            if new_img:
                self._right_ctk_img = new_img
                if hasattr(self, "_right_lbl") and self._right_lbl.winfo_exists():
                    self._right_lbl.configure(image=new_img)
                else:
                    self._right_lbl = ctk.CTkLabel(self.right_panel, image=new_img, text="")
                    self._right_lbl.place(relx=0.5, rely=0.5, anchor="center")
        except Exception as e:
            logging.debug("Error redimensionando imagen derecha de carnes: %s", e)

    def _toggle_password_visibility(self) -> None:
        """Toggle password masking between show='●' and show=''."""
        self._pwd_visible = not self._pwd_visible
        if self._pwd_visible:
            self.pass_entry.configure(show="")
            if self._flame_on_img:
                self.eye_btn.configure(image=self._flame_on_img, text="")
            else:
                self.eye_btn.configure(text="🔥", text_color="#FF9E3C")
        else:
            self.pass_entry.configure(show="●")
            if self._flame_off_img:
                self.eye_btn.configure(image=self._flame_off_img, text="")
            else:
                self.eye_btn.configure(text="🔥", text_color=DarkTheme.TEXT_MUTED)

    # ── Public API ────────────────────────────────────────────────────────────
    def focus_login(self) -> None:
        def _set_focus():
            try:
                if self.winfo_exists() and hasattr(self, "user_entry") and self.user_entry.winfo_exists():
                    self.user_entry.focus_set()
            except Exception:
                pass
        self.after(100, _set_focus)

    def reset_fields(self) -> None:
        self.user_entry.delete(0, "end")
        self.pass_entry.delete(0, "end")
        self._pwd_visible = False
        self.pass_entry.configure(show="●")
        if self._flame_off_img:
            self.eye_btn.configure(image=self._flame_off_img, text="")
        else:
            self.eye_btn.configure(text="🔥", text_color=DarkTheme.TEXT_MUTED)
        self.error_lbl.configure(text="")
        self.focus_login()

    # ── Auth Logic ────────────────────────────────────────────────────────────
    def _do_login(self) -> None:
        username = self.user_entry.get().strip()
        password = self.pass_entry.get()

        if not username or not password:
            self.error_lbl.configure(text="⚠  Ingresa usuario y contraseña.")
            return

        self.login_btn.configure(state="disabled", text="INICIANDO TURNO...", text_color_disabled="#90763E")
        self.after(50, lambda: self._authenticate(username, password))

    def _authenticate(self, username: str, password: str) -> None:
        try:
            with get_db_connection() as conn:
                user = UserModel.authenticate(conn, username, password)

            if user:
                logging.info(
                    "Usuario '%s' autenticado con éxito (rol: '%s').",
                    user.username, user.role
                )
                sound_manager.play_login_success()
                self.error_lbl.configure(text="")
                self.login_btn.configure(state="normal", text="INICIAR MI TURNO →")
                self.on_login_success(user)
            else:
                logging.warning("Fallo de autenticación para '%s'.", username)
                sound_manager.play_error()
                self.error_lbl.configure(text="⚠  Credenciales incorrectas.")
                self.login_btn.configure(state="normal", text="INICIAR MI TURNO →")
                self.pass_entry.delete(0, "end")
                self.pass_entry.focus_set()
        except PermissionError as pe:
            logging.warning("Intento de acceso de operador inactivo '%s': %s", username, pe)
            sound_manager.play_error()
            self.error_lbl.configure(text=f"⚠  {pe}")
            self.login_btn.configure(state="normal", text="INICIAR MI TURNO →")
            self.pass_entry.delete(0, "end")
            self.pass_entry.focus_set()
        except Exception as e:
            logging.error("Error durante login: %s", e)
            sound_manager.play_error()
            self.error_lbl.configure(text=f"⚠  Error de sistema: {e}")
            self.login_btn.configure(state="normal", text="INICIAR MI TURNO →")

    def destroy(self) -> None:
        """Cancel pending resize callbacks before destroying widget tree."""
        if getattr(self, "_resize_job", None):
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
            self._resize_job = None
        super().destroy()


class LoginView(ctk.CTk):
    """Standalone window wrapper around LoginFrame for testing and backward compatibility."""

    def __init__(self, on_login_success):
        super().__init__()
        if sys.platform.startswith("win"):
            import ctypes
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("xlburguer.pos.1.0")
            except Exception:
                pass

        self.title("Sistema POS & Gestión - XL Burguer")
        self.configure(fg_color=DarkTheme.BG_ROOT)
        set_window_icon(self)

        try:
            self.state("zoomed")
        except Exception:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            self.geometry(f"{screen_w-20}x{screen_h-60}+0+0")

        self.login_frame = LoginFrame(self, on_login_success=on_login_success)
        self.login_frame.pack(fill="both", expand=True)

