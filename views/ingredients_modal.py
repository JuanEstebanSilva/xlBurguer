"""Ingredients & Gram-Based Inventory Management Modals for XL Burguer.
Provides complete management of raw ingredients, subproducts and portion stocks:
- IngredientsManagerModal: Table of all ingredients with stock in grams (g) and kg, min stock, unit cost, status, actions.
- IngredientPurchaseModal: Register purchases in kilograms (kg) or grams (g) with automatic conversion to grams (1 kg = 1000 g).
- IngredientAdjustmentModal: Register stock adjustments and wastage/merma in grams.
- IngredientFormModal: Create and edit ingredient specifications (name, min stock, cost/g).
- InventoryMovementsModal: Audit log of all inventory movements.
"""

import math
import tkinter as tk
from tkinter import messagebox
from typing import Callable, Dict, List, Optional, Tuple
import customtkinter as ctk

from database.connection import get_db_connection
from models.ingredient import Ingredient, IngredientModel, InventoryMovement
from models.product import format_currency, format_currency_short
from utils.asset_manager import center_modal, get_ctk_icon, build_standard_modal_header
from utils.sound_manager import sound_manager
from utils.theme import DarkTheme, apply_palette_button


def _center(dlg: ctk.CTkToplevel, parent, w: int, h: int) -> None:
    center_modal(dlg, w, h, parent)


# ─────────────────────────────────────────────────────────────────────────────
# 1. INGREDIENT PURCHASE MODAL (ENTRADA DE COMPRAS CON CONVERSIÓN KG -> G)
# ─────────────────────────────────────────────────────────────────────────────
class IngredientPurchaseModal(ctk.CTkToplevel):
    """Modal for registering ingredient purchases in Kg or grams with automatic
    conversion to inventory grams ($1\text{ kg} = 1000\text{ g}$) and cost recalculation.
    """

    def __init__(
        self,
        parent,
        selected_ingredient_id: Optional[int] = None,
        on_success_callback: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        self.on_success_callback = on_success_callback
        self.selected_ingredient_id = selected_ingredient_id

        self.title("Entrada de Compra de Ingrediente - XL Burguer")
        self.resizable(False, False)
        self.configure(fg_color=DarkTheme.BG_ROOT)

        with get_db_connection() as conn:
            self.ingredients = IngredientModel.get_all(conn, active_only=True)

        self._build_ui()
        _center(self, parent, 520, 560)
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self) -> None:
        icon = get_ctk_icon("cube_white", size=(16, 16))
        build_standard_modal_header(
            self,
            title_text="Entrada de Compra de Ingrediente",
            title_icon=icon,
            on_close_cmd=self.destroy,
            show_close_btn=False,
            text_color="#FFFFFF"
        )

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # 1. Ingredient Selector
        ctk.CTkLabel(
            body,
            text="Ingrediente a ingresar:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(anchor="w", pady=(0, 4))

        ing_names = [f"{ing.id} - {ing.name}" for ing in self.ingredients]
        self.ing_combo = ctk.CTkComboBox(
            body,
            values=ing_names,
            width=460,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            text_color=DarkTheme.INPUT_TEXT,
            dropdown_fg_color=DarkTheme.BG_ELEVATED,
            command=lambda v: self._update_previews()
        )
        self.ing_combo.pack(fill="x", pady=(0, 14))

        # Select initial ingredient if provided
        if self.selected_ingredient_id:
            for idx, ing in enumerate(self.ingredients):
                if ing.id == self.selected_ingredient_id:
                    self.ing_combo.set(ing_names[idx])
                    break
        elif ing_names:
            self.ing_combo.set(ing_names[0])

        # Current stock info badge
        self.stock_info_lbl = ctk.CTkLabel(
            body,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#38BDF8"
        )
        self.stock_info_lbl.pack(anchor="w", pady=(0, 10))

        # 2. Quantity & Unit Row
        qty_row = ctk.CTkFrame(body, fg_color="transparent")
        qty_row.pack(fill="x", pady=(0, 10))

        qty_col = ctk.CTkFrame(qty_row, fg_color="transparent")
        qty_col.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkLabel(
            qty_col,
            text="Cantidad comprada:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(anchor="w", pady=(0, 4))

        self.qty_entry = ctk.CTkEntry(
            qty_col,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            placeholder_text="Ej: 5.0",
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            text_color=DarkTheme.INPUT_TEXT
        )
        self.qty_entry.pack(fill="x")
        self.qty_entry.bind("<KeyRelease>", lambda e: self._update_previews())

        unit_col = ctk.CTkFrame(qty_row, fg_color="transparent")
        unit_col.pack(side="right", padx=(8, 0))

        ctk.CTkLabel(
            unit_col,
            text="Unidad de compra:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(anchor="w", pady=(0, 4))

        self.unit_combo = ctk.CTkComboBox(
            unit_col,
            values=["Kilogramos (kg)", "Gramos (g)"],
            width=170,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            text_color=DarkTheme.INPUT_TEXT,
            dropdown_fg_color=DarkTheme.BG_ELEVATED,
            command=lambda v: self._update_previews()
        )
        self.unit_combo.set("Kilogramos (kg)")
        self.unit_combo.pack()

        # Grams conversion preview chip
        self.conversion_preview = ctk.CTkLabel(
            body,
            text="Conversión: 0.0 kg = 0 g a ingresar al inventario",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FBBF24"
        )
        self.conversion_preview.pack(anchor="w", pady=(0, 10))

        # 3. Total Purchase Cost (COP)
        ctk.CTkLabel(
            body,
            text="Costo total de la compra (COP $):",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(anchor="w", pady=(0, 4))

        self.cost_entry = ctk.CTkEntry(
            body,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            placeholder_text="Ej: 120000",
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            text_color=DarkTheme.INPUT_TEXT
        )
        self.cost_entry.pack(fill="x", pady=(0, 4))
        self.cost_entry.bind("<KeyRelease>", lambda e: self._update_previews())

        # Resulting cost per gram preview
        self.cost_preview = ctk.CTkLabel(
            body,
            text="Costo calculado: $0 COP / gramo",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8"
        )
        self.cost_preview.pack(anchor="w", pady=(0, 10))

        # 4. Notes / Provider (Optional)
        ctk.CTkLabel(
            body,
            text="Proveedor / Notas de factura (Opcional):",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(anchor="w", pady=(0, 4))

        self.notes_entry = ctk.CTkEntry(
            body,
            height=34,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            placeholder_text="Ej: Compra Carnes La Especial, Factura #1024",
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            text_color=DarkTheme.INPUT_TEXT
        )
        self.notes_entry.pack(fill="x", pady=(0, 14))

        # Actions buttons
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(6, 0))

        cancel_btn = ctk.CTkButton(
            btn_row,
            text="Cancelar",
            height=38,
            width=120,
            fg_color="#1F2937",
            hover_color="#374151",
            text_color="#E5E7EB",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            command=self.destroy
        )
        cancel_btn.pack(side="left")

        save_btn = ctk.CTkButton(
            btn_row,
            text="✔ Registrar Entrada",
            height=38,
            fg_color="#10B981",
            hover_color="#059669",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            command=self._on_save
        )
        save_btn.pack(side="right", fill="x", expand=True, padx=(10, 0))

        self._update_previews()

    def _get_current_ingredient(self) -> Optional[Ingredient]:
        sel = self.ing_combo.get()
        if not sel or " - " not in sel:
            return None
        try:
            ing_id = int(sel.split(" - ")[0])
            for ing in self.ingredients:
                if ing.id == ing_id:
                    return ing
        except Exception:
            pass
        return None

    def _update_previews(self) -> None:
        ing = self._get_current_ingredient()
        if ing:
            self.stock_info_lbl.configure(
                text=f"Stock Actual: {ing.stock_g:,.0f} g  ({ing.stock_kg:,.2f} kg)  |  Costo actual: ${ing.cost_per_g:.2f}/g"
            )

        # Quantity and unit
        raw_qty = self.qty_entry.get().strip().replace(",", ".")
        unit_is_kg = "kg" in self.unit_combo.get().lower()

        qty_g = 0.0
        try:
            qty_val = float(raw_qty) if raw_qty else 0.0
            qty_g = (qty_val * 1000.0) if unit_is_kg else qty_val
            unit_str = "kg" if unit_is_kg else "g"
            self.conversion_preview.configure(
                text=f"Conversión: {qty_val:,.2f} {unit_str} = {qty_g:,.0f} g a sumar al inventario"
            )
        except ValueError:
            self.conversion_preview.configure(text="Cantidad no válida")

        # Cost
        raw_cost = self.cost_entry.get().strip().replace(".", "").replace(",", ".")
        try:
            cost_val = float(raw_cost) if raw_cost else 0.0
            if qty_g > 0 and cost_val > 0:
                cost_per_g = cost_val / qty_g
                cost_per_kg = cost_per_g * 1000.0
                self.cost_preview.configure(
                    text=f"Nuevo costo calculado: ${cost_per_g:,.2f} COP / gramo  (${cost_per_kg:,.0f} COP / kg)"
                )
            else:
                self.cost_preview.configure(text="Ingrese cantidad y costo para calcular costo/g")
        except ValueError:
            self.cost_preview.configure(text="Costo no válido")

    def _on_save(self) -> None:
        ing = self._get_current_ingredient()
        if not ing:
            messagebox.showerror("Error", "Seleccione un ingrediente válido.", parent=self)
            return

        raw_qty = self.qty_entry.get().strip().replace(",", ".")
        try:
            qty_val = float(raw_qty)
            if qty_val <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Error", "Ingrese una cantidad válida mayor a cero.", parent=self)
            return

        raw_cost = self.cost_entry.get().strip().replace(".", "").replace(",", ".")
        try:
            cost_val = float(raw_cost)
            if cost_val < 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Error", "Ingrese un costo de compra válido.", parent=self)
            return

        unit = "kg" if "kg" in self.unit_combo.get().lower() else "g"
        notes = self.notes_entry.get().strip()

        try:
            with get_db_connection() as conn:
                IngredientModel.register_purchase(
                    conn=conn,
                    ingredient_id=ing.id,
                    quantity=qty_val,
                    unit=unit,
                    total_cost=cost_val,
                    notes=notes
                )
            sound_manager.play_success()
            messagebox.showinfo(
                "Entrada Exitosa",
                f"Se han ingresado {(qty_val*1000.0 if unit == 'kg' else qty_val):,.0f} gramos a '{ing.name}'.",
                parent=self
            )
            if self.on_success_callback:
                self.on_success_callback()
            self.destroy()
        except Exception as ex:
            sound_manager.play_error()
            messagebox.showerror("Error", f"No se pudo registrar la compra: {ex}", parent=self)


# ─────────────────────────────────────────────────────────────────────────────
# 2. INGREDIENT ADJUSTMENT / MERMA MODAL
# ─────────────────────────────────────────────────────────────────────────────
class IngredientAdjustmentModal(ctk.CTkToplevel):
    """Modal for registering manual adjustments or wastage/merma directly in grams."""

    def __init__(
        self,
        parent,
        selected_ingredient_id: Optional[int] = None,
        on_success_callback: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        self.on_success_callback = on_success_callback
        self.selected_ingredient_id = selected_ingredient_id

        self.title("Ajuste de Stock / Registro de Merma - XL Burguer")
        self.resizable(False, False)
        self.configure(fg_color=DarkTheme.BG_ROOT)

        with get_db_connection() as conn:
            self.ingredients = IngredientModel.get_all(conn, active_only=True)

        self._build_ui()
        _center(self, parent, 520, 520)
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self) -> None:
        icon = get_ctk_icon("warning_amber", size=(16, 16))
        build_standard_modal_header(
            self,
            title_text="Ajuste de Stock y Registro de Merma (g)",
            title_icon=icon,
            on_close_cmd=self.destroy,
            show_close_btn=False,
            text_color="#FFFFFF"
        )

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # Ingredient selector
        ctk.CTkLabel(
            body,
            text="Ingrediente a ajustar:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(anchor="w", pady=(0, 4))

        ing_names = [f"{ing.id} - {ing.name}" for ing in self.ingredients]
        self.ing_combo = ctk.CTkComboBox(
            body,
            values=ing_names,
            width=460,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            text_color=DarkTheme.INPUT_TEXT,
            dropdown_fg_color=DarkTheme.BG_ELEVATED,
            command=lambda v: self._update_display()
        )
        self.ing_combo.pack(fill="x", pady=(0, 10))

        if self.selected_ingredient_id:
            for idx, ing in enumerate(self.ingredients):
                if ing.id == self.selected_ingredient_id:
                    self.ing_combo.set(ing_names[idx])
                    break
        elif ing_names:
            self.ing_combo.set(ing_names[0])

        # Current stock banner
        self.stock_card = ctk.CTkFrame(body, fg_color="#1E2332", border_color="#333C4F", border_width=1, corner_radius=6)
        self.stock_card.pack(fill="x", pady=(0, 12))

        self.current_stock_lbl = ctk.CTkLabel(
            self.stock_card,
            text="Stock Actual: 0 g",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38BDF8"
        )
        self.current_stock_lbl.pack(padx=12, pady=8)

        # Movement Type
        ctk.CTkLabel(
            body,
            text="Tipo de movimiento:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(anchor="w", pady=(0, 4))

        self.type_combo = ctk.CTkComboBox(
            body,
            values=["MERMA (Desperdicio / Daño)", "AJUSTE (Conteo físico de inventario)"],
            width=460,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            text_color=DarkTheme.INPUT_TEXT,
            dropdown_fg_color=DarkTheme.BG_ELEVATED,
            command=lambda v: self._update_display()
        )
        self.type_combo.set("MERMA (Desperdicio / Daño)")
        self.type_combo.pack(fill="x", pady=(0, 12))

        # Quantity in grams
        self.qty_title = ctk.CTkLabel(
            body,
            text="Gramos perdidos / mermados (g):",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        )
        self.qty_title.pack(anchor="w", pady=(0, 4))

        self.qty_entry = ctk.CTkEntry(
            body,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            placeholder_text="Ej: 250",
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            text_color=DarkTheme.INPUT_TEXT
        )
        self.qty_entry.pack(fill="x", pady=(0, 4))
        self.qty_entry.bind("<KeyRelease>", lambda e: self._update_display())

        # Projected stock preview
        self.projected_lbl = ctk.CTkLabel(
            body,
            text="Stock proyectado: 0 g",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FBBF24"
        )
        self.projected_lbl.pack(anchor="w", pady=(0, 10))

        # Motivo / Razón (mandatory)
        ctk.CTkLabel(
            body,
            text="Motivo / Justificación obligatoria:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(anchor="w", pady=(0, 4))

        self.reason_entry = ctk.CTkEntry(
            body,
            height=34,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            placeholder_text="Ej: Se dañó una porción al freír / Vencimiento",
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            text_color=DarkTheme.INPUT_TEXT
        )
        self.reason_entry.pack(fill="x", pady=(0, 14))

        # Buttons
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(4, 0))

        cancel_btn = ctk.CTkButton(
            btn_row,
            text="Cancelar",
            height=38,
            width=120,
            fg_color="#1F2937",
            hover_color="#374151",
            text_color="#E5E7EB",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            command=self.destroy
        )
        cancel_btn.pack(side="left")

        save_btn = ctk.CTkButton(
            btn_row,
            text="✔ Guardar Ajuste",
            height=38,
            fg_color="#F59E0B",
            hover_color="#D97706",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            command=self._on_save
        )
        save_btn.pack(side="right", fill="x", expand=True, padx=(10, 0))

        self._update_display()

    def _get_current_ingredient(self) -> Optional[Ingredient]:
        sel = self.ing_combo.get()
        if not sel or " - " not in sel:
            return None
        try:
            ing_id = int(sel.split(" - ")[0])
            for ing in self.ingredients:
                if ing.id == ing_id:
                    return ing
        except Exception:
            pass
        return None

    def _update_display(self) -> None:
        ing = self._get_current_ingredient()
        if not ing:
            return

        self.current_stock_lbl.configure(
            text=f"Stock Actual: {ing.stock_g:,.0f} g  ({ing.stock_kg:,.2f} kg)"
        )

        is_merma = "MERMA" in self.type_combo.get()
        if is_merma:
            self.qty_title.configure(text="Gramos perdidos / mermados (g):")
        else:
            self.qty_title.configure(text="Nuevo stock físico total contado (g):")

        raw_val = self.qty_entry.get().strip().replace(",", ".")
        try:
            val = float(raw_val) if raw_val else 0.0
            if is_merma:
                proj = max(0.0, ing.stock_g - val)
                self.projected_lbl.configure(
                    text=f"Stock proyectado tras merma: {proj:,.0f} g ({proj/1000.0:,.2f} kg)"
                )
            else:
                diff = val - ing.stock_g
                sign = "+" if diff >= 0 else ""
                self.projected_lbl.configure(
                    text=f"Nuevo stock: {val:,.0f} g  (Diferencia: {sign}{diff:,.0f} g)"
                )
        except ValueError:
            self.projected_lbl.configure(text="Ingrese una cantidad en gramos válida")

    def _on_save(self) -> None:
        ing = self._get_current_ingredient()
        if not ing:
            messagebox.showerror("Error", "Seleccione un ingrediente válido.", parent=self)
            return

        is_merma = "MERMA" in self.type_combo.get()
        raw_val = self.qty_entry.get().strip().replace(",", ".")
        try:
            val = float(raw_val)
            if val < 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Error", "Ingrese una cantidad válida en gramos.", parent=self)
            return

        reason = self.reason_entry.get().strip()
        if not reason:
            messagebox.showerror("Error", "Debe ingresar un motivo o justificación para el ajuste.", parent=self)
            return

        if is_merma:
            new_stock = max(0.0, ing.stock_g - val)
            mov_type = "MERMA"
        else:
            new_stock = val
            mov_type = "AJUSTE"

        try:
            with get_db_connection() as conn:
                IngredientModel.adjust_stock(
                    conn=conn,
                    ingredient_id=ing.id,
                    new_stock_g=new_stock,
                    movement_type=mov_type,
                    notes=f"{mov_type}: {reason}"
                )
            sound_manager.play_success()
            messagebox.showinfo("Ajuste Guardado", f"El stock de '{ing.name}' ahora es {new_stock:,.0f} g.", parent=self)
            if self.on_success_callback:
                self.on_success_callback()
            self.destroy()
        except Exception as ex:
            sound_manager.play_error()
            messagebox.showerror("Error", f"No se pudo guardar el ajuste: {ex}", parent=self)


# ─────────────────────────────────────────────────────────────────────────────
# 3. INGREDIENT FORM MODAL (CREAR / EDITAR INGREDIENTE)
# ─────────────────────────────────────────────────────────────────────────────
class IngredientFormModal(ctk.CTkToplevel):
    """Modal for creating or editing an ingredient record."""

    def __init__(
        self,
        parent,
        ingredient: Optional[Ingredient] = None,
        on_success_callback: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        self.ingredient = ingredient
        self.on_success_callback = on_success_callback

        title_text = f"Editar Ingrediente: {ingredient.name}" if ingredient else "Crear Nuevo Ingrediente"
        self.title(title_text)
        self.resizable(False, False)
        self.configure(fg_color=DarkTheme.BG_ROOT)

        self._build_ui()
        _center(self, parent, 500, 480)
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self) -> None:
        icon = get_ctk_icon("pen_gold" if self.ingredient else "file_circle_plus_white", size=(16, 16))
        build_standard_modal_header(
            self,
            title_text="Editar Ingrediente" if self.ingredient else "Nuevo Ingrediente (Gramos)",
            title_icon=icon,
            on_close_cmd=self.destroy,
            show_close_btn=False,
            text_color="#FFFFFF"
        )

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # Name
        ctk.CTkLabel(
            body,
            text="Nombre del ingrediente:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(anchor="w", pady=(0, 4))

        self.name_entry = ctk.CTkEntry(
            body,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            placeholder_text="Ej: Carne de Res Molida 125g / Queso Cheddar",
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            text_color=DarkTheme.INPUT_TEXT
        )
        self.name_entry.pack(fill="x", pady=(0, 12))

        # Stock Mínimo (g)
        ctk.CTkLabel(
            body,
            text="Stock Mínimo de alerta en gramos (g):",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(anchor="w", pady=(0, 4))

        self.min_stock_entry = ctk.CTkEntry(
            body,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            placeholder_text="Ej: 1000 (equivale a 1 kg)",
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            text_color=DarkTheme.INPUT_TEXT
        )
        self.min_stock_entry.pack(fill="x", pady=(0, 12))

        # Cost per gram
        ctk.CTkLabel(
            body,
            text="Costo estimado por gramo (COP $ / g):",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(anchor="w", pady=(0, 4))

        self.cost_entry = ctk.CTkEntry(
            body,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            placeholder_text="Ej: 24.0 (equivale a $24,000 por kg)",
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            text_color=DarkTheme.INPUT_TEXT
        )
        self.cost_entry.pack(fill="x", pady=(0, 12))

        # Initial Stock (only if new)
        self.stock_entry = None
        if not self.ingredient:
            ctk.CTkLabel(
                body,
                text="Existencias iniciales en gramos (g):",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color=DarkTheme.TEXT_SECONDARY
            ).pack(anchor="w", pady=(0, 4))

            self.stock_entry = ctk.CTkEntry(
                body,
                height=36,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                placeholder_text="Ej: 5000 (equivale a 5 kg)",
                fg_color=DarkTheme.INPUT_BG,
                border_color=DarkTheme.INPUT_BORDER,
                text_color=DarkTheme.INPUT_TEXT
            )
            self.stock_entry.pack(fill="x", pady=(0, 12))

        # Populate fields if editing
        if self.ingredient:
            self.name_entry.insert(0, self.ingredient.name)
            self.min_stock_entry.insert(0, str(int(self.ingredient.min_stock_g)))
            self.cost_entry.insert(0, str(self.ingredient.cost_per_g))

        # Buttons
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(12, 0))

        cancel_btn = ctk.CTkButton(
            btn_row,
            text="Cancelar",
            height=38,
            width=120,
            fg_color="#1F2937",
            hover_color="#374151",
            text_color="#E5E7EB",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            command=self.destroy
        )
        cancel_btn.pack(side="left")

        save_btn = ctk.CTkButton(
            btn_row,
            text="✔ Guardar Ingrediente",
            height=38,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            command=self._on_save
        )
        save_btn.pack(side="right", fill="x", expand=True, padx=(10, 0))

    def _on_save(self) -> None:
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showerror("Error", "El nombre del ingrediente no puede estar vacío.", parent=self)
            return

        try:
            min_stock = float(self.min_stock_entry.get().strip().replace(",", "."))
            if min_stock < 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Error", "Ingrese un stock mínimo válido en gramos.", parent=self)
            return

        try:
            cost_g = float(self.cost_entry.get().strip().replace(",", "."))
            if cost_g < 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Error", "Ingrese un costo por gramo válido.", parent=self)
            return

        try:
            with get_db_connection() as conn:
                if self.ingredient:
                    IngredientModel.update(
                        conn=conn,
                        ingredient_id=self.ingredient.id,
                        name=name,
                        min_stock_g=min_stock,
                        cost_per_g=cost_g
                    )
                    msg = f"Ingrediente '{name}' actualizado con éxito."
                else:
                    raw_stock = self.stock_entry.get().strip().replace(",", ".") if self.stock_entry else "0"
                    init_stock = float(raw_stock) if raw_stock else 0.0
                    IngredientModel.create(
                        conn=conn,
                        name=name,
                        stock_g=init_stock,
                        min_stock_g=min_stock,
                        cost_per_g=cost_g
                    )
                    msg = f"Ingrediente '{name}' creado con éxito."

            sound_manager.play_success()
            messagebox.showinfo("Éxito", msg, parent=self)
            if self.on_success_callback:
                self.on_success_callback()
            self.destroy()
        except Exception as ex:
            sound_manager.play_error()
            messagebox.showerror("Error", f"Error al guardar: {ex}", parent=self)


# ─────────────────────────────────────────────────────────────────────────────
# 4. INVENTORY MOVEMENTS AUDIT MODAL
# ─────────────────────────────────────────────────────────────────────────────
class InventoryMovementsModal(ctk.CTkToplevel):
    """Modal displaying full audit logs of inventory movements (sales, purchases, mermas)."""

    def __init__(self, parent, ingredient_id: Optional[int] = None):
        super().__init__(parent)
        self.ingredient_id = ingredient_id

        self.title("Historial de Movimientos de Inventario - XL Burguer")
        self.resizable(False, False)
        self.configure(fg_color=DarkTheme.BG_ROOT)

        self._build_ui()
        _center(self, parent, 900, 600)
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self) -> None:
        icon = get_ctk_icon("chart_column_white", size=(16, 16))
        build_standard_modal_header(
            self,
            title_text="Auditoría de Movimientos de Inventario (Gramos)",
            title_icon=icon,
            on_close_cmd=self.destroy,
            show_close_btn=False,
            text_color="#FFFFFF"
        )

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=12)

        # Table Header
        header_frame = ctk.CTkFrame(body, fg_color="#1E2332", height=32, corner_radius=6)
        header_frame.pack(fill="x", pady=(0, 6))
        header_frame.pack_propagate(False)

        cols = [
            ("Fecha y Hora", 140, "w"),
            ("Ingrediente / Item", 180, "w"),
            ("Tipo", 90, "center"),
            ("Cantidad (g)", 95, "center"),
            ("Stock Anterior", 95, "center"),
            ("Nuevo Stock", 95, "center"),
            ("Detalles / Notas", 160, "w"),
        ]

        for text, w, anchor in cols:
            lbl = ctk.CTkLabel(
                header_frame,
                text=text,
                width=w,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#94A3B8",
                anchor=anchor
            )
            lbl.pack(side="left", padx=4)

        # Scrollable rows
        rows_scroll = ctk.CTkScrollableFrame(body, fg_color="transparent")
        rows_scroll.pack(fill="both", expand=True)

        with get_db_connection() as conn:
            movements = IngredientModel.get_movements(conn, ingredient_id=self.ingredient_id, limit=150)

        if not movements:
            ctk.CTkLabel(
                rows_scroll,
                text="No hay movimientos registrados en el historial.",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=DarkTheme.TEXT_MUTED
            ).pack(pady=40)
            return

        type_colors = {
            "COMPRA": ("#065F46", "#34D399"),
            "VENTA": ("#1E3A8A", "#93C5FD"),
            "MERMA": ("#7F1D1D", "#F87171"),
            "AJUSTE": ("#78350F", "#FBBF24"),
            "INICIAL": ("#312E81", "#A5B4FC")
        }

        for idx, m in enumerate(movements):
            row_bg = "#0B0F1D" if (idx % 2 == 0) else "#101626"
            rf = ctk.CTkFrame(rows_scroll, fg_color=row_bg, height=32, corner_radius=4)
            rf.pack(fill="x", pady=1)
            rf.pack_propagate(False)

            # Date
            ctk.CTkLabel(rf, text=m.created_at[:19], width=140, anchor="w", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#94A3B8").pack(side="left", padx=4)
            # Item
            ctk.CTkLabel(rf, text=m.item_name or "-", width=180, anchor="w", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#FFFFFF").pack(side="left", padx=4)

            # Type badge
            bg_c, fg_c = type_colors.get(m.movement_type, ("#1E293B", "#94A3B8"))
            tb = ctk.CTkFrame(rf, fg_color=bg_c, width=90, height=22, corner_radius=4)
            tb.pack(side="left", padx=4)
            tb.pack_propagate(False)
            ctk.CTkLabel(tb, text=m.movement_type, font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"), text_color=fg_c).pack(expand=True)

            # Quantities
            ctk.CTkLabel(rf, text=f"{m.quantity:,.0f} g", width=95, anchor="center", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#F8FAFC").pack(side="left", padx=4)
            ctk.CTkLabel(rf, text=f"{m.previous_stock:,.0f} g", width=95, anchor="center", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#64748B").pack(side="left", padx=4)
            ctk.CTkLabel(rf, text=f"{m.new_stock:,.0f} g", width=95, anchor="center", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#38BDF8").pack(side="left", padx=4)
            # Notes
            ctk.CTkLabel(rf, text=m.notes or "-", width=160, anchor="w", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#CBD5E1").pack(side="left", padx=4)


# ─────────────────────────────────────────────────────────────────────────────
# 5. INGREDIENTS MANAGER MODAL (VENTANA PRINCIPAL DE GESTIÓN DE INGREDIENTES)
# ─────────────────────────────────────────────────────────────────────────────
class IngredientsManagerModal(ctk.CTkToplevel):
    """Executive dialog for complete ingredients catalog & gram-based inventory management."""

    def __init__(self, parent, on_refresh_parent_callback: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self.on_refresh_parent_callback = on_refresh_parent_callback

        self.title("Gestión de Ingredientes e Inventario en Gramos - XL Burguer")
        self.resizable(False, False)
        self.configure(fg_color=DarkTheme.BG_ROOT)

        self.ingredients: List[Ingredient] = []
        self.filtered_ingredients: List[Ingredient] = []

        self._build_ui()
        _center(self, parent, 1020, 680)
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass

        self.load_data()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self) -> None:
        icon = get_ctk_icon("cube_white", size=(16, 16))
        build_standard_modal_header(
            self,
            title_text="Gestión de Ingredientes y Control de Gramos",
            title_icon=icon,
            on_close_cmd=self.destroy,
            show_close_btn=False,
            text_color="#FFFFFF"
        )

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=10)

        # ── Controls Bar ──────────────────────────────────────────────────────
        controls = ctk.CTkFrame(body, fg_color=DarkTheme.BG_CARD, border_color=DarkTheme.BORDER_SUBTLE, border_width=1, corner_radius=8)
        controls.pack(fill="x", pady=(0, 8))

        row1 = ctk.CTkFrame(controls, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(8, 6))

        # Search entry
        self.search_entry = ctk.CTkEntry(
            row1,
            width=260,
            height=34,
            placeholder_text="Buscar ingrediente por nombre...",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            text_color=DarkTheme.INPUT_TEXT
        )
        self.search_entry.pack(side="left", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", lambda e: self._apply_filters())

        # Status filter
        ctk.CTkLabel(row1, text="Estado:", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=DarkTheme.TEXT_SECONDARY).pack(side="left", padx=(0, 4))
        self.status_filter = ctk.CTkComboBox(
            row1,
            values=["Todos", "Normal", "Bajo", "Agotado"],
            width=120,
            height=34,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            text_color=DarkTheme.INPUT_TEXT,
            dropdown_fg_color=DarkTheme.BG_ELEVATED,
            command=lambda v: self._apply_filters()
        )
        self.status_filter.set("Todos")
        self.status_filter.pack(side="left", padx=(0, 10))

        # Action Buttons on Right
        self.audit_btn = ctk.CTkButton(
            row1,
            text=" Movimientos",
            image=get_ctk_icon("chart_column_white", size=(14, 14)),
            compound="left",
            height=34,
            fg_color="#0F172A",
            border_color="#334155",
            border_width=1,
            hover_color="#1E293B",
            text_color="#94A3B8",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            command=self._open_movements
        )
        self.audit_btn.pack(side="right")

        self.adjust_btn = ctk.CTkButton(
            row1,
            text=" Ajuste / Merma",
            image=get_ctk_icon("warning_amber", size=(14, 14)),
            compound="left",
            height=34,
            fg_color="#78350F",
            hover_color="#92400E",
            border_color="#F59E0B",
            border_width=1,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            command=self._open_adjustment
        )
        self.adjust_btn.pack(side="right", padx=(0, 8))

        self.purchase_btn = ctk.CTkButton(
            row1,
            text=" + Entrada Compra (Kg/g)",
            image=get_ctk_icon("cube_white", size=(14, 14)),
            compound="left",
            height=34,
            fg_color="#065F46",
            hover_color="#047857",
            border_color="#10B981",
            border_width=1,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            command=self._open_purchase
        )
        self.purchase_btn.pack(side="right", padx=(0, 8))

        self.new_ing_btn = ctk.CTkButton(
            row1,
            text=" + Nuevo Ingrediente",
            image=get_ctk_icon("file_circle_plus_white", size=(14, 14)),
            compound="left",
            height=34,
            fg_color="#1D4ED8",
            hover_color="#2563EB",
            border_color="#3B82F6",
            border_width=1,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            command=self._open_new_ingredient
        )
        self.new_ing_btn.pack(side="right", padx=(0, 8))

        # KPI row
        row2 = ctk.CTkFrame(controls, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=(0, 6))

        self.kpi_total = ctk.CTkLabel(row2, text="Total: 0", font=ctk.CTkFont(family="Segoe UI", size=11), text_color=DarkTheme.TEXT_SECONDARY)
        self.kpi_total.pack(side="left", padx=(0, 12))

        self.kpi_normal = ctk.CTkLabel(row2, text="✔ Normal: 0", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#34D399")
        self.kpi_normal.pack(side="left", padx=(0, 12))

        self.kpi_low = ctk.CTkLabel(row2, text="⚠ Bajo: 0", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#FBBF24")
        self.kpi_low.pack(side="left", padx=(0, 12))

        self.kpi_out = ctk.CTkLabel(row2, text="❗ Agotado: 0", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#F87171")
        self.kpi_out.pack(side="left", padx=(0, 12))

        self.kpi_val = ctk.CTkLabel(row2, text="Valoración Total: COP $0", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#38BDF8")
        self.kpi_val.pack(side="right")

        # ── Table Container ───────────────────────────────────────────────────
        table_container = ctk.CTkFrame(body, fg_color=DarkTheme.BG_CARD, border_color=DarkTheme.BORDER_SUBTLE, border_width=1, corner_radius=8)
        table_container.pack(fill="both", expand=True)

        header_frame = ctk.CTkFrame(table_container, fg_color=DarkTheme.BG_ELEVATED, height=36, corner_radius=6)
        header_frame.pack(fill="x", padx=6, pady=(6, 4))
        header_frame.pack_propagate(False)

        cols_def = [
            ("ID", 40, "center"),
            ("Ingrediente", 200, "w"),
            ("Stock (g)", 95, "center"),
            ("Stock (Kg)", 85, "center"),
            ("Stock Mín (g)", 90, "center"),
            ("Costo / g", 85, "center"),
            ("Costo / Kg", 95, "center"),
            ("Estado", 80, "center"),
            ("Acciones", 120, "center"),
        ]

        for text, w, anchor in cols_def:
            lbl = ctk.CTkLabel(
                header_frame,
                text=text,
                width=w,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=DarkTheme.TEXT_SECONDARY,
                anchor=anchor
            )
            lbl.pack(side="left", padx=2)

        self.rows_scroll = ctk.CTkScrollableFrame(table_container, fg_color="transparent")
        self.rows_scroll.pack(fill="both", expand=True, padx=4, pady=(0, 6))

    def load_data(self) -> None:
        with get_db_connection() as conn:
            self.ingredients = IngredientModel.get_all(conn, active_only=True)
        self._apply_filters()

    def _apply_filters(self) -> None:
        query = self.search_entry.get().strip().lower()
        st_filter = self.status_filter.get()

        filtered = []
        for ing in self.ingredients:
            if query and (query not in ing.name.lower()):
                continue
            if st_filter != "Todos" and ing.status != st_filter:
                continue
            filtered.append(ing)

        self.filtered_ingredients = filtered
        self._update_kpis()
        self._render_rows()

    def _update_kpis(self) -> None:
        total = len(self.ingredients)
        normal = sum(1 for i in self.ingredients if i.status == "Normal")
        low = sum(1 for i in self.ingredients if i.status == "Bajo")
        out = sum(1 for i in self.ingredients if i.status == "Agotado")
        total_val = sum(max(0.0, i.stock_g) * i.cost_per_g for i in self.ingredients)

        self.kpi_total.configure(text=f"Total: {total}")
        self.kpi_normal.configure(text=f"✔ Normal: {normal}")
        self.kpi_low.configure(text=f"⚠ Bajo: {low}")
        self.kpi_out.configure(text=f"❗ Agotado: {out}")
        self.kpi_val.configure(text=f"Valoración Total: {format_currency(total_val)}")

    def _render_rows(self) -> None:
        for w in self.rows_scroll.winfo_children():
            w.destroy()

        if not self.filtered_ingredients:
            ctk.CTkLabel(
                self.rows_scroll,
                text="No hay ingredientes que coincidan con la búsqueda.",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=DarkTheme.TEXT_MUTED
            ).pack(pady=40)
            return

        for idx, ing in enumerate(self.filtered_ingredients):
            row_bg = "#0B0F1D" if (idx % 2 == 0) else "#101626"
            rf = ctk.CTkFrame(self.rows_scroll, fg_color=row_bg, height=36, corner_radius=4)
            rf.pack(fill="x", pady=1)
            rf.pack_propagate(False)

            # ID
            ctk.CTkLabel(rf, text=str(ing.id), width=40, font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#64748B").pack(side="left", padx=2)

            # Name
            ctk.CTkLabel(rf, text=ing.name, width=200, anchor="w", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#FFFFFF").pack(side="left", padx=4)

            # Stock (g)
            ctk.CTkLabel(rf, text=f"{ing.stock_g:,.0f} g", width=95, font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#38BDF8").pack(side="left", padx=2)

            # Stock (Kg)
            ctk.CTkLabel(rf, text=f"{ing.stock_kg:,.2f} kg", width=85, font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#CBD5E1").pack(side="left", padx=2)

            # Min Stock (g)
            ctk.CTkLabel(rf, text=f"{ing.min_stock_g:,.0f} g", width=90, font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#FBBF24").pack(side="left", padx=2)

            # Cost / g
            ctk.CTkLabel(rf, text=f"${ing.cost_per_g:,.2f}", width=85, font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#94A3B8").pack(side="left", padx=2)

            # Cost / Kg
            ctk.CTkLabel(rf, text=f"{format_currency_short(ing.cost_per_kg)}/kg", width=95, font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#94A3B8").pack(side="left", padx=2)

            # Status pill
            st_text, st_bg, st_border, st_fg = ing.status_badge
            st_frame = ctk.CTkFrame(rf, fg_color=st_bg, border_color=st_border, border_width=1, width=80, height=24, corner_radius=4)
            st_frame.pack(side="left", padx=2)
            st_frame.pack_propagate(False)
            ctk.CTkLabel(st_frame, text=st_text, font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"), text_color=st_fg).pack(expand=True)

            # Actions Box
            act_box = ctk.CTkFrame(rf, fg_color="transparent", width=120)
            act_box.pack(side="left", padx=4)

            # 1. Edit (pen)
            edit_btn = ctk.CTkButton(
                act_box,
                text="",
                width=28,
                height=26,
                corner_radius=4,
                cursor="hand2",
                command=lambda i=ing: self._open_edit_ingredient(i)
            )
            apply_palette_button(edit_btn, variant="editar", icon_name="pen_gold", icon_size=(13, 13))
            edit_btn.pack(side="left", padx=2)

            # 2. Purchase entry (+)
            buy_btn = ctk.CTkButton(
                act_box,
                text="+",
                width=28,
                height=26,
                fg_color="#064E3B",
                hover_color="#065F46",
                text_color="#34D399",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                corner_radius=4,
                cursor="hand2",
                command=lambda i=ing: self._open_purchase(i.id)
            )
            buy_btn.pack(side="left", padx=2)

            # 3. Adjust (warning)
            adj_btn = ctk.CTkButton(
                act_box,
                text="±",
                width=28,
                height=26,
                fg_color="#78350F",
                hover_color="#92400E",
                text_color="#FBBF24",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                corner_radius=4,
                cursor="hand2",
                command=lambda i=ing: self._open_adjustment(i.id)
            )
            adj_btn.pack(side="left", padx=2)

            # 4. Delete
            del_btn = ctk.CTkButton(
                act_box,
                text="",
                width=28,
                height=26,
                corner_radius=4,
                cursor="hand2",
                command=lambda i=ing: self._delete_ingredient(i)
            )
            apply_palette_button(del_btn, variant="eliminar", icon_name="trash_arrow_red", icon_size=(13, 13))
            del_btn.pack(side="left", padx=2)

    def _open_purchase(self, ingredient_id: Optional[int] = None) -> None:
        IngredientPurchaseModal(self, selected_ingredient_id=ingredient_id, on_success_callback=self._on_submodal_saved)

    def _open_adjustment(self, ingredient_id: Optional[int] = None) -> None:
        IngredientAdjustmentModal(self, selected_ingredient_id=ingredient_id, on_success_callback=self._on_submodal_saved)

    def _open_new_ingredient(self) -> None:
        IngredientFormModal(self, ingredient=None, on_success_callback=self._on_submodal_saved)

    def _open_edit_ingredient(self, ingredient: Ingredient) -> None:
        IngredientFormModal(self, ingredient=ingredient, on_success_callback=self._on_submodal_saved)

    def _open_movements(self) -> None:
        InventoryMovementsModal(self)

    def _delete_ingredient(self, ingredient: Ingredient) -> None:
        if not messagebox.askyesno(
            "Confirmar Eliminación",
            f"¿Está seguro de eliminar el ingrediente '{ingredient.name}'?",
            parent=self
        ):
            return

        try:
            with get_db_connection() as conn:
                IngredientModel.delete(conn, ingredient.id)
            sound_manager.play_success()
            messagebox.showinfo("Eliminado", f"El ingrediente '{ingredient.name}' ha sido eliminado.", parent=self)
            self._on_submodal_saved()
        except Exception as ex:
            sound_manager.play_error()
            messagebox.showerror("Error", str(ex), parent=self)

    def _on_submodal_saved(self) -> None:
        self.load_data()
        if self.on_refresh_parent_callback:
            self.on_refresh_parent_callback()

