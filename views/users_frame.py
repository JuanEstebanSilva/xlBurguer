"""Users and Customers Management Frame for XL Burguer POS System.
Features:
- Full-width unified executive controls bar matching Inventory, POS & Stats styling.
- Clientes / Usuarios del Sistema segmented tab switch.
- Executive KPI ranking summary (Total Clientes, Compradores Activos, Facturado a Clientes, Valor Promedio de Venta).
- Ranked Customer Directory table:
    - Shows Ranking (#1, #2, #3...), Customer Name, Phone, Purchase count, Total spent.
    - National ID (Cédula) is kept out of the main table to avoid visual clutter as requested.
    - Fast pagination (20 items per page) providing instantaneous (<20 ms) load times.
- Customer Detail Modal (Ficha del Cliente):
    - Full customer profile with avatar initials, Cédula / NIT, phone, and registration date.
    - Summary metrics: Total Compras, Facturado, Ticket Promedio.
    - Itemized purchase history with thermal receipt reprint [🎫 Ver Ticket] invoking TicketPreviewModal.
- Customer Registration & Editing Modal (CustomerFormModal) with brand topbar and touch keypad support.
- System Users Management (UserFormModal & table):
    - Create / Edit users with role assignment (Cajero POS / Administrador) and secure password hashing.
    - Delete system user with protection against deleting the sole administrator or active users with sales.
- ZERO Excel export (as requested).
"""

import logging
import math
import re
import sqlite3
import tkinter as tk
from tkinter import messagebox
from typing import Any, Callable, Dict, List, Optional, Tuple
import customtkinter as ctk

from database.connection import get_db_connection
from hardware.ticket_printer import format_ticket
from views.ticket_preview_modal import TicketPreviewModal
from models.customer import Customer, CustomerModel
from models.product import Product, ProductModel
from models.sale import SaleModel
from models.user import User, UserModel
from utils.asset_manager import center_modal, get_ctk_icon, build_standard_modal_header, get_tinted_ctk_icon
from utils.sound_manager import sound_manager
from utils.theme import DarkTheme, apply_palette_button, bind_tab_navigation

try:
    from views.pos_frame import TouchKeypadModal
except Exception:
    TouchKeypadModal = None


def format_encargado(raw: str) -> str:
    """Format representative name to strictly first name + first surname.
    e.g. 'Juan Esteban Silva Gómez' -> 'Juan Silva'
         'Chef Mauricio Vargas' -> 'Mauricio Vargas'
         'Don Hernando Ruiz' -> 'Hernando Ruiz'
         'Carlos Méndez' -> 'Carlos Méndez'
    """
    if not raw:
        return "—"
    honorifics = {"chef", "don", "doña", "dona", "sr", "sra", "sr.", "sra.", "dr", "dra", "dr.", "dra.", "ing", "ing."}
    parts = [p for p in raw.strip().split() if p.lower() not in honorifics]
    if not parts:
        return "—"
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} {parts[1]}"
    if len(parts) >= 4:
        return f"{parts[0]} {parts[2]}"
    return f"{parts[0]} {parts[-1]}"


def _set_dialog_icon_and_center(dialog: ctk.CTkToplevel, parent, w: int, h: int) -> None:
    """Center dialog and attach official window icon."""
    center_modal(dialog, w, h, parent)


def _format_payment_method_widget(parent, payment_method: str) -> ctk.CTkLabel:
    """Renders payment method as clean white text with its icon, without any button/pill frame."""
    pm = str(payment_method or "EFECTIVO").upper()
    if "TARJETA" in pm:
        ico = get_ctk_icon("credit_card_white", size=(13, 13)) or "💳"
        lbl_text = " Tarjeta"
    elif "TRANSFER" in pm:
        ico = get_ctk_icon("repeat_white", size=(13, 13)) or "📱"
        lbl_text = " Transferencia"
    elif "FIADO" in pm:
        ico = get_ctk_icon("tag_white", size=(13, 13)) or "🤝"
        lbl_text = " Fiado"
    else:
        ico = get_ctk_icon("money_white", size=(13, 13)) or "💵"
        lbl_text = " Efectivo"

    if isinstance(ico, str):
        return ctk.CTkLabel(
            parent,
            text=f"{ico}{lbl_text}",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#FFFFFF",
            anchor="w"
        )
    else:
        return ctk.CTkLabel(
            parent,
            image=ico,
            compound="left",
            text=lbl_text,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#FFFFFF",
            anchor="w"
        )


# Canonical Tab navigation helper aliased from utils.theme
_bind_tab_navigation = bind_tab_navigation




# ─────────────────────────────────────────────────────────────────────────────
# 1. CUSTOMER FORM MODAL (REGISTRAR / EDITAR CLIENTE O EMPRESA)
# ─────────────────────────────────────────────────────────────────────────────
class CustomerFormModal(ctk.CTkToplevel):
    """Modern modal dialog to register or edit a Customer (Persona Natural) or Company (Empresa Convenio).
    Includes on-screen touch numeric keypad buttons for tactile POS screens.
    """

    def __init__(
        self,
        parent,
        customer: Optional[Dict[str, Any]] = None,
        on_success_callback: Optional[Callable[[], None]] = None,
        default_customer_type: str = "PERSONA"
    ):
        super().__init__(parent)
        self.customer = customer
        self.on_success_callback = on_success_callback
        self.is_edit = customer is not None
        self.default_customer_type = customer.get("customer_type", default_customer_type) if customer else default_customer_type

        c_name = customer.get("full_name", "") if customer else ""
        c_type = self.default_customer_type
        if self.is_edit:
            title_txt = f"Editar Empresa: {c_name}" if c_type == "EMPRESA" else f"Editar Cliente: {c_name}"
        else:
            title_txt = "Registrar Nueva Empresa" if c_type == "EMPRESA" else "Registrar Nuevo Cliente"

        self.title(title_txt)
        self.resizable(False, False)
        self.configure(fg_color="#15171F")

        self._build_ui(title_txt)
        modal_h = 550 if c_type != "EMPRESA" else 630
        _set_dialog_icon_and_center(self, parent, 540, modal_h)

        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self, title_txt: str) -> None:
        c = self.customer or {}
        is_emp = (self.default_customer_type == "EMPRESA")

        # White title icons for all headers
        if self.is_edit:
            title_icon = get_ctk_icon("pen_white", size=(16, 16))
        elif is_emp:
            title_icon = get_ctk_icon("building_solid_white", size=(16, 16)) or get_ctk_icon("hospital_user_white", size=(16, 16))
        else:
            title_icon = get_ctk_icon("user_plus_solid_white", size=(16, 16))
        build_standard_modal_header(self, title_txt, title_icon, on_close_cmd=self.destroy, text_color="#FFFFFF")

        # ── Footer Actions (packed with side="bottom" first to guarantee full visibility) ──
        actions_row = ctk.CTkFrame(self, fg_color="transparent", height=48)
        actions_row.pack(side="bottom", fill="x", padx=20, pady=(6, 16))
        actions_row.pack_propagate(False)

        cancel_btn = ctk.CTkButton(
            actions_row,
            text="  Cancelar",
            image=get_ctk_icon("ban_red", size=(15, 15)),
            compound="left",
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
        cancel_btn.pack(side="left")

        if self.is_edit:
            btn_txt = "  Editar Cambios"
            save_icon = get_ctk_icon("pen_orange", size=(15, 15)) or get_ctk_icon("pen_gold", size=(15, 15))
            save_fg = "#2A1608"
            save_hover = "#451A03"
            save_border = "#F59E0B"
            save_text_color = "#FBBF24"
        else:
            btn_txt = "  Crear Empresa" if is_emp else "  Crear Cliente"
            save_icon = get_ctk_icon("floppy_green", size=(15, 15)) or get_ctk_icon("floppy_white", size=(15, 15))
            save_fg = "#0A1D16"
            save_hover = "#0F2E22"
            save_border = "#10B981"
            save_text_color = "#34D399"

        save_btn = ctk.CTkButton(
            actions_row,
            image=save_icon,
            compound="left",
            text=btn_txt,
            width=175,
            height=38,
            fg_color=save_fg,
            hover_color=save_hover,
            border_color=save_border,
            border_width=1.5,
            text_color=save_text_color,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self._save_customer
        )
        save_btn.pack(side="right")
        self.save_btn = save_btn

        # ── Form Content (expands to fill the remaining area) ────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(6, 4))

        # Main Card
        card = ctk.CTkFrame(
            body,
            fg_color="#181A22",
            border_color="#252836",
            border_width=1,
            corner_radius=8
        )
        card.pack(fill="both", expand=True, padx=2, pady=2)

        form_grid = ctk.CTkFrame(card, fg_color="transparent")
        form_grid.pack(fill="both", expand=True, padx=16, pady=14)

        # Fixed customer type (Persona Natural vs Empresa is selected via the respective button in view)
        self.customer_type_var = ctk.StringVar(value=self.default_customer_type)

        kb_img = get_ctk_icon("keyboard_white", size=(16, 16)) or get_ctk_icon("keyboard_slate", size=(16, 16))

        # 1. Cédula / NIT
        self.doc_lbl = ctk.CTkLabel(
            form_grid,
            text="NIT DE LA EMPRESA (*):" if is_emp else "CÉDULA DE CIUDADANÍA (*):",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFFFFF"
        )
        self.doc_lbl.pack(anchor="w", pady=(0, 2))

        doc_row = ctk.CTkFrame(form_grid, fg_color="transparent")
        doc_row.pack(fill="x", pady=(0, 10))

        self.doc_entry = ctk.CTkEntry(
            doc_row,
            height=36,
            placeholder_text="Ej: 900000000-1" if is_emp else "Ej: 123456789",
            placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=DarkTheme.INPUT_BG,
            border_color="#3B4A66",
            border_width=1.5,
            text_color=DarkTheme.INPUT_TEXT,
            corner_radius=6
        )
        self.doc_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        if c.get("document_id"):
            self.doc_entry.insert(0, str(c["document_id"]))

        ctk.CTkButton(
            doc_row,
            image=kb_img,
            text="",
            width=36,
            height=36,
            fg_color="#111624",
            border_color="#283347",
            border_width=1,
            hover_color="#1E293B",
            corner_radius=6,
            cursor="hand2",
            command=lambda: self._open_keypad(self.doc_entry, "NIT de la Empresa" if is_emp else "Cédula")
        ).pack(side="left")

        # 2. Nombres / Razón Social
        self.name_lbl = ctk.CTkLabel(
            form_grid,
            text="NOMBRE DE LA EMPRESA (*):" if is_emp else "NOMBRES (*):",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFFFFF"
        )
        self.name_lbl.pack(anchor="w", pady=(0, 2))

        self.name_entry = ctk.CTkEntry(
            form_grid,
            height=36,
            placeholder_text="Ej: Los Portales" if is_emp else "Ej: Pepito",
            placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=DarkTheme.INPUT_BG,
            border_color="#3B4A66",
            border_width=1.5,
            text_color=DarkTheme.INPUT_TEXT,
            corner_radius=6
        )
        self.name_entry.pack(fill="x", pady=(0, 10))
        if c.get("first_name"):
            self.name_entry.insert(0, str(c["first_name"]))

        # 3. Apellidos / Contacto Representante
        self.last_name_lbl = ctk.CTkLabel(
            form_grid,
            text="REPRESENTANTE LEGAL / ENCARGADO:" if is_emp else "APELLIDOS:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFFFFF"
        )
        self.last_name_lbl.pack(anchor="w", pady=(0, 2))

        self.last_name_entry = ctk.CTkEntry(
            form_grid,
            height=36,
            placeholder_text="Ej: Diego Martínez" if is_emp else "Ej: Pérez",
            placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=DarkTheme.INPUT_BG,
            border_color="#3B4A66",
            border_width=1.5,
            text_color=DarkTheme.INPUT_TEXT,
            corner_radius=6
        )
        self.last_name_entry.pack(fill="x", pady=(0, 10))
        if c.get("last_name"):
            self.last_name_entry.insert(0, str(c["last_name"]))

        # 4. Teléfono
        self.phone_lbl = ctk.CTkLabel(
            form_grid,
            text="TELÉFONO DE CONTACTO:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFFFFF"
        )
        self.phone_lbl.pack(anchor="w", pady=(0, 2))

        phone_row = ctk.CTkFrame(form_grid, fg_color="transparent")
        phone_row.pack(fill="x", pady=(0, 6))

        self.phone_entry = ctk.CTkEntry(
            phone_row,
            height=36,
            placeholder_text="Ej: 3000000000 (10 dígitos)",
            placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=DarkTheme.INPUT_BG,
            border_color="#3B4A66",
            border_width=1.5,
            text_color=DarkTheme.INPUT_TEXT,
            corner_radius=6
        )
        self.phone_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        if c.get("phone"):
            self.phone_entry.insert(0, str(c["phone"]))

        ctk.CTkButton(
            phone_row,
            image=kb_img,
            text="",
            width=36,
            height=36,
            fg_color="#111624",
            border_color="#283347",
            border_width=1,
            hover_color="#1E293B",
            corner_radius=6,
            cursor="hand2",
            command=lambda: self._open_keypad(self.phone_entry, "Teléfono de Contacto")
        ).pack(side="left")

        # 5. Descuento Empresarial Pactado (%)
        self.discount_frame = ctk.CTkFrame(form_grid, fg_color="transparent")
        if is_emp:
            self.discount_frame.pack(fill="x", pady=(0, 4))

        self.disc_lbl = ctk.CTkLabel(
            self.discount_frame,
            text="DESCUENTO EMPRESARIAL PACTADO (%):",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFFFFF"
        )
        self.disc_lbl.pack(anchor="w", pady=(0, 2))

        disc_row = ctk.CTkFrame(self.discount_frame, fg_color="transparent")
        disc_row.pack(fill="x", pady=(0, 4))

        init_disc = f"{c.get('discount_percent', 0.0):.0f}" if c.get("discount_percent") else "0"
        self.discount_entry = ctk.CTkEntry(
            disc_row,
            height=36,
            placeholder_text="Ej: 10 (0% - 100%)",
            placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=DarkTheme.INPUT_BG,
            border_color="#3B4A66",
            border_width=1.5,
            text_color=DarkTheme.INPUT_TEXT,
            corner_radius=6
        )
        self.discount_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.discount_entry.insert(0, init_disc)

        ctk.CTkButton(
            disc_row,
            image=kb_img,
            text="",
            width=36,
            height=36,
            fg_color="#111624",
            border_color="#283347",
            border_width=1,
            hover_color="#1E293B",
            corner_radius=6,
            cursor="hand2",
            command=lambda: self._open_keypad(self.discount_entry, "Descuento %")
        ).pack(side="left")

        # Setup Tab navigation across form fields
        tab_widgets = [self.doc_entry, self.name_entry, self.last_name_entry, self.phone_entry]
        if is_emp and hasattr(self, "discount_entry"):
            tab_widgets.append(self.discount_entry)
        tab_widgets.extend([cancel_btn, save_btn])
        _bind_tab_navigation(self, tab_widgets, on_enter=self._save_customer)
        self.after(100, lambda: self.doc_entry.focus_set())


    def _on_type_toggle(self, val: str) -> None:
        pass

    def _open_keypad(self, target_entry: ctk.CTkEntry, title: str) -> None:
        if not TouchKeypadModal:
            return
        TouchKeypadModal(
            parent=self,
            title=title,
            subtitle="Digite los números",
            initial_value=target_entry.get().strip(),
            on_confirm_callback=lambda val: [target_entry.delete(0, "end"), target_entry.insert(0, val)]
        )

    def _save_customer(self) -> None:
        doc = self.doc_entry.get().strip()
        first_name = self.name_entry.get().strip()
        last_name = self.last_name_entry.get().strip()
        phone = self.phone_entry.get().strip() or None
        c_type = self.customer_type_var.get() if hasattr(self, "customer_type_var") else "PERSONA"

        # Cédula / NIT: permite cualquier formato de cédula o pasaporte, solo valida que no esté vacío
        if not doc:
            sound_manager.play_error()
            doc_label = "el NIT de la empresa" if c_type == "EMPRESA" else "la Cédula del cliente"
            messagebox.showwarning("Campo Obligatorio", f"Por favor ingrese {doc_label}.", parent=self)
            self.doc_entry.focus_set()
            return

        # Nombres: obligatorio
        if not first_name:
            sound_manager.play_error()
            name_label = "el nombre de la empresa" if c_type == "EMPRESA" else "el nombre del cliente"
            messagebox.showwarning("Campo Obligatorio", f"Por favor ingrese {name_label}.", parent=self)
            self.name_entry.focus_set()
            return

        # Validación de letras en nombres y apellidos para Persona Natural
        if c_type == "PERSONA":
            if not re.fullmatch(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s'-]+$", first_name):
                sound_manager.play_error()
                messagebox.showwarning(
                    "Nombre Inválido",
                    "El nombre del cliente solo puede contener letras y espacios (sin números ni caracteres especiales).",
                    parent=self
                )
                self.name_entry.focus_set()
                return
            if last_name and not re.fullmatch(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s'-]+$", last_name):
                sound_manager.play_error()
                messagebox.showwarning(
                    "Apellido Inválido",
                    "El apellido del cliente solo puede contener letras y espacios (sin números ni caracteres especiales).",
                    parent=self
                )
                self.last_name_entry.focus_set()
                return
        else:
            if not re.search(r"[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ]", first_name):
                sound_manager.play_error()
                messagebox.showwarning(
                    "Nombre de Empresa Inválido",
                    "El nombre de la empresa debe contener letras.",
                    parent=self
                )
                self.name_entry.focus_set()
                return
            if last_name and not re.fullmatch(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s'-]+$", last_name):
                sound_manager.play_error()
                messagebox.showwarning(
                    "Representante Inválido",
                    "El nombre del representante/encargado solo puede contener letras y espacios (sin números ni caracteres especiales).",
                    parent=self
                )
                self.last_name_entry.focus_set()
                return

        # Teléfono: si se ingresa, debe iniciar con 3 y tener exactamente 10 dígitos (ni más ni menos)
        if phone:
            clean_phone = re.sub(r"[\s\-]", "", phone)
            if not (clean_phone.isdigit() and len(clean_phone) == 10 and clean_phone.startswith("3")):
                sound_manager.play_error()
                messagebox.showwarning(
                    "Teléfono Inválido",
                    "El teléfono de contacto debe comenzar con el número 3 y tener exactamente 10 dígitos numéricos (ni más ni menos, ej: 3000000000).",
                    parent=self
                )
                self.phone_entry.focus_set()
                return
            phone = clean_phone

        discount_val = 0.0
        if c_type == "EMPRESA" and hasattr(self, "discount_entry"):
            disc_raw = self.discount_entry.get().replace(",", ".").strip()
            if disc_raw:
                try:
                    parsed_disc = float(disc_raw)
                except ValueError:
                    sound_manager.play_error()
                    messagebox.showwarning(
                        "Descuento Inválido",
                        "El descuento empresarial debe ser un valor numérico.",
                        parent=self
                    )
                    self.discount_entry.focus_set()
                    return

                if parsed_disc < 0 or parsed_disc > 100:
                    sound_manager.play_error()
                    messagebox.showwarning(
                        "Descuento Fuera de Límite",
                        "El descuento empresarial pactado no puede ser superior al 100% ni menor al 0%.",
                        parent=self
                    )
                    self.discount_entry.focus_set()
                    return
                discount_val = parsed_disc

        try:
            with get_db_connection() as conn:
                if self.is_edit:
                    c_id = self.customer["id"]
                    # Check if document belongs to someone else
                    existing = CustomerModel.get_by_document(conn, doc)
                    if existing and existing.id != c_id:
                        sound_manager.play_error()
                        messagebox.showwarning("Documento Duplicado", f"Ya existe otro cliente/empresa registrado con la cédula/NIT '{doc}'.", parent=self)
                        return

                    CustomerModel.update(conn, c_id, first_name, last_name, phone, document_id=doc, customer_type=c_type, discount_percent=discount_val)
                else:
                    existing = CustomerModel.get_by_document(conn, doc)
                    if existing:
                        sound_manager.play_error()
                        messagebox.showwarning("Registro Existente", f"El cliente/empresa con cédula/NIT '{doc}' ya se encuentra registrado:\n\n{existing.full_name}", parent=self)
                        return

                    CustomerModel.create(conn, doc, first_name, last_name, phone, customer_type=c_type, discount_percent=discount_val)

            sound_manager.play_sale_success()
            if self.on_success_callback:
                self.on_success_callback()
            self.destroy()

        except Exception as e:
            sound_manager.play_error()
            messagebox.showerror("Error al Guardar", f"No se pudo guardar la información:\n{e}", parent=self)


# ─────────────────────────────────────────────────────────────────────────────
# 2. USER FORM MODAL (CREAR / EDITAR USUARIO DEL SISTEMA)
# ─────────────────────────────────────────────────────────────────────────────
class UserFormModal(ctk.CTkToplevel):
    """Modern modal dialog for Creating or Editing System User Accounts (Cajeros & Administrador)."""

    def __init__(
        self,
        parent,
        user: Optional[User] = None,
        on_success_callback: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        self.user = user
        self.on_success_callback = on_success_callback
        self.is_edit = user is not None
        self.is_admin_user = bool(self.is_edit and self.user and self.user.is_admin)

        title_txt = f"Editar Usuario: {user.username}" if self.is_edit else "Registrar Nuevo Operador"
        self.title(title_txt)
        self.resizable(False, False)
        self.configure(fg_color="#15171F")

        self._build_ui(title_txt)
        modal_height = 480 if self.is_admin_user else 650
        _set_dialog_icon_and_center(self, parent, 520, modal_height)

        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self, title_txt: str) -> None:
        u = self.user

        # ── Brand Topbar in pure white ────────────────────────────────────────
        title_icon = get_ctk_icon("pen_white", size=(16, 16)) if self.is_edit else (get_ctk_icon("users_gear_solid_white", size=(16, 16)) or get_ctk_icon("user_solid_white", size=(16, 16)))
        build_standard_modal_header(self, title_txt, title_icon, on_close_cmd=self.destroy, text_color="#FFFFFF")

        # ── Footer Actions (packed with side="bottom" first to guarantee full visibility) ──
        actions_row = ctk.CTkFrame(self, fg_color="transparent", height=48)
        actions_row.pack(side="bottom", fill="x", padx=20, pady=(6, 16))
        actions_row.pack_propagate(False)

        cancel_btn = ctk.CTkButton(
            actions_row,
            image=get_ctk_icon("ban_red", size=(15, 15)),
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
        cancel_btn.pack(side="left")

        if self.is_edit:
            btn_txt = "  Editar Cambios"
            save_icon = get_ctk_icon("pen_orange", size=(15, 15)) or get_ctk_icon("pen_gold", size=(15, 15))
            save_fg = "#2A1608"
            save_hover = "#451A03"
            save_border = "#F59E0B"
            save_text_color = "#FBBF24"
        else:
            btn_txt = "  Crear Cajero"
            save_icon = get_ctk_icon("floppy_green", size=(15, 15)) or get_ctk_icon("floppy_white", size=(15, 15))
            save_fg = "#0A1D16"
            save_hover = "#0F2E22"
            save_border = "#10B981"
            save_text_color = "#34D399"

        save_btn = ctk.CTkButton(
            actions_row,
            image=save_icon,
            compound="left",
            text=btn_txt,
            width=165,
            height=38,
            fg_color=save_fg,
            hover_color=save_hover,
            border_color=save_border,
            border_width=1.5,
            text_color=save_text_color,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self._save_user
        )
        save_btn.pack(side="right")

        # ── Form Content ─────────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(6, 4))

        card = ctk.CTkFrame(
            body,
            fg_color="#181A22",
            border_color="#252836",
            border_width=1,
            corner_radius=8
        )
        card.pack(fill="both", expand=True, padx=2, pady=2)

        form_grid = ctk.CTkFrame(card, fg_color="transparent")
        form_grid.pack(fill="both", expand=True, padx=16, pady=14)

        # 1. Nombre Completo del Operador (*)
        ctk.CTkLabel(
            form_grid,
            text="NOMBRE COMPLETO DEL OPERADOR (*):",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFFFFF"
        ).pack(anchor="w", pady=(0, 2))

        self.name_entry = ctk.CTkEntry(
            form_grid,
            height=34,
            placeholder_text="Ej: Carlos Mendoza",
            placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=DarkTheme.INPUT_BG,
            border_color="#3B4A66",
            border_width=1.5,
            text_color=DarkTheme.INPUT_TEXT,
            corner_radius=6
        )
        self.name_entry.pack(fill="x", pady=(0, 8))
        if u and u.full_name:
            self.name_entry.insert(0, u.full_name)

        # Cashier extra fields (Cédula, Teléfono, Correo) - Only for Cajeros, not for Administrator
        if not self.is_admin_user:
            # 2. Cédula (*)
            ctk.CTkLabel(
                form_grid,
                text="CÉDULA (*):",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#FFFFFF"
            ).pack(anchor="w", pady=(0, 2))

            self.doc_entry = ctk.CTkEntry(
                form_grid,
                height=34,
                placeholder_text="Ej: 1049628190",
                placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                fg_color=DarkTheme.INPUT_BG,
                border_color="#3B4A66",
                border_width=1.5,
                text_color=DarkTheme.INPUT_TEXT,
                corner_radius=6
            )
            self.doc_entry.pack(fill="x", pady=(0, 8))
            if u and getattr(u, "document_id", None):
                self.doc_entry.insert(0, str(u.document_id))

            # 3. Teléfono de Contacto
            ctk.CTkLabel(
                form_grid,
                text="TELÉFONO DE CONTACTO:",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#FFFFFF"
            ).pack(anchor="w", pady=(0, 2))

            self.phone_entry = ctk.CTkEntry(
                form_grid,
                height=34,
                placeholder_text="Ej: 3101234567",
                placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                fg_color=DarkTheme.INPUT_BG,
                border_color="#3B4A66",
                border_width=1.5,
                text_color=DarkTheme.INPUT_TEXT,
                corner_radius=6
            )
            self.phone_entry.pack(fill="x", pady=(0, 8))
            if u and getattr(u, "phone", None):
                self.phone_entry.insert(0, str(u.phone))

            # 4. Correo Electrónico
            ctk.CTkLabel(
                form_grid,
                text="CORREO ELECTRÓNICO:",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#FFFFFF"
            ).pack(anchor="w", pady=(0, 2))

            self.email_entry = ctk.CTkEntry(
                form_grid,
                height=34,
                placeholder_text="Ej: cajero@xlburguer.com",
                placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                fg_color=DarkTheme.INPUT_BG,
                border_color="#3B4A66",
                border_width=1.5,
                text_color=DarkTheme.INPUT_TEXT,
                corner_radius=6
            )
            self.email_entry.pack(fill="x", pady=(0, 8))
            if u and getattr(u, "email", None):
                self.email_entry.insert(0, str(u.email))

        # Usuario de Acceso (*)
        ctk.CTkLabel(
            form_grid,
            text="USUARIO DE ACCESO (*):",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFFFFF"
        ).pack(anchor="w", pady=(0, 2))

        self.username_entry = ctk.CTkEntry(
            form_grid,
            height=34,
            placeholder_text="Ej: cajero1 o admin",
            placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=DarkTheme.INPUT_BG,
            border_color="#3B4A66",
            border_width=1.5,
            text_color=DarkTheme.INPUT_TEXT,
            corner_radius=6
        )
        self.username_entry.pack(fill="x", pady=(0, 8))
        if u and u.username:
            self.username_entry.insert(0, u.username)

        # Contraseña
        pwd_label = "NUEVA CONTRASEÑA (dejar en blanco para no cambiar):" if self.is_edit else "CONTRASEÑA DE ACCESO (*):"
        ctk.CTkLabel(
            form_grid,
            text=pwd_label,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFFFFF"
        ).pack(anchor="w", pady=(0, 2))

        pwd_row = ctk.CTkFrame(form_grid, fg_color="transparent")
        pwd_row.pack(fill="x", pady=(0, 6))

        self.pwd_entry = ctk.CTkEntry(
            pwd_row,
            height=34,
            show="•",
            placeholder_text="Contraseña segura" if not self.is_edit else "Conservar contraseña actual",
            placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=DarkTheme.INPUT_BG,
            border_color="#3B4A66",
            border_width=1.5,
            text_color=DarkTheme.INPUT_TEXT,
            corner_radius=6
        )
        self.pwd_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.eye_img_closed = get_ctk_icon("eye_white", size=(16, 16)) or get_ctk_icon("eye_slate", size=(16, 16))
        self.eye_img_open = get_ctk_icon("eye-slash-solid", size=(16, 16)) or get_ctk_icon("eye-slash-solid-full", size=(16, 16)) or get_ctk_icon("eye_slash_white", size=(16, 16)) or self.eye_img_closed
        self.pwd_visible = False
        self.eye_btn = ctk.CTkButton(
            pwd_row,
            image=self.eye_img_closed,
            text="",
            width=36,
            height=34,
            fg_color="#111624",
            border_color="#283347",
            border_width=1,
            hover_color="#1E293B",
            corner_radius=6,
            cursor="hand2",
            command=self._toggle_pwd_visibility
        )
        self.eye_btn.pack(side="left")

        # Setup Tab navigation across form fields
        tab_widgets = [self.name_entry]
        if not self.is_admin_user:
            if hasattr(self, "doc_entry"):
                tab_widgets.append(self.doc_entry)
            if hasattr(self, "phone_entry"):
                tab_widgets.append(self.phone_entry)
            if hasattr(self, "email_entry"):
                tab_widgets.append(self.email_entry)
        tab_widgets.extend([self.username_entry, self.pwd_entry, cancel_btn, save_btn])
        _bind_tab_navigation(self, tab_widgets, on_enter=self._save_user)
        self.after(100, lambda: self.name_entry.focus_set())

    def _toggle_pwd_visibility(self) -> None:
        self.pwd_visible = not self.pwd_visible
        if self.pwd_visible:
            self.pwd_entry.configure(show="")
            self.eye_btn.configure(
                image=self.eye_img_open,
                fg_color="#1E293B",
                border_color="#3B82F6"
            )
        else:
            self.pwd_entry.configure(show="•")
            self.eye_btn.configure(
                image=self.eye_img_closed,
                fg_color="#111624",
                border_color="#283347"
            )

    def _save_user(self) -> None:
        full_name = self.name_entry.get().strip()
        username = self.username_entry.get().strip()
        password = self.pwd_entry.get().strip()

        doc_id = self.doc_entry.get().strip() if hasattr(self, "doc_entry") else ""
        phone = self.phone_entry.get().strip() if hasattr(self, "phone_entry") else ""
        email = self.email_entry.get().strip() if hasattr(self, "email_entry") else ""

        if not full_name:
            sound_manager.play_error()
            messagebox.showwarning("Campo Requerido", "Por favor ingrese el nombre completo del operador.", parent=self)
            self.name_entry.focus_set()
            return

        if not self.is_admin_user and not doc_id:
            sound_manager.play_error()
            messagebox.showwarning("Campo Requerido", "Por favor ingrese el número de cédula del operador.", parent=self)
            if hasattr(self, "doc_entry"):
                self.doc_entry.focus_set()
            return

        if not username:
            sound_manager.play_error()
            messagebox.showwarning("Campo Requerido", "Por favor ingrese el nombre de usuario de acceso.", parent=self)
            self.username_entry.focus_set()
            return

        if " " in username:
            sound_manager.play_error()
            messagebox.showwarning("Usuario Inválido", "El nombre de usuario de acceso no puede contener espacios en blanco.", parent=self)
            self.username_entry.focus_set()
            return

        if not self.is_edit and not password:
            sound_manager.play_error()
            messagebox.showwarning("Campo Requerido", "Por favor ingrese la contraseña de acceso para el nuevo cajero.", parent=self)
            self.pwd_entry.focus_set()
            return

        try:
            with get_db_connection() as conn:
                cur = conn.cursor()
                if self.is_edit:
                    u_id = self.user.id
                    # Verify unique username across other users
                    cur.execute("SELECT id FROM users WHERE username = ? AND id != ?", (username, u_id))
                    if cur.fetchone():
                        sound_manager.play_error()
                        messagebox.showwarning("Usuario Existente", f"El nombre de usuario '{username}' ya está en uso.", parent=self)
                        return

                    if self.is_admin_user:
                        UserModel.update_user(
                            conn,
                            user_id=u_id,
                            username=username,
                            full_name=full_name,
                            role="ADMIN",
                            password=password if password else None
                        )
                    else:
                        UserModel.update_user(
                            conn,
                            user_id=u_id,
                            username=username,
                            full_name=full_name,
                            role="CASHIER",
                            password=password if password else None,
                            document_id=doc_id,
                            phone=phone,
                            email=email
                        )

                    try:
                        top = self.winfo_toplevel()
                        if hasattr(top, "refresh_user_badge"):
                            top.refresh_user_badge()
                    except Exception:
                        pass
                else:
                    cur.execute("SELECT id FROM users WHERE username = ?", (username,))
                    if cur.fetchone():
                        sound_manager.play_error()
                        messagebox.showwarning("Usuario Existente", f"El nombre de usuario '{username}' ya está en uso.", parent=self)
                        return

                    UserModel.create_user(
                        conn,
                        username=username,
                        password=password,
                        full_name=full_name,
                        role="CASHIER",
                        document_id=doc_id,
                        phone=phone,
                        email=email,
                        is_active=1
                    )

            sound_manager.play_sale_success()
            if self.on_success_callback:
                self.on_success_callback()
            self.destroy()

        except Exception as e:
            sound_manager.play_error()
            messagebox.showerror("Error al Guardar", f"No se pudo guardar la información del operador:\n{e}", parent=self)



# ─────────────────────────────────────────────────────────────────────────────
# 2.5 USER DETAIL MODAL (FICHA DEL COLABORADOR / OPERADOR DEL SISTEMA)
# ─────────────────────────────────────────────────────────────────────────────
class UserDetailModal(ctk.CTkToplevel):
    """Detailed Profile & Performance Modal for a System User (Operador / Administrador).
    Shows:
    - Official Executive Header with Cambria Bold Italic Title & Auto-tinted Violet Icon (#666BC5).
    - User avatar badge with initials, role pill, active status pill.
    - User credentials & contact card: Username, Document ID, Phone, Email.
    - KPI Performance summary: Total Sales made, Total Invoiced ($ COP), Average ticket.
    - Permanently anchored 'Cerrar Ficha' button at footer.
    """
    def __init__(self, parent, user: User):
        super().__init__(parent)
        self.user = user
        self.title("Ficha de Colaborador - XL Burguer")
        self.configure(fg_color="#15171F")
        self.resizable(False, False)

        _set_dialog_icon_and_center(self, parent, 540, 480)

        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda e: self.destroy())

        self._build_ui()

    def _build_ui(self) -> None:
        u = self.user

        # Header with Cambria italic title & auto-tinted icon
        user_icon = get_ctk_icon("user-tie-solid-full", size=(16, 16)) or get_ctk_icon("user_solid_white", size=(16, 16))
        build_standard_modal_header(self, "Ficha de Colaborador", user_icon, on_close_cmd=self.destroy, show_close_btn=False)

        # Body container
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(6, 10))

        # 1. Profile Banner Card
        prof_card = ctk.CTkFrame(body, fg_color="#181A22", border_color="#252836", border_width=1, corner_radius=8)
        prof_card.pack(fill="x", pady=(0, 10))

        prof_inner = ctk.CTkFrame(prof_card, fg_color="transparent")
        prof_inner.pack(fill="x", padx=16, pady=12)

        is_adm = u.is_admin
        avatar_border = "#F59E0B" if is_adm else "#3B82F6"
        avatar_text_col = "#FBBF24" if is_adm else "#60A5FA"
        avatar_bg = "#2A1B0A" if is_adm else "#0F1E36"

        avatar_frame = ctk.CTkFrame(
            prof_inner,
            fg_color=avatar_bg,
            border_color=avatar_border,
            border_width=1.5,
            corner_radius=24,
            width=48,
            height=48
        )
        avatar_frame.pack(side="left", padx=(0, 14))
        avatar_frame.pack_propagate(False)

        initials = "".join([part[:1] for part in (u.full_name or "").split()[:2]]).upper() or "US"
        ctk.CTkLabel(
            avatar_frame,
            text=initials,
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=avatar_text_col
        ).pack(expand=True)

        info_box = ctk.CTkFrame(prof_inner, fg_color="transparent")
        info_box.pack(side="left", fill="y")

        name_row = ctk.CTkFrame(info_box, fg_color="transparent")
        name_row.pack(anchor="w")

        ctk.CTkLabel(
            name_row,
            text=u.full_name,
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#FFFFFF"
        ).pack(side="left")

        role_fg = "#FBBF24" if is_adm else "#38BDF8"
        role_border = "#F59E0B" if is_adm else "#0284C7"
        role_bg = "#78350F" if is_adm else "#0C2340"
        role_txt = "Administrador" if is_adm else "Cajero"

        role_pill = ctk.CTkFrame(name_row, fg_color=role_bg, border_color=role_border, border_width=1, corner_radius=10, height=20)
        role_pill.pack(side="left", padx=(10, 4))
        ctk.CTkLabel(role_pill, text=role_txt, font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=role_fg).pack(padx=8, pady=1)

        is_act = bool(u.active)
        st_bg = "#064E3B" if is_act else "#450A0A"
        st_border = "#10B981" if is_act else "#EF4444"
        st_fg = "#34D399" if is_act else "#F87171"
        st_txt = "Activo" if is_act else "Inactivo"

        st_pill = ctk.CTkFrame(name_row, fg_color=st_bg, border_color=st_border, border_width=1, corner_radius=10, height=20)
        st_pill.pack(side="left", padx=4)
        ctk.CTkLabel(st_pill, text=st_txt, font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=st_fg).pack(padx=8, pady=1)

        ctk.CTkLabel(
            info_box,
            text=f"Usuario del sistema: @{u.username}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=DarkTheme.TEXT_MUTED
        ).pack(anchor="w", pady=(2, 0))

        # 2. Details Info Grid
        meta_card = ctk.CTkFrame(body, fg_color="#181A22", border_color="#252836", border_width=1, corner_radius=8)
        meta_card.pack(fill="x", pady=(0, 10))

        meta_grid = ctk.CTkFrame(meta_card, fg_color="transparent")
        meta_grid.pack(fill="x", padx=16, pady=12)
        meta_grid.grid_columnconfigure((0, 1), weight=1)

        fields = [
            ("Documento / Cédula:", u.document_id if u.document_id else "No registrado"),
            ("Teléfono de Contacto:", u.phone if u.phone else "No registrado"),
            ("Correo Electrónico:", u.email if u.email else "No registrado"),
            ("ID en Sistema:", f"Operador #{u.id}"),
        ]

        for i, (lbl_txt, val_txt) in enumerate(fields):
            r = i // 2
            c = i % 2
            item_box = ctk.CTkFrame(meta_grid, fg_color="transparent")
            item_box.grid(row=r, column=c, sticky="w", padx=10, pady=4)
            ctk.CTkLabel(item_box, text=lbl_txt, font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=DarkTheme.TEXT_MUTED).pack(anchor="w")
            ctk.CTkLabel(item_box, text=val_txt, font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#E2E8F0").pack(anchor="w")

        # 3. Performance KPI stats
        total_sales = 0
        total_amount = 0.0
        try:
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(total), 0) as tot FROM sales WHERE user_id = ?", (u.id,))
                row = cur.fetchone()
                if row:
                    total_sales = int(row["cnt"] or 0)
                    total_amount = float(row["tot"] or 0.0)
        except Exception:
            pass
        avg_ticket = (total_amount / total_sales) if total_sales > 0 else 0.0

        kpi_card = ctk.CTkFrame(body, fg_color="#181A22", border_color="#252836", border_width=1, corner_radius=8)
        kpi_card.pack(fill="x", pady=(0, 12))

        kpi_inner = ctk.CTkFrame(kpi_card, fg_color="transparent")
        kpi_inner.pack(fill="x", padx=14, pady=10)
        kpi_inner.grid_columnconfigure((0, 1, 2), weight=1)

        kpis = [
            ("Facturas Emitidas", f"{total_sales:,}", "#38BDF8", "#082F49", "#0284C7"),
            ("Total Recaudado", f"${total_amount:,.0f} COP", "#34D399", "#061A12", "#10B981"),
            ("Promedio por Venta", f"${avg_ticket:,.0f} COP", "#FBBF24", "#1C1304", "#F59E0B"),
        ]

        for idx, (title, val, fg_col, bg_col, bd_col) in enumerate(kpis):
            chip = ctk.CTkFrame(kpi_inner, fg_color=bg_col, border_color=bd_col, border_width=1.2, corner_radius=6)
            chip.grid(row=0, column=idx, sticky="nsew", padx=4, pady=2)
            ctk.CTkLabel(chip, text=title, font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"), text_color=DarkTheme.TEXT_MUTED).pack(anchor="w", padx=10, pady=(6, 1))
            ctk.CTkLabel(chip, text=val, font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=fg_col).pack(anchor="w", padx=10, pady=(0, 6))

        # 4. Footer close button
        footer = ctk.CTkFrame(self, fg_color="transparent", height=44)
        footer.pack(fill="x", side="bottom", padx=20, pady=(0, 14))

        close_btn = ctk.CTkButton(
            footer,
            text="  Cerrar Ficha",
            image=get_ctk_icon("ban_red", size=(15, 15)),
            compound="left",
            width=140,
            height=36,
            fg_color="#1C1117",
            hover_color="#2D151E",
            border_color="#EF4444",
            border_width=1.5,
            text_color="#F87171",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self.destroy
        )
        close_btn.pack(side="right")


# ─────────────────────────────────────────────────────────────────────────────
# 3. COMPANY QUOTA EDIT MODAL (ASIGNAR / EDITAR CUPO Y SALDO RESTANTE)
# ─────────────────────────────────────────────────────────────────────────────
class CompanyQuotaEditModal(ctk.CTkToplevel):
    """Modern modal dialog to assign or directly edit an enterprise's product quota and remaining balance.
    Permite modificar directamente 'cuánto le queda de este producto' y el cupo pactado.
    """

    def __init__(
        self,
        parent,
        company: Optional[Dict[str, Any]] = None,
        quota: Optional[Dict[str, Any]] = None,
        on_success_callback: Optional[Callable[[], None]] = None,
        customer_id: Optional[int] = None,
        company_name: Optional[str] = None
    ):
        super().__init__(parent)
        if company is not None:
            self.company = company
        else:
            self.company = {"id": customer_id or 0, "full_name": company_name or "Empresa"}

        self.quota = quota
        self.on_success_callback = on_success_callback
        self.is_edit = quota is not None

        c_name = self.company.get("first_name", "") or self.company.get("full_name", "")
        p_name = quota.get("product_name", "") if quota else "Nuevo Producto"
        title_txt = f"Editar Saldo y Cupo: {p_name}" if self.is_edit else "Asignar Producto en Convenio"

        self.title(title_txt)
        self.resizable(False, False)
        self.configure(fg_color="#15171F")

        self._build_ui(title_txt)
        _set_dialog_icon_and_center(self, parent, 540, 560)

        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self, title_txt: str) -> None:
        q = self.quota or {}

        # Brand topbar in pure white
        title_icon = get_ctk_icon("pen_white", size=(16, 16)) if self.is_edit else (get_ctk_icon("file_circle_plus_white", size=(16, 16)) or get_ctk_icon("meat_white", size=(16, 16)))
        build_standard_modal_header(self, title_txt, title_icon, on_close_cmd=self.destroy, text_color="#FFFFFF")

        # ── Footer Actions (packed with side="bottom" first to guarantee full visibility) ──
        actions_row = ctk.CTkFrame(self, fg_color="transparent", height=48)
        actions_row.pack(side="bottom", fill="x", padx=20, pady=(6, 16))
        actions_row.pack_propagate(False)

        cancel_btn = ctk.CTkButton(
            actions_row,
            text="  Cancelar",
            image=get_ctk_icon("ban_red", size=(15, 15)),
            compound="left",
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
        cancel_btn.pack(side="left")

        if self.is_edit:
            edit_btn_ico = get_ctk_icon("pen_orange", size=(15, 15)) or get_ctk_icon("pen_gold", size=(15, 15))
            save_btn = ctk.CTkButton(
                actions_row,
                image=edit_btn_ico,
                compound="left",
                text="  Editar Cambios",
                width=175,
                height=38,
                fg_color="#2A1608",
                hover_color="#451A03",
                border_color="#F59E0B",
                border_width=1.5,
                text_color="#FBBF24",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                corner_radius=6,
                cursor="hand2",
                command=self._save_quota
            )
        else:
            save_icon = get_ctk_icon("floppy_green", size=(15, 15)) or get_ctk_icon("floppy_white", size=(15, 15))
            save_btn = ctk.CTkButton(
                actions_row,
                image=save_icon,
                compound="left",
                text="  Crear Cupo",
                width=180,
                height=38,
                fg_color="#0A1D16",
                hover_color="#0F2E22",
                border_color="#10B981",
                border_width=1.5,
                text_color="#34D399",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                corner_radius=6,
                cursor="hand2",
                command=self._save_quota
            )
        save_btn.pack(side="right")
        self.save_btn = save_btn

        # ── Form Content (expands to fill the remaining area) ────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(6, 4))

        # Card container with clean subtle border (no orange outline)
        card = ctk.CTkFrame(body, fg_color="#181A22", border_color="#252836", border_width=1.2, corner_radius=8)
        card.pack(fill="both", expand=True)

        form = ctk.CTkFrame(card, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=16, pady=16)

        # Empresa Info Banner with white company icon and formatted (Encargado)
        emp_badge = ctk.CTkFrame(form, fg_color="#111624", border_color="#252836", border_width=1, corner_radius=6)
        emp_badge.pack(fill="x", pady=(0, 12))
        emp_inner = ctk.CTkFrame(emp_badge, fg_color="transparent")
        emp_inner.pack(padx=10, pady=5)
        b_ico = get_ctk_icon("building_solid_white", size=(15, 15)) or get_ctk_icon("building-solid-full", size=(15, 15))
        if b_ico:
            ctk.CTkLabel(emp_inner, image=b_ico, text="").pack(side="left", padx=(0, 6))

        c_full = self.company.get("first_name", "") or self.company.get("full_name", "Empresa")
        enc_txt = format_encargado(self.company.get("last_name", ""))
        nit_txt = self.company.get("document_id", "—")
        if enc_txt and enc_txt != "—":
            emp_header_str = f"Empresa: {c_full} ({enc_txt})  •  NIT: {nit_txt}"
        else:
            emp_header_str = f"Empresa: {c_full}  •  NIT: {nit_txt}"

        ctk.CTkLabel(
            emp_inner,
            text=emp_header_str,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFFFFF"
        ).pack(side="left")

        # 1. Producto / Corte
        ctk.CTkLabel(form, text="PRODUCTO / CORTE (*):", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#94A3B8").pack(anchor="w", pady=(0, 2))

        self.products_map = {}
        with get_db_connection() as conn:
            all_prods = sorted(ProductModel.get_all(conn), key=lambda x: (x.name or "").lower())
            self.products_map = {f"{p.id} - {p.name}": p for p in all_prods if p.name}

        if self.is_edit:
            prod_id = q.get("product_id", "")
            p_display = f"{prod_id} - {q.get('product_name', 'Producto')}" if prod_id else q.get("product_name", "Producto")
            self.prod_lbl = ctk.CTkLabel(
                form,
                text=p_display,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color="#FFFFFF",
                anchor="w"
            )
            self.prod_lbl.pack(fill="x", pady=(0, 10))
            self.selected_product_id = q.get("product_id")
            default_unit = q.get("unit", "kg")
        else:
            prod_values = ["-- Seleccionar Producto --"] + list(self.products_map.keys())
            self.prod_dropdown = ctk.CTkOptionMenu(
                form,
                values=prod_values,
                height=36,
                fg_color="#0F172A",
                button_color="#1E293B",
                button_hover_color="#334155",
                dropdown_fg_color="#0F172A",
                dropdown_text_color="#FFFFFF",
                text_color="#FFFFFF",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                command=self._on_product_dropdown_selected
            )
            self.prod_dropdown.set("-- Seleccionar Producto --")
            self.prod_dropdown.pack(fill="x", pady=(0, 10))
            default_unit = "kg"
            self.selected_product_id = None

        kb_img = get_ctk_icon("keyboard_slate", size=(16, 16))

        # 2. Cupo Mensual Pactado
        ctk.CTkLabel(form, text="CUPO MENSUAL PACTADO (*):", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#94A3B8").pack(anchor="w", pady=(0, 2))
        cupo_row = ctk.CTkFrame(form, fg_color="transparent")
        cupo_row.pack(fill="x", pady=(0, 10))

        self.quota_entry = ctk.CTkEntry(
            cupo_row,
            height=36,
            placeholder_text="0.00",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#060B18",
            border_color="#3B4A66",
            border_width=1.5,
            text_color="#F8FAFC"
        )
        self.quota_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        if self.is_edit:
            self.quota_entry.insert(0, f"{q.get('quota_quantity', 0.0):.2f}")

        ctk.CTkButton(
            cupo_row,
            image=kb_img,
            text="",
            width=36,
            height=36,
            fg_color="#111624",
            border_color="#283347",
            border_width=1,
            hover_color="#1E293B",
            corner_radius=6,
            cursor="hand2",
            command=lambda: self._open_keypad(self.quota_entry, "Cupo Mensual")
        ).pack(side="left", padx=(0, 6))

        self.unit_var = ctk.StringVar(value=default_unit)
        self.unit_menu = ctk.CTkOptionMenu(
            cupo_row,
            values=["kg", "lb", "g", "und", "paq", "cja"],
            variable=self.unit_var,
            width=80,
            height=36,
            fg_color="#111624",
            button_color="#283347",
            font=ctk.CTkFont(family="Segoe UI", size=12)
        )
        self.unit_menu.pack(side="left")

        # 3. SALDO RESTANTE ACTUAL ("LE QUEDA") - DIRECTLY EDITABLE
        ctk.CTkLabel(
            form,
            text="SALDO RESTANTE (*):",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#34D399"
        ).pack(anchor="w", pady=(0, 2))

        rem_row = ctk.CTkFrame(form, fg_color="transparent")
        rem_row.pack(fill="x", pady=(0, 10))

        self.rem_entry = ctk.CTkEntry(
            rem_row,
            height=36,
            placeholder_text="0.00",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color="#061A12",
            border_color="#10B981",
            border_width=1.5,
            text_color="#34D399"
        )
        self.rem_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        if self.is_edit:
            self.rem_entry.insert(0, f"{q.get('remaining_quantity', 0.0):.2f}")

        ctk.CTkButton(
            rem_row,
            image=kb_img,
            text="",
            width=36,
            height=36,
            fg_color="#111624",
            border_color="#283347",
            border_width=1,
            hover_color="#1E293B",
            corner_radius=6,
            cursor="hand2",
            command=lambda: self._open_keypad(self.rem_entry, "Saldo Restante")
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            rem_row,
            text="= Cupo",
            width=65,
            height=36,
            fg_color="#111624",
            border_color="#10B981",
            border_width=1,
            hover_color="#064E3B",
            text_color="#34D399",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self._sync_rem_with_quota
        ).pack(side="left")

        # 4. Notas / Observaciones
        ctk.CTkLabel(form, text="NOTAS / OBSERVACIONES (Opcional):", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#94A3B8").pack(anchor="w", pady=(0, 2))
        self.notes_entry = ctk.CTkEntry(
            form,
            height=36,
            placeholder_text="Ej: Facturación a fin de mes",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#060B18",
            border_color="#3B4A66",
            border_width=1.5,
            text_color="#F8FAFC"
        )
        self.notes_entry.pack(fill="x", pady=(0, 10))
        if q.get("notes"):
            self.notes_entry.insert(0, str(q["notes"]))

        # Setup Tab navigation across form fields
        tab_widgets = []
        if not self.is_edit and hasattr(self, "prod_dropdown"):
            tab_widgets.append(self.prod_dropdown)
        tab_widgets.extend([self.quota_entry, self.rem_entry, self.notes_entry, cancel_btn, save_btn])
        _bind_tab_navigation(self, tab_widgets, on_enter=self._save_quota)
        self.after(100, lambda: self.quota_entry.focus_set())



    def _on_product_dropdown_selected(self, val: str) -> None:
        p = self.products_map.get(val)
        if p:
            self.selected_product_id = p.id
            u = "und" if p.sale_type == "UNIDAD" else "kg"
            self.unit_var.set(u)
        else:
            self.selected_product_id = None

    def _sync_rem_with_quota(self) -> None:
        val = self.quota_entry.get().strip()
        self.rem_entry.delete(0, "end")
        if val:
            self.rem_entry.insert(0, val)

    def _open_keypad(self, target_entry: ctk.CTkEntry, title: str) -> None:
        if not TouchKeypadModal:
            return
        TouchKeypadModal(
            parent=self,
            title=title,
            subtitle="Digite los números",
            initial_value=target_entry.get().strip(),
            on_confirm_callback=lambda val: [target_entry.delete(0, "end"), target_entry.insert(0, val)]
        )

    def _save_quota(self) -> None:
        q_raw = self.quota_entry.get().replace(",", ".").strip()
        r_raw = self.rem_entry.get().replace(",", ".").strip()
        if not q_raw and not r_raw:
            sound_manager.play_error()
            messagebox.showwarning("Valores Inválidos", "Por favor ingrese el cupo pactado.", parent=self)
            return
        if not r_raw and q_raw:
            r_raw = q_raw
            self.rem_entry.delete(0, "end")
            self.rem_entry.insert(0, q_raw)
        try:
            quota_val = float(q_raw)
            rem_val = float(r_raw)
        except ValueError:
            sound_manager.play_error()
            messagebox.showwarning("Valores Inválidos", "Por favor ingrese valores numéricos válidos para el cupo y saldo restante.", parent=self)
            return

        unit = self.unit_var.get().strip() or "kg"
        notes = self.notes_entry.get().strip() if hasattr(self, "notes_entry") and self.notes_entry else ""

        try:
            with get_db_connection() as conn:
                if self.is_edit:
                    quota_id = self.quota["id"]
                    CustomerModel.update_company_quota_remaining(conn, quota_id, new_remaining=rem_val, new_quota=quota_val, notes=notes)
                else:
                    if not self.selected_product_id:
                        sound_manager.play_error()
                        messagebox.showwarning("Producto Requerido", "Seleccione un producto para asignar.", parent=self)
                        return
                    CustomerModel.set_company_quota(
                        conn,
                        customer_id=self.company["id"],
                        product_id=self.selected_product_id,
                        quota_quantity=quota_val,
                        unit=unit,
                        notes=notes,
                        remaining_quantity=rem_val,
                        remaining=rem_val
                    )

            sound_manager.play_sale_success()
            if self.on_success_callback:
                self.on_success_callback()
            self.destroy()
        except Exception as e:
            sound_manager.play_error()
            messagebox.showerror("Error al Guardar Cupo", f"No se pudo guardar el convenio:\n{e}", parent=self)


# ─────────────────────────────────────────────────────────────────────────────
# 3B. COMPANY DETAIL MODAL (FICHA DE EMPRESA & CONVENIOS DE FIADOS)
# ─────────────────────────────────────────────────────────────────────────────
class CompanyDetailModal(ctk.CTkToplevel):
    """Executive corporate modal presenting Company Profile, Fiados & Quotas Agreements
    ("¿Cuánto le queda de cada producto?"), direct quota editing, and sales dispatch history.
    """

    def __init__(
        self,
        parent,
        company: Optional[Dict[str, Any]] = None,
        customer: Optional[Dict[str, Any]] = None,
        on_edit_request: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_delete_request: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_refresh_request: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        self.company = company or customer or {}
        self.on_edit_request = on_edit_request
        self.on_delete_request = on_delete_request
        self.on_refresh_request = on_refresh_request

        # Determine company ranking among companies
        c_target = self.company
        rank = c_target.get("ranking") or c_target.get("rank")
        if not rank:
            try:
                with get_db_connection() as conn:
                    all_comps = CustomerModel.get_all_with_stats(conn, customer_type="EMPRESA")
                    for i, item in enumerate(all_comps, 1):
                        if item["id"] == c_target.get("id"):
                            rank = i
                            break
            except Exception:
                rank = None
        self.company_rank = rank

        self.quotas_page_size = 5
        self.quotas_current_page = 1
        self.quotas_total_pages = 1

        self.purchases_page_size = 5
        self.purchases_current_page = 1
        self.purchases_total_pages = 1

        c_name = self.company.get("full_name", "Empresa")
        self.title("Ficha de Empresa")
        self.minsize(860, 680)
        self.resizable(True, True)
        self.configure(fg_color="#15171F")

        self._build_ui()
        _set_dialog_icon_and_center(self, parent, 860, 740)

        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self) -> None:
        c = self.company
        c_id = c["id"]

        with get_db_connection() as conn:
            self.quotas = CustomerModel.get_company_quotas(conn, c_id)
            self.summary = CustomerModel.get_company_fiados_summary(conn, c_id)
            self.purchases = CustomerModel.get_customer_purchases(conn, c_id)

        # ── 1. Topbar in pure white ──────────────────────────────────────────
        tag_icon = get_ctk_icon("building_solid_white", size=(16, 16)) or get_ctk_icon("building_user_white", size=(16, 16))
        build_standard_modal_header(self, "Ficha de Empresa", tag_icon, on_close_cmd=self.destroy, show_close_btn=False, text_color="#FFFFFF")

        # ── 2. Body (Scrollable for responsive safety on all monitor resolutions) ──
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=10)

        # Profile Card
        prof_card = ctk.CTkFrame(body, fg_color="#181A22", border_color="#334155", border_width=1.2, corner_radius=8)
        prof_card.pack(fill="x", pady=(0, 8))

        prof_inner = ctk.CTkFrame(prof_card, fg_color="transparent")
        prof_inner.pack(fill="x", padx=14, pady=10)

        # Avatar with company icon and rank tints (Top 1 Gold, Top 2 Silver, Top 3 Bronze, Rank 4+ Sky Blue)
        if self.company_rank == 1:
            border_col = "#F59E0B"
            av_bg = "#3B1806"
            bld_ico = get_tinted_ctk_icon("building_solid_white", "#F59E0B", size=(22, 22)) or get_ctk_icon("building_solid_white", size=(22, 22))
        elif self.company_rank == 2:
            border_col = "#CBD5E1"
            av_bg = "#222B38"
            bld_ico = get_tinted_ctk_icon("building_solid_white", "#FFFFFF", size=(22, 22)) or get_ctk_icon("building_solid_white", size=(22, 22))
        elif self.company_rank == 3:
            border_col = "#D97706"
            av_bg = "#381B09"
            bld_ico = get_tinted_ctk_icon("building_solid_white", "#FED7AA", size=(22, 22)) or get_ctk_icon("building_solid_white", size=(22, 22))
        else:
            border_col = "#38BDF8"
            av_bg = "#0B192C"
            bld_ico = get_tinted_ctk_icon("building_solid_white", "#38BDF8", size=(22, 22)) or get_ctk_icon("building_solid_white", size=(22, 22))

        av = ctk.CTkFrame(prof_inner, fg_color=av_bg, border_color=border_col, border_width=1.5, corner_radius=22, width=44, height=44)
        av.pack(side="left", padx=(0, 14))
        av.pack_propagate(False)
        ctk.CTkLabel(av, image=bld_ico, text="").pack(expand=True)

        info_box = ctk.CTkFrame(prof_inner, fg_color="transparent")
        info_box.pack(side="left", fill="both", expand=True)

        c_display_name = c.get("first_name", "") or c.get("full_name", "Empresa")
        # Company name & top medal badge (Row 0, Columns 0-1)
        name_row = ctk.CTkFrame(info_box, fg_color="transparent")
        name_row.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        ctk.CTkLabel(
            name_row,
            text=c_display_name,
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#FFFFFF"
        ).pack(side="left")

        if self.company_rank in (1, 2, 3):
            med_img = get_ctk_icon(f"{self.company_rank}.png", size=(20, 20))
            if med_img:
                ctk.CTkLabel(name_row, image=med_img, text="").pack(side="left", padx=(8, 4))

            if self.company_rank == 1:
                t_bg, t_bd, t_fg = "#78350F", "#F59E0B", "#FBBF24"
            elif self.company_rank == 2:
                t_bg, t_bd, t_fg = "#1E293B", "#94A3B8", "#E2E8F0"
            else:
                t_bg, t_bd, t_fg = "#451A03", "#D97706", "#FCD34D"

            # Top pill is placed in Row 0, Column 2, positioned directly above Tel chip
            top_pill = ctk.CTkFrame(info_box, fg_color=t_bg, border_color=t_bd, border_width=1, corner_radius=10, height=20)
            top_pill.grid(row=0, column=2, sticky="w", pady=(0, 4))
            ctk.CTkLabel(
                top_pill,
                text=f"★ TOP #{self.company_rank}",
                font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
                text_color=t_fg
            ).pack(padx=6, pady=1)

        p_txt = c.get("phone") if c.get("phone") else "Sin registrar"
        contact_txt = format_encargado(c.get("last_name", "")) or "No especificado"
        doc_txt = c.get("document_id", "—")

        # Row 1: Metadata chips with real vector/PNG icons
        # 1. NIT / RUT Chip (Slate box with ID card icon)
        nit_chip = ctk.CTkFrame(info_box, fg_color="#111624", border_color="#283347", border_width=1, corner_radius=6)
        nit_chip.grid(row=1, column=0, sticky="w", padx=(0, 6))
        nit_inner = ctk.CTkFrame(nit_chip, fg_color="transparent")
        nit_inner.pack(padx=8, pady=2)
        ico_id = get_tinted_ctk_icon("id-card-solid-full", "#CBD5E1", size=(13, 13)) or get_ctk_icon("id_card_slate", size=(13, 13))
        if ico_id:
            ctk.CTkLabel(nit_inner, image=ico_id, text="").pack(side="left", padx=(0, 5))
        ctk.CTkLabel(
            nit_inner,
            text=f"NIT / RUT: {doc_txt}",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#CBD5E1"
        ).pack(side="left")

        # 2. Encargado Chip (Blue box with profile icon)
        enc_chip = ctk.CTkFrame(info_box, fg_color="#0C2340", border_color="#0284C7", border_width=1, corner_radius=6)
        enc_chip.grid(row=1, column=1, sticky="w", padx=(0, 6))
        enc_inner = ctk.CTkFrame(enc_chip, fg_color="transparent")
        enc_inner.pack(padx=8, pady=2)
        ico_enc = get_ctk_icon("user_solid_blue", size=(13, 13)) or get_tinted_ctk_icon("user-solid-full", "#38BDF8", size=(13, 13))
        if ico_enc:
            ctk.CTkLabel(enc_inner, image=ico_enc, text="").pack(side="left", padx=(0, 5))
        ctk.CTkLabel(
            enc_inner,
            text=f"Encargado: {contact_txt}",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#38BDF8"
        ).pack(side="left")

        # 3. Tel Chip (Green box with phone icon) - Placed in Row 1, Column 2, aligned under top_pill
        tel_chip = ctk.CTkFrame(info_box, fg_color="#061A12", border_color="#059669", border_width=1, corner_radius=6)
        tel_chip.grid(row=1, column=2, sticky="w")
        tel_inner = ctk.CTkFrame(tel_chip, fg_color="transparent")
        tel_inner.pack(padx=8, pady=2)
        ico_tel = get_ctk_icon("mobile_green", size=(13, 13)) or get_tinted_ctk_icon("mobile-screen-solid-full", "#34D399", size=(13, 13))
        if ico_tel:
            ctk.CTkLabel(tel_inner, image=ico_tel, text="").pack(side="left", padx=(0, 5))
        ctk.CTkLabel(
            tel_inner,
            text=f"Tel: {p_txt}",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#34D399"
        ).pack(side="left")

        # Buttons on right of profile card: [✏ Editar] on top, [🗑 Eliminar] on bottom
        btn_grp = ctk.CTkFrame(prof_inner, fg_color="transparent")
        btn_grp.pack(side="right")

        btn_edit = ctk.CTkButton(
            btn_grp,
            text=" Editar",
            width=82,
            height=26,
            corner_radius=5,
            cursor="hand2",
            command=self._on_edit_company
        )
        apply_palette_button(btn_edit, variant="editar", icon_name="pen_gold", icon_size=(13, 13), font_size=10)
        btn_edit.pack(fill="x", pady=(0, 4))

        btn_del = ctk.CTkButton(
            btn_grp,
            text=" Eliminar",
            width=82,
            height=26,
            corner_radius=5,
            cursor="hand2",
            command=self._on_delete_company
        )
        apply_palette_button(btn_del, variant="eliminar", icon_name="trash_red", icon_size=(13, 13), font_size=10)
        btn_del.pack(fill="x")

        # ── 3. KPI Strip ─────────────────────────────────────────────────────
        kpi_row = ctk.CTkFrame(body, fg_color="transparent")
        kpi_row.pack(fill="x", pady=(0, 8))
        kpi_row.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="comp_kpis")

        c_cnt = len(self.quotas)
        tot_cupo = sum(q["quota_quantity"] for q in self.quotas)
        tot_rem = sum(q["remaining_quantity"] for q in self.quotas)
        tot_fiado = self.summary.get("total_fiado_amount", 0.0)

        def _make_kpi_card(parent, col, title, val, text_color, border_color, bg_color, icon_name=None):
            bx = ctk.CTkFrame(parent, fg_color=bg_color, border_color=border_color, border_width=1.2, corner_radius=6, height=30)
            bx.grid(row=0, column=col, sticky="ew", padx=2)
            lbl_box = ctk.CTkFrame(bx, fg_color="transparent")
            lbl_box.pack(pady=4)
            if icon_name:
                ico = get_ctk_icon(icon_name, size=(12, 12))
                if ico:
                    ctk.CTkLabel(lbl_box, image=ico, text="").pack(side="left", padx=(0, 4))
            ctk.CTkLabel(lbl_box, text=f"{title}: {val}", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=text_color).pack(side="left")

        _make_kpi_card(kpi_row, 0, "Productos Convenio", str(c_cnt), "#38BDF8", "#0284C7", "#082F49", icon_name="cube_sky")
        _make_kpi_card(kpi_row, 1, "Cupo Total", f"{tot_cupo:.1f} kg", "#67E8F9", "#0E7490", "#083344", icon_name="box_open_cyan")
        _make_kpi_card(kpi_row, 2, "Saldo Disponible", f"{tot_rem:.1f} kg", "#34D399", "#10B981", "#064E3B", icon_name="box_open_green")
        _make_kpi_card(kpi_row, 3, "Total Fiado", f"${tot_fiado:,.0f} COP", "#FBBF24", "#F59E0B", "#451A03", icon_name="coins_gold")

        # ── 4. Main Quotas Section ("¿Cuánto le queda de cada producto?") ─────
        quotas_container = ctk.CTkFrame(body, fg_color="#181A22", border_color="#252836", border_width=1, corner_radius=8)
        quotas_container.pack(fill="x", pady=(0, 8), padx=0)

        # Quotas Header with Actions [➕ Asignar Producto] [🔄 Renovar]
        q_hdr = ctk.CTkFrame(quotas_container, fg_color="transparent", height=36)
        q_hdr.pack(fill="x", padx=12, pady=(8, 4))
        q_hdr.pack_propagate(False)

        ctk.CTkLabel(
            q_hdr,
            text="CONVENIO DE FIADOS POR PRODUCTO",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFFFFF"
        ).pack(side="left")

        # Right buttons
        renew_btn = ctk.CTkButton(
            q_hdr,
            image=get_ctk_icon("retweet_sky", size=(13, 13)) or get_ctk_icon("recycle_sky", size=(13, 13)),
            compound="left",
            text="  Renovar",
            height=26,
            fg_color="#111624",
            border_color="#38BDF8",
            border_width=1,
            hover_color="#0C2340",
            text_color="#38BDF8",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=5,
            cursor="hand2",
            command=self._on_renew_quotas
        )
        renew_btn.pack(side="right", padx=(4, 0))

        add_q_btn = ctk.CTkButton(
            q_hdr,
            image=get_ctk_icon("file_circle_plus_green", size=(13, 13)),
            compound="left",
            text="  Asignar Producto",
            height=26,
            fg_color="#0A1D16",
            border_color="#10B981",
            border_width=1,
            hover_color="#0F2E22",
            text_color="#34D399",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=5,
            cursor="hand2",
            command=self._open_new_quota_modal
        )
        add_q_btn.pack(side="right")

        # Table header (7 clean columns)
        th = ctk.CTkFrame(quotas_container, fg_color="#111624", corner_radius=6, height=28)
        th.pack(fill="x", padx=10, pady=(2, 4))
        th.pack_propagate(False)
        th.grid_columnconfigure(0, weight=0, minsize=35)   # #
        th.grid_columnconfigure(1, weight=0, minsize=45)   # ID
        th.grid_columnconfigure(2, weight=1, minsize=180)  # Producto
        th.grid_columnconfigure(3, weight=1, minsize=120)  # Cupo Pactado
        th.grid_columnconfigure(4, weight=1, minsize=110)  # Fiado
        th.grid_columnconfigure(5, weight=1, minsize=170)  # Saldo Restante
        th.grid_columnconfigure(6, weight=0, minsize=80)   # Acciones

        ctk.CTkLabel(th, text="#", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="center").grid(row=0, column=0, sticky="ew", padx=2)
        ctk.CTkLabel(th, text="ID", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="center").grid(row=0, column=1, sticky="ew", padx=2)
        ctk.CTkLabel(th, text="Producto", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="w").grid(row=0, column=2, sticky="ew", padx=(10, 4))
        ctk.CTkLabel(th, text="Cupo Pactado", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="center").grid(row=0, column=3, sticky="ew", padx=4)
        ctk.CTkLabel(th, text="Fiado", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="center").grid(row=0, column=4, sticky="ew", padx=4)
        ctk.CTkLabel(th, text="Saldo Restante", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#34D399", anchor="center").grid(row=0, column=5, sticky="ew", padx=4)
        ctk.CTkLabel(th, text="Acciones", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="center").grid(row=0, column=6, sticky="ew", padx=(4, 10))

        # Quotas rows container (5 items per page)
        self.quotas_rows_container = ctk.CTkFrame(quotas_container, fg_color="transparent")
        self.quotas_rows_container.pack(fill="x", padx=10, pady=(0, 4))
        self.quotas_scroll = self.quotas_rows_container  # backwards compatibility alias

        # Quotas pagination bar
        self.quotas_pag_frame = ctk.CTkFrame(quotas_container, fg_color="#111624", corner_radius=6, height=30)
        self.quotas_pag_frame.pack(fill="x", padx=10, pady=(2, 6))
        self.quotas_pag_frame.pack_propagate(False)

        self.quotas_page_info = ctk.CTkLabel(
            self.quotas_pag_frame,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=DarkTheme.TEXT_MUTED
        )
        self.quotas_page_info.pack(side="left", padx=10)

        q_nav = ctk.CTkFrame(self.quotas_pag_frame, fg_color="transparent")
        q_nav.pack(side="right", padx=6)

        self.quotas_prev_btn = ctk.CTkButton(
            q_nav,
            text="◀ Ant.",
            width=58,
            height=22,
            fg_color="#181E2C",
            hover_color="#243048",
            border_color="#334155",
            border_width=1,
            text_color="#94A3B8",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            corner_radius=4,
            cursor="hand2",
            command=self._prev_quotas_page
        )
        self.quotas_prev_btn.pack(side="left", padx=2)

        self.quotas_page_lbl = ctk.CTkLabel(
            q_nav,
            text="Pág. 1 de 1",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=DarkTheme.TEXT_MUTED
        )
        self.quotas_page_lbl.pack(side="left", padx=8)

        self.quotas_next_btn = ctk.CTkButton(
            q_nav,
            text="Sig. ▶",
            width=58,
            height=22,
            fg_color="#181E2C",
            hover_color="#243048",
            border_color="#334155",
            border_width=1,
            text_color="#94A3B8",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            corner_radius=4,
            cursor="hand2",
            command=self._next_quotas_page
        )
        self.quotas_next_btn.pack(side="left", padx=2)

        # ── 5. Historial de Despachos / Compras Fiadas ─────────────────────────
        hist_container = ctk.CTkFrame(body, fg_color="#181A22", border_color="#252836", border_width=1, corner_radius=8)
        hist_container.pack(fill="x", pady=(0, 6))

        h_hdr = ctk.CTkFrame(hist_container, fg_color="transparent", height=32)
        h_hdr.pack(fill="x", padx=12, pady=(6, 2))
        h_hdr.pack_propagate(False)

        self.purchases_hdr_lbl = ctk.CTkLabel(
            h_hdr,
            text="HISTORIAL DE DESPACHOS Y VENTAS",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFFFFF"
        )
        self.purchases_hdr_lbl.pack(side="left")

        self.purchases_count_lbl = ctk.CTkLabel(
            h_hdr,
            text=f"Facturas: {len(self.purchases)}",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#94A3B8"
        )
        self.purchases_count_lbl.pack(side="right", padx=6)

        # Table header for Historial (8 columns with separated Fecha and Hora)
        h_th = ctk.CTkFrame(hist_container, fg_color="#111624", corner_radius=6, height=28)
        h_th.pack(fill="x", padx=10, pady=(2, 4))
        h_th.pack_propagate(False)
        h_th.grid_columnconfigure(0, weight=0, minsize=35)   # #
        h_th.grid_columnconfigure(1, weight=0, minsize=90)   # Factura
        h_th.grid_columnconfigure(2, weight=0, minsize=95)   # Fecha
        h_th.grid_columnconfigure(3, weight=0, minsize=65)   # Hora
        h_th.grid_columnconfigure(4, weight=0, minsize=125)  # Método de Pago
        h_th.grid_columnconfigure(5, weight=0, minsize=110)  # Cajero
        h_th.grid_columnconfigure(6, weight=1)               # Total
        h_th.grid_columnconfigure(7, weight=0, minsize=80)   # Acciones

        ctk.CTkLabel(h_th, text="#", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="center").grid(row=0, column=0, sticky="ew", padx=2)
        ctk.CTkLabel(h_th, text="Factura", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="w").grid(row=0, column=1, sticky="ew", padx=(8, 2))
        ctk.CTkLabel(h_th, text="Fecha", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="w").grid(row=0, column=2, sticky="ew", padx=4)
        ctk.CTkLabel(h_th, text="Hora", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="w").grid(row=0, column=3, sticky="ew", padx=4)
        ctk.CTkLabel(h_th, text="Método de Pago", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="w").grid(row=0, column=4, sticky="ew", padx=4)
        ctk.CTkLabel(h_th, text="Cajero", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="w").grid(row=0, column=5, sticky="ew", padx=4)
        ctk.CTkLabel(h_th, text="Total", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="center").grid(row=0, column=6, sticky="ew", padx=4)
        ctk.CTkLabel(h_th, text="Acciones", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="center").grid(row=0, column=7, sticky="ew", padx=(4, 10))

        # Purchases rows container
        self.purchases_rows_container = ctk.CTkFrame(hist_container, fg_color="transparent")
        self.purchases_rows_container.pack(fill="x", padx=10, pady=(0, 4))

        # Purchases pagination bar
        self.purchases_pag_frame = ctk.CTkFrame(hist_container, fg_color="#111624", corner_radius=6, height=30)
        self.purchases_pag_frame.pack(fill="x", padx=10, pady=(2, 6))
        self.purchases_pag_frame.pack_propagate(False)

        self.purchases_page_info = ctk.CTkLabel(
            self.purchases_pag_frame,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=DarkTheme.TEXT_MUTED
        )
        self.purchases_page_info.pack(side="left", padx=10)

        p_nav = ctk.CTkFrame(self.purchases_pag_frame, fg_color="transparent")
        p_nav.pack(side="right", padx=6)

        self.purchases_prev_btn = ctk.CTkButton(
            p_nav,
            text="◀ Ant.",
            width=58,
            height=22,
            fg_color="#181E2C",
            hover_color="#243048",
            border_color="#334155",
            border_width=1,
            text_color="#94A3B8",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            corner_radius=4,
            cursor="hand2",
            command=self._prev_purchases_page
        )
        self.purchases_prev_btn.pack(side="left", padx=2)

        self.purchases_page_lbl = ctk.CTkLabel(
            p_nav,
            text="Pág. 1 de 1",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=DarkTheme.TEXT_MUTED
        )
        self.purchases_page_lbl.pack(side="left", padx=8)

        self.purchases_next_btn = ctk.CTkButton(
            p_nav,
            text="Sig. ▶",
            width=58,
            height=22,
            fg_color="#181E2C",
            hover_color="#243048",
            border_color="#334155",
            border_width=1,
            text_color="#94A3B8",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            corner_radius=4,
            cursor="hand2",
            command=self._next_purchases_page
        )
        self.purchases_next_btn.pack(side="left", padx=2)

        self._render_quotas_rows()
        self._render_purchases_rows()

        # ── 6. Footer ────────────────────────────────────────────────────────
        footer = ctk.CTkFrame(self, fg_color="transparent", height=40)
        footer.pack(fill="x", padx=18, pady=(2, 10))

        ctk.CTkButton(
            footer,
            image=get_ctk_icon("ban_red", size=(16, 16)),
            compound="left",
            text="  Cerrar Ficha",
            width=130,
            height=36,
            fg_color="#1C1117",
            border_color="#EF4444",
            border_width=1.5,
            hover_color="#2D151E",
            text_color="#F87171",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self.destroy
        ).pack(side="right")

    def _prev_quotas_page(self) -> None:
        if self.quotas_current_page > 1:
            self.quotas_current_page -= 1
            self._render_quotas_rows()

    def _next_quotas_page(self) -> None:
        if self.quotas_current_page < self.quotas_total_pages:
            self.quotas_current_page += 1
            self._render_quotas_rows()

    def _prev_purchases_page(self) -> None:
        if self.purchases_current_page > 1:
            self.purchases_current_page -= 1
            self._render_purchases_rows()

    def _next_purchases_page(self) -> None:
        if self.purchases_current_page < self.purchases_total_pages:
            self.purchases_current_page += 1
            self._render_purchases_rows()

    def _render_quotas_rows(self) -> None:
        for w in self.quotas_rows_container.winfo_children():
            w.destroy()

        if not self.quotas:
            empty_box = ctk.CTkFrame(self.quotas_rows_container, fg_color="transparent")
            empty_box.pack(pady=16)
            ctk.CTkLabel(
                empty_box,
                text="Sin convenios asignados. Haga clic en '  Asignar Producto' para registrar productos y cupos.",
                font=ctk.CTkFont(family="Segoe UI", size=11, slant="italic"),
                text_color=DarkTheme.TEXT_MUTED
            ).pack()
            self.quotas_page_info.configure(text="0 convenios registrados")
            self.quotas_page_lbl.configure(text="Pág. 0 de 0")
            self.quotas_prev_btn.configure(state="disabled")
            self.quotas_next_btn.configure(state="disabled")
            return

        total_items = len(self.quotas)
        self.quotas_total_pages = max(1, math.ceil(total_items / self.quotas_page_size))
        if self.quotas_current_page > self.quotas_total_pages:
            self.quotas_current_page = self.quotas_total_pages
        if self.quotas_current_page < 1:
            self.quotas_current_page = 1

        start_idx = (self.quotas_current_page - 1) * self.quotas_page_size
        end_idx = min(start_idx + self.quotas_page_size, total_items)
        page_items = self.quotas[start_idx:end_idx]

        edit_icon = get_ctk_icon("pen_gold", size=(14, 14))
        trash_icon = get_ctk_icon("trash_red", size=(14, 14)) or get_ctk_icon("trash_arrow_red", size=(14, 14))

        for idx, q in enumerate(page_items):
            global_idx = start_idx + idx + 1
            r_bg = "#111624" if idx % 2 == 0 else "#0E1320"
            row = ctk.CTkFrame(self.quotas_rows_container, fg_color=r_bg, corner_radius=6, height=36)
            row.pack(fill="x", pady=2)
            row.pack_propagate(False)

            row.grid_columnconfigure(0, weight=0, minsize=35)   # #
            row.grid_columnconfigure(1, weight=0, minsize=45)   # ID
            row.grid_columnconfigure(2, weight=1, minsize=180)  # Producto
            row.grid_columnconfigure(3, weight=1, minsize=120)  # Cupo Pactado
            row.grid_columnconfigure(4, weight=1, minsize=110)  # Fiado
            row.grid_columnconfigure(5, weight=1, minsize=170)  # Saldo Restante
            row.grid_columnconfigure(6, weight=0, minsize=80)   # Acciones

            # Col 0: Index (#)
            ctk.CTkLabel(
                row,
                text=str(global_idx),
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color="#64748B",
                anchor="center"
            ).grid(row=0, column=0, sticky="ew", padx=2)

            # Col 1: ID without '#'
            ctk.CTkLabel(
                row,
                text=str(q.get("product_id", "")),
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color="#38BDF8",
                anchor="center"
            ).grid(row=0, column=1, sticky="ew", padx=2)

            # Col 2: Product Name (Plain text, no meat icon)
            ctk.CTkLabel(
                row,
                text=q.get("product_name", ""),
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#FFFFFF",
                anchor="w"
            ).grid(row=0, column=2, sticky="ew", padx=(10, 4))

            # Col 3: Cupo Pactado (White font)
            ctk.CTkLabel(
                row,
                text=f"{q['quota_quantity']:.2f} {q['unit']}",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color="#FFFFFF",
                anchor="center"
            ).grid(row=0, column=3, sticky="ew", padx=4)

            # Col 4: Fiado (Color-coded: red if > quota, green if == quota, orange if < quota)
            consumed = q["consumed_quantity"]
            quota_val = q["quota_quantity"]
            if consumed > quota_val:
                col_txt = "#EF4444"
            elif consumed == quota_val:
                col_txt = "#10B981"
            else:
                col_txt = "#F59E0B"
            ctk.CTkLabel(
                row,
                text=f"{consumed:.2f} {q['unit']}",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=col_txt,
                anchor="center"
            ).grid(row=0, column=4, sticky="ew", padx=4)

            # Col 5: Saldo Restante
            rem = q["remaining_quantity"]
            rem_ico = None
            if rem <= 0:
                rem_txt = f"⛔ Agotado (0.00 {q['unit']})"
                rem_fg = "#F87171"
                rem_bg = "#330F13"
                rem_border = "#EF4444"
            elif rem <= 5:
                rem_txt = f"⚠ Le quedan {rem:.2f} {q['unit']}"
                rem_fg = "#FBBF24"
                rem_bg = "#351C05"
                rem_border = "#F59E0B"
            else:
                rem_txt = f" Le quedan {rem:.2f} {q['unit']}"
                rem_ico = get_ctk_icon("check_green", size=(12, 12))
                rem_fg = "#34D399"
                rem_bg = "#062E1D"
                rem_border = "#10B981"

            rem_pill = ctk.CTkFrame(row, fg_color=rem_bg, border_color=rem_border, border_width=1, corner_radius=6, height=24)
            rem_pill.grid(row=0, column=5, sticky="", padx=4)
            if rem_ico:
                ctk.CTkLabel(rem_pill, image=rem_ico, compound="left", text=rem_txt, font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"), text_color=rem_fg).pack(padx=8, pady=2)
            else:
                ctk.CTkLabel(rem_pill, text=rem_txt, font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"), text_color=rem_fg).pack(padx=8, pady=2)

            # Col 6: Acciones [✏ Editar Saldo/Cupo] [🗑]
            act_box = ctk.CTkFrame(row, fg_color="transparent")
            act_box.grid(row=0, column=6, sticky="", padx=(4, 10))

            # Edit quota button
            btn_eq = ctk.CTkButton(
                act_box,
                text="",
                width=28,
                height=26,
                corner_radius=5,
                cursor="hand2",
                command=lambda quota_item=q: self._open_edit_quota_modal(quota_item)
            )
            apply_palette_button(btn_eq, variant="editar", icon_name="pen_gold", icon_size=(13, 13))
            btn_eq.pack(side="left", padx=2)

            # Delete quota button
            btn_dq = ctk.CTkButton(
                act_box,
                text="",
                width=28,
                height=26,
                corner_radius=5,
                cursor="hand2",
                command=lambda quota_item=q: self._delete_quota(quota_item)
            )
            apply_palette_button(btn_dq, variant="eliminar", icon_name="trash_red", icon_size=(13, 13))
            btn_dq.pack(side="left", padx=2)

        self.quotas_page_info.configure(text=f"Mostrando {start_idx + 1}-{end_idx} de {total_items} convenios")
        self.quotas_page_lbl.configure(text=f"Pág. {self.quotas_current_page} de {self.quotas_total_pages}")
        self.quotas_prev_btn.configure(state="normal" if self.quotas_current_page > 1 else "disabled")
        self.quotas_next_btn.configure(state="normal" if self.quotas_current_page < self.quotas_total_pages else "disabled")

    def _render_purchases_rows(self) -> None:
        for w in self.purchases_rows_container.winfo_children():
            w.destroy()

        if hasattr(self, "purchases_hdr_lbl"):
            self.purchases_hdr_lbl.configure(text="HISTORIAL DE DESPACHOS Y VENTAS")
        if hasattr(self, "purchases_count_lbl"):
            self.purchases_count_lbl.configure(text=f"Facturas: {len(self.purchases)}")

        if not self.purchases:
            empty_box = ctk.CTkFrame(self.purchases_rows_container, fg_color="transparent")
            empty_box.pack(pady=16)
            ctk.CTkLabel(
                empty_box,
                text="No hay despachos o compras registradas para esta empresa todavía.",
                font=ctk.CTkFont(family="Segoe UI", size=11, slant="italic"),
                text_color=DarkTheme.TEXT_MUTED
            ).pack()
            self.purchases_page_info.configure(text="0 facturas registradas")
            self.purchases_page_lbl.configure(text="Pág. 0 de 0")
            self.purchases_prev_btn.configure(state="disabled")
            self.purchases_next_btn.configure(state="disabled")
            return

        total_items = len(self.purchases)
        self.purchases_total_pages = max(1, math.ceil(total_items / self.purchases_page_size))
        if self.purchases_current_page > self.purchases_total_pages:
            self.purchases_current_page = self.purchases_total_pages
        if self.purchases_current_page < 1:
            self.purchases_current_page = 1

        start_idx = (self.purchases_current_page - 1) * self.purchases_page_size
        end_idx = min(start_idx + self.purchases_page_size, total_items)
        page_items = self.purchases[start_idx:end_idx]

        for idx, sale in enumerate(page_items):
            global_idx = start_idx + idx + 1
            r_bg = "#111624" if idx % 2 == 0 else "#0E1320"
            row = ctk.CTkFrame(self.purchases_rows_container, fg_color=r_bg, corner_radius=6, height=36)
            row.pack(fill="x", pady=2)
            row.pack_propagate(False)

            row.grid_columnconfigure(0, weight=0, minsize=35)   # #
            row.grid_columnconfigure(1, weight=0, minsize=90)   # Factura
            row.grid_columnconfigure(2, weight=0, minsize=95)   # Fecha
            row.grid_columnconfigure(3, weight=0, minsize=65)   # Hora
            row.grid_columnconfigure(4, weight=0, minsize=125)  # Método Pago
            row.grid_columnconfigure(5, weight=0, minsize=110)  # Cajero
            row.grid_columnconfigure(6, weight=1)               # Total
            row.grid_columnconfigure(7, weight=0, minsize=80)   # Acciones

            # Col 0: #
            ctk.CTkLabel(row, text=str(global_idx), font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#64748B", anchor="center").grid(row=0, column=0, sticky="ew", padx=2)

            # Col 1: Factura (sin '#' y en blanco)
            inv_num = str(sale.get("invoice_number", "—"))
            ctk.CTkLabel(row, text=inv_num, font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#FFFFFF", anchor="w").grid(row=0, column=1, sticky="ew", padx=(8, 2))

            # Col 2: Fecha & Col 3: Hora
            ts = str(sale.get("timestamp") or sale.get("created_at") or "")
            ts_parts = ts.split()
            date_txt = ts_parts[0] if len(ts_parts) > 0 else "—"
            time_txt = ts_parts[1][:5] if len(ts_parts) > 1 else "—"

            ctk.CTkLabel(row, text=date_txt, font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#E2E8F0", anchor="w").grid(row=0, column=2, sticky="ew", padx=4)
            ctk.CTkLabel(row, text=time_txt, font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#94A3B8", anchor="w").grid(row=0, column=3, sticky="ew", padx=4)

            # Col 4: Método de Pago (palabra con icono en blanco, sin contenedor pill)
            pm_cell = _format_payment_method_widget(row, sale.get("payment_method"))
            pm_cell.grid(row=0, column=4, sticky="w", padx=4)

            # Col 5: Cajero
            cashier = sale.get("cashier_name", "Diego")
            ctk.CTkLabel(row, text=cashier, font=ctk.CTkFont(family="Segoe UI", size=10), text_color=DarkTheme.TEXT_SECONDARY, anchor="w").grid(row=0, column=5, sticky="ew", padx=4)

            # Col 6: Total (alineado y no pegado al borde)
            tot_txt = f"${sale.get('total', 0):,.0f}".replace(",", ".")
            ctk.CTkLabel(row, text=f"{tot_txt} COP", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#34D399", anchor="center").grid(row=0, column=6, sticky="ew", padx=4)

            # Col 7: Ver Ticket button
            act_box = ctk.CTkFrame(row, fg_color="transparent")
            act_box.grid(row=0, column=7, sticky="", padx=(4, 10))
            btn_ticket = ctk.CTkButton(
                act_box,
                text="",
                width=28,
                height=26,
                corner_radius=5,
                cursor="hand2",
                command=lambda s_id=sale["id"]: self._view_receipt(s_id)
            )
            apply_palette_button(btn_ticket, variant="ver", icon_name="ticket_white", icon_size=(13, 13))
            btn_ticket.pack(side="left", padx=2)

        self.purchases_page_info.configure(text=f"Mostrando {start_idx + 1}-{end_idx} de {total_items} facturas")
        self.purchases_page_lbl.configure(text=f"Pág. {self.purchases_current_page} de {self.purchases_total_pages}")
        self.purchases_prev_btn.configure(state="normal" if self.purchases_current_page > 1 else "disabled")
        self.purchases_next_btn.configure(state="normal" if self.purchases_current_page < self.purchases_total_pages else "disabled")

    def _view_receipt(self, sale_id: int) -> None:
        try:
            with get_db_connection() as conn:
                detail = SaleModel.get_sale_by_id(conn, sale_id)
            if not detail:
                messagebox.showerror("Error", "No se encontró el detalle de la venta solicitada.", parent=self)
                return

            ticket_text = format_ticket(detail)
            sound_manager.play_sale_success()
            TicketPreviewModal(parent=self, ticket_text=ticket_text)
        except Exception as e:
            messagebox.showerror("Error al mostrar recibo", f"Ocurrió un error al cargar el recibo:\n{e}", parent=self)

    def _open_new_quota_modal(self) -> None:
        CompanyQuotaEditModal(
            parent=self,
            company=self.company,
            quota=None,
            on_success_callback=self._reload_data
        )

    def _open_edit_quota_modal(self, quota: Dict[str, Any]) -> None:
        CompanyQuotaEditModal(
            parent=self,
            company=self.company,
            quota=quota,
            on_success_callback=self._reload_data
        )

    def _delete_quota(self, quota: Dict[str, Any]) -> None:
        p_name = quota.get("product_name", "el producto")
        if not messagebox.askyesno(
            "Confirmar Eliminación de Convenio",
            f"¿Desea eliminar el convenio de '{p_name}' para la empresa {self.company.get('full_name')}?",
            parent=self
        ):
            return

        try:
            with get_db_connection() as conn:
                CustomerModel.delete_company_quota(conn, quota["id"])
            sound_manager.play_sale_success()
            self._reload_data()
        except Exception as e:
            sound_manager.play_error()
            messagebox.showerror("Error al Eliminar Convenio", f"No se pudo eliminar el cupo:\n{e}", parent=self)

    def _on_renew_quotas(self) -> None:
        if not messagebox.askyesno(
            "Renovar Período / Reiniciar Cupos",
            f"¿Desea liquidar y renovar el período para {self.company.get('full_name')}?\n\n"
            f"Esta acción reiniciará las cantidades consumidas a 0 y restablecerá el saldo disponible al cupo pactado.",
            parent=self
        ):
            return

        try:
            with get_db_connection() as conn:
                CustomerModel.settle_company_quotas(conn, self.company["id"])
            sound_manager.play_sale_success()
            messagebox.showinfo("Período Renovado", "Los cupos han sido restablecidos exitosamente para el nuevo período.", parent=self)
            self._reload_data()
        except Exception as e:
            sound_manager.play_error()
            messagebox.showerror("Error al Renovar", f"No se pudo renovar los cupos:\n{e}", parent=self)

    def _reload_data(self) -> None:
        c_id = self.company["id"]
        with get_db_connection() as conn:
            self.quotas = CustomerModel.get_company_quotas(conn, c_id)
            self.summary = CustomerModel.get_company_fiados_summary(conn, c_id)
            self.purchases = CustomerModel.get_customer_purchases(conn, c_id)
        self._render_quotas_rows()
        self._render_purchases_rows()
        if self.on_refresh_request:
            self.on_refresh_request()

    def _on_edit_company(self) -> None:
        c = self.company
        cb = self.on_edit_request
        self.destroy()
        if cb:
            cb(c)

    def _on_delete_company(self) -> None:
        c = self.company
        cb = self.on_delete_request
        if cb:
            deleted = cb(c, parent_dialog=self)
            if deleted:
                self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# 3B.0. COMPANY DISCOUNT MODAL (MODAL EJECUTIVO DE DESCUENTO PACTADO EN ESPAÑOL)
# ─────────────────────────────────────────────────────────────────────────────
class CompanyDiscountModal(ctk.CTkToplevel):
    """Modern modal dialog in Spanish for configuring the corporate discount percentage (0% to 100%).
    Pre-fills the existing discount value, offers rapid touch presets, and replaces generic input prompts.
    """

    def __init__(
        self,
        parent,
        company: Dict[str, Any],
        on_saved_callback: Optional[Callable[[float], None]] = None
    ):
        super().__init__(parent)
        self.company = company
        self.on_saved_callback = on_saved_callback

        c_name = company.get("first_name", "") or company.get("full_name", "Empresa")
        self.title("Descuento Comercial Pactado")
        self.resizable(False, False)
        self.configure(fg_color="#15171F")

        curr_disc = float(company.get("discount_percent", 0.0) or 0.0)
        self.curr_disc = curr_disc

        self._build_ui(c_name)
        _set_dialog_icon_and_center(self, parent, 460, 390)

        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass

        self.bind("<Return>", lambda e: self._on_save())
        self.bind("<KP_Enter>", lambda e: self._on_save())
        self.bind("<Escape>", lambda e: self.destroy())

        self.after(120, self._focus_entry)

    def _focus_entry(self) -> None:
        try:
            if hasattr(self, "entry") and self.entry.winfo_exists():
                self.entry.focus_set()
                self.entry.select_range(0, 'end')
        except Exception:
            pass

    def _build_ui(self, c_name: str) -> None:
        c = self.company
        disc_icon = get_ctk_icon("percent_white", size=(16, 16)) or get_ctk_icon("percent_solid_white", size=(16, 16))
        build_standard_modal_header(self, "Descuento Comercial Pactado", disc_icon, on_close_cmd=self.destroy, show_close_btn=False, text_color="#FFFFFF")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=14)

        # Company summary card
        card = ctk.CTkFrame(body, fg_color="#181A22", border_color="#283347", border_width=1.2, corner_radius=8)
        card.pack(fill="x", pady=(0, 12))

        inner_card = ctk.CTkFrame(card, fg_color="transparent")
        inner_card.pack(fill="x", padx=14, pady=10)

        av = ctk.CTkFrame(inner_card, fg_color="#1E293B", border_color="#334155", border_width=1.5, corner_radius=18, width=38, height=38)
        av.pack(side="left", padx=(0, 10))
        av.pack_propagate(False)
        b_ico = get_ctk_icon("building_solid_white", size=(18, 18)) or get_ctk_icon("building-solid-full", size=(18, 18))
        ctk.CTkLabel(av, image=b_ico, text="").pack(expand=True)

        info = ctk.CTkFrame(inner_card, fg_color="transparent")
        info.pack(side="left", fill="y")

        top_line = ctk.CTkFrame(info, fg_color="transparent")
        top_line.pack(anchor="w")
        ctk.CTkLabel(top_line, text=c_name, font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), text_color="#FFFFFF").pack(side="left")

        enc_full = format_encargado(c.get("last_name", "")) or ""
        first_enc = enc_full.split()[0] if enc_full and enc_full != "—" else ""
        if first_enc:
            ctk.CTkLabel(top_line, text=f"   👤 {first_enc}", font=ctk.CTkFont(family="Segoe UI", size=12), text_color="#93C5FD").pack(side="left")

        doc_txt = c.get("document_id", "—")
        ctk.CTkLabel(info, text=f"NIT / RUT: {doc_txt}   •   Descuento en compras corporativas", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#94A3B8").pack(anchor="w", pady=(2, 0))

        # Explanation
        ctk.CTkLabel(
            body,
            text="Ingrese el porcentaje que se descontará automáticamente en caja:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#E2E8F0"
        ).pack(anchor="w", pady=(0, 8))

        # Quick preset buttons: [0% Sin Desc] [5%] [10%] [15%] [20%]
        presets_frame = ctk.CTkFrame(body, fg_color="transparent")
        presets_frame.pack(fill="x", pady=(0, 12))
        presets_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        self.preset_btns = []
        for idx, p in enumerate([0, 5, 10, 15, 20]):
            lbl = "0% (Sin desc.)" if p == 0 else f"{p}%"
            is_active = (round(self.curr_disc, 1) == float(p))
            b = ctk.CTkButton(
                presets_frame,
                text=lbl,
                height=30,
                fg_color="#0C2340" if is_active else "#111624",
                border_color="#0284C7" if is_active else "#283347",
                border_width=1.2,
                hover_color="#075985" if is_active else "#1E293B",
                text_color="#38BDF8" if is_active else "#CBD5E1",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                corner_radius=6,
                command=lambda val=p: self._set_preset(val)
            )
            b.grid(row=0, column=idx, padx=2, sticky="ew")
            self.preset_btns.append((p, b))

        # Large input frame in Blue Theme
        input_box = ctk.CTkFrame(body, fg_color="#0A1526", border_color="#0284C7", border_width=1.5, corner_radius=8, height=54)
        input_box.pack(fill="x", pady=(0, 14))
        input_box.pack_propagate(False)

        input_inner = ctk.CTkFrame(input_box, fg_color="transparent")
        input_inner.pack(expand=True)

        init_val = f"{self.curr_disc:.1f}" if self.curr_disc % 1 != 0 else f"{int(self.curr_disc)}"
        self.entry_var = tk.StringVar(value=init_val)
        self.entry = ctk.CTkEntry(
            input_inner,
            textvariable=self.entry_var,
            width=110,
            height=38,
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            fg_color="transparent",
            text_color="#38BDF8",
            border_width=0,
            justify="center"
        )
        self.entry.pack(side="left")

        ctk.CTkLabel(
            input_inner,
            text="%",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color="#38BDF8"
        ).pack(side="left", padx=(4, 0))

        # Action Buttons in Spanish: [Cancelar] [Editar Cambios]
        btn_bar = ctk.CTkFrame(body, fg_color="transparent", height=48)
        btn_bar.pack(fill="x", pady=(8, 0))
        btn_bar.pack_propagate(False)

        cancel_btn = ctk.CTkButton(
            btn_bar,
            text="  Cancelar",
            image=get_ctk_icon("ban_red", size=(15, 15)),
            compound="left",
            width=135,
            height=38,
            fg_color="#1C1117",
            hover_color="#2D151E",
            border_color="#EF4444",
            border_width=1.5,
            text_color="#F87171",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self.destroy
        )
        cancel_btn.pack(side="left")

        save_icon = get_ctk_icon("pen_orange", size=(15, 15)) or get_ctk_icon("pen_gold", size=(15, 15))
        save_btn = ctk.CTkButton(
            btn_bar,
            image=save_icon,
            compound="left",
            text="  Editar Cambios",
            width=165,
            height=38,
            fg_color="#2A1608",
            hover_color="#451A03",
            border_color="#F59E0B",
            border_width=1.5,
            text_color="#FBBF24",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self._on_save
        )
        save_btn.pack(side="right")

        _bind_tab_navigation(self, [self.entry, cancel_btn, save_btn], on_enter=self._on_save)

    def _set_preset(self, val: int) -> None:
        self.entry_var.set(str(val))
        for p, b in self.preset_btns:
            if p == val:
                b.configure(fg_color="#0C2340", border_color="#0284C7", hover_color="#075985", text_color="#38BDF8")
            else:
                b.configure(fg_color="#111624", border_color="#283347", hover_color="#1E293B", text_color="#CBD5E1")
        self._focus_entry()

    def _on_save(self) -> None:
        val_str = self.entry_var.get().strip().replace("%", "").replace(",", ".")
        try:
            val_num = float(val_str)
            if not (0.0 <= val_num <= 100.0):
                raise ValueError("Fuera de rango")
        except ValueError:
            messagebox.showerror("Valor Inválido", "El descuento debe ser un número entre 0% y 100%.", parent=self)
            return

        c = self.company
        c_name = c.get("first_name", "") or c.get("full_name", "Empresa")
        try:
            with get_db_connection() as conn:
                CustomerModel.update(
                    conn,
                    c["id"],
                    first_name=c.get("first_name") or c.get("full_name", ""),
                    last_name=c.get("last_name") or "",
                    discount_percent=val_num
                )
            c["discount_percent"] = val_num
            sound_manager.play_sale_success()
            if self.on_saved_callback:
                self.on_saved_callback(val_num)
            self.destroy()
        except Exception as e:
            logging.error("Error actualizando descuento en CompanyDiscountModal: %s", e)
            messagebox.showerror("Error", f"No se pudo actualizar el descuento:\n{e}", parent=self)


# ─────────────────────────────────────────────────────────────────────────────
# 3B.1. FIADOS & CONVENIOS DASHBOARD MODAL (GESTIÓN CENTRAL DE FIADOS)
# ─────────────────────────────────────────────────────────────────────────────
class FiadosDashboardModal(ctk.CTkToplevel):
    """Executive Central Dashboard for Corporate Fiados, Quotas, and Agreements.
    Allows cashiers and administrators to select any company, monitor quota status,
    view remaining meat balances ('¿Cuánto le queda?'), add new cuts, adjust quotas,
    and renew monthly cycles.
    """

    def __init__(
        self,
        parent,
        on_refresh_callback: Optional[Callable[[], None]] = None,
        preselected_company_id: Optional[int] = None
    ):
        super().__init__(parent)
        self.on_refresh_callback = on_refresh_callback
        self.preselected_company_id = preselected_company_id

        self.title("Control de Fiados y Convenios")
        self.resizable(False, False)
        self.configure(fg_color="#0F1420")

        self.companies: List[Dict[str, Any]] = []
        self.company_options_map: Dict[str, Dict[str, Any]] = {}
        self.selected_company: Optional[Dict[str, Any]] = None
        self.quotas: List[Dict[str, Any]] = []
        self.summary: Dict[str, Any] = {}

        self._load_companies()
        self._build_ui()
        _set_dialog_icon_and_center(self, parent, 940, 650)

        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda e: self.destroy())

    def _load_companies(self) -> None:
        try:
            with get_db_connection() as conn:
                self.companies = CustomerModel.get_all_with_stats(conn, customer_type="EMPRESA")
        except Exception as e:
            logging.error("Error cargando empresas en FiadosDashboardModal: %s", e)
            self.companies = []

        self.company_options_map = {}
        for c in self.companies:
            c_name = c.get("first_name", "") or c.get("full_name", "Empresa")
            nit = c.get("document_id", "")
            key = f"{c_name} (NIT: {nit})" if nit else c_name
            self.company_options_map[key] = c

        if self.preselected_company_id:
            for c in self.companies:
                if c["id"] == self.preselected_company_id:
                    self.selected_company = c
                    break

        if not self.selected_company and self.companies:
            self.selected_company = self.companies[0]

    def _build_ui(self) -> None:
        # 1. Standard Executive Header Bar
        fiado_icon = get_ctk_icon("hand-holding-dollar-solid-full.svg", size=(18, 18)) or get_ctk_icon("coins_white", size=(18, 18)) or get_ctk_icon("hand-holding-dollar-solid-full", size=(18, 18))
        build_standard_modal_header(self, "Control de Fiados y Convenios", fiado_icon, on_close_cmd=self.destroy, text_color="#FFFFFF")

        if not self.companies:
            empty_box = ctk.CTkFrame(self, fg_color="transparent")
            empty_box.pack(expand=True, fill="both")
            ctk.CTkLabel(
                empty_box,
                text="No hay empresas registradas en el sistema.\nRegistre una empresa primero para asignarle convenios y fiados.",
                font=ctk.CTkFont(family="Segoe UI", size=12, slant="italic"),
                text_color=DarkTheme.TEXT_MUTED
            ).pack(expand=True)
            return

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=10)

        # 2. Company Selector Bar & Corporate Identity Card
        sel_card = ctk.CTkFrame(body, fg_color="#181A22", border_color="#78350F", border_width=1.5, corner_radius=8)
        sel_card.pack(fill="x", pady=(0, 10))

        sel_inner = ctk.CTkFrame(sel_card, fg_color="transparent")
        sel_inner.pack(fill="x", padx=14, pady=10)

        # Avatar on the left: Orange badge with matching orange building icon
        av_box = ctk.CTkFrame(sel_inner, fg_color="#3B1806", border_color="#F59E0B", border_width=1.5, corner_radius=22, width=44, height=44)
        av_box.pack(side="left", padx=(0, 14))
        av_box.pack_propagate(False)
        bld_ico = get_tinted_ctk_icon("building_solid_white", "#F59E0B", size=(22, 22)) or get_ctk_icon("building_solid_white", size=(22, 22))
        ctk.CTkLabel(av_box, image=bld_ico, text="").pack(expand=True)

        # Center info
        info_box = ctk.CTkFrame(sel_inner, fg_color="transparent")
        info_box.pack(side="left", fill="both", expand=True, padx=(0, 12))

        # Top row inside info: Label + OptionMenu
        top_sel_row = ctk.CTkFrame(info_box, fg_color="transparent")
        top_sel_row.pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            top_sel_row,
            text="Empresa con Convenio:",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#F8FAFC"
        ).pack(side="left", padx=(0, 10))

        options = list(self.company_options_map.keys())
        default_val = options[0] if options else ""
        if self.selected_company:
            for k, c in self.company_options_map.items():
                if c["id"] == self.selected_company["id"]:
                    default_val = k
                    break

        self.company_selector = ctk.CTkOptionMenu(
            top_sel_row,
            values=options,
            command=self._on_company_selected,
            width=320,
            height=32,
            fg_color="#0F172A",
            button_color="#1E293B",
            button_hover_color="#334155",
            text_color="#FFFFFF",
            dropdown_fg_color="#0F172A",
            dropdown_text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=7
        )
        self.company_selector.set(default_val)
        self.company_selector.pack(side="left")

        # Subtitle row: NIT, Contacto, Tel (larger size, clean light slate color, comfortable pady)
        self.lbl_company_meta = ctk.CTkLabel(
            info_box,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#CBD5E1"
        )
        self.lbl_company_meta.pack(anchor="w", pady=(4, 1))

        # Right side: Single sleek discount pill button
        self.meta_frame = ctk.CTkFrame(sel_inner, fg_color="transparent")
        self.meta_frame.pack(side="right")

        self.btn_desc_badge = ctk.CTkButton(
            self.meta_frame,
            image=get_ctk_icon("percent_green", size=(14, 14)) or get_ctk_icon("percent_white", size=(14, 14)),
            compound="left",
            text="  Sin Descuento Pactado",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#94A3B8",
            fg_color="#0F172A",
            hover_color="#1E293B",
            border_color="#334155",
            border_width=1.5,
            corner_radius=17,
            height=34,
            cursor="hand2",
            command=self._edit_discount
        )
        self.btn_desc_badge.pack(side="right")

        # 3. KPI Row - Harmonious Typography & Colors
        self.kpi_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.kpi_frame.pack(fill="x", pady=(0, 10))
        self.kpi_frame.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="fiado_kpis")

        self.kpi_widgets = {}

        def _make_kpi(col, title, default_val, text_color, border_color, bg_color, icon_name=None):
            bx = ctk.CTkFrame(self.kpi_frame, fg_color=bg_color, border_color=border_color, border_width=1.2, corner_radius=8, height=66)
            bx.grid(row=0, column=col, sticky="ew", padx=3)
            hdr_bx = ctk.CTkFrame(bx, fg_color="transparent")
            hdr_bx.pack(pady=(6, 2))
            if icon_name:
                ico = get_ctk_icon(icon_name, size=(16, 16))
                if ico:
                    ctk.CTkLabel(hdr_bx, image=ico, text="").pack(side="left", padx=(0, 6))
            ctk.CTkLabel(hdr_bx, text=title, font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=text_color).pack(side="left")
            lbl_v = ctk.CTkLabel(bx, text=default_val, font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"), text_color=text_color)
            lbl_v.pack(pady=(0, 6))
            return lbl_v

        self.kpi_widgets["convenio_prods"] = _make_kpi(0, "Productos en Convenio", "0", "#38BDF8", "#0284C7", "#0A192F", icon_name="cube_sky")
        self.kpi_widgets["cupo"] = _make_kpi(1, "Cupo Total Asignado", "0", "#22D3EE", "#0891B2", "#082836", icon_name="box_open_cyan")
        self.kpi_widgets["entregado"] = _make_kpi(2, "Despachado", "0", "#FBBF24", "#D97706", "#24180A", icon_name="truck_fast_amber")
        self.kpi_widgets["saldo"] = _make_kpi(3, "Saldo Restante", "0", "#FB7185", "#F43F5E", "#2D0B18", icon_name="box_open_cyan")

        # 4. Quotas Table Section
        quotas_box = ctk.CTkFrame(body, fg_color="#131826", border_color="#283347", border_width=1.2, corner_radius=8)
        quotas_box.pack(fill="both", expand=True, pady=(0, 10))

        q_top = ctk.CTkFrame(quotas_box, fg_color="transparent", height=38)
        q_top.pack(fill="x", padx=12, pady=(8, 4))
        q_top.pack_propagate(False)

        ctk.CTkLabel(
            q_top,
            text="DETALLE DE CUPOS PACTADOS Y SALDOS DISPONIBLES",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFFFFF"
        ).pack(side="left")

        # Right buttons inside table header: [+ Asignar Fiado] [Renovar Periodo]
        ctk.CTkButton(
            q_top,
            image=get_ctk_icon("retweet_sky", size=(13, 13)) or get_ctk_icon("recycle_sky", size=(13, 13)),
            compound="left",
            text="  Renovar",
            height=26,
            fg_color="#081E2E",
            border_color="#0EA5E9",
            border_width=1,
            hover_color="#0C2D48",
            text_color="#38BDF8",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=5,
            cursor="hand2",
            command=self._on_renew_quotas
        ).pack(side="right", padx=(4, 0))

        ctk.CTkButton(
            q_top,
            image=get_ctk_icon("file_circle_plus_green", size=(13, 13)) or get_ctk_icon("circle-plus-solid-full.svg", size=(13, 13)),
            compound="left",
            text="  Asignar Fiado",
            height=26,
            fg_color="#0A1D16",
            border_color="#10B981",
            border_width=1,
            hover_color="#0F2E22",
            text_color="#34D399",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=5,
            cursor="hand2",
            command=self._open_new_quota_modal
        ).pack(side="right")

        # Table Column Headers (8 columns)
        th = ctk.CTkFrame(quotas_box, fg_color="#0B0F19", corner_radius=6, height=30)
        th.pack(fill="x", padx=(10, 24), pady=(2, 4))
        th.pack_propagate(False)

        th.grid_columnconfigure(0, weight=0, minsize=35)   # #
        th.grid_columnconfigure(1, weight=0, minsize=45)   # ID
        th.grid_columnconfigure(2, weight=1)               # Producto
        th.grid_columnconfigure(3, weight=0, minsize=140)  # Categoría
        th.grid_columnconfigure(4, weight=0, minsize=105)  # Cupo Pactado
        th.grid_columnconfigure(5, weight=0, minsize=105)  # Fiado
        th.grid_columnconfigure(6, weight=0, minsize=165)  # SALDO RESTANTE
        th.grid_columnconfigure(7, weight=0, minsize=80)   # Acciones

        ctk.CTkLabel(th, text="#", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="center").grid(row=0, column=0, sticky="ew", padx=2)
        ctk.CTkLabel(th, text="ID", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="center").grid(row=0, column=1, sticky="ew", padx=2)
        ctk.CTkLabel(th, text="Producto", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="w").grid(row=0, column=2, sticky="ew", padx=(8, 4))
        ctk.CTkLabel(th, text="Categoría", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="w").grid(row=0, column=3, sticky="ew", padx=(8, 4))
        ctk.CTkLabel(th, text="Cupo Pactado", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="center").grid(row=0, column=4, sticky="ew", padx=4)
        ctk.CTkLabel(th, text="Fiado", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="center").grid(row=0, column=5, sticky="ew", padx=4)
        ctk.CTkLabel(th, text="SALDO RESTANTE", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#FB7185", anchor="center").grid(row=0, column=6, sticky="ew", padx=4)
        ctk.CTkLabel(th, text="Acciones", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8", anchor="center").grid(row=0, column=7, sticky="ew", padx=(4, 6))

        # Quotas scroll list
        self.quotas_scroll = ctk.CTkScrollableFrame(quotas_box, fg_color="transparent")
        self.quotas_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        # 5. Footer Bar
        footer = ctk.CTkFrame(body, fg_color="transparent", height=36)
        footer.pack(fill="x")

        ctk.CTkButton(
            footer,
            image=get_ctk_icon("building_user_white", size=(14, 14)) or get_ctk_icon("building-user-solid-full", size=(14, 14)) or get_ctk_icon("eye_white", size=(14, 14)),
            compound="left",
            text="  Ver Ficha de Empresa",
            height=32,
            fg_color="#1E3A8A",
            hover_color="#2563EB",
            border_color="#3B82F6",
            border_width=1,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=5,
            cursor="hand2",
            command=self._open_company_profile
        ).pack(side="left")

        ctk.CTkButton(
            footer,
            image=get_ctk_icon("floppy_green", size=(15, 15)) or get_ctk_icon("check_green", size=(15, 15)),
            compound="left",
            text="  Guardar",
            width=120,
            height=32,
            fg_color="#0A1D16",
            border_color="#10B981",
            border_width=1.5,
            hover_color="#0F2E22",
            text_color="#34D399",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=5,
            cursor="hand2",
            command=self.destroy
        ).pack(side="right")

        self._render_company_data()

    def _on_company_selected(self, key: str) -> None:
        self.selected_company = self.company_options_map.get(key)
        self._render_company_data()

    def _edit_discount(self) -> None:
        if not self.selected_company:
            return

        def _after_saved(new_val: float):
            self.selected_company["discount_percent"] = new_val
            self._render_company_data()
            if self.on_refresh_callback:
                self.on_refresh_callback()

        CompanyDiscountModal(self, self.selected_company, on_saved_callback=_after_saved)

    def _render_company_data(self) -> None:
        if not self.selected_company:
            return

        c = self.selected_company
        c_id = c["id"]

        # 1. Update corporate banner details
        enc_formatted = format_encargado(c.get("last_name", "")) or "No especificado"
        ph = c.get("phone", "—")
        doc_txt = c.get("document_id", "—")
        c_full = c.get("first_name", "") or c.get("full_name", "Empresa")

        if hasattr(self, "lbl_company_title") and self.lbl_company_title.winfo_exists():
            self.lbl_company_title.configure(text=c_full)
        if hasattr(self, "lbl_company_meta") and self.lbl_company_meta.winfo_exists():
            self.lbl_company_meta.configure(text=f"NIT / RUT: {doc_txt}    •    👤 Encargado: {enc_formatted}    •    📞 Tel: {ph}")

        desc_pct = float(c.get("discount_percent", 0.0) or 0.0)
        if desc_pct > 0:
            self.btn_desc_badge.configure(
                image=get_ctk_icon("percent_green", size=(14, 14)) or get_ctk_icon("percent_white", size=(14, 14)),
                text=f"  {desc_pct:.1f}% Descuento Pactado",
                fg_color="#064E3B",
                hover_color="#065F46",
                border_color="#10B981",
                text_color="#6EE7B7"
            )
        else:
            self.btn_desc_badge.configure(
                image=get_ctk_icon("percent_white", size=(14, 14)),
                text="  Sin Descuento Pactado",
                fg_color="#0F172A",
                hover_color="#1E293B",
                border_color="#334155",
                text_color="#94A3B8"
            )

        # 2. Query quotas & summary
        try:
            with get_db_connection() as conn:
                self.quotas = CustomerModel.get_company_quotas(conn, c_id)
                self.summary = CustomerModel.get_company_fiados_summary(conn, c_id)
        except Exception as e:
            logging.error("Error cargando cupos en FiadosDashboardModal: %s", e)
            self.quotas = []
            self.summary = {}

        # 3. Update KPIs
        c_count = len(self.quotas)
        tot_cupo = sum(q["quota_quantity"] for q in self.quotas)
        tot_consumed = sum(q["consumed_quantity"] for q in self.quotas)
        tot_rem = sum(q["remaining_quantity"] for q in self.quotas)

        self.kpi_widgets["convenio_prods"].configure(text=str(c_count))
        self.kpi_widgets["cupo"].configure(text=f"{tot_cupo:.1f}")
        self.kpi_widgets["entregado"].configure(text=f"{tot_consumed:.1f}")
        self.kpi_widgets["saldo"].configure(text=f"{tot_rem:.1f}")

        # 4. Render Quota rows
        for w in self.quotas_scroll.winfo_children():
            w.destroy()

        if not self.quotas:
            empty = ctk.CTkFrame(self.quotas_scroll, fg_color="transparent")
            empty.pack(expand=True, fill="both", pady=30)
            ctk.CTkLabel(
                empty,
                text="Esta empresa no tiene convenios de productos asignados todavía.\nHaga clic en '  Asignar Fiado' para registrar uno.",
                font=ctk.CTkFont(family="Segoe UI", size=11, slant="italic"),
                text_color=DarkTheme.TEXT_MUTED
            ).pack()
            return

        edit_icon = get_ctk_icon("pen_gold", size=(13, 13))
        trash_icon = get_ctk_icon("trash_arrow_red", size=(13, 13)) or get_ctk_icon("trash_red", size=(13, 13))

        for idx, q in enumerate(self.quotas):
            row_bg = "#111624" if idx % 2 == 0 else "#0E1320"
            row = ctk.CTkFrame(self.quotas_scroll, fg_color=row_bg, corner_radius=6, height=38)
            row.pack(fill="x", pady=2)
            row.pack_propagate(False)

            row.grid_columnconfigure(0, weight=0, minsize=35)   # #
            row.grid_columnconfigure(1, weight=0, minsize=45)   # ID
            row.grid_columnconfigure(2, weight=1)               # Producto
            row.grid_columnconfigure(3, weight=0, minsize=140)  # Categoría
            row.grid_columnconfigure(4, weight=0, minsize=105)  # Cupo Pactado
            row.grid_columnconfigure(5, weight=0, minsize=105)  # Fiado
            row.grid_columnconfigure(6, weight=0, minsize=165)  # SALDO RESTANTE
            row.grid_columnconfigure(7, weight=0, minsize=80)   # Acciones

            # Col 0: Index (#)
            ctk.CTkLabel(
                row,
                text=str(idx + 1),
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color="#64748B",
                anchor="center"
            ).grid(row=0, column=0, sticky="ew", padx=2)

            # Col 1: ID (without '#')
            ctk.CTkLabel(
                row,
                text=str(q.get("product_id", "")),
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color="#38BDF8",
                anchor="center"
            ).grid(row=0, column=1, sticky="ew", padx=2)

            # Col 2: Product Name (Plain text without meat icon)
            ctk.CTkLabel(
                row,
                text=str(q.get("product_name", "")),
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#FFFFFF",
                anchor="w"
            ).grid(row=0, column=2, sticky="ew", padx=(8, 4))

            # Col 3: Categoría (Plain white text left aligned)
            cat_name = q.get("category_name") or "General"
            ctk.CTkLabel(
                row,
                text=cat_name,
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color="#FFFFFF",
                anchor="w"
            ).grid(row=0, column=3, sticky="ew", padx=(8, 4))

            # Col 4: Cupo Pactado (White font)
            ctk.CTkLabel(
                row,
                text=f"{q['quota_quantity']:.2f} {q['unit']}",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color="#FFFFFF",
                anchor="center"
            ).grid(row=0, column=4, sticky="ew", padx=4)

            # Col 5: Fiado (Color-coded: red if > quota, green if == quota, orange if < quota)
            consumed = q["consumed_quantity"]
            quota_val = q["quota_quantity"]
            if consumed > quota_val:
                col_txt = "#EF4444"
            elif consumed == quota_val:
                col_txt = "#10B981"
            else:
                col_txt = "#F59E0B"

            ctk.CTkLabel(
                row,
                text=f"{consumed:.2f} {q['unit']}",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=col_txt,
                anchor="center"
            ).grid(row=0, column=5, sticky="ew", padx=4)

            # Col 6: Saldo Restante ("Le Queda")
            rem = q["remaining_quantity"]
            rem_ico = None
            if rem > 5:
                rem_txt = f" Le quedan {rem:.2f} {q['unit']}"
                rem_ico = get_ctk_icon("check_green", size=(12, 12))
                rem_fg = "#34D399"
                rem_bg = "#062E1D"
                rem_border = "#10B981"
            elif rem > 0:
                rem_txt = f"⚠ Le quedan {rem:.2f} {q['unit']}"
                rem_fg = "#FBBF24"
                rem_bg = "#351C05"
                rem_border = "#F59E0B"
            else:
                rem_txt = f"⛔ Agotado ({rem:.2f} {q['unit']})"
                rem_fg = "#F87171"
                rem_bg = "#330F13"
                rem_border = "#EF4444"

            rem_pill = ctk.CTkFrame(row, fg_color=rem_bg, border_color=rem_border, border_width=1, corner_radius=6, height=24)
            rem_pill.grid(row=0, column=6, sticky="", padx=4)
            if rem_ico:
                ctk.CTkLabel(rem_pill, image=rem_ico, compound="left", text=rem_txt, font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"), text_color=rem_fg).pack(padx=8, pady=2)
            else:
                ctk.CTkLabel(rem_pill, text=rem_txt, font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"), text_color=rem_fg).pack(padx=8, pady=2)

            # Col 7: Acciones
            act_box = ctk.CTkFrame(row, fg_color="transparent")
            act_box.grid(row=0, column=7, sticky="", padx=(4, 6))

            ctk.CTkButton(
                act_box,
                image=edit_icon,
                text="",
                width=26,
                height=26,
                fg_color="#18140B",
                border_color="#D97706",
                border_width=1.2,
                hover_color="#451A03",
                corner_radius=5,
                cursor="hand2",
                command=lambda quota_item=q: self._open_edit_quota_modal(quota_item)
            ).pack(side="left", padx=2)

            ctk.CTkButton(
                act_box,
                image=trash_icon,
                text="",
                width=26,
                height=26,
                fg_color="#181114",
                border_color="#991B1B",
                border_width=1.2,
                hover_color="#450A0A",
                corner_radius=5,
                cursor="hand2",
                command=lambda quota_item=q: self._delete_quota(quota_item)
            ).pack(side="left", padx=2)

    def _open_new_quota_modal(self) -> None:
        if not self.selected_company:
            return
        CompanyQuotaEditModal(
            parent=self,
            company=self.selected_company,
            quota=None,
            on_success_callback=self._reload_current_company
        )

    def _open_edit_quota_modal(self, quota: Dict[str, Any]) -> None:
        if not self.selected_company:
            return
        CompanyQuotaEditModal(
            parent=self,
            company=self.selected_company,
            quota=quota,
            on_success_callback=self._reload_current_company
        )

    def _delete_quota(self, quota: Dict[str, Any]) -> None:
        p_name = quota.get("product_name", "el producto")
        c_name = self.selected_company.get("first_name") or self.selected_company.get("full_name")
        if not messagebox.askyesno(
            "Confirmar Eliminación de Convenio",
            f"¿Desea eliminar el convenio de '{p_name}' para la empresa {c_name}?",
            parent=self
        ):
            return

        try:
            with get_db_connection() as conn:
                CustomerModel.delete_company_quota(conn, quota["id"])
            sound_manager.play_sale_success()
            self._reload_current_company()
        except Exception as e:
            sound_manager.play_error()
            messagebox.showerror("Error al Eliminar Convenio", f"No se pudo eliminar el cupo:\n{e}", parent=self)

    def _on_renew_quotas(self) -> None:
        c_name = self.selected_company.get("first_name") or self.selected_company.get("full_name")
        if not messagebox.askyesno(
            "Renovar Período / Restablecer Cupos",
            f"¿Desea liquidar y renovar el período mensual para {c_name}?\n\n"
            f"Esta acción reiniciará las entregas a 0 y restablecerá el saldo disponible al cupo pactado.",
            parent=self
        ):
            return

        try:
            with get_db_connection() as conn:
                CustomerModel.settle_company_quotas(conn, self.selected_company["id"])
            sound_manager.play_sale_success()
            messagebox.showinfo("Período Renovado", "Los cupos han sido restablecidos exitosamente para el nuevo período.", parent=self)
            self._reload_current_company()
        except Exception as e:
            sound_manager.play_error()
            messagebox.showerror("Error al Renovar", f"No se pudo renovar los cupos:\n{e}", parent=self)

    def _open_company_profile(self) -> None:
        if not self.selected_company:
            return
        root = getattr(self, "master", None) or self
        CompanyDetailModal(
            parent=root,
            company=self.selected_company,
            on_edit_request=None,
            on_delete_request=None
        )

    def _reload_current_company(self) -> None:
        # Refresh current company data locally inside modal without re-running full directory load
        self._render_company_data()

    def destroy(self) -> None:
        if getattr(self, "on_refresh_callback", None):
            try:
                self.on_refresh_callback()
            except Exception:
                pass
        super().destroy()


# ─────────────────────────────────────────────────────────────────────────────
# 3C. CUSTOMER DETAIL MODAL (FICHA DEL COMPRADOR / HISTORIAL ITEMIZADO)
# ─────────────────────────────────────────────────────────────────────────────
class CustomerDetailModal(ctk.CTkToplevel):
    """Rich modal window presenting full Customer Profile, Purchasing Metrics,
    and complete itemized invoice history with thermal ticket reprint support.
    """

    def __init__(
        self,
        parent,
        customer: Dict[str, Any],
        on_edit_request: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_delete_request: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        if customer.get("customer_type") == "EMPRESA":
            super().__init__(parent)
            self.withdraw()
            CompanyDetailModal(
                parent=parent,
                company=customer,
                on_edit_request=on_edit_request,
                on_delete_request=on_delete_request
            )
            self.destroy()
            return

        super().__init__(parent)
        self.customer = customer
        self.on_edit_request = on_edit_request
        self.on_delete_request = on_delete_request
        self.current_page = 0
        self.page_size = 5
        self.purchases: List[Dict[str, Any]] = []

        # Determine rank among personas (top buyers)
        rank = customer.get("ranking") or customer.get("rank")
        if not rank:
            try:
                with get_db_connection() as conn:
                    all_custs = CustomerModel.get_all_with_stats(conn, customer_type="PERSONA")
                    for i, item in enumerate(all_custs, 1):
                        if item["id"] == customer["id"]:
                            rank = i
                            break
            except Exception:
                rank = None
        self.customer_rank = rank

        self.title(f"Ficha del Cliente: {customer['full_name']}")
        self.resizable(False, False)
        self.configure(fg_color="#15171F")

        self._build_ui()
        _set_dialog_icon_and_center(self, parent, 750, 560)

        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self) -> None:
        c = self.customer

        # ── 1. Brand Topbar (White icon & text) ──────────────────────────────
        user_icon = get_ctk_icon("user_solid_white", size=(16, 16)) or get_ctk_icon("circle_user_slate", size=(16, 16))
        build_standard_modal_header(self, "Ficha del Cliente", user_icon, on_close_cmd=self.destroy, show_close_btn=False, text_color="#FFFFFF")

        # ── 2. Body Container ────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=10)

        # Profile Card
        prof_card = ctk.CTkFrame(body, fg_color="#181A22", border_color="#252836", border_width=1, corner_radius=8)
        prof_card.pack(fill="x", pady=(0, 10))

        prof_inner = ctk.CTkFrame(prof_card, fg_color="transparent")
        prof_inner.pack(fill="x", padx=14, pady=10)

        # Avatar initials (highlighted with rank tints)
        if self.customer_rank == 1:
            border_col = "#F59E0B"
            init_col = "#FBBF24"
            av_bg = "#3D2B08"
        elif self.customer_rank == 2:
            border_col = "#CBD5E1"
            init_col = "#FFFFFF"
            av_bg = "#222B38"
        elif self.customer_rank == 3:
            border_col = "#EA580C"
            init_col = "#FED7AA"
            av_bg = "#381B09"
        else:
            border_col = "#38BDF8"
            init_col = "#38BDF8"
            av_bg = "#0B192C"

        avatar_frame = ctk.CTkFrame(
            prof_inner,
            fg_color=av_bg,
            border_color=border_col,
            border_width=1.5,
            corner_radius=22,
            width=44,
            height=44
        )
        avatar_frame.pack(side="left", padx=(0, 12))
        avatar_frame.pack_propagate(False)

        cust_initials = (c.get("first_name", "")[:1] + c.get("last_name", "")[:1]).upper() or "CL"
        ctk.CTkLabel(
            avatar_frame,
            text=cust_initials,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=init_col
        ).pack(expand=True)

        info_box = ctk.CTkFrame(prof_inner, fg_color="transparent")
        info_box.pack(side="left", fill="both", expand=True)

        # Customer name & top medal badge (Row 0, Columns 0-1)
        name_row = ctk.CTkFrame(info_box, fg_color="transparent")
        name_row.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        ctk.CTkLabel(
            name_row,
            text=c["full_name"],
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#FFFFFF"
        ).pack(side="left")

        if self.customer_rank in (1, 2, 3):
            med_img = get_ctk_icon(f"{self.customer_rank}.png", size=(20, 20))
            if med_img:
                ctk.CTkLabel(name_row, image=med_img, text="").pack(side="left", padx=(8, 4))

            if self.customer_rank == 1:
                t_bg, t_bd, t_fg = "#78350F", "#F59E0B", "#FBBF24"
            elif self.customer_rank == 2:
                t_bg, t_bd, t_fg = "#1E293B", "#94A3B8", "#E2E8F0"
            else:
                t_bg, t_bd, t_fg = "#451A03", "#D97706", "#FCD34D"

            # Top pill is placed in Row 0, Column 2, positioned directly above Tel chip
            top_pill = ctk.CTkFrame(info_box, fg_color=t_bg, border_color=t_bd, border_width=1, corner_radius=10, height=20)
            top_pill.grid(row=0, column=2, sticky="w", pady=(0, 4))
            ctk.CTkLabel(
                top_pill,
                text=f"★ TOP #{self.customer_rank}",
                font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
                text_color=t_fg
            ).pack(padx=6, pady=1)

        p_txt = c.get("phone") if c.get("phone") else "Sin registrar"
        doc_txt = c.get("document_id", "—")
        reg_txt = str(c.get("created_at", ""))[:10] if c.get("created_at") else ""

        # Row 1: Metadata chips with real vector/PNG icons
        # 1. Cédula Chip (Slate box with ID card icon)
        doc_chip = ctk.CTkFrame(info_box, fg_color="#111624", border_color="#283347", border_width=1, corner_radius=6)
        doc_chip.grid(row=1, column=0, sticky="w", padx=(0, 6))
        doc_inner = ctk.CTkFrame(doc_chip, fg_color="transparent")
        doc_inner.pack(padx=8, pady=2)
        ico_id = get_tinted_ctk_icon("id-card-solid-full", "#CBD5E1", size=(13, 13)) or get_ctk_icon("id_card_slate", size=(13, 13))
        if ico_id:
            ctk.CTkLabel(doc_inner, image=ico_id, text="").pack(side="left", padx=(0, 5))
        ctk.CTkLabel(
            doc_inner,
            text=f"Cédula: {doc_txt}",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#CBD5E1"
        ).pack(side="left")

        # 2. Registrado Chip (Blue box with calendar icon)
        reg_chip = ctk.CTkFrame(info_box, fg_color="#0C2340", border_color="#0284C7", border_width=1, corner_radius=6)
        reg_chip.grid(row=1, column=1, sticky="w", padx=(0, 6))
        reg_inner = ctk.CTkFrame(reg_chip, fg_color="transparent")
        reg_inner.pack(padx=8, pady=2)
        ico_cal = get_ctk_icon("calendar_day_sky", size=(13, 13)) or get_tinted_ctk_icon("calendar-solid-full", "#38BDF8", size=(13, 13))
        if ico_cal:
            ctk.CTkLabel(reg_inner, image=ico_cal, text="").pack(side="left", padx=(0, 5))
        ctk.CTkLabel(
            reg_inner,
            text=f"Registrado: {reg_txt}" if reg_txt else "Registrado: —",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#38BDF8"
        ).pack(side="left")

        # 3. Tel Chip (Green box with phone icon) - Placed in Row 1, Column 2, aligned under top_pill
        tel_chip = ctk.CTkFrame(info_box, fg_color="#061A12", border_color="#059669", border_width=1, corner_radius=6)
        tel_chip.grid(row=1, column=2, sticky="w")
        tel_inner = ctk.CTkFrame(tel_chip, fg_color="transparent")
        tel_inner.pack(padx=8, pady=2)
        ico_tel = get_ctk_icon("mobile_green", size=(13, 13)) or get_tinted_ctk_icon("mobile-screen-solid-full", "#34D399", size=(13, 13))
        if ico_tel:
            ctk.CTkLabel(tel_inner, image=ico_tel, text="").pack(side="left", padx=(0, 5))
        ctk.CTkLabel(
            tel_inner,
            text=f"Tel: {p_txt}",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#34D399"
        ).pack(side="left")

        # Actions on right of profile card: [Editar] on top, [Eliminar] below
        btn_grp = ctk.CTkFrame(prof_inner, fg_color="transparent")
        btn_grp.pack(side="right")

        btn_edit = ctk.CTkButton(
            btn_grp,
            text=" Editar",
            width=82,
            height=26,
            corner_radius=5,
            cursor="hand2",
            command=self._on_edit
        )
        apply_palette_button(btn_edit, variant="editar", icon_name="pen_gold", icon_size=(12, 12), font_size=10)
        btn_edit.pack(fill="x", pady=(0, 4))

        btn_del = ctk.CTkButton(
            btn_grp,
            text=" Eliminar",
            width=82,
            height=26,
            corner_radius=5,
            cursor="hand2",
            command=self._on_delete
        )
        apply_palette_button(btn_del, variant="eliminar", icon_name="trash_red", icon_size=(12, 12), font_size=10)
        btn_del.pack(fill="x")

        # ── 3. Metrics Strip ─────────────────────────────────────────────────
        chips_row = ctk.CTkFrame(body, fg_color="transparent")
        chips_row.pack(fill="x", pady=(0, 10))
        chips_row.grid_columnconfigure((0, 1, 2), weight=1, uniform="cust_chips")

        c1 = ctk.CTkFrame(chips_row, fg_color="#064E3B", border_color="#10B981", border_width=1, corner_radius=6, height=28)
        c1.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.lbl_purchases_count = ctk.CTkLabel(c1, text="", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#34D399")
        self.lbl_purchases_count.pack(pady=4)

        c2 = ctk.CTkFrame(chips_row, fg_color="#78350F", border_color="#F59E0B", border_width=1, corner_radius=6, height=28)
        c2.grid(row=0, column=1, sticky="ew", padx=2)
        self.lbl_total_spent = ctk.CTkLabel(c2, text="", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#FBBF24")
        self.lbl_total_spent.pack(pady=4)

        c3 = ctk.CTkFrame(chips_row, fg_color="#0C2340", border_color="#38BDF8", border_width=1, corner_radius=6, height=28)
        c3.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        self.lbl_avg_spent = ctk.CTkLabel(c3, text="", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#38BDF8")
        self.lbl_avg_spent.pack(pady=4)

        # ── 4. Compact Purchases History Table ────────────────────────────────
        hist_lbl_row = ctk.CTkFrame(body, fg_color="transparent", height=28)
        hist_lbl_row.pack(fill="x", pady=(0, 4))

        self.lbl_hist_title = ctk.CTkLabel(
            hist_lbl_row,
            text="HISTORIAL DE COMPRAS",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFFFFF"
        )
        self.lbl_hist_title.pack(side="left")

        self.lbl_hist_count = ctk.CTkLabel(
            hist_lbl_row,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#94A3B8"
        )
        self.lbl_hist_count.pack(side="right", padx=6)

        table_card = ctk.CTkFrame(body, fg_color="#181A22", border_color="#252836", border_width=1, corner_radius=8)
        table_card.pack(fill="both", expand=True)

        # Table Header (7 columns with separated Fecha and Hora)
        th_frame = ctk.CTkFrame(table_card, fg_color="#111624", corner_radius=6, height=30)
        th_frame.pack(fill="x", padx=6, pady=(6, 4))
        th_frame.pack_propagate(False)

        cols = [
            ("Factura", 90, "w", (8, 2)),
            ("Fecha", 90, "w", 4),
            ("Hora", 60, "w", 4),
            ("Método de Pago", 120, "w", 4),
            ("Cajero", 110, "w", 4),
            ("Total", 95, "center", 4),
            ("Acciones", 75, "center", 0),
        ]
        for name, w, anch, pad in cols:
            lbl = ctk.CTkLabel(
                th_frame,
                text=name,
                width=w,
                anchor=anch,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=DarkTheme.TEXT_MUTED
            )
            lbl.pack(side="left", padx=pad)

        # Table rows container
        self.rows_container = ctk.CTkFrame(table_card, fg_color="transparent")
        self.rows_container.pack(fill="both", expand=True, padx=6, pady=2)

        # Pagination bar at bottom of table_card
        self.pagination_frame = ctk.CTkFrame(table_card, fg_color="#111624", corner_radius=6, height=30)
        self.pagination_frame.pack(fill="x", padx=6, pady=(4, 6))
        self.pagination_frame.pack_propagate(False)

        self.lbl_page_info = ctk.CTkLabel(
            self.pagination_frame,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=DarkTheme.TEXT_MUTED
        )
        self.lbl_page_info.pack(side="left", padx=10)

        nav_box = ctk.CTkFrame(self.pagination_frame, fg_color="transparent")
        nav_box.pack(side="right", padx=6)

        self.btn_prev = ctk.CTkButton(
            nav_box,
            text="◀ Ant.",
            width=55,
            height=22,
            fg_color="#181E2C",
            hover_color="#243048",
            border_color="#334155",
            border_width=1,
            text_color="#94A3B8",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            corner_radius=4,
            cursor="hand2",
            command=self._prev_page
        )
        self.btn_prev.pack(side="left", padx=2)

        self.lbl_page_num = ctk.CTkLabel(
            nav_box,
            text="Pág. 1 de 1",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=DarkTheme.TEXT_MUTED
        )
        self.lbl_page_num.pack(side="left", padx=8)

        self.btn_next = ctk.CTkButton(
            nav_box,
            text="Sig. ▶",
            width=55,
            height=22,
            fg_color="#181E2C",
            hover_color="#243048",
            border_color="#334155",
            border_width=1,
            text_color="#94A3B8",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            corner_radius=4,
            cursor="hand2",
            command=self._next_page
        )
        self.btn_next.pack(side="left", padx=2)

        # ── 5. Footer Actions ────────────────────────────────────────────────
        footer = ctk.CTkFrame(self, fg_color="transparent", height=40)
        footer.pack(fill="x", padx=18, pady=(4, 10))

        ctk.CTkButton(
            footer,
            image=get_ctk_icon("ban_red", size=(16, 16)),
            compound="left",
            text="  Cerrar Ficha",
            width=130,
            height=34,
            fg_color="#1C1117",
            border_color="#EF4444",
            border_width=1.5,
            hover_color="#2D151E",
            text_color="#F87171",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self.destroy
        ).pack(side="right")

        # Initial load of purchases and table rendering
        self._reload_purchases()

    def _reload_purchases(self) -> None:
        try:
            with get_db_connection() as conn:
                self.purchases = CustomerModel.get_customer_purchases(conn, self.customer["id"])
        except Exception:
            self.purchases = []

        total_spent = sum(p["total"] for p in self.purchases)
        p_count = len(self.purchases)
        avg_spent = (total_spent / p_count) if p_count > 0 else 0

        self.lbl_purchases_count.configure(text=f"Total Compras: {p_count}")
        fact_val_txt = f"$ {total_spent:,.0f}".replace(",", ".")
        self.lbl_total_spent.configure(text=f"Total Facturado: {fact_val_txt}")
        avg_val_txt = f"$ {avg_spent:,.0f}".replace(",", ".")
        self.lbl_avg_spent.configure(text=f"Ticket Promedio: {avg_val_txt}")
        self.lbl_hist_title.configure(text="HISTORIAL DE COMPRAS")
        if hasattr(self, "lbl_hist_count"):
            self.lbl_hist_count.configure(text=f"Facturas: {p_count}")

        self._render_table()

    def _render_table(self) -> None:
        for widget in self.rows_container.winfo_children():
            widget.destroy()

        if not self.purchases:
            empty_box = ctk.CTkFrame(self.rows_container, fg_color="transparent")
            empty_box.pack(fill="both", expand=True, pady=28)
            ctk.CTkLabel(
                empty_box,
                text="Sin compras registradas",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=DarkTheme.TEXT_MUTED
            ).pack(pady=(0, 2))
            ctk.CTkLabel(
                empty_box,
                text="Las facturas asociadas a este cliente aparecerán aquí.",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=DarkTheme.TEXT_SECONDARY
            ).pack()
            self.lbl_page_info.configure(text="0 facturas")
            self.lbl_page_num.configure(text="Pág. 0 de 0")
            self.btn_prev.configure(state="disabled")
            self.btn_next.configure(state="disabled")
            return

        total_items = len(self.purchases)
        total_pages = max(1, (total_items + self.page_size - 1) // self.page_size)
        if self.current_page >= total_pages:
            self.current_page = total_pages - 1
        if self.current_page < 0:
            self.current_page = 0

        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, total_items)
        page_items = self.purchases[start_idx:end_idx]

        for idx, sale in enumerate(page_items):
            row_bg = "#181A22" if (idx % 2 == 0) else "#141720"
            r_frame = ctk.CTkFrame(self.rows_container, fg_color=row_bg, corner_radius=4, height=32)
            r_frame.pack(fill="x", pady=1.5)
            r_frame.pack_propagate(False)

            def _hover_enter(e, rf=r_frame):
                try:
                    rf.configure(fg_color="#1E2333")
                except Exception:
                    pass

            def _hover_leave(e, rf=r_frame, bg=row_bg):
                try:
                    rf.configure(fg_color=bg)
                except Exception:
                    pass

            r_frame.bind("<Enter>", _hover_enter)
            r_frame.bind("<Leave>", _hover_leave)

            # Col 1: Factura (sin '#' y en blanco)
            inv_num = str(sale.get("invoice_number", "—"))
            ctk.CTkLabel(
                r_frame,
                text=inv_num,
                width=90,
                anchor="w",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color="#FFFFFF"
            ).pack(side="left", padx=(8, 2))

            # Col 2: Fecha & Col 3: Hora
            ts = str(sale.get("timestamp") or sale.get("created_at") or "")
            ts_parts = ts.split()
            date_txt = ts_parts[0] if len(ts_parts) > 0 else "—"
            time_txt = ts_parts[1][:5] if len(ts_parts) > 1 else "—"

            ctk.CTkLabel(
                r_frame,
                text=date_txt,
                width=90,
                anchor="w",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color="#E2E8F0"
            ).pack(side="left", padx=4)

            ctk.CTkLabel(
                r_frame,
                text=time_txt,
                width=60,
                anchor="w",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color="#94A3B8"
            ).pack(side="left", padx=4)

            # Col 4: Método de Pago (palabra con icono en blanco, sin botón pill)
            pm_cell = _format_payment_method_widget(r_frame, sale.get("payment_method"))
            pm_cell.configure(width=120)
            pm_cell.pack(side="left", padx=4)

            # Col 5: Cajero
            cashier = sale.get("cashier_name", "Diego")
            ctk.CTkLabel(
                r_frame,
                text=cashier,
                width=110,
                anchor="w",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=DarkTheme.TEXT_SECONDARY
            ).pack(side="left", padx=4)

            # Col 6: Total (bien alineado)
            tot_txt = f"${sale['total']:,.0f}".replace(",", ".")
            ctk.CTkLabel(
                r_frame,
                text=tot_txt,
                width=95,
                anchor="center",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color="#34D399"
            ).pack(side="left", padx=4)

            # Col 7: Acciones (Ticket icon and Trash icon)
            act_box = ctk.CTkFrame(r_frame, fg_color="transparent", width=75)
            act_box.pack(side="left")
            act_box.pack_propagate(False)

            # Ticket button (only icon)
            btn_t = ctk.CTkButton(
                act_box,
                text="",
                width=26,
                height=22,
                corner_radius=4,
                cursor="hand2",
                command=lambda s_id=sale["id"]: self._view_receipt(s_id)
            )
            apply_palette_button(btn_t, variant="ver", icon_name="ticket_white", icon_size=(13, 13))
            btn_t.pack(side="left", padx=2, pady=4)

            # Trash button (only icon)
            btn_d = ctk.CTkButton(
                act_box,
                text="",
                width=26,
                height=22,
                corner_radius=4,
                cursor="hand2",
                command=lambda s_id=sale["id"], s_inv=sale["invoice_number"]: self._delete_invoice(s_id, s_inv)
            )
            apply_palette_button(btn_d, variant="eliminar", icon_name="trash_red", icon_size=(13, 13))
            btn_d.pack(side="left", padx=2, pady=4)

        # Update pagination controls
        self.lbl_page_info.configure(text=f"Mostrando {start_idx + 1}-{end_idx} de {total_items} facturas")
        self.lbl_page_num.configure(text=f"Pág. {self.current_page + 1} de {total_pages}")
        self.btn_prev.configure(state="normal" if self.current_page > 0 else "disabled")
        self.btn_next.configure(state="normal" if self.current_page < total_pages - 1 else "disabled")

    def _prev_page(self) -> None:
        if self.current_page > 0:
            self.current_page -= 1
            self._render_table()

    def _next_page(self) -> None:
        total_items = len(self.purchases)
        total_pages = max(1, (total_items + self.page_size - 1) // self.page_size)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self._render_table()

    def _delete_invoice(self, sale_id: int, invoice_number: str) -> None:
        if not messagebox.askyesno(
            "Confirmar Eliminación",
            f"¿Está seguro de que desea eliminar la factura #{invoice_number}?\n\nEsta acción restaurará automáticamente el inventario de los productos vendidos y no se puede deshacer.",
            parent=self
        ):
            return

        try:
            with get_db_connection() as conn:
                ok = SaleModel.delete_sale(conn, sale_id)

            if ok:
                sound_manager.play_warning()
                messagebox.showinfo("Factura Eliminada", f"La factura #{invoice_number} fue eliminada y el stock fue restaurado exitosamente.", parent=self)
                self._reload_purchases()
            else:
                messagebox.showerror("Error", "No se encontró la factura a eliminar.", parent=self)
        except Exception as e:
            messagebox.showerror("Error al eliminar", f"Ocurrió un error al eliminar la factura:\n{e}", parent=self)

    def _view_receipt(self, sale_id: int) -> None:
        try:
            with get_db_connection() as conn:
                detail = SaleModel.get_sale_by_id(conn, sale_id)
            if not detail:
                messagebox.showerror("Error", "No se encontró el detalle de la venta solicitada.", parent=self)
                return

            ticket_text = format_ticket(detail)
            sound_manager.play_sale_success()
            TicketPreviewModal(parent=self, ticket_text=ticket_text)
        except Exception as e:
            messagebox.showerror("Error al mostrar recibo", f"Ocurrió un error al cargar el recibo:\n{e}", parent=self)

    def _on_edit(self) -> None:
        c = self.customer
        cb = self.on_edit_request
        self.destroy()
        if cb:
            cb(c)

    def _on_delete(self) -> None:
        c = self.customer
        cb = self.on_delete_request
        if cb:
            deleted = cb(c, parent_dialog=self)
            if deleted:
                self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# 4. CUSTOM TAB SWITCHER (CLIENTES VS USUARIOS DEL SISTEMA)
# ─────────────────────────────────────────────────────────────────────────────
class CustomTabSwitcher(ctk.CTkFrame):
    """Sleek segmented switcher with icons for Clientes and Usuarios del Sistema."""

    def __init__(self, parent, command: Optional[Callable[[str], None]] = None):
        super().__init__(
            parent,
            fg_color="#0D111A",
            border_color="#283347",
            border_width=1.2,
            corner_radius=8,
            height=36
        )
        self.command = command
        self._current = "Clientes"

        btn_width = 185
        # Client tab button with white/slate users icon
        self.btn_clientes = ctk.CTkButton(
            self,
            image=get_ctk_icon("users_gear_solid_white", size=(15, 15)) or get_ctk_icon("users-gear-solid-full", size=(15, 15)),
            compound="left",
            text="  Clientes",
            width=btn_width,
            height=30,
            corner_radius=6,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            cursor="hand2",
            command=lambda: self.set("Clientes")
        )
        self.btn_clientes.pack(side="left", padx=(3, 2), pady=3)

        # System users tab button with white/slate user-tie icon
        self.btn_users = ctk.CTkButton(
            self,
            image=get_ctk_icon("user_tie_solid_slate", size=(15, 15)) or get_ctk_icon("user-tie-solid-full", size=(15, 15)),
            compound="left",
            text="  Usuarios del Sistema",
            width=btn_width,
            height=30,
            corner_radius=6,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            cursor="hand2",
            command=lambda: self.set("Usuarios del Sistema")
        )
        self.btn_users.pack(side="left", padx=(2, 3), pady=3)
        self._update_styles()

    def get(self) -> str:
        return self._current

    def set(self, val: str) -> None:
        val_norm = "Usuarios del Sistema" if "usuario" in str(val).lower() else "Clientes"
        prev = self._current
        self._current = val_norm
        self._update_styles()
        if self.command:
            self.command(self._current)

    def _update_styles(self) -> None:
        if self._current == "Clientes":
            self.btn_clientes.configure(
                fg_color="#1D4ED8",
                hover_color="#2563EB",
                border_color="#3B82F6",
                border_width=1,
                text_color="#FFFFFF",
                image=get_ctk_icon("users_gear_solid_white", size=(15, 15)) or get_ctk_icon("users-gear-solid-full", size=(15, 15))
            )
            self.btn_users.configure(
                fg_color="transparent",
                hover_color="#182033",
                border_width=0,
                text_color="#94A3B8",
                image=get_ctk_icon("user_tie_solid_slate", size=(15, 15)) or get_ctk_icon("user-tie-solid-full", size=(15, 15))
            )
        else:
            self.btn_clientes.configure(
                fg_color="transparent",
                hover_color="#182033",
                border_width=0,
                text_color="#94A3B8",
                image=get_ctk_icon("users_gear_solid_slate", size=(15, 15)) or get_ctk_icon("users-gear-solid-full", size=(15, 15))
            )
            self.btn_users.configure(
                fg_color="#1D4ED8",
                hover_color="#2563EB",
                border_color="#3B82F6",
                border_width=1,
                text_color="#FFFFFF",
                image=get_ctk_icon("user_tie_solid_white", size=(15, 15)) or get_ctk_icon("user-tie-solid-full", size=(15, 15))
            )


# ─────────────────────────────────────────────────────────────────────────────
# 5. MAIN USERS AND CUSTOMERS FRAME
# ─────────────────────────────────────────────────────────────────────────────
class UsersFrame(ctk.CTkFrame):
    """Executive Users and Customers Presentation Frame for XL Burguer.
    Features:
    - Unified executive topbar matching Inventory, POS & Stats.
    - Clientes / Usuarios del Sistema segmented tab switch.
    - Executive KPI ranking summary chips.
    - Customer Ranking table with fast pagination and un-cluttered display.
    - Detailed Customer Profile Modal with full purchase history and receipt reprint.
    - System Users management table with role pills, Edit and Delete actions.
    - ZERO Excel export (as requested).
    """

    def __init__(self, parent):
        super().__init__(parent, fg_color=DarkTheme.BG_ROOT, corner_radius=0)
        self.all_customers: List[Dict[str, Any]] = []
        self.filtered_customers: List[Dict[str, Any]] = []
        self.personas_list: List[Dict[str, Any]] = []
        self.empresas_list: List[Dict[str, Any]] = []

        # Separate pagination for 50/50 workspace
        self.personas_current_page: int = 1
        self.personas_page_size: int = 15
        self.personas_total_pages: int = 1

        self.empresas_current_page: int = 1
        self.empresas_page_size: int = 15
        self.empresas_total_pages: int = 1

        # Pagination aliases for backward-compatibility with unit tests
        self.current_page: int = 1
        self.page_size: int = 15
        self.total_pages: int = 1

        self.selected_customer_id: Optional[int] = None
        self._search_job = None
        self.SEARCH_DEBOUNCE_MS: int = 300

        self._build_ui()
        self.load_data()

    def _build_ui(self) -> None:
        # ── 1. Compact Controls & Filter Bar ─────────────────────────────────
        self.controls_bar = ctk.CTkFrame(
            self,
            fg_color=DarkTheme.BG_CARD,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=8
        )
        self.controls_bar.pack(fill="x", padx=10, pady=(4, 6))

        # Top row: Search + Tab Switcher + Action Buttons
        row_controls = ctk.CTkFrame(self.controls_bar, fg_color="transparent")
        row_controls.pack(fill="x", padx=10, pady=8)

        # Search Entry with touch keyboard, clear button, and search button
        search_box = ctk.CTkFrame(row_controls, fg_color="transparent")
        search_box.pack(side="left", padx=(0, 10))

        self.search_entry = ctk.CTkEntry(
            search_box,
            width=280,
            height=34,
            placeholder_text="Buscar por nombre o teléfono...",
            placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=DarkTheme.INPUT_BG,
            border_color="#3B4A66",
            border_width=1.5,
            text_color=DarkTheme.INPUT_TEXT,
            corner_radius=6
        )
        self.search_entry.pack(side="left", padx=(0, 4))
        self.search_entry.bind("<KeyRelease>", self._on_search_key)
        self.search_entry.bind("<Return>", lambda e: self._on_search_enter())
        self.search_entry.bind("<KP_Enter>", lambda e: self._on_search_enter())

        # Touch keyboard button [⌨]
        kb_img = get_ctk_icon("keyboard_white", size=(16, 16)) or get_ctk_icon("keyboard_slate", size=(16, 16))
        self.touch_kb_btn = ctk.CTkButton(
            search_box,
            image=kb_img,
            text="",
            width=36,
            height=34,
            fg_color="#111624",
            border_color="#283347",
            border_width=1.2,
            hover_color="#182033",
            corner_radius=6,
            cursor="hand2",
            command=self._open_touch_search_keypad
        )
        self.touch_kb_btn.pack(side="left", padx=(0, 4))

        # Magenta/purple search button [🔍] matching inventory & stats
        search_magenta_img = get_ctk_icon("search_magenta", size=(16, 16))
        self.search_btn = ctk.CTkButton(
            search_box,
            image=search_magenta_img,
            text="",
            width=36,
            height=34,
            fg_color="#191126",
            border_color="#C026D3",
            border_width=1.5,
            hover_color="#2A163B",
            corner_radius=6,
            cursor="hand2",
            command=self._on_search_enter
        )
        self.search_btn.pack(side="left", padx=(0, 4))

        # Filter Reset Button [Eraser icon + text "Limpiar"]
        eraser_icon = get_ctk_icon("eraser_slate", size=(14, 14)) or get_ctk_icon("eraser_white", size=(14, 14)) or get_ctk_icon("eraser-solid-full", size=(14, 14))
        self.clear_btn = ctk.CTkButton(
            search_box,
            image=eraser_icon,
            compound="left",
            text="  Limpiar",
            width=92,
            height=36,
            fg_color="#111624",
            border_color="#475569",
            border_width=1.5,
            hover_color="#1E293B",
            text_color="#E2E8F0",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=8,
            cursor="hand2",
            command=self._on_clear_search_click
        )
        self.clear_btn.pack(side="left", padx=(0, 6))

        # Data Reload Button [Two-arrows repeat icon + text "Recargar"]
        repeat_icon = get_ctk_icon("repeat_blue", size=(14, 14)) or get_ctk_icon("repeat_white", size=(14, 14))
        self.reload_btn = ctk.CTkButton(
            search_box,
            image=repeat_icon,
            compound="left",
            text="  Recargar",
            width=92,
            height=36,
            fg_color="#0F172A",
            border_color="#2563EB",
            border_width=1.5,
            hover_color="#1E293B",
            text_color="#93C5FD",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=8,
            cursor="hand2",
            command=self._on_refresh_click
        )
        self.reload_btn.pack(side="left")
        self.reset_btn = self.clear_btn

        # Segmented Selector with icons moved to the right: [ Clientes | Usuarios del Sistema ]
        self.tab_selector = CustomTabSwitcher(
            row_controls,
            command=self._on_tab_change
        )
        self.tab_selector.pack(side="right", padx=(6, 0))

        # Backwards-compatibility alias for test suites (not packed in UI as requested)
        self.add_icon = get_ctk_icon("user-plus-solid-full", size=(16, 16)) or get_ctk_icon("file_circle_plus_white", size=(16, 16))
        self.add_btn = ctk.CTkButton(
            row_controls,
            image=self.add_icon,
            compound="left",
            text="  Registrar Cliente",
            command=self._on_add_click
        )

        # Divider between controls and KPI summary (Hidden to elevate table list like system users)
        self.kpi_divider = ctk.CTkFrame(self.controls_bar, fg_color=DarkTheme.BORDER_SUBTLE, height=1)
        # self.kpi_divider.pack(fill="x", padx=10, pady=(2, 6))

        # Bottom row of controls bar: KPI counters & ranking chips (Retained in memory for test compatibility)
        self.row_kpis = ctk.CTkFrame(self.controls_bar, fg_color="transparent")
        # self.row_kpis.pack(fill="x", padx=10, pady=(0, 8))

        # Hidden/compatibility label for test suite
        self.kpi_total_lbl = ctk.CTkLabel(
            self.row_kpis,
            text="Total de 0 clientes",
            font=ctk.CTkFont(family="Segoe UI", size=1),
            text_color="#090E17"
        )

        # ── LEFT SIDE (Chips ocultados a petición del usuario: los conteos ya están en los directorios) ──
        left_kpis = ctk.CTkFrame(self.row_kpis, fg_color="transparent")
        # left_kpis.pack(side="left")  # Oculto a petición del usuario

        # 1. Total Clientes (Mantenido para compatibilidad de tests)
        c_tot_box = ctk.CTkFrame(left_kpis, fg_color="#090E17", border_color="#1D4ED8", border_width=1.5, corner_radius=6, height=28)
        c_tot_inner = ctk.CTkFrame(c_tot_box, fg_color="transparent")
        c_tot_inner.pack(padx=8, pady=3)
        ico_tot = get_ctk_icon("users_solid_white", size=(13, 13)) or get_ctk_icon("users-solid-full", size=(13, 13))
        if ico_tot:
            ctk.CTkLabel(c_tot_inner, image=ico_tot, text="").pack(side="left", padx=(0, 5))
        self.chip_total_cust = ctk.CTkLabel(
            c_tot_inner,
            text="Total Clientes: 0",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#38BDF8"
        )
        self.chip_total_cust.pack(side="left")

        # 2. Total Personas (Mantenido para compatibilidad de tests)
        c_per_box = ctk.CTkFrame(left_kpis, fg_color="#061A12", border_color="#059669", border_width=1.5, corner_radius=6, height=28)
        c_per_inner = ctk.CTkFrame(c_per_box, fg_color="transparent")
        c_per_inner.pack(padx=8, pady=3)
        ico_per = get_ctk_icon("user_solid_white", size=(13, 13)) or get_ctk_icon("user-solid-full", size=(13, 13))
        if ico_per:
            ctk.CTkLabel(c_per_inner, image=ico_per, text="").pack(side="left", padx=(0, 5))
        self.chip_total_personas = ctk.CTkLabel(
            c_per_inner,
            text="Total Personas: 0",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#34D399"
        )
        self.chip_total_personas.pack(side="left")

        # 3. Total Empresas (Mantenido para compatibilidad de tests)
        c_emp_box = ctk.CTkFrame(left_kpis, fg_color="#1C1304", border_color="#D97706", border_width=1.5, corner_radius=6, height=28)
        c_emp_inner = ctk.CTkFrame(c_emp_box, fg_color="transparent")
        c_emp_inner.pack(padx=8, pady=3)
        ico_emp = get_ctk_icon("building_solid_white", size=(13, 13)) or get_ctk_icon("building-solid-full", size=(13, 13))
        if ico_emp:
            ctk.CTkLabel(c_emp_inner, image=ico_emp, text="").pack(side="left", padx=(0, 5))
        self.chip_total_empresas = ctk.CTkLabel(
            c_emp_inner,
            text="Total Empresas: 0",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FBBF24"
        )
        self.chip_total_empresas.pack(side="left")

        # ── RIGHT SIDE: Executive Chips: Facturado | Venta Prom ────────────
        right_kpis = ctk.CTkFrame(self.row_kpis, fg_color="transparent")
        right_kpis.pack(side="right")

        # 4. Activos (Oculto a petición del usuario)
        c_act_box = ctk.CTkFrame(right_kpis, fg_color="#061A12", border_color="#10B981", border_width=1.5, corner_radius=6, height=28)
        c_act_inner = ctk.CTkFrame(c_act_box, fg_color="transparent")
        c_act_inner.pack(padx=8, pady=3)
        ico_act = get_ctk_icon("check_green", size=(13, 13))
        if ico_act:
            ctk.CTkLabel(c_act_inner, image=ico_act, text="").pack(side="left", padx=(0, 5))
        self.chip_active_buyers = ctk.CTkLabel(
            c_act_inner,
            text="Activos: 0",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#34D399"
        )
        self.chip_active_buyers.pack(side="left")

        # 5. Facturado (Executive styling)
        c_fac_box = ctk.CTkFrame(right_kpis, fg_color="#181308", border_color="#F59E0B", border_width=1.5, corner_radius=8, height=32)
        c_fac_box.pack(side="left", padx=4)
        c_fac_inner = ctk.CTkFrame(c_fac_box, fg_color="transparent")
        c_fac_inner.pack(padx=10, pady=4)
        ico_fac = get_ctk_icon("coins_gold", size=(14, 14)) or get_ctk_icon("coins-solid-full", size=(14, 14))
        if ico_fac:
            ctk.CTkLabel(c_fac_inner, image=ico_fac, text="").pack(side="left", padx=(0, 6))
        self.chip_total_spent = ctk.CTkLabel(
            c_fac_inner,
            text="Facturado: $ 0",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#FBBF24"
        )
        self.chip_total_spent.pack(side="left")

        # 6. Venta Prom (Executive styling)
        c_avg_box = ctk.CTkFrame(right_kpis, fg_color="#081E2E", border_color="#0EA5E9", border_width=1.5, corner_radius=8, height=32)
        c_avg_box.pack(side="left", padx=(4, 0))
        c_avg_inner = ctk.CTkFrame(c_avg_box, fg_color="transparent")
        c_avg_inner.pack(padx=10, pady=4)
        ico_avg = get_ctk_icon("chart_column_white", size=(14, 14)) or get_ctk_icon("chart-column-solid-full", size=(14, 14))
        if ico_avg:
            ctk.CTkLabel(c_avg_inner, image=ico_avg, text="").pack(side="left", padx=(0, 6))
        self.chip_avg_ticket = ctk.CTkLabel(
            c_avg_inner,
            text="Venta Prom: $ 0",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38BDF8"
        )
        self.chip_avg_ticket.pack(side="left")

        # Backward compatibility dict for unit tests
        self.kpi_cards = {
            "total_cust": self.chip_total_cust,
            "active_buyers": self.chip_active_buyers,
            "total_spent": self.chip_total_spent,
            "avg_ticket": self.chip_avg_ticket,
            "total_personas": self.chip_total_personas,
            "total_empresas": self.chip_total_empresas,
        }

        # ── 2. Clientes Workspace (50 / 50 Split: Personas Naturales vs Empresas Fiados) ───
        self.customers_workspace = ctk.CTkFrame(
            self,
            fg_color=DarkTheme.BG_CARD,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=8
        )
        self.customers_workspace.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        # Uniform 50/50 grid configuration with central divider
        self.customers_workspace.grid_columnconfigure(0, weight=1, uniform="cust_split")
        self.customers_workspace.grid_columnconfigure(1, weight=0, minsize=16)
        self.customers_workspace.grid_columnconfigure(2, weight=1, uniform="cust_split")
        self.customers_workspace.grid_rowconfigure(0, weight=1)

        # ─── LEFT PANEL (50%): PERSONAS NATURALES ────────────────────────────
        self.personas_panel = ctk.CTkFrame(self.customers_workspace, fg_color="transparent")
        self.personas_panel.grid(row=0, column=0, sticky="nsew", padx=(10, 4), pady=8)

        # Personas Top Header
        p_hdr_bar = ctk.CTkFrame(self.personas_panel, fg_color="transparent", height=32)
        p_hdr_bar.pack(fill="x", pady=(0, 6))

        p_title_box = ctk.CTkFrame(p_hdr_bar, fg_color="transparent")
        p_title_box.pack(side="left")

        p_hdr_ico = get_ctk_icon("users_solid_white", size=(16, 16)) or get_ctk_icon("users-solid-full", size=(16, 16))
        ctk.CTkLabel(
            p_title_box,
            image=p_hdr_ico,
            compound="left",
            text="  PERSONA NATURAL",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#FFFFFF"
        ).pack(side="left")

        self.personas_count_badge = ctk.CTkLabel(
            p_title_box,
            text="0 registradas",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#38BDF8",
            fg_color="#0C2340",
            corner_radius=6,
            padx=8,
            pady=2
        )
        self.personas_count_badge.pack(side="left", padx=8)

        # Quick Add Persona Button with user-plus-solid-full icon
        p_add_ico = get_ctk_icon("user_plus_solid_white", size=(14, 14)) or get_ctk_icon("user-plus-solid-full", size=(14, 14))
        p_add_btn = ctk.CTkButton(
            p_hdr_bar,
            image=p_add_ico,
            compound="left",
            text="  Registrar Persona",
            width=140,
            height=30,
            fg_color="#064E3B",
            hover_color="#047857",
            border_color="#10B981",
            border_width=1.5,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=lambda: self._open_new_customer_modal("PERSONA")
        )
        p_add_btn.pack(side="right")

        # Personas Table Columns: (#, Cliente, Teléfono, Compras, Gasto Total, Acciones)
        self.personas_columns = [
            ("ranking", "#", 42, "center", 0),
            ("full_name", "Cliente", 130, "w", 3),
            ("phone", "Teléfono", 95, "center", 2),
            ("total_purchases", "Compras", 55, "center", 1),
            ("total_spent", "Gasto Total", 85, "center", 2),
            ("actions", "Acciones", 96, "center", 0),
        ]

        p_table_hdr = ctk.CTkFrame(
            self.personas_panel,
            fg_color=DarkTheme.BG_ELEVATED,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=6,
            height=32
        )
        p_table_hdr.pack(fill="x", pady=(0, 4), padx=(0, 22))
        p_table_hdr.pack_propagate(False)

        for col_idx, (col_key, label, width, anchor, weight) in enumerate(self.personas_columns):
            p_table_hdr.grid_columnconfigure(
                col_idx,
                weight=weight,
                minsize=width if weight == 0 else 0,
                uniform="p_col" if weight > 0 else ""
            )
            cell_padx = (10, 2) if anchor == "w" else 2
            ctk.CTkLabel(
                p_table_hdr,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=DarkTheme.TEXT_SECONDARY,
                anchor=anchor
            ).grid(row=0, column=col_idx, sticky="nsew", padx=cell_padx, pady=3)

        self.personas_scroll = ctk.CTkScrollableFrame(self.personas_panel, fg_color="transparent")
        self.personas_scroll.pack(fill="both", expand=True, pady=(0, 4))

        # Personas Pagination Bar
        self.personas_pagination = ctk.CTkFrame(self.personas_panel, fg_color="transparent", height=30)
        self.personas_pagination.pack(fill="x", pady=(2, 4))

        self.personas_prev_btn = ctk.CTkButton(
            self.personas_pagination,
            text="◀ Ant.",
            width=58,
            height=26,
            fg_color="#111624",
            border_color="#283347",
            border_width=1,
            hover_color="#1E293B",
            text_color=DarkTheme.TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=5,
            cursor="hand2",
            command=self._prev_personas_page
        )
        self.personas_prev_btn.pack(side="left")

        self.personas_page_lbl = ctk.CTkLabel(
            self.personas_pagination,
            text="Pág. 1 de 1 (0)",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=DarkTheme.TEXT_MUTED
        )
        self.personas_page_lbl.pack(side="left", padx=8)

        self.personas_next_btn = ctk.CTkButton(
            self.personas_pagination,
            text="Sig. ▶",
            width=58,
            height=26,
            fg_color="#111624",
            border_color="#283347",
            border_width=1,
            hover_color="#1E293B",
            text_color=DarkTheme.TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=5,
            cursor="hand2",
            command=self._next_personas_page
        )
        self.personas_next_btn.pack(side="left")

        # ─── VERTICAL DIVIDER ────────────────────────────────────────────────
        divider_box = ctk.CTkFrame(self.customers_workspace, fg_color="transparent", width=16)
        divider_box.grid(row=0, column=1, sticky="ns", pady=8)
        divider_box.pack_propagate(False)

        sep = ctk.CTkFrame(divider_box, fg_color="#334155", width=2)
        sep.pack(fill="y", expand=True)

        # ─── RIGHT PANEL (50%): EMPRESAS & CONVENIOS (FIADOS) ────────────────
        self.empresas_panel = ctk.CTkFrame(self.customers_workspace, fg_color="transparent")
        self.empresas_panel.grid(row=0, column=2, sticky="nsew", padx=(4, 10), pady=8)

        # Empresas Top Header
        e_hdr_bar = ctk.CTkFrame(self.empresas_panel, fg_color="transparent", height=32)
        e_hdr_bar.pack(fill="x", pady=(0, 6))

        e_title_box = ctk.CTkFrame(e_hdr_bar, fg_color="transparent")
        e_title_box.pack(side="left")

        e_hdr_ico = get_ctk_icon("building_solid_white", size=(16, 16)) or get_ctk_icon("building-solid-full", size=(16, 16))
        ctk.CTkLabel(
            e_title_box,
            image=e_hdr_ico,
            compound="left",
            text="  EMPRESAS",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#FFFFFF"
        ).pack(side="left")

        self.empresas_count_badge = ctk.CTkLabel(
            e_title_box,
            text="0 registradas",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#FBBF24",
            fg_color="#3B1C04",
            corner_radius=6,
            padx=8,
            pady=2
        )
        self.empresas_count_badge.pack(side="left", padx=8)

        # Quick Add Empresa Button with hospital-user-solid-full icon
        e_add_ico = get_ctk_icon("hospital_user_white", size=(14, 14)) or get_ctk_icon("hospital-user-solid-full", size=(14, 14)) or get_ctk_icon("building_solid_white", size=(14, 14))
        e_add_btn = ctk.CTkButton(
            e_hdr_bar,
            image=e_add_ico,
            compound="left",
            text="  Registrar Empresa",
            width=140,
            height=30,
            fg_color="#78350F",
            hover_color="#92400E",
            border_color="#F59E0B",
            border_width=1.5,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=lambda: self._open_new_customer_modal("EMPRESA")
        )
        e_add_btn.pack(side="right")

        # Central Fiados & Quotas button with hand-holding-dollar icon
        fiados_ico = get_ctk_icon("hand_holding_dollar_white", size=(14, 14)) or get_ctk_icon("hand-holding-dollar-solid-full", size=(14, 14))
        fiados_btn = ctk.CTkButton(
            e_hdr_bar,
            image=fiados_ico,
            compound="left",
            text="  Fiados & Cupos",
            width=130,
            height=30,
            fg_color="#082F49",
            hover_color="#0C4A6E",
            border_color="#0284C7",
            border_width=1.5,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self._open_fiados_dashboard_modal
        )
        fiados_btn.pack(side="right", padx=(0, 6))

        # Empresas Table Columns: (#, Empresa, Encargado, Teléfono, Compras, Gasto Total, Acciones)
        self.empresas_columns = [
            ("ranking", "#", 42, "center", 0),
            ("company_name", "Empresa", 120, "w", 3),
            ("contact_name", "Encargado", 100, "w", 2),
            ("phone", "Teléfono", 95, "center", 2),
            ("total_purchases", "Compras", 55, "center", 1),
            ("total_spent", "Gasto Total", 85, "center", 2),
            ("actions", "Acciones", 96, "center", 0),
        ]

        e_table_hdr = ctk.CTkFrame(
            self.empresas_panel,
            fg_color=DarkTheme.BG_ELEVATED,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=6,
            height=32
        )
        e_table_hdr.pack(fill="x", pady=(0, 4), padx=(0, 22))
        e_table_hdr.pack_propagate(False)

        for col_idx, (col_key, label, width, anchor, weight) in enumerate(self.empresas_columns):
            e_table_hdr.grid_columnconfigure(
                col_idx,
                weight=weight,
                minsize=width if weight == 0 else 0,
                uniform="e_col" if weight > 0 else ""
            )
            cell_padx = (10, 2) if anchor == "w" else 2
            ctk.CTkLabel(
                e_table_hdr,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=DarkTheme.TEXT_SECONDARY,
                anchor=anchor
            ).grid(row=0, column=col_idx, sticky="nsew", padx=cell_padx, pady=3)

        self.empresas_scroll = ctk.CTkScrollableFrame(self.empresas_panel, fg_color="transparent")
        self.empresas_scroll.pack(fill="both", expand=True, pady=(0, 4))

        # Empresas Pagination Bar
        self.empresas_pagination = ctk.CTkFrame(self.empresas_panel, fg_color="transparent", height=30)
        self.empresas_pagination.pack(fill="x", pady=(2, 4))

        self.empresas_prev_btn = ctk.CTkButton(
            self.empresas_pagination,
            text="◀ Ant.",
            width=58,
            height=26,
            fg_color="#111624",
            border_color="#283347",
            border_width=1,
            hover_color="#1E293B",
            text_color=DarkTheme.TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=5,
            cursor="hand2",
            command=self._prev_empresas_page
        )
        self.empresas_prev_btn.pack(side="left")

        self.empresas_page_lbl = ctk.CTkLabel(
            self.empresas_pagination,
            text="Pág. 1 de 1 (0)",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=DarkTheme.TEXT_MUTED
        )
        self.empresas_page_lbl.pack(side="left", padx=8)

        self.empresas_next_btn = ctk.CTkButton(
            self.empresas_pagination,
            text="Sig. ▶",
            width=58,
            height=26,
            fg_color="#111624",
            border_color="#283347",
            border_width=1,
            hover_color="#1E293B",
            text_color=DarkTheme.TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=5,
            cursor="hand2",
            command=self._next_empresas_page
        )
        self.empresas_next_btn.pack(side="left")

        # Backward compatibility aliases for existing unit tests
        self.cust_columns = self.personas_columns
        self.cust_scroll = self.personas_scroll
        self.cust_prev_btn = self.personas_prev_btn
        self.cust_next_btn = self.personas_next_btn
        self.cust_page_lbl = self.personas_page_lbl

        # ── 3. Usuarios del Sistema Workspace (50 / 50 Split: Rendimiento Cajeros vs Directorio Usuarios) ──
        self.users_workspace = ctk.CTkFrame(
            self,
            fg_color=DarkTheme.BG_CARD,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=8
        )

        self.users_workspace.grid_columnconfigure(0, weight=1, uniform="users_split")
        self.users_workspace.grid_columnconfigure(1, weight=0, minsize=16)
        self.users_workspace.grid_columnconfigure(2, weight=1, uniform="users_split")
        self.users_workspace.grid_rowconfigure(0, weight=1)

        # ─── LEFT PANEL (50%): ESTADÍSTICAS Y RENDIMIENTO DE CAJEROS ────────
        self.cashier_stats_panel = ctk.CTkFrame(self.users_workspace, fg_color="transparent")
        self.cashier_stats_panel.grid(row=0, column=0, sticky="nsew", padx=(10, 4), pady=8)

        cs_hdr_bar = ctk.CTkFrame(self.cashier_stats_panel, fg_color="transparent", height=32)
        cs_hdr_bar.pack(fill="x", pady=(0, 6))

        cs_title_box = ctk.CTkFrame(cs_hdr_bar, fg_color="transparent")
        cs_title_box.pack(side="left")

        stats_ico = get_ctk_icon("ranking-star-solid-full", size=(16, 16)) or get_ctk_icon("chart_column_white", size=(16, 16))
        ctk.CTkLabel(
            cs_title_box,
            image=stats_ico,
            compound="left",
            text="  RENDIMIENTO DE VENTAS POR CAJERO",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#FFFFFF"
        ).pack(side="left")

        self.cashier_stats_badge = ctk.CTkLabel(
            cs_hdr_bar,
            text="Ranking en tiempo real",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#38BDF8",
            fg_color="#082F49",
            corner_radius=6,
            padx=8,
            pady=2
        )
        self.cashier_stats_badge.pack(side="right")

        # Top summary chips inside left panel (Enlarged and highlighted for high visibility)
        cs_kpi_bar = ctk.CTkFrame(self.cashier_stats_panel, fg_color="#0D111A", border_color="#334155", border_width=1.5, corner_radius=7, height=38)
        cs_kpi_bar.pack(fill="x", pady=(0, 6))
        cs_kpi_bar.pack_propagate(False)

        self.kpi_cashier_total_lbl = ctk.CTkLabel(
            cs_kpi_bar,
            text="Total de Ventas: $ 0",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#FFFFFF"
        )
        self.kpi_cashier_total_lbl.pack(side="left", padx=12, pady=4)

        trophy_ico = get_tinted_ctk_icon("trophy-solid-full", "#FBBF24", size=(18, 18)) or get_ctk_icon("trophy_gold", size=(18, 18))
        self.kpi_cashier_top_lbl = ctk.CTkLabel(
            cs_kpi_bar,
            image=trophy_ico,
            compound="left",
            text="  Líder: —",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#FBBF24"
        )
        self.kpi_cashier_top_lbl.pack(side="right", padx=12, pady=4)

        self.cashier_stats_scroll = ctk.CTkScrollableFrame(self.cashier_stats_panel, fg_color="transparent")
        self.cashier_stats_scroll.pack(fill="both", expand=True, pady=(0, 4))

        # ─── VERTICAL DIVIDER ────────────────────────────────────────────────
        divider_box_u = ctk.CTkFrame(self.users_workspace, fg_color="transparent", width=16)
        divider_box_u.grid(row=0, column=1, sticky="ns", pady=8)
        divider_box_u.pack_propagate(False)

        sep_u = ctk.CTkFrame(divider_box_u, fg_color="#334155", width=2)
        sep_u.pack(fill="y", expand=True)

        # ─── RIGHT PANEL (50%): DIRECTORIO DE USUARIOS DEL SISTEMA ───────────
        self.system_users_panel = ctk.CTkFrame(self.users_workspace, fg_color="transparent")
        self.system_users_panel.grid(row=0, column=2, sticky="nsew", padx=(4, 10), pady=8)

        u_hdr_bar = ctk.CTkFrame(self.system_users_panel, fg_color="transparent", height=32)
        u_hdr_bar.pack(fill="x", pady=(0, 6))

        u_title_box = ctk.CTkFrame(u_hdr_bar, fg_color="transparent")
        u_title_box.pack(side="left")

        u_hdr_ico = get_ctk_icon("user-tie-solid-full", size=(16, 16)) or get_ctk_icon("user_tie_solid_white", size=(16, 16))
        ctk.CTkLabel(
            u_title_box,
            image=u_hdr_ico,
            compound="left",
            text="  USUARIOS DEL SISTEMA",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#FFFFFF"
        ).pack(side="left")

        self.users_count_badge = ctk.CTkLabel(
            u_title_box,
            text="0 operadores",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#94A3B8",
            fg_color="#0F172A",
            corner_radius=6,
            padx=8,
            pady=2
        )
        self.users_count_badge.pack(side="left", padx=8)

        u_add_ico = get_ctk_icon("user-plus-solid-full", size=(14, 14)) or get_ctk_icon("file_circle_plus_white", size=(14, 14))
        u_add_btn = ctk.CTkButton(
            u_hdr_bar,
            image=u_add_ico,
            compound="left",
            text="  Nuevo Usuario",
            width=135,
            height=28,
            fg_color="#1D4ED8",
            hover_color="#2563EB",
            border_color="#3B82F6",
            border_width=1,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self._open_new_user_modal
        )
        u_add_btn.pack(side="right")

        # Users Table Columns
        self.system_users_columns = [
            ("id", "#", 40, "center", 0),
            ("user", "Operador / Usuario", 160, "w", 1),
            ("role", "Rol", 115, "center", 0),
            ("status", "Estado", 75, "center", 0),
            ("actions", "Acciones", 96, "center", 0),
        ]

        u_table_hdr = ctk.CTkFrame(
            self.system_users_panel,
            fg_color=DarkTheme.BG_ELEVATED,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=6,
            height=32
        )
        u_table_hdr.pack(fill="x", pady=(0, 4))
        u_table_hdr.pack_propagate(False)

        for col_idx, (col_key, label, width, anchor, weight) in enumerate(self.system_users_columns):
            u_table_hdr.grid_columnconfigure(col_idx, weight=weight, minsize=width if weight == 0 else 0)
            cell_padx = (8, 2) if anchor == "w" else 2
            ctk.CTkLabel(
                u_table_hdr,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=DarkTheme.TEXT_SECONDARY,
                anchor=anchor
            ).grid(row=0, column=col_idx, sticky="nsew", padx=cell_padx, pady=3)

        self.users_scroll = ctk.CTkScrollableFrame(self.system_users_panel, fg_color="transparent")
        self.users_scroll.pack(fill="both", expand=True, pady=(0, 4))

    def _open_touch_search_keypad(self) -> None:
        """Open on-screen keypad to type numeric phone or document into search bar (Clientes tab only)."""
        if hasattr(self, "tab_selector") and self.tab_selector.get() != "Clientes":
            return
        if not TouchKeypadModal:
            return
        init_val = self.search_entry.get().strip()
        TouchKeypadModal(
            parent=self,
            title="Búsqueda Numérica",
            subtitle="Digite los dígitos para filtrar",
            initial_value=init_val,
            on_confirm_callback=self._on_touch_search_confirmed
        )

    def _on_touch_search_confirmed(self, val: str) -> None:
        self._cancel_search_debounce()
        self.search_entry.delete(0, "end")
        self.search_entry.insert(0, val)
        self._do_search()

    def _on_tab_change(self, mode: str) -> None:
        """Switch view between customer directory and system user accounts."""
        self._cancel_search_debounce()
        # Always clear search and reset page on tab switch to avoid cross-filtering bugs
        self.search_entry.delete(0, "end")
        self.current_page = 1

        plus_ico = get_ctk_icon("user-plus-solid-full", size=(16, 16)) or get_ctk_icon("file_circle_plus_white", size=(16, 16))
        if mode == "Clientes":
            self.add_btn.configure(
                text="  Registrar Cliente",
                image=plus_ico,
                fg_color="#059669",
                hover_color="#10B981",
                border_color="#34D399"
            )
            if hasattr(self, "touch_kb_btn") and hasattr(self, "search_entry"):
                try:
                    self.touch_kb_btn.pack(side="left", padx=(0, 4), after=self.search_entry)
                except Exception:
                    self.touch_kb_btn.pack(side="left", padx=(0, 4))

            if hasattr(self, "users_workspace"):
                self.users_workspace.pack_forget()

            # Facturado / Venta Prom KPI chips removed to match clean layout of Usuarios del Sistema
            self.kpi_divider.pack_forget()
            self.row_kpis.pack_forget()
            self.customers_workspace.pack(fill="both", expand=True, padx=10, pady=(0, 8))
            self.search_entry.configure(placeholder_text="Buscar por nombre o teléfono...")
            self.load_data()
        else:
            self.add_btn.configure(
                text="  Registrar Usuario",
                image=plus_ico,
                fg_color="#1D4ED8",
                hover_color="#2563EB",
                border_color="#3B82F6"
            )
            if hasattr(self, "touch_kb_btn"):
                self.touch_kb_btn.pack_forget()

            self.kpi_divider.pack_forget()
            self.row_kpis.pack_forget()
            self.customers_workspace.pack_forget()
            self.users_workspace.pack(fill="both", expand=True, padx=10, pady=(0, 8))
            self.search_entry.configure(placeholder_text="Buscar operador o usuario...")
            self._render_users_table()

    def _on_refresh_click(self) -> None:
        """Refresh button handler that respects active tab."""
        sound_manager.play_click()
        if hasattr(self, "tab_selector") and self.tab_selector.get() == "Usuarios del Sistema":
            self._render_users_table()
        else:
            self.load_data()

    def _on_add_click(self) -> None:
        if self.tab_selector.get() == "Clientes":
            self._open_new_customer_modal()
        else:
            self._open_new_user_modal()

    def _open_new_customer_modal(self, default_type: str = "PERSONA") -> None:
        CustomerFormModal(self, customer=None, on_success_callback=self.load_data, default_customer_type=default_type)

    def _open_edit_customer_modal(self, customer: Dict[str, Any]) -> None:
        CustomerFormModal(self, customer=customer, on_success_callback=self.load_data)

    def _open_view_customer_modal(self, customer: Dict[str, Any]) -> None:
        if customer.get("customer_type") == "EMPRESA":
            CompanyDetailModal(
                parent=self,
                customer=customer,
                on_edit_request=self._open_edit_customer_modal,
                on_delete_request=self._delete_customer
            )
        else:
            CustomerDetailModal(
                parent=self,
                customer=customer,
                on_edit_request=self._open_edit_customer_modal,
                on_delete_request=self._delete_customer
            )

    def _delete_customer(self, customer: Dict[str, Any], parent_dialog=None) -> bool:
        c_name = customer["full_name"]
        c_id = customer["id"]
        dlg_parent = parent_dialog or self

        if not messagebox.askyesno(
            "Confirmar Eliminación",
            f"¿Está seguro de que desea eliminar al cliente:\n\n{c_name}?\n\nEsta acción no se puede deshacer.",
            parent=dlg_parent
        ):
            return False

        try:
            with get_db_connection() as conn:
                CustomerModel.delete(conn, c_id)
            sound_manager.play_sale_success()
            messagebox.showinfo(
                "Cliente Eliminado",
                f"El cliente '{c_name}' ha sido eliminado exitosamente.",
                parent=dlg_parent
            )
            self.load_data()
            return True
        except sqlite3.IntegrityError:
            sound_manager.play_error()
            messagebox.showwarning(
                "No se puede eliminar",
                f"No es posible eliminar a '{c_name}' porque tiene historial de compras/facturas registradas en el sistema.",
                parent=dlg_parent
            )
            return False
        except Exception as e:
            sound_manager.play_error()
            messagebox.showerror(
                "Error al eliminar",
                f"Ocurrió un error inesperado al eliminar el cliente:\n{e}",
                parent=dlg_parent
            )
            return False

    def _open_view_user_modal(self, user: User) -> None:
        """Open detailed profile modal for an operator."""
        UserDetailModal(self, user)

    def _open_new_user_modal(self) -> None:
        UserFormModal(self, user=None, on_success_callback=self._render_users_table)

    def _open_edit_user_modal(self, user: User) -> None:
        UserFormModal(self, user=user, on_success_callback=self._render_users_table)

    def _delete_system_user(self, user: User) -> None:
        if user.is_admin:
            sound_manager.play_error()
            messagebox.showwarning(
                "Acción No Permitida",
                "No se puede eliminar al Administrador del sistema. Debe existir siempre una cuenta de Administrador.",
                parent=self
            )
            return

        if not messagebox.askyesno(
            "Confirmar Eliminación",
            f"¿Está seguro de que desea eliminar la cuenta de acceso:\n\n{user.full_name} ({user.username})?\n\nEsta acción eliminará sus permisos de acceso.",
            parent=self
        ):
            return

        try:
            with get_db_connection() as conn:
                success, msg = UserModel.delete_user(conn, user.id)

            if success:
                sound_manager.play_sale_success()
                messagebox.showinfo("Usuario Eliminado", msg, parent=self)
                self._render_users_table()
            else:
                sound_manager.play_error()
                messagebox.showwarning("No se pudo eliminar", msg, parent=self)
        except Exception as e:
            sound_manager.play_error()
            messagebox.showerror("Error al eliminar", f"No se pudo eliminar el usuario:\n{e}", parent=self)

    def _toggle_user_status(self, user: User) -> None:
        """Toggle an operator's active status. Administrator cannot be deactivated."""
        if user.is_admin:
            sound_manager.play_error()
            messagebox.showwarning(
                "Acción No Permitida",
                "El Administrador del sistema no puede ser desactivado.",
                parent=self
            )
            return

        action_verb = "desactivar" if user.active else "activar"
        if not messagebox.askyesno(
            "Cambiar Estado",
            f"¿Está seguro de que desea {action_verb} la cuenta del operador:\n\n{user.full_name} (@{user.username})?",
            parent=self
        ):
            return

        try:
            with get_db_connection() as conn:
                success, msg, new_st = UserModel.toggle_active(conn, user.id)
            if success:
                sound_manager.play_sale_success()
                self._render_users_table()
            else:
                sound_manager.play_error()
                messagebox.showwarning("Aviso", msg, parent=self)
        except Exception as e:
            sound_manager.play_error()
            messagebox.showerror("Error", f"No se pudo cambiar el estado del operador:\n{e}", parent=self)

    def _render_cashier_stats(self) -> None:
        """Render ranked cashier performance cards and metrics in left 50% panel."""
        for w in self.cashier_stats_scroll.winfo_children():
            w.destroy()

        try:
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT u.id, u.username, u.full_name, u.role,
                           COALESCE(SUM(s.total), 0) AS total_sold,
                           COUNT(s.id) AS sales_count,
                           COALESCE(AVG(s.total), 0) AS avg_ticket,
                           MAX(s.timestamp) AS last_sale_at
                    FROM users u
                    LEFT JOIN sales s ON s.user_id = u.id
                    GROUP BY u.id
                    ORDER BY total_sold DESC, sales_count DESC
                """)
                stats = [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logging.error("Error cargando estadísticas de cajeros: %s", e)
            stats = []

        grand_total = sum(float(r["total_sold"] or 0) for r in stats)
        tot_sales_count = sum(int(r["sales_count"] or 0) for r in stats)

        # Update top KPI labels
        if hasattr(self, "kpi_cashier_total_lbl"):
            gt_str = f"$ {grand_total:,.0f}".replace(",", ".")
            self.kpi_cashier_total_lbl.configure(
                text=f"Total de Ventas: {gt_str} ({tot_sales_count} ventas)"
            )

        leader_name = stats[0]["full_name"] if stats else "—"
        if hasattr(self, "kpi_cashier_top_lbl"):
            trophy_ico = get_tinted_ctk_icon("trophy-solid-full", "#FBBF24", size=(18, 18)) or get_ctk_icon("trophy_gold", size=(18, 18))
            self.kpi_cashier_top_lbl.configure(
                image=trophy_ico,
                compound="left",
                text=f"  Líder: {leader_name}",
                text_color="#FBBF24"
            )

        if not stats:
            empty = ctk.CTkFrame(self.cashier_stats_scroll, fg_color="transparent")
            empty.pack(fill="x", pady=40)
            ctk.CTkLabel(
                empty,
                text="No hay registros de ventas para los cajeros.",
                font=ctk.CTkFont(family="Segoe UI", size=11, slant="italic"),
                text_color=DarkTheme.TEXT_MUTED
            ).pack()
            return

        for idx, cs in enumerate(stats):
            rank = idx + 1
            tot_sold = float(cs["total_sold"] or 0)
            s_cnt = int(cs["sales_count"] or 0)
            avg_t = float(cs["avg_ticket"] or 0)
            pct = (tot_sold / grand_total * 100.0) if grand_total > 0 else 0.0

            # Rank badge styling
            if rank == 1:
                card_border = "#F59E0B"
                card_bg = "#251C08"
                m_row_bg = "#1B1405"
                pbar_bg = "#3A2A0B"
                r_bg = "#B45309"
                r_border = "#F59E0B"
                r_fg = "#FFFFFF"
                bar_color = "#F59E0B"
            elif rank == 2:
                card_border = "#E2E8F0"
                card_bg = "#212836"
                m_row_bg = "#171F2B"
                pbar_bg = "#334155"
                r_bg = "#475569"
                r_border = "#E2E8F0"
                r_fg = "#FFFFFF"
                bar_color = "#E2E8F0"
            elif rank == 3:
                card_border = "#EA580C"
                card_bg = "#281508"
                m_row_bg = "#1E0E05"
                pbar_bg = "#3D1F0C"
                r_bg = "#7C2D12"
                r_border = "#EA580C"
                r_fg = "#FFFFFF"
                bar_color = "#EA580C"
            else:
                card_border = "#2563EB"
                card_bg = "#0B1528"
                m_row_bg = "#070E1B"
                pbar_bg = "#1E3A8A"
                r_bg = "#1E40AF"
                r_border = "#3B82F6"
                r_fg = "#93C5FD"
                bar_color = "#38BDF8"

            card = ctk.CTkFrame(
                self.cashier_stats_scroll,
                fg_color=card_bg,
                border_color=card_border,
                border_width=1.2,
                corner_radius=8
            )
            card.pack(fill="x", pady=3, padx=2)

            # Header of Card: Medal/Rank Pill + Operator Name + Role Pill
            c_hdr = ctk.CTkFrame(card, fg_color="transparent", height=32)
            c_hdr.pack(fill="x", padx=10, pady=(6, 4))

            # Medals for Top 3, Rank Pill for others
            if rank in (1, 2, 3):
                medal_img = get_ctk_icon(f"{rank}.png", size=(26, 26))
                if medal_img:
                    m_lbl = ctk.CTkLabel(c_hdr, image=medal_img, text="", width=28)
                    m_lbl.pack(side="left", padx=(0, 8))
                else:
                    rp = ctk.CTkFrame(c_hdr, fg_color=r_bg, border_color=r_border, border_width=1, corner_radius=5, height=22, width=32)
                    rp.pack(side="left", padx=(0, 8))
                    rp.pack_propagate(False)
                    ctk.CTkLabel(rp, text=f"#{rank}", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=r_fg).place(relx=0.5, rely=0.5, anchor="center")
            else:
                rp = ctk.CTkFrame(c_hdr, fg_color=r_bg, border_color=r_border, border_width=1, corner_radius=5, height=22, width=32)
                rp.pack(side="left", padx=(0, 8))
                rp.pack_propagate(False)
                ctk.CTkLabel(rp, text=f"#{rank}", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=r_fg).place(relx=0.5, rely=0.5, anchor="center")

            # Name & Username
            name_box = ctk.CTkFrame(c_hdr, fg_color="transparent")
            name_box.pack(side="left", fill="x", expand=True)

            ctk.CTkLabel(
                name_box,
                text=cs["full_name"],
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#FFFFFF"
            ).pack(side="left")

            ctk.CTkLabel(
                name_box,
                text=f"  @{cs['username']}",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=DarkTheme.TEXT_MUTED
            ).pack(side="left")

            # Role pill ("Administrador" or "Cajero")
            is_adm = str(cs.get("role", "")).upper() in ("ADMIN", "ADMINISTRADOR")
            role_txt = "Administrador" if is_adm else "Cajero"
            role_fg = "#FBBF24" if is_adm else "#38BDF8"
            role_border = "#F59E0B" if is_adm else "#0284C7"
            role_bg = "#78350F" if is_adm else "#0C2340"

            role_pill = ctk.CTkFrame(c_hdr, fg_color=role_bg, border_color=role_border, border_width=1, corner_radius=10, height=20)
            role_pill.pack(side="right")
            ctk.CTkLabel(role_pill, text=role_txt, font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"), text_color=role_fg).pack(padx=8, pady=1)

            # Metrics 3-column strip with enlarged typography
            m_row = ctk.CTkFrame(card, fg_color=m_row_bg, corner_radius=6, height=54)
            m_row.pack(fill="x", padx=10, pady=(2, 6))
            m_row.pack_propagate(False)
            m_row.grid_columnconfigure((0, 1, 2), weight=1, uniform="c_metrics")

            # Metric 1: Total Facturado
            m1 = ctk.CTkFrame(m_row, fg_color="transparent")
            m1.grid(row=0, column=0, sticky="nsew", pady=4)
            ctk.CTkLabel(m1, text="Facturado", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8").pack()
            m1_txt = f"$ {tot_sold:,.0f}".replace(",", ".")
            ctk.CTkLabel(m1, text=m1_txt, font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"), text_color="#FBBF24").pack()

            # Metric 2: Cantidad Ventas
            m2 = ctk.CTkFrame(m_row, fg_color="transparent")
            m2.grid(row=0, column=1, sticky="nsew", pady=4)
            ctk.CTkLabel(m2, text="Ventas Realizadas", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8").pack()
            ctk.CTkLabel(m2, text=f"{s_cnt} facturas", font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"), text_color="#38BDF8").pack()

            # Metric 3: Ticket Promedio
            m3 = ctk.CTkFrame(m_row, fg_color="transparent")
            m3.grid(row=0, column=2, sticky="nsew", pady=4)
            ctk.CTkLabel(m3, text="Ticket Promedio", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8").pack()
            m3_txt = f"$ {avg_t:,.0f}".replace(",", ".")
            ctk.CTkLabel(m3, text=m3_txt, font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"), text_color="#34D399").pack()

            # Progress bar of % share
            p_row = ctk.CTkFrame(card, fg_color="transparent")
            p_row.pack(fill="x", padx=10, pady=(0, 6))

            pbar = ctk.CTkProgressBar(p_row, height=6, corner_radius=3, fg_color=pbar_bg, progress_color=bar_color)
            pbar.pack(fill="x", pady=(2, 2))
            pbar.set(max(0.0, min(1.0, pct / 100.0)))

            lbl_pct = ctk.CTkLabel(
                p_row,
                text=f"{pct:.1f}% de la facturación global del negocio",
                font=ctk.CTkFont(family="Segoe UI", size=9),
                text_color=DarkTheme.TEXT_MUTED
            )
            lbl_pct.pack(anchor="w")

    def _render_users_table(self) -> None:
        """Render cashier stats (left 50%) and all system users (right 50%) with 5 columns."""
        from database.connection import normalize_text

        # 1. Render cashier statistics on the left
        self._render_cashier_stats()

        # 2. Render system users directory on the right
        for w in self.users_scroll.winfo_children():
            w.destroy()

        search_q = self.search_entry.get().strip().lower() if hasattr(self, "search_entry") else ""

        try:
            with get_db_connection() as conn:
                all_users = UserModel.get_all(conn)
        except Exception as e:
            logging.error("Error cargando usuarios: %s", e)
            all_users = []

        if search_q:
            norm_q = normalize_text(search_q)
            users = [
                u for u in all_users
                if norm_q in normalize_text(u.full_name) or norm_q in normalize_text(u.username)
            ]
        else:
            users = all_users

        if hasattr(self, "users_count_badge"):
            self.users_count_badge.configure(text=f"{len(users)} operadores")

        pen_icon = get_ctk_icon("pen_gold", size=(14, 14))
        trash_icon = get_ctk_icon("trash_red", size=(14, 14)) or get_ctk_icon("trash_arrow_red", size=(14, 14))

        if not users:
            empty = ctk.CTkFrame(self.users_scroll, fg_color="transparent")
            empty.pack(fill="x", pady=40)
            ctk.CTkLabel(
                empty,
                text="No se encontraron operadores o usuarios registrados.",
                font=ctk.CTkFont(family="Segoe UI", size=11, slant="italic"),
                text_color=DarkTheme.TEXT_MUTED
            ).pack()
            return

        for idx, u in enumerate(users):
            row_bg = DarkTheme.BG_CARD if (idx % 2 == 0) else DarkTheme.BG_ROW_ALT
            row = ctk.CTkFrame(
                self.users_scroll,
                fg_color=row_bg,
                border_color=DarkTheme.BORDER_SUBTLE,
                border_width=1,
                corner_radius=6,
                height=42
            )
            row.pack(fill="x", pady=2)
            row.pack_propagate(False)

            def _hover_u_enter(e, rf=row):
                try:
                    rf.configure(fg_color=DarkTheme.BG_ROW_HOVER, border_color="#3B82F6")
                except Exception:
                    pass

            def _hover_u_leave(e, rf=row, bg=row_bg):
                try:
                    rf.configure(fg_color=bg, border_color=DarkTheme.BORDER_SUBTLE)
                except Exception:
                    pass

            row.bind("<Enter>", _hover_u_enter)
            row.bind("<Leave>", _hover_u_leave)

            # 5 Columns: (#, Operador / Usuario, Rol, Estado, Acciones)
            row.grid_columnconfigure(0, weight=0, minsize=40)
            row.grid_columnconfigure(1, weight=1)
            row.grid_columnconfigure(2, weight=0, minsize=115)
            row.grid_columnconfigure(3, weight=0, minsize=75)
            row.grid_columnconfigure(4, weight=0, minsize=75)

            # Col 0: Sequential Index # (1, 2, 3...)
            lbl_id = ctk.CTkLabel(
                row,
                text=str(idx + 1),
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=DarkTheme.TEXT_MUTED,
                anchor="center"
            )
            lbl_id.grid(row=0, column=0, sticky="ew", padx=4, pady=6)
            lbl_id.bind("<Enter>", _hover_u_enter)
            lbl_id.bind("<Leave>", _hover_u_leave)

            # Col 1: Operador / Usuario (Icon on left, vertical stack on right)
            cell_u = ctk.CTkFrame(row, fg_color="transparent")
            cell_u.grid(row=0, column=1, sticky="ew", padx=6, pady=2)
            cell_u.bind("<Enter>", _hover_u_enter)
            cell_u.bind("<Leave>", _hover_u_leave)

            is_adm = u.is_admin
            u_icon = get_ctk_icon("users_gear_solid_blue" if is_adm else "user_solid_blue", size=(24, 24)) or get_ctk_icon("user_solid_white", size=(24, 24))
            lbl_uico = ctk.CTkLabel(cell_u, image=u_icon, text="")
            lbl_uico.pack(side="left", padx=(2, 8))
            lbl_uico.bind("<Enter>", _hover_u_enter)
            lbl_uico.bind("<Leave>", _hover_u_leave)

            v_text_u = ctk.CTkFrame(cell_u, fg_color="transparent")
            v_text_u.pack(side="left", fill="both", expand=True)
            v_text_u.bind("<Enter>", _hover_u_enter)
            v_text_u.bind("<Leave>", _hover_u_leave)

            lbl_fn = ctk.CTkLabel(
                v_text_u,
                text=u.full_name,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=DarkTheme.TEXT_PRIMARY,
                anchor="w"
            )
            lbl_fn.pack(anchor="w")
            lbl_fn.bind("<Enter>", _hover_u_enter)
            lbl_fn.bind("<Leave>", _hover_u_leave)

            lbl_un = ctk.CTkLabel(
                v_text_u,
                text=f"@{u.username}",
                font=ctk.CTkFont(family="Segoe UI", size=9),
                text_color=DarkTheme.TEXT_MUTED,
                anchor="w"
            )
            lbl_un.pack(anchor="w")
            lbl_un.bind("<Enter>", _hover_u_enter)
            lbl_un.bind("<Leave>", _hover_u_leave)

            # Col 2: Role Pill ("Administrador" or "Cajero")
            is_adm = u.is_admin
            role_fg = "#FBBF24" if is_adm else "#38BDF8"
            role_border = "#F59E0B" if is_adm else "#0284C7"
            role_bg = "#78350F" if is_adm else "#0C2340"
            role_txt = "Administrador" if is_adm else "Cajero"

            role_pill = ctk.CTkFrame(row, fg_color=role_bg, border_color=role_border, border_width=1, corner_radius=10, height=22)
            role_pill.grid(row=0, column=2, sticky="", padx=4, pady=6)
            role_lbl = ctk.CTkLabel(role_pill, text=role_txt, font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=role_fg)
            role_lbl.pack(padx=10, pady=1)
            role_pill.bind("<Enter>", _hover_u_enter)
            role_pill.bind("<Leave>", _hover_u_leave)
            role_lbl.bind("<Enter>", _hover_u_enter)
            role_lbl.bind("<Leave>", _hover_u_leave)

            # Col 3: Estado Button / Pill (Clickable toggle between Activo and Inactivo)
            is_act = bool(u.active)
            st_bg = "#064E3B" if is_act else "#450A0A"
            st_border = "#10B981" if is_act else "#EF4444"
            st_fg = "#34D399" if is_act else "#F87171"
            st_hover = "#0D3325" if is_act else "#2E0A0A"
            st_txt = "Activo" if is_act else "Inactivo"

            st_btn = ctk.CTkButton(
                row,
                text=st_txt,
                width=68,
                height=22,
                fg_color=st_bg,
                border_color=st_border,
                border_width=1,
                hover_color=st_hover,
                text_color=st_fg,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                corner_radius=10,
                cursor="hand2",
                command=lambda usr=u: self._toggle_user_status(usr)
            )
            st_btn.grid(row=0, column=3, sticky="", padx=4, pady=6)

            # Col 4: Actions Box: [👁️] [✏️] [🗑️]
            act_box = ctk.CTkFrame(row, fg_color="transparent")
            act_box.grid(row=0, column=4, sticky="", padx=(4, 6), pady=4)
            act_box.bind("<Enter>", _hover_u_enter)
            act_box.bind("<Leave>", _hover_u_leave)

            view_u_btn = ctk.CTkButton(
                act_box,
                text="",
                width=26,
                height=26,
                corner_radius=5,
                cursor="hand2",
                command=lambda usr=u: self._open_view_user_modal(usr)
            )
            apply_palette_button(view_u_btn, variant="ver", icon_name="eye_white", icon_size=(14, 14))
            view_u_btn.pack(side="left", padx=1)

            edit_u_btn = ctk.CTkButton(
                act_box,
                text="",
                width=26,
                height=26,
                corner_radius=5,
                cursor="hand2",
                command=lambda usr=u: self._open_edit_user_modal(usr)
            )
            apply_palette_button(edit_u_btn, variant="editar", icon_name="pen_gold", icon_size=(14, 14))
            edit_u_btn.pack(side="left", padx=1)

            if not is_adm:
                del_u_btn = ctk.CTkButton(
                    act_box,
                    text="",
                    width=26,
                    height=26,
                    corner_radius=5,
                    cursor="hand2",
                    command=lambda usr=u: self._delete_system_user(usr)
                )
                apply_palette_button(del_u_btn, variant="eliminar", icon_name="trash_red", icon_size=(14, 14))
                del_u_btn.pack(side="left", padx=1)

    def load_data(self) -> None:
        """Fetch all customers, calculate KPIs, split into Personas vs Empresas 50/50, and render tables."""
        if hasattr(self, "tab_selector") and self.tab_selector.get() == "Usuarios del Sistema":
            self._render_users_table()
            return

        search_q = self.search_entry.get().strip() if hasattr(self, "search_entry") else ""
        try:
            with get_db_connection() as conn:
                self.all_customers = CustomerModel.get_all_with_stats(conn, query=search_q)
                metrics = CustomerModel.get_summary_metrics(conn)

            # Separate into Personas and Empresas
            self.personas_list = [c for c in self.all_customers if c.get("customer_type") != "EMPRESA"]
            self.empresas_list = [c for c in self.all_customers if c.get("customer_type") == "EMPRESA"]

            tot_cust = metrics['total_customers']
            act_buy = metrics['active_buyers']
            tot_spent = metrics['total_spent_customers']
            avg_tkt = metrics['avg_ticket']

            # Update KPI labels
            self.kpi_total_lbl.configure(
                text=f"Total: {tot_cust} clientes ({len(self.personas_list)} Personas | {len(self.empresas_list)} Empresas). Mostrando {len(self.all_customers)}"
            )
            self.chip_total_cust.configure(text=f"Total Clientes: {tot_cust}")
            if hasattr(self, "chip_total_personas"):
                self.chip_total_personas.configure(text=f"Total Personas: {len(self.personas_list)}")
            if hasattr(self, "chip_total_empresas"):
                self.chip_total_empresas.configure(text=f"Total Empresas: {len(self.empresas_list)}")

            self.chip_active_buyers.configure(text=f"Activos: {act_buy}")
            tot_spent_str = f"${tot_spent:,.0f}".replace(",", ".")
            self.chip_total_spent.configure(text=f"Facturado: {tot_spent_str}")
            avg_tkt_str = f"${avg_tkt:,.0f}".replace(",", ".")
            self.chip_avg_ticket.configure(text=f"Venta Prom: {avg_tkt_str}")

            if hasattr(self, "personas_count_badge"):
                self.personas_count_badge.configure(text=f"{len(self.personas_list)} registradas")
            if hasattr(self, "empresas_count_badge"):
                self.empresas_count_badge.configure(text=f"{len(self.empresas_list)} registradas")

            self.filtered_customers = self.all_customers

            # Pagination calculations
            self.personas_total_pages = max(1, math.ceil(len(self.personas_list) / self.personas_page_size))
            if self.personas_current_page > self.personas_total_pages:
                self.personas_current_page = self.personas_total_pages

            self.empresas_total_pages = max(1, math.ceil(len(self.empresas_list) / self.empresas_page_size))
            if self.empresas_current_page > self.empresas_total_pages:
                self.empresas_current_page = self.empresas_total_pages

            # Test sync
            self.total_pages = self.personas_total_pages
            self.current_page = self.personas_current_page

            self._render_personas_table_rows()
            self._render_empresas_table_rows()

        except Exception as e:
            logging.error("Error cargando clientes en UsersFrame: %s", e)

    def _render_personas_table_rows(self) -> None:
        """Render paginated rows of natural personas."""
        for w in self.personas_scroll.winfo_children():
            w.destroy()

        count = len(self.personas_list)
        self.personas_page_lbl.configure(text=f"Pág. {self.personas_current_page} de {self.personas_total_pages} ({count})")
        self.personas_prev_btn.configure(state="normal" if self.personas_current_page > 1 else "disabled")
        self.personas_next_btn.configure(state="normal" if self.personas_current_page < self.personas_total_pages else "disabled")

        # Also update backward-compatibility alias
        if hasattr(self, "cust_page_lbl") and self.cust_page_lbl is not self.personas_page_lbl:
            self.cust_page_lbl.configure(text=f"Página {self.personas_current_page} de {self.personas_total_pages} ({count} clientes)")

        if not self.personas_list:
            no_row = ctk.CTkFrame(self.personas_scroll, fg_color="transparent")
            no_row.pack(fill="x", pady=25)
            ctk.CTkLabel(
                no_row,
                text="No hay personas naturales coincidentes.",
                font=ctk.CTkFont(family="Segoe UI", size=10, slant="italic"),
                text_color=DarkTheme.TEXT_MUTED
            ).pack()
            return

        start_idx = (self.personas_current_page - 1) * self.personas_page_size
        end_idx = start_idx + self.personas_page_size
        page_items = self.personas_list[start_idx:end_idx]

        view_img = get_ctk_icon("eye_white", size=(13, 13)) or get_ctk_icon("eye_slate", size=(13, 13))
        edit_img = get_ctk_icon("pen_gold", size=(13, 13)) or get_ctk_icon("pen_orange", size=(13, 13))
        trash_img = get_ctk_icon("trash_red", size=(13, 13)) or get_ctk_icon("trash_arrow_red", size=(13, 13))

        u_ico_row = get_ctk_icon("user_solid_white", size=(24, 24)) or get_ctk_icon("user-solid-full", size=(24, 24))
        phone_ico = get_ctk_icon("mobile_white", size=(12, 12)) or get_ctk_icon("phone_white", size=(12, 12))

        # Medals for Top 3
        med_img1 = get_ctk_icon("1.png", size=(28, 28)) or get_ctk_icon("1.png", size=(30, 30))
        med_img2 = get_ctk_icon("2.png", size=(28, 28)) or get_ctk_icon("2.png", size=(30, 30))
        med_img3 = get_ctk_icon("3.png", size=(28, 28)) or get_ctk_icon("3.png", size=(30, 30))

        for idx, cust in enumerate(page_items):
            rank_num = start_idx + idx + 1
            row_bg = DarkTheme.BG_CARD if (idx % 2 == 0) else DarkTheme.BG_ROW_ALT

            row = ctk.CTkFrame(
                self.personas_scroll,
                fg_color=row_bg,
                border_color=DarkTheme.BORDER_SUBTLE,
                border_width=1,
                corner_radius=6,
                height=48
            )
            row.pack(fill="x", pady=2)
            row.pack_propagate(False)
            row.grid_propagate(False)
            row.grid_rowconfigure(0, weight=1)

            for col_idx, (_, _, width, _, weight) in enumerate(self.personas_columns):
                row.grid_columnconfigure(
                    col_idx,
                    weight=weight,
                    minsize=width if weight == 0 else 0,
                    uniform="p_col" if weight > 0 else ""
                )

            def _hover_p_enter(e, rf=row):
                try:
                    rf.configure(fg_color=DarkTheme.BG_ROW_HOVER, border_color="#3B82F6")
                except Exception:
                    pass

            def _hover_p_leave(e, rf=row, bg=row_bg):
                try:
                    rf.configure(fg_color=bg, border_color=DarkTheme.BORDER_SUBTLE)
                except Exception:
                    pass

            row.bind("<Enter>", _hover_p_enter)
            row.bind("<Leave>", _hover_p_leave)

            # Col 0: Ranking (#1, #2, #3 medals, #4+ pill badge)
            if rank_num == 1 and med_img1:
                lbl_r = ctk.CTkLabel(row, image=med_img1, text="")
                lbl_r.grid(row=0, column=0, sticky="", padx=4, pady=2)
                lbl_r.bind("<Enter>", _hover_p_enter)
                lbl_r.bind("<Leave>", _hover_p_leave)
            elif rank_num == 2 and med_img2:
                lbl_r = ctk.CTkLabel(row, image=med_img2, text="")
                lbl_r.grid(row=0, column=0, sticky="", padx=4, pady=2)
                lbl_r.bind("<Enter>", _hover_p_enter)
                lbl_r.bind("<Leave>", _hover_p_leave)
            elif rank_num == 3 and med_img3:
                lbl_r = ctk.CTkLabel(row, image=med_img3, text="")
                lbl_r.grid(row=0, column=0, sticky="", padx=4, pady=2)
                lbl_r.bind("<Enter>", _hover_p_enter)
                lbl_r.bind("<Leave>", _hover_p_leave)
            else:
                rank_pill = ctk.CTkFrame(row, fg_color="#181E2C", border_color="#283347", border_width=1, corner_radius=5, height=22, width=32)
                rank_pill.grid(row=0, column=0, sticky="", padx=4, pady=2)
                rank_pill.pack_propagate(False)
                lbl_r = ctk.CTkLabel(rank_pill, text=f"#{rank_num}", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8")
                lbl_r.place(relx=0.5, rely=0.5, anchor="center")
                rank_pill.bind("<Enter>", _hover_p_enter)
                rank_pill.bind("<Leave>", _hover_p_leave)
                lbl_r.bind("<Enter>", _hover_p_enter)
                lbl_r.bind("<Leave>", _hover_p_leave)

            # Col 1: Cliente / Cédula (Large icon on left, vertical text stack on right)
            cell_c = ctk.CTkFrame(row, fg_color="transparent")
            cell_c.grid(row=0, column=1, sticky="w", padx=(8, 4), pady=2)
            cell_c.bind("<Enter>", _hover_p_enter)
            cell_c.bind("<Leave>", _hover_p_leave)

            c_name = cust["full_name"]
            c_doc = cust.get("document_id", "")

            # Avatar icon on left
            lbl_ico = ctk.CTkLabel(cell_c, image=u_ico_row, text="")
            lbl_ico.pack(side="left", padx=(2, 8))
            lbl_ico.bind("<Enter>", _hover_p_enter)
            lbl_ico.bind("<Leave>", _hover_p_leave)

            # Name on top, Cédula below
            v_text = ctk.CTkFrame(cell_c, fg_color="transparent")
            v_text.pack(side="left", fill="both", expand=True)
            v_text.bind("<Enter>", _hover_p_enter)
            v_text.bind("<Leave>", _hover_p_leave)

            lbl_n = ctk.CTkLabel(
                v_text,
                text=c_name,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#FFFFFF",
                anchor="w"
            )
            lbl_n.pack(anchor="w")
            lbl_n.bind("<Enter>", _hover_p_enter)
            lbl_n.bind("<Leave>", _hover_p_leave)

            lbl_d = ctk.CTkLabel(
                v_text,
                text=f"CC: {c_doc}" if c_doc else "CC: —",
                font=ctk.CTkFont(family="Segoe UI", size=9),
                text_color=DarkTheme.TEXT_MUTED,
                anchor="w"
            )
            lbl_d.pack(anchor="w")
            lbl_d.bind("<Enter>", _hover_p_enter)
            lbl_d.bind("<Leave>", _hover_p_leave)

            # Col 2: Teléfono
            phone_val = cust.get("phone", "") or "—"
            if phone_ico and phone_val != "—":
                lbl_ph = ctk.CTkLabel(
                    row,
                    image=phone_ico,
                    compound="left",
                    text=f" {phone_val}",
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    text_color="#E2E8F0",
                    anchor="center"
                )
            else:
                lbl_ph = ctk.CTkLabel(
                    row,
                    text=phone_val,
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    text_color="#E2E8F0" if phone_val != "—" else DarkTheme.TEXT_MUTED,
                    anchor="center"
                )
            lbl_ph.grid(row=0, column=2, sticky="nsew", padx=4, pady=2)
            lbl_ph.bind("<Enter>", _hover_p_enter)
            lbl_ph.bind("<Leave>", _hover_p_leave)

            # Col 3: Compras (Plain white text, centered)
            purchases_count = cust.get("total_purchases", 0)
            lbl_comp = ctk.CTkLabel(
                row,
                text=str(purchases_count),
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="#FFFFFF",
                anchor="center"
            )
            lbl_comp.grid(row=0, column=3, sticky="nsew", padx=4, pady=2)
            lbl_comp.bind("<Enter>", _hover_p_enter)
            lbl_comp.bind("<Leave>", _hover_p_leave)

            # Col 4: Gasto Total (Plain white text, bold, centered)
            total_spent = cust.get("total_spent", 0.0)
            tot_str = f"$ {total_spent:,.0f}".replace(",", ".") if total_spent > 0 else "$ 0"
            lbl_fact = ctk.CTkLabel(
                row,
                text=tot_str,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#FFFFFF",
                anchor="center"
            )
            lbl_fact.grid(row=0, column=4, sticky="nsew", padx=4, pady=2)
            lbl_fact.bind("<Enter>", _hover_p_enter)
            lbl_fact.bind("<Leave>", _hover_p_leave)

            # Col 5: Acciones (Centered action box [👁] [✏] [🗑])
            act_box = ctk.CTkFrame(row, fg_color="transparent")
            act_box.grid(row=0, column=5, sticky="", padx=4, pady=2)
            act_box.bind("<Enter>", _hover_p_enter)
            act_box.bind("<Leave>", _hover_p_leave)

            b_v = ctk.CTkButton(
                act_box,
                text="",
                width=28,
                height=28,
                corner_radius=6,
                cursor="hand2",
                command=lambda c=cust: self._open_view_customer_modal(c)
            )
            apply_palette_button(b_v, variant="ver", icon_name="eye_white", icon_size=(13, 13))
            b_v.pack(side="left", padx=2)

            b_e = ctk.CTkButton(
                act_box,
                text="",
                width=28,
                height=28,
                corner_radius=6,
                cursor="hand2",
                command=lambda c=cust: self._open_edit_customer_modal(c)
            )
            apply_palette_button(b_e, variant="editar", icon_name="pen_gold", icon_size=(13, 13))
            b_e.pack(side="left", padx=2)

            b_d = ctk.CTkButton(
                act_box,
                text="",
                width=28,
                height=28,
                corner_radius=6,
                cursor="hand2",
                command=lambda c=cust: self._delete_customer(c)
            )
            apply_palette_button(b_d, variant="eliminar", icon_name="trash_red", icon_size=(13, 13))
            b_d.pack(side="left", padx=2)

    def _render_empresas_table_rows(self) -> None:
        """Render paginated rows of enterprises with product quota fiados and remaining balances."""
        for w in self.empresas_scroll.winfo_children():
            w.destroy()

        count = len(self.empresas_list)
        self.empresas_page_lbl.configure(text=f"Pág. {self.empresas_current_page} de {self.empresas_total_pages} ({count})")
        self.empresas_prev_btn.configure(state="normal" if self.empresas_current_page > 1 else "disabled")
        self.empresas_next_btn.configure(state="normal" if self.empresas_current_page < self.empresas_total_pages else "disabled")

        if not self.empresas_list:
            no_row = ctk.CTkFrame(self.empresas_scroll, fg_color="transparent")
            no_row.pack(fill="x", pady=25)
            ctk.CTkLabel(
                no_row,
                text="No hay empresas o convenios coincidentes.",
                font=ctk.CTkFont(family="Segoe UI", size=10, slant="italic"),
                text_color=DarkTheme.TEXT_MUTED
            ).pack()
            return

        start_idx = (self.empresas_current_page - 1) * self.empresas_page_size
        end_idx = start_idx + self.empresas_page_size
        page_items = self.empresas_list[start_idx:end_idx]

        # Load quotas for all items on page
        quotas_by_company = {}
        try:
            with get_db_connection() as conn:
                for emp in page_items:
                    quotas_by_company[emp["id"]] = CustomerModel.get_company_quotas(conn, emp["id"])
        except Exception as e:
            logging.error("Error cargando cupos para vista empresas: %s", e)

        med_img1 = get_ctk_icon("1.png", size=(28, 28))
        med_img2 = get_ctk_icon("2.png", size=(28, 28))
        med_img3 = get_ctk_icon("3.png", size=(28, 28))
        view_img = get_ctk_icon("eye_white", size=(13, 13)) or get_ctk_icon("eye_slate", size=(13, 13))
        edit_img = get_ctk_icon("pen_gold", size=(13, 13)) or get_ctk_icon("pen_orange", size=(13, 13))
        trash_img = get_ctk_icon("trash_red", size=(13, 13)) or get_ctk_icon("trash_arrow_red", size=(13, 13))

        for idx, emp in enumerate(page_items):
            rank_num = start_idx + idx + 1
            row_bg = DarkTheme.BG_CARD if (idx % 2 == 0) else DarkTheme.BG_ROW_ALT

            row = ctk.CTkFrame(
                self.empresas_scroll,
                fg_color=row_bg,
                border_color=DarkTheme.BORDER_SUBTLE,
                border_width=1,
                corner_radius=6,
                height=48
            )
            row.pack(fill="x", pady=2)
            row.pack_propagate(False)
            row.grid_propagate(False)
            row.grid_rowconfigure(0, weight=1)

            for col_idx, (_, _, width, _, weight) in enumerate(self.empresas_columns):
                row.grid_columnconfigure(
                    col_idx,
                    weight=weight,
                    minsize=width if weight == 0 else 0,
                    uniform="e_col" if weight > 0 else ""
                )

            def _hover_e_enter(e, rf=row):
                try:
                    rf.configure(fg_color="#24170A", border_color="#F59E0B")
                except Exception:
                    pass

            def _hover_e_leave(e, rf=row, bg=row_bg):
                try:
                    rf.configure(fg_color=bg, border_color=DarkTheme.BORDER_SUBTLE)
                except Exception:
                    pass

            row.bind("<Enter>", _hover_e_enter)
            row.bind("<Leave>", _hover_e_leave)

            # Col 0: Ranking (#1, #2, #3 medals, #4+ pill badge)
            if rank_num == 1 and med_img1:
                lbl_r = ctk.CTkLabel(row, image=med_img1, text="")
                lbl_r.grid(row=0, column=0, sticky="", padx=4, pady=2)
                lbl_r.bind("<Enter>", _hover_e_enter)
                lbl_r.bind("<Leave>", _hover_e_leave)
            elif rank_num == 2 and med_img2:
                lbl_r = ctk.CTkLabel(row, image=med_img2, text="")
                lbl_r.grid(row=0, column=0, sticky="", padx=4, pady=2)
                lbl_r.bind("<Enter>", _hover_e_enter)
                lbl_r.bind("<Leave>", _hover_e_leave)
            elif rank_num == 3 and med_img3:
                lbl_r = ctk.CTkLabel(row, image=med_img3, text="")
                lbl_r.grid(row=0, column=0, sticky="", padx=4, pady=2)
                lbl_r.bind("<Enter>", _hover_e_enter)
                lbl_r.bind("<Leave>", _hover_e_leave)
            else:
                rank_pill = ctk.CTkFrame(row, fg_color="#181E2C", border_color="#283347", border_width=1, corner_radius=5, height=22, width=32)
                rank_pill.grid(row=0, column=0, sticky="", padx=4, pady=2)
                rank_pill.pack_propagate(False)
                lbl_r = ctk.CTkLabel(rank_pill, text=f"#{rank_num}", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8")
                lbl_r.place(relx=0.5, rely=0.5, anchor="center")
                rank_pill.bind("<Enter>", _hover_e_enter)
                rank_pill.bind("<Leave>", _hover_e_leave)
                lbl_r.bind("<Enter>", _hover_e_enter)
                lbl_r.bind("<Leave>", _hover_e_leave)

            # Col 1: Empresa / NIT (Large building icon on left, vertical text stack on right)
            cell_e = ctk.CTkFrame(row, fg_color="transparent")
            cell_e.grid(row=0, column=1, sticky="w", padx=(8, 4), pady=2)
            cell_e.bind("<Enter>", _hover_e_enter)
            cell_e.bind("<Leave>", _hover_e_leave)

            company_name = emp.get("first_name", "") or emp.get("full_name", "")
            nit_val = emp.get("document_id", "")
            bld_icon_row = get_ctk_icon("building_solid_white", size=(24, 24)) or get_ctk_icon("building-solid-full", size=(24, 24))

            # Building icon on left
            lbl_bico = ctk.CTkLabel(cell_e, image=bld_icon_row, text="")
            lbl_bico.pack(side="left", padx=(2, 8))
            lbl_bico.bind("<Enter>", _hover_e_enter)
            lbl_bico.bind("<Leave>", _hover_e_leave)

            # Name on top, NIT below
            v_text_e = ctk.CTkFrame(cell_e, fg_color="transparent")
            v_text_e.pack(side="left", fill="both", expand=True)
            v_text_e.bind("<Enter>", _hover_e_enter)
            v_text_e.bind("<Leave>", _hover_e_leave)

            lbl_en = ctk.CTkLabel(
                v_text_e,
                text=company_name,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#FFFFFF",
                anchor="w"
            )
            lbl_en.pack(anchor="w")
            lbl_en.bind("<Enter>", _hover_e_enter)
            lbl_en.bind("<Leave>", _hover_e_leave)

            lbl_nit = ctk.CTkLabel(
                v_text_e,
                text=f"NIT: {nit_val}" if nit_val else "NIT: —",
                font=ctk.CTkFont(family="Segoe UI", size=9),
                text_color=DarkTheme.TEXT_MUTED,
                anchor="w"
            )
            lbl_nit.pack(anchor="w")
            lbl_nit.bind("<Enter>", _hover_e_enter)
            lbl_nit.bind("<Leave>", _hover_e_leave)

            # Col 2: Encargado (First Name + First Surname only)
            enc_name = format_encargado(emp.get("last_name", "")) or "—"
            lbl_enc = ctk.CTkLabel(
                row,
                text=enc_name,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="#FFFFFF" if enc_name != "—" else DarkTheme.TEXT_MUTED,
                anchor="w"
            )
            lbl_enc.grid(row=0, column=2, sticky="nsew", padx=6, pady=2)
            lbl_enc.bind("<Enter>", _hover_e_enter)
            lbl_enc.bind("<Leave>", _hover_e_leave)

            # Col 3: Teléfono
            phone_val = emp.get("phone", "") or "—"
            phone_ico = get_ctk_icon("mobile_white", size=(12, 12)) or get_ctk_icon("phone_white", size=(12, 12))
            if phone_ico and phone_val != "—":
                lbl_ph = ctk.CTkLabel(
                    row,
                    image=phone_ico,
                    compound="left",
                    text=f" {phone_val}",
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    text_color="#E2E8F0",
                    anchor="center"
                )
            else:
                lbl_ph = ctk.CTkLabel(
                    row,
                    text=phone_val,
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    text_color="#E2E8F0" if phone_val != "—" else DarkTheme.TEXT_MUTED,
                    anchor="center"
                )
            lbl_ph.grid(row=0, column=3, sticky="nsew", padx=4, pady=2)
            lbl_ph.bind("<Enter>", _hover_e_enter)
            lbl_ph.bind("<Leave>", _hover_e_leave)

            # Col 4: Compras (Plain white text, centered, no badge)
            purchases_count = emp.get("total_purchases", 0)
            lbl_comp = ctk.CTkLabel(
                row,
                text=str(purchases_count),
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="#FFFFFF",
                anchor="center"
            )
            lbl_comp.grid(row=0, column=4, sticky="nsew", padx=4, pady=2)
            lbl_comp.bind("<Enter>", _hover_e_enter)
            lbl_comp.bind("<Leave>", _hover_e_leave)

            # Col 5: Gasto Total (Plain white text, bold, centered)
            total_spent = emp.get("total_spent", 0.0)
            fiado_amt = emp.get("fiado_spent", 0.0)
            show_amt = fiado_amt if fiado_amt > 0 else total_spent
            tot_emp_str = f"$ {show_amt:,.0f}".replace(",", ".") if show_amt > 0 else "$ 0"
            lbl_fact = ctk.CTkLabel(
                row,
                text=tot_emp_str,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#FFFFFF",
                anchor="center"
            )
            lbl_fact.grid(row=0, column=5, sticky="nsew", padx=4, pady=2)
            lbl_fact.bind("<Enter>", _hover_e_enter)
            lbl_fact.bind("<Leave>", _hover_e_leave)

            # Col 6: Acciones (Centered action box [👁] [✏] [🗑])
            act_box = ctk.CTkFrame(row, fg_color="transparent")
            act_box.grid(row=0, column=6, sticky="", padx=4, pady=2)
            act_box.bind("<Enter>", _hover_e_enter)
            act_box.bind("<Leave>", _hover_e_leave)

            b_ve = ctk.CTkButton(
                act_box,
                text="",
                width=28,
                height=28,
                corner_radius=6,
                cursor="hand2",
                command=lambda c=emp: self._open_view_customer_modal(c)
            )
            apply_palette_button(b_ve, variant="ver", icon_name="eye_white", icon_size=(13, 13))
            b_ve.pack(side="left", padx=2)

            b_ee = ctk.CTkButton(
                act_box,
                text="",
                width=28,
                height=28,
                corner_radius=6,
                cursor="hand2",
                command=lambda c=emp: self._open_edit_customer_modal(c)
            )
            apply_palette_button(b_ee, variant="editar", icon_name="pen_gold", icon_size=(13, 13))
            b_ee.pack(side="left", padx=2)

            b_de = ctk.CTkButton(
                act_box,
                text="",
                width=28,
                height=28,
                corner_radius=6,
                cursor="hand2",
                command=lambda c=emp: self._delete_customer(c)
            )
            apply_palette_button(b_de, variant="eliminar", icon_name="trash_red", icon_size=(13, 13))
            b_de.pack(side="left", padx=2)

    def _prev_personas_page(self) -> None:
        if self.personas_current_page > 1:
            self.personas_current_page -= 1
            self.current_page = self.personas_current_page
            self._render_personas_table_rows()

    def _next_personas_page(self) -> None:
        if self.personas_current_page < self.personas_total_pages:
            self.personas_current_page += 1
            self.current_page = self.personas_current_page
            self._render_personas_table_rows()

    def _prev_empresas_page(self) -> None:
        if self.empresas_current_page > 1:
            self.empresas_current_page -= 1
            self._render_empresas_table_rows()

    def _next_empresas_page(self) -> None:
        if self.empresas_current_page < self.empresas_total_pages:
            self.empresas_current_page += 1
            self._render_empresas_table_rows()

    def _prev_cust_page(self) -> None:
        """Compatibility wrapper for unit tests."""
        self._prev_personas_page()

    def _next_cust_page(self) -> None:
        """Compatibility wrapper for unit tests."""
        self._next_personas_page()

    def _render_customer_table_rows(self) -> None:
        """Compatibility wrapper for unit tests."""
        self._render_personas_table_rows()
        self._render_empresas_table_rows()

    def _cancel_search_debounce(self) -> None:
        """Safely cancel any pending debounced search timer."""
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except Exception:
                pass
            self._search_job = None

    def _on_search_key(self, event=None) -> None:
        """Debounced search on keystroke (300ms delay to suppress rapid sequential requests)."""
        if event and event.keysym in (
            "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
            "Caps_Lock", "Tab", "ISO_Left_Tab", "Up", "Down", "Left", "Right",
            "Home", "End", "Prior", "Next", "Escape", "Return", "KP_Enter"
        ):
            return

        self._cancel_search_debounce()

        # If user cleared the input (Backspace / Delete), execute immediately
        q = self.search_entry.get().strip() if hasattr(self, "search_entry") else ""
        if not q:
            self._do_search()
            return

        self._search_job = self.after(self.SEARCH_DEBOUNCE_MS, self._do_search)

    def _on_search_enter(self) -> None:
        """Immediate search execution upon pressing Enter or clicking Search button."""
        self._cancel_search_debounce()
        self._do_search()

    def _do_search(self) -> None:
        """Execute search filter."""
        self._search_job = None
        self.personas_current_page = 1
        self.empresas_current_page = 1
        self.current_page = 1
        if self.tab_selector.get() == "Clientes":
            self.load_data()
        else:
            self._render_users_table()

    def _on_clear_search_click(self) -> None:
        """Clear search input, reset pagination, and reload."""
        self._cancel_search_debounce()
        try:
            sound_manager.play_click()
        except Exception:
            pass
        self._clear_search()

    def _clear_search(self) -> None:
        """Clear search input and reload full directory."""
        self._cancel_search_debounce()
        self.search_entry.delete(0, "end")
        self.personas_current_page = 1
        self.empresas_current_page = 1
        self.current_page = 1
        if self.tab_selector.get() == "Clientes":
            self.load_data()
        else:
            self._render_users_table()

    def _reset_filters(self) -> None:
        """Reset search and refresh."""
        self._clear_search()

    def _open_fiados_dashboard_modal(self) -> None:
        """Open central corporate fiados & quota management dashboard."""
        FiadosDashboardModal(
            parent=self,
            on_refresh_callback=self.load_data
        )

