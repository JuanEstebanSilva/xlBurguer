"""Ticket Preview Modal for XL Burguer.
Interactive CustomTkinter modal displaying thermal receipt in graphical (logos & QR)
or monospace text mode with destination printer selection and instant printing.
"""

import logging
from tkinter import messagebox
from typing import Optional

import customtkinter as ctk

from hardware.ticket_printer import (
    get_target_printer,
    is_thermal_or_text_printer,
    list_available_printers,
    print_ticket_raw,
    render_ticket_image,
    save_printer_preference,
    strip_accents,
)
from utils.asset_manager import center_modal
from utils.theme import DarkTheme


class TicketPreviewModal(ctk.CTkToplevel):
    """Non-blocking modern modal displaying the 40-column thermal receipt preview."""

    def __init__(self, parent, ticket_text: str, on_close_callback=None, *args, **kwargs):
        super().__init__(parent)
        self.ticket_text = ticket_text
        self.on_close_callback = on_close_callback

        # Detect printers and initial target
        self.available_printers = list_available_printers()
        self.selected_printer = get_target_printer() or (
            self.available_printers[0] if self.available_printers else "Generic / Text Only"
        )
        self.is_cash = "EFECTIVO RECIBIDO" in ticket_text
        self.view_mode = "graphic"

        self.title("Comprobante de Venta - Vista Previa")
        self.resizable(False, False)
        self.configure(fg_color=DarkTheme.BG_MODAL)

        self._build_ui()
        center_modal(self, 520, 720, parent)

        # Modal window properties
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda e: self._on_close())
        self.bind("<Return>", lambda e: self._on_print())
        self.bind("<KP_Enter>", lambda e: self._on_print())
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        # Header banner
        header = ctk.CTkFrame(
            self,
            fg_color=DarkTheme.BG_MODAL_HEADER,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=0,
            height=54
        )
        header.pack(fill="x", side="top")

        title_lbl = ctk.CTkLabel(
            header,
            text="🧾 Comprobante de Venta - XL Burguer",
            font=ctk.CTkFont(family="Cambria", size=14, weight="bold", slant="italic"),
            text_color="#666BC5"
        )
        title_lbl.pack(pady=14)

        # Printer selector & status toolbar
        printer_bar = ctk.CTkFrame(
            self,
            fg_color=DarkTheme.BG_CARD,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=8,
            height=44
        )
        printer_bar.pack(fill="x", padx=18, pady=(10, 4))

        lbl_icon = ctk.CTkLabel(
            printer_bar,
            text="🖨️",
            font=ctk.CTkFont(size=14)
        )
        lbl_icon.pack(side="left", padx=(12, 4), pady=6)

        lbl_target = ctk.CTkLabel(
            printer_bar,
            text="Destino:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=DarkTheme.TEXT_MUTED
        )
        lbl_target.pack(side="left", padx=(0, 8), pady=6)

        if self.available_printers:
            self.printer_var = ctk.StringVar(value=self.selected_printer)
            self.printer_dropdown = ctk.CTkOptionMenu(
                printer_bar,
                values=self.available_printers,
                variable=self.printer_var,
                command=self._on_printer_changed,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                fg_color=DarkTheme.BG_CARD_ELEVATED,
                button_color=DarkTheme.BORDER_FOCUS,
                button_hover_color=DarkTheme.ACCENT_GOLD_HOVER,
                text_color=DarkTheme.TEXT_PRIMARY,
                dropdown_fg_color=DarkTheme.BG_CARD,
                dropdown_hover_color=DarkTheme.BG_CARD_ELEVATED,
                dropdown_text_color=DarkTheme.TEXT_PRIMARY,
                height=28,
                corner_radius=6,
                width=210
            )
            self.printer_dropdown.pack(side="left", padx=4, pady=6)
        else:
            fallback_lbl = ctk.CTkLabel(
                printer_bar,
                text=self.selected_printer,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=DarkTheme.TEXT_PRIMARY
            )
            fallback_lbl.pack(side="left", padx=4, pady=6)

        # Badge mode
        self.badge_lbl = ctk.CTkLabel(
            printer_bar,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=4,
            padx=8,
            pady=2
        )
        self.badge_lbl.pack(side="right", padx=(4, 6), pady=6)
        self._update_badge()

        # View mode toggle button
        self.view_toggle_btn = ctk.CTkButton(
            printer_bar,
            text="📄 Ver Texto",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            fg_color=DarkTheme.BG_CARD_ELEVATED,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            hover_color=DarkTheme.ACCENT_GOLD_HOVER,
            text_color=DarkTheme.TEXT_PRIMARY,
            height=28,
            width=96,
            corner_radius=6,
            command=self._toggle_view
        )
        self.view_toggle_btn.pack(side="right", padx=(4, 10), pady=6)

        # Receipt display container
        self.receipt_container = ctk.CTkFrame(
            self,
            fg_color=DarkTheme.BG_CARD,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=8
        )
        self.receipt_container.pack(fill="both", expand=True, padx=18, pady=8)

        # 1. Graphical View (High-DPI scrollable ticket with logos & QR)
        self.scrollable_graphic = ctk.CTkScrollableFrame(
            self.receipt_container,
            fg_color="#F8FAFC",
            border_width=0,
            corner_radius=6
        )

        try:
            self.ticket_img = render_ticket_image(self.ticket_text)
            disp_w = int(self.ticket_img.width * 0.65)
            disp_h = int(self.ticket_img.height * 0.65)
            self.ctk_img = ctk.CTkImage(
                light_image=self.ticket_img,
                dark_image=self.ticket_img,
                size=(disp_w, disp_h)
            )
            self.img_label = ctk.CTkLabel(
                self.scrollable_graphic,
                image=self.ctk_img,
                text="",
                fg_color="transparent"
            )
            self.img_label.pack(pady=10, expand=True)
            self.has_graphic_img = True
        except Exception as e:
            logging.warning("Error al generar imagen de ticket para vista previa: %s", e)
            self.has_graphic_img = False

        # 2. Text View (40-column monospace)
        self.text_frame = ctk.CTkFrame(
            self.receipt_container,
            fg_color="#FFFDF7",
            border_width=0,
            corner_radius=6
        )
        self.textbox = ctk.CTkTextbox(
            self.text_frame,
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#18181B",
            fg_color="#FFFDF7",
            corner_radius=6,
            wrap="none"
        )
        self.textbox.pack(fill="both", expand=True, padx=6, pady=6)
        self.textbox.insert("1.0", self.ticket_text)
        self.textbox.configure(state="disabled")

        # Initial view selection
        if getattr(self, "has_graphic_img", False):
            self.scrollable_graphic.pack(fill="both", expand=True, padx=4, pady=4)
        else:
            self.view_mode = "text"
            self.text_frame.pack(fill="both", expand=True, padx=4, pady=4)
            self.view_toggle_btn.configure(state="disabled")

        # Bottom Actions
        actions = ctk.CTkFrame(
            self,
            fg_color=DarkTheme.BG_MODAL_HEADER,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=0,
            height=64
        )
        actions.pack(fill="x", side="bottom")

        self.reprint_btn = ctk.CTkButton(
            actions,
            text="🖨️ Imprimir Ticket (Enter)",
            fg_color=DarkTheme.SUCCESS_PRIMARY,
            hover_color=DarkTheme.SUCCESS_HOVER,
            text_color="#FFFFFF",
            corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._on_print
        )
        self.reprint_btn.pack(side="left", padx=18, pady=14, expand=True)

        close_btn = ctk.CTkButton(
            actions,
            text="Cerrar (Esc)",
            fg_color=DarkTheme.BTN_NEUTRAL_BG,
            border_color=DarkTheme.BTN_NEUTRAL_BORDER,
            border_width=1,
            hover_color=DarkTheme.BTN_NEUTRAL_HOVER,
            text_color=DarkTheme.BTN_NEUTRAL_TEXT,
            corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._on_close
        )
        close_btn.pack(side="right", padx=18, pady=14, expand=True)

    def _update_badge(self) -> None:
        if is_thermal_or_text_printer(self.selected_printer):
            self.badge_lbl.configure(
                text="● Térmica RAW",
                text_color=DarkTheme.SUCCESS_PRIMARY,
                fg_color="#064E3B"
            )
        else:
            self.badge_lbl.configure(
                text="● Modo Hoja GDI",
                text_color="#F59E0B",
                fg_color="#451A03"
            )

    def _on_printer_changed(self, chosen_printer: str) -> None:
        self.selected_printer = chosen_printer
        save_printer_preference(chosen_printer)
        self._update_badge()

    def _on_close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if self.on_close_callback:
            try:
                self.on_close_callback()
            except Exception:
                pass

    def _on_print(self) -> None:
        success, msg = print_ticket_raw(
            self.ticket_text,
            printer_name=self.selected_printer,
            open_drawer=self.is_cash
        )
        if success:
            messagebox.showinfo("Impresora Térmica", msg, parent=self)
        else:
            messagebox.showwarning("Impresora Térmica", msg, parent=self)
        self._on_close()

    def _toggle_view(self) -> None:
        if self.view_mode == "graphic":
            self.view_mode = "text"
            self.scrollable_graphic.pack_forget()
            self.text_frame.pack(fill="both", expand=True, padx=4, pady=4)
            self.view_toggle_btn.configure(text="🧾 Ver Gráfico")
        else:
            self.view_mode = "graphic"
            self.text_frame.pack_forget()
            self.scrollable_graphic.pack(fill="both", expand=True, padx=4, pady=4)
            self.view_toggle_btn.configure(text="📄 Ver Texto")
