"""POS (Point of Sale) Frame for XL Burguer.
Sober, ergonomic, high-performance butcher counter presentation layer.
Features a 50/50 Split View:
- Left Panel: Customer identification bar (Cédula lookup, Case A badge, Case B inline quick registration),
  barcode/search, quick cuts pills, giant 32px weight/qty display, live scale read, integrated touch numpad,
  and prominent '➕ Agregar a la Venta' action button (NO intrusive modal popups during weighing).
- Right Panel: Visual receipt cart, itemized cuts, live subtotals, giant totalizer display, and '💳 COBRAR (F12)'.
- Multi-payment Checkout Modal: Efectivo 💵, Transferencia 📲, Tarjeta 💳 with quick denominations and giant change.
"""

import inspect
import logging
import os
import re
import tkinter as tk
from tkinter import messagebox
from typing import Any, Dict, List, Optional, Tuple
import customtkinter as ctk

from database.connection import get_db_connection
from hardware.barcode_scanner import BarcodeScannerListener
from hardware.ticket_printer import format_ticket, print_ticket_raw
from views.ticket_preview_modal import TicketPreviewModal
from models.customer import Customer, CustomerModel
from models.product import (
    Product,
    ProductModel,
    calculate_item_price,
    convert_quantity_to_base,
    format_currency,
    format_currency_short,
)
from models.sale import CartItem, SaleModel
from models.user import User
from utils.asset_manager import get_asset_path, set_window_icon, center_modal, get_ctk_icon, build_standard_modal_header
from utils.sound_manager import sound_manager
from utils.theme import DarkTheme


# ─────────────────────────────────────────────────────────────────────────────
# TOUCHSCREEN NUMERIC KEYPAD MODAL (CÉDULA / NIT / PLU / CÓDIGO)
# ─────────────────────────────────────────────────────────────────────────────
class TouchKeypadModal(ctk.CTkToplevel):
    """Large, finger-friendly on-screen numeric keypad for touchscreen POS terminals.
    Allows cashiers to enter customer document ID or product PLU code with large buttons.
    """

    def __init__(
        self,
        parent,
        title: str = "Ingresar Cédula / Documento",
        subtitle: str = "Toque los números en pantalla para digitar",
        initial_value: str = "",
        on_confirm_callback=None
    ):
        super().__init__(parent)
        self.on_confirm_callback = on_confirm_callback

        self.title(title)
        self.configure(fg_color=DarkTheme.BG_ROOT)
        self.resizable(False, False)

        self.val_var = tk.StringVar(value=initial_value)

        self._build_ui(title, subtitle)
        center_modal(self, 420, 500, parent)

        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        self.grab_set()

        # Keyboard shortcuts
        self.bind("<Return>", lambda e: self._on_confirm())
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self, title: str, subtitle: str) -> None:
        keypad_ico = get_ctk_icon("id_card_slate", size=(16, 16)) or get_ctk_icon("circle_user_slate", size=(16, 16))
        build_standard_modal_header(self, title, keypad_ico, on_close_cmd=self.destroy, show_close_btn=False)

        content = ctk.CTkFrame(self, fg_color=DarkTheme.BG_ROOT)
        content.pack(fill="both", expand=True, padx=20, pady=(6, 12))

        # Display
        disp_frame = ctk.CTkFrame(content, fg_color=DarkTheme.INPUT_BG, border_color=DarkTheme.PRIMARY_BORDER, border_width=2, corner_radius=10, height=54)
        disp_frame.pack(fill="x", pady=(0, 10))
        disp_frame.pack_propagate(False)

        self.entry = ctk.CTkEntry(
            disp_frame,
            textvariable=self.val_var,
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            justify="center",
            fg_color="transparent",
            border_width=0,
            text_color=DarkTheme.INPUT_TEXT
        )
        self.entry.pack(fill="both", expand=True, padx=8)
        self.entry.focus_set()

        # Touch Keypad Grid (4 rows x 3 columns)
        keypad_frame = ctk.CTkFrame(content, fg_color="transparent")
        keypad_frame.pack(fill="both", expand=True, pady=(0, 10))

        for c in range(3):
            keypad_frame.columnconfigure(c, weight=1)
        for r in range(4):
            keypad_frame.rowconfigure(r, weight=1)

        keys = [
            ("7", 0, 0), ("8", 0, 1), ("9", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("1", 2, 0), ("2", 2, 1), ("3", 2, 2),
            ("C", 3, 0), ("0", 3, 1), ("⌫", 3, 2),
        ]

        for text, r, c in keys:
            is_clear = (text == "C")
            is_back = (text == "⌫")
            btn_bg = DarkTheme.DANGER_BG if is_clear else (DarkTheme.WARNING_BG if is_back else DarkTheme.BG_CARD_ELEVATED)
            hover_bg = DarkTheme.DANGER_HOVER if is_clear else (DarkTheme.WARNING_HOVER if is_back else DarkTheme.BG_CARD_HOVER)
            text_col = DarkTheme.DANGER_TEXT if is_clear else (DarkTheme.WARNING_TEXT if is_back else DarkTheme.TEXT_PRIMARY)
            border_col = DarkTheme.DANGER_BORDER if is_clear else (DarkTheme.WARNING_BORDER if is_back else DarkTheme.BORDER_SUBTLE)

            btn = ctk.CTkButton(
                keypad_frame,
                text=text,
                height=48,
                fg_color=btn_bg,
                hover_color=hover_bg,
                text_color=text_col,
                border_color=border_col,
                border_width=1,
                font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
                corner_radius=8,
                command=lambda t=text: self._on_key(t)
            )
            btn.grid(row=r, column=c, padx=3, pady=3, sticky="nsew")

        # Bottom Action Buttons
        btn_box = ctk.CTkFrame(content, fg_color="transparent")
        btn_box.pack(fill="x", pady=(4, 0))

        cancel_btn = ctk.CTkButton(
            btn_box,
            text="Cancelar",
            height=44,
            width=110,
            fg_color=DarkTheme.BG_ELEVATED,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            hover_color=DarkTheme.BG_CARD_HOVER,
            text_color=DarkTheme.TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            command=self.destroy
        )
        cancel_btn.pack(side="left", padx=(0, 6))

        confirm_btn = ctk.CTkButton(
            btn_box,
            text="ACEPTAR (Enter)",
            height=44,
            fg_color=DarkTheme.ACCENT_GOLD,
            hover_color=DarkTheme.ACCENT_GOLD_HOVER,
            text_color="#0A0A0A",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=8,
            command=self._on_confirm
        )
        confirm_btn.pack(side="left", fill="x", expand=True)

    def _on_key(self, key: str) -> None:
        curr = self.val_var.get()
        if key == "C":
            self.val_var.set("")
        elif key == "⌫":
            self.val_var.set(curr[:-1])
        else:
            self.val_var.set(curr + key)
        self.entry.icursor("end")

    def _on_confirm(self) -> None:
        val = self.val_var.get().strip()
        cb = self.on_confirm_callback
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if cb:
            cb(val)


# ─────────────────────────────────────────────────────────────────────────────
# TOUCHSCREEN PRODUCT DISCOUNT MODAL (PRODUCTO POR PRODUCTO)
# ─────────────────────────────────────────────────────────────────────────────
class ProductDiscountModal(ctk.CTkToplevel):
    """Touchscreen modal for applying line-item product discounts (0% to 100%)."""

    def __init__(
        self,
        parent,
        product_name: str,
        original_price: float,
        current_discount_pct: float = 0.0,
        on_confirm_callback=None
    ):
        super().__init__(parent)
        self.on_confirm_callback = on_confirm_callback
        self.original_price = float(original_price)
        self.current_pct = max(0.0, min(100.0, float(current_discount_pct)))

        self.title("Descuento del Producto")
        self.configure(fg_color=DarkTheme.BG_ROOT)
        self.resizable(False, False)

        self._has_error = False
        self.pct_var = tk.StringVar(value=str(int(self.current_pct)) if self.current_pct > 0 else "0")

        self._build_ui(product_name)
        center_modal(self, 440, 530, parent)

        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        self.grab_set()

        self.bind("<Return>", lambda e: self._on_confirm())
        self.bind("<KP_Enter>", lambda e: self._on_confirm())
        self.bind("<Escape>", lambda e: self.destroy())

        def _on_modal_tab(event, reverse=False):
            tab_widgets = [self.entry, self.cancel_btn, self.apply_btn]
            curr = event.widget
            match_idx = None
            for idx, w in enumerate(tab_widgets):
                if w == curr or getattr(w, "_entry", None) == curr or getattr(w, "_canvas", None) == curr:
                    match_idx = idx
                    break
            if match_idx is not None:
                next_idx = (match_idx - 1) if reverse else (match_idx + 1)
                if next_idx >= len(tab_widgets):
                    next_idx = 0
                elif next_idx < 0:
                    next_idx = len(tab_widgets) - 1
                tab_widgets[next_idx].focus_set()
                return "break"
            return None

        self.bind("<Tab>", lambda e: _on_modal_tab(e, False))
        self.bind("<Shift-Tab>", lambda e: _on_modal_tab(e, True))

        self.after(100, self._focus_entry_initial)

    def _focus_entry_initial(self) -> None:
        try:
            if hasattr(self, "entry") and self.entry.winfo_exists():
                self.entry.focus_set()
                self.entry.select_range(0, 'end')
        except Exception:
            pass

    def _on_entry_focus(self, focused: bool) -> None:
        if getattr(self, "_has_error", False):
            self.entry_frame.configure(border_color="#EF4444")
        else:
            self.entry_frame.configure(border_color="#60A5FA" if focused else "#2563EB")

    def _build_ui(self, product_name: str) -> None:
        # 1. Standard Executive Topbar with XL Burguer & HunzaIA Logos (Without X close button, white icon & text)
        disc_icon = get_ctk_icon("percent_white", size=(16, 16)) or get_ctk_icon("percent-solid-full", size=(16, 16))
        build_standard_modal_header(
            self,
            "Descuento del Producto",
            disc_icon,
            on_close_cmd=self.destroy,
            show_close_btn=False,
            text_color="#FFFFFF"
        )

        content = ctk.CTkFrame(self, fg_color=DarkTheme.BG_ROOT)
        content.pack(fill="both", expand=True, padx=20, pady=(6, 12))

        # Active product banner
        prod_box = ctk.CTkFrame(content, fg_color="#141A28", border_color="#222D42", border_width=1, corner_radius=8)
        prod_box.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            prod_box,
            text=product_name[:42] + ("..." if len(product_name) > 42 else ""),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#F8FAFC",
            anchor="w"
        ).pack(fill="x", padx=12, pady=8)

        # Price summary card
        summary_card = ctk.CTkFrame(content, fg_color="#111624", border_color="#1E283D", border_width=1, corner_radius=8)
        summary_card.pack(fill="x", pady=(0, 10))

        orig_row = ctk.CTkFrame(summary_card, fg_color="transparent")
        orig_row.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(orig_row, text="Precio base:", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8").pack(side="left")
        ctk.CTkLabel(orig_row, text=format_currency(self.original_price), font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#E2E8F0").pack(side="right")

        disc_row = ctk.CTkFrame(summary_card, fg_color="transparent")
        disc_row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(disc_row, text="Descuento aplicado:", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8").pack(side="left")
        self.saving_lbl = ctk.CTkLabel(disc_row, text="-$0", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#10B981")
        self.saving_lbl.pack(side="right")

        final_row = ctk.CTkFrame(summary_card, fg_color="transparent")
        final_row.pack(fill="x", padx=12, pady=(2, 8))
        ctk.CTkLabel(final_row, text="Total con descuento:", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color="#F8FAFC").pack(side="left")
        self.final_price_lbl = ctk.CTkLabel(final_row, text=format_currency(self.original_price), font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"), text_color="#38BDF8")
        self.final_price_lbl.pack(side="right")

        # Quick preset buttons: [0%] [10%] [20%] [50%]
        ctk.CTkLabel(content, text="Seleccione porcentaje rápido:", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#94A3B8").pack(anchor="w", padx=2, pady=(4, 4))
        presets_frame = ctk.CTkFrame(content, fg_color="transparent")
        presets_frame.pack(fill="x", pady=(0, 10))

        presets = [0, 10, 20, 50]
        self.preset_btns = {}
        for p in presets:
            lbl = "0%" if p == 0 else f"{p}%"
            btn = ctk.CTkButton(
                presets_frame,
                text=lbl,
                height=34,
                fg_color="#059669" if p == int(self.current_pct) else "#111624",
                border_color="#10B981" if p == int(self.current_pct) else "#222D42",
                border_width=1,
                hover_color="#0E291F" if p == int(self.current_pct) else "#192338",
                text_color="#FFFFFF" if p == int(self.current_pct) else "#CBD5E1",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                corner_radius=6,
                cursor="hand2",
                command=lambda val=p: self._select_preset(val)
            )
            btn.pack(side="left", fill="x", expand=True, padx=2)
            self.preset_btns[p] = btn

        # Custom percentage entry with seamless, smooth container
        ctk.CTkLabel(content, text="O digite porcentaje personalizado (0 - 100%):", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#94A3B8").pack(anchor="w", padx=2, pady=(4, 4))
        self.entry_frame = ctk.CTkFrame(
            content,
            fg_color="#0D1322",
            border_color="#2563EB",
            border_width=1.5,
            corner_radius=8,
            height=46
        )
        self.entry_frame.pack(fill="x", pady=(0, 4))
        self.entry_frame.pack_propagate(False)

        self.entry = ctk.CTkEntry(
            self.entry_frame,
            textvariable=self.pct_var,
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            justify="center",
            fg_color="transparent",
            border_width=0,
            text_color="#FFFFFF"
        )
        self.entry.pack(side="left", fill="both", expand=True, padx=(12, 4), pady=2)
        self.pct_var.trace_add("write", lambda *args: self._on_pct_change())

        pct_sign_lbl = ctk.CTkLabel(
            self.entry_frame,
            text="% ",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#38BDF8"
        )
        pct_sign_lbl.pack(side="right", padx=(0, 14))

        # Focus styling for custom entry container
        self.entry.bind("<FocusIn>", lambda e: self._on_entry_focus(True), add="+")
        self.entry.bind("<FocusOut>", lambda e: self._on_entry_focus(False), add="+")

        # Inline Error notification label for validation
        self.error_lbl = ctk.CTkLabel(
            content,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#EF4444"
        )
        self.error_lbl.pack(fill="x", pady=(2, 6))

        # Footer Actions
        actions_frame = ctk.CTkFrame(content, fg_color="transparent")
        actions_frame.pack(fill="x", pady=(4, 0))

        cancel_icon = get_ctk_icon("ban_red", size=(15, 15)) or get_ctk_icon("xmark_red", size=(15, 15))
        self.cancel_btn = ctk.CTkButton(
            actions_frame,
            image=cancel_icon,
            compound="left",
            text="  Cancelar",
            width=135,
            height=38,
            fg_color="#1C1117",
            border_color="#EF4444",
            border_width=1.5,
            hover_color="#2D151E",
            text_color="#F87171",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self.destroy
        )
        self.cancel_btn.pack(side="left")

        # Square check icon for apply button per user request
        apply_icon = (
            get_ctk_icon("square_check", size=(16, 16))
            or get_ctk_icon("square-check-solid-full", size=(16, 16))
            or get_ctk_icon("check_green", size=(16, 16))
        )
        self.apply_btn = ctk.CTkButton(
            actions_frame,
            image=apply_icon,
            compound="left",
            text="  Aplicar Descuento",
            height=38,
            fg_color="#059669",
            hover_color="#10B981",
            border_color="#34D399",
            border_width=1.2,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self._on_confirm
        )
        self.apply_btn.pack(side="right")

        self._on_pct_change()

    def _select_preset(self, pct: int) -> None:
        self.pct_var.set(str(pct))

    def _on_pct_change(self) -> None:
        val_str = self.pct_var.get().replace(",", ".").strip()
        self._has_error = False

        if not val_str:
            pct = 0.0
            if hasattr(self, "error_lbl"):
                self.error_lbl.configure(text="")
            if hasattr(self, "entry_frame"):
                self.entry_frame.configure(border_color="#2563EB")
            if hasattr(self, "apply_btn"):
                self.apply_btn.configure(state="normal", fg_color="#059669")
        else:
            try:
                raw_pct = float(val_str)
                if raw_pct > 100.0:
                    self._has_error = True
                    if hasattr(self, "error_lbl"):
                        self.error_lbl.configure(text="⚠ Porcentaje no válido: el máximo permitido es 100%")
                    if hasattr(self, "entry_frame"):
                        self.entry_frame.configure(border_color="#EF4444")
                    if hasattr(self, "apply_btn"):
                        self.apply_btn.configure(state="disabled", fg_color="#334155")
                    if hasattr(self, "saving_lbl"):
                        self.saving_lbl.configure(text="Porcentaje no válido", text_color="#EF4444")
                    if hasattr(self, "final_price_lbl"):
                        self.final_price_lbl.configure(text="--", text_color="#94A3B8")
                    if hasattr(self, "preset_btns"):
                        for btn in self.preset_btns.values():
                            btn.configure(fg_color="#111624", border_color="#222D42", text_color="#CBD5E1")
                    return
                elif raw_pct < 0.0:
                    self._has_error = True
                    if hasattr(self, "error_lbl"):
                        self.error_lbl.configure(text="⚠ Porcentaje no válido: no puede ser negativo")
                    if hasattr(self, "entry_frame"):
                        self.entry_frame.configure(border_color="#EF4444")
                    if hasattr(self, "apply_btn"):
                        self.apply_btn.configure(state="disabled", fg_color="#334155")
                    if hasattr(self, "saving_lbl"):
                        self.saving_lbl.configure(text="Porcentaje no válido", text_color="#EF4444")
                    if hasattr(self, "final_price_lbl"):
                        self.final_price_lbl.configure(text="--", text_color="#94A3B8")
                    if hasattr(self, "preset_btns"):
                        for btn in self.preset_btns.values():
                            btn.configure(fg_color="#111624", border_color="#222D42", text_color="#CBD5E1")
                    return
                else:
                    pct = raw_pct
                    if hasattr(self, "error_lbl"):
                        self.error_lbl.configure(text="")
                    if hasattr(self, "entry_frame"):
                        self.entry_frame.configure(border_color="#2563EB")
                    if hasattr(self, "apply_btn"):
                        self.apply_btn.configure(state="normal", fg_color="#059669")
            except ValueError:
                self._has_error = True
                if hasattr(self, "error_lbl"):
                    self.error_lbl.configure(text="⚠ Ingrese un valor numérico válido (0 - 100)")
                if hasattr(self, "entry_frame"):
                    self.entry_frame.configure(border_color="#EF4444")
                if hasattr(self, "apply_btn"):
                    self.apply_btn.configure(state="disabled", fg_color="#334155")
                if hasattr(self, "saving_lbl"):
                    self.saving_lbl.configure(text="Valor inválido", text_color="#EF4444")
                if hasattr(self, "final_price_lbl"):
                    self.final_price_lbl.configure(text="--", text_color="#94A3B8")
                if hasattr(self, "preset_btns"):
                    for btn in self.preset_btns.values():
                        btn.configure(fg_color="#111624", border_color="#222D42", text_color="#CBD5E1")
                return

        disc_amt = round(self.original_price * (pct / 100.0))
        final_price = max(0.0, self.original_price - disc_amt)

        if hasattr(self, "saving_lbl"):
            self.saving_lbl.configure(text=f"-{format_currency(disc_amt)} ({int(pct)}%)", text_color="#10B981")
        if hasattr(self, "final_price_lbl"):
            self.final_price_lbl.configure(text=format_currency(final_price), text_color="#38BDF8")

        if hasattr(self, "preset_btns"):
            for p, btn in self.preset_btns.items():
                if p == int(pct) and (pct == p):
                    btn.configure(fg_color="#059669", border_color="#10B981", text_color="#FFFFFF")
                else:
                    btn.configure(fg_color="#111624", border_color="#222D42", text_color="#CBD5E1")

    def _on_confirm(self) -> None:
        val_str = self.pct_var.get().replace(",", ".").strip()
        try:
            pct = float(val_str) if val_str else 0.0
        except Exception:
            messagebox.showwarning(
                "Porcentaje No Válido",
                "Por favor ingrese un número válido entre 0% y 100%.",
                parent=self
            )
            return

        if pct < 0.0 or pct > 100.0:
            messagebox.showwarning(
                "Porcentaje No Válido",
                "El porcentaje de descuento no es válido. El valor máximo permitido es 100% y no puede ser negativo.",
                parent=self
            )
            return

        cb = self.on_confirm_callback
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if cb:
            cb(pct)


# ─────────────────────────────────────────────────────────────────────────────
# BACKWARD-COMPATIBLE QUANTITY MODAL (LIGHT THEME)
# ─────────────────────────────────────────────────────────────────────────────
class QuantityModal(ctk.CTkToplevel):
    """Fallback / legacy quantity modal preserved for compatibility."""

    def __init__(
        self,
        parent,
        product: Product,
        scale_driver=None,
        on_confirm_callback=None,
        on_close_callback=None
    ):
        super().__init__(parent)
        self.product = product
        self.scale_driver = None
        self.on_confirm_callback = on_confirm_callback
        self.on_close_callback = on_close_callback

        self.current_unit = "und" if product.sale_type == "UNIDAD" else "und"
        self.quantity_var = tk.StringVar(value="1")
        self.subtotal_var = tk.StringVar(value="COP $ 0")

        self._build_ui()
        self._update_calculations()
        center_modal(self, 480, 510, parent)

        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        self.grab_set()

        self.bind("<Return>", lambda e: self._on_confirm())
        self.bind("<Escape>", lambda e: self._on_close())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._focus_entry)

    def _focus_entry(self) -> None:
        if self.winfo_exists() and hasattr(self, "qty_entry"):
            try:
                self.qty_entry.focus_set()
                self.qty_entry.select_range(0, 'end')
            except Exception:
                pass

    def _build_ui(self) -> None:
        cart_ico = get_ctk_icon("cart_plus_gold", size=(16, 16)) or get_ctk_icon("cart_plus_white", size=(16, 16))
        build_standard_modal_header(self, "Modificar Cantidad", cart_ico, on_close_cmd=self._on_close, show_close_btn=False)

        content = ctk.CTkFrame(self, fg_color="#121418")
        content.pack(fill="both", expand=True, padx=16, pady=(4, 10))

        # Product Header Info Strip
        prod_strip = ctk.CTkFrame(content, fg_color="#181A22", border_color="#252836", border_width=1, corner_radius=8)
        prod_strip.pack(fill="x", pady=(0, 8), ipady=3)
        ctk.CTkLabel(
            prod_strip,
            text=self.product.name,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#F8FAFC"
        ).pack(pady=(4, 1))
        ctk.CTkLabel(
            prod_strip,
            text=f"Precio Base: {self.product.formatted_price_base}  •  Stock: {self.product.formatted_stock}",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#94A3B8"
        ).pack(pady=(0, 4))

        if self.product.sale_type == "PESO":
            unit_frame = ctk.CTkFrame(content, fg_color="#1A1D24", corner_radius=8)
            unit_frame.pack(fill="x", pady=(0, 8), padx=4)

            ctk.CTkLabel(
                unit_frame,
                text="Unidad de Medida:",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#94A3B8"
            ).pack(side="left", padx=12, pady=6)

            self.unit_seg = ctk.CTkSegmentedButton(
                unit_frame,
                values=["kg", "lb", "g"],
                command=self._on_unit_change,
                selected_color=DarkTheme.PRIMARY,
                selected_hover_color=DarkTheme.PRIMARY_HOVER,
                unselected_color=DarkTheme.BG_ELEVATED,
                unselected_hover_color=DarkTheme.BG_CARD_HOVER,
                text_color=DarkTheme.TEXT_PRIMARY,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
            )
            self.unit_seg.set(self.current_unit)
            self.unit_seg.pack(side="right", padx=10, pady=6)

        disp_card = ctk.CTkFrame(content, fg_color="#1A1D24", border_color="#2A2F3D", border_width=1, corner_radius=8)
        disp_card.pack(fill="x", pady=(0, 8), ipady=4)

        qty_row = ctk.CTkFrame(disp_card, fg_color="transparent")
        qty_row.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(
            qty_row,
            text="Cantidad / Peso:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#94A3B8"
        ).pack(side="left")

        self.qty_entry = ctk.CTkEntry(
            qty_row,
            textvariable=self.quantity_var,
            width=140,
            height=38,
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            justify="right",
            fg_color="#121418",
            border_color="#2E3544",
            border_width=1,
            text_color="#F8FAFC"
        )
        self.qty_entry.pack(side="right")
        self.qty_entry.bind("<KeyRelease>", lambda e: self._update_calculations())

        sub_row = ctk.CTkFrame(disp_card, fg_color="transparent")
        sub_row.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(
            sub_row,
            text="Subtotal Item:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#94A3B8"
        ).pack(side="left")

        ctk.CTkLabel(
            sub_row,
            textvariable=self.subtotal_var,
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#10B981"
        ).pack(side="right")

        btn_row = ctk.CTkFrame(content, fg_color="transparent")
        btn_row.pack(fill="x", pady=6)

        self.confirm_btn = ctk.CTkButton(
            btn_row,
            text="➕  AGREGAR (Enter)",
            height=42,
            fg_color=DarkTheme.SUCCESS,
            hover_color=DarkTheme.SUCCESS_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=8,
            command=self._on_confirm
        )
        self.confirm_btn.pack(fill="x", expand=True)

        def _on_qty_tab(event, reverse=False):
            tab_items = [self.qty_entry, self.confirm_btn]
            curr = event.widget
            match_idx = None
            for idx, w in enumerate(tab_items):
                if w == curr or getattr(w, "_entry", None) == curr or getattr(w, "_canvas", None) == curr:
                    match_idx = idx
                    break
            if match_idx is not None:
                next_idx = (match_idx - 1) if reverse else (match_idx + 1)
                if next_idx >= len(tab_items):
                    next_idx = 0
                elif next_idx < 0:
                    next_idx = len(tab_items) - 1
                tab_items[next_idx].focus_set()
                return "break"
            return None

        self.bind("<Tab>", lambda e: _on_qty_tab(e, False))
        self.bind("<Shift-Tab>", lambda e: _on_qty_tab(e, True))

    def _on_unit_change(self, val: str) -> None:
        self.current_unit = val
        self._update_calculations()

    def _update_calculations(self) -> None:
        try:
            qty = float(self.quantity_var.get().replace(",", ".").strip() or "0")
            subtotal = calculate_item_price(self.product.price_base, qty, self.current_unit, self.product.sale_type)
            self.subtotal_var.set(format_currency(subtotal))
        except Exception:
            self.subtotal_var.set("COP $ 0")

    def _on_confirm(self) -> None:
        try:
            qty = float(self.quantity_var.get().replace(",", ".").strip())
            if qty <= 0:
                raise ValueError("La cantidad debe ser mayor a 0.")
            tot = calculate_item_price(self.product.price_base, qty, self.current_unit, self.product.sale_type)
            item = CartItem(
                product_id=self.product.id,
                product_name=self.product.name,
                category_id=self.product.category_id,
                category_name=self.product.category_name,
                sale_type=self.product.sale_type,
                quantity=qty,
                unit_selected=self.current_unit,
                price_base=self.product.price_base,
                total_price=tot
            )
            callback = self.on_confirm_callback
            self._on_close()
            if callback:
                callback(item)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _on_close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if self.on_close_callback:
            self.on_close_callback()


# ─────────────────────────────────────────────────────────────────────────────
# REDESIGNED CHECKOUT MODAL (MULTI-PAYMENT & EMERALD CHANGE)
# ─────────────────────────────────────────────────────────────────────────────
class CircleButton(ctk.CTkButton):
    """Circular denomination button with zero-minsize grid padding to prevent text clipping."""
    def _create_grid(self):
        super()._create_grid()
        self.grid_columnconfigure(0, minsize=0)
        self.grid_columnconfigure(4, minsize=0)
        self.grid_rowconfigure(0, minsize=0)
        self.grid_rowconfigure(4, minsize=0)


class CompanyQuickQuotasModal(ctk.CTkToplevel):
    """Compact modal in POS showing an enterprise's agreed products and remaining quotas."""
    def __init__(self, parent, company: Customer):
        super().__init__(parent)
        self.company = company
        self.title("Convenio y Cupos Fiados")
        self.resizable(False, False)
        self.configure(fg_color="#15171F")

        self._build_ui(parent)
        center_modal(self, 590, 480, parent)
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self, parent) -> None:
        icon_corp = get_ctk_icon("building_user_gold", size=(16, 16)) or get_ctk_icon("tag_gold", size=(16, 16))
        build_standard_modal_header(self, "Convenio de Fiados", icon_corp, on_close_cmd=self.destroy, show_close_btn=False)

        # Body
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(4, 12))

        # Company info bar
        info_bar = ctk.CTkFrame(body, fg_color="#18140B", border_color="#D97706", border_width=1, corner_radius=8)
        info_bar.pack(fill="x", pady=(0, 10), ipady=4)

        c_contact = self.company.last_name or "Sin contacto"
        c_phone = self.company.phone or "Sin teléfono"
        ctk.CTkLabel(
            info_bar,
            text=f"NIT: {self.company.document_id}   •   Contacto: {c_contact}   •   Tel: {c_phone}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#FDE68A"
        ).pack(padx=12, pady=4)

        # Quotas list
        with get_db_connection() as conn:
            quotas = CustomerModel.get_company_quotas(conn, self.company.id)
            summary = CustomerModel.get_company_fiados_summary(conn, self.company.id)

        # Header of table
        hdr = ctk.CTkFrame(body, fg_color="#1E293B", corner_radius=6, height=32)
        hdr.pack(fill="x", pady=(0, 4))
        hdr.pack_propagate(False)
        hdr.grid_columnconfigure(0, weight=1)
        hdr.grid_columnconfigure(1, weight=0, minsize=105)
        hdr.grid_columnconfigure(2, weight=0, minsize=105)
        hdr.grid_columnconfigure(3, weight=0, minsize=125)

        ctk.CTkLabel(hdr, text="Producto / Corte", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="w").grid(row=0, column=0, sticky="ew", padx=(12, 4))
        ctk.CTkLabel(hdr, text="Cupo Pactado", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="center").grid(row=0, column=1, sticky="ew", padx=4)
        ctk.CTkLabel(hdr, text="Entregado (Fiado)", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="center").grid(row=0, column=2, sticky="ew", padx=4)
        ctk.CTkLabel(hdr, text="LE QUEDA", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#FBBF24", anchor="center").grid(row=0, column=3, sticky="ew", padx=(4, 12))

        scroll = ctk.CTkScrollableFrame(body, fg_color="transparent", height=180)
        scroll.pack(fill="both", expand=True, pady=(0, 10))

        if not quotas:
            empty_box = ctk.CTkFrame(scroll, fg_color="transparent")
            empty_box.pack(pady=30)
            ctk.CTkLabel(
                empty_box,
                text="No hay productos registrados en el convenio de esta empresa todavía.\nPuede agregarlos en el módulo de Usuarios / Empresas.",
                font=ctk.CTkFont(family="Segoe UI", size=11, slant="italic"),
                text_color=DarkTheme.TEXT_MUTED,
                justify="center"
            ).pack()
        else:
            for idx, q in enumerate(quotas):
                r_bg = "#111624" if idx % 2 == 0 else "#0D1322"
                row = ctk.CTkFrame(scroll, fg_color=r_bg, corner_radius=6, height=36)
                row.pack(fill="x", pady=2)
                row.pack_propagate(False)
                row.grid_columnconfigure(0, weight=1)
                row.grid_columnconfigure(1, weight=0, minsize=105)
                row.grid_columnconfigure(2, weight=0, minsize=105)
                row.grid_columnconfigure(3, weight=0, minsize=125)

                prod_ico = get_ctk_icon("cube_white", size=(14, 14)) or get_ctk_icon("box_open_white", size=(14, 14))
                ctk.CTkLabel(row, image=prod_ico, compound="left", text=f"  {q['product_name']}", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#F8FAFC", anchor="w").grid(row=0, column=0, sticky="ew", padx=(12, 4))
                ctk.CTkLabel(row, text=f"{q['quota_quantity']:.2f} {q['unit']}", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8", anchor="center").grid(row=0, column=1, sticky="ew", padx=4)
                ctk.CTkLabel(row, text=f"{q['consumed_quantity']:.2f} {q['unit']}", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#F87171", anchor="center").grid(row=0, column=2, sticky="ew", padx=4)

                rem = q['remaining_quantity']
                rem_color = "#34D399" if rem > 0 else "#EF4444"
                rem_pill = ctk.CTkFrame(row, fg_color="#062518" if rem > 0 else "#2B0F13", corner_radius=6, height=24)
                rem_pill.grid(row=0, column=3, sticky="", padx=(4, 12))
                ctk.CTkLabel(rem_pill, text=f"{rem:.2f} {q['unit']}", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=rem_color).pack(padx=8, pady=2)

        # Footer summary
        tot_fiado = summary.get("total_fiado_amount", 0.0)
        footer = ctk.CTkFrame(body, fg_color="#181A22", corner_radius=8, height=44)
        footer.pack(fill="x")
        footer.pack_propagate(False)

        ctk.CTkLabel(
            footer,
            text=f"Total acumulado en fiados: COP ${tot_fiado:,.0f}",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FBBF24"
        ).pack(side="left", padx=14)

        ctk.CTkButton(
            footer,
            text="Entendido",
            width=90,
            height=28,
            fg_color="#1D4ED8",
            hover_color="#2563EB",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            command=self.destroy
        ).pack(side="right", padx=10)


class CheckoutModal(ctk.CTkToplevel):
    """Checkout modal with Multi-Payment selector (Efectivo, Transferencia, Tarjeta, Fiado),
    Full-width branded Top Bar with subtle divider,
    Colombian circular denomination shortcuts (circles: 58x58, corner_radius=29),
    prominent totalizer card, emerald green change display, and complete section-based
    Tab/Keyboard navigation.
    """

    def __init__(
        self,
        parent,
        total_amount: float,
        on_complete_sale_callback,
        customer: Optional[Customer] = None
    ):
        super().__init__(parent)
        self.total_amount = total_amount
        self.on_complete_sale_callback = on_complete_sale_callback
        self.customer = customer

        self.title("Cobro y Facturación")
        self.configure(fg_color="#0D0E12")
        self.resizable(False, False)

        self.payment_method = "EFECTIVO"  # EFECTIVO | TRANSFERENCIA | TARJETA | FIADO
        self.transfer_platform: str = "NEQUI"
        self.transfer_platform_var = tk.StringVar(value="NEQUI")
        self.platform_cards: Dict[str, ctk.CTkButton] = {}
        self.platform_radios: Dict[str, ctk.CTkRadioButton] = {}
        self.cash_var = tk.StringVar(value="")
        self.cash_display_var = tk.StringVar(value="$ 0")
        self.change_var = tk.StringVar(value="$ 0")
        self.cash_history: List[str] = []
        self._last_btn_val: Optional[str] = None
        self._syncing_cash: bool = False
        self._confirm_ready: bool = False

        # ─── NAVIGATION STATE (Section 1: METHODS, Section 2: CONTENT) ───
        self.nav_section: str = "METHODS"  # "METHODS" | "CASH" | "TRANSFER" | "CARD" | "FIADO"
        self.method_focus_idx: int = 0
        self.cash_focus_idx: int = 0
        self.transfer_focus_idx: int = 0

        self.method_buttons: List[ctk.CTkButton] = []
        self.cash_nav_items: List[ctk.CTkButton] = []
        self.transfer_nav_items: List[ctk.CTkButton] = []
        self.denom_buttons_map: Dict[int, CircleButton] = {}

        # Two-way sync between raw cash_var ("50000") and formatted cash_display_var ("$ 50.000")
        self.cash_var.trace_add("write", self._on_cash_var_changed)
        self.cash_display_var.trace_add("write", self._on_display_var_changed)

        self._build_ui(parent)
        self._setup_navigation_items()
        self._bind_keyboard_events()
        self._set_payment_method("EFECTIVO", enter_section=False)
        self._update_change()

        # Always center modal dead in the center of the screen
        center_modal(self, 510, 695, parent)

        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        self.grab_set()

        # Start with active focus highlight on first payment method (Efectivo)
        self.after(50, self._apply_focus_highlight)

    def _on_cash_var_changed(self, *args) -> None:
        if self._syncing_cash:
            return
        self._syncing_cash = True
        try:
            raw = "".join(c for c in self.cash_var.get() if c.isdigit())
            if raw:
                formatted = f"{int(raw):,.0f}".replace(",", ".")
                self.cash_display_var.set(f"$ {formatted}")
            else:
                self.cash_display_var.set("$ 0")
        finally:
            self._syncing_cash = False

    def _on_display_var_changed(self, *args) -> None:
        if self._syncing_cash:
            return
        self._syncing_cash = True
        try:
            raw = "".join(c for c in self.cash_display_var.get() if c.isdigit())
            self.cash_var.set(raw)
        finally:
            self._syncing_cash = False
        self._update_change()

    def _build_ui(self, parent) -> None:
        # ─── 1. TOP BAR & TITLE (Clean logos-only topbar + centered title) ───
        checkout_ico = get_ctk_icon("coins_white", size=(16, 16)) or get_ctk_icon("coins_gold", size=(16, 16))
        build_standard_modal_header(
            self,
            title_text="Finalización de Venta y Cobro",
            title_icon=checkout_ico,
            on_close_cmd=self.destroy,
            show_close_btn=False,
            text_color="#FFFFFF"
        )

        # ─── MAIN CONTENT CONTAINER (Below Top Bar & Title) ───────────────────
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=22, pady=(2, 16))

        # Cashier & Customer Pills stacked below header banner
        cashier_name = "Cajero XL Burguer"
        if hasattr(parent, "current_user") and parent.current_user:
            try:
                from database.connection import get_db_connection
                from models.user import UserModel
                with get_db_connection() as conn:
                    fresh_u = UserModel.get_by_id(conn, parent.current_user.id)
                    if fresh_u:
                        parent.current_user = fresh_u
            except Exception:
                pass
            cashier_name = parent.current_user.full_name or parent.current_user.username or "Cajero XL Burguer"

        user_icon = get_ctk_icon("circle_user_slate", size=(13, 13))

        pills_row = ctk.CTkFrame(self.main_container, fg_color="transparent")
        pills_row.pack(fill="x", pady=(0, 6))

        pills_center = ctk.CTkFrame(pills_row, fg_color="transparent")
        pills_center.pack(anchor="center")

        # Cajero pill
        cashier_pill = ctk.CTkFrame(
            pills_center,
            fg_color="#1E2C33",
            border_color="#365463",
            border_width=1.5,
            corner_radius=12,
            height=24
        )
        cashier_pill.pack(side="left", padx=4)
        cashier_pill.pack_propagate(False)

        ctk.CTkLabel(
            cashier_pill,
            text=f" Cajero: {cashier_name}",
            image=user_icon,
            compound="left",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color="#A2BDC9",
            fg_color="transparent",
            height=20
        ).pack(side="left", padx=8)

        # Cliente pill
        cust_name = self.customer.full_name if self.customer else "Anónimo"
        customer_pill = ctk.CTkFrame(
            pills_center,
            fg_color="#332D24",
            border_color="#594E3C",
            border_width=1.5,
            corner_radius=12,
            height=24
        )
        customer_pill.pack(side="left", padx=4)
        customer_pill.pack_propagate(False)

        ctk.CTkLabel(
            customer_pill,
            text=f" Cliente: {cust_name}",
            image=user_icon,
            compound="left",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color="#D4C7B5",
            fg_color="transparent",
            height=20
        ).pack(side="left", padx=8)

        # ─── 2. TOP SPLIT (Total Box on Left, Payment Methods on Right) ──────
        top_split = ctk.CTkFrame(self.main_container, fg_color="transparent")
        top_split.pack(fill="x", pady=(0, 8))
        top_split.grid_columnconfigure(0, weight=1)
        top_split.grid_columnconfigure(1, weight=0)

        # Left: Total a Pagar Card (Modern Segoe UI typography)
        total_card = ctk.CTkFrame(
            top_split,
            fg_color="#060B18",
            border_color="#0284C7",
            border_width=1.5,
            corner_radius=10
        )
        total_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        ctk.CTkLabel(
            total_card,
            text="TOTAL A PAGAR",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color="#38BDF8"
        ).pack(anchor="center", pady=(10, 2))

        formatted_total = f"{self.total_amount:,.0f}".replace(",", ".")
        ctk.CTkLabel(
            total_card,
            text=f"COP $ {formatted_total}",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color="#FFFFFF"
        ).pack(anchor="center", pady=(0, 10))

        # Right: Metodo de pago Stacked
        method_frame = ctk.CTkFrame(top_split, fg_color="transparent")
        method_frame.grid(row=0, column=1, sticky="nsew")

        ctk.CTkLabel(
            method_frame,
            text="Metodo de pago",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#94A3B8"
        ).pack(anchor="w", pady=(0, 3))

        icon_money = get_ctk_icon("money_slate", size=(16, 16))
        icon_trans = get_ctk_icon("mobile_slate", size=(16, 16))
        icon_card = get_ctk_icon("credit_card_slate", size=(16, 16))

        self.btn_cash = ctk.CTkButton(
            method_frame,
            text="Efectivo",
            image=icon_money,
            compound="left",
            width=126,
            height=26,
            corner_radius=6,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=lambda: self._on_method_button_clicked("EFECTIVO")
        )
        self.btn_cash._payment_method = "EFECTIVO"
        self.btn_cash.pack(pady=2)

        self.btn_transfer = ctk.CTkButton(
            method_frame,
            text="Transferencia",
            image=icon_trans,
            compound="left",
            width=126,
            height=26,
            corner_radius=6,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=lambda: self._on_method_button_clicked("TRANSFERENCIA")
        )
        self.btn_transfer._payment_method = "TRANSFERENCIA"
        self.btn_transfer.pack(pady=2)

        self.btn_card = ctk.CTkButton(
            method_frame,
            text="Tarjeta",
            image=icon_card,
            compound="left",
            width=126,
            height=26,
            corner_radius=6,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=lambda: self._on_method_button_clicked("TARJETA")
        )
        self.btn_card._payment_method = "TARJETA"
        self.btn_card.pack(pady=2)

        icon_fiado_slate = get_ctk_icon("building_user_slate", size=(15, 15)) or get_ctk_icon("building_user_gold", size=(15, 15))
        self.btn_fiado = ctk.CTkButton(
            method_frame,
            text="Fiado (Empresa)",
            image=icon_fiado_slate,
            compound="left",
            width=126,
            height=26,
            corner_radius=6,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=lambda: self._on_method_button_clicked("FIADO")
        )
        self.btn_fiado._payment_method = "FIADO"

        # El botón de Fiado aparece ÚNICAMENTE cuando el cliente es una Empresa
        is_company = False
        if self.customer:
            is_company = bool(getattr(self.customer, "is_company", False) or getattr(self.customer, "is_corporate", False))
        if is_company:
            self.btn_fiado.pack(pady=2)

        # ─── 3. DASHED SEPARATOR LINE ─────────────────────────────────────────
        dash_canvas = tk.Canvas(self.main_container, height=6, bg="#0D0E12", highlightthickness=0, bd=0)
        dash_canvas.pack(fill="x", pady=(6, 8))

        def _draw_dash(event=None):
            dash_canvas.delete("all")
            w = dash_canvas.winfo_width()
            if w > 10:
                dash_canvas.create_line(4, 3, w - 4, 3, dash=(6, 6), fill="#252D3F", width=1.5)

        dash_canvas.bind("<Configure>", _draw_dash)

        # ─── 4. CASH SECTION (Efectivo Recibido + Circles + Pills) ───────────
        self.cash_container = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.cash_container.pack(fill="x")

        ctk.CTkLabel(
            self.cash_container,
            text="EFECTIVO RECIBIDO",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color="#94A3B8"
        ).pack(anchor="w", pady=(0, 4))

        # Centered Cash Box (Segoe UI bold, legible with zero cut-off)
        self.cash_box = ctk.CTkFrame(
            self.cash_container,
            fg_color="#060B18",
            border_color="#242B3D",
            border_width=1.5,
            corner_radius=8,
            height=46
        )
        self.cash_box.pack(fill="x", pady=(0, 10))
        self.cash_box.pack_propagate(False)

        self.cash_entry = ctk.CTkEntry(
            self.cash_box,
            textvariable=self.cash_display_var,
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            justify="center",
            fg_color="transparent",
            border_width=0,
            text_color="#FFFFFF"
        )
        self.cash_entry.pack(fill="both", expand=True, padx=8)

        # Denomination circular buttons (6 cols x 2 rows, circles 58x58, zero text clipping)
        grid_frame = ctk.CTkFrame(self.cash_container, fg_color="transparent")
        grid_frame.pack(fill="x", pady=(0, 4))
        for c in range(6):
            grid_frame.grid_columnconfigure(c, weight=1)

        # Fila 0: 5.000 | 10.000 | 50.000 | 1.000 | 100 | 50
        row0_items = [
            (0, "5.000", 5000),
            (1, "10.000", 10000),
            (2, "50.000", 50000),
            (3, "1.000", 1000),
            (4, "100", 100),
            (5, "50", 50),
        ]
        for col, text, val in row0_items:
            f_size = 9 if len(text) >= 7 else 10
            b = CircleButton(
                grid_frame,
                text=text,
                width=58,
                height=58,
                corner_radius=29,
                font=ctk.CTkFont(family="Segoe UI", size=f_size, weight="bold"),
                fg_color="#111624",
                hover_color="#1E2638",
                text_color="#CBD5E1",
                border_color="#232D42",
                border_width=1.2,
                command=lambda v=val: self._on_denom_click(v)
            )
            b._denom_val = val
            b.grid(row=0, column=col, padx=3, pady=3)
            self.denom_buttons_map[val] = b

        # Fila 1: 2.000 | 20.000 | 100.000 | 500 | 200 | [⌫]
        row1_items = [
            (0, "2.000", 2000),
            (1, "20.000", 20000),
            (2, "100.000", 100000),
            (3, "500", 500),
            (4, "200", 200),
        ]
        for col, text, val in row1_items:
            f_size = 9 if len(text) >= 7 else 10
            b = CircleButton(
                grid_frame,
                text=text,
                width=58,
                height=58,
                corner_radius=29,
                font=ctk.CTkFont(family="Segoe UI", size=f_size, weight="bold"),
                fg_color="#111624",
                hover_color="#1E2638",
                text_color="#CBD5E1",
                border_color="#232D42",
                border_width=1.2,
                command=lambda v=val: self._on_denom_click(v)
            )
            b._denom_val = val
            b.grid(row=1, column=col, padx=3, pady=3)
            self.denom_buttons_map[val] = b

        # Undo button (Col 5, Row 1) - Prominent red backspace icon
        undo_icon = get_ctk_icon("delete_left_red", size=(30, 24))
        self.undo_btn = CircleButton(
            grid_frame,
            text="" if undo_icon else "⌫",
            image=undo_icon,
            width=58,
            height=58,
            corner_radius=29,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#1A0D11",
            hover_color="#2D1117",
            border_color="#EF4444",
            border_width=1.5,
            command=lambda: self._on_denom_click("undo")
        )
        self.undo_btn.grid(row=1, column=5, padx=3, pady=3)

        # Quick action pills: Pago Exacto & Borrar Todo
        actions_frame = ctk.CTkFrame(self.cash_container, fg_color="transparent")
        actions_frame.pack(fill="x", pady=(6, 0))
        actions_frame.grid_columnconfigure(0, weight=1)
        actions_frame.grid_columnconfigure(1, weight=1)

        star_icon = get_ctk_icon("star_gold", size=(15, 15))
        trash_icon = get_ctk_icon("trash_red", size=(15, 15))

        self.exact_btn = ctk.CTkButton(
            actions_frame,
            text="Pago exacto",
            image=star_icon,
            compound="left",
            height=36,
            corner_radius=18,
            fg_color="#140E05",
            hover_color="#241708",
            border_color="#D97706",
            border_width=1.5,
            text_color="#FBBF24",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=lambda: self._on_denom_click("exact")
        )
        self.exact_btn.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.clear_btn = ctk.CTkButton(
            actions_frame,
            text="Borrar todo",
            image=trash_icon,
            compound="left",
            height=36,
            corner_radius=18,
            fg_color="#1A0D11",
            hover_color="#2D1117",
            border_color="#EF4444",
            border_width=1.5,
            text_color="#F87171",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=lambda: self._on_denom_click("clear")
        )
        self.clear_btn.grid(row=0, column=1, padx=(6, 0), sticky="ew")

        # ─── TRANSFER SECTION (Nequi / Daviplata / Bancolombia) ───────────────
        self.transfer_container = ctk.CTkFrame(self.main_container, fg_color="transparent")

        # 3 Platform columns: Nequi, DAVI plata, Bancolombia
        self.transfer_platforms_frame = ctk.CTkFrame(self.transfer_container, fg_color="transparent")
        self.transfer_platforms_frame.pack(fill="x", pady=(4, 6))
        self.transfer_platforms_frame.grid_columnconfigure(0, weight=1)
        self.transfer_platforms_frame.grid_columnconfigure(1, weight=1)
        self.transfer_platforms_frame.grid_columnconfigure(2, weight=1)

        platforms_data = [
            ("NEQUI", "Nequi", "nequi"),
            ("DAVIPLATA", "DAVI plata", "daviplata"),
            ("BANCOLOMBIA", "Bancolombia", "bancolombia"),
        ]

        for col_idx, (key, display_name, icon_name) in enumerate(platforms_data):
            col_frame = ctk.CTkFrame(self.transfer_platforms_frame, fg_color="transparent")
            col_frame.grid(row=0, column=col_idx, padx=6, sticky="n")

            logo_img = get_ctk_icon(icon_name, size=(78, 78))

            card_btn = ctk.CTkButton(
                col_frame,
                text="",
                image=logo_img,
                width=96,
                height=96,
                fg_color="#FFFFFF",
                hover_color="#F8FAFC",
                corner_radius=10,
                border_width=0,
                border_color="#FFFFFF",
                cursor="hand2",
                command=lambda k=key: self._select_transfer_platform(k)
            )
            card_btn._platform_key = key
            card_btn.pack(pady=(0, 8))
            self.platform_cards[key] = card_btn

            radio = ctk.CTkRadioButton(
                col_frame,
                text=display_name,
                variable=self.transfer_platform_var,
                value=key,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color="#FFFFFF",
                fg_color="#0284C7",
                hover_color="#0369A1",
                border_color="#334155",
                border_width_unchecked=2,
                border_width_checked=5,
                radiobutton_width=18,
                radiobutton_height=18,
                cursor="hand2",
                command=lambda k=key: self._select_transfer_platform(k)
            )
            radio._platform_key = key
            radio.pack()
            self.platform_radios[key] = radio

        # Information box
        self.transfer_info_box = ctk.CTkFrame(
            self.transfer_container,
            fg_color="#060B18",
            border_color="#242B3D",
            border_width=1.5,
            corner_radius=8
        )
        self.transfer_info_box.pack(fill="x", pady=(14, 4), ipady=8)

        self.transfer_header_lbl = ctk.CTkLabel(
            self.transfer_info_box,
            text="Transferencia (Nequi / Daviplata / Bancolombia)",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#93C5FD",
            justify="center"
        )
        self.transfer_header_lbl.pack(pady=(6, 4))

        self.transfer_detail_lbl = ctk.CTkLabel(
            self.transfer_info_box,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8",
            justify="center"
        )
        self.transfer_detail_lbl.pack(pady=(0, 6))

        # Container for Card payments (shown when Tarjeta)
        self.card_container = ctk.CTkFrame(
            self.main_container,
            fg_color="#060B18",
            border_color="#242B3D",
            border_width=1.5,
            corner_radius=8
        )
        self.card_info_lbl = ctk.CTkLabel(
            self.card_container,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#CBD5E1",
            justify="center"
        )
        self.card_info_lbl.pack(pady=24, padx=16)

        # Container for Fiado (shown when Fiado Empresa)
        self.fiado_container = ctk.CTkFrame(
            self.main_container,
            fg_color="#18140B",
            border_color="#D97706",
            border_width=1.5,
            corner_radius=8
        )
        self.fiado_title_lbl = ctk.CTkLabel(
            self.fiado_container,
            text="🤝 VENTA A CRÉDITO EMPRESARIAL (FIADO)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#FBBF24"
        )
        self.fiado_title_lbl.pack(pady=(16, 6))

        self.fiado_info_lbl = ctk.CTkLabel(
            self.fiado_container,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#E2E8F0",
            justify="center"
        )
        self.fiado_info_lbl.pack(pady=(0, 16), padx=16)

        # ─── 5. BOTTOM FRAME (Cambio Card + Confirm Button) ──────────────────
        self.bottom_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.bottom_frame.pack(fill="x", side="bottom", pady=(8, 0))

        # Change Card
        self.change_card = ctk.CTkFrame(
            self.bottom_frame,
            fg_color="#06140D",
            border_color="#059669",
            border_width=1.8,
            corner_radius=10
        )
        self.change_card.pack(fill="x", pady=(0, 8), ipady=4)

        ctk.CTkLabel(
            self.change_card,
            text="Cambio",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#34D399"
        ).pack(pady=(4, 0))

        self.change_lbl = ctk.CTkLabel(
            self.change_card,
            textvariable=self.change_var,
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color="#34D399"
        )
        self.change_lbl.pack(pady=(0, 6))

        # Confirm Button
        self.confirm_btn = ctk.CTkButton(
            self.bottom_frame,
            text="Confirmar y emitir ticket",
            height=42,
            corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self._on_confirm_payment
        )
        self.confirm_btn.pack(fill="x")

    def _setup_navigation_items(self) -> None:
        """Construct the ordered lists of items for Section 1 (Methods) and Section 2 (Content)."""
        is_company = False
        if self.customer:
            is_company = bool(getattr(self.customer, "is_company", False) or getattr(self.customer, "is_corporate", False))

        # Method buttons: [Efectivo, Transferencia, Tarjeta (, Fiado)]
        self.method_buttons = [self.btn_cash, self.btn_transfer, self.btn_card]
        if is_company and hasattr(self, "btn_fiado"):
            self.method_buttons.append(self.btn_fiado)

        # Cash navigation items strictly in the user's requested order:
        # 5.000, 10.000, 50.000, 1.000, 100, 50, 2.000, 20.000, 100.000, 500, 200, undo, exact, clear, confirm
        self.cash_nav_items = [
            self.denom_buttons_map[5000],
            self.denom_buttons_map[10000],
            self.denom_buttons_map[50000],
            self.denom_buttons_map[1000],
            self.denom_buttons_map[100],
            self.denom_buttons_map[50],
            self.denom_buttons_map[2000],
            self.denom_buttons_map[20000],
            self.denom_buttons_map[100000],
            self.denom_buttons_map[500],
            self.denom_buttons_map[200],
            self.undo_btn,
            self.exact_btn,
            self.clear_btn,
            self.confirm_btn,
        ]

        # Transfer navigation items: Nequi, Daviplata, Bancolombia, confirm
        self.transfer_nav_items = [
            self.platform_cards["NEQUI"],
            self.platform_cards["DAVIPLATA"],
            self.platform_cards["BANCOLOMBIA"],
            self.confirm_btn,
        ]

    def _bind_keyboard_events(self) -> None:
        """Bind Tab, Shift-Tab, Return, Escape, and digit keys for seamless modal operation."""
        self.bind("<Tab>", self._handle_tab_key)
        self.bind("<Shift-Tab>", self._handle_shift_tab_key)
        self.bind("<ISO_Left_Tab>", self._handle_shift_tab_key)
        self.bind("<Return>", self._handle_return_key)
        self.bind("<KP_Enter>", self._handle_return_key)
        self.bind("<space>", self._handle_space_key)
        self.bind("<Escape>", self._handle_escape_key)
        self.bind("<Key>", self._handle_key_press)

    def _apply_focus_highlight(self) -> None:
        """Apply glowing focus outlines and contrast states based on active section and focus index."""
        target = None
        if self.nav_section == "METHODS":
            if 0 <= self.method_focus_idx < len(self.method_buttons):
                target = self.method_buttons[self.method_focus_idx]
        elif self.nav_section == "CASH":
            if 0 <= self.cash_focus_idx < len(self.cash_nav_items):
                target = self.cash_nav_items[self.cash_focus_idx]
        elif self.nav_section == "TRANSFER":
            if 0 <= self.transfer_focus_idx < len(self.transfer_nav_items):
                target = self.transfer_nav_items[self.transfer_focus_idx]
        elif self.nav_section in ("CARD", "FIADO"):
            target = self.confirm_btn

        # 1. Method buttons highlight
        for idx, btn in enumerate(self.method_buttons):
            method = getattr(btn, "_payment_method", "")
            is_active_method = (self.payment_method == method)
            is_focused = (self.nav_section == "METHODS" and idx == self.method_focus_idx)

            if is_focused:
                btn.configure(border_color="#38BDF8", border_width=2.5)
            elif is_active_method:
                if method == "FIADO":
                    btn.configure(border_color="#F59E0B", border_width=1.5, fg_color="#92400E", text_color="#FDE68A")
                else:
                    btn.configure(border_color="#5A6273", border_width=1.5, fg_color="#3E434D", text_color="#FFFFFF")
            else:
                btn.configure(border_color="#242B3D", border_width=1.0, fg_color="#141722", text_color="#94A3B8")

        # 2. Cash items highlight
        if hasattr(self, "cash_nav_items"):
            for item in self.cash_nav_items:
                if item == self.confirm_btn:
                    continue
                is_focused = (self.nav_section == "CASH" and item == target)
                if item == self.undo_btn:
                    if is_focused:
                        item.configure(border_color="#FCA5A5", border_width=2.5, fg_color="#3F1219")
                    else:
                        item.configure(border_color="#EF4444", border_width=1.5, fg_color="#1A0D11")
                elif item == self.exact_btn:
                    if is_focused:
                        item.configure(border_color="#FCD34D", border_width=2.5, fg_color="#2A1B0A")
                    else:
                        item.configure(border_color="#D97706", border_width=1.5, fg_color="#140E05")
                elif item == self.clear_btn:
                    if is_focused:
                        item.configure(border_color="#FCA5A5", border_width=2.5, fg_color="#3F1219")
                    else:
                        item.configure(border_color="#EF4444", border_width=1.5, fg_color="#1A0D11")
                else:
                    # Circular denomination buttons
                    if is_focused:
                        item.configure(border_color="#38BDF8", border_width=2.5, fg_color="#1E293B", text_color="#FFFFFF")
                    else:
                        item.configure(border_color="#232D42", border_width=1.2, fg_color="#111624", text_color="#CBD5E1")

        # 3. Transfer platform cards highlight
        if hasattr(self, "platform_cards"):
            for k, card in self.platform_cards.items():
                is_selected = (self.transfer_platform == k)
                is_focused = (self.nav_section == "TRANSFER" and card == target)
                if is_focused:
                    card.configure(border_color="#38BDF8", border_width=3.5)
                elif is_selected:
                    card.configure(border_color="#0284C7", border_width=2.5)
                else:
                    card.configure(border_color="#FFFFFF", border_width=0)

        # 4. Confirm button highlight
        if hasattr(self, "confirm_btn"):
            is_focused = (target == self.confirm_btn)
            if is_focused:
                self.confirm_btn.configure(border_color="#34D399", border_width=2.5)
            else:
                ready = getattr(self, "_confirm_ready", True)
                self.confirm_btn.configure(border_color="#4F5D7E" if ready else "#1E2638", border_width=1)

    def _enter_section(self, section: str) -> None:
        """Transition keyboard focus into Section 2 (Content) for the chosen payment method."""
        self.nav_section = section
        if section == "CASH":
            self.cash_focus_idx = 0  # Starts at 5.000
        elif section == "TRANSFER":
            # Set to current transfer platform card or Nequi
            target_key = self.transfer_platform or "NEQUI"
            card = self.platform_cards.get(target_key)
            if card and card in self.transfer_nav_items:
                self.transfer_focus_idx = self.transfer_nav_items.index(card)
            else:
                self.transfer_focus_idx = 0
        elif section in ("CARD", "FIADO"):
            pass  # target is directly confirm_btn
        self._apply_focus_highlight()

    def _on_method_button_clicked(self, method: str) -> None:
        """Handle mouse click on a payment method button."""
        self._set_payment_method(method)
        if method == "EFECTIVO":
            self._enter_section("CASH")
        elif method == "TRANSFERENCIA":
            self._enter_section("TRANSFER")
        elif method == "TARJETA":
            self._enter_section("CARD")
        elif method == "FIADO":
            self._enter_section("FIADO")

    def _handle_tab_key(self, event=None) -> str:
        """Tab key navigation enforcing strict separation between sections."""
        if self.nav_section == "METHODS":
            # Cycle exclusively among payment method buttons until user selects one
            self.method_focus_idx = (self.method_focus_idx + 1) % len(self.method_buttons)
            self._apply_focus_highlight()
            return "break"

        elif self.nav_section == "CASH":
            # Cycle strictly among cash items (5.000 ... confirm_btn -> loops to 5.000)
            self.cash_focus_idx = (self.cash_focus_idx + 1) % len(self.cash_nav_items)
            self._apply_focus_highlight()
            return "break"

        elif self.nav_section == "TRANSFER":
            # Cycle: Nequi -> Daviplata -> Bancolombia -> confirm_btn -> loops to Nequi
            self.transfer_focus_idx = (self.transfer_focus_idx + 1) % len(self.transfer_nav_items)
            self._apply_focus_highlight()
            return "break"

        elif self.nav_section in ("CARD", "FIADO"):
            # Return to payment methods
            self.nav_section = "METHODS"
            target_btn = self.btn_card if self.nav_section == "CARD" else getattr(self, "btn_fiado", self.btn_card)
            if target_btn in self.method_buttons:
                self.method_focus_idx = self.method_buttons.index(target_btn)
            self._apply_focus_highlight()
            return "break"

        return "break"

    def _handle_shift_tab_key(self, event=None) -> str:
        """Shift-Tab moves backwards, returning to Section 1 when at the start of Section 2."""
        if self.nav_section == "METHODS":
            self.method_focus_idx = (self.method_focus_idx - 1) % len(self.method_buttons)
            self._apply_focus_highlight()
            return "break"

        elif self.nav_section == "CASH":
            if self.cash_focus_idx == 0:
                # Shift-Tab from 5.000 returns to Section 1 (Payment Methods)
                self.nav_section = "METHODS"
                self.method_focus_idx = self.method_buttons.index(self.btn_cash)
                self._apply_focus_highlight()
            else:
                self.cash_focus_idx -= 1
                self._apply_focus_highlight()
            return "break"

        elif self.nav_section == "TRANSFER":
            if self.transfer_focus_idx == 0:
                self.nav_section = "METHODS"
                self.method_focus_idx = self.method_buttons.index(self.btn_transfer)
                self._apply_focus_highlight()
            else:
                self.transfer_focus_idx -= 1
                self._apply_focus_highlight()
            return "break"

        elif self.nav_section in ("CARD", "FIADO"):
            self.nav_section = "METHODS"
            target_btn = self.btn_card if self.nav_section == "CARD" else getattr(self, "btn_fiado", self.btn_card)
            if target_btn in self.method_buttons:
                self.method_focus_idx = self.method_buttons.index(target_btn)
            self._apply_focus_highlight()
            return "break"

        return "break"

    def _handle_return_key(self, event=None) -> str:
        """Handle Return/Enter key based on active section."""
        if self.nav_section == "METHODS":
            btn = self.method_buttons[self.method_focus_idx]
            method = getattr(btn, "_payment_method", "EFECTIVO")
            self._set_payment_method(method)
            if method == "EFECTIVO":
                self._enter_section("CASH")
            elif method == "TRANSFERENCIA":
                self._enter_section("TRANSFER")
            elif method == "TARJETA":
                self._enter_section("CARD")
            elif method == "FIADO":
                self._enter_section("FIADO")
            return "break"

        elif self.nav_section == "CASH":
            item = self.cash_nav_items[self.cash_focus_idx]
            if item == self.confirm_btn:
                self._on_confirm_payment()
            elif item == self.undo_btn:
                self._on_denom_click("undo")
            elif item == self.exact_btn:
                self._on_denom_click("exact")
            elif item == self.clear_btn:
                self._on_denom_click("clear")
            else:
                val = getattr(item, "_denom_val", None)
                if val:
                    self._on_denom_click(val)
            return "break"

        elif self.nav_section == "TRANSFER":
            item = self.transfer_nav_items[self.transfer_focus_idx]
            if item == self.confirm_btn:
                self._on_confirm_payment()
            else:
                plat_key = getattr(item, "_platform_key", None)
                if plat_key:
                    self._select_transfer_platform(plat_key)
                    # Automatically advance focus to confirm button
                    self.transfer_focus_idx = self.transfer_nav_items.index(self.confirm_btn)
                    self._apply_focus_highlight()
            return "break"

        elif self.nav_section in ("CARD", "FIADO"):
            self._on_confirm_payment()
            return "break"

        return "break"

    def _handle_space_key(self, event=None) -> str:
        return self._handle_return_key(event)

    def _handle_escape_key(self, event=None) -> str:
        if self.nav_section != "METHODS":
            # Return focus to methods section
            self.nav_section = "METHODS"
            target_btn = self.btn_cash
            if self.payment_method == "TRANSFERENCIA":
                target_btn = self.btn_transfer
            elif self.payment_method == "TARJETA":
                target_btn = self.btn_card
            elif self.payment_method == "FIADO" and hasattr(self, "btn_fiado"):
                target_btn = self.btn_fiado
            if target_btn in self.method_buttons:
                self.method_focus_idx = self.method_buttons.index(target_btn)
            self._apply_focus_highlight()
            return "break"
        else:
            self.destroy()
            return "break"

    def _handle_key_press(self, event) -> Optional[str]:
        """Capture numeric typing (0-9) and BackSpace for direct numpad entry in cash mode."""
        if not event or not event.char:
            if event and event.keysym in ("BackSpace", "Delete") and self.payment_method == "EFECTIVO":
                self._on_undo()
                return "break"
            return None

        if self.payment_method == "EFECTIVO":
            if event.char.isdigit():
                curr = self.cash_var.get().replace(".", "").replace(",", "").strip()
                if curr == "0":
                    curr = ""
                new_str = curr + event.char
                self.cash_var.set(new_str)
                self.cash_history.append(curr)
                self._last_btn_val = new_str
                self._update_change()
                return "break"
            elif event.char in ("\x08",):  # Backspace
                self._on_undo()
                return "break"

        return None

    def _select_transfer_platform(self, plat: str) -> None:
        self.transfer_platform = plat
        self.transfer_platform_var.set(plat)

        plat_display = {
            "NEQUI": "Nequi",
            "DAVIPLATA": "Daviplata",
            "BANCOLOMBIA": "Bancolombia"
        }.get(plat, "Nequi / Daviplata / Bancolombia")

        formatted_total = f"{self.total_amount:,.0f}".replace(",", ".")
        self.transfer_header_lbl.configure(text=f"Transferencia ({plat_display})")
        self.transfer_detail_lbl.configure(
            text=f"Pago registrado por valor exacto: COP $ {formatted_total}.\nListo para confirmar y emitir ticket."
        )
        self._set_confirm_button_state(ready=True)
        try:
            sound_manager.play_click()
        except Exception:
            pass
        self._apply_focus_highlight()

    def _set_confirm_button_state(self, ready: bool) -> None:
        self._confirm_ready = ready
        if ready:
            self.confirm_btn.configure(
                state="normal",
                fg_color="#2A354D",
                hover_color="#384766",
                border_color="#4F5D7E",
                border_width=1,
                text_color="#FFFFFF"
            )
        else:
            self.confirm_btn.configure(
                state="disabled",
                fg_color="#141824",
                border_color="#1E2638",
                border_width=1,
                text_color="#475569"
            )

    def _set_payment_method(self, method: str, enter_section: bool = True) -> None:
        if method == "FIADO":
            if not self.customer:
                sound_manager.play_error()
                messagebox.showwarning(
                    "Empresa Requerida",
                    "Para registrar una venta fiada, primero debe asignar o registrar una empresa o cliente en el módulo de ventas.",
                    parent=self
                )
                return

        self.payment_method = method

        is_cash = (method == "EFECTIVO")
        is_trans = (method == "TRANSFERENCIA")
        is_card = (method == "TARJETA")
        is_fiado = (method == "FIADO")

        # Reset confirm button default styling
        self.confirm_btn.configure(
            text="Confirmar y emitir ticket",
            fg_color="#2A354D",
            hover_color="#384766",
            border_color="#4F5D7E"
        )

        if is_cash:
            self.transfer_container.pack_forget()
            self.card_container.pack_forget()
            if hasattr(self, "fiado_container"):
                self.fiado_container.pack_forget()
            self.cash_container.pack(fill="x")
            self.change_card.pack(fill="x", pady=(0, 8), ipady=4, before=self.confirm_btn)
            self._update_change()
            if enter_section:
                self._enter_section("CASH")
        elif is_trans:
            self.cash_container.pack_forget()
            self.change_card.pack_forget()
            self.card_container.pack_forget()
            if hasattr(self, "fiado_container"):
                self.fiado_container.pack_forget()
            self.transfer_container.pack(fill="x", pady=(8, 4))
            formatted_total = f"{self.total_amount:,.0f}".replace(",", ".")
            plat_display = {
                "NEQUI": "Nequi",
                "DAVIPLATA": "Daviplata",
                "BANCOLOMBIA": "Bancolombia"
            }.get(self.transfer_platform, "Nequi / Daviplata / Bancolombia")
            self.transfer_header_lbl.configure(text=f"Transferencia ({plat_display})")
            self.transfer_detail_lbl.configure(
                text=f"Pago registrado por valor exacto: COP $ {formatted_total}.\nListo para confirmar y emitir ticket."
            )
            self._set_confirm_button_state(ready=True)
            if enter_section:
                self._enter_section("TRANSFER")
        elif is_card:
            self.cash_container.pack_forget()
            self.change_card.pack_forget()
            self.transfer_container.pack_forget()
            if hasattr(self, "fiado_container"):
                self.fiado_container.pack_forget()
            self.card_container.pack(fill="x", pady=(18, 12))
            formatted_total = f"{self.total_amount:,.0f}".replace(",", ".")
            self.card_info_lbl.configure(
                text=f"Tarjeta Débito o Crédito (Datáfono)\n\nPago registrado por valor exacto: COP $ {formatted_total}.\nListo para confirmar y emitir ticket."
            )
            self._set_confirm_button_state(ready=True)
            if enter_section:
                self._enter_section("CARD")
        else:  # is_fiado
            self.cash_container.pack_forget()
            self.change_card.pack_forget()
            self.transfer_container.pack_forget()
            self.card_container.pack_forget()
            if hasattr(self, "fiado_container"):
                self.fiado_container.pack(fill="x", pady=(18, 12))
                c_name = self.customer.full_name if self.customer else "Anónimo"
                c_doc = self.customer.document_id if self.customer else "Sin registrar"
                is_comp = getattr(self.customer, "is_company", False)
                doc_lbl = "NIT" if is_comp else "CC"
                formatted_total = f"{self.total_amount:,.0f}".replace(",", ".")
                self.fiado_info_lbl.configure(
                    text=f"Titular: {c_name}   •   {doc_lbl}: {c_doc}\n\n"
                         f"Monto total a crédito: COP $ {formatted_total}\n"
                         f"Los productos se descontarán del cupo pactado y se cargarán a la cuenta de la empresa para cobro a fin de mes."
                )
            self.confirm_btn.configure(
                text="✔ Confirmar Venta Fiada (Crédito)",
                fg_color="#B45309",
                hover_color="#D97706",
                border_color="#F59E0B"
            )
            self._set_confirm_button_state(ready=True)
            if enter_section:
                self._enter_section("FIADO")

        self._apply_focus_highlight()

    def _on_denom_click(self, val) -> None:
        self.nav_section = "CASH"
        if val in self.denom_buttons_map:
            btn = self.denom_buttons_map[val]
            if btn in self.cash_nav_items:
                self.cash_focus_idx = self.cash_nav_items.index(btn)
        elif val == "undo":
            self.cash_focus_idx = self.cash_nav_items.index(self.undo_btn)
        elif val == "exact":
            self.cash_focus_idx = self.cash_nav_items.index(self.exact_btn)
        elif val == "clear":
            self.cash_focus_idx = self.cash_nav_items.index(self.clear_btn)

        if val == "clear":
            self.cash_history.clear()
            self._last_btn_val = None
            self.cash_var.set("")
        elif val == "undo":
            self._on_undo()
        elif val == "exact":
            curr_str = self.cash_var.get()
            self.cash_history.append(curr_str)
            target = str(int(self.total_amount))
            self.cash_var.set(target)
            self._last_btn_val = target
        else:
            try:
                curr = float(self.cash_var.get().replace(".", "").replace(",", "").strip() or "0")
            except Exception:
                curr = 0
            curr_str = self.cash_var.get()
            self.cash_history.append(curr_str)
            new_val = curr + float(val)
            new_str = str(int(new_val))
            self.cash_var.set(new_str)
            self._last_btn_val = new_str

        self._update_change()
        self._apply_focus_highlight()

    def _on_undo(self) -> None:
        curr_text = self.cash_var.get().strip()
        if self._last_btn_val is not None and curr_text != self._last_btn_val:
            if curr_text:
                new_text = curr_text[:-1]
                self.cash_var.set(new_text)
                self._last_btn_val = new_text
        elif self.cash_history:
            prev_val = self.cash_history.pop()
            self.cash_var.set(prev_val)
            self._last_btn_val = prev_val
        else:
            if curr_text:
                new_text = curr_text[:-1]
                self.cash_var.set(new_text)
                self._last_btn_val = new_text
        self._update_change()

    def _update_change(self) -> None:
        if self.payment_method != "EFECTIVO":
            self.change_var.set("$ 0")
            self._set_confirm_button_state(ready=True)
            return

        try:
            val_str = self.cash_var.get().replace(".", "").replace(",", "").strip()
            cash = float(val_str) if val_str else 0.0
            diff = cash - self.total_amount

            if cash <= 0:
                self.change_var.set("$ 0")
                self.change_lbl.configure(text_color="#64748B")
                self._set_confirm_button_state(ready=False)
            elif diff < 0:
                formatted_diff = f"{abs(diff):,.0f}".replace(",", ".")
                self.change_var.set(f"Faltan $ {formatted_diff}")
                self.change_lbl.configure(text_color="#FF5E61")
                self._set_confirm_button_state(ready=False)
            else:
                formatted_diff = f"{diff:,.0f}".replace(",", ".")
                self.change_var.set(f"$ {formatted_diff}")
                self.change_lbl.configure(text_color="#34D399")
                self._set_confirm_button_state(ready=True)
        except Exception:
            self.change_var.set("$ 0")
            self._set_confirm_button_state(ready=False)

    def _on_confirm_payment(self) -> None:
        try:
            if self.payment_method == "EFECTIVO":
                val_str = self.cash_var.get().replace(".", "").replace(",", "").strip()
                cash = float(val_str) if val_str else 0.0
                if cash < self.total_amount:
                    formatted_cash = f"{cash:,.0f}".replace(",", ".")
                    formatted_tot = f"{self.total_amount:,.0f}".replace(",", ".")
                    messagebox.showerror(
                        "Pago Insuficiente",
                        f"El monto recibido ($ {formatted_cash}) es menor al total ($ {formatted_tot}).",
                        parent=self
                    )
                    return
            else:
                cash = self.total_amount

            chosen_method = self.payment_method
            if self.payment_method == "TRANSFERENCIA":
                plat = getattr(self, "transfer_platform", None) or "NEQUI"
                chosen_method = f"TRANSFERENCIA ({plat})"

            callback = self.on_complete_sale_callback
            try:
                self.grab_release()
            except Exception:
                pass
            self.destroy()

            if callback:
                # Support both callback(cash) and callback(cash, payment_method, customer_id)
                sig = inspect.signature(callback)
                if len(sig.parameters) >= 3:
                    cust_id = self.customer.id if self.customer else None
                    callback(cash, chosen_method, cust_id)
                elif len(sig.parameters) == 2:
                    callback(cash, chosen_method)
                else:
                    callback(cash)

        except Exception as e:
            messagebox.showerror("Error de Cobro", str(e), parent=self)


def abbreviate_product_name(name: str) -> str:
    """Intelligently abbreviate product names for compact quick buttons (Top 5).
    Example: 'Vino Tinto Reserva 750 ml' -> 'Vino 750', 'Costilla de Res' -> 'Costilla'.
    """
    if not name:
        return ""
    clean = name.strip()
    if len(clean) <= 12:
        return clean

    # Detect size/volume like 750 ml, 1 L, 500 g
    vol_match = re.search(r"(\d+)\s*(ml|l|g|kg)\b", clean, re.IGNORECASE)
    first_word = clean.split()[0]
    if vol_match and len(first_word) <= 7:
        return f"{first_word} {vol_match.group(1)}"

    # Remove common filler words
    shortened = re.sub(
        r"\b(de res|de cerdo|de pollo|campesina|campesino|especial|premium|fresco|fresca|nacional|tradicional|madurado|madurada|dry aged|artesanal|para)\b",
        "",
        clean,
        flags=re.IGNORECASE
    )
    shortened = " ".join(shortened.split())
    # Strip dangling trailing prepositions/symbols
    shortened = re.sub(r"\s+(de|con|para|y|/|-)$", "", shortened, flags=re.IGNORECASE)

    if len(shortened) <= 13:
        return shortened

    words = shortened.split()
    if len(words) >= 2 and len(f"{words[0]} {words[1]}") <= 13:
        cand = f"{words[0]} {words[1]}"
        return re.sub(r"\s+(de|con|para|y|/|-)$", "", cand, flags=re.IGNORECASE)
    if len(words) >= 1 and len(words[0]) <= 13:
        return words[0]

    return clean[:11].strip() + ".."


# ─────────────────────────────────────────────────────────────────────────────
# TOUCH-OPTIMIZED UNIT SELECTOR TOGGLE (UNIFORM TILES, NO ARTIFACTS)
# ─────────────────────────────────────────────────────────────────────────────
class TouchUnitToggle(ctk.CTkFrame):
    """Touch-friendly unit toggle with uniform button dimensions and no layout artifacts.
    Replaces default segmented button to provide large, tactile, equal-width unit tiles.
    """

    def __init__(self, master, on_change_callback=None, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("border_width", 0)
        kwargs.setdefault("corner_radius", 6)
        super().__init__(master, **kwargs)
        self.on_change_callback = on_change_callback
        self.buttons: Dict[str, ctk.CTkButton] = {}
        self.current_value: str = "kg"
        self._values: List[str] = []
        self._buttons_dict = self.buttons  # CTkSegmentedButton compatibility attribute

    def set_units(self, units: List[str], active_unit: Optional[str] = None, enabled: bool = True) -> None:
        self._values = list(units)
        for btn in list(self.buttons.values()):
            try:
                btn.destroy()
            except Exception:
                pass
        self.buttons.clear()

        if active_unit and active_unit in units:
            self.current_value = active_unit
        elif units:
            self.current_value = units[0]

        btn_width = 46 if len(units) > 1 else 52
        btn_height = 36

        for u in units:
            btn = ctk.CTkButton(
                self,
                text=u,
                width=btn_width,
                height=btn_height,
                corner_radius=6,
                border_width=1,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                command=lambda val=u: self._on_btn_click(val)
            )
            btn.pack(side="left", padx=2, pady=2)
            self.buttons[u] = btn

        self._refresh_styles()
        if not enabled:
            for b in self.buttons.values():
                b.configure(state="disabled", text_color_disabled="#F59E0B")

    def _on_btn_click(self, val: str) -> None:
        if val != self.current_value:
            self.current_value = val
            self._refresh_styles()
            if self.on_change_callback:
                self.on_change_callback(val)

    def cycle_next(self) -> None:
        """Cycle to the next available unit (e.g. kg -> lb -> g -> kg)."""
        if len(self._values) > 1:
            try:
                curr_idx = self._values.index(self.current_value)
                next_idx = (curr_idx + 1) % len(self._values)
                self._on_btn_click(self._values[next_idx])
            except ValueError:
                self._on_btn_click(self._values[0])

    def set(self, val: str) -> None:
        if val in self.buttons:
            self.current_value = val
            self._refresh_styles()

    def get(self) -> str:
        return self.current_value

    def configure(self, **kwargs):
        if "values" in kwargs:
            vals = kwargs.pop("values")
            st = kwargs.pop("state", "normal")
            kwargs.pop("text_color_disabled", None)
            self.set_units(vals, self.current_value, enabled=(st != "disabled"))
        if "state" in kwargs:
            st = kwargs.pop("state")
            for b in self.buttons.values():
                b.configure(state=st, text_color_disabled="#F59E0B")
        if kwargs:
            super().configure(**kwargs)

    def _refresh_styles(self) -> None:
        for u, btn in self.buttons.items():
            if u == self.current_value:
                btn.configure(
                    fg_color="#18130B",
                    hover_color="#2B210F",
                    border_color="#D97706",
                    border_width=1.5,
                    text_color="#FFFFFF",
                    text_color_disabled="#FFFFFF"
                )
            else:
                btn.configure(
                    fg_color="#111624",
                    hover_color="#182033",
                    border_color="#283347",
                    border_width=1,
                    text_color="#64748B",
                    text_color_disabled="#64748B"
                )


# ─────────────────────────────────────────────────────────────────────────────
# REDESIGNED POS FRAME (50/50 SPLIT VIEW, INTEGRATED WEIGHING & KEYPAD)
# ─────────────────────────────────────────────────────────────────────────────
class POSFrame(ctk.CTkFrame):
    """Sober, high-performance butcher counter POS presentation frame.
    Left Panel: Dominant capture, weighing, scale sync, touch keypad, customer bar.
    Right Panel: Visual receipt cart, itemized cuts, giant total, checkout button.
    """

    # Brand Colors (Dark Gourmet Butcher)
    _BG_DARK       = DarkTheme.BG_ROOT
    _BG_PANEL      = DarkTheme.BG_CARD
    _BORDER        = DarkTheme.BORDER_SUBTLE
    _PRIMARY_BLUE  = DarkTheme.PRIMARY
    _PRIMARY_HOVER = DarkTheme.PRIMARY_HOVER
    _EMERALD       = DarkTheme.SUCCESS
    _EMERALD_HOVER = DarkTheme.SUCCESS_HOVER
    _GOLD          = DarkTheme.PRIMARY
    _TEXT_LIGHT    = DarkTheme.TEXT_PRIMARY
    _TEXT_MUTED    = DarkTheme.TEXT_SECONDARY
    _TEXT_FAINT    = DarkTheme.TEXT_MUTED
    _INPUT_BG      = DarkTheme.INPUT_BG
    _INPUT_BORDER  = DarkTheme.INPUT_BORDER

    CATALOG_PLACEHOLDER = "Seleccionar"

    def __init__(
        self,
        parent,
        current_user: Optional[User] = None,
        scale_driver: Optional[Any] = None
    ):
        super().__init__(parent, fg_color=self._BG_DARK, corner_radius=0)
        self.current_user = current_user
        self.scale_driver = None

        # Operational State
        self.cart_items: List[CartItem] = []
        self._catalog_map: Dict[str, Product] = {}
        self.active_product: Optional[Product] = None
        self.current_customer: Optional[Customer] = None
        self.current_unit: str = "und"
        self._is_initial_qty: bool = True
        self.keypad_frame: Optional[ctk.CTkFrame] = None

        # State stringvars
        self.quantity_var = tk.StringVar(value="-")
        self.item_subtotal_var = tk.StringVar(value="COP $ --")

        self.scanner_listener = BarcodeScannerListener(self._on_scanner_barcode_scanned)

        self._build_ui()
        self.refresh_catalog()

        # Global key listener on top window
        try:
            self.winfo_toplevel().bind("<Key>", self._on_global_key_press, add="+")
        except Exception:
            pass

    # ── User and Session Management ───────────────────────────────────────────
    def set_user(self, user: User) -> None:
        self.current_user = user
        if hasattr(self, "cashier_lbl"):
            self.cashier_lbl.configure(text=f"Cajero: {user.full_name}")

    def reset_session(self) -> None:
        self.cart_items.clear()
        self._clear_customer()
        self._render_cart()
        if hasattr(self, "barcode_entry"):
            self.barcode_entry.delete(0, "end")
        self.active_product = None
        self._render_active_product()

    # ── Root UI Construction (50/50 Split View) ───────────────────────────────
    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1, uniform="pos_split")  # Left Capture Panel (50%)
        self.columnconfigure(1, weight=1, uniform="pos_split")  # Right Cart & Total (50%)
        self.rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_right_panel()

    # ──────────────────────────────────────────────────────────────────────────
    # LEFT PANEL: CAPTURA Y PESAJE
    # ──────────────────────────────────────────────────────────────────────────
    def _build_left_panel(self) -> None:
        left_container = ctk.CTkFrame(
            self,
            fg_color="transparent",
            border_width=0,
            corner_radius=0
        )
        left_container.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=(2, 8))

        # ── 1. Customer Identification Bar (Al Tope) ──────────────────────────
        self.cust_section = ctk.CTkFrame(left_container, fg_color="transparent")
        self.cust_section.pack(fill="x", padx=12, pady=(8, 4))
        self._render_customer_section()

        # Subtle divider
        ctk.CTkFrame(left_container, fg_color=self._BORDER, height=1).pack(fill="x", padx=12, pady=4)

        # ── 2. Product Search & Catalog ───────────────────────────────────────
        search_box = ctk.CTkFrame(left_container, fg_color="transparent")
        search_box.pack(fill="x", padx=12, pady=(4, 6))

        ctk.CTkLabel(
            search_box,
            text="BUSCAR PRODUCTOS:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#94A3B8"
        ).pack(anchor="w", pady=(0, 4))

        search_row = ctk.CTkFrame(search_box, fg_color="transparent")
        search_row.pack(fill="x")

        # Entry wrapper with embedded tag icon
        prod_input_frame = ctk.CTkFrame(
            search_row,
            fg_color="#0D1322",
            border_color="#3B4A66",
            border_width=1.5,
            corner_radius=8,
            width=140,
            height=38
        )
        prod_input_frame.pack_propagate(False)
        prod_input_frame.pack(side="left", padx=(0, 6))

        self.barcode_entry = ctk.CTkEntry(
            prod_input_frame,
            placeholder_text="Código",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color="transparent",
            border_width=0,
            text_color="#F1F5F9"
        )
        self.barcode_entry.pack(side="left", fill="both", expand=True, padx=(10, 2), pady=3)
        self.barcode_entry.bind("<Return>", lambda e: self._on_barcode_enter())
        self.barcode_entry.bind("<KP_Enter>", lambda e: self._on_barcode_enter())
        self.barcode_entry.bind("<Tab>", lambda e: (self._focus_product_selector(), "break")[1])
        self.barcode_entry.bind("<Shift-Tab>", lambda e: (self._focus_customer_entry(), "break")[1])
        self.barcode_entry.bind("<ISO_Left_Tab>", lambda e: (self._focus_customer_entry(), "break")[1])

        tag_img = get_ctk_icon("tag_slate", size=(16, 16))
        tag_btn = ctk.CTkButton(
            prod_input_frame,
            image=tag_img,
            text="",
            width=28,
            height=28,
            fg_color="transparent",
            hover_color="#182033",
            corner_radius=4,
            cursor="hand2",
            command=self._open_touch_barcode_keypad
        )
        tag_btn.pack(side="right", padx=(2, 8), pady=3)

        self.barcode_entry.bind("<FocusIn>", lambda e: prod_input_frame.configure(border_color="#3B82F6"), add="+")
        self.barcode_entry.bind("<FocusOut>", lambda e: prod_input_frame.configure(border_color="#3B4A66"), add="+")
        prod_input_frame._canvas.bind("<Button-1>", lambda e: self.barcode_entry.focus_set())

        # Touch keyboard button
        kb_img = get_ctk_icon("keyboard_slate", size=(18, 18))
        barcode_touch_btn = ctk.CTkButton(
            search_row,
            image=kb_img,
            text="",
            width=40,
            height=38,
            fg_color="#111624",
            border_color="#283347",
            border_width=1.5,
            hover_color="#182033",
            corner_radius=8,
            command=self._open_touch_barcode_keypad
        )
        barcode_touch_btn.pack(side="left", padx=(0, 6))

        # Magenta/purple search button
        search_img = get_ctk_icon("search_magenta", size=(18, 18))
        search_btn = ctk.CTkButton(
            search_row,
            image=search_img,
            text="",
            width=40,
            height=38,
            fg_color="#191126",
            border_color="#C026D3",
            border_width=1.5,
            hover_color="#2A163B",
            corner_radius=8,
            command=self._on_barcode_enter
        )
        search_btn.pack(side="left", padx=(0, 6))

        # Dropdown Combobox (wide, readonly, keyboard-operable)
        self.product_selector = ctk.CTkComboBox(
            search_row,
            width=180,
            height=38,
            values=["Seleccionar"],
            command=self._on_dropdown_product_selected,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#0D1322",
            border_color="#283347",
            border_width=1.5,
            button_color="#111624",
            button_hover_color="#182033",
            text_color="#CBD5E1",
            corner_radius=8,
            state="readonly"
        )
        self.product_selector.pack(side="left", fill="x", expand=True)

        def _open_sel_menu(e=None):
            try:
                self.product_selector._open_dropdown_menu()
            except Exception:
                pass
            return "break"

        def _on_selector_tab(e=None):
            self._focus_qty_entry()
            return "break"

        def _on_selector_shift_tab(e=None):
            self._focus_barcode_entry()
            return "break"

        self.product_selector.bind("<Return>", _open_sel_menu)
        self.product_selector.bind("<KP_Enter>", _open_sel_menu)
        self.product_selector.bind("<space>", _open_sel_menu)
        self.product_selector.bind("<Down>", _open_sel_menu)
        self.product_selector.bind("<Tab>", _on_selector_tab)
        self.product_selector.bind("<Shift-Tab>", _on_selector_shift_tab)
        self.product_selector.bind("<ISO_Left_Tab>", _on_selector_shift_tab)
        self.product_selector.bind("<FocusIn>", lambda e: self.product_selector.configure(border_color="#3B82F6"), add="+")
        self.product_selector.bind("<FocusOut>", lambda e: self.product_selector.configure(border_color="#283347"), add="+")

        if hasattr(self.product_selector, "_entry"):
            self.product_selector._entry.bind("<Return>", _open_sel_menu)
            self.product_selector._entry.bind("<KP_Enter>", _open_sel_menu)
            self.product_selector._entry.bind("<space>", _open_sel_menu)
            self.product_selector._entry.bind("<Down>", _open_sel_menu)
            self.product_selector._entry.bind("<Tab>", _on_selector_tab)
            self.product_selector._entry.bind("<Shift-Tab>", _on_selector_shift_tab)
            self.product_selector._entry.bind("<ISO_Left_Tab>", _on_selector_shift_tab)
            self.product_selector._entry.bind("<FocusIn>", lambda e: self.product_selector.configure(border_color="#3B82F6"), add="+")
            self.product_selector._entry.bind("<FocusOut>", lambda e: self.product_selector.configure(border_color="#283347"), add="+")

        # ── 3. Quick Cut Pills (Botonera de Productos Frecuentes - Top 5) ─────
        quick_cuts_frame = ctk.CTkFrame(left_container, fg_color="transparent")
        quick_cuts_frame.pack(fill="x", padx=12, pady=(2, 8))

        ctk.CTkLabel(
            quick_cuts_frame,
            text="PRODUCTOS FRECUENTES",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#94A3B8"
        ).pack(anchor="w", pady=(0, 4))

        self.cuts_grid = ctk.CTkFrame(quick_cuts_frame, fg_color="transparent")
        self.cuts_grid.pack(fill="x")
        self._render_frequent_products()

        # ── 4. Dominant Weighing & Active Cut Display ──────────────────────────
        self.weigh_card = ctk.CTkFrame(
            left_container,
            fg_color="#0A0E1A",
            border_color="#1A2436",
            border_width=1,
            corner_radius=10
        )
        self.weigh_card.pack(fill="x", padx=12, pady=(0, 8), ipady=4)

        # Header row: Product name on left, Stock in far right corner
        card_header = ctk.CTkFrame(self.weigh_card, fg_color="transparent")
        card_header.pack(fill="x", padx=12, pady=(6, 2))

        self.active_prod_stock_lbl = ctk.CTkLabel(
            card_header,
            text="Stock: --",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8",
            anchor="e"
        )
        self.active_prod_stock_lbl.pack(side="right", padx=(8, 0), anchor="ne")

        prod_info_box = ctk.CTkFrame(card_header, fg_color="transparent")
        prod_info_box.pack(side="left", fill="both", expand=True)

        self.active_prod_lbl = ctk.CTkLabel(
            prod_info_box,
            text="--",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#F1F5F9",
            anchor="w"
        )
        self.active_prod_lbl.pack(fill="x", anchor="w")

        self.active_prod_price_lbl = ctk.CTkLabel(
            prod_info_box,
            text="Precio Base: --",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8",
            anchor="w"
        )
        self.active_prod_price_lbl.pack(fill="x", anchor="w", pady=(1, 0))

        self.active_prod_sub = ctk.CTkLabel(self.weigh_card, text="", height=0)

        # Giant Display Box: Black sunken container with Amber Unit Pill on Left & Huge Text on Right
        disp_box = ctk.CTkFrame(
            self.weigh_card,
            fg_color="#050811",
            border_color="#182232",
            border_width=1,
            corner_radius=8
        )
        disp_box.pack(fill="x", padx=12, pady=(4, 6), ipady=4)

        # Unit selector buttons inside the bar on the left (Touch-friendly amber outline)
        self.unit_toggle = TouchUnitToggle(
            disp_box,
            on_change_callback=self._on_unit_change
        )
        self.unit_toggle.pack(side="left", padx=(8, 6), pady=6)
        self.unit_toggle.set_units(["--"], active_unit="--", enabled=False)
        self.unit_seg = self.unit_toggle

        # Unit label on far right
        self.unit_disp_lbl = ctk.CTkLabel(
            disp_box,
            text="--",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color="#FFFFFF"
        )
        self.unit_disp_lbl.pack(side="right", padx=(4, 16), pady=6)

        # Numeric entry in center/right
        self.qty_entry = ctk.CTkEntry(
            disp_box,
            textvariable=self.quantity_var,
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            justify="right",
            fg_color="transparent",
            border_width=0,
            text_color="#FFFFFF"
        )
        self.qty_entry.pack(side="right", fill="both", expand=True, padx=(4, 2), pady=6)
        self.qty_entry.bind("<KeyRelease>", lambda e: self._on_qty_keypress())
        self.qty_entry.bind("<Return>", lambda e: self._add_active_product_to_cart())
        self.qty_entry.bind("<KP_Enter>", lambda e: self._add_active_product_to_cart())
        self.qty_entry.bind("<Tab>", lambda e: (self._focus_add_item_btn(), "break")[1])
        self.qty_entry.bind("<Shift-Tab>", lambda e: (self._focus_product_selector(), "break")[1])
        self.qty_entry.bind("<ISO_Left_Tab>", lambda e: (self._focus_product_selector(), "break")[1])
        self.qty_entry.bind("<FocusIn>", lambda e: disp_box.configure(border_color="#3B82F6"), add="+")
        self.qty_entry.bind("<FocusOut>", lambda e: disp_box.configure(border_color="#182232"), add="+")

        # Live Subtotal of active product
        subtotal_row = ctk.CTkFrame(self.weigh_card, fg_color="transparent")
        subtotal_row.pack(fill="x", padx=12, pady=(0, 4))

        ctk.CTkLabel(
            subtotal_row,
            text="Subtotal productos:",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8"
        ).pack(side="left")

        self.subtotal_disp = ctk.CTkLabel(
            subtotal_row,
            textvariable=self.item_subtotal_var,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#10B981"
        )
        self.subtotal_disp.pack(side="right")

        # ── Quick Discount Bar (Descuento Producto por Producto) ─────────────
        disc_row = ctk.CTkFrame(self.weigh_card, fg_color="transparent")
        disc_row.pack(fill="x", padx=12, pady=(2, 6))

        tags_icon = get_ctk_icon("tags_slate", size=(16, 16))
        ctk.CTkLabel(
            disc_row,
            image=tags_icon,
            compound="left",
            text="  Descuento:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#94A3B8"
        ).pack(side="left", padx=(0, 6))

        self.active_discount_pct = 0.0
        self.disc_btn_pills = {}
        for p_val in [0, 10, 20, 50]:
            btn = ctk.CTkButton(
                disc_row,
                text=f"{p_val}%" if p_val > 0 else "0%",
                width=42,
                height=26,
                fg_color="#059669" if p_val == 0 else "#111624",
                border_color="#10B981" if p_val == 0 else "#222D42",
                border_width=1,
                hover_color="#0E291F" if p_val == 0 else "#192338",
                text_color="#FFFFFF" if p_val == 0 else "#94A3B8",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                corner_radius=6,
                cursor="hand2",
                command=lambda pv=p_val: self._set_active_discount(pv)
            )
            btn.pack(side="left", padx=2)
            self.disc_btn_pills[p_val] = btn

        self.custom_disc_btn = ctk.CTkButton(
            disc_row,
            image=None,
            text="Otro",
            width=54,
            height=26,
            fg_color="#111624",
            border_color="#222D42",
            border_width=1,
            hover_color="#192338",
            text_color="#94A3B8",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self._open_custom_discount_active
        )
        self.custom_disc_btn.pack(side="left", padx=2)

        # ── Primary Action Button: Agregar Producto (Enter) ───────────────────
        cart_green_img = get_ctk_icon("cart_plus_green", size=(18, 18))
        self.add_item_btn = ctk.CTkButton(
            self.weigh_card,
            image=cart_green_img,
            text="  Agregar producto (Enter)",
            compound="left",
            height=46,
            fg_color="#071913",
            border_color="#059669",
            border_width=1.5,
            hover_color="#0E291F",
            text_color="#34D399",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=8,
            command=self._add_active_product_to_cart
        )
        self.add_item_btn.pack(fill="x", padx=12, pady=(4, 8))
        self.add_item_btn.bind("<Return>", lambda e: (self._add_active_product_to_cart(), "break")[1])
        self.add_item_btn.bind("<KP_Enter>", lambda e: (self._add_active_product_to_cart(), "break")[1])
        self.add_item_btn.bind("<space>", lambda e: (self._add_active_product_to_cart(), "break")[1])
        self.add_item_btn.bind("<Tab>", lambda e: (self._focus_checkout_btn(), "break")[1])
        self.add_item_btn.bind("<Shift-Tab>", lambda e: (self._focus_qty_entry(), "break")[1])
        self.add_item_btn.bind("<ISO_Left_Tab>", lambda e: (self._focus_qty_entry(), "break")[1])
        self.add_item_btn.bind("<FocusIn>", lambda e: self.add_item_btn.configure(border_color="#10B981", border_width=2.5), add="+")
        self.add_item_btn.bind("<FocusOut>", lambda e: self.add_item_btn.configure(border_color="#059669", border_width=1.5), add="+")

        # ── 5. Integrated On-Screen Touch Keypad ──────────────────────────────
        self.keypad_frame = ctk.CTkFrame(left_container, fg_color="transparent")
        self.keypad_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        for c in range(4):
            self.keypad_frame.columnconfigure(c, weight=1)
        for r in range(4):
            self.keypad_frame.rowconfigure(r, weight=1)

        keypad_keys = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2), ("⌫", 0, 3),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2), ("C", 1, 3),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2), ("+1", 2, 3),
            ("0", 3, 0), ("00", 3, 1), (".", 3, 2), ("+ Unid", 3, 3),
        ]

        self.scale_btn = None

        for text, r, c in keypad_keys:
            is_clear = (text == "C")
            is_back = (text == "⌫")
            is_plus_one = (text == "+1")
            is_unit = (text == "+ Unid")

            if is_clear:
                bg = "#240D11"
                border_col = "#DC2626"
                border_w = 1.5
                hover_bg = "#361319"
                txt_col = "#EF4444"
                btn_font = ctk.CTkFont(family="Segoe UI", size=17, weight="bold")
                cmd = lambda: self._on_keypad_press("C")
                btn = ctk.CTkButton(
                    self.keypad_frame,
                    text=text,
                    height=48,
                    fg_color=bg,
                    border_color=border_col,
                    border_width=border_w,
                    hover_color=hover_bg,
                    text_color=txt_col,
                    font=btn_font,
                    corner_radius=8,
                    command=cmd
                )
            elif is_back:
                bg = "#1B160A"
                border_col = "#D97706"
                border_w = 1.5
                hover_bg = "#2A200F"
                back_img = get_ctk_icon("delete_left_gold", size=(22, 22))
                cmd = lambda: self._on_keypad_press("⌫")
                btn = ctk.CTkButton(
                    self.keypad_frame,
                    image=back_img,
                    text="",
                    height=48,
                    fg_color=bg,
                    border_color=border_col,
                    border_width=border_w,
                    hover_color=hover_bg,
                    corner_radius=8,
                    command=cmd
                )
            elif is_plus_one:
                bg = "#071913"
                border_col = "#059669"
                border_w = 1.5
                hover_bg = "#0E291F"
                txt_col = "#34D399"
                btn_font = ctk.CTkFont(family="Segoe UI", size=15, weight="bold")
                cmd = lambda: self._on_keypad_press("+1")
                btn = ctk.CTkButton(
                    self.keypad_frame,
                    text="+1",
                    height=48,
                    fg_color=bg,
                    border_color=border_col,
                    border_width=border_w,
                    hover_color=hover_bg,
                    text_color=txt_col,
                    font=btn_font,
                    corner_radius=8,
                    command=cmd
                )
            elif is_unit:
                bg = "#0B182B"
                border_col = "#2563EB"
                border_w = 1.5
                hover_bg = "#122542"
                txt_col = "#60A5FA"
                btn_font = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
                cmd = lambda: self._on_keypad_press("+ Unid")
                btn = ctk.CTkButton(
                    self.keypad_frame,
                    text=text,
                    height=48,
                    fg_color=bg,
                    border_color=border_col,
                    border_width=border_w,
                    hover_color=hover_bg,
                    text_color=txt_col,
                    font=btn_font,
                    corner_radius=8,
                    command=cmd
                )
            else:
                bg = "#111624"
                border_col = "#222D42"
                border_w = 1
                hover_bg = "#192338"
                txt_col = "#F1F5F9"
                btn_font = ctk.CTkFont(family="Segoe UI", size=17, weight="bold")
                cmd = lambda t=text: self._on_keypad_press(t)
                btn = ctk.CTkButton(
                    self.keypad_frame,
                    text=text,
                    height=48,
                    fg_color=bg,
                    border_color=border_col,
                    border_width=border_w,
                    hover_color=hover_bg,
                    text_color=txt_col,
                    font=btn_font,
                    corner_radius=8,
                    command=cmd
                )

            btn.grid(row=r, column=c, padx=3, pady=3, sticky="nsew")

    # ──────────────────────────────────────────────────────────────────────────
    # RIGHT PANEL: TICKET VISUAL Y TOTALIZADOR
    # ──────────────────────────────────────────────────────────────────────────
    def _build_right_panel(self) -> None:
        right_container = ctk.CTkFrame(
            self,
            fg_color=self._BG_PANEL,
            border_color=self._BORDER,
            border_width=1,
            corner_radius=12
        )
        right_container.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=(2, 8))

        # Header bar of Right Panel
        cart_header = ctk.CTkFrame(right_container, fg_color="transparent")
        cart_header.pack(fill="x", padx=14, pady=(10, 6))

        ticket_img = get_ctk_icon("ticket_white", size=(22, 22))
        ticket_lbl = ctk.CTkLabel(
            cart_header,
            image=ticket_img,
            text="  Ticket de venta",
            compound="left",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#F8FAFC"
        )
        ticket_lbl.pack(side="left")

        user_name = self.current_user.full_name if self.current_user else "Cajero General"
        self.cashier_lbl = ctk.CTkLabel(
            cart_header,
            text=f"Cajero: {user_name}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8"
        )

        trash_img = get_ctk_icon("trash_red", size=(16, 16))
        clear_btn = ctk.CTkButton(
            cart_header,
            image=trash_img,
            text="  Eliminar",
            compound="left",
            width=92,
            height=32,
            fg_color="#220D10",
            border_color="#DC2626",
            border_width=1.5,
            hover_color="#331317",
            text_color="#EF4444",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            command=self._clear_cart
        )
        clear_btn.pack(side="right")

        # Table Column Headers
        tbl_headers = ctk.CTkFrame(
            right_container,
            fg_color="#111624",
            border_color="#1E283D",
            border_width=1,
            corner_radius=6,
            height=32
        )
        tbl_headers.pack(fill="x", padx=12, pady=(4, 4))

        tbl_headers.grid_columnconfigure(0, weight=1)
        tbl_headers.grid_columnconfigure(1, weight=0)
        tbl_headers.grid_columnconfigure(2, weight=0)
        tbl_headers.grid_columnconfigure(3, weight=0)
        tbl_headers.grid_columnconfigure(4, weight=0)
        tbl_headers.grid_columnconfigure(5, weight=0)
        tbl_headers.grid_columnconfigure(6, weight=0, minsize=16)

        ctk.CTkLabel(
            tbl_headers,
            text="Producto",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8",
            anchor="w"
        ).grid(row=0, column=0, sticky="ew", padx=(12, 4), pady=5)

        ctk.CTkLabel(
            tbl_headers,
            text="Unidad",
            width=44,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8",
            anchor="center"
        ).grid(row=0, column=1, sticky="", padx=2, pady=5)

        ctk.CTkLabel(
            tbl_headers,
            text="Cantidad",
            width=68,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8",
            anchor="center"
        ).grid(row=0, column=2, sticky="", padx=2, pady=5)

        ctk.CTkLabel(
            tbl_headers,
            text="Precio base",
            width=78,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8",
            anchor="e"
        ).grid(row=0, column=3, sticky="e", padx=(2, 6), pady=5)

        ctk.CTkLabel(
            tbl_headers,
            text="Subtotal",
            width=82,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8",
            anchor="e"
        ).grid(row=0, column=4, sticky="e", padx=(2, 6), pady=5)

        ctk.CTkLabel(
            tbl_headers,
            text="Acciones",
            width=68,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8",
            anchor="center"
        ).grid(row=0, column=5, sticky="e", padx=(2, 4), pady=5)

        # Scrollable Cart Table
        self.cart_scroll = ctk.CTkScrollableFrame(
            right_container,
            fg_color="#080C16",
            corner_radius=6
        )
        self.cart_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        # Bottom Totalizer & Checkout Card
        total_section = ctk.CTkFrame(
            right_container,
            fg_color="transparent",
            border_color=self._BORDER,
            border_width=1,
            corner_radius=10
        )
        total_section.pack(fill="x", padx=12, pady=(0, 8), ipady=2)

        # Summary line
        sum_row = ctk.CTkFrame(total_section, fg_color="transparent")
        sum_row.pack(fill="x", padx=16, pady=(4, 2))

        ctk.CTkLabel(
            sum_row,
            text="Subtotal canasta:",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8"
        ).pack(side="left")

        self.subtotal_disp_lbl = ctk.CTkLabel(
            sum_row,
            text="COP $ 0",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#CBD5E1"
        )
        self.subtotal_disp_lbl.pack(side="right")

        iva_row = ctk.CTkFrame(total_section, fg_color="transparent")
        iva_row.pack(fill="x", padx=16, pady=(0, 2))

        ctk.CTkLabel(
            iva_row,
            text="IVA (0% canasta básica)",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8"
        ).pack(side="left")

        ctk.CTkLabel(
            iva_row,
            text="COP $ 0",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#CBD5E1"
        ).pack(side="right")

        # Discount summary row
        self.discount_row = ctk.CTkFrame(total_section, fg_color="transparent")
        ctk.CTkLabel(
            self.discount_row,
            text="Descuentos aplicados:",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#10B981"
        ).pack(side="left")

        self.discount_disp_lbl = ctk.CTkLabel(
            self.discount_row,
            text="-COP $ 0",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#10B981"
        )
        self.discount_disp_lbl.pack(side="right")

        # Giant Total Display with Neon Cyan Outline
        self.giant_total_box = ctk.CTkFrame(
            total_section,
            fg_color="#060B18",
            border_color="#0284C7",
            border_width=1.8,
            corner_radius=10
        )
        self.giant_total_box.pack(fill="x", padx=4, pady=(2, 6), ipady=4)

        ctk.CTkLabel(
            self.giant_total_box,
            text="TOTAL A PAGAR",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#38BDF8"
        ).pack(pady=(4, 0))

        self.total_disp_lbl = ctk.CTkLabel(
            self.giant_total_box,
            text="COP $ 0",
            font=ctk.CTkFont(family="Segoe UI", size=32, weight="bold"),
            text_color="#FFFFFF"
        )
        self.total_disp_lbl.pack(pady=(0, 2))

        self.item_count_lbl = ctk.CTkLabel(
            self.giant_total_box,
            text="0 productos en el carrito",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8"
        )
        self.item_count_lbl.pack(pady=(0, 6))

        # Checkout Button with Emerald Green Outline and Money Icon
        money_img = get_ctk_icon("money_green", size=(24, 24))
        self.checkout_btn = ctk.CTkButton(
            total_section,
            image=money_img,
            text="  COBRAR FACTURA",
            compound="left",
            height=54,
            fg_color="#071913",
            border_color="#059669",
            border_width=2,
            hover_color="#0E291F",
            text_color="#34D399",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            corner_radius=10,
            command=self._on_checkout_click
        )
        self.checkout_btn.pack(fill="x", padx=4, pady=(4, 4))
        self.checkout_btn.bind("<Return>", lambda e: (self._on_checkout_click(), "break")[1])
        self.checkout_btn.bind("<KP_Enter>", lambda e: (self._on_checkout_click(), "break")[1])
        self.checkout_btn.bind("<space>", lambda e: (self._on_checkout_click(), "break")[1])
        self.checkout_btn.bind("<Tab>", lambda e: (self._focus_customer_entry() if hasattr(self, "customer_doc_entry") else self._focus_barcode_entry(), "break")[1])
        self.checkout_btn.bind("<Shift-Tab>", lambda e: (self._focus_add_item_btn(), "break")[1])
        self.checkout_btn.bind("<ISO_Left_Tab>", lambda e: (self._focus_add_item_btn(), "break")[1])
        self.checkout_btn.bind("<FocusIn>", lambda e: self.checkout_btn.configure(border_color="#34D399", border_width=3.0), add="+")
        self.checkout_btn.bind("<FocusOut>", lambda e: self.checkout_btn.configure(border_color="#059669", border_width=2.0), add="+")

        self._render_cart()

    # ──────────────────────────────────────────────────────────────────────────
    # CUSTOMER IDENTIFICATION FLOW (CASE A & CASE B INLINE REGISTRATION)
    # ──────────────────────────────────────────────────────────────────────────
    def _render_customer_section(self, mode: str = "search", doc_prefill: str = "") -> None:
        for w in self.cust_section.winfo_children():
            w.destroy()

        # Ocultar el teclado numérico de cantidades durante el registro rápido de cliente para evitar compresión
        if mode == "quick_reg":
            if getattr(self, "keypad_frame", None) and self.keypad_frame.winfo_manager() == "pack":
                self.keypad_frame.pack_forget()
        else:
            if getattr(self, "keypad_frame", None) and self.keypad_frame.winfo_manager() != "pack":
                if hasattr(self, "weigh_card") and self.weigh_card.winfo_manager() == "pack":
                    self.keypad_frame.pack(after=self.weigh_card, fill="both", expand=True, padx=12, pady=(0, 8))
                else:
                    self.keypad_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        if self.current_customer:
            # ── CASE A: Customer Active Badge ─────────────────────────────────
            is_company = getattr(self.current_customer, "is_company", False)
            border_col = "#F59E0B" if is_company else DarkTheme.SUCCESS_BORDER
            text_col = "#FBBF24" if is_company else DarkTheme.SUCCESS
            doc_lbl = "NIT" if is_company else "CC"
            prefix = "🏢 [EMPRESA]" if is_company else "👤"

            badge = ctk.CTkFrame(
                self.cust_section,
                fg_color="#18140B" if is_company else DarkTheme.BG_ELEVATED,
                border_color=border_col,
                border_width=1.5 if is_company else 1,
                corner_radius=8
            )
            badge.pack(fill="x", ipady=2)

            info_txt = f"{prefix} {self.current_customer.full_name}  •  {doc_lbl}: {self.current_customer.document_id}"
            ctk.CTkLabel(
                badge,
                text=info_txt,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color=text_col
            ).pack(side="left", padx=12, pady=4)

            change_btn = ctk.CTkButton(
                badge,
                text="✕ Cambiar",
                width=75,
                height=26,
                fg_color=DarkTheme.BG_CARD,
                hover_color=DarkTheme.DANGER_BG,
                border_color=DarkTheme.BORDER_SUBTLE,
                border_width=1,
                text_color=DarkTheme.DANGER,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                corner_radius=6,
                command=self._clear_customer
            )
            change_btn.pack(side="right", padx=8, pady=4)

            if is_company:
                quotas_btn = ctk.CTkButton(
                    badge,
                    text="📋 Cupos Fiados",
                    width=96,
                    height=26,
                    fg_color="#291804",
                    hover_color="#451A03",
                    border_color="#D97706",
                    border_width=1.2,
                    text_color="#FBBF24",
                    font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                    corner_radius=6,
                    command=self._show_company_quick_quotas
                )
                quotas_btn.pack(side="right", padx=(0, 4), pady=4)

        elif mode == "quick_reg":
            # ── CASE B: Inline Quick Registration Form (Mockup High-Fidelity) ─
            reg_box = ctk.CTkFrame(
                self.cust_section,
                fg_color="#0A0D14",
                border_color="#F59E0B",
                border_width=1.5,
                corner_radius=8
            )
            reg_box.pack(fill="x", padx=2, pady=4, ipadx=8, ipady=10)

            self.reg_type_var = ctk.StringVar(value="PERSONA")

            # Header info inside golden box:
            header_frame = ctk.CTkFrame(reg_box, fg_color="transparent")
            header_frame.pack(fill="x", padx=12, pady=(6, 6))

            ctk.CTkLabel(
                header_frame,
                text=f"Doc/NIT {doc_prefill} no registrado.",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color="#F59E0B",
                anchor="w"
            ).pack(side="left")

            # Radio / Toggle selector: [👤 Persona | 🏢 Empresa]
            self.reg_type_seg = ctk.CTkSegmentedButton(
                header_frame,
                values=["Persona", "Empresa"],
                command=self._on_quick_reg_type_toggle,
                height=28,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                fg_color="#111624",
                selected_color="#D97706",
                selected_hover_color="#B45309",
                unselected_color="#111624",
                text_color="#FFFFFF"
            )
            self.reg_type_seg.set("Persona")
            self.reg_type_seg.pack(side="right")

            # Row 1: Nombre / Razón Social and Apellido / Contacto
            row1 = ctk.CTkFrame(reg_box, fg_color="transparent")
            row1.pack(fill="x", padx=12, pady=(4, 8))
            row1.grid_columnconfigure(0, weight=1)
            row1.grid_columnconfigure(1, weight=1)

            self.new_first_name_entry = ctk.CTkEntry(
                row1,
                placeholder_text="Nombre *",
                placeholder_text_color="#64748B",
                height=40,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                fg_color="#060B18",
                border_color="#242B3D",
                border_width=1,
                corner_radius=6,
                text_color="#F8FAFC"
            )
            self.new_first_name_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

            self.new_last_name_entry = ctk.CTkEntry(
                row1,
                placeholder_text="Apellido *",
                placeholder_text_color="#64748B",
                height=40,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                fg_color="#060B18",
                border_color="#242B3D",
                border_width=1,
                corner_radius=6,
                text_color="#F8FAFC"
            )
            self.new_last_name_entry.grid(row=0, column=1, sticky="ew", padx=(5, 0))

            # Row 2: Telefono opcional * + Guardar (Green) + Cancelar (Red)
            row2 = ctk.CTkFrame(reg_box, fg_color="transparent")
            row2.pack(fill="x", padx=12, pady=(0, 6))
            row2.grid_columnconfigure(0, weight=4)
            row2.grid_columnconfigure(1, weight=3)
            row2.grid_columnconfigure(2, weight=3)

            self.new_phone_entry = ctk.CTkEntry(
                row2,
                placeholder_text="Teléfono (Ej: 3000000000) *",
                placeholder_text_color="#64748B",
                height=40,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                fg_color="#060B18",
                border_color="#242B3D",
                border_width=1,
                corner_radius=6,
                text_color="#F8FAFC"
            )
            self.new_phone_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))

            save_icon = get_ctk_icon("floppy_green", size=(16, 16))
            cancel_icon = get_ctk_icon("ban_red", size=(16, 16))

            save_btn = ctk.CTkButton(
                row2,
                text=" Guardar",
                image=save_icon,
                compound="left",
                height=40,
                fg_color="#061A10",
                hover_color="#0E2B1C",
                border_color="#10B981",
                border_width=1.5,
                text_color="#34D399",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                corner_radius=6,
                command=lambda: self._quick_register_customer(doc_prefill)
            )
            save_btn.grid(row=0, column=1, sticky="ew", padx=3)

            cancel_btn = ctk.CTkButton(
                row2,
                text=" Cancelar",
                image=cancel_icon,
                compound="left",
                height=40,
                fg_color="#1A0A0E",
                hover_color="#2D1117",
                border_color="#EF4444",
                border_width=1.5,
                text_color="#F87171",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                corner_radius=6,
                command=self._clear_customer
            )
            cancel_btn.grid(row=0, column=2, sticky="ew", padx=(3, 0))

            self.new_first_name_entry.bind("<Return>", lambda e: self.new_last_name_entry.focus_set())
            self.new_last_name_entry.bind("<Return>", lambda e: self.new_phone_entry.focus_set())
            self.new_phone_entry.bind("<Return>", lambda e: self._quick_register_customer(doc_prefill))
            self.new_first_name_entry.focus_set()

        else:
            # ── Default Identification Bar (Mockup High-Fidelity) ─────────────
            id_bar = ctk.CTkFrame(self.cust_section, fg_color="transparent")
            id_bar.pack(fill="x")

            ctk.CTkLabel(
                id_bar,
                text="CLIENTE",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#94A3B8"
            ).pack(side="left", padx=(0, 10))

            # Entry wrapper with embedded ID card icon
            cust_input_frame = ctk.CTkFrame(
                id_bar,
                fg_color="#0D1322",
                border_color="#3B4A66",
                border_width=1.5,
                corner_radius=8,
                height=38
            )
            cust_input_frame.pack_propagate(False)
            cust_input_frame.pack(side="left", fill="x", expand=True, padx=(0, 6))

            self.customer_doc_entry = ctk.CTkEntry(
                cust_input_frame,
                placeholder_text="Cédula o NIT de Empresa",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                fg_color="transparent",
                border_width=0,
                text_color="#F1F5F9"
            )
            self.customer_doc_entry.pack(side="left", fill="both", expand=True, padx=(10, 2), pady=3)
            self.customer_doc_entry.bind("<Return>", lambda e: self._on_customer_search())
            self.customer_doc_entry.bind("<KP_Enter>", lambda e: self._on_customer_search())
            self.customer_doc_entry.bind("<Tab>", lambda e: (self._focus_barcode_entry(), "break")[1])
            self.customer_doc_entry.bind("<Shift-Tab>", lambda e: (self._focus_checkout_btn(), "break")[1])
            self.customer_doc_entry.bind("<ISO_Left_Tab>", lambda e: (self._focus_checkout_btn(), "break")[1])

            id_card_img = get_ctk_icon("id_card_slate", size=(20, 20))
            id_card_btn = ctk.CTkButton(
                cust_input_frame,
                image=id_card_img,
                text="",
                width=28,
                height=28,
                fg_color="transparent",
                hover_color="#182033",
                corner_radius=4,
                cursor="hand2",
                command=self._open_touch_customer_keypad
            )
            id_card_btn.pack(side="right", padx=(2, 8), pady=3)

            self.customer_doc_entry.bind("<FocusIn>", lambda e: cust_input_frame.configure(border_color="#3B82F6"), add="+")
            self.customer_doc_entry.bind("<FocusOut>", lambda e: cust_input_frame.configure(border_color="#3B4A66"), add="+")
            cust_input_frame._canvas.bind("<Button-1>", lambda e: self.customer_doc_entry.focus_set())

            # Touch keyboard button
            kb_img = get_ctk_icon("keyboard_slate", size=(18, 18))
            cust_touch_btn = ctk.CTkButton(
                id_bar,
                image=kb_img,
                text="",
                width=40,
                height=38,
                fg_color="#111624",
                border_color="#283347",
                border_width=1.5,
                hover_color="#182033",
                corner_radius=8,
                command=self._open_touch_customer_keypad
            )
            cust_touch_btn.pack(side="left", padx=(0, 6))

            # Magenta/purple search button
            search_img = get_ctk_icon("search_magenta", size=(18, 18))
            search_cust_btn = ctk.CTkButton(
                id_bar,
                image=search_img,
                text="",
                width=40,
                height=38,
                fg_color="#191126",
                border_color="#C026D3",
                border_width=1.5,
                hover_color="#2A163B",
                corner_radius=8,
                command=self._on_customer_search
            )
            search_cust_btn.pack(side="left")

    def _open_touch_customer_keypad(self) -> None:
        init_val = self.customer_doc_entry.get().strip() if hasattr(self, "customer_doc_entry") else ""
        TouchKeypadModal(
            parent=self,
            title="Teclado Numérico - Cédula / NIT",
            on_confirm_callback=self._on_touch_customer_confirmed,
            initial_value=init_val
        )

    def _on_touch_customer_confirmed(self, val: str) -> None:
        if hasattr(self, "customer_doc_entry"):
            self.customer_doc_entry.delete(0, "end")
            self.customer_doc_entry.insert(0, val)
            self._on_customer_search()

    def _open_touch_barcode_keypad(self) -> None:
        init_val = self.barcode_entry.get().strip() if hasattr(self, "barcode_entry") else ""
        TouchKeypadModal(
            parent=self,
            title="Teclado Numérico - Código / PLU",
            on_confirm_callback=self._on_touch_barcode_confirmed,
            initial_value=init_val
        )

    def _on_touch_barcode_confirmed(self, val: str) -> None:
        if hasattr(self, "barcode_entry"):
            self.barcode_entry.delete(0, "end")
            self.barcode_entry.insert(0, val)
            self._on_barcode_enter()

    def _on_customer_search(self) -> None:
        if not hasattr(self, "customer_doc_entry"):
            return
        doc = self.customer_doc_entry.get().strip()
        if not doc or doc in ("0", "222222222222", "consumidor final"):
            self._set_anonymous_customer()
            return

        with get_db_connection() as conn:
            cust = CustomerModel.get_by_document(conn, doc)

        if cust:
            self.current_customer = cust
            self._render_customer_section()
            if getattr(cust, "is_company", False) and getattr(cust, "discount_percent", 0.0) > 0:
                self._set_active_discount(cust.discount_percent)
            self._focus_barcode_entry()
        else:
            self._render_customer_section(mode="quick_reg", doc_prefill=doc)

    def _on_quick_reg_type_toggle(self, val: str) -> None:
        if val == "Empresa":
            self.reg_type_var.set("EMPRESA")
            if hasattr(self, "new_first_name_entry"):
                self.new_first_name_entry.configure(placeholder_text="Nombre empresa (Ej: Los Portales) *")
            if hasattr(self, "new_last_name_entry"):
                self.new_last_name_entry.configure(placeholder_text="Representante (Ej: Diego Martínez) *")
            if hasattr(self, "new_phone_entry"):
                self.new_phone_entry.configure(placeholder_text="Teléfono (Ej: 3000000000) *")
        else:
            self.reg_type_var.set("PERSONA")
            if hasattr(self, "new_first_name_entry"):
                self.new_first_name_entry.configure(placeholder_text="Nombre *")
            if hasattr(self, "new_last_name_entry"):
                self.new_last_name_entry.configure(placeholder_text="Apellido *")
            if hasattr(self, "new_phone_entry"):
                self.new_phone_entry.configure(placeholder_text="Teléfono (Ej: 3000000000) *")

    def _quick_register_customer(self, doc: str) -> None:
        first = self.new_first_name_entry.get().strip()
        last = self.new_last_name_entry.get().strip()
        phone = self.new_phone_entry.get().strip()
        c_type = self.reg_type_var.get() if hasattr(self, "reg_type_var") else "PERSONA"

        # 1. Documento o NIT: no lleva validación restrictiva de formato (admite números, letras, guiones, etc.)
        doc_clean = str(doc).strip()
        if not doc_clean:
            sound_manager.play_error()
            messagebox.showwarning("Atención", "El documento o NIT es requerido.", parent=self)
            return

        # 2. Validación de Nombre
        if not first:
            sound_manager.play_error()
            lbl = "el nombre de la empresa" if c_type == "EMPRESA" else "el nombre del cliente"
            messagebox.showwarning("Atención", f"Ingrese {lbl}.", parent=self)
            self.new_first_name_entry.focus_set()
            return

        if c_type == "PERSONA":
            # Para persona: el nombre no pueden ser números
            if re.search(r"\d", first):
                sound_manager.play_error()
                messagebox.showwarning(
                    "Nombre Inválido",
                    "El nombre del cliente está mal escrito: no puede contener números.",
                    parent=self
                )
                self.new_first_name_entry.focus_set()
                return

        # 3. Validación de Apellido / Representante
        if c_type == "EMPRESA":
            if not last:
                sound_manager.play_error()
                messagebox.showwarning("Atención", "Ingrese el representante de la empresa.", parent=self)
                self.new_last_name_entry.focus_set()
                return
            # El nombre del representante debe llevar nombre (no pueden ser números)
            if re.search(r"\d", last):
                sound_manager.play_error()
                messagebox.showwarning(
                    "Representante Inválido",
                    "El nombre del representante está mal escrito: no puede contener números.",
                    parent=self
                )
                self.new_last_name_entry.focus_set()
                return
        else:
            # Para persona: el apellido no pueden ser números
            if not last:
                sound_manager.play_error()
                messagebox.showwarning("Atención", "Ingrese el apellido del cliente.", parent=self)
                self.new_last_name_entry.focus_set()
                return
            if re.search(r"\d", last):
                sound_manager.play_error()
                messagebox.showwarning(
                    "Apellido Inválido",
                    "El apellido del cliente está mal escrito: no puede contener números.",
                    parent=self
                )
                self.new_last_name_entry.focus_set()
                return

        # 4. Validación de Teléfono: obligatorio, debe empezar por 3 y tener exactamente 10 dígitos
        if not phone:
            sound_manager.play_error()
            messagebox.showwarning(
                "Teléfono Obligatorio",
                "El número de teléfono está mal escrito: debe comenzar con 3 y tener exactamente 10 dígitos (Ej: 3000000000).",
                parent=self
            )
            self.new_phone_entry.focus_set()
            return

        clean_phone = re.sub(r"[\s\-\.\(\)]", "", phone)
        if not clean_phone.isdigit():
            sound_manager.play_error()
            messagebox.showwarning(
                "Teléfono Inválido",
                "El número de teléfono está mal escrito: solo puede contener números.",
                parent=self
            )
            self.new_phone_entry.focus_set()
            return

        if not clean_phone.startswith("3"):
            sound_manager.play_error()
            messagebox.showwarning(
                "Teléfono Inválido",
                "El número de teléfono está mal escrito: los números en Colombia deben comenzar por 3.",
                parent=self
            )
            self.new_phone_entry.focus_set()
            return

        if len(clean_phone) != 10:
            sound_manager.play_error()
            messagebox.showwarning(
                "Teléfono Inválido",
                f"El número de teléfono está mal escrito: debe tener exactamente 10 dígitos (actualmente tiene {len(clean_phone)}).",
                parent=self
            )
            self.new_phone_entry.focus_set()
            return

        try:
            with get_db_connection() as conn:
                cust = CustomerModel.create(conn, doc_clean, first, last or "", clean_phone, customer_type=c_type)
            sound_manager.play_sale_success()
            self.current_customer = cust
            self._render_customer_section()
            if getattr(cust, "is_company", False) and getattr(cust, "discount_percent", 0.0) > 0:
                self._set_active_discount(cust.discount_percent)
            self._focus_barcode_entry()
        except Exception as e:
            sound_manager.play_error()
            messagebox.showerror("Error", f"No se pudo guardar: {e}", parent=self)

    def _show_company_quick_quotas(self) -> None:
        if self.current_customer and getattr(self.current_customer, "is_company", False):
            CompanyQuickQuotasModal(parent=self.winfo_toplevel(), company=self.current_customer)

    def _clear_customer(self) -> None:
        self.current_customer = None
        self._set_active_discount(0.0)
        self._render_customer_section()

    def _set_anonymous_customer(self) -> None:
        self.current_customer = None
        self._set_active_discount(0.0)
        self._render_customer_section()
        self._focus_barcode_entry()

    # ──────────────────────────────────────────────────────────────────────────
    # PRODUCT SELECTION & MEASUREMENT
    # ──────────────────────────────────────────────────────────────────────────
    def _open_new_product_from_pos(self) -> None:
        """Permite al cajero registrar rápidamente un nuevo corte/producto sin salir de Ventas."""
        try:
            from views.inventory_frame import ProductFormModal

            def on_saved():
                self.refresh_catalog()
                self._focus_barcode_entry()

            ProductFormModal(
                parent=self.winfo_toplevel(),
                product=None,
                on_save_callback=on_saved
            )
        except Exception as e:
            logging.error("Error abriendo modal de nuevo producto desde POS: %s", e)

    def refresh_catalog(self) -> None:
        try:
            with get_db_connection() as conn:
                products = ProductModel.get_all(conn)

            # Sort products naturally by ID (1, 2, 3... N)
            products = sorted(products, key=lambda p: (p.id, p.name))

            self._catalog_map = {}
            vals = [self.CATALOG_PLACEHOLDER]
            for p in products:
                label = f"{p.id} - {p.name}"
                self._catalog_map[label] = p
                self._catalog_map[p.name] = p
                self._catalog_map[str(p.id)] = p
                if p.barcode:
                    self._catalog_map[str(p.barcode).strip()] = p
                vals.append(label)

            self.product_selector.configure(values=vals)
            self.product_selector.set(self.CATALOG_PLACEHOLDER)

            # Do not auto-select ID 1 or first product. POS starts clean with placeholders.
            if not self.active_product:
                self._render_active_product()
            self._render_frequent_products()
        except Exception as e:
            self.product_selector.configure(values=["Error cargando"])

    def _select_product(self, product: Product) -> None:
        self.active_product = product
        self._is_initial_qty = True
        self._set_active_discount(0.0)

        pkg_info = product.fixed_package_info
        if product.sale_type == "PESO":
            self._is_fixed_qty = False
            self.current_unit = "kg"
            self.unit_toggle.set_units(["kg", "lb", "g"], active_unit="kg", enabled=True)
            self.unit_disp_lbl.configure(text="kg")
            self.quantity_var.set("1.00")
            self.qty_entry.configure(state="normal")
            if getattr(self, "scale_btn", None):
                self.scale_btn.configure(state="normal")
        elif pkg_info is not None:
            # Fixed quantity package like wine bottle (750 ml) - user cannot edit quantity
            fixed_qty, fixed_unit = pkg_info
            self._is_fixed_qty = True
            self.current_unit = fixed_unit
            self.unit_toggle.set_units([fixed_unit], active_unit=fixed_unit, enabled=True)
            self.unit_disp_lbl.configure(text=fixed_unit)
            self.quantity_var.set(str(int(fixed_qty) if fixed_qty.is_integer() else fixed_qty))
            self.qty_entry.configure(state="readonly")
            if getattr(self, "scale_btn", None):
                self.scale_btn.configure(state="disabled")
        else:
            # Standard UNIDAD product (e.g. arepas, huevos)
            self._is_fixed_qty = False
            self.current_unit = "und"
            self.unit_toggle.set_units(["und"], active_unit="und", enabled=True)
            self.unit_disp_lbl.configure(text="und")
            self.quantity_var.set("1")
            self.qty_entry.configure(state="normal")
            if getattr(self, "scale_btn", None):
                self.scale_btn.configure(state="disabled")

        self._render_active_product()
        self._update_item_calculations()

        # Synchronize combobox display with selected product ("code - name")
        if hasattr(self, "product_selector") and hasattr(self, "_catalog_map"):
            code_str = str(product.barcode if product.barcode else product.id).strip()
            target_label = f"{code_str} - {product.name}"
            matched = False
            for label, p in self._catalog_map.items():
                if p.id == product.id and " - " in label:
                    self.product_selector.set(label)
                    matched = True
                    break
            if not matched:
                self.product_selector.set(target_label)

        # Synchronize barcode/ID entry with ONLY the code
        if hasattr(self, "barcode_entry"):
            code_str = str(product.barcode if product.barcode else product.id).strip()
            if self.barcode_entry.get().strip() != code_str:
                self.barcode_entry.delete(0, "end")
                self.barcode_entry.insert(0, code_str)

    def _render_active_product(self) -> None:
        if not self.active_product:
            self.active_prod_lbl.configure(text="--")
            if hasattr(self, "active_prod_price_lbl"):
                self.active_prod_price_lbl.configure(text="Precio Base: --")
            if hasattr(self, "active_prod_stock_lbl"):
                self.active_prod_stock_lbl.configure(text="Stock: --", text_color="#94A3B8")
            if hasattr(self, "active_prod_sub"):
                self.active_prod_sub.configure(text="")
            if hasattr(self, "unit_disp_lbl"):
                self.unit_disp_lbl.configure(text="--")
            if hasattr(self, "unit_toggle"):
                self.unit_toggle.set_units(["--"], active_unit="--", enabled=False)
            self.quantity_var.set("-")
            self.item_subtotal_var.set("COP $ --")
            self._set_active_discount(0.0)
            if hasattr(self, "barcode_entry") and self.barcode_entry.winfo_exists():
                self.barcode_entry.delete(0, "end")
            if hasattr(self, "product_selector"):
                self.product_selector.set(self.CATALOG_PLACEHOLDER)
            if getattr(self, "scale_btn", None):
                self.scale_btn.configure(state="disabled")
            return

        p = self.active_product
        self.active_prod_lbl.configure(text=p.name)
        stock_txt = f"Stock: {p.formatted_stock}"
        if p.is_low_stock:
            stock_txt += "  [Stock Bajo]"

        if hasattr(self, "active_prod_price_lbl"):
            self.active_prod_price_lbl.configure(text=f"Precio Base: {p.formatted_price_base}")
        if hasattr(self, "active_prod_stock_lbl"):
            stock_color = DarkTheme.DANGER if p.is_low_stock else self._TEXT_MUTED
            self.active_prod_stock_lbl.configure(
                text=stock_txt,
                text_color=stock_color
            )
        if hasattr(self, "active_prod_sub"):
            self.active_prod_sub.configure(
                text=f"Precio Base: {p.formatted_price_base}   •   {stock_txt}"
            )

    def _get_top_frequent_products(self) -> List[Product]:
        """Fetch the top 5 most frequently sold products from sales history.
        Falls back to default popular cuts if fewer than 5 have sales recorded.
        """
        top_prods: List[Product] = []
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT p.id, p.barcode, p.name, p.category_id, c.name as category_name,
                           p.sale_type, p.price_base, p.cost, p.iva, p.unit_measure,
                           p.stock, p.min_stock,
                           COUNT(si.id) as times_sold,
                           SUM(si.quantity) as total_qty
                    FROM products p
                    JOIN categories c ON p.category_id = c.id
                    JOIN sale_items si ON p.id = si.product_id
                    GROUP BY p.id
                    ORDER BY times_sold DESC, total_qty DESC
                    LIMIT 5
                """)
                rows = cursor.fetchall()
                for r in rows:
                    top_prods.append(ProductModel._row_to_product(r))

                if len(top_prods) < 5:
                    existing_ids = {p.id for p in top_prods}
                    default_cut_names = ["Hamburguesa Clásica", "Hamburguesa Doble", "Perro Caliente", "Salchipapa", "Papas Francesas"]
                    for dname in default_cut_names:
                        if len(top_prods) >= 5:
                            break
                        matches = ProductModel.search(conn, dname)
                        for m in matches:
                            if m.id not in existing_ids:
                                top_prods.append(m)
                                existing_ids.add(m.id)
                                break

                if len(top_prods) < 5:
                    existing_ids = {p.id for p in top_prods}
                    all_prods = ProductModel.get_all(conn)
                    for ap in all_prods:
                        if ap.id not in existing_ids:
                            top_prods.append(ap)
                            existing_ids.add(ap.id)
                            if len(top_prods) >= 5:
                                break
        except Exception as e:
            logging.error("Error fetching frequent products: %s", e)

        return top_prods[:5]

    def _render_frequent_products(self) -> None:
        """Render dynamic top 5 best-selling product pills with intelligent abbreviations."""
        if not hasattr(self, "cuts_grid") or self.cuts_grid is None:
            return

        for w in self.cuts_grid.winfo_children():
            w.destroy()

        prods = self._get_top_frequent_products()
        for c in range(5):
            self.cuts_grid.grid_columnconfigure(c, weight=1, uniform="cut_col")

        for col_idx in range(5):
            if col_idx < len(prods):
                p = prods[col_idx]
                disp_name = abbreviate_product_name(p.name)
                btn = ctk.CTkButton(
                    self.cuts_grid,
                    text=disp_name,
                    height=28,
                    fg_color="#111624",
                    border_color="#222D42",
                    border_width=1,
                    hover_color="#182033",
                    text_color="#CBD5E1",
                    font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                    corner_radius=6,
                    cursor="hand2",
                    command=lambda prod=p: self._on_quick_cut_click(prod)
                )
                btn.grid(row=0, column=col_idx, padx=2, sticky="ew")
            else:
                lbl = ctk.CTkLabel(
                    self.cuts_grid,
                    text="--",
                    height=28,
                    font=ctk.CTkFont(family="Segoe UI", size=10),
                    text_color="#475569"
                )
                lbl.grid(row=0, column=col_idx, padx=2, sticky="ew")

    def _on_barcode_enter(self) -> None:
        code = self.barcode_entry.get().strip()
        if not code:
            return
        self.scanner_listener.reset()

        with get_db_connection() as conn:
            product = ProductModel.get_by_barcode_or_id(conn, code)
            if not product:
                # Try search by name keyword
                matches = ProductModel.search(conn, code)
                if matches:
                    product = matches[0]

        if product:
            sound_manager.play_barcode()
            self._select_product(product)
            self._focus_qty_entry()
        else:
            sound_manager.play_warning()
            messagebox.showwarning(
                "Producto No Encontrado",
                f"No se encontró ningún producto con código o nombre: '{code}'",
                parent=self
            )

    def _on_dropdown_product_selected(self, choice: str) -> None:
        if choice == self.CATALOG_PLACEHOLDER or choice not in self._catalog_map:
            return
        prod = self._catalog_map.get(choice)
        if prod:
            self._select_product(prod)
            self._focus_qty_entry()

    def _on_quick_cut_click(self, target: Any) -> None:
        if isinstance(target, Product):
            self._select_product(target)
            self._focus_qty_entry()
            return

        kw = str(target).lower().strip()
        synonyms = {
            "carne molida": ["carne molida", "molida"],
            "pechuga": ["pechuga", "pollo"],
            "chuleta": ["chuleta", "cerdo"],
            "costilla": ["costilla"],
            "lomo fino": ["lomo fino", "lomo"],
        }
        search_terms = synonyms.get(kw, [kw])

        # 1. Search in loaded catalog map
        for term in search_terms:
            for prod in self._catalog_map.values():
                if term in prod.name.lower():
                    self._select_product(prod)
                    self._focus_qty_entry()
                    return

        # 2. Search in database
        with get_db_connection() as conn:
            for term in search_terms:
                matches = ProductModel.search(conn, term)
                if matches:
                    self._select_product(matches[0])
                    self._focus_qty_entry()
                    return

    def _on_unit_change(self, val: str) -> None:
        self._on_unit_segment_change(val)

    def _on_unit_segment_change(self, val: str) -> None:
        if not self.active_product:
            return
        old_unit = self.current_unit
        new_unit = val
        self.current_unit = new_unit
        self.unit_disp_lbl.configure(text=new_unit)

        # Smart unit conversion on displayed quantity (only for PESO)
        if self.active_product.sale_type == "PESO":
            try:
                curr_q = float(self.quantity_var.get().replace(",", ".").strip() or "1")
                if old_unit == "kg" and new_unit == "lb":
                    curr_q = curr_q * 2.0
                elif old_unit == "kg" and new_unit == "g":
                    curr_q = curr_q * 1000.0
                elif old_unit == "lb" and new_unit == "kg":
                    curr_q = curr_q / 2.0
                elif old_unit == "lb" and new_unit == "g":
                    curr_q = curr_q * 500.0
                elif old_unit == "g" and new_unit == "kg":
                    curr_q = curr_q / 1000.0
                elif old_unit == "g" and new_unit == "lb":
                    curr_q = curr_q / 500.0

                if new_unit == "g":
                    self.quantity_var.set(f"{curr_q:.0f}")
                else:
                    self.quantity_var.set(f"{curr_q:.2f}")
            except Exception:
                pass

        self._update_item_calculations()

    def _read_scale_live(self) -> None:
        """Deprecated: hardware scale removed for XL Burguer."""
        pass

    def _on_qty_keypress(self) -> None:
        if getattr(self, "_is_fixed_qty", False):
            return
        self._is_initial_qty = False
        self._update_item_calculations()

    def _on_keypad_press(self, key: str) -> None:
        if getattr(self, "_is_fixed_qty", False):
            # User cannot edit quantity for fixed package products (e.g. wine 750 ml)
            return

        curr = self.quantity_var.get().strip()
        if curr == "-":
            curr = ""
            self._is_initial_qty = True

        if key == "C":
            self.quantity_var.set("0")
            self._is_initial_qty = False
        elif key == "⌫":
            if len(curr) > 1:
                self.quantity_var.set(curr[:-1])
            else:
                self.quantity_var.set("0")
            self._is_initial_qty = False
        elif key == "+1":
            try:
                curr_val = int(float(curr)) if curr and curr != "-" else 0
                self.quantity_var.set(str(curr_val + 1))
            except Exception:
                self.quantity_var.set("1")
            self._is_initial_qty = False
        elif "Unid" in key or key == "± Unid":
            try:
                q = float(self.quantity_var.get().replace(",", ".").strip() or "0")
                self.quantity_var.set(str(int(q + 1)))
            except Exception:
                self.quantity_var.set("1")
            self._is_initial_qty = False
            return
        else:
            # Number or decimal point
            if self._is_initial_qty:
                if key == ".":
                    self.quantity_var.set("0.")
                else:
                    self.quantity_var.set(key)
                self._is_initial_qty = False
            else:
                if key == "." and "." in curr:
                    return
                if curr == "0" and key != ".":
                    self.quantity_var.set(key)
                else:
                    self.quantity_var.set(curr + key)

        self._update_item_calculations()

    def _set_active_discount(self, pct: float) -> None:
        self.active_discount_pct = max(0.0, min(100.0, float(pct)))
        if hasattr(self, "disc_btn_pills"):
            for p_val, btn in self.disc_btn_pills.items():
                if int(self.active_discount_pct) == p_val:
                    btn.configure(fg_color="#059669", border_color="#10B981", text_color="#FFFFFF")
                else:
                    btn.configure(fg_color="#111624", border_color="#222D42", text_color="#94A3B8")
            if hasattr(self, "custom_disc_btn"):
                is_custom = int(self.active_discount_pct) not in self.disc_btn_pills
                if is_custom and self.active_discount_pct > 0:
                    self.custom_disc_btn.configure(text=f"{int(self.active_discount_pct)}%", image=None, fg_color="#059669", border_color="#10B981", text_color="#FFFFFF")
                else:
                    self.custom_disc_btn.configure(text="Otro", image=None, fg_color="#111624", border_color="#222D42", text_color="#94A3B8")
        self._update_item_calculations()

    def _open_custom_discount_active(self) -> None:
        if not self.active_product:
            messagebox.showwarning("Atención", "Seleccione un producto para aplicar descuento.", parent=self)
            return
        try:
            q_str = self.quantity_var.get().replace(",", ".").strip()
            qty = float(q_str) if q_str else 1.0
            tot = calculate_item_price(self.active_product.price_base, qty, self.current_unit, self.active_product.sale_type)
        except Exception:
            tot = self.active_product.price_base

        ProductDiscountModal(
            parent=self,
            product_name=self.active_product.name,
            original_price=tot,
            current_discount_pct=self.active_discount_pct,
            on_confirm_callback=self._set_active_discount
        )

    def _open_cart_item_discount(self, index: int) -> None:
        if 0 <= index < len(self.cart_items):
            item = self.cart_items[index]
            def _apply(pct: float):
                item.apply_discount(pct)
                # If another line item exists with same product, same unit, and same discount, merge them
                duplicate_match = next(
                    (it for it in self.cart_items
                     if it is not item
                     and it.product_id == item.product_id
                     and it.unit_selected == item.unit_selected
                     and round(it.discount_percent, 1) == round(item.discount_percent, 1)),
                    None
                )
                if duplicate_match:
                    duplicate_match.quantity += item.quantity
                    base_tot = calculate_item_price(
                        duplicate_match.price_base,
                        duplicate_match.quantity,
                        duplicate_match.unit_selected,
                        duplicate_match.sale_type
                    )
                    duplicate_match.original_price = base_tot
                    duplicate_match.apply_discount(duplicate_match.discount_percent)
                    self.cart_items.remove(item)
                self._render_cart()
                sound_manager.play_added()

            ProductDiscountModal(
                parent=self,
                product_name=item.product_name,
                original_price=item.original_price,
                current_discount_pct=item.discount_percent,
                on_confirm_callback=_apply
            )

    def _update_item_calculations(self) -> None:
        if not self.active_product:
            self.item_subtotal_var.set("COP $ --")
            return

        try:
            q_str = self.quantity_var.get().replace(",", ".").strip()
            if not q_str or q_str == "-":
                self.item_subtotal_var.set("COP $ --")
                return
            qty = float(q_str)
            tot = calculate_item_price(self.active_product.price_base, qty, self.current_unit, self.active_product.sale_type)
            disc_pct = getattr(self, "active_discount_pct", 0.0)
            if disc_pct > 0:
                disc_amt = round(tot * (disc_pct / 100.0))
                net = max(0.0, tot - disc_amt)
                self.item_subtotal_var.set(f"{format_currency(net)} (-{int(disc_pct)}%)")
            else:
                self.item_subtotal_var.set(format_currency(tot))
        except Exception:
            self.item_subtotal_var.set("COP $ --")

    def _add_active_product_to_cart(self) -> None:
        if not self.active_product:
            messagebox.showwarning("Atención", "Seleccione un producto para agregar a la venta.", parent=self)
            return

        try:
            q_str = self.quantity_var.get().replace(",", ".").strip()
            qty = float(q_str) if q_str else 0.0
            if qty <= 0:
                raise ValueError("La cantidad o peso debe ser superior a cero.")

            # Validate product stock in database / active product
            if self.active_product.stock <= 0:
                raise ValueError(
                    f"El producto '{self.active_product.name}' está agotado (Stock: 0). "
                    f"No se puede agregar a la venta."
                )

            new_req_base = convert_quantity_to_base(qty, self.current_unit, self.active_product.sale_type)

            # Sum total stock already reserved in cart across ALL line items of this product
            current_cart_base = sum(
                it.base_stock_deduction
                for it in self.cart_items
                if it.product_id == self.active_product.id
            )

            total_req_base = current_cart_base + new_req_base
            if total_req_base > self.active_product.stock:
                remaining_base = max(0.0, self.active_product.stock - current_cart_base)
                if self.active_product.sale_type == "PESO":
                    tot_s = self.active_product.formatted_stock
                    in_cart_s = f"{current_cart_base / 1000.0:.2f} kg" if current_cart_base >= 1000 else f"{current_cart_base:.0f} g"
                    rem_s = f"{remaining_base / 1000.0:.2f} kg" if remaining_base >= 1000 else f"{remaining_base:.0f} g"
                    req_s = f"{new_req_base / 1000.0:.2f} kg" if new_req_base >= 1000 else f"{new_req_base:.0f} g"
                else:
                    tot_s = f"{int(self.active_product.stock)} und"
                    in_cart_s = f"{int(current_cart_base)} und"
                    rem_s = f"{int(remaining_base)} und"
                    req_s = f"{int(new_req_base)} und"

                if current_cart_base > 0:
                    raise ValueError(
                        f"Stock insuficiente para '{self.active_product.name}'.\n\n"
                        f"• Stock total en inventario: {tot_s}\n"
                        f"• Ya en el carrito: {in_cart_s}\n"
                        f"• Disponible restante: {rem_s}\n\n"
                        f"No es posible agregar {req_s} adicionales."
                    )
                else:
                    raise ValueError(
                        f"Stock insuficiente para '{self.active_product.name}'.\n\n"
                        f"• Stock disponible: {tot_s}\n\n"
                        f"No es posible agregar {req_s}."
                    )

            tot = calculate_item_price(self.active_product.price_base, qty, self.current_unit, self.active_product.sale_type)
            disc_pct = round(getattr(self, "active_discount_pct", 0.0), 1)

            # Consolidate ONLY if the same product, same unit, AND same discount percentage already exists in cart
            existing_item = next(
                (it for it in self.cart_items
                 if it.product_id == self.active_product.id
                 and it.unit_selected == self.current_unit
                 and round(it.discount_percent, 1) == disc_pct),
                None
            )

            if existing_item:
                existing_item.quantity += qty
                base_tot = calculate_item_price(
                    self.active_product.price_base,
                    existing_item.quantity,
                    self.current_unit,
                    self.active_product.sale_type
                )
                existing_item.original_price = base_tot
                existing_item.apply_discount(disc_pct)
            else:
                item = CartItem(
                    product_id=self.active_product.id,
                    product_name=self.active_product.name,
                    category_id=self.active_product.category_id,
                    category_name=self.active_product.category_name,
                    sale_type=self.active_product.sale_type,
                    quantity=qty,
                    unit_selected=self.current_unit,
                    price_base=self.active_product.price_base,
                    total_price=tot,
                    original_price=tot,
                    discount_percent=disc_pct
                )
                if disc_pct > 0:
                    item.apply_discount(disc_pct)
                self.cart_items.append(item)

            self._set_active_discount(0.0)
            self._render_cart()
            sound_manager.play_added()

            # Reset ready for next product
            self._is_initial_qty = True
            if self.active_product.sale_type == "PESO":
                self.quantity_var.set("1.00")
            elif getattr(self, "_is_fixed_qty", False):
                pkg = self.active_product.fixed_package_info
                if pkg:
                    self.quantity_var.set(str(int(pkg[0]) if pkg[0].is_integer() else pkg[0]))
            else:
                self.quantity_var.set("1")
            self._update_item_calculations()
            self._focus_barcode_entry()

        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    # ──────────────────────────────────────────────────────────────────────────
    # CART RENDERING & MANAGEMENT
    # ──────────────────────────────────────────────────────────────────────────
    def _render_cart(self) -> None:
        for w in self.cart_scroll.winfo_children():
            w.destroy()

        subtotal = 0.0

        if not self.cart_items:
            empty_box = ctk.CTkFrame(self.cart_scroll, fg_color="transparent")
            empty_box.pack(pady=60)

            ctk.CTkLabel(
                empty_box,
                text="TICKET VACÍO",
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color=DarkTheme.TEXT_MUTED
            ).pack()

            ctk.CTkLabel(
                empty_box,
                text="Seleccione un producto a la izquierda para agregarlo a la canasta.",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=self._TEXT_FAINT
            ).pack(pady=4)
        else:
            del_img = get_ctk_icon("xmark_red", size=(16, 16))
            for idx, item in enumerate(self.cart_items):
                subtotal += item.total_price

                row_bg = "#0B0F1D" if (idx % 2 == 0) else "#111624"
                row_frame = ctk.CTkFrame(self.cart_scroll, fg_color=row_bg, corner_radius=6, height=36)
                row_frame.pack(fill="x", pady=2)

                row_frame.grid_columnconfigure(0, weight=1)
                row_frame.grid_columnconfigure(1, weight=0)
                row_frame.grid_columnconfigure(2, weight=0)
                row_frame.grid_columnconfigure(3, weight=0)
                row_frame.grid_columnconfigure(4, weight=0)
                row_frame.grid_columnconfigure(5, weight=0)

                if item.sale_type == "PESO":
                    qty_display = f"{item.quantity:.2f} {item.unit_selected}"
                elif item.unit_selected == "ml":
                    bottles = int(round(item.quantity / 750.0)) if item.quantity >= 750 else 1
                    qty_display = f"{bottles}x 750 ml" if bottles > 1 else f"{int(item.quantity)} ml"
                else:
                    qty_display = f"{int(item.quantity)} und"

                price_base_disp = f"${int(item.price_base)}/g" if item.sale_type == "PESO" else f"${int(item.price_base)}/{item.unit_selected}"

                # Col 0: Producto (absorbs remaining space, left-aligned)
                prod_title = item.product_name
                has_discount = item.discount_percent > 0
                if has_discount:
                    prod_title = f"{item.product_name} (-{int(item.discount_percent)}%)"

                ctk.CTkLabel(
                    row_frame,
                    text=prod_title,
                    anchor="w",
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold" if has_discount else "normal"),
                    text_color="#34D399" if has_discount else "#E2E8F0"
                ).grid(row=0, column=0, sticky="ew", padx=(12, 4), pady=4)

                # Col 1: Unidad (centered)
                ctk.CTkLabel(
                    row_frame,
                    text=item.unit_selected,
                    width=44,
                    anchor="center",
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    text_color="#CBD5E1"
                ).grid(row=0, column=1, sticky="", padx=2, pady=4)

                # Col 2: Cantidad (centered)
                ctk.CTkLabel(
                    row_frame,
                    text=qty_display,
                    width=68,
                    anchor="center",
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    text_color="#CBD5E1"
                ).grid(row=0, column=2, sticky="", padx=2, pady=4)

                # Col 3: Precio Base (right-aligned)
                ctk.CTkLabel(
                    row_frame,
                    text=price_base_disp,
                    width=78,
                    anchor="e",
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    text_color="#CBD5E1"
                ).grid(row=0, column=3, sticky="e", padx=(2, 6), pady=4)

                # Col 4: Subtotal (right-aligned)
                ctk.CTkLabel(
                    row_frame,
                    text=format_currency_short(item.total_price),
                    width=82,
                    anchor="e",
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold" if has_discount else "normal"),
                    text_color="#10B981" if has_discount else "#E2E8F0"
                ).grid(row=0, column=4, sticky="e", padx=(2, 6), pady=4)

                # Col 5: Acciones (Descuento + Eliminar)
                actions_cell = ctk.CTkFrame(row_frame, fg_color="transparent")
                actions_cell.grid(row=0, column=5, sticky="e", padx=(2, 4), pady=4)

                disc_txt = f"-{int(item.discount_percent)}%" if has_discount else ""
                disc_bg = "#064E3B" if has_discount else "#111624"
                disc_fg = "#34D399" if has_discount else "#94A3B8"
                disc_border = "#059669" if has_discount else "#222D42"

                disc_pct_ico = get_ctk_icon("percent-solid-full", size=(12, 12)) if not has_discount else None
                disc_btn = ctk.CTkButton(
                    actions_cell,
                    image=disc_pct_ico,
                    text=disc_txt,
                    width=34,
                    height=26,
                    fg_color=disc_bg,
                    border_color=disc_border,
                    border_width=1,
                    hover_color="#0E291F",
                    text_color=disc_fg,
                    font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                    corner_radius=4,
                    cursor="hand2",
                    command=lambda i=idx: self._open_cart_item_discount(i)
                )
                disc_btn.pack(side="left", padx=(0, 4))

                del_btn = ctk.CTkButton(
                    actions_cell,
                    image=del_img,
                    text="" if del_img else "×",
                    width=26,
                    height=26,
                    fg_color="transparent",
                    hover_color="#331317",
                    border_width=0,
                    corner_radius=4,
                    cursor="hand2",
                    command=lambda i=idx: self._remove_from_cart(i)
                )
                del_btn.pack(side="left")

        # Update summary labels
        total_discount = sum(it.discount_amount for it in self.cart_items)
        if total_discount > 0:
            if hasattr(self, "discount_row") and hasattr(self, "giant_total_box"):
                self.discount_row.pack(fill="x", padx=16, pady=(0, 2), before=self.giant_total_box)
            if hasattr(self, "discount_disp_lbl"):
                self.discount_disp_lbl.configure(text=f"-{format_currency(total_discount)}")
        else:
            if hasattr(self, "discount_row"):
                self.discount_row.pack_forget()

        self.subtotal_disp_lbl.configure(text=format_currency(subtotal + total_discount))
        self.total_disp_lbl.configure(text=format_currency(subtotal))
        count = len(self.cart_items)
        prod_word = "producto" if count == 1 else "productos"
        self.item_count_lbl.configure(text=f"{count} {prod_word} en el carrito")

    def _remove_from_cart(self, index: int) -> None:
        if 0 <= index < len(self.cart_items):
            self.cart_items.pop(index)
            self._render_cart()

    def _clear_cart(self) -> None:
        if self.cart_items:
            if messagebox.askyesno("Limpiar Venta", "¿Desea vaciar el carrito actual?", parent=self):
                self.cart_items.clear()
                self._clear_customer()
                self.active_product = None
                if hasattr(self, "barcode_entry") and self.barcode_entry.winfo_exists():
                    self.barcode_entry.delete(0, "end")
                self._render_active_product()
                self._render_cart()
                self._focus_barcode_entry()

    # ──────────────────────────────────────────────────────────────────────────
    # CHECKOUT & TICKET DISPATCH
    # ──────────────────────────────────────────────────────────────────────────
    def _on_checkout_click(self) -> None:
        if not self.cart_items:
            messagebox.showwarning(
                "Carrito Vacío",
                "Agregue al menos un producto al carrito antes de cobrar.",
                parent=self
            )
            return

        total = sum(i.total_price for i in self.cart_items)
        CheckoutModal(
            parent=self,
            total_amount=total,
            on_complete_sale_callback=self._process_checkout,
            customer=self.current_customer
        )

    def _process_checkout(
        self,
        cash_received: float,
        payment_method: str = "EFECTIVO",
        customer_id: Optional[int] = None
    ) -> None:
        user_id = self.current_user.id if self.current_user else 1
        # Always synchronize fresh user info from DB
        try:
            with get_db_connection() as conn:
                from models.user import UserModel
                fresh_user = UserModel.get_by_id(conn, user_id)
                if fresh_user:
                    self.current_user = fresh_user
        except Exception:
            pass

        cashier_name = self.current_user.full_name if (self.current_user and self.current_user.full_name) else "Cajero XL Burguer"
        target_customer_id = customer_id or (self.current_customer.id if self.current_customer else None)

        try:
            with get_db_connection() as conn:
                sale_detail = SaleModel.process_sale(
                    conn=conn,
                    user_id=user_id,
                    cart_items=self.cart_items,
                    cash_received=cash_received,
                    customer_id=target_customer_id,
                    payment_method=payment_method
                )

            # Generate formatted receipt with customer, exact operator, and payment method
            resolved_cashier = sale_detail.user_name or cashier_name or "Cajero XL Burguer"
            ticket_text = format_ticket(
                invoice_number=sale_detail.invoice_number,
                timestamp=sale_detail.timestamp,
                cashier_name=resolved_cashier,
                items=sale_detail.items,
                subtotal=sale_detail.subtotal,
                total=sale_detail.total,
                cash_received=sale_detail.cash_received,
                cash_change=sale_detail.cash_change,
                customer_name=sale_detail.customer_name,
                customer_document=sale_detail.customer_document,
                payment_method=sale_detail.payment_method
            )

            # Reset cart and refresh product stock
            sound_manager.play_sale_success()
            try:
                top = self.winfo_toplevel()
                if hasattr(top, "mark_dirty"):
                    top.mark_dirty("inventory", "stats", "users")
            except Exception:
                pass
            self.cart_items.clear()
            self._clear_customer()
            self._render_cart()
            self.active_product = None
            if hasattr(self, "barcode_entry") and self.barcode_entry.winfo_exists():
                self.barcode_entry.delete(0, "end")
            self._render_active_product()
            self.refresh_catalog()

            # Show on-screen thermal ticket modal
            TicketPreviewModal(
                parent=self,
                ticket_text=ticket_text,
                on_close_callback=self._focus_barcode_entry
            )

        except Exception as e:
            messagebox.showerror(
                "Fallo en la Venta",
                f"No se pudo completar la transacción:\n{e}",
                parent=self
            )

    # ──────────────────────────────────────────────────────────────────────────
    # KEYBOARD SHORTCUTS & HARDWARE SCANNER INTEGRATION
    # ──────────────────────────────────────────────────────────────────────────
    def _focus_customer_entry(self) -> None:
        if hasattr(self, "customer_doc_entry") and self.customer_doc_entry.winfo_exists():
            try:
                self.customer_doc_entry.focus_set()
                self.customer_doc_entry.select_range(0, 'end')
            except Exception:
                pass
        else:
            self._focus_barcode_entry()

    def _focus_barcode_entry(self) -> None:
        if hasattr(self, "barcode_entry") and self.barcode_entry.winfo_exists():
            try:
                self.barcode_entry.focus_set()
                self.barcode_entry.select_range(0, 'end')
            except Exception:
                pass

    def _focus_product_selector(self) -> None:
        if hasattr(self, "product_selector") and self.product_selector.winfo_exists():
            try:
                if hasattr(self.product_selector, "_entry"):
                    self.product_selector._entry.focus_set()
                else:
                    self.product_selector.focus_set()
            except Exception:
                pass

    def _focus_qty_entry(self) -> None:
        if hasattr(self, "qty_entry") and self.qty_entry.winfo_exists():
            try:
                self.qty_entry.focus_set()
                self.qty_entry.select_range(0, 'end')
            except Exception:
                pass

    def _focus_add_item_btn(self) -> None:
        if hasattr(self, "add_item_btn") and self.add_item_btn.winfo_exists():
            try:
                self.add_item_btn.focus_set()
            except Exception:
                pass

    def _focus_checkout_btn(self) -> None:
        if hasattr(self, "checkout_btn") and self.checkout_btn.winfo_exists():
            try:
                self.checkout_btn.focus_set()
            except Exception:
                pass

    def _on_global_key_press(self, event) -> None:
        if not self.winfo_ismapped():
            return

        focused = self.focus_get()
        if focused:
            try:
                if focused.winfo_toplevel() != self.winfo_toplevel():
                    return
            except Exception:
                pass

        keysym = getattr(event, "keysym", "")
        char = getattr(event, "char", "")
        state = getattr(event, "state", 0)
        is_ctrl = bool(state & 0x0004)  # Control mask in Tkinter

        # F12 or Ctrl+Enter: Cobrar (Checkout)
        if keysym == "F12" or (is_ctrl and keysym in ("Return", "KP_Enter")):
            self._on_checkout_click()
            return

        # F1: Enfocar cédula / NIT de cliente
        if keysym == "F1":
            self._focus_customer_entry()
            return

        # F2: Enfocar barra de código / ID de producto
        if keysym == "F2":
            self._focus_barcode_entry()
            return

        # F3: Consumidor Final rápido
        if keysym == "F3":
            self._set_anonymous_customer()
            return

        # F4: Leer Báscula en tiempo real
        if keysym == "F4":
            self._read_scale_live()
            return

        # F5: Desplegar selector de productos
        if keysym == "F5":
            self._focus_product_selector()
            try:
                self.product_selector._open_dropdown_menu()
            except Exception:
                pass
            return

        # Ctrl+D or F6: Descuento personalizado en producto activo
        if (is_ctrl and keysym.lower() == "d") or keysym == "F6":
            self._open_custom_discount_active()
            return

        # Ctrl+U: Alternar unidad de peso (kg -> lb -> g)
        if is_ctrl and keysym.lower() == "u":
            if hasattr(self, "unit_toggle"):
                self.unit_toggle.cycle_next()
            return

        # Quick discount shortcuts: Ctrl+1 (0%), Ctrl+2 (10%), Ctrl+3 (20%), Ctrl+4 (50%)
        if is_ctrl and keysym in ("1", "exclam"):
            self._set_active_discount(0.0)
            return
        if is_ctrl and keysym in ("2", "at"):
            self._set_active_discount(10.0)
            return
        if is_ctrl and keysym in ("3", "numbersign"):
            self._set_active_discount(20.0)
            return
        if is_ctrl and keysym in ("4", "dollar"):
            self._set_active_discount(50.0)
            return

        # Ctrl+Delete: Vaciar carrito
        if is_ctrl and keysym == "Delete":
            self._clear_cart()
            return

        # Delete: Eliminar último producto si no está editando texto
        if keysym == "Delete":
            if not isinstance(focused, (ctk.CTkEntry, tk.Entry, ctk.CTkTextbox, tk.Text)):
                if self.cart_items:
                    self._remove_from_cart(len(self.cart_items) - 1)
                return

        # Hardware scanner HID listener
        self.scanner_listener.handle_key_press(char, keysym)

    def _on_scanner_barcode_scanned(self, code: str) -> None:
        if not self.winfo_ismapped():
            return

        focused = self.focus_get()
        if focused:
            try:
                if focused.winfo_toplevel() != self.winfo_toplevel():
                    return
            except Exception:
                pass

        if hasattr(self, "barcode_entry") and self.barcode_entry.winfo_exists():
            self.barcode_entry.delete(0, "end")

        with get_db_connection() as conn:
            product = ProductModel.get_by_barcode_or_id(conn, code)

        if product:
            sound_manager.play_barcode()
            self._select_product(product)
            self._focus_qty_entry()
        else:
            sound_manager.play_warning()
            messagebox.showwarning(
                "Producto No Encontrado",
                f"Código escaneado no encontrado: '{code}'",
                parent=self
            )
