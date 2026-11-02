"""Recipe & Portion Management Modal for XL Burguer.
Provides complete management of product recipes, portion gram weights,
calculated production costs, margins, and theoretical portion availability.
"""

import math
import tkinter as tk
from tkinter import messagebox
from typing import Callable, Dict, List, Optional, Tuple
import customtkinter as ctk

from database.connection import get_db_connection
from models.ingredient import Ingredient, IngredientModel, RecipeItem
from models.product import Product, ProductModel, format_currency, format_currency_short
from utils.asset_manager import center_modal, get_ctk_icon, build_standard_modal_header
from utils.sound_manager import sound_manager
from utils.theme import DarkTheme, apply_palette_button


def _center(dlg: ctk.CTkToplevel, parent, w: int, h: int) -> None:
    center_modal(dlg, w, h, parent)


class RecipeManagerModal(ctk.CTkToplevel):
    """Modern modal dialog for viewing, configuring and tuning fast-food recipes
    in grams (g), computing live preparation costs, theoretical stock portions, and margins.
    """

    def __init__(
        self,
        parent,
        selected_product_id: Optional[int] = None,
        on_recipe_saved_callback: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        self.on_recipe_saved_callback = on_recipe_saved_callback
        self.selected_product_id = selected_product_id

        self.title("Administración de Recetas y Porciones - XL Burguer")
        self.resizable(False, False)
        self.configure(fg_color=DarkTheme.BG_ROOT)

        # In-memory recipe items for the active product: list of dicts:
        # [{"ingredient_id": int, "name": str, "quantity_g": float, "cost_per_g": float, "stock_g": float}]
        self.current_recipe_items: List[Dict[str, Any]] = []

        with get_db_connection() as conn:
            self.all_products = [p for p in ProductModel.get_all(conn) if p.is_active]
            self.all_ingredients = IngredientModel.get_all(conn, active_only=True)

        self._build_ui()
        _center(self, parent, 960, 680)
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass

        self._load_selected_product_recipe()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self) -> None:
        icon = get_ctk_icon("chart_column_white", size=(16, 16))
        build_standard_modal_header(
            self,
            title_text="Administración de Recetas y Porciones en Gramos",
            title_icon=icon,
            on_close_cmd=self.destroy,
            show_close_btn=False,
            text_color="#FFFFFF"
        )

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=12)

        # ── 1. Product Selector Bar ──────────────────────────────────────────
        prod_bar = ctk.CTkFrame(body, fg_color=DarkTheme.BG_CARD, border_color=DarkTheme.BORDER_SUBTLE, border_width=1, corner_radius=8)
        prod_bar.pack(fill="x", pady=(0, 10))

        pb_inner = ctk.CTkFrame(prod_bar, fg_color="transparent")
        pb_inner.pack(fill="x", padx=12, pady=10)

        ctk.CTkLabel(
            pb_inner,
            text="Producto a configurar:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(side="left", padx=(0, 10))

        prod_options = [f"{p.id} - {p.name} ({p.category_name})" for p in self.all_products]
        self.prod_combo = ctk.CTkComboBox(
            pb_inner,
            values=prod_options,
            width=360,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            text_color=DarkTheme.INPUT_TEXT,
            dropdown_fg_color=DarkTheme.BG_ELEVATED,
            command=lambda v: self._load_selected_product_recipe()
        )
        self.prod_combo.pack(side="left")

        # Select initial product
        if self.selected_product_id:
            for idx, p in enumerate(self.all_products):
                if p.id == self.selected_product_id:
                    self.prod_combo.set(prod_options[idx])
                    break
        elif prod_options:
            self.prod_combo.set(prod_options[0])

        self.price_badge = ctk.CTkLabel(
            pb_inner,
            text="Precio Venta: COP $ 0",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#34D399"
        )
        self.price_badge.pack(side="right", padx=(10, 0))

        # ── 2. Metric Cards (Cost, Margins, Theoretical Portions) ────────────
        metrics_grid = ctk.CTkFrame(body, fg_color="transparent")
        metrics_grid.pack(fill="x", pady=(0, 10))
        metrics_grid.columnconfigure((0, 1, 2), weight=1, uniform="metric_cards")

        # Card 1: Costo Receta
        c1 = ctk.CTkFrame(metrics_grid, fg_color="#161A24", border_color="#2A3245", border_width=1.5, corner_radius=8)
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 6), ipady=4)
        ctk.CTkLabel(c1, text="COSTO TOTAL RECETA", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8").pack(anchor="w", padx=10, pady=(6, 2))
        self.cost_lbl = ctk.CTkLabel(c1, text="COP $ 0", font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"), text_color="#38BDF8")
        self.cost_lbl.pack(anchor="w", padx=10)
        self.cost_sub_lbl = ctk.CTkLabel(c1, text="Suma de ingredientes", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#64748B")
        self.cost_sub_lbl.pack(anchor="w", padx=10, pady=(0, 4))

        # Card 2: Margen de Ganancia
        c2 = ctk.CTkFrame(metrics_grid, fg_color="#161A24", border_color="#134739", border_width=1.5, corner_radius=8)
        c2.grid(row=0, column=1, sticky="nsew", padx=3, ipady=4)
        ctk.CTkLabel(c2, text="MARGEN BRUTO", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8").pack(anchor="w", padx=10, pady=(6, 2))
        self.margin_lbl = ctk.CTkLabel(c2, text="0.0 %", font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"), text_color="#34D399")
        self.margin_lbl.pack(anchor="w", padx=10)
        self.margin_sub_lbl = ctk.CTkLabel(c2, text="Utilidad por unidad: COP $ 0", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#64748B")
        self.margin_sub_lbl.pack(anchor="w", padx=10, pady=(0, 4))

        # Card 3: Porciones Disponibles
        c3 = ctk.CTkFrame(metrics_grid, fg_color="#161A24", border_color="#78350F", border_width=1.5, corner_radius=8)
        c3.grid(row=0, column=2, sticky="nsew", padx=(6, 0), ipady=4)
        ctk.CTkLabel(c3, text="PORCIONES EN STOCK", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8").pack(anchor="w", padx=10, pady=(6, 2))
        self.portions_lbl = ctk.CTkLabel(c3, text="0 porciones", font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"), text_color="#FBBF24")
        self.portions_lbl.pack(anchor="w", padx=10)
        self.limiting_lbl = ctk.CTkLabel(c3, text="Limitado por: -", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#94A3B8")
        self.limiting_lbl.pack(anchor="w", padx=10, pady=(0, 4))

        # ── 3. Table of Recipe Items ─────────────────────────────────────────
        table_container = ctk.CTkFrame(body, fg_color=DarkTheme.BG_CARD, border_color=DarkTheme.BORDER_SUBTLE, border_width=1, corner_radius=8)
        table_container.pack(fill="both", expand=True, pady=(0, 10))

        header_frame = ctk.CTkFrame(table_container, fg_color=DarkTheme.BG_ELEVATED, height=34, corner_radius=6)
        header_frame.pack(fill="x", padx=6, pady=(6, 4))
        header_frame.pack_propagate(False)

        cols = [
            ("Ingrediente", 200, "w"),
            ("Porción (g)", 95, "center"),
            ("Costo / g", 85, "center"),
            ("Costo Porción", 110, "center"),
            ("Stock Actual", 120, "center"),
            ("Rendimiento", 100, "center"),
            ("Acciones", 80, "center")
        ]

        for text, w, anchor in cols:
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

        # ── 4. Add Ingredient Bar ────────────────────────────────────────────
        add_bar = ctk.CTkFrame(body, fg_color="#181A22", border_color="#252836", border_width=1, corner_radius=8)
        add_bar.pack(fill="x", pady=(0, 10))

        ab_inner = ctk.CTkFrame(add_bar, fg_color="transparent")
        ab_inner.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(ab_inner, text="Agregar Ingrediente:", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=DarkTheme.TEXT_SECONDARY).pack(side="left", padx=(0, 6))

        ing_choices = [f"{i.id} - {i.name}" for i in self.all_ingredients]
        self.add_ing_combo = ctk.CTkComboBox(
            ab_inner,
            values=ing_choices,
            width=260,
            height=34,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            text_color=DarkTheme.INPUT_TEXT,
            dropdown_fg_color=DarkTheme.BG_ELEVATED
        )
        if ing_choices:
            self.add_ing_combo.set(ing_choices[0])
        self.add_ing_combo.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(ab_inner, text="Gramos (g):", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=DarkTheme.TEXT_SECONDARY).pack(side="left", padx=(0, 4))
        self.add_qty_entry = ctk.CTkEntry(
            ab_inner,
            width=90,
            height=34,
            placeholder_text="Ej: 125",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            text_color=DarkTheme.INPUT_TEXT
        )
        self.add_qty_entry.pack(side="left", padx=(0, 10))

        add_item_btn = ctk.CTkButton(
            ab_inner,
            text=" + Añadir a Receta",
            image=get_ctk_icon("file_circle_plus_white", size=(14, 14)),
            compound="left",
            height=34,
            fg_color="#0F766E",
            hover_color="#0D9488",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            command=self._on_add_ingredient_clicked
        )
        add_item_btn.pack(side="left")

        # ── 5. Footer Actions ────────────────────────────────────────────────
        footer = ctk.CTkFrame(body, fg_color="transparent")
        footer.pack(fill="x")

        close_btn = ctk.CTkButton(
            footer,
            text="Cerrar",
            width=120,
            height=38,
            fg_color="#1F2937",
            hover_color="#374151",
            text_color="#E5E7EB",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            command=self.destroy
        )
        close_btn.pack(side="left")

        save_recipe_btn = ctk.CTkButton(
            footer,
            text="✔ Guardar Receta y Actualizar Costo",
            height=38,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            command=self._on_save_recipe
        )
        save_recipe_btn.pack(side="right", fill="x", expand=True, padx=(12, 0))

    def _get_active_product(self) -> Optional[Product]:
        val = self.prod_combo.get()
        if not val or " - " not in val:
            return None
        try:
            p_id = int(val.split(" - ")[0])
            for p in self.all_products:
                if p.id == p_id:
                    return p
        except Exception:
            pass
        return None

    def _load_selected_product_recipe(self) -> None:
        prod = self._get_active_product()
        if not prod:
            return

        self.price_badge.configure(text=f"Precio Venta: {format_currency(prod.price_base)}")

        with get_db_connection() as conn:
            # Refresh ingredients from DB to have latest stock
            self.all_ingredients = IngredientModel.get_all(conn, active_only=True)
            db_recipe = IngredientModel.get_recipe_for_product(conn, prod.id)

        self.current_recipe_items = []
        for item in db_recipe:
            self.current_recipe_items.append({
                "ingredient_id": item.ingredient_id,
                "name": item.ingredient_name,
                "quantity_g": item.quantity_g,
                "cost_per_g": item.cost_per_g,
                "stock_g": item.current_ingredient_stock_g
            })

        self._refresh_calculations_and_table()

    def _refresh_calculations_and_table(self) -> None:
        prod = self._get_active_product()
        price = prod.price_base if prod else 0.0

        total_cost = 0.0
        min_portions = 999999 if self.current_recipe_items else 0
        limiting_name = "-"

        for item in self.current_recipe_items:
            qty_g = item["quantity_g"]
            cost_g = item["cost_per_g"]
            stock_g = item["stock_g"]

            item_cost = qty_g * cost_g
            total_cost += item_cost

            possible = int(math.floor(max(0.0, stock_g) / qty_g)) if qty_g > 0 else 999999
            if possible < min_portions:
                min_portions = possible
                limiting_name = f"{item['name']} ({stock_g:,.0f}g disp.)"

        if not self.current_recipe_items:
            min_portions = 0
            limiting_name = "Sin receta asignada"

        margin_cop = max(0.0, price - total_cost)
        margin_pct = ((margin_cop / price) * 100.0) if price > 0 else 0.0

        # Update KPI cards
        self.cost_lbl.configure(text=format_currency(total_cost))
        self.cost_sub_lbl.configure(text=f"{len(self.current_recipe_items)} ingredientes asignados")

        self.margin_lbl.configure(text=f"{margin_pct:.1f} %")
        self.margin_sub_lbl.configure(text=f"Ganancia: {format_currency(margin_cop)}")

        if min_portions == 0:
            self.portions_lbl.configure(text="0 porciones", text_color="#F87171")
        elif min_portions < 10:
            self.portions_lbl.configure(text=f"{min_portions} porciones", text_color="#FBBF24")
        else:
            self.portions_lbl.configure(text=f"{min_portions} porciones", text_color="#34D399")

        self.limiting_lbl.configure(text=f"Limitante: {limiting_name}")

        # Render rows
        for w in self.rows_scroll.winfo_children():
            w.destroy()

        if not self.current_recipe_items:
            ctk.CTkLabel(
                self.rows_scroll,
                text="Este producto aún no tiene ingredientes asignados en su receta.",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=DarkTheme.TEXT_MUTED
            ).pack(pady=40)
            return

        for idx, item in enumerate(self.current_recipe_items):
            row_bg = "#0B0F1D" if (idx % 2 == 0) else "#101626"
            rf = ctk.CTkFrame(self.rows_scroll, fg_color=row_bg, height=36, corner_radius=4)
            rf.pack(fill="x", pady=1)
            rf.pack_propagate(False)

            qty_g = item["quantity_g"]
            cost_g = item["cost_per_g"]
            stock_g = item["stock_g"]
            portion_cost = qty_g * cost_g
            possible = int(math.floor(max(0.0, stock_g) / qty_g)) if qty_g > 0 else 0

            # 1. Ingrediente
            ctk.CTkLabel(rf, text=item["name"], width=200, anchor="w", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#FFFFFF").pack(side="left", padx=4)

            # 2. Porción (g)
            ctk.CTkLabel(rf, text=f"{qty_g:,.0f} g", width=95, font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#38BDF8").pack(side="left", padx=2)

            # 3. Costo / g
            ctk.CTkLabel(rf, text=f"${cost_g:,.2f}", width=85, font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#94A3B8").pack(side="left", padx=2)

            # 4. Costo porción
            ctk.CTkLabel(rf, text=format_currency(portion_cost), width=110, font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#34D399").pack(side="left", padx=2)

            # 5. Stock Actual
            stock_txt = f"{stock_g:,.0f} g" if stock_g < 1000 else f"{stock_g/1000.0:,.2f} kg"
            stk_color = "#F87171" if stock_g <= 0 else ("#FBBF24" if stock_g < 1000 else "#CBD5E1")
            ctk.CTkLabel(rf, text=stock_txt, width=120, font=ctk.CTkFont(family="Segoe UI", size=10), text_color=stk_color).pack(side="left", padx=2)

            # 6. Rendimiento
            ctk.CTkLabel(rf, text=f"{possible} und", width=100, font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=stk_color).pack(side="left", padx=2)

            # 7. Acciones (Eliminar)
            del_btn = ctk.CTkButton(
                rf,
                text="",
                width=28,
                height=26,
                corner_radius=4,
                cursor="hand2",
                command=lambda ing_id=item["ingredient_id"]: self._remove_ingredient_from_recipe(ing_id)
            )
            apply_palette_button(del_btn, variant="eliminar", icon_name="trash_arrow_red", icon_size=(13, 13))
            del_btn.pack(side="left", padx=6)

    def _on_add_ingredient_clicked(self) -> None:
        sel = self.add_ing_combo.get()
        if not sel or " - " not in sel:
            messagebox.showerror("Error", "Seleccione un ingrediente válido.", parent=self)
            return

        try:
            ing_id = int(sel.split(" - ")[0])
        except ValueError:
            return

        # Check if already in recipe
        for item in self.current_recipe_items:
            if item["ingredient_id"] == ing_id:
                messagebox.showwarning("Atención", f"El ingrediente '{item['name']}' ya se encuentra en la receta.", parent=self)
                return

        raw_qty = self.add_qty_entry.get().strip().replace(",", ".")
        try:
            qty_g = float(raw_qty)
            if qty_g <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Error", "Ingrese una cantidad en gramos válida mayor a cero.", parent=self)
            return

        # Find ingredient object
        ing_obj = next((i for i in self.all_ingredients if i.id == ing_id), None)
        if not ing_obj:
            return

        self.current_recipe_items.append({
            "ingredient_id": ing_obj.id,
            "name": ing_obj.name,
            "quantity_g": qty_g,
            "cost_per_g": ing_obj.cost_per_g,
            "stock_g": ing_obj.stock_g
        })

        self.add_qty_entry.delete(0, "end")
        self._refresh_calculations_and_table()

    def _remove_ingredient_from_recipe(self, ingredient_id: int) -> None:
        self.current_recipe_items = [it for it in self.current_recipe_items if it["ingredient_id"] != ingredient_id]
        self._refresh_calculations_and_table()

    def _on_save_recipe(self) -> None:
        prod = self._get_active_product()
        if not prod:
            messagebox.showerror("Error", "Seleccione un producto para guardar la receta.", parent=self)
            return

        recipe_tuples = [(it["ingredient_id"], it["quantity_g"]) for it in self.current_recipe_items]

        try:
            with get_db_connection() as conn:
                IngredientModel.save_recipe(conn, prod.id, recipe_tuples)

            sound_manager.play_success()
            messagebox.showinfo(
                "Receta Guardada",
                f"Se ha actualizado exitosamente la receta de '{prod.name}' con {len(recipe_tuples)} ingredientes.\n"
                f"El costo de preparación del producto ha sido recalculado automáticamente.",
                parent=self
            )
            if self.on_recipe_saved_callback:
                self.on_recipe_saved_callback()
            self._load_selected_product_recipe()
        except Exception as ex:
            sound_manager.play_error()
            messagebox.showerror("Error", f"No se pudo guardar la receta: {ex}", parent=self)

