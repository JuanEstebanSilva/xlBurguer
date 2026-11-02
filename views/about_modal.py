"""About Modal Dialog for Carnicería San Diego.
Displays corporate identity, official symbol logo ('logoCompleto.png'),
system diagnostics, and version info in Dark Theme.
"""

import os
import customtkinter as ctk
from PIL import Image

from utils.asset_manager import get_asset_path, set_window_icon, center_modal
from utils.theme import DarkTheme


class AboutModal(ctk.CTkToplevel):
    """Corporate Identity and System Information modal dialog (Dark Theme)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Acerca de")
        self.configure(fg_color=DarkTheme.BG_MODAL)
        self.resizable(False, False)

        self._build_ui()
        center_modal(self, 480, 520, parent)

        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self) -> None:
        container = ctk.CTkFrame(self, fg_color=DarkTheme.BG_MODAL, corner_radius=0)
        container.pack(fill="both", expand=True, padx=28, pady=24)

        # 1. Corporate Symbol Emblem ('logoCompleto.png' / 'logo San Diego')
        logo_path = get_asset_path("logoCompleto.png")
        if not os.path.exists(logo_path):
            logo_path = get_asset_path("logo San Diego")
        if os.path.exists(logo_path):
            try:
                pil_logo = Image.open(logo_path).convert("RGBA")
                # Aspect ratio ~1.076:1 -> 114x106
                ctk_logo = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(114, 106))
                lbl_logo = ctk.CTkLabel(container, image=ctk_logo, text="")
                lbl_logo.pack(pady=(4, 10))
            except Exception:
                pass

        # 2. Company & Product Titles
        ctk.CTkLabel(
            container,
            text="CARNICERÍA SAN DIEGO",
            font=ctk.CTkFont(family="Cambria", size=20, weight="bold", slant="italic"),
            text_color="#C5A059"
        ).pack()

        ctk.CTkLabel(
            container,
            text="SISTEMA DE PUNTO DE VENTA & GESTIÓN COMERCIAL",
            font=ctk.CTkFont(family="Cambria", size=10, weight="bold", slant="italic"),
            text_color="#C5A059"
        ).pack(pady=(2, 0))

        ctk.CTkLabel(
            container,
            text="Villa de Leyva • Boyacá • Colombia",
            font=ctk.CTkFont(family="Cambria", size=11, weight="bold", slant="italic"),
            text_color="#C5A059"
        ).pack(pady=(2, 14))

        ctk.CTkFrame(container, fg_color=DarkTheme.BORDER_SUBTLE, height=1).pack(fill="x", pady=(0, 14))

        # 3. System Specs & Features Card
        info_card = ctk.CTkFrame(
            container,
            fg_color=DarkTheme.BG_CARD_ELEVATED,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=10
        )
        info_card.pack(fill="x", pady=(0, 18), ipady=6, padx=4)

        specs = [
            ("Versión del Sistema:", "2.1 (Dark Gourmet Edition)"),
            ("Interfaz Gráfica:", "CustomTkinter + Touchscreen HMI (Dark Mode)"),
            ("Base de Datos:", "SQLite3 Relacional (Local Offline)"),
            ("Impresión Fiscal/POS:", "Ticket Térmico 40 Columnas (ESC/POS)"),
            ("Control de Báscula:", "Driver Serial RS-232 / Emulador Activo"),
        ]

        for label, val in specs:
            row = ctk.CTkFrame(info_card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=3)
            ctk.CTkLabel(
                row,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=DarkTheme.TEXT_MUTED
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=val,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=DarkTheme.TEXT_PRIMARY
            ).pack(side="right")

        # 4. Close Button
        close_btn = ctk.CTkButton(
            container,
            text="Cerrar",
            height=38,
            fg_color=DarkTheme.BTN_NEUTRAL_BG,
            border_color=DarkTheme.BTN_NEUTRAL_BORDER,
            border_width=1,
            hover_color=DarkTheme.BTN_NEUTRAL_HOVER,
            text_color=DarkTheme.BTN_NEUTRAL_TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            command=self.destroy
        )
        close_btn.pack(fill="x", padx=4)
