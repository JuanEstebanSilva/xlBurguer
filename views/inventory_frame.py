"""Catalog and Inventory Management Frame for XL Burguer.
Provides complete management of fast-food products, ingredients and recipes:
- Interactive columns with ascending/descending sorting and visual arrows.
- Omni-search by name, barcode, ID, or category.
- Multi-filtering by Category, Inventory Status (Normal, Bajo, Agotado), and Commercialization Type (Peso, Unidad).
- Automated inventory status calculation and colored badges.
- Rich ProductDetailModal ("Ver producto") with pricing, margins, valuation, and recipe ingredients in grams.
- Professional ProductFormModal ("Crear / Editar producto") with strict validations and NO product photographs.
- Quick access to Ingredients Management (in grams) and Recipe / Portions Manager.
- Compact, ultra-snug vertical layout eliminating dead space below the topbar.
"""

import logging
import math
import os
import sqlite3
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox
from typing import Callable, Dict, List, Optional, Tuple
import customtkinter as ctk
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from database.connection import get_db_connection, normalize_text
from models.ingredient import IngredientModel
from models.product import (
    Product,
    ProductModel,
    convert_quantity_to_base,
    format_currency,
    format_currency_short,
    format_stock_display
)
from models.user import User
from utils.asset_manager import center_modal, get_ctk_icon, get_tinted_ctk_icon, build_standard_modal_header
from utils.sound_manager import sound_manager
from utils.theme import DarkTheme, safe_reset_entry, apply_palette_button, PaletteButton, bind_tab_navigation
from views.ingredients_modal import IngredientsManagerModal
from views.pos_frame import TouchKeypadModal
from views.recipe_modal import RecipeManagerModal


def _set_dialog_icon_and_center(dialog: ctk.CTkToplevel, parent, w: int, h: int) -> None:
    """Center dialog and attach official window icon."""
    center_modal(dialog, w, h, parent)


# ─────────────────────────────────────────────────────────────────────────────
# 1. PRODUCT DETAIL MODAL (VER PRODUCTO / FICHA TÉCNICA)
# ─────────────────────────────────────────────────────────────────────────────
class ProductDetailModal(ctk.CTkToplevel):
    """Modern modal dialog displaying a complete technical & financial sheet of a product.
    Matches the official XL Burguer dark theme with topbar, white section headers,
    and streamlined financial & stock metrics.
    """

    def __init__(self, parent, product: Product, on_edit_request: Optional[Callable[[Product], None]] = None):
        super().__init__(parent)
        self.product = product
        self.on_edit_request = on_edit_request

        self.title(f"Ficha Técnica: {product.name}")
        self.resizable(False, False)
        self.configure(fg_color="#15171F")

        self._build_ui()
        _set_dialog_icon_and_center(self, parent, 600, 580)

        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self) -> None:
        p = self.product

        # ── Standard Executive Topbar with XL Burguer Logos (No [X] button, White Title & Icon) ──
        detail_icon = get_ctk_icon("eye_white", size=(16, 16))
        build_standard_modal_header(
            self,
            title_text="Detalle del Producto",
            title_icon=detail_icon,
            on_close_cmd=self.destroy,
            show_close_btn=False,
            text_color="#FFFFFF"
        )

        # ── Footer Actions (Permanently anchored at bottom) ──────────────────
        actions_row = ctk.CTkFrame(self, fg_color="transparent")
        actions_row.pack(fill="x", side="bottom", padx=24, pady=(6, 14))

        edit_btn = ctk.CTkButton(
            actions_row,
            text="  Editar Este Producto",
            image=get_ctk_icon("pen_gold", size=(16, 16)),
            compound="left",
            height=38,
            fg_color="#1F1A14",
            hover_color="#2A231A",
            border_color="#F59E0B",
            border_width=1.5,
            text_color="#FCD34D",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self._on_edit_click
        )
        edit_btn.pack(side="left")

        close_btn = ctk.CTkButton(
            actions_row,
            text="  Cerrar Ficha",
            image=get_ctk_icon("ban_red", size=(16, 16)),
            compound="left",
            width=130,
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
        close_btn.pack(side="right")

        # ── Body Card (Clean, snug, scrollable on smaller displays) ──────────
        body = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        body.pack(fill="both", expand=True, padx=20, pady=(6, 4))

        # ── Hero Banner: Modern, friendly, executive header with avatar & tags ──
        hero_banner = ctk.CTkFrame(
            body,
            fg_color="#161A24",
            border_color="#2A3245",
            border_width=1.5,
            corner_radius=10
        )
        hero_banner.pack(fill="x", pady=(0, 12))

        b_content = ctk.CTkFrame(hero_banner, fg_color="transparent")
        b_content.pack(fill="both", expand=True, padx=14, pady=12)

        # Avatar Box (Meat icon for peso, cube for unidad)
        avatar_icon_name = "meat_gold" if p.sale_type == "PESO" else "cube_gold"
        avatar_icon = get_ctk_icon(avatar_icon_name, size=(24, 24))
        avatar_box = ctk.CTkFrame(
            b_content,
            fg_color="#1E2332",
            border_color="#333C4F",
            border_width=1.5,
            corner_radius=8,
            width=46,
            height=46
        )
        avatar_box.pack(side="left", padx=(0, 12))
        avatar_box.pack_propagate(False)

        ctk.CTkLabel(avatar_box, image=avatar_icon, text="").pack(expand=True)

        # Title and Badges Info
        b_info = ctk.CTkFrame(b_content, fg_color="transparent")
        b_info.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            b_info,
            text=p.name.upper(),
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#FFFFFF"
        ).pack(anchor="w")

        # Badges row: Category pill, ID badge, Barcode badge
        tags_row = ctk.CTkFrame(b_info, fg_color="transparent")
        tags_row.pack(anchor="w", pady=(4, 0))

        # Category pill
        cat_badge = ctk.CTkFrame(tags_row, fg_color="#13233A", border_color="#1E40AF", border_width=1, corner_radius=5)
        cat_badge.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            cat_badge,
            image=get_ctk_icon("tags_white", size=(12, 12)),
            compound="left",
            text=f" {p.category_name}",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#93C5FD"
        ).pack(padx=8, pady=2)

        # ID pill
        id_badge = ctk.CTkFrame(tags_row, fg_color="#1E2230", border_color="#334155", border_width=1, corner_radius=5)
        id_badge.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            id_badge,
            text=f"ID #{p.id}",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#CBD5E1"
        ).pack(padx=8, pady=2)

        # Barcode pill
        barcode_text = p.barcode if p.barcode else "Sin código"
        bar_badge = ctk.CTkFrame(tags_row, fg_color="#1E2230", border_color="#334155", border_width=1, corner_radius=5)
        bar_badge.pack(side="left")
        ctk.CTkLabel(
            bar_badge,
            text=f"Cód: {barcode_text}",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#94A3B8"
        ).pack(padx=8, pady=2)

        # Right side: Sales Type Pill (REPLACES redundant "Normal" status)
        sale_icon = get_ctk_icon("scale_gold" if p.sale_type == "PESO" else "cube_gold", size=(14, 14))
        sale_text = f"  Venta por {p.unit_measure.upper()}" if p.sale_type == "PESO" else f"  Venta por {p.unit_measure.capitalize()}"
        sale_bg = "#261C0D" if p.sale_type == "PESO" else "#0B2338"
        sale_border = "#D97706" if p.sale_type == "PESO" else "#0284C7"
        sale_fg = "#FCD34D" if p.sale_type == "PESO" else "#7DD3FC"

        sale_pill = ctk.CTkFrame(
            b_content,
            fg_color=sale_bg,
            border_color=sale_border,
            border_width=1.5,
            corner_radius=6,
            height=32
        )
        sale_pill.pack(side="right", padx=(10, 0))
        ctk.CTkLabel(
            sale_pill,
            image=sale_icon,
            compound="left",
            text=sale_text,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=sale_fg
        ).pack(padx=10, pady=4)

        # ── Section 1: Financial & Commercial Metrics (4 Modern Cards) ───────
        sec1_header = ctk.CTkFrame(body, fg_color="transparent")
        sec1_header.pack(fill="x", pady=(0, 6))

        stats_icon = get_ctk_icon("chart_column_white", size=(16, 16))
        ctk.CTkLabel(
            sec1_header,
            image=stats_icon,
            compound="left",
            text="  MÉTRICAS FINANCIERAS Y PRECIOS",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFFFFF"
        ).pack(anchor="w")

        grid_frame = ctk.CTkFrame(body, fg_color="transparent")
        grid_frame.pack(fill="x", pady=(0, 12))
        grid_frame.columnconfigure((0, 1), weight=1, uniform="metric_cards")

        # Card 1: Precio Venta
        c1 = ctk.CTkFrame(grid_frame, fg_color="#161A24", border_color="#144C3D", border_width=1.5, corner_radius=10)
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=4, ipady=4)
        c1_top = ctk.CTkFrame(c1, fg_color="transparent")
        c1_top.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            c1_top,
            image=get_ctk_icon("tag_white", size=(14, 14)),
            compound="left",
            text="  PRECIO DE VENTA",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#94A3B8"
        ).pack(anchor="w")
        ctk.CTkLabel(c1, text=p.display_price_sale, font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"), text_color="#34D399").pack(anchor="w", padx=12)
        p_sub = f"${p.price_base:.1f}/g base" if p.sale_type == "PESO" else f"Unidad de venta: {p.unit_measure}"
        ctk.CTkLabel(c1, text=p_sub, font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#64748B").pack(anchor="w", padx=12, pady=(0, 6))

        # Card 2: Costo de Adquisición
        c2 = ctk.CTkFrame(grid_frame, fg_color="#161A24", border_color="#2A3245", border_width=1.5, corner_radius=10)
        c2.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=4, ipady=4)
        c2_top = ctk.CTkFrame(c2, fg_color="transparent")
        c2_top.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            c2_top,
            image=get_ctk_icon("coins_white", size=(14, 14)),
            compound="left",
            text="  COSTO DE COMPRA",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#94A3B8"
        ).pack(anchor="w")
        ctk.CTkLabel(c2, text=p.display_cost, font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"), text_color="#F8FAFC").pack(anchor="w", padx=12)
        c_sub = f"${p.cost:.1f}/g base" if p.sale_type == "PESO" else f"Costo por {p.unit_measure}"
        ctk.CTkLabel(c2, text=c_sub, font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#64748B").pack(anchor="w", padx=12, pady=(0, 6))

        # Card 3: Utilidad
        c3 = ctk.CTkFrame(grid_frame, fg_color="#161A24", border_color="#134739", border_width=1.5, corner_radius=10)
        c3.grid(row=1, column=0, sticky="nsew", padx=(0, 5), pady=4, ipady=4)
        c3_top = ctk.CTkFrame(c3, fg_color="transparent")
        c3_top.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            c3_top,
            image=get_ctk_icon("chart_column_white", size=(14, 14)),
            compound="left",
            text="  UTILIDAD ESTIMADA",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#94A3B8"
        ).pack(anchor="w")

        c3_mid = ctk.CTkFrame(c3, fg_color="transparent")
        c3_mid.pack(fill="x", padx=12)
        margin_sign = "+" if p.profit_margin_amount >= 0 else ""
        margin_color = "#34D399" if p.profit_margin_amount >= 0 else "#F87171"
        ctk.CTkLabel(
            c3_mid,
            text=f"{margin_sign}{format_currency_short(p.profit_margin_amount)}",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=margin_color
        ).pack(side="left")

        # Margin pill
        m_pill = ctk.CTkFrame(c3_mid, fg_color="#06281E", border_color="#059669", border_width=1, corner_radius=10)
        m_pill.pack(side="right")
        ctk.CTkLabel(
            m_pill,
            text=f"{p.profit_margin_pct:.1f}% margen",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#34D399"
        ).pack(padx=8, pady=1)

        ctk.CTkLabel(c3, text="Rentabilidad sobre precio venta", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#64748B").pack(anchor="w", padx=12, pady=(2, 6))

        # Card 4: IVA
        c4 = ctk.CTkFrame(grid_frame, fg_color="#161A24", border_color="#2A3245", border_width=1.5, corner_radius=10)
        c4.grid(row=1, column=1, sticky="nsew", padx=(5, 0), pady=4, ipady=4)
        c4_top = ctk.CTkFrame(c4, fg_color="transparent")
        c4_top.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            c4_top,
            image=get_ctk_icon("percent_white", size=(14, 14)),
            compound="left",
            text="  IMPUESTO A LAS VENTAS (IVA)",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#94A3B8"
        ).pack(anchor="w")

        c4_mid = ctk.CTkFrame(c4, fg_color="transparent")
        c4_mid.pack(fill="x", padx=12)
        ctk.CTkLabel(
            c4_mid,
            text=p.display_iva,
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#FFFFFF"
        ).pack(side="left")

        iva_desc = "Exento de alimentos" if p.iva == 0 else ("Tarifa Especial" if p.iva <= 5 else "Tarifa General")
        iva_pill = ctk.CTkFrame(c4_mid, fg_color="#1A202C", border_color="#334155", border_width=1, corner_radius=10)
        iva_pill.pack(side="right")
        ctk.CTkLabel(
            iva_pill,
            text=iva_desc,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#CBD5E1"
        ).pack(padx=8, pady=1)

        ctk.CTkLabel(c4, text="Gravamen tributario por ley", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#64748B").pack(anchor="w", padx=12, pady=(2, 6))

        # ── Section 2: Inventory Health & Valuation ──────────────────────────
        sec2_header = ctk.CTkFrame(body, fg_color="transparent")
        sec2_header.pack(fill="x", pady=(0, 6))

        box_icon = get_ctk_icon("box_open_white", size=(16, 16))
        ctk.CTkLabel(
            sec2_header,
            image=box_icon,
            compound="left",
            text="  ESTADO DE INVENTARIO Y EXISTENCIAS",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFFFFF"
        ).pack(anchor="w")

        inv_card = ctk.CTkFrame(
            body,
            fg_color="#161A24",
            border_color="#2A3245",
            border_width=1.5,
            corner_radius=10
        )
        inv_card.pack(fill="x", pady=(0, 8))

        # Stock Numbers Row
        s_row = ctk.CTkFrame(inv_card, fg_color="transparent")
        s_row.pack(fill="x", padx=14, pady=(10, 6))

        s_left = ctk.CTkFrame(s_row, fg_color="transparent")
        s_left.pack(side="left")
        ctk.CTkLabel(s_left, text="STOCK DISPONIBLE ACTUAL", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8").pack(anchor="w")
        ctk.CTkLabel(s_left, text=p.display_stock, font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"), text_color="#F8FAFC").pack(anchor="w")

        s_right = ctk.CTkFrame(s_row, fg_color="transparent")
        s_right.pack(side="right")
        ctk.CTkLabel(s_right, text="STOCK MÍNIMO DE ALERTA", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8").pack(anchor="e")
        ctk.CTkLabel(s_right, text=p.display_min_stock, font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"), text_color="#FBBF24").pack(anchor="e")

        # Health Chip: AUTHORITATIVE INVENTORY STATUS (Only here, exactly where it belongs!)
        if p.stock <= 0:
            health_text = "  Alerta: Producto sin existencias en almacén (Agotado)"
            health_icon = get_ctk_icon("ban_red", size=(14, 14))
            health_bg, health_border, health_fg = "#2D1115", "#DC2626", "#F87171"
        elif p.is_low_stock:
            health_text = f"  Atención: Stock bajo el nivel mínimo de alerta ({p.display_stock} disp.)"
            health_icon = get_ctk_icon("warning_amber", size=(14, 14))
            health_bg, health_border, health_fg = "#2E1C0C", "#D97706", "#FBBF24"
        else:
            health_text = f"  Nivel óptimo de inventario en almacén ({p.display_stock} disponibles)"
            health_icon = get_ctk_icon("check_green", size=(14, 14))
            health_bg, health_border, health_fg = "#06281E", "#059669", "#34D399"

        health_chip = ctk.CTkFrame(
            inv_card,
            fg_color=health_bg,
            border_color=health_border,
            border_width=1.2,
            corner_radius=6
        )
        health_chip.pack(fill="x", padx=14, pady=(2, 8))
        ctk.CTkLabel(
            health_chip,
            image=health_icon,
            compound="left",
            text=health_text,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=health_fg
        ).pack(anchor="w", padx=10, pady=6)

        # Thin divider
        ctk.CTkFrame(inv_card, fg_color="#252836", height=1).pack(fill="x", padx=14, pady=(2, 6))

        # Valuation row
        val_row = ctk.CTkFrame(inv_card, fg_color="transparent")
        val_row.pack(fill="x", padx=14, pady=(2, 8))

        v1 = ctk.CTkFrame(val_row, fg_color="transparent")
        v1.pack(side="left")
        ctk.CTkLabel(v1, text="Valoración al Costo:", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#94A3B8").pack(anchor="w")
        ctk.CTkLabel(v1, text=format_currency(p.total_inventory_valuation_cost), font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color="#CBD5E1").pack(anchor="w")

        v2 = ctk.CTkFrame(val_row, fg_color="transparent")
        v2.pack(side="right")
        ctk.CTkLabel(v2, text="Valoración a Precio Venta:", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#94A3B8").pack(anchor="e")
        ctk.CTkLabel(v2, text=format_currency(p.total_inventory_valuation_sale), font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color="#34D399").pack(anchor="e")

        # ── Section 3: Recipe & Grams Composition (XL Burguer) ───────────────
        with get_db_connection() as conn:
            recipe = IngredientModel.get_recipe_for_product(conn, p.id)
            limiting_info = IngredientModel.get_limiting_ingredient_details(conn, p.id)

        sec3_header = ctk.CTkFrame(body, fg_color="transparent")
        sec3_header.pack(fill="x", pady=(10, 6))

        recipe_icon = get_ctk_icon("chart_column_white", size=(16, 16))
        ctk.CTkLabel(
            sec3_header,
            image=recipe_icon,
            compound="left",
            text="  COMPOSICIÓN DE RECETA EN GRAMOS (XL BURGUER)",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFFFFF"
        ).pack(side="left")

        rec_btn = ctk.CTkButton(
            sec3_header,
            text=" Gestionar Receta",
            image=get_ctk_icon("pen_gold", size=(13, 13)),
            compound="left",
            height=28,
            fg_color="#1E293B",
            hover_color="#334155",
            border_color="#6366F1",
            border_width=1,
            text_color="#A5B4FC",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self._on_manage_recipe
        )
        rec_btn.pack(side="right")

        rec_card = ctk.CTkFrame(
            body,
            fg_color="#161A24",
            border_color="#2A3245",
            border_width=1.5,
            corner_radius=10
        )
        rec_card.pack(fill="x", pady=(0, 12))

        if recipe:
            # Header info: theoretical portions and limiting ingredient
            if limiting_info:
                lim_name, lim_stk, lim_req, lim_portions = limiting_info
                lim_bg = "#06281E" if lim_portions >= 10 else ("#2E1C0C" if lim_portions > 0 else "#2D1115")
                lim_border = "#059669" if lim_portions >= 10 else ("#D97706" if lim_portions > 0 else "#DC2626")
                lim_fg = "#34D399" if lim_portions >= 10 else ("#FBBF24" if lim_portions > 0 else "#F87171")
                lim_status_text = f"  Porciones disponibles con inventario actual: {lim_portions} und. (Limitado por: {lim_name} - {lim_stk:,.0f}g disp.)"
            else:
                lim_bg, lim_border, lim_fg = "#06281E", "#059669", "#34D399"
                lim_status_text = "  Receta activa sin ingredientes limitantes."

            port_chip = ctk.CTkFrame(rec_card, fg_color=lim_bg, border_color=lim_border, border_width=1.2, corner_radius=6)
            port_chip.pack(fill="x", padx=12, pady=(10, 6))
            ctk.CTkLabel(
                port_chip,
                text=lim_status_text,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=lim_fg
            ).pack(anchor="w", padx=10, pady=4)

            # Table header
            t_hdr = ctk.CTkFrame(rec_card, fg_color="#1E2332", height=26, corner_radius=4)
            t_hdr.pack(fill="x", padx=12, pady=(4, 2))
            t_hdr.pack_propagate(False)

            ctk.CTkLabel(t_hdr, text="Ingrediente", width=180, anchor="w", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8").pack(side="left", padx=4)
            ctk.CTkLabel(t_hdr, text="Porción (g)", width=80, anchor="center", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8").pack(side="left", padx=4)
            ctk.CTkLabel(t_hdr, text="Costo / Porción", width=100, anchor="center", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8").pack(side="left", padx=4)
            ctk.CTkLabel(t_hdr, text="Rendimiento", width=90, anchor="center", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94A3B8").pack(side="left", padx=4)

            for idx, item in enumerate(recipe):
                rf = ctk.CTkFrame(rec_card, fg_color="#0F131D" if idx % 2 == 0 else "#141A27", height=28, corner_radius=4)
                rf.pack(fill="x", padx=12, pady=1)
                rf.pack_propagate(False)

                ctk.CTkLabel(rf, text=item.ingredient_name, width=180, anchor="w", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#FFFFFF").pack(side="left", padx=4)
                ctk.CTkLabel(rf, text=f"{item.quantity_g:,.0f} g", width=80, anchor="center", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#38BDF8").pack(side="left", padx=4)
                ctk.CTkLabel(rf, text=format_currency(item.cost_contribution), width=100, anchor="center", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#34D399").pack(side="left", padx=4)
                ctk.CTkLabel(rf, text=f"{item.possible_portions} und", width=90, anchor="center", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#CBD5E1").pack(side="left", padx=4)

            ctk.CTkFrame(rec_card, fg_color="transparent", height=6).pack()
        else:
            ctk.CTkLabel(
                rec_card,
                text="Este producto no tiene receta de ingredientes registrada.\nSe comercializa como unidad directa o bebida de inventario simple.",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="#94A3B8"
            ).pack(padx=16, pady=16)

    def _on_manage_recipe(self) -> None:
        p = self.product
        self.destroy()
        RecipeManagerModal(self.master, selected_product_id=p.id)

    def _on_edit_click(self) -> None:
        p = self.product
        callback = self.on_edit_request
        self.destroy()
        if callback:
            callback(p)


# ─────────────────────────────────────────────────────────────────────────────
# 2. PRODUCT FORM MODAL (CREAR / EDITAR PRODUCTO)
# ─────────────────────────────────────────────────────────────────────────────
class ProductFormModal(ctk.CTkToplevel):
    """Modern modal dialog for Creating or Editing a product with thorough field validations.
    Features executive topbar, dark theme palette matching the app, compact IVA input,
    attractive margin calculations card, compact spin buttons for stock, zero-scrollbar layout,
    and full Tab navigation.
    """

    UNIT_OPTIONS_PESO = ["kg", "lb", "g"]
    UNIT_OPTIONS_UNIDAD = ["Unidad", "Paquete", "Botella", "Pieza", "Caja"]
    UNIT_MAP_UNIDAD_TO_DB = {
        "Unidad": "und",
        "Paquete": "pqte",
        "Botella": "botella",
        "Pieza": "pza",
        "Caja": "caja",
    }
    UNIT_MAP_DB_TO_UNIDAD = {
        "und": "Unidad",
        "unidad": "Unidad",
        "unidades": "Unidad",
        "pqte": "Paquete",
        "paquete": "Paquete",
        "botella": "Botella",
        "botellas": "Botella",
        "pza": "Pieza",
        "pieza": "Pieza",
        "caja": "Caja",
    }

    def __init__(
        self,
        parent,
        product: Optional[Product] = None,
        on_save_callback: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        self.product = product
        self.on_save_callback = on_save_callback

        is_edit = product is not None
        mode_title = f"Editar Producto: {product.name}" if is_edit else "Creación de nuevo producto"
        self.title(mode_title)
        self.resizable(False, False)
        self.configure(fg_color="#15171F")

        # Load available categories
        with get_db_connection() as conn:
            self.categories = ProductModel.get_categories(conn)
        self.cat_dict = {name: cid for cid, name in self.categories}
        self.cat_id_to_name = {cid: name for cid, name in self.categories}

        self._build_ui(mode_title, is_edit)
        _set_dialog_icon_and_center(self, parent, 630, 590)

        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self, title: str, is_edit: bool) -> None:
        p = self.product

        # ── Executive Topbar with XL Burguer Logos, White Title & Icon, No [X] Button ──
        title_icon = get_ctk_icon("pen_white", size=(16, 16)) if is_edit else get_ctk_icon("file_circle_plus_white", size=(16, 16))
        title_text = "Editar Producto" if is_edit else "Creación de Nuevo Producto"
        build_standard_modal_header(
            self,
            title_text=title_text,
            title_icon=title_icon,
            on_close_cmd=self.destroy,
            show_close_btn=False,
            text_color="#FFFFFF"
        )

        # ── Footer Actions (Permanently anchored at bottom) ──────────────────
        actions_row = ctk.CTkFrame(self, fg_color="transparent", height=48)
        actions_row.pack(fill="x", side="bottom", padx=24, pady=(6, 14))
        actions_row.pack_propagate(False)

        self.cancel_btn = ctk.CTkButton(
            actions_row,
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
        self.cancel_btn.pack(side="left")

        save_btn_text = "  Editar Cambios" if is_edit else "  Crear Producto"
        save_btn_icon = get_ctk_icon("pen_orange", size=(15, 15)) if is_edit else (get_ctk_icon("floppy_green", size=(15, 15)) or get_ctk_icon("floppy_white", size=(15, 15)))
        save_btn_fg = "#2A1608" if is_edit else "#0A1D16"
        save_btn_hover = "#451A03" if is_edit else "#0F2E22"
        save_btn_border = "#F59E0B" if is_edit else "#10B981"
        save_btn_text_color = "#FBBF24" if is_edit else "#34D399"

        self.save_btn = ctk.CTkButton(
            actions_row,
            text=save_btn_text,
            image=save_btn_icon,
            compound="left",
            width=165,
            height=38,
            fg_color=save_btn_fg,
            hover_color=save_btn_hover,
            border_color=save_btn_border,
            border_width=1.5,
            text_color=save_btn_text_color,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self._save
        )
        self.save_btn.pack(side="right")
        self.save_btn.bind("<Return>", lambda e: self._save())

        # ── Scrollable Form Area (Ensures complete visibility across all resolutions) ──
        form = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        form.pack(fill="both", expand=True, padx=20, pady=(6, 4))
        self.form_frame = form

        # ── Row 1: Identification (ID producto & Código de barras) ───────────
        row1 = ctk.CTkFrame(form, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 9))

        # ID producto (Compact column, editable on create)
        c_id = ctk.CTkFrame(row1, fg_color="transparent")
        c_id.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(c_id, text="ID producto", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8").pack(anchor="w", pady=(0, 2))
        self.id_entry = ctk.CTkEntry(
            c_id,
            width=110,
            height=36,
            fg_color="#14161E",
            border_color="#252836",
            border_width=1,
            text_color="#F8FAFC",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            corner_radius=6
        )
        if p:
            self.id_entry.insert(0, str(p.id))
            self.id_entry.configure(state="disabled", text_color="#64748B")
        else:
            try:
                with get_db_connection() as conn:
                    next_id = ProductModel.get_max_id(conn) + 1
            except Exception:
                next_id = 1
            self.id_entry.insert(0, str(next_id))
        self.id_entry.pack(fill="x")

        # Código de barras (Wider box, pre-filled with EAN candidate)
        c_bar = ctk.CTkFrame(row1, fg_color="transparent")
        c_bar.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(c_bar, text="Código de barras", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8").pack(anchor="w", pady=(0, 2))
        auto_code = ""
        if not p:
            try:
                with get_db_connection() as conn:
                    auto_code = ProductModel.get_next_available_barcode(conn)
            except Exception:
                auto_code = "1"

        self.barcode_entry = ctk.CTkEntry(
            c_bar,
            height=36,
            placeholder_text=f"Ej : {auto_code or '1'} ...",
            placeholder_text_color="#475569",
            fg_color="#14161E",
            border_color="#252836",
            border_width=1,
            text_color="#F8FAFC",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            corner_radius=6
        )
        if p and p.barcode:
            self.barcode_entry.insert(0, p.barcode)
        elif not p and auto_code:
            self.barcode_entry.insert(0, auto_code)
        self.barcode_entry.pack(fill="x")

        # ── Row 2: Nombre del producto ───────────────────────────────────────
        c_name = ctk.CTkFrame(form, fg_color="transparent")
        c_name.pack(fill="x", pady=(0, 9))
        ctk.CTkLabel(c_name, text="Nombre del producto", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8").pack(anchor="w", pady=(0, 2))
        self.name_entry = ctk.CTkEntry(
            c_name,
            height=36,
            placeholder_text="Ej : Punta de anca, queso campesino ...",
            placeholder_text_color="#475569",
            fg_color="#14161E",
            border_color="#252836",
            border_width=1,
            text_color="#F8FAFC",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            corner_radius=6
        )
        if p:
            self.name_entry.insert(0, p.name)
        self.name_entry.pack(fill="x")

        # ── Row 3: Categoría: & Tipo de venta: ───────────────────────────────
        self.row3 = ctk.CTkFrame(form, fg_color="transparent")
        self.row3.pack(fill="x", pady=(0, 9))
        self.row3.columnconfigure(0, weight=1)
        self.row3.columnconfigure(1, weight=1)

        # Categoría
        c_cat = ctk.CTkFrame(self.row3, fg_color="transparent")
        c_cat.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ctk.CTkLabel(c_cat, text="Categoría:", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8").pack(anchor="w", pady=(0, 2))

        cat_names = list(self.cat_dict.keys())
        cat_values = ["-- Seleccionar categoría --"] + cat_names + ["Otra..."]
        self.cat_combo = ctk.CTkComboBox(
            c_cat,
            height=36,
            values=cat_values,
            fg_color="#14161E",
            border_color="#252836",
            border_width=1,
            text_color="#F8FAFC",
            dropdown_fg_color="#181A22",
            dropdown_text_color="#F8FAFC",
            dropdown_hover_color="#252836",
            corner_radius=6,
            state="readonly",
            command=self._on_category_changed
        )
        if p:
            self.cat_combo.set(self.cat_id_to_name.get(p.category_id, cat_names[0] if cat_names else "Otra..."))
        else:
            self.cat_combo.set("-- Seleccionar categoría --")
        self.cat_combo.pack(fill="x")

        # Tipo de venta
        c_type = ctk.CTkFrame(self.row3, fg_color="transparent")
        c_type.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ctk.CTkLabel(c_type, text="Tipo de venta:", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8").pack(anchor="w", pady=(0, 2))

        type_box = ctk.CTkFrame(c_type, fg_color="transparent")
        type_box.pack(fill="x")
        type_box.columnconfigure((0, 1), weight=1, uniform="type_btns")

        self.current_sale_type = "PESO" if (not p or p.sale_type == "PESO") else "UNIDAD"

        self.btn_peso = ctk.CTkButton(
            type_box,
            text=" Peso",
            compound="left",
            height=36,
            corner_radius=6,
            cursor="hand2",
            command=lambda: self._select_sale_type("PESO")
        )
        self.btn_peso.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        self.btn_unidad = ctk.CTkButton(
            type_box,
            text=" Unidad",
            compound="left",
            height=36,
            corner_radius=6,
            cursor="hand2",
            command=lambda: self._select_sale_type("UNIDAD")
        )
        self.btn_unidad.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        # Dynamic New Category Frame (revealed when 'Otra...' is selected)
        self.new_cat_frame = ctk.CTkFrame(form, fg_color="#10131B", border_color="#252836", border_width=1, corner_radius=6)
        new_cat_inner = ctk.CTkFrame(self.new_cat_frame, fg_color="transparent")
        new_cat_inner.pack(fill="x", padx=10, pady=6)
        ctk.CTkLabel(new_cat_inner, text="Nombre de la nueva categoría:", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#FBBF24").pack(anchor="w", pady=(0, 2))
        self.new_cat_entry = ctk.CTkEntry(
            new_cat_inner,
            height=32,
            placeholder_text="Escriba el nombre de la nueva categoría...",
            placeholder_text_color="#475569",
            fg_color="#14161E",
            border_color="#F59E0B",
            border_width=1,
            text_color="#F8FAFC",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            corner_radius=6
        )
        self.new_cat_entry.pack(fill="x")

        # ── Row 4: Unidad de medida: & IVA % ─────────────────────────────────
        self.row4 = ctk.CTkFrame(form, fg_color="transparent")
        self.row4.pack(fill="x", pady=(0, 9))
        self.row4.columnconfigure(0, weight=1)
        self.row4.columnconfigure(1, weight=1)

        # Unidad de medida (Strictly locked options, read-only)
        c_unit = ctk.CTkFrame(self.row4, fg_color="transparent")
        c_unit.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ctk.CTkLabel(c_unit, text="Unidad de medida:", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8").pack(anchor="w", pady=(0, 2))

        init_units = self.UNIT_OPTIONS_PESO if self.current_sale_type == "PESO" else self.UNIT_OPTIONS_UNIDAD
        self.unit_combo = ctk.CTkComboBox(
            c_unit,
            height=36,
            values=init_units,
            fg_color="#14161E",
            border_color="#252836",
            border_width=1,
            text_color="#F8FAFC",
            dropdown_fg_color="#181A22",
            dropdown_text_color="#F8FAFC",
            dropdown_hover_color="#252836",
            corner_radius=6,
            state="readonly",
            command=self._on_unit_changed
        )
        if p:
            if self.current_sale_type == "PESO":
                self.unit_combo.set(p.unit_measure if p.unit_measure in self.UNIT_OPTIONS_PESO else "kg")
            else:
                self.unit_combo.set(self.UNIT_MAP_DB_TO_UNIDAD.get(p.unit_measure.lower(), "Unidad"))
        else:
            self.unit_combo.set("kg" if self.current_sale_type == "PESO" else "Unidad")
        self.unit_combo.pack(fill="x")

        # IVA % (Caja compacta con chips directos y validación max 100%)
        c_iva = ctk.CTkFrame(self.row4, fg_color="transparent")
        c_iva.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ctk.CTkLabel(c_iva, text="IVA %", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8").pack(anchor="w", pady=(0, 2))

        iva_box = ctk.CTkFrame(c_iva, fg_color="transparent")
        iva_box.pack(fill="x")

        entry_iva_frame = ctk.CTkFrame(iva_box, fg_color="#14161E", border_color="#252836", border_width=1, corner_radius=6, width=60, height=36)
        entry_iva_frame.pack(side="left", padx=(0, 6))
        entry_iva_frame.pack_propagate(False)

        self.iva_entry = ctk.CTkEntry(
            entry_iva_frame,
            fg_color="transparent",
            border_width=0,
            text_color="#F8FAFC",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            justify="center"
        )
        curr_iva = int(p.iva) if p and float(p.iva).is_integer() else (p.iva if p else 0)
        self.iva_entry.insert(0, str(curr_iva))
        self.iva_entry.pack(side="left", fill="both", expand=True, padx=(4, 1))
        self.iva_entry.bind("<KeyRelease>", lambda e: self._on_iva_text_changed())

        ctk.CTkLabel(entry_iva_frame, text="%", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8").pack(side="right", padx=(0, 6))

        self.iva_chips = {}
        for rate in [0, 5, 19]:
            btn = ctk.CTkButton(
                iva_box,
                text=f"{rate}%",
                width=42,
                height=36,
                corner_radius=6,
                cursor="hand2",
                command=lambda r=rate: self._set_iva_preset(r)
            )
            btn.pack(side="left", padx=2)
            self.iva_chips[rate] = btn

        # ── Row 5: Precio de venta & Precio de compra ────────────────────────
        row5 = ctk.CTkFrame(form, fg_color="transparent")
        row5.pack(fill="x", pady=(0, 9))
        row5.columnconfigure(0, weight=1)
        row5.columnconfigure(1, weight=1)

        # Precio de venta
        c_pventa = ctk.CTkFrame(row5, fg_color="transparent")
        c_pventa.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.lbl_pventa = ctk.CTkLabel(c_pventa, text="Precio de venta ($/Kg):", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8")
        self.lbl_pventa.pack(anchor="w", pady=(0, 2))

        self.price_entry = ctk.CTkEntry(
            c_pventa,
            height=36,
            placeholder_text="$ 200.000",
            placeholder_text_color="#475569",
            fg_color="#14161E",
            border_color="#252836",
            border_width=1,
            text_color="#F8FAFC",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            corner_radius=6
        )
        if p:
            val_p = p.unit_selling_price_commercial
            self.price_entry.insert(0, f"$ {int(val_p):,}".replace(",", "."))
        self.price_entry.pack(fill="x")
        self.price_entry.bind("<KeyRelease>", lambda e: self._update_calculation_helpers())

        # Precio de compra
        c_pcompra = ctk.CTkFrame(row5, fg_color="transparent")
        c_pcompra.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.lbl_pcompra = ctk.CTkLabel(c_pcompra, text="Precio de compra ($/Kg):", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8")
        self.lbl_pcompra.pack(anchor="w", pady=(0, 2))

        self.cost_entry = ctk.CTkEntry(
            c_pcompra,
            height=36,
            placeholder_text="$ 100.000",
            placeholder_text_color="#475569",
            fg_color="#14161E",
            border_color="#252836",
            border_width=1,
            text_color="#F8FAFC",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            corner_radius=6
        )
        if p:
            val_c = p.unit_cost_commercial
            self.cost_entry.insert(0, f"$ {int(val_c):,}".replace(",", "."))
        self.cost_entry.pack(fill="x")
        self.cost_entry.bind("<KeyRelease>", lambda e: self._update_calculation_helpers())

        # ── Row 6: Attractive Margins & Equivalences Visual Card (Mockup Style) ─
        self.calc_card = ctk.CTkFrame(form, fg_color="#10121A", border_color="#252836", border_width=1, corner_radius=8, height=92)
        self.calc_card.pack(fill="x", pady=(0, 9))
        self.calc_card.pack_propagate(False)

        # Left container (Ganancia estimada + Equivalencias)
        left_frame = ctk.CTkFrame(self.calc_card, fg_color="transparent")
        left_frame.pack(side="left", fill="both", expand=True, padx=(14, 8), pady=8)

        # Col 1: Ganancia estimada
        col_gain = ctk.CTkFrame(left_frame, fg_color="transparent")
        col_gain.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            col_gain,
            text="Ganancia estimada:",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8"
        ).pack(anchor="w")

        self.lbl_profit_val = ctk.CTkLabel(
            col_gain,
            text="+$ 0 / kg",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#34D399"
        )
        self.lbl_profit_val.pack(anchor="w", pady=(2, 0))

        # Col 2: Equivalencias (3 vertical lines)
        col_equiv = ctk.CTkFrame(left_frame, fg_color="transparent")
        col_equiv.pack(side="left", fill="both", expand=True, padx=(10, 0))

        self.lbl_equiv_title = ctk.CTkLabel(
            col_equiv,
            text="Equivalencias:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#C8BFE7"
        )
        self.lbl_equiv_title.pack(anchor="w")

        self.lbl_equiv_line1 = ctk.CTkLabel(col_equiv, text="1 Lb = $ 0", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#C8BFE7")
        self.lbl_equiv_line1.pack(anchor="w", pady=(1, 0))

        self.lbl_equiv_line2 = ctk.CTkLabel(col_equiv, text="100g = $ 0", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#C8BFE7")
        self.lbl_equiv_line2.pack(anchor="w")

        self.lbl_equiv_line3 = ctk.CTkLabel(col_equiv, text="1 Kg = $ 0", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#C8BFE7")
        self.lbl_equiv_line3.pack(anchor="w")

        # Middle vertical divider line
        self.calc_divider = ctk.CTkFrame(self.calc_card, width=2, fg_color="#334155")
        self.calc_divider.pack(side="left", fill="y", padx=8, pady=10)

        # Right container (Donut Chart + Margen percentage)
        right_frame = ctk.CTkFrame(self.calc_card, fg_color="transparent")
        right_frame.pack(side="right", fill="both", expand=True, padx=(8, 14), pady=8)

        center_right = ctk.CTkFrame(right_frame, fg_color="transparent")
        center_right.pack(expand=True)

        self.chart_canvas = tk.Canvas(center_right, width=64, height=60, bg="#10121A", highlightthickness=0)
        self.chart_canvas.pack(side="left", padx=(0, 10))

        self.lbl_margin_val = ctk.CTkLabel(
            center_right,
            text="Margen: 0.0%",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#C8BFE7"
        )
        self.lbl_margin_val.pack(side="left")

        # ── Row 7: Compact 3-Column Stock & Status Row (With spin buttons) ─────
        row7 = ctk.CTkFrame(form, fg_color="transparent")
        row7.pack(fill="x", pady=(0, 8))
        row7.columnconfigure(0, weight=3)
        row7.columnconfigure(1, weight=3)
        row7.columnconfigure(2, weight=4)

        # Col 0: Stock inicial
        c_sinit = ctk.CTkFrame(row7, fg_color="transparent")
        c_sinit.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=2)
        self.lbl_stock = ctk.CTkLabel(c_sinit, text="Stock inicial (Kg):", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8")
        self.lbl_stock.pack(anchor="w", pady=(0, 2))

        box_sinit = ctk.CTkFrame(c_sinit, fg_color="#14161E", border_color="#252836", border_width=1, corner_radius=6, height=38)
        box_sinit.pack(fill="x", pady=2)
        box_sinit.pack_propagate(False)

        btn_sinit_minus = ctk.CTkButton(
            box_sinit,
            text="−",
            width=26,
            height=28,
            corner_radius=4,
            fg_color="#1E2330",
            hover_color="#2A3346",
            text_color="#F8FAFC",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            cursor="hand2",
            command=lambda: self._step_stock(-1)
        )
        btn_sinit_minus.pack(side="left", padx=(4, 2))

        self.lbl_stock_unit = ctk.CTkLabel(box_sinit, text="Kg", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8")
        self.lbl_stock_unit.pack(side="right", padx=(2, 6))

        btn_sinit_plus = ctk.CTkButton(
            box_sinit,
            text="+",
            width=26,
            height=28,
            corner_radius=4,
            fg_color="#1E2330",
            hover_color="#2A3346",
            text_color="#F8FAFC",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            cursor="hand2",
            command=lambda: self._step_stock(1)
        )
        btn_sinit_plus.pack(side="right", padx=(2, 2))

        self.stock_entry = ctk.CTkEntry(
            box_sinit,
            fg_color="transparent",
            border_width=0,
            text_color="#F8FAFC",
            justify="center",
            placeholder_text="0",
            font=ctk.CTkFont(family="Segoe UI", size=12)
        )
        if p:
            if p.sale_type == "PESO":
                u = p.unit_measure.lower().strip()
                val_s = p.stock / 1000.0 if u == "kg" else (p.stock / 500.0 if u == "lb" else p.stock)
            else:
                val_s = p.stock
            self.stock_entry.insert(0, str(int(val_s) if float(val_s).is_integer() else val_s))
        self.stock_entry.pack(side="left", fill="both", expand=True, padx=(2, 2))
        self.stock_entry.bind("<KeyRelease>", lambda e: self._update_live_status())

        # Col 1: Stock minimo
        c_smin = ctk.CTkFrame(row7, fg_color="transparent")
        c_smin.grid(row=0, column=1, sticky="nsew", padx=(5, 5), pady=2)
        self.lbl_min_stock = ctk.CTkLabel(c_smin, text="Stock mín. alerta (Kg):", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8")
        self.lbl_min_stock.pack(anchor="w", pady=(0, 2))

        box_smin = ctk.CTkFrame(c_smin, fg_color="#14161E", border_color="#252836", border_width=1, corner_radius=6, height=38)
        box_smin.pack(fill="x", pady=2)
        box_smin.pack_propagate(False)

        btn_smin_minus = ctk.CTkButton(
            box_smin,
            text="−",
            width=26,
            height=28,
            corner_radius=4,
            fg_color="#1E2330",
            hover_color="#2A3346",
            text_color="#F8FAFC",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            cursor="hand2",
            command=lambda: self._step_min_stock(-1)
        )
        btn_smin_minus.pack(side="left", padx=(4, 2))

        self.lbl_min_unit = ctk.CTkLabel(box_smin, text="Kg", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8")
        self.lbl_min_unit.pack(side="right", padx=(2, 6))

        btn_smin_plus = ctk.CTkButton(
            box_smin,
            text="+",
            width=26,
            height=28,
            corner_radius=4,
            fg_color="#1E2330",
            hover_color="#2A3346",
            text_color="#F8FAFC",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            cursor="hand2",
            command=lambda: self._step_min_stock(1)
        )
        btn_smin_plus.pack(side="right", padx=(2, 2))

        self.min_stock_entry = ctk.CTkEntry(
            box_smin,
            fg_color="transparent",
            border_width=0,
            text_color="#F8FAFC",
            justify="center",
            placeholder_text="0",
            font=ctk.CTkFont(family="Segoe UI", size=12)
        )
        if p:
            if p.sale_type == "PESO":
                u = p.unit_measure.lower().strip()
                val_ms = p.min_stock / 1000.0 if u == "kg" else (p.min_stock / 500.0 if u == "lb" else p.min_stock)
            else:
                val_ms = p.min_stock
            self.min_stock_entry.insert(0, str(int(val_ms) if float(val_ms).is_integer() else val_ms))
        self.min_stock_entry.pack(side="left", fill="both", expand=True, padx=(2, 2))
        self.min_stock_entry.bind("<KeyRelease>", lambda e: self._update_live_status())


        # Col 2: Estado proyectado
        c_status = ctk.CTkFrame(row7, fg_color="transparent")
        c_status.grid(row=0, column=2, sticky="nsew", padx=(5, 0), pady=2)
        ctk.CTkLabel(c_status, text="Estado proyectado:", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8").pack(anchor="w", pady=(0, 2))

        self.live_status_chip = ctk.CTkFrame(
            c_status,
            fg_color="#06281E",
            border_color="#059669",
            border_width=1.5,
            corner_radius=6,
            height=38
        )
        self.live_status_chip.pack(fill="x", pady=2)
        self.live_status_chip.pack_propagate(False)

        self.live_status_lbl = ctk.CTkLabel(
            self.live_status_chip,
            text="✔ Normal",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#34D399"
        )
        self.live_status_lbl.pack(expand=True)

        # ── Render Initial Dynamic States ────────────────────────────────────
        self._render_type_buttons()
        self._render_iva_chips()
        self._apply_type_labels()
        self._update_calculation_helpers()
        self._update_live_status()

        # Setup keyboard TAB navigation
        self._setup_tab_navigation()

    def _setup_tab_navigation(self) -> None:
        """Bind Tab and Shift-Tab traversal to navigate cleanly across form widgets."""
        def _get_active_tab_widgets():
            widgets = [
                self.id_entry,
                self.barcode_entry,
                self.name_entry,
                self.cat_combo,
            ]
            if self.cat_combo.get() == "Otra..." and self.new_cat_frame.winfo_manager() == "pack":
                widgets.append(self.new_cat_entry)
            widgets.extend([
                self.btn_peso,
                self.btn_unidad,
                self.unit_combo,
                self.iva_entry,
                self.price_entry,
                self.cost_entry,
                self.stock_entry,
                self.min_stock_entry,
                self.cancel_btn,
                self.save_btn,
            ])
            return widgets

        def _on_form_focus(w):
            if w in [self.id_entry, self.barcode_entry, self.name_entry]:
                try:
                    self.form_frame._parent_canvas.yview_moveto(0.0)
                except Exception:
                    pass
            elif w in [self.stock_entry, self.min_stock_entry, self.cancel_btn, self.save_btn]:
                try:
                    self.form_frame._parent_canvas.yview_moveto(1.0)
                except Exception:
                    pass

        bind_tab_navigation(
            self,
            _get_active_tab_widgets,
            on_enter=self._save,
            focus_color="#38BDF8",
            on_focus_callback=_on_form_focus
        )


    def _on_category_changed(self, choice: str) -> None:
        """Show new category input when 'Otra...' is picked, or hide otherwise."""
        if choice == "Otra...":
            self.new_cat_frame.pack(fill="x", pady=(0, 9), after=self.row3)
            self.new_cat_entry.focus_set()
        else:
            self.new_cat_frame.pack_forget()

    def _select_sale_type(self, sale_type: str) -> None:
        self.current_sale_type = sale_type
        # Update dropdown options strictly based on sale type
        new_units = self.UNIT_OPTIONS_PESO if sale_type == "PESO" else self.UNIT_OPTIONS_UNIDAD
        self.unit_combo.configure(values=new_units)
        self.unit_combo.set("kg" if sale_type == "PESO" else "Unidad")

        self._render_type_buttons()
        self._apply_type_labels()
        self._update_calculation_helpers()
        self._update_live_status()

    def _render_type_buttons(self) -> None:
        if self.current_sale_type == "PESO":
            self.btn_peso.configure(
                fg_color="#2A1220",
                hover_color="#3B192E",
                border_color="#EC4899",
                border_width=1.5,
                text_color="#F472B6",
                image=get_ctk_icon("scale_pink", size=(18, 18))
            )
            self.btn_unidad.configure(
                fg_color="#14161E",
                hover_color="#1E293B",
                border_color="#252836",
                border_width=1,
                text_color="#94A3B8",
                image=get_ctk_icon("cube_slate", size=(18, 18))
            )
        else:
            self.btn_peso.configure(
                fg_color="#14161E",
                hover_color="#1E293B",
                border_color="#252836",
                border_width=1,
                text_color="#94A3B8",
                image=get_ctk_icon("scale_slate", size=(18, 18))
            )
            self.btn_unidad.configure(
                fg_color="#2A1220",
                hover_color="#3B192E",
                border_color="#EC4899",
                border_width=1.5,
                text_color="#F472B6",
                image=get_ctk_icon("cube_pink", size=(18, 18))
            )

    def _draw_margin_chart(self, margin_pct: float) -> None:
        """Render a sleek circular donut chart matching user requirements with #C8BFE7 slice."""
        if not hasattr(self, "chart_canvas"):
            return
        c = self.chart_canvas
        c.delete("all")
        cx, cy = 32, 30
        rx_out, ry_out = 26, 26
        rx_in, ry_in = 15, 15

        # Background track (cost slice or empty track)
        c.create_oval(cx - rx_out, cy - ry_out, cx + rx_out, cy + ry_out, fill="#1F2937", outline="")

        pct = max(0.0, min(100.0, margin_pct))
        if pct > 0:
            slice_color = "#C8BFE7" if margin_pct >= 0 else "#F87171"
            extent = -(pct / 100.0) * 360.0
            c.create_arc(
                cx - rx_out, cy - ry_out, cx + rx_out, cy + ry_out,
                start=90, extent=extent,
                fill=slice_color, outline=""
            )

        # Inner donut cutout
        c.create_oval(cx - rx_in, cy - ry_in, cx + rx_in, cy + ry_in, fill="#10121A", outline="")

    def _set_iva_preset(self, rate: int) -> None:
        self.iva_entry.delete(0, "end")
        self.iva_entry.insert(0, str(rate))
        self._render_iva_chips()
        self._update_calculation_helpers()

    def _on_iva_text_changed(self) -> None:
        self._render_iva_chips()
        self._update_calculation_helpers()

    def _render_iva_chips(self) -> None:
        try:
            val = int(float(self.iva_entry.get().replace(",", ".").strip() or "0"))
        except Exception:
            val = -1
        for rate, btn in self.iva_chips.items():
            if rate == val:
                btn.configure(
                    fg_color="#1E293B",
                    hover_color="#25354D",
                    border_color="#3B82F6",
                    border_width=1.5,
                    text_color="#60A5FA"
                )
            else:
                btn.configure(
                    fg_color="#14161E",
                    hover_color="#1E293B",
                    border_color="#252836",
                    border_width=1,
                    text_color="#94A3B8"
                )

    def _on_unit_changed(self, val: str) -> None:
        self._apply_type_labels()
        self._update_calculation_helpers()

    def _apply_type_labels(self) -> None:
        u = self.unit_combo.get().strip() or ("kg" if self.current_sale_type == "PESO" else "Unidad")
        unit_display = u.capitalize() if u.lower() == "kg" else u

        if self.current_sale_type == "PESO":
            self.lbl_pventa.configure(text=f"Precio de venta ($/{unit_display}):")
            self.lbl_pcompra.configure(text=f"Precio de compra ($/{unit_display}):")
            self.lbl_stock.configure(text=f"Stock inicial ({unit_display}):" if not self.product else f"Stock actual ({unit_display}):")
            self.lbl_min_stock.configure(text=f"Stock mín. alerta ({unit_display}):")
        else:
            self.lbl_pventa.configure(text=f"Precio de venta ($/{u}):")
            self.lbl_pcompra.configure(text=f"Precio de compra ($/{u}):")
            self.lbl_stock.configure(text=f"Stock inicial ({u}):" if not self.product else f"Stock actual ({u}):")
            self.lbl_min_stock.configure(text=f"Stock mín. alerta ({u}):")

        self.lbl_stock_unit.configure(text=unit_display)
        self.lbl_min_unit.configure(text=unit_display)

    def _update_calculation_helpers(self, *args) -> None:
        is_peso = (self.current_sale_type == "PESO")
        u = self.unit_combo.get().strip() or ("kg" if is_peso else "Unidad")

        p_str = self.price_entry.get().replace("$", "").replace(".", "").replace(",", "").strip()
        c_str = self.cost_entry.get().replace("$", "").replace(".", "").replace(",", "").strip()

        try:
            price_val = float(p_str) if p_str else 0.0
            cost_val = float(c_str) if c_str else 0.0

            if price_val > 0:
                margin_val = price_val - cost_val
                margin_pct = (margin_val / price_val) * 100.0
                sign = "+" if margin_val >= 0 else ""

                profit_color = "#34D399" if margin_val >= 0 else "#F87171"
                self.lbl_profit_val.configure(
                    text=f"{sign}${margin_val:,.0f} / {u.lower()}".replace(",", "."),
                    text_color=profit_color
                )

                # Render donut chart
                self._draw_margin_chart(margin_pct)

                # Theme color matching the donut chart fill (#C8BFE7)
                theme_color = "#C8BFE7" if margin_val >= 0 else "#F87171"
                self.lbl_margin_val.configure(text=f"Margen: {margin_pct:.1f}%", text_color=theme_color)

                if is_peso:
                    if u.lower() == "lb":
                        equiv_g = price_val / 500.0
                        equiv_lb = price_val
                        equiv_kg = price_val * 2.0
                    elif u.lower() == "g":
                        equiv_g = price_val
                        equiv_lb = price_val * 500.0
                        equiv_kg = price_val * 1000.0
                    else:  # 'kg'
                        equiv_g = price_val / 1000.0
                        equiv_lb = price_val / 2.0
                        equiv_kg = price_val
                    self.lbl_equiv_title.configure(text="Equivalencias:", text_color=theme_color)
                    self.lbl_equiv_line1.configure(text=f"1 Lb = ${equiv_lb:,.0f}".replace(",", "."), text_color=theme_color)
                    self.lbl_equiv_line2.configure(text=f"100g = ${equiv_g * 100:,.0f}".replace(",", "."), text_color=theme_color)
                    self.lbl_equiv_line3.configure(text=f"1 Kg = ${equiv_kg:,.0f}".replace(",", "."), text_color=theme_color)
                else:
                    cost_pct = (cost_val / price_val * 100.0) if price_val > 0 else 0.0
                    self.lbl_equiv_title.configure(text="Rentabilidad:", text_color=theme_color)
                    self.lbl_equiv_line1.configure(text=f"Margen: {margin_pct:.1f}%", text_color=theme_color)
                    self.lbl_equiv_line2.configure(text=f"Costo: {cost_pct:.1f}%", text_color=theme_color)
                    self.lbl_equiv_line3.configure(text=f"1 Und = ${price_val:,.0f}".replace(",", "."), text_color=theme_color)
            else:
                self.lbl_profit_val.configure(text=f"+$ 0 / {u.lower()}", text_color="#64748B")
                self._draw_margin_chart(0.0)
                self.lbl_margin_val.configure(text="Margen: 0.0%", text_color="#64748B")
                self.lbl_equiv_title.configure(text="Equivalencias:", text_color="#64748B")
                self.lbl_equiv_line1.configure(text="1 Lb = $ 0", text_color="#64748B")
                self.lbl_equiv_line2.configure(text="100g = $ 0", text_color="#64748B")
                self.lbl_equiv_line3.configure(text="1 Kg = $ 0", text_color="#64748B")
        except Exception:
            self.lbl_profit_val.configure(text=f"+$ 0 / {u.lower()}", text_color="#64748B")
            self._draw_margin_chart(0.0)
            self.lbl_margin_val.configure(text="Margen: 0.0%", text_color="#64748B")
            self.lbl_equiv_title.configure(text="Valores inválidos", text_color="#F87171")
            self.lbl_equiv_line1.configure(text="Revise precio", text_color="#F87171")
            self.lbl_equiv_line2.configure(text="y costo ingresados", text_color="#F87171")
            self.lbl_equiv_line3.configure(text="", text_color="#F87171")

    def _step_stock(self, delta: int) -> None:
        """Increment or decrement stock value by unit-appropriate step."""
        try:
            curr_str = self.stock_entry.get().replace(",", ".").strip() or "0"
            val = float(curr_str)
        except ValueError:
            val = 0.0
        unit = self.unit_combo.get().strip().lower()
        step = 100.0 if (self.current_sale_type == "PESO" and unit == "g") else 1.0
        new_val = max(0.0, round(val + delta * step, 2))
        self.stock_entry.delete(0, "end")
        self.stock_entry.insert(0, str(int(new_val)) if new_val.is_integer() else f"{new_val:.2f}")
        self._update_live_status()

    def _step_min_stock(self, delta: int) -> None:
        """Increment or decrement min stock alert value by unit-appropriate step."""
        try:
            curr_str = self.min_stock_entry.get().replace(",", ".").strip() or "0"
            val = float(curr_str)
        except ValueError:
            val = 0.0
        unit = self.unit_combo.get().strip().lower()
        step = 100.0 if (self.current_sale_type == "PESO" and unit == "g") else 1.0
        new_val = max(0.0, round(val + delta * step, 2))
        self.min_stock_entry.delete(0, "end")
        self.min_stock_entry.insert(0, str(int(new_val)) if new_val.is_integer() else f"{new_val:.2f}")
        self._update_live_status()

    def _update_live_status(self) -> None:
        try:
            s_val = float(self.stock_entry.get().replace(",", ".").strip() or "0")
            ms_val = float(self.min_stock_entry.get().replace(",", ".").strip() or "0")

            if s_val <= 0:
                self.live_status_chip.configure(fg_color="#2D1115", border_color="#DC2626")
                self.live_status_lbl.configure(text="✖ Agotado", text_color="#F87171")
            elif s_val <= ms_val:
                self.live_status_chip.configure(fg_color="#2E1C0C", border_color="#D97706")
                self.live_status_lbl.configure(text="⚠ Bajo Stock", text_color="#FBBF24")
            else:
                self.live_status_chip.configure(fg_color="#06281E", border_color="#059669")
                self.live_status_lbl.configure(text="✔ Normal", text_color="#34D399")
        except Exception:
            pass

    def _save(self) -> None:
        name = self.name_entry.get().strip()
        barcode = self.barcode_entry.get().strip() or None
        cat_choice = self.cat_combo.get().strip()
        sale_type = self.current_sale_type

        # ── 1. ID Validation ─────────────────────────────────────────────────
        custom_id = None
        if not self.product:
            raw_id = self.id_entry.get().strip()
            if not raw_id:
                messagebox.showerror("Campo Requerido", "Debe ingresar un ID para el producto.", parent=self)
                self.id_entry.focus_set()
                return
            if not raw_id.isdigit() or int(raw_id) <= 0:
                messagebox.showerror("ID Inválido", "El ID del producto debe ser un número entero positivo mayor a cero.", parent=self)
                self.id_entry.focus_set()
                return
            custom_id = int(raw_id)

        # ── 2. Mandatory Validations ─────────────────────────────────────────
        if not name:
            messagebox.showerror("Campo Requerido", "El nombre del producto no puede estar vacío.", parent=self)
            self.name_entry.focus_set()
            return

        # ── 3. Category Validation & Creation ────────────────────────────────
        with get_db_connection() as conn:
            # ── 3.1. ID Validation against Max Registered ID ─────────────────
            if not self.product and custom_id is not None:
                max_id = ProductModel.get_max_id(conn)
                if max_id > 0 and custom_id <= max_id:
                    messagebox.showerror(
                        "ID No Permitido",
                        f"El ID #{custom_id} no puede ser menor ni igual al último ID registrado en la base de datos (#{max_id}).\n\n"
                        f"Por favor ingrese un ID a partir de #{max_id + 1}.",
                        parent=self
                    )
                    self.id_entry.focus_set()
                    return

                if ProductModel.check_id_exists(conn, custom_id):
                    messagebox.showerror(
                        "ID Duplicado",
                        f"El ID #{custom_id} ya se encuentra asignado a otro producto en la base de datos.\nPor favor ingrese un número de ID único.",
                        parent=self
                    )
                    self.id_entry.focus_set()
                    return

            if cat_choice in ("-- Seleccionar categoría --", ""):
                messagebox.showerror("Categoría Requerida", "Por favor seleccione una categoría para el producto.", parent=self)
                self.cat_combo.focus_set()
                return

            if cat_choice == "Otra...":
                new_cat_name = self.new_cat_entry.get().strip()
                if not new_cat_name:
                    messagebox.showerror("Categoría Requerida", "Ingrese el nombre de la nueva categoría.", parent=self)
                    self.new_cat_entry.focus_set()
                    return
                clean_cat = new_cat_name[0].upper() + new_cat_name[1:] if len(new_cat_name) > 1 else new_cat_name.upper()
                cat_id = ProductModel.create_category(conn, clean_cat)
            else:
                cat_id = self.cat_dict.get(cat_choice)
                if not cat_id:
                    messagebox.showerror("Categoría Inválida", "Seleccione una categoría válida del listado.", parent=self)
                    self.cat_combo.focus_set()
                    return

            # ── 5. Numeric Validations ───────────────────────────────────────
            try:
                raw_price = float(self.price_entry.get().replace("$", "").replace(".", "").replace(",", ".").strip())
            except ValueError:
                messagebox.showerror("Precio Inválido", "El precio de venta debe ser un número válido mayor a cero.", parent=self)
                self.price_entry.focus_set()
                return

            if raw_price <= 0:
                messagebox.showerror("Precio Inválido", "El precio de venta debe ser estrictamente mayor a 0.", parent=self)
                self.price_entry.focus_set()
                return

            try:
                c_text = self.cost_entry.get().replace("$", "").replace(".", "").replace(",", ".").strip()
                raw_cost = float(c_text) if c_text else 0.0
            except ValueError:
                messagebox.showerror("Costo Inválido", "El costo de compra debe ser un número válido.", parent=self)
                self.cost_entry.focus_set()
                return

            if raw_cost < 0:
                messagebox.showerror("Costo Inválido", "El costo de compra no puede ser un valor negativo.", parent=self)
                self.cost_entry.focus_set()
                return

            try:
                iva_val = float(self.iva_entry.get().replace(",", ".").strip() or "0")
            except ValueError:
                messagebox.showerror("IVA Inválido", "El porcentaje de IVA debe ser un número válido.", parent=self)
                self.iva_entry.focus_set()
                return

            if not (0 <= iva_val <= 100):
                messagebox.showerror("IVA Inválido", "El porcentaje de IVA debe estar comprendido entre 0% y 100%.", parent=self)
                self.iva_entry.focus_set()
                return

            try:
                raw_stock = float(self.stock_entry.get().replace(",", ".").strip() or "0")
            except ValueError:
                messagebox.showerror("Stock Inválido", "El stock debe ser un valor numérico.", parent=self)
                self.stock_entry.focus_set()
                return

            if raw_stock < 0:
                messagebox.showerror("Stock Inválido", "El stock disponible no puede ser negativo.", parent=self)
                self.stock_entry.focus_set()
                return

            try:
                raw_min_stock = float(self.min_stock_entry.get().replace(",", ".").strip() or "0")
            except ValueError:
                messagebox.showerror("Stock Mínimo Inválido", "El stock mínimo debe ser un valor numérico.", parent=self)
                self.min_stock_entry.focus_set()
                return

            if raw_min_stock < 0:
                messagebox.showerror("Stock Mínimo Inválido", "El stock mínimo de alerta no puede ser negativo.", parent=self)
                self.min_stock_entry.focus_set()
                return

            # ── 6. Unit Measure Resolution ───────────────────────────────────
            selected_unit_display = self.unit_combo.get().strip()
            if sale_type == "PESO":
                unit_measure = selected_unit_display.lower()
                if unit_measure not in self.UNIT_OPTIONS_PESO:
                    unit_measure = "kg"
            else:
                unit_measure = self.UNIT_MAP_UNIDAD_TO_DB.get(selected_unit_display, "und")

            # ── 7. Conversions to Base Database Units ─────────────────────────
            if sale_type == "PESO":
                if unit_measure == "kg":
                    price_base = raw_price / 1000.0
                    cost_base = raw_cost / 1000.0
                    stock_base = raw_stock * 1000.0
                    min_stock_base = raw_min_stock * 1000.0
                elif unit_measure == "lb":
                    price_base = raw_price / 500.0
                    cost_base = raw_cost / 500.0
                    stock_base = raw_stock * 500.0
                    min_stock_base = raw_min_stock * 500.0
                else:  # 'g'
                    price_base = raw_price
                    cost_base = raw_cost
                    stock_base = raw_stock
                    min_stock_base = raw_min_stock
            else:
                price_base = raw_price
                cost_base = raw_cost
                stock_base = raw_stock
                min_stock_base = raw_min_stock

            # ── 8. Barcode Validation & Uniqueness Check ─────────────────────
            if not barcode and not self.product:
                barcode = ProductModel.get_next_available_barcode(conn)

            if barcode:
                clean_bc = barcode.strip()
                import re
                if not re.match(r'^[A-Za-z0-9\-_]+$', clean_bc):
                    messagebox.showerror(
                        "Código Inválido",
                        "El código de barras contiene caracteres no permitidos.\nUtilice números o guiones.",
                        parent=self
                    )
                    self.barcode_entry.focus_set()
                    return

                exclude = self.product.id if self.product else None
                if ProductModel.check_barcode_exists(conn, clean_bc, exclude_id=exclude):
                    messagebox.showerror(
                        "Código Duplicado",
                        f"Ya existe otro producto registrado con el código de barras '{clean_bc}'.\nPor favor asigne un código único.",
                        parent=self
                    )
                    self.barcode_entry.focus_set()
                    return
                barcode = clean_bc

            # ── 9. Execute DB Transaction ────────────────────────────────────
            try:
                if self.product:
                    ProductModel.update(
                        conn=conn,
                        product_id=self.product.id,
                        barcode=barcode,
                        name=name,
                        category_id=cat_id,
                        sale_type=sale_type,
                        price_base=price_base,
                        cost=cost_base,
                        iva=iva_val,
                        unit_measure=unit_measure,
                        stock=stock_base,
                        min_stock=min_stock_base
                    )
                else:
                    ProductModel.create(
                        conn=conn,
                        barcode=barcode,
                        name=name,
                        category_id=cat_id,
                        sale_type=sale_type,
                        price_base=price_base,
                        cost=cost_base,
                        iva=iva_val,
                        unit_measure=unit_measure,
                        stock=stock_base,
                        min_stock=min_stock_base,
                        custom_id=custom_id
                    )
            except Exception as e:
                messagebox.showerror("Error al Guardar", f"No se pudo guardar el producto en la base de datos:\n{e}", parent=self)
                return

        callback = self.on_save_callback
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if callback:
            callback()


# ─────────────────────────────────────────────────────────────────────────────
# 3. ADD STOCK MODAL (AGREGAR STOCK / RECEPCIÓN Y ENTRADA DE MERCANCÍA)
# ─────────────────────────────────────────────────────────────────────────────
class AddStockModal(ctk.CTkToplevel):
    """Modern modal dialog for receiving and adding stock to existing inventory.
    Provides:
    - Fast product search by barcode, ID, or name, plus combo dropdown selector.
    - Product identification display (ID, Código de barras, Nombre, Stock actual, Tipo).
    - Intelligent quantity entry with unit adaptation (kg/lb/g for PESO, units for UNIDAD).
    - Dynamic staging list allowing multiple products to be queued.
    - Live projected stock calculation per product.
    - Atomic batch processing in SQLite with immediate UI refresh.
    """

    def __init__(self, parent, on_save_callback: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self.on_save_callback = on_save_callback

        self.title("Agregar Stock al Inventario")
        self.resizable(False, False)
        self.configure(fg_color="#15171F")

        # Staged batch items: List of dicts
        self.batch_items: List[Dict[str, Any]] = []
        self.current_page: int = 1
        self.items_per_page: int = 5

        # Load all products sorted naturally by ID
        with get_db_connection() as conn:
            self.all_products: List[Product] = sorted(ProductModel.get_all(conn), key=lambda p: (p.id, p.name))

        self.products_by_id: Dict[int, Product] = {p.id: p for p in self.all_products}
        self.selected_product: Optional[Product] = None

        self._build_ui()
        _set_dialog_icon_and_center(self, parent, 880, 700)

        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        # Start with empty selection so user selects product
        self._reset_product_fields()
        self._setup_tab_navigation()
        self.after(50, lambda: (self.search_entry.focus_set(), self.search_entry.select_range(0, "end")))

    def _build_ui(self) -> None:
        # ── Standard Executive Topbar with XL Burguer Logos ───────────
        title_icon = get_ctk_icon("cube_white", size=(16, 16)) or get_ctk_icon("file_circle_plus_white", size=(16, 16))
        build_standard_modal_header(
            self,
            "Agregar Stock al Inventario",
            title_icon,
            on_close_cmd=self.destroy,
            show_close_btn=False,
            text_color="#FFFFFF"
        )

        # ── Card 1: Selection & Entry Form ────────────────────────────────────
        input_card = ctk.CTkFrame(
            self,
            fg_color="#181A22",
            border_color="#252836",
            border_width=1,
            corner_radius=8
        )
        input_card.pack(fill="x", padx=16, pady=(10, 6))

        # Row 0: Header of Card 1
        card1_header = ctk.CTkFrame(input_card, fg_color="transparent")
        card1_header.pack(fill="x", padx=14, pady=(8, 6))

        tag_icon = get_ctk_icon("tag_white", size=(14, 14)) or get_ctk_icon("tags_white", size=(14, 14))
        ctk.CTkLabel(
            card1_header,
            image=tag_icon,
            compound="left",
            text="  Seleccionar Producto y Cantidad a Ingresar",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#FFFFFF"
        ).pack(side="left")

        # Row 1: Search & Combobox
        sel_row = ctk.CTkFrame(input_card, fg_color="transparent")
        sel_row.pack(fill="x", padx=14, pady=(0, 6))

        ctk.CTkLabel(
            sel_row,
            text="Buscar:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#94A3B8"
        ).pack(side="left", padx=(0, 6))

        self.search_entry = ctk.CTkEntry(
            sel_row,
            width=120,
            height=32,
            placeholder_text="--",
            placeholder_text_color="#64748B",
            fg_color="#14161E",
            border_color="#252836",
            border_width=1,
            text_color="#F8FAFC",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=6
        )
        self.search_entry.pack(side="left", padx=(0, 4))
        self.search_entry.bind("<Return>", lambda e: self._on_quick_search())

        # Keypad button for quick search / scan entry
        kb_search_btn = ctk.CTkButton(
            sel_row,
            text="",
            image=get_ctk_icon("keyboard_slate", size=(15, 15)),
            width=34,
            height=32,
            fg_color="#111624",
            border_color="#283347",
            border_width=1,
            hover_color="#182033",
            corner_radius=6,
            cursor="hand2",
            command=self._open_search_keypad
        )
        kb_search_btn.pack(side="left", padx=(0, 4))

        self.search_btn = ctk.CTkButton(
            sel_row,
            text="",
            image=get_ctk_icon("search_magenta", size=(15, 15)),
            width=34,
            height=32,
            fg_color="#191126",
            border_color="#C026D3",
            border_width=1,
            hover_color="#2A163B",
            corner_radius=6,
            cursor="hand2",
            command=self._on_quick_search
        )
        self.search_btn.pack(side="left", padx=(0, 14))

        ctk.CTkLabel(
            sel_row,
            text="O seleccionar de la lista:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#94A3B8"
        ).pack(side="left", padx=(0, 6))

        combo_values = ["-- Seleccionar producto de la lista --"] + ([f"{p.id} - {p.name}" for p in self.all_products] if self.all_products else [])
        self.product_combo = ctk.CTkComboBox(
            sel_row,
            height=32,
            values=combo_values,
            command=self._on_combo_select,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="#14161E",
            border_color="#252836",
            border_width=1,
            text_color="#F8FAFC",
            dropdown_fg_color="#181A22",
            dropdown_text_color="#F8FAFC",
            dropdown_hover_color="#252836",
            corner_radius=6
        )
        self.product_combo.pack(side="left", fill="x", expand=True)
        self.product_combo.set(combo_values[0])

        # Row 2: Fields (ID, Barcode, Name)
        fields_row = ctk.CTkFrame(input_card, fg_color="transparent")
        fields_row.pack(fill="x", padx=14, pady=(0, 6))
        fields_row.columnconfigure(0, weight=1)
        fields_row.columnconfigure(1, weight=2)
        fields_row.columnconfigure(2, weight=4)

        # ID
        f_id = ctk.CTkFrame(fields_row, fg_color="transparent")
        f_id.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ctk.CTkLabel(f_id, text="ID producto:", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8").pack(anchor="w", pady=(0, 2))
        self.disp_id = ctk.CTkEntry(f_id, height=32, fg_color="#14161E", border_color="#252836", border_width=1, text_color="#CBD5E1", corner_radius=6, font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"))
        self.disp_id.insert(0, "--")
        self.disp_id.pack(fill="x")
        self.disp_id.configure(state="disabled")

        # Barcode
        f_bar = ctk.CTkFrame(fields_row, fg_color="transparent")
        f_bar.grid(row=0, column=1, sticky="nsew", padx=(6, 6))
        ctk.CTkLabel(f_bar, text="Código de barras:", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8").pack(anchor="w", pady=(0, 2))
        self.disp_barcode = ctk.CTkEntry(f_bar, height=32, fg_color="#14161E", border_color="#252836", border_width=1, text_color="#CBD5E1", corner_radius=6, font=ctk.CTkFont(family="Segoe UI", size=11))
        self.disp_barcode.insert(0, "--")
        self.disp_barcode.pack(fill="x")
        self.disp_barcode.configure(state="disabled")

        # Name
        f_name = ctk.CTkFrame(fields_row, fg_color="transparent")
        f_name.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        ctk.CTkLabel(f_name, text="Nombre del producto:", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8").pack(anchor="w", pady=(0, 2))
        self.disp_name = ctk.CTkEntry(f_name, height=32, fg_color="#14161E", border_color="#252836", border_width=1, text_color="#F8FAFC", corner_radius=6, font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"))
        self.disp_name.insert(0, "--")
        self.disp_name.pack(fill="x")
        self.disp_name.configure(state="disabled")

        # Row 3: Current Stock, Type, Quantity Input, Unit & Add Button
        qty_row = ctk.CTkFrame(input_card, fg_color="transparent")
        qty_row.pack(fill="x", padx=14, pady=(0, 8))

        # Stock Actual badge - visual, high-contrast, modern
        self.badge_stock_actual = ctk.CTkFrame(qty_row, fg_color="#0F172A", border_color="#2563EB", border_width=1.5, corner_radius=6, height=34)
        self.badge_stock_actual.pack(side="left", padx=(0, 6))
        self.lbl_stock_actual = ctk.CTkLabel(
            self.badge_stock_actual,
            text="Stock actual: --",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#60A5FA",
            padx=10
        )
        self.lbl_stock_actual.pack(expand=True)

        # Sale type badge
        self.badge_sale_type = ctk.CTkFrame(qty_row, fg_color="#14161E", border_color="#252836", border_width=1, corner_radius=6, height=34)
        self.badge_sale_type.pack(side="left", padx=(0, 14))
        self.lbl_sale_type = ctk.CTkLabel(
            self.badge_sale_type,
            text="Tipo: --",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8",
            padx=10
        )
        self.lbl_sale_type.pack(expand=True)

        # Quantity Input
        ctk.CTkLabel(
            qty_row,
            text="Cantidad que ingresa:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#F59E0B"
        ).pack(side="left", padx=(0, 6))

        self.qty_entry = ctk.CTkEntry(
            qty_row,
            width=95,
            height=34,
            placeholder_text="--",
            placeholder_text_color="#64748B",
            fg_color="#14161E",
            border_color="#F59E0B",
            border_width=1.5,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            justify="center",
            corner_radius=6
        )
        self.qty_entry.pack(side="left", padx=(0, 4))
        self.qty_entry.bind("<KeyRelease>", lambda e: self._on_qty_change())
        self.qty_entry.bind("<Return>", lambda e: self._add_current_to_batch())

        # Touch keypad button for quantity
        kb_btn = ctk.CTkButton(
            qty_row,
            text="",
            image=get_ctk_icon("keyboard_slate", size=(15, 15)),
            width=34,
            height=34,
            fg_color="#111624",
            border_color="#283347",
            border_width=1,
            hover_color="#182033",
            corner_radius=6,
            cursor="hand2",
            command=self._open_touch_keypad
        )
        kb_btn.pack(side="left", padx=(0, 6))

        # Unit Combobox
        self.unit_combo = ctk.CTkComboBox(
            qty_row,
            width=70,
            height=34,
            values=["kg", "lb", "g"],
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="#14161E",
            border_color="#252836",
            border_width=1,
            text_color="#F8FAFC",
            dropdown_fg_color="#181A22",
            dropdown_text_color="#F8FAFC",
            dropdown_hover_color="#252836",
            corner_radius=6,
            command=lambda v: self._on_qty_change()
        )
        self.unit_combo.set("kg")
        self.unit_combo.pack(side="left", padx=(0, 10))

        # Total Resulting Stock pill (replaces Proyección with Total)
        self.pill_projected = ctk.CTkFrame(qty_row, fg_color="#06281E", border_color="#047857", border_width=1, corner_radius=6, height=34)
        self.pill_projected.pack(side="left", padx=(0, 10))
        self.lbl_projected = ctk.CTkLabel(
            self.pill_projected,
            text="Total: --",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#34D399",
            padx=10
        )
        self.lbl_projected.pack(expand=True)

        # Button "+ Agregar a la lista"
        self.add_btn = ctk.CTkButton(
            qty_row,
            text="+ Agregar a la lista",
            image=get_ctk_icon("cart_plus_green", size=(15, 15)) or get_ctk_icon("file_circle_plus_white", size=(15, 15)),
            compound="left",
            width=165,
            height=34,
            fg_color="#0A2E20",
            hover_color="#0F4732",
            border_color="#10B981",
            border_width=1.5,
            text_color="#34D399",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self._add_current_to_batch
        )
        self.add_btn.pack(side="right")
        self.add_btn.bind("<Return>", lambda e: self._add_current_to_batch())

        # ── Card 2: Staging Batch List ────────────────────────────────────────
        batch_card = ctk.CTkFrame(
            self,
            fg_color="#181A22",
            border_color="#252836",
            border_width=1,
            corner_radius=8
        )
        batch_card.pack(fill="both", expand=True, padx=16, pady=(0, 6))

        # Header of Card 2 (Clean title without '2.' or '(Lote)', with 'Vaciar lista' on the right)
        card2_header = ctk.CTkFrame(batch_card, fg_color="transparent")
        card2_header.pack(fill="x", padx=14, pady=(8, 4))

        cube_icon = get_tinted_ctk_icon("cube_white", DarkTheme.PALETTE_TITULOS_TEXT, size=(14, 14)) or get_ctk_icon("cube_white", size=(14, 14))
        ctk.CTkLabel(
            card2_header,
            image=cube_icon,
            compound="left",
            text="  Lista de Productos a Ingresar",
            font=ctk.CTkFont(family="Cambria", size=12, weight="bold", slant="italic"),
            text_color=DarkTheme.PALETTE_TITULOS_TEXT
        ).pack(side="left")

        # Right side of card 2 header: Vaciar lista button and summary label
        header_actions = ctk.CTkFrame(card2_header, fg_color="transparent")
        header_actions.pack(side="right")

        self.clear_btn = ctk.CTkButton(
            header_actions,
            text="  Vaciar lista",
            image=get_ctk_icon("trash_red", size=(13, 13)) or get_ctk_icon("delete_left_red", size=(13, 13)),
            compound="left",
            width=105,
            height=28,
            fg_color="#231015",
            hover_color="#38131B",
            border_color="#EF4444",
            border_width=1,
            text_color="#F87171",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=5,
            cursor="hand2",
            command=self._clear_batch
        )
        self.clear_btn.pack(side="right")

        self.lbl_batch_summary = ctk.CTkLabel(
            header_actions,
            text="0 productos",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FBBF24"
        )
        self.lbl_batch_summary.pack(side="right", padx=(0, 10))

        # Table Column Header (9 columns: #, ID, Código, Nombre, Categoría, Stock Actual, Ingreso (+), Total Resultante, Quitar)
        tbl_header = ctk.CTkFrame(batch_card, height=30, fg_color="#111319", corner_radius=4)
        tbl_header.pack(fill="x", padx=14, pady=(0, 2))
        tbl_header.pack_propagate(False)

        self.cols_def = [
            ("#", 32, "center", 0),
            ("ID", 38, "center", 0),
            ("Código", 115, "center", 0),
            ("Nombre del Producto", 0, "w", 3),
            ("Categoría", 0, "w", 2),
            ("Stock Actual", 85, "center", 0),
            ("Ingreso (+)", 90, "center", 0),
            ("Total Resultante", 95, "center", 0),
            ("Quitar", 45, "center", 0),
        ]

        for idx, (col_name, col_w, col_anchor, col_weight) in enumerate(self.cols_def):
            if col_weight > 0:
                tbl_header.columnconfigure(idx, weight=col_weight)
            else:
                tbl_header.columnconfigure(idx, minsize=col_w)
            c_frame = ctk.CTkFrame(tbl_header, fg_color="transparent")
            c_frame.grid(row=0, column=idx, sticky="nsew", padx=2)
            lbl = ctk.CTkLabel(
                c_frame,
                text=col_name,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color="#94A3B8"
            )
            lbl.pack(anchor=col_anchor, expand=(col_anchor == "center"), fill="x" if col_anchor == "w" else "none")

        # Table rows container (paginated, exactly 5 rows)
        self.table_rows_container = ctk.CTkFrame(
            batch_card,
            fg_color="transparent",
            corner_radius=0
        )
        self.table_rows_container.pack(fill="both", expand=True, padx=14, pady=(2, 2))
        self.batch_scroll = self.table_rows_container

        # Bottom Pagination Bar inside Card 2
        self.pagination_frame = ctk.CTkFrame(batch_card, fg_color="transparent", height=34)
        self.pagination_frame.pack(side="bottom", fill="x", padx=14, pady=(2, 6))

        self.page_prev_btn = ctk.CTkButton(
            self.pagination_frame,
            text="◀ Anterior",
            width=88,
            height=28,
            fg_color="#1E293B",
            hover_color="#334155",
            border_color="#475569",
            border_width=1,
            text_color="#CBD5E1",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            command=self._prev_page
        )
        self.page_prev_btn.pack(side="left")

        self.page_info_lbl = ctk.CTkLabel(
            self.pagination_frame,
            text="Página 1 de 1",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8"
        )
        self.page_info_lbl.pack(side="left", padx=14)

        self.page_next_btn = ctk.CTkButton(
            self.pagination_frame,
            text="Siguiente ▶",
            width=88,
            height=28,
            fg_color="#1E293B",
            hover_color="#334155",
            border_color="#475569",
            border_width=1,
            text_color="#CBD5E1",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            command=self._next_page
        )
        self.page_next_btn.pack(side="left")

        # ── Footer Bar: Cancel & Save/Process ──────────────────────────────────
        footer = ctk.CTkFrame(self, fg_color="transparent", height=48)
        footer.pack(fill="x", side="bottom", padx=16, pady=(4, 12))
        footer.pack_propagate(False)

        self.cancel_btn = ctk.CTkButton(
            footer,
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
        self.cancel_btn.pack(side="left")

        self.save_btn = ctk.CTkButton(
            footer,
            text="  Guardar y Procesar Stock",
            image=get_ctk_icon("floppy_green", size=(15, 15)) or get_ctk_icon("floppy_white", size=(15, 15)),
            compound="left",
            width=230,
            height=38,
            fg_color="#0A1D16",
            hover_color="#0F2E22",
            border_color="#10B981",
            border_width=1.5,
            text_color="#34D399",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self._save_and_process
        )
        self.save_btn.pack(side="right")

        self._render_batch_rows()

    # ── Tab Navigation Setup ──────────────────────────────────────────────────
    def _setup_tab_navigation(self) -> None:
        """Bind Tab and Shift-Tab traversal to navigate cleanly across AddStockModal widgets."""
        def _get_nav_widgets():
            widgets = [self.search_entry, self.search_btn, self.product_combo, self.qty_entry]
            try:
                if str(self.unit_combo.cget("state")) != "disabled":
                    widgets.append(self.unit_combo)
            except Exception:
                widgets.append(self.unit_combo)
            widgets.extend([self.add_btn, self.clear_btn, self.save_btn, self.cancel_btn])
            return widgets

        bind_tab_navigation(self, _get_nav_widgets, focus_color="#38BDF8")

    # ── Pagination Controls ───────────────────────────────────────────────────
    def _prev_page(self) -> None:
        if self.current_page > 1:
            self.current_page -= 1
            self._render_batch_rows()

    def _next_page(self) -> None:
        count = len(self.batch_items)
        total_pages = max(1, math.ceil(count / self.items_per_page))
        if self.current_page < total_pages:
            self.current_page += 1
            self._render_batch_rows()

    # ── Product Search & Selection ────────────────────────────────────────────
    def _open_search_keypad(self) -> None:
        curr = self.search_entry.get().strip()
        TouchKeypadModal(
            parent=self,
            title="Teclado Numérico - Buscar Producto",
            initial_value=curr,
            on_confirm_callback=self._on_touch_search_confirmed
        )

    def _on_touch_search_confirmed(self, val: str) -> None:
        self.search_entry.delete(0, "end")
        self.search_entry.insert(0, val)
        self._on_quick_search()

    def _reset_product_fields(self) -> None:
        self.selected_product = None
        if hasattr(self, "disp_id"):
            self.disp_id.configure(state="normal")
            self.disp_id.delete(0, "end")
            self.disp_id.insert(0, "--")
            self.disp_id.configure(state="disabled")

        if hasattr(self, "disp_barcode"):
            self.disp_barcode.configure(state="normal")
            self.disp_barcode.delete(0, "end")
            self.disp_barcode.insert(0, "--")
            self.disp_barcode.configure(state="disabled")

        if hasattr(self, "disp_name"):
            self.disp_name.configure(state="normal")
            self.disp_name.delete(0, "end")
            self.disp_name.insert(0, "--")
            self.disp_name.configure(state="disabled")

        if hasattr(self, "search_entry"):
            self.search_entry.delete(0, "end")

        if hasattr(self, "product_combo"):
            vals = self.product_combo.cget("values")
            if vals:
                self.product_combo.set(vals[0])

        if hasattr(self, "lbl_stock_actual"):
            self.lbl_stock_actual.configure(text="Stock actual: --")

        if hasattr(self, "lbl_sale_type"):
            self.lbl_sale_type.configure(text="Tipo: --")

        if hasattr(self, "unit_combo"):
            self.unit_combo.configure(values=["--"], state="disabled")
            self.unit_combo.set("--")

        if hasattr(self, "lbl_projected"):
            self.lbl_projected.configure(text="Total: --")

        if hasattr(self, "qty_entry"):
            self.qty_entry.delete(0, "end")

    def _select_product(self, p: Product) -> None:
        self.selected_product = p
        self.disp_id.configure(state="normal")
        self.disp_id.delete(0, "end")
        self.disp_id.insert(0, str(p.id))
        self.disp_id.configure(state="disabled")

        self.disp_barcode.configure(state="normal")
        self.disp_barcode.delete(0, "end")
        self.disp_barcode.insert(0, p.barcode if p.barcode else "Sin código")
        self.disp_barcode.configure(state="disabled")

        self.disp_name.configure(state="normal")
        self.disp_name.delete(0, "end")
        self.disp_name.insert(0, p.name)
        self.disp_name.configure(state="disabled")

        # Load clean numeric ID into search entry
        self.search_entry.delete(0, "end")
        self.search_entry.insert(0, str(p.id))

        self.lbl_stock_actual.configure(text=f"Stock actual: {p.display_stock}")
        self.lbl_sale_type.configure(text=f"Tipo: {p.display_sale_type}")

        if p.sale_type == "PESO":
            self.unit_combo.configure(values=["kg", "lb", "g"], state="normal")
            u = p.unit_measure.lower().strip()
            self.unit_combo.set(u if u in ("kg", "lb", "g") else "kg")
        else:
            um = p.unit_measure if p.unit_measure else "und"
            self.unit_combo.configure(values=[um], state="disabled")
            self.unit_combo.set(um)

        self._on_qty_change()

    def _on_combo_select(self, choice: str) -> None:
        if not choice or choice.startswith("Sin productos") or choice.startswith("--"):
            self._reset_product_fields()
            return
        try:
            pid_str = choice.split("-")[0].replace("#", "").strip()
            pid = int(pid_str)
            if pid in self.products_by_id:
                self._select_product(self.products_by_id[pid])
        except Exception:
            pass

    def _on_quick_search(self) -> None:
        q = self.search_entry.get().strip()
        if not q:
            return

        # 1. Check direct ID match
        if q.isdigit() and int(q) in self.products_by_id:
            p = self.products_by_id[int(q)]
            self._select_product(p)
            self._sync_combo_selection(p)
            self.qty_entry.focus_set()
            self.qty_entry.select_range(0, "end")
            return

        # 2. Check barcode match
        for p in self.all_products:
            if p.barcode and p.barcode.strip() == q:
                self._select_product(p)
                self._sync_combo_selection(p)
                self.qty_entry.focus_set()
                self.qty_entry.select_range(0, "end")
                return

        # 3. Check name match with normalized text
        norm_q = normalize_text(q)
        for p in self.all_products:
            if norm_q in normalize_text(p.name):
                self._select_product(p)
                self._sync_combo_selection(p)
                self.qty_entry.focus_set()
                self.qty_entry.select_range(0, "end")
                return

        messagebox.showwarning("Producto no encontrado", f"No se encontró ningún producto con '{q}'.", parent=self)

    def _sync_combo_selection(self, p: Product) -> None:
        target_prefix = f"{p.id} -"
        for val in self.product_combo.cget("values"):
            if val.startswith(target_prefix):
                self.product_combo.set(val)
                break

    def _on_qty_change(self) -> None:
        if not self.selected_product:
            self.lbl_projected.configure(text="Total: --")
            return

        raw_val = self.qty_entry.get().strip().replace(",", ".")
        try:
            qty_val = float(raw_val)
            if qty_val <= 0:
                self.lbl_projected.configure(text="Total: --")
                return
            unit = self.unit_combo.get()
            base_delta = convert_quantity_to_base(qty_val, unit, self.selected_product.sale_type)
            proj_stock = self.selected_product.stock + base_delta
            proj_str = format_stock_display(proj_stock, self.selected_product.sale_type, self.selected_product.unit_measure)
            self.lbl_projected.configure(text=f"Total: {proj_str}")
        except Exception:
            self.lbl_projected.configure(text="Total: --")

    def _open_touch_keypad(self) -> None:
        curr = self.qty_entry.get().strip()
        TouchKeypadModal(
            parent=self,
            title="Teclado Numérico - Cantidad a Ingresar",
            initial_value=curr,
            on_confirm_callback=self._on_touch_qty_confirmed
        )

    def _on_touch_qty_confirmed(self, val: str) -> None:
        self.qty_entry.delete(0, "end")
        self.qty_entry.insert(0, val)
        self._on_qty_change()

    def _add_current_to_batch(self) -> None:
        p = self.selected_product
        if not p:
            messagebox.showwarning("Seleccione Producto", "Por favor seleccione un producto para ingresar.", parent=self)
            return

        raw_val = self.qty_entry.get().strip().replace(",", ".")
        try:
            qty_val = float(raw_val)
            if qty_val <= 0:
                raise ValueError()
        except Exception:
            messagebox.showerror("Cantidad Inválida", "La cantidad que ingresa debe ser un número positivo mayor a 0.", parent=self)
            self.qty_entry.focus_set()
            return

        unit = self.unit_combo.get()
        base_delta = convert_quantity_to_base(qty_val, unit, p.sale_type)

        # Check if product is already in the batch
        existing = next((item for item in self.batch_items if item["product_id"] == p.id), None)
        if existing:
            existing["input_qty"] += qty_val
            existing["base_qty_to_add"] += base_delta
            existing["formatted_delta"] = self._format_delta(existing["base_qty_to_add"], p)
            existing["projected_stock"] = existing["current_stock"] + existing["base_qty_to_add"]
            existing["formatted_projected"] = format_stock_display(existing["projected_stock"], p.sale_type, p.unit_measure)
        else:
            item = {
                "product_id": p.id,
                "barcode": p.barcode or "",
                "name": p.name,
                "category_name": p.category_name,
                "sale_type": p.sale_type,
                "unit_measure": p.unit_measure,
                "current_stock": p.stock,
                "formatted_current": p.display_stock,
                "input_qty": qty_val,
                "input_unit": unit,
                "base_qty_to_add": base_delta,
                "formatted_delta": self._format_delta(base_delta, p),
                "projected_stock": p.stock + base_delta,
                "formatted_projected": format_stock_display(p.stock + base_delta, p.sale_type, p.unit_measure),
            }
            self.batch_items.append(item)
            # Navigate to the page containing the new item
            self.current_page = max(1, math.ceil(len(self.batch_items) / self.items_per_page))

        self._render_batch_rows()
        self._reset_product_fields()
        self.after(20, lambda: (self.search_entry.focus_set(), self.search_entry.select_range(0, "end")))

    def _format_delta(self, base_grams_or_units: float, p: Product) -> str:
        if p.sale_type == "PESO":
            u = p.unit_measure.lower().strip()
            if u == "kg":
                val = base_grams_or_units / 1000.0
                return f"{int(val) if val.is_integer() else val:.2f} kg"
            elif u == "lb":
                val = base_grams_or_units / 500.0
                return f"{int(val) if val.is_integer() else val:.2f} lb"
            else:
                return f"{base_grams_or_units:.0f} g"
        if float(base_grams_or_units).is_integer():
            return f"{int(base_grams_or_units)} {p.unit_measure}"
        return f"{base_grams_or_units:.1f} {p.unit_measure}"

    def _render_batch_rows(self) -> None:
        for widget in self.table_rows_container.winfo_children():
            widget.destroy()

        count = len(self.batch_items)
        total_pages = max(1, math.ceil(count / self.items_per_page))
        if self.current_page > total_pages:
            self.current_page = total_pages
        if self.current_page < 1:
            self.current_page = 1

        self.lbl_batch_summary.configure(
            text=f"{count} producto{'s' if count != 1 else ''}"
        )

        if count == 0:
            self.clear_btn.configure(state="disabled", text_color="#64748B", border_color="#281A22")
            self.page_info_lbl.configure(text="Página 1 de 1 (0 productos)")
            self.page_prev_btn.configure(state="disabled", fg_color="#14161E", text_color="#475569")
            self.page_next_btn.configure(state="disabled", fg_color="#14161E", text_color="#475569")

            empty_frame = ctk.CTkFrame(self.table_rows_container, fg_color="transparent")
            empty_frame.pack(fill="both", expand=True, pady=32)

            ctk.CTkLabel(
                empty_frame,
                text="📦",
                font=ctk.CTkFont(size=30)
            ).pack(pady=(0, 4))

            ctk.CTkLabel(
                empty_frame,
                text="La lista está vacía",
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color="#CBD5E1"
            ).pack()

            ctk.CTkLabel(
                empty_frame,
                text="Seleccione un producto arriba, indique la cantidad y presione '+ Agregar a la lista'.",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="#64748B"
            ).pack(pady=(2, 0))
            return

        self.clear_btn.configure(state="normal", text_color="#F87171", border_color="#EF4444")

        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, count)
        page_items = self.batch_items[start_idx:end_idx]

        for i, item in enumerate(page_items):
            actual_idx = start_idx + i
            row_bg = "#151821" if actual_idx % 2 == 0 else "#191C27"
            row_frame = ctk.CTkFrame(
                self.table_rows_container,
                height=34,
                fg_color=row_bg,
                border_color="#222634",
                border_width=1,
                corner_radius=4
            )
            row_frame.pack(fill="x", pady=1)
            row_frame.pack_propagate(False)

            for col_i, (c_name, c_w, c_anchor, c_weight) in enumerate(self.cols_def):
                if c_weight > 0:
                    row_frame.columnconfigure(col_i, weight=c_weight)
                else:
                    row_frame.columnconfigure(col_i, minsize=c_w)

            # Col 0: #
            c0 = ctk.CTkFrame(row_frame, fg_color="transparent")
            c0.grid(row=0, column=0, sticky="nsew", padx=2)
            ctk.CTkLabel(c0, text=str(actual_idx + 1), font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#64748B").pack(expand=True)

            # Col 1: ID (clean number without #)
            c1 = ctk.CTkFrame(row_frame, fg_color="transparent")
            c1.grid(row=0, column=1, sticky="nsew", padx=2)
            ctk.CTkLabel(c1, text=str(item['product_id']), font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#94A3B8").pack(expand=True)

            # Col 2: Barcode
            c2 = ctk.CTkFrame(row_frame, fg_color="transparent")
            c2.grid(row=0, column=2, sticky="nsew", padx=2)
            barcode_str = item["barcode"] if item["barcode"] else "—"
            ctk.CTkLabel(c2, text=barcode_str, font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#CBD5E1").pack(expand=True)

            # Col 3: Product Name
            c3 = ctk.CTkFrame(row_frame, fg_color="transparent")
            c3.grid(row=0, column=3, sticky="nsew", padx=4)
            ctk.CTkLabel(
                c3,
                text=item["name"],
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#F8FAFC"
            ).pack(side="left", fill="x")

            # Col 4: Category
            c4 = ctk.CTkFrame(row_frame, fg_color="transparent")
            c4.grid(row=0, column=4, sticky="nsew", padx=4)
            ctk.CTkLabel(
                c4,
                text=item["category_name"],
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="#94A3B8"
            ).pack(side="left", fill="x")

            # Col 5: Current Stock
            c5 = ctk.CTkFrame(row_frame, fg_color="transparent")
            c5.grid(row=0, column=5, sticky="nsew", padx=2)
            ctk.CTkLabel(c5, text=item["formatted_current"], font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8").pack(expand=True)

            # Col 6: Inbound (+)
            c6 = ctk.CTkFrame(row_frame, fg_color="transparent")
            c6.grid(row=0, column=6, sticky="nsew", padx=2)
            chip_ingreso = ctk.CTkFrame(c6, fg_color="#064E3B", corner_radius=4, height=22)
            chip_ingreso.pack(expand=True)
            ctk.CTkLabel(
                chip_ingreso,
                text=f"+{item['formatted_delta']}",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#34D399",
                padx=8
            ).pack()

            # Col 7: Resulting Stock
            c7 = ctk.CTkFrame(row_frame, fg_color="transparent")
            c7.grid(row=0, column=7, sticky="nsew", padx=2)
            ctk.CTkLabel(
                c7,
                text=item["formatted_projected"],
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#FBBF24"
            ).pack(expand=True)

            # Col 8: Delete button
            c8 = ctk.CTkFrame(row_frame, fg_color="transparent")
            c8.grid(row=0, column=8, sticky="nsew", padx=2)
            del_icon = get_ctk_icon("trash_red", size=(14, 14))
            del_btn = ctk.CTkButton(
                c8,
                image=del_icon,
                text="",
                width=28,
                height=26,
                fg_color="#2A1014",
                hover_color="#451219",
                border_color="#EF4444",
                border_width=1,
                corner_radius=4,
                cursor="hand2",
                command=lambda item_idx=actual_idx: self._remove_from_batch(item_idx)
            )
            del_btn.pack(expand=True)

        # Update pagination bar
        self.page_info_lbl.configure(
            text=f"Página {self.current_page} de {total_pages} (5 por pág. · {count} producto{'s' if count != 1 else ''})"
        )
        self.page_prev_btn.configure(
            state="normal" if self.current_page > 1 else "disabled",
            fg_color="#1E293B" if self.current_page > 1 else "#14161E",
            text_color="#CBD5E1" if self.current_page > 1 else "#475569"
        )
        self.page_next_btn.configure(
            state="normal" if self.current_page < total_pages else "disabled",
            fg_color="#1E293B" if self.current_page < total_pages else "#14161E",
            text_color="#CBD5E1" if self.current_page < total_pages else "#475569"
        )

    def _remove_from_batch(self, index: int) -> None:
        if 0 <= index < len(self.batch_items):
            del self.batch_items[index]
            total_pages = max(1, math.ceil(len(self.batch_items) / self.items_per_page))
            if self.current_page > total_pages:
                self.current_page = total_pages
            self._render_batch_rows()

    def _clear_batch(self) -> None:
        if not self.batch_items:
            return
        if messagebox.askyesno("Vaciar Lista", "¿Desea eliminar todos los productos de la lista actual?", parent=self):
            self.batch_items.clear()
            self.current_page = 1
            self._render_batch_rows()

    def _save_and_process(self) -> None:
        if not self.batch_items:
            messagebox.showwarning(
                "Lote Vacío",
                "Debe agregar al menos un producto a la lista antes de procesar el stock.",
                parent=self
            )
            return

        count = len(self.batch_items)
        if not messagebox.askyesno(
            "Confirmar Ingreso de Stock",
            f"¿Está seguro de procesar el ingreso de stock para {count} producto{'s' if count != 1 else ''}?\n\n"
            "El inventario se actualizará de inmediato en la base de datos.",
            parent=self
        ):
            return

        try:
            with get_db_connection() as conn:
                items_to_save = [(item["product_id"], item["base_qty_to_add"]) for item in self.batch_items]
                ProductModel.add_stock_batch(conn, items_to_save)
        except Exception as e:
            messagebox.showerror(
                "Error al Guardar",
                f"Ocurrió un error al actualizar el stock en la base de datos:\n{e}",
                parent=self
            )
            return

        messagebox.showinfo(
            "Stock Actualizado",
            f"¡Se ha procesado exitosamente el ingreso de stock para {count} producto{'s' if count != 1 else ''}!",
            parent=self
        )

        callback = self.on_save_callback
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if callback:
            callback()


BatchStockEntryModal = AddStockModal


# ─────────────────────────────────────────────────────────────────────────────
# 4. MAIN INVENTORY FRAME (CATÁLOGO Y GESTIÓN DE PRODUCTOS)
# ─────────────────────────────────────────────────────────────────────────────
class InventoryFrame(ctk.CTkFrame):
    """Catalog and Inventory Management Presentation Frame for XL Burguer.
    Features:
    - Snug vertical layout fitting immediately under the topbar with minimal margin.
    - Full search across ID, barcode, name, and category.
    - Filters by Category, Inventory Status (Normal, Bajo, Agotado), and Commercialization Type (Peso, Unidad).
    - Sortable table headers with visual arrow indicators (▲ / ▼).
    - Auto-computed status pills, clear action buttons (Ver, Editar, Eliminar).
    - Direct access to Gram-Based Ingredients Management and Fast-Food Recipe Tuning.
    - Live KPI counter chips.
    """

    def __init__(self, parent, current_user: Optional[User] = None):
        super().__init__(parent, fg_color=DarkTheme.BG_ROOT, corner_radius=0)
        self.current_user = current_user

        self.products: List[Product] = []
        self.filtered_products: List[Product] = []

        # Sorting state: (column_key, direction: 'asc' | 'desc')
        self.sort_column: str = "name"
        self.sort_direction: str = "asc"

        # Pagination state (24 products per page)
        self.current_page: int = 1
        self.page_size: int = 24
        self.total_pages: int = 1

        # Debounce state for live product search
        self._search_debounce_job: Optional[str] = None
        self.SEARCH_DEBOUNCE_MS: int = 300

        self._setup_columns_def()
        self._build_ui()
        self.load_data()

    @property
    def is_admin(self) -> bool:
        """Return True if user is administrator, False for Cajero POS."""
        if self.current_user is None:
            return True
        return bool(self.current_user.is_admin)

    def set_current_user(self, user: Optional[User]) -> None:
        """Update current active user and dynamically reapply permissions."""
        old_admin = self.is_admin
        self.current_user = user
        if old_admin != self.is_admin:
            self.apply_role_permissions()

    def apply_role_permissions(self) -> None:
        """Update buttons, columns, and rows based on current user permissions."""
        if hasattr(self, "add_prod_btn") and hasattr(self, "export_excel_btn") and hasattr(self, "add_stock_btn"):
            if self.is_admin:
                self.add_prod_btn.pack(side="right")
                if hasattr(self, "manage_recipes_btn"):
                    self.manage_recipes_btn.pack(side="right", padx=(0, 8))
                if hasattr(self, "manage_ingredients_btn"):
                    self.manage_ingredients_btn.pack(side="right", padx=(0, 8))
                self.add_stock_btn.pack(side="right", padx=(0, 8))
                self.export_excel_btn.pack(side="right", padx=(0, 8))
            else:
                self.add_prod_btn.pack_forget()
                if hasattr(self, "manage_recipes_btn"):
                    self.manage_recipes_btn.pack_forget()
                if hasattr(self, "manage_ingredients_btn"):
                    self.manage_ingredients_btn.pack_forget()
                self.add_stock_btn.pack_forget()
                self.export_excel_btn.pack_forget()

        self._setup_columns_def()
        self._build_header_row()
        self._render_rows()

    def _setup_columns_def(self) -> None:
        """Define table columns with strict vertical alignment spanning 100% of the table width."""
        base_cols = [
            ("id", "ID", 42, "center", True, 0),
            ("barcode", "Código", 76, "center", True, 0),
            ("name", "Producto", 160, "w", True, 3),
            ("category_name", "Categoría", 150, "w", True, 2),
            ("sale_type", "Tipo", 58, "center", True, 0),
            ("unit_measure", "Unidad", 68, "center", True, 0),
            ("price_base", "Precio Venta", 110, "center", True, 1),
            ("cost", "Costo", 98, "center", True, 1),
            ("iva", "IVA", 48, "center", True, 0),
            ("min_stock", "Stock mín", 86, "center", True, 0),
            ("stock", "Stock actual", 98, "center", True, 0),
            ("status", "Estado", 66, "center", True, 0),
        ]
        if self.is_admin:
            base_cols.append(("actions", "Acciones", 118, "center", False, 0))
        self.columns_def = base_cols

    def _build_ui(self) -> None:
        # ── 1. Compact Controls & Filter Bar ─────────────────────────────────
        # Snug packing with minimal top margin (pady=(4, 6)) to sit right below the topbar
        self.controls_bar = ctk.CTkFrame(
            self,
            fg_color=DarkTheme.BG_CARD,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=8
        )
        self.controls_bar.pack(fill="x", padx=10, pady=(4, 6))

        # Top row of controls bar: Search + Filters
        row_controls = ctk.CTkFrame(self.controls_bar, fg_color="transparent")
        row_controls.pack(fill="x", padx=10, pady=(8, 6))

        # Search Entry with touch keyboard and magenta search button
        search_box = ctk.CTkFrame(row_controls, fg_color="transparent")
        search_box.pack(side="left", padx=(0, 10))

        self.search_entry = ctk.CTkEntry(
            search_box,
            width=280,
            height=38,
            placeholder_text="Buscar por nombre, código o ID",
            placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=DarkTheme.INPUT_BG,
            border_color=DarkTheme.INPUT_BORDER,
            border_width=1.5,
            text_color=DarkTheme.INPUT_TEXT,
            corner_radius=8
        )
        self.search_entry.pack(side="left", padx=(0, 6))
        self.search_entry.bind("<KeyRelease>", self._on_search_key_debounced)
        self.search_entry.bind("<Return>", lambda e: self._on_search_enter())
        self.search_entry.bind("<KP_Enter>", lambda e: self._on_search_enter())

        # Touch keyboard button [⌨]
        kb_img = get_ctk_icon("keyboard_slate", size=(18, 18))
        touch_kb_btn = ctk.CTkButton(
            search_box,
            image=kb_img,
            text="",
            width=40,
            height=38,
            fg_color="#111624",
            border_color="#283347",
            border_width=1.5,
            hover_color="#182033",
            corner_radius=8,
            cursor="hand2",
            command=self._open_touch_search_keypad
        )
        touch_kb_btn.pack(side="left", padx=(0, 6))

        # Magenta/purple search button [🔍]
        search_img = get_ctk_icon("search_magenta", size=(18, 18))
        search_btn = ctk.CTkButton(
            search_box,
            image=search_img,
            text="",
            width=40,
            height=38,
            fg_color="#191126",
            border_color="#C026D3",
            border_width=1.5,
            hover_color="#2A163B",
            corner_radius=8,
            cursor="hand2",
            command=self._on_search_enter
        )
        search_btn.pack(side="left")

        # Category Filter Dropdown
        ctk.CTkLabel(
            row_controls,
            text="Categoría:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(side="left", padx=(10, 4))
        self.category_filter = ctk.CTkComboBox(
            row_controls,
            width=165,
            height=38,
            values=["Todas las categorías"],
            command=lambda v: self._on_filter_changed(),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=DarkTheme.INPUT_BG,
            border_color="#3B4A66",
            border_width=1.5,
            button_color="#1E293B",
            button_hover_color="#334155",
            text_color=DarkTheme.INPUT_TEXT,
            dropdown_fg_color=DarkTheme.BG_ELEVATED,
            dropdown_text_color=DarkTheme.TEXT_PRIMARY,
            dropdown_hover_color=DarkTheme.BG_CARD_HOVER,
            corner_radius=8
        )
        self.category_filter.set("Todas las categorías")
        self.category_filter.pack(side="left", padx=(0, 10))

        # Status Filter Dropdown
        ctk.CTkLabel(
            row_controls,
            text="Estado:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(side="left", padx=(6, 4))
        self.status_filter = ctk.CTkComboBox(
            row_controls,
            width=145,
            height=38,
            values=["Todos los estados", "Normal", "Bajo Stock", "Agotado"],
            command=lambda v: self._on_filter_changed(),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=DarkTheme.INPUT_BG,
            border_color="#3B4A66",
            border_width=1.5,
            button_color="#1E293B",
            button_hover_color="#334155",
            text_color=DarkTheme.INPUT_TEXT,
            dropdown_fg_color=DarkTheme.BG_ELEVATED,
            dropdown_text_color=DarkTheme.TEXT_PRIMARY,
            dropdown_hover_color=DarkTheme.BG_CARD_HOVER,
            corner_radius=8
        )
        self.status_filter.set("Todos los estados")
        self.status_filter.pack(side="left", padx=(0, 10))

        # Type Filter Dropdown
        ctk.CTkLabel(
            row_controls,
            text="Tipo:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(side="left", padx=(6, 4))
        self.type_filter = ctk.CTkComboBox(
            row_controls,
            width=130,
            height=38,
            values=["Todos los tipos", "Por Peso", "Por Unidad"],
            command=lambda v: self._on_filter_changed(),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=DarkTheme.INPUT_BG,
            border_color="#3B4A66",
            border_width=1.5,
            button_color="#1E293B",
            button_hover_color="#334155",
            text_color=DarkTheme.INPUT_TEXT,
            dropdown_fg_color=DarkTheme.BG_ELEVATED,
            dropdown_text_color=DarkTheme.TEXT_PRIMARY,
            dropdown_hover_color=DarkTheme.BG_CARD_HOVER,
            corner_radius=8
        )
        self.type_filter.set("Todos los tipos")
        self.type_filter.pack(side="left", padx=(0, 8))

        # Data Reload Button [Two-arrows repeat icon + text "Recargar"] - Aligned to the far right
        repeat_icon = get_ctk_icon("repeat_blue", size=(15, 15)) or get_ctk_icon("repeat_white", size=(15, 15))
        self.reload_btn = ctk.CTkButton(
            row_controls,
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
            command=self._reload_inventory
        )
        self.reload_btn.pack(side="right", padx=0)

        # Filter Reset Button [Eraser icon + text "Limpiar"] - To the left of reload button on the right
        eraser_icon = get_ctk_icon("eraser_slate", size=(15, 15)) or get_ctk_icon("eraser_white", size=(15, 15)) or get_ctk_icon("eraser-solid-full", size=(15, 15))
        self.clear_filters_btn = ctk.CTkButton(
            row_controls,
            image=eraser_icon,
            compound="left",
            text="  Limpiar",
            width=92,
            height=36,
            fg_color="#111624",
            border_color="#475569",
            border_width=1.5,
            hover_color="#1E293B",
            text_color="#CBD5E1",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=8,
            cursor="hand2",
            command=self._reset_all_filters
        )
        self.clear_filters_btn.pack(side="right", padx=(0, 8))
        clear_filters_btn = self.clear_filters_btn

        # Subtle divider between filters and KPI summary
        ctk.CTkFrame(self.controls_bar, fg_color=DarkTheme.BORDER_SUBTLE, height=1).pack(fill="x", padx=10, pady=(2, 6))

        # Bottom row of controls bar: KPI counters & Action Buttons
        row_kpis = ctk.CTkFrame(self.controls_bar, fg_color="transparent")
        row_kpis.pack(fill="x", padx=10, pady=(0, 8))

        # Interactive KPI chips aligned to the left
        self.kpi_normal_btn = ctk.CTkButton(
            row_kpis,
            text="✔ Normal: 0",
            height=28,
            fg_color="#064E3B",
            hover_color="#065F46",
            border_color="#10B981",
            border_width=1,
            text_color="#34D399",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=lambda: self._filter_by_status_pill("Normal")
        )
        self.kpi_normal_btn.pack(side="left", padx=(0, 4))

        self.kpi_low_btn = ctk.CTkButton(
            row_kpis,
            text="⚠ Bajo: 0",
            height=28,
            fg_color="#78350F",
            hover_color="#92400E",
            border_color="#F59E0B",
            border_width=1,
            text_color="#FBBF24",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=lambda: self._filter_by_status_pill("Bajo")
        )
        self.kpi_low_btn.pack(side="left", padx=3)

        self.kpi_out_btn = ctk.CTkButton(
            row_kpis,
            text="❗ Agotado: 0",
            height=28,
            fg_color="#450A0A",
            hover_color="#5C1318",
            border_color="#F87171",
            border_width=1.5,
            text_color="#FCA5A5",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=lambda: self._filter_by_status_pill("Agotado")
        )
        self.kpi_out_btn.pack(side="left", padx=3)

        # Financial valuation display - Sophisticated executive badge with depth and border
        self.val_badge = ctk.CTkFrame(
            row_kpis,
            fg_color="#0F172A",
            border_color="#334155",
            border_width=1,
            corner_radius=14,
            height=30
        )
        self.val_badge.place(relx=0.48, rely=0.5, anchor="center")
        self.kpi_valuation_lbl = ctk.CTkLabel(
            self.val_badge,
            text="Valor: COP $ 0",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38BDF8"
        )
        self.kpi_valuation_lbl.pack(padx=16, pady=3)
        self.kpi_valuation_btn = self.kpi_valuation_lbl

        # Right buttons: "+ Agregar producto", "Recetas", "Ingredientes (g)", "Agregar stock" and "Exportar Excel"
        add_icon = get_ctk_icon("file_circle_plus_white", size=(16, 16))
        self.add_prod_btn = ctk.CTkButton(
            row_kpis,
            image=add_icon,
            compound="left",
            text=" Agregar producto",
            height=36,
            fg_color="#1D4ED8",
            hover_color="#2563EB",
            border_color="#3B82F6",
            border_width=1.5,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=18,
            cursor="hand2",
            command=self._open_new_product_modal
        )
        if self.is_admin:
            self.add_prod_btn.pack(side="right")

        recipes_icon = get_ctk_icon("chart_column_white", size=(15, 15))
        self.manage_recipes_btn = ctk.CTkButton(
            row_kpis,
            image=recipes_icon,
            compound="left",
            text=" Recetas",
            height=34,
            fg_color="#312E81",
            hover_color="#3730A3",
            border_color="#6366F1",
            border_width=1.5,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=16,
            cursor="hand2",
            command=self._open_recipes_modal
        )
        if self.is_admin:
            self.manage_recipes_btn.pack(side="right", padx=(0, 8))

        ing_icon = get_ctk_icon("cube_white", size=(15, 15))
        self.manage_ingredients_btn = ctk.CTkButton(
            row_kpis,
            image=ing_icon,
            compound="left",
            text=" Ingredientes (g)",
            height=34,
            fg_color="#064E3B",
            hover_color="#065F46",
            border_color="#10B981",
            border_width=1.5,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=16,
            cursor="hand2",
            command=self._open_ingredients_modal
        )
        if self.is_admin:
            self.manage_ingredients_btn.pack(side="right", padx=(0, 8))

        stock_icon = get_ctk_icon("cube_white", size=(16, 16))
        self.add_stock_btn = ctk.CTkButton(
            row_kpis,
            image=stock_icon,
            compound="left",
            text=" Agregar stock",
            height=34,
            fg_color="#78350F",
            hover_color="#92400E",
            border_color="#F59E0B",
            border_width=1.5,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=16,
            cursor="hand2",
            command=self._open_add_stock_modal
        )
        if self.is_admin:
            self.add_stock_btn.pack(side="right", padx=(0, 8))

        excel_img = get_ctk_icon("excel_white", size=(15, 15))
        self.export_excel_btn = ctk.CTkButton(
            row_kpis,
            image=excel_img,
            compound="left",
            text=" Exportar excel (.xlsx)",
            height=32,
            fg_color="#022C22",
            hover_color="#064E3B",
            border_color="#10B981",
            border_width=1.5,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=16,
            cursor="hand2",
            command=self._export_to_excel
        )
        if self.is_admin:
            self.export_excel_btn.pack(side="right", padx=(0, 8))

        # ── 2. Main Table Container ──────────────────────────────────────────
        self.table_container = ctk.CTkFrame(
            self,
            fg_color=DarkTheme.BG_CARD,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=8
        )
        self.table_container.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        # Interactive Table Header Row
        self.header_row = ctk.CTkFrame(
            self.table_container,
            fg_color=DarkTheme.BG_ELEVATED,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=6,
            height=36
        )
        self.header_row.pack(fill="x", padx=6, pady=(6, 4))
        self.header_row.pack_propagate(False)

        self._build_header_row()

        # Bottom Pagination Bar (anchored at bottom)
        self.pagination_frame = ctk.CTkFrame(self.table_container, fg_color="transparent", height=38)
        self.pagination_frame.pack(side="bottom", fill="x", padx=10, pady=(2, 6))

        self.page_prev_btn = ctk.CTkButton(
            self.pagination_frame,
            text="◀ Anterior",
            width=88,
            height=30,
            fg_color="#1E293B",
            hover_color="#334155",
            border_color="#475569",
            border_width=1,
            text_color="#CBD5E1",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            command=self._prev_page
        )
        self.page_prev_btn.pack(side="left")

        self.page_info_lbl = ctk.CTkLabel(
            self.pagination_frame,
            text="Página 1 de 1",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=DarkTheme.TEXT_SECONDARY
        )
        self.page_info_lbl.pack(side="left", padx=14)

        self.page_next_btn = ctk.CTkButton(
            self.pagination_frame,
            text="Siguiente ▶",
            width=88,
            height=30,
            fg_color="#1E293B",
            hover_color="#334155",
            border_color="#475569",
            border_width=1,
            text_color="#CBD5E1",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            command=self._next_page
        )
        self.page_next_btn.pack(side="left")

        # Scrollable Rows Frame (border_width=0, corner_radius=0 ensures zero offset with header)
        self.rows_scroll = ctk.CTkScrollableFrame(
            self.table_container,
            fg_color="transparent",
            corner_radius=0,
            border_width=0
        )
        self.rows_scroll.pack(fill="both", expand=True, padx=6, pady=(0, 2))
        try:
            self.rows_scroll._parent_canvas.configure(yscrollincrement=40)
        except Exception:
            pass

        # Dynamically sync spacer whenever geometry changes
        self.table_container.bind("<Configure>", self._on_table_container_configure, add="+")
        self.rows_scroll.bind("<Configure>", self._sync_header_scroll_spacer, add="+")
        self.header_row.bind("<Configure>", self._sync_header_scroll_spacer, add="+")

    def _build_header_row(self) -> None:
        """Construct or reconstruct table header according to columns_def."""
        for w in self.header_row.winfo_children():
            w.destroy()

        self.header_buttons: Dict[str, tk.Label] = {}
        for col_idx, (col_key, label, width, anchor, sortable, weight) in enumerate(self.columns_def):
            self.header_row.grid_columnconfigure(col_idx, weight=weight, minsize=width)
            cell_padx = (8, 4) if col_key in ("name", "category_name") else 2

            header_text = f"{label}  ▲" if col_key == self.sort_column and self.sort_direction == "asc" else (
                f"{label}  ▼" if col_key == self.sort_column else (f"{label}  ⇅" if sortable else label)
            )
            hdr_color = "#38BDF8" if col_key == self.sort_column else DarkTheme.TEXT_SECONDARY

            lbl = tk.Label(
                self.header_row,
                text=header_text,
                width=1,
                bg=DarkTheme.BG_ELEVATED,
                fg=hdr_color,
                font=("Segoe UI", 10, "bold"),
                anchor=anchor,
                cursor="hand2" if sortable else ""
            )
            lbl.grid(row=0, column=col_idx, sticky="nsew", padx=cell_padx, pady=4)

            if sortable:
                def _bind_header(k, w):
                    def _enter(e):
                        if k != self.sort_column:
                            w.configure(fg=DarkTheme.TEXT_PRIMARY)
                    def _leave(e):
                        if k != self.sort_column:
                            w.configure(fg=DarkTheme.TEXT_SECONDARY)
                    return _enter, _leave
                h_enter, h_leave = _bind_header(col_key, lbl)
                lbl.bind("<Enter>", h_enter)
                lbl.bind("<Leave>", h_leave)
                lbl.bind("<Button-1>", lambda e, k=col_key: self._on_header_click(k))
                self.header_buttons[col_key] = lbl

        # Column spacer in header corresponding to rows_scroll vertical scrollbar track
        spacer_col = len(self.columns_def)
        self.header_row.grid_columnconfigure(spacer_col, weight=0, minsize=17)
        tk.Label(self.header_row, text="", width=1, bg=DarkTheme.BG_ELEVATED).grid(row=0, column=spacer_col)

    def _on_table_container_configure(self, event=None) -> None:
        self._sync_header_scroll_spacer()

    def _sync_header_scroll_spacer(self, event=None) -> None:
        """Keep the header spacer column exactly matched to the scrollable frame's scrollbar track."""
        try:
            if not self.winfo_exists():
                return
            spacer_col = len(self.columns_def)
            sb_w = 0
            if hasattr(self.rows_scroll, "_scrollbar") and self.rows_scroll._scrollbar.winfo_exists():
                sb_w = self.rows_scroll._scrollbar.winfo_width()
            if sb_w <= 1:
                sb_w = 16
            target_spacer = max(16, sb_w + 1)
            self.header_row.grid_columnconfigure(spacer_col, weight=0, minsize=target_spacer)
        except Exception:
            pass

    def _schedule_sync_spacer(self) -> None:
        try:
            if hasattr(self, "_after_spacer_id") and self._after_spacer_id:
                self.after_cancel(self._after_spacer_id)
                self._after_spacer_id = None
        except Exception:
            pass
        try:
            if self.winfo_exists():
                self._after_spacer_id = self.after(30, self._safe_sync_spacer)
        except Exception:
            pass

    def _safe_sync_spacer(self) -> None:
        self._after_spacer_id = None
        try:
            if self.winfo_exists():
                self._sync_header_scroll_spacer()
        except Exception:
            pass

    def _open_touch_search_keypad(self) -> None:
        """Open touch numeric keypad modal for search input."""
        init_val = self.search_entry.get().strip()
        TouchKeypadModal(
            parent=self,
            title="Teclado Numérico - Buscar Producto",
            on_confirm_callback=self._on_touch_search_confirmed,
            initial_value=init_val
        )

    def _on_touch_search_confirmed(self, val: str) -> None:
        self._cancel_search_debounce()
        self.search_entry.delete(0, "end")
        self.search_entry.insert(0, val)
        self._on_filter_changed()

    def _filter_by_status_pill(self, status_target: str) -> None:
        """Interactive filter toggle by clicking KPI pills."""
        curr = self.status_filter.get()
        if status_target in curr:
            self.status_filter.set("Todos los estados")
        else:
            if status_target == "Normal":
                self.status_filter.set("Normal")
            elif status_target == "Bajo":
                self.status_filter.set("Bajo Stock")
            elif status_target == "Agotado":
                self.status_filter.set("Agotado")
        self._apply_filters_and_render()

    def _cancel_search_debounce(self) -> None:
        """Safely cancel any pending debounced search timer."""
        if self._search_debounce_job is not None:
            try:
                self.after_cancel(self._search_debounce_job)
            except Exception:
                pass
            self._search_debounce_job = None

    def _on_search_key_debounced(self, event=None) -> None:
        """Debounce search queries when typing in the search bar.
        Suppresses rapid sequential requests until the user pauses typing (300ms).
        """
        if event and event.keysym in (
            "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
            "Caps_Lock", "Tab", "ISO_Left_Tab", "Up", "Down", "Left", "Right",
            "Home", "End", "Prior", "Next", "Escape", "Return", "KP_Enter"
        ):
            return

        self._cancel_search_debounce()

        # If the input was completely cleared (e.g. Backspace or deleted), update immediately
        text = self.search_entry.get().strip() if hasattr(self, "search_entry") else ""
        if not text:
            self._on_filter_changed()
            return

        self._search_debounce_job = self.after(self.SEARCH_DEBOUNCE_MS, self._execute_debounced_search)

    def _execute_debounced_search(self) -> None:
        self._search_debounce_job = None
        self._on_filter_changed()

    def _on_search_enter(self) -> None:
        """Immediate search execution upon pressing Enter or clicking Search button."""
        self._cancel_search_debounce()
        self._on_filter_changed()

    def _clear_search(self) -> None:
        self._cancel_search_debounce()
        safe_reset_entry(self.search_entry)
        self._on_filter_changed()

    def _reset_all_filters(self) -> None:
        """Reset all search text and dropdown filters to default state in one click."""
        self._cancel_search_debounce()
        try:
            sound_manager.play_click()
        except Exception:
            pass
        safe_reset_entry(self.search_entry)
        self.category_filter.set("Todas las categorías")
        self.status_filter.set("Todos los estados")
        self.type_filter.set("Todos los tipos")
        self.current_page = 1
        self._apply_filters_and_render()

    def _reload_inventory(self) -> None:
        """Fetch fresh products from database, reset pagination, and refresh table & KPIs."""
        self._cancel_search_debounce()
        try:
            sound_manager.play_click()
        except Exception:
            pass
        self.current_page = 1
        self.load_data()

    def _prev_page(self) -> None:
        if self.current_page > 1:
            self.current_page -= 1
            self._update_pagination_ui()
            self._render_rows()

    def _next_page(self) -> None:
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._update_pagination_ui()
            self._render_rows()

    def _update_pagination_ui(self) -> None:
        if not hasattr(self, "page_info_lbl"):
            return
        total_items = len(self.filtered_products)
        if total_items == 0:
            self.page_info_lbl.configure(text="Página 0 de 0 (0 productos)")
            self.page_prev_btn.configure(state="disabled")
            self.page_next_btn.configure(state="disabled")
            return

        start_idx = (self.current_page - 1) * self.page_size + 1
        end_idx = min(self.current_page * self.page_size, total_items)
        self.page_info_lbl.configure(
            text=f"Página {self.current_page} de {self.total_pages} (Mostrando {start_idx} - {end_idx} de {total_items} productos)"
        )
        self.page_prev_btn.configure(state="normal" if self.current_page > 1 else "disabled")
        self.page_next_btn.configure(state="normal" if self.current_page < self.total_pages else "disabled")

    def _on_filter_changed(self) -> None:
        self.current_page = 1
        self._apply_filters_and_render()

    def _on_header_click(self, col_key: str) -> None:
        if self.sort_column == col_key:
            self.sort_direction = "desc" if self.sort_direction == "asc" else "asc"
        else:
            self.sort_column = col_key
            self.sort_direction = "asc"

        self._apply_filters_and_render()

    def load_data(self) -> None:
        """Fetch all products from database and refresh category filter options."""
        with get_db_connection() as conn:
            categories = ProductModel.get_categories(conn)
            cat_opts = ["Todas las categorías"] + [name for _, name in categories]
            curr_cat = self.category_filter.get()
            self.category_filter.configure(values=cat_opts)
            if curr_cat not in cat_opts:
                self.category_filter.set("Todas las categorías")

            self.products = ProductModel.get_all(conn)

        self._apply_filters_and_render()

    def _apply_filters_and_render(self) -> None:
        """Filter and sort the in-memory product list, update KPI chips, and render rows."""
        query = self.search_entry.get().strip().lower()
        cat_selected = self.category_filter.get()
        status_selected = self.status_filter.get()
        type_selected = self.type_filter.get()

        # ── 1. Filter ────────────────────────────────────────────────────────
        filtered = self.products[:]

        # Search term filter
        if query:
            filtered = [
                p for p in filtered
                if (
                    query in p.name.lower()
                    or (p.barcode and query in p.barcode.lower())
                    or (query in str(p.id))
                    or (query in p.category_name.lower())
                )
            ]

        # Category filter
        if cat_selected and cat_selected != "Todas las categorías":
            filtered = [p for p in filtered if p.category_name == cat_selected]

        # Status filter
        if status_selected and status_selected != "Todos los estados":
            clean_st = "Normal" if "Normal" in status_selected else ("Bajo" if "Bajo" in status_selected else "Agotado")
            filtered = [p for p in filtered if p.status == clean_st]

        # Type filter
        if type_selected and type_selected != "Todos los tipos":
            wanted_type = "PESO" if "Peso" in type_selected else "UNIDAD"
            filtered = [p for p in filtered if p.sale_type == wanted_type]

        # ── 2. Sort ──────────────────────────────────────────────────────────
        def get_sort_key(prod: Product):
            k = self.sort_column
            if k == "id":
                return prod.id
            elif k == "barcode":
                return prod.barcode or ""
            elif k == "name":
                return prod.name.lower()
            elif k == "category_name":
                return prod.category_name.lower()
            elif k == "sale_type":
                return prod.sale_type
            elif k == "unit_measure":
                return prod.unit_measure
            elif k == "price_base":
                return prod.price_base
            elif k == "cost":
                return prod.cost
            elif k == "iva":
                return prod.iva
            elif k == "min_stock":
                return prod.min_stock
            elif k == "stock":
                return prod.stock
            elif k == "status":
                order_map = {"Agotado": 0, "Bajo": 1, "Normal": 2}
                return order_map.get(prod.status, 3)
            return prod.name.lower()

        reverse = (self.sort_direction == "desc")
        filtered.sort(key=get_sort_key, reverse=reverse)
        self.filtered_products = filtered

        # ── 3. Update Header Arrows & Sort Active Indicator ──────────────────
        for col_key, lbl in self.header_buttons.items():
            base_label = next(l for k, l, *rest in self.columns_def if k == col_key)
            if col_key == self.sort_column:
                arrow = "▲" if self.sort_direction == "asc" else "▼"
                lbl.configure(
                    text=f"{base_label}  {arrow}",
                    fg="#38BDF8"
                )
            else:
                lbl.configure(
                    text=f"{base_label}  ⇅",
                    fg=DarkTheme.TEXT_SECONDARY
                )

        # ── 4. Update KPI Counters & Valuation ────────────────────────────────
        total_count = len(self.products)
        normal_count = sum(1 for p in self.products if p.status == "Normal")
        low_count = sum(1 for p in self.products if p.status == "Bajo")
        out_count = sum(1 for p in self.products if p.status == "Agotado")

        # Total valuation of positive stock in COP
        total_val = sum(max(0.0, p.stock) * p.price_base for p in self.products)

        if hasattr(self, "kpi_total_lbl") and self.kpi_total_lbl and self.kpi_total_lbl.winfo_exists():
            self.kpi_total_lbl.configure(text=f"Total de {total_count} productos. Mostrando {len(filtered)}")
        self.kpi_normal_btn.configure(text=f"✔ Normal: {normal_count}")
        self.kpi_low_btn.configure(text=f"⚠ Bajo: {low_count}")
        self.kpi_out_btn.configure(text=f"❗ Agotado: {out_count}")
        self.kpi_valuation_lbl.configure(text=f"Valor: {format_currency(total_val)}")

        # ── 5. Update Pagination & Render Rows ───────────────────────────────
        self.total_pages = max(1, math.ceil(len(self.filtered_products) / self.page_size))
        self.current_page = max(1, min(self.current_page, self.total_pages))
        self._update_pagination_ui()

        self._render_rows()

    def _render_rows(self) -> None:
        """Render the paginated products for the current page with high-performance widgets."""
        for w in self.rows_scroll.winfo_children():
            w.destroy()

        if not self.filtered_products:
            empty_frame = ctk.CTkFrame(self.rows_scroll, fg_color="transparent")
            empty_frame.pack(fill="both", expand=True, pady=40)
            ctk.CTkLabel(
                empty_frame,
                text="SIN PRODUCTOS REGISTRADOS",
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color=DarkTheme.TEXT_MUTED
            ).pack()
            ctk.CTkLabel(
                empty_frame,
                text="No se encontraron productos con los filtros seleccionados.",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=DarkTheme.TEXT_SECONDARY
            ).pack(pady=(4, 2))
            ctk.CTkLabel(
                empty_frame,
                text="Intente cambiar los términos de búsqueda o restablecer los filtros.",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=DarkTheme.TEXT_MUTED
            ).pack()
            return

        start_idx = (self.current_page - 1) * self.page_size
        end_idx = start_idx + self.page_size
        page_products = self.filtered_products[start_idx:end_idx]

        self._first_row_frame = None

        for idx, prod in enumerate(page_products):
            # Alternating dark backgrounds with subtle border
            row_bg = "#0B0F1D" if (idx % 2 == 0) else "#101626"
            row_border = "#1A2234"
            hover_bg = "#162036"
            hover_border = "#2D4268"

            row_frame = ctk.CTkFrame(
                self.rows_scroll,
                fg_color=row_bg,
                border_color=row_border,
                border_width=1,
                corner_radius=6,
                height=38
            )
            row_frame.pack(fill="x", pady=1)
            row_frame.pack_propagate(False)

            if idx == 0:
                self._first_row_frame = row_frame

            # Mirror exact grid column configuration from header_row
            for col_idx, (_, _, w, _, _, wt) in enumerate(self.columns_def):
                row_frame.grid_columnconfigure(col_idx, weight=wt, minsize=w)

            row_labels = []

            # Smooth hover highlight on row frame and its native child labels
            def make_hover(rf, labels, bg, bd, h_bg, h_bd):
                def _enter(e):
                    try:
                        rf.configure(fg_color=h_bg, border_color=h_bd)
                        for l in labels:
                            l.configure(bg=h_bg)
                    except Exception:
                        pass
                def _leave(e):
                    try:
                        rf.configure(fg_color=bg, border_color=bd)
                        for l in labels:
                            l.configure(bg=bg)
                    except Exception:
                        pass
                return _enter, _leave

            row_enter, row_leave = make_hover(row_frame, row_labels, row_bg, row_border, hover_bg, hover_border)
            row_frame.bind("<Enter>", row_enter)
            row_frame.bind("<Leave>", row_leave)

            # Commercial unit display formatting
            if prod.sale_type == "PESO":
                u_low = prod.unit_measure.lower()
                unit_disp = "Kg" if u_low == "kg" else ("g" if u_low == "g" else "lb")
                p_val = prod.unit_selling_price_commercial
                price_disp = f"{format_currency_short(p_val)} /{unit_disp}"

                c_val = prod.unit_cost_commercial
                cost_disp = f"{format_currency_short(c_val)} /{unit_disp}"

                min_v = prod.min_stock / 1000.0 if u_low == "kg" else (prod.min_stock / 500.0 if u_low == "lb" else prod.min_stock)
                min_stock_disp = f"{int(min_v) if min_v.is_integer() else f'{min_v:.2f}'} {unit_disp}"

                stk_raw = max(0.0, prod.stock)
                stk_v = stk_raw / 1000.0 if u_low == "kg" else (stk_raw / 500.0 if u_low == "lb" else stk_raw)
                stock_disp = f"{int(stk_v) if stk_v.is_integer() else f'{stk_v:.2f}'} {unit_disp}"
            else:
                unit_disp = "und"
                price_disp = f"{format_currency_short(prod.price_base)} /und"
                cost_disp = f"{format_currency_short(prod.cost)} /und"

                m_int = int(prod.min_stock) if float(prod.min_stock).is_integer() else f"{prod.min_stock:.1f}"
                min_stock_disp = f"{m_int} und"

                s_val = max(0.0, prod.stock)
                s_int = int(s_val) if float(s_val).is_integer() else f"{s_val:.1f}"
                stock_disp = f"{s_int} und"

            iva_disp = f"{int(prod.iva)}%" if float(prod.iva).is_integer() else f"{prod.iva:.1f}%"

            # 11 text columns: (col_key, val_text, anchor, text_color, is_bold)
            cols_data = [
                ("id", str(prod.id), "center", DarkTheme.TEXT_MUTED, False),
                ("barcode", prod.barcode or "-", "center", DarkTheme.TEXT_SECONDARY, False),
                ("name", prod.name, "w", DarkTheme.TEXT_PRIMARY, True),
                ("category_name", prod.category_name, "w", DarkTheme.TEXT_SECONDARY, False),
                ("sale_type", prod.display_sale_type, "center", DarkTheme.TEXT_SECONDARY, False),
                ("unit_measure", unit_disp, "center", DarkTheme.TEXT_MUTED, False),
                ("price_base", price_disp, "center", DarkTheme.SUCCESS_TEXT, True),
                ("cost", cost_disp, "center", DarkTheme.TEXT_SECONDARY, False),
                ("iva", iva_disp, "center", DarkTheme.INFO_TEXT, False),
                ("min_stock", min_stock_disp, "center", DarkTheme.WARNING_TEXT, False),
                ("stock", stock_disp, "center", DarkTheme.TEXT_PRIMARY, True),
            ]

            for col_idx, (col_key, val_text, anchor, text_color, is_bold) in enumerate(cols_data):
                cell_padx = (8, 4) if col_key in ("name", "category_name") else 2
                # Ultra-fast native tk.Label with width=1 for strict column adherence
                lbl = tk.Label(
                    row_frame,
                    text=val_text,
                    width=1,
                    bg=row_bg,
                    fg=text_color,
                    font=("Segoe UI", 10, "bold" if is_bold else "normal"),
                    anchor=anchor
                )
                lbl.grid(row=0, column=col_idx, sticky="nsew", padx=cell_padx)
                lbl.bind("<Enter>", row_enter)
                lbl.bind("<Leave>", row_leave)
                row_labels.append(lbl)

            # Col 11: Estado Centered Chip Badge with official icons
            st = prod.status
            if st == "Normal":
                st_icon_img = get_ctk_icon("check_green", size=(20, 20))
            elif st == "Bajo":
                st_icon_img = get_ctk_icon("warning_amber", size=(20, 20))
            else:
                st_icon_img = get_ctk_icon("xmark_red", size=(20, 20))

            status_container = tk.Frame(row_frame, bg=row_bg)
            status_container.grid(row=0, column=11, sticky="nsew", padx=2)
            status_container.bind("<Enter>", row_enter)
            status_container.bind("<Leave>", row_leave)
            row_labels.append(status_container)

            status_chip = ctk.CTkLabel(
                status_container,
                image=st_icon_img,
                text="",
                width=24,
                height=24,
                fg_color="transparent"
            )
            status_chip.pack(expand=True)
            status_chip.bind("<Enter>", row_enter)
            status_chip.bind("<Leave>", row_leave)

            # Col 12: Action buttons with user's official SVG icons: Ver (eye), Editar (pen), Eliminar (trash-arrow)
            # Only rendered if current user has administrator privileges
            if self.is_admin:
                actions_frame = tk.Frame(row_frame, bg=row_bg)
                actions_frame.grid(row=0, column=12, sticky="nsew", padx=2)
                actions_frame.bind("<Enter>", row_enter)
                actions_frame.bind("<Leave>", row_leave)
                row_labels.append(actions_frame)

                btn_box = tk.Frame(actions_frame, bg=row_bg)
                btn_box.pack(expand=True)
                btn_box.bind("<Enter>", row_enter)
                btn_box.bind("<Leave>", row_leave)
                row_labels.append(btn_box)

                view_img = get_ctk_icon("eye_slate", size=(14, 14))
                edit_img = get_ctk_icon("pen_gold", size=(14, 14))
                trash_img = get_ctk_icon("trash_arrow_red", size=(14, 14))

                # 1. View button (👁) with generous internal padding
                view_btn = ctk.CTkButton(
                    btn_box,
                    text="",
                    width=32,
                    height=28,
                    corner_radius=6,
                    cursor="hand2",
                    command=lambda p=prod: self._open_detail_product_modal(p)
                )
                apply_palette_button(view_btn, variant="ver", icon_name="eye_slate", icon_size=(14, 14))
                view_btn.pack(side="left", padx=2)

                # 2. Edit button (✏) with generous internal padding
                edit_btn = ctk.CTkButton(
                    btn_box,
                    text="",
                    width=32,
                    height=28,
                    corner_radius=6,
                    cursor="hand2",
                    command=lambda p=prod: self._open_edit_product_modal(p)
                )
                apply_palette_button(edit_btn, variant="editar", icon_name="pen_gold", icon_size=(14, 14))
                edit_btn.pack(side="left", padx=2)

                # 3. Delete button (🗑) with generous internal padding
                del_btn = ctk.CTkButton(
                    btn_box,
                    text="",
                    width=32,
                    height=28,
                    corner_radius=6,
                    cursor="hand2",
                    command=lambda p=prod: self._delete_product(p)
                )
                apply_palette_button(del_btn, variant="eliminar", icon_name="trash_arrow_red", icon_size=(14, 14))
                del_btn.pack(side="left", padx=2)

        # Subtle bottom spacer so the last row aligns naturally without excess void
        bottom_spacer = ctk.CTkFrame(self.rows_scroll, fg_color="transparent", height=4)
        bottom_spacer.pack(fill="x", pady=(0, 2))

        # Dynamically sync scrollbar spacer in header if rows exist
        try:
            if self.winfo_exists():
                self.update_idletasks()
                self._sync_header_scroll_spacer()
                self._schedule_sync_spacer()
        except Exception:
            pass

    # ── Modal Launchers ──────────────────────────────────────────────────────
    def _open_detail_product_modal(self, product: Product) -> None:
        try:
            on_edit = self._open_edit_product_modal if self.is_admin else None
            ProductDetailModal(parent=self, product=product, on_edit_request=on_edit)
        except Exception as e:
            logging.exception("Error al abrir ProductDetailModal: %s", e)
            messagebox.showerror("Error al Abrir Detalle", f"No se pudo abrir el detalle del producto:\n{e}", parent=self)

    def _open_new_product_modal(self) -> None:
        if not self.is_admin:
            messagebox.showwarning("Acceso Denegado", "Solo el Administrador puede registrar nuevos productos.", parent=self)
            return
        try:
            ProductFormModal(parent=self, product=None, on_save_callback=self.load_data)
        except Exception as e:
            logging.exception("Error al abrir ProductFormModal: %s", e)
            messagebox.showerror("Error al Abrir Formulario", f"No se pudo abrir el formulario de producto:\n{e}", parent=self)

    def _open_add_stock_modal(self) -> None:
        if not self.is_admin:
            messagebox.showwarning("Acceso Denegado", "Solo el Administrador puede ingresar o actualizar stock.", parent=self)
            return
        try:
            AddStockModal(parent=self, on_save_callback=self.load_data)
        except Exception as e:
            logging.exception("Error al abrir AddStockModal: %s", e)
            messagebox.showerror("Error al Abrir Entrada de Stock", f"No se pudo abrir la ventana de agregar stock:\n{e}", parent=self)

    def _open_recipes_modal(self, product_id: Optional[int] = None) -> None:
        if not self.is_admin:
            messagebox.showwarning("Acceso Denegado", "Solo el Administrador puede gestionar recetas.", parent=self)
            return
        try:
            RecipeManagerModal(parent=self, selected_product_id=product_id, on_recipe_saved_callback=self.load_data)
        except Exception as e:
            logging.exception("Error al abrir RecipeManagerModal: %s", e)
            messagebox.showerror("Error", f"No se pudo abrir la gestión de recetas:\n{e}", parent=self)

    def _open_ingredients_modal(self) -> None:
        if not self.is_admin:
            messagebox.showwarning("Acceso Denegado", "Solo el Administrador puede gestionar ingredientes.", parent=self)
            return
        try:
            IngredientsManagerModal(parent=self, on_refresh_parent_callback=self.load_data)
        except Exception as e:
            logging.exception("Error al abrir IngredientsManagerModal: %s", e)
            messagebox.showerror("Error", f"No se pudo abrir la gestión de ingredientes:\n{e}", parent=self)

    def _open_edit_product_modal(self, product: Product) -> None:
        if not self.is_admin:
            messagebox.showwarning("Acceso Denegado", "Solo el Administrador puede modificar productos.", parent=self)
            return
        try:
            ProductFormModal(parent=self, product=product, on_save_callback=self.load_data)
        except Exception as e:
            logging.exception("Error al abrir ProductFormModal (edit): %s", e)
            messagebox.showerror("Error al Abrir Modificación", f"No se pudo abrir la modificación del producto:\n{e}", parent=self)

    def _delete_product(self, product: Product) -> None:
        if not self.is_admin:
            messagebox.showwarning("Acceso Denegado", "Solo el Administrador puede eliminar productos.", parent=self)
            return
        if messagebox.askyesno(
            "Confirmar Eliminación",
            f"¿Está seguro de que desea eliminar el producto '{product.name}' (ID #{product.id})?\n\nEsta acción no se puede deshacer.",
            parent=self
        ):
            try:
                with get_db_connection() as conn:
                    ProductModel.delete(conn, product.id)
                self.load_data()
            except sqlite3.IntegrityError:
                messagebox.showerror(
                    "Operación Bloqueada",
                    f"No se puede eliminar el producto '{product.name}' porque tiene ventas o movimientos históricos asociados en el sistema.\n\nPara descontinuar el producto, configure su stock en 0.",
                    parent=self
                )
            except Exception as e:
                messagebox.showerror("Error al Eliminar", f"No se pudo eliminar el producto:\n{e}", parent=self)

    # ── Excel Export ─────────────────────────────────────────────────────────
    def _export_to_excel(self) -> None:
        """Export current filtered inventory catalog to a polished Microsoft Excel (.xlsx) file."""
        if not self.is_admin:
            messagebox.showwarning("Acceso Denegado", "Solo el Administrador puede exportar el inventario a Excel.", parent=self)
            return
        if not self.products:
            messagebox.showwarning("Sin Datos", "No hay productos disponibles para exportar.", parent=self)
            return

        from datetime import datetime
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"Inventario_XLBurguer_{now_str}.xlsx"

        file_path = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar Catálogo de Inventario a Excel",
            defaultextension=".xlsx",
            initialfile=default_filename,
            filetypes=[("Libro de Excel (*.xlsx)", "*.xlsx")]
        )
        if not file_path:
            return

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Inventario"
            ws.views.sheetView[0].showGridLines = True

            # Styles
            title_font = Font(name="Calibri", size=16, bold=True, color="1E293B")
            meta_font = Font(name="Calibri", size=10, italic=True, color="64748B")
            header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
            header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
            data_font = Font(name="Calibri", size=10, color="0F172A")
            total_font = Font(name="Calibri", size=11, bold=True, color="0F172A")

            thin_border = Border(
                left=Side(style="thin", color="CBD5E1"),
                right=Side(style="thin", color="CBD5E1"),
                top=Side(style="thin", color="CBD5E1"),
                bottom=Side(style="thin", color="CBD5E1")
            )
            total_border = Border(
                top=Side(style="thin", color="0F172A"),
                bottom=Side(style="double", color="0F172A")
            )

            # Title
            ws["A1"] = "XL BURGUER — REPORTE GENERAL DE INVENTARIO"
            ws["A1"].font = title_font
            ws["A2"] = f"Generado el: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}  |  Total de productos: {len(self.filtered_products)}"
            ws["A2"].font = meta_font

            # Headers
            headers = [
                ("ID", 8, "center"),
                ("Código", 14, "center"),
                ("Nombre del Producto", 34, "left"),
                ("Categoría", 22, "left"),
                ("Tipo", 12, "center"),
                ("Unidad", 10, "center"),
                ("Precio Venta", 16, "right"),
                ("Costo", 16, "right"),
                ("IVA %", 10, "center"),
                ("Stock Mínimo", 14, "right"),
                ("Stock Actual", 14, "right"),
                ("Estado", 12, "center"),
                ("Valor Total Stock", 18, "right")
            ]

            start_row = 4
            for col_idx, (h_name, _, align_dir) in enumerate(headers, start=1):
                cell = ws.cell(row=start_row, column=col_idx, value=h_name)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal=align_dir, vertical="center")
                cell.border = thin_border
            ws.row_dimensions[start_row].height = 26

            # Fill data rows
            current_row = start_row + 1
            for p in self.filtered_products:
                unit_disp = "Kg" if p.unit_measure.lower() == "kg" else ("g" if p.unit_measure.lower() == "g" else ("lb" if p.unit_measure.lower() == "lb" else p.unit_measure))
                if p.sale_type == "PESO":
                    p_val = p.unit_selling_price_commercial
                    c_val = p.unit_cost_commercial
                    u_low = p.unit_measure.lower()
                    stk_v = p.stock / 1000.0 if u_low == "kg" else (p.stock / 500.0 if u_low == "lb" else p.stock)
                    min_v = p.min_stock / 1000.0 if u_low == "kg" else (p.min_stock / 500.0 if u_low == "lb" else p.min_stock)
                    val_tot = max(0.0, p.stock) * p.price_base
                else:
                    p_val = p.price_base
                    c_val = p.cost
                    stk_v = p.stock
                    min_v = p.min_stock
                    val_tot = max(0.0, p.stock) * p.price_base

                row_values = [
                    (p.id, "center", None),
                    (p.barcode or "-", "center", None),
                    (p.name, "left", None),
                    (p.category_name, "left", None),
                    (p.display_sale_type, "center", None),
                    (unit_disp, "center", None),
                    (p_val, "right", '"$"#,##0'),
                    (c_val, "right", '"$"#,##0'),
                    (p.iva / 100.0, "center", "0%"),
                    (min_v, "right", "#,##0.00" if isinstance(min_v, float) and not min_v.is_integer() else "#,##0"),
                    (stk_v, "right", "#,##0.00" if isinstance(stk_v, float) and not stk_v.is_integer() else "#,##0"),
                    (p.status, "center", None),
                    (val_tot, "right", '"$"#,##0')
                ]

                # Background fill based on status
                if p.status == "Normal":
                    st_fill = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
                    st_font_color = "065F46"
                elif p.status == "Bajo":
                    st_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
                    st_font_color = "92400E"
                else:
                    st_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
                    st_font_color = "991B1B"

                for col_idx, (val, align_dir, num_fmt) in enumerate(row_values, start=1):
                    cell = ws.cell(row=current_row, column=col_idx, value=val)
                    cell.font = data_font
                    cell.alignment = Alignment(horizontal=align_dir, vertical="center")
                    cell.border = thin_border
                    if num_fmt:
                        cell.number_format = num_fmt
                    if col_idx == 12:  # Estado column
                        cell.fill = st_fill
                        cell.font = Font(name="Calibri", size=10, bold=True, color=st_font_color)

                ws.row_dimensions[current_row].height = 20
                current_row += 1

            # Totals row
            total_row_idx = current_row
            ws.cell(row=total_row_idx, column=3, value="TOTALES").font = total_font
            ws.cell(row=total_row_idx, column=3).alignment = Alignment(horizontal="right", vertical="center")
            ws.cell(row=total_row_idx, column=13, value=f"=SUM(M5:M{total_row_idx-1})")
            ws.cell(row=total_row_idx, column=13).font = total_font
            ws.cell(row=total_row_idx, column=13).number_format = '"$"#,##0'
            ws.cell(row=total_row_idx, column=13).alignment = Alignment(horizontal="right", vertical="center")

            for col_idx in range(1, len(headers) + 1):
                ws.cell(row=total_row_idx, column=col_idx).border = total_border

            # Set column widths
            for col_idx, (_, col_w, _) in enumerate(headers, start=1):
                col_letter = get_column_letter(col_idx)
                ws.column_dimensions[col_letter].width = col_w

            wb.save(file_path)

            if messagebox.askyesno(
                "Exportación Exitosa",
                f"El inventario se exportó exitosamente a:\n{file_path}\n\n¿Desea abrir el archivo en Excel ahora?",
                parent=self
            ):
                try:
                    os.startfile(file_path)
                except Exception:
                    pass
        except Exception as e:
            messagebox.showerror("Error al Exportar", f"Ocurrió un error al generar el archivo Excel:\n{e}", parent=self)

