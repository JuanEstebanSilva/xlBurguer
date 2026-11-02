"""Statistics, Visual Charts, Sales History and Reporting Frame for XL Burguer.
Provides an executive dashboard featuring:
- Top full-width unified controls and filter bar (100% width) matching Inventory & POS styling.
- Quick preset buttons with dedicated calendar icons:
    - 'Hoy' with calendar_day_white
    - '7 Días' with calendar_week_white
    - 'Este Mes' with calendar_regular_white
    - 'Todo' with infinity_white
- Search box with magenta/purple lupita button (search_magenta) and reset button (recycle_slate).
- 50/50 horizontal split layout:
    - Left column (50%):
        - 4 compact KPI cards (2x2 grid) with white titles, calendar icons, larger readable sales counts/averages.
        - Evolución de Ventas Diarias bar chart with stats_white icon.
        - Medios de Pago in green scales with icons (money, phone, card).
        - Top Categorías in amber scale without emojis/icons.
    - Right column (50%): Full vertical height Sales Invoices Table:
        - Columns: Factura, Fecha y Hora, Cajero, Cliente, Ítems, Método (only icon), Total Factura, Acciones.
        - Efectivo and Cambio columns removed as requested.
        - Action button labeled 'Ver factura' in blue with ticket icon opening thermal preview.
- Instantaneous pagination (25 invoices per page).
- Native executive Microsoft Excel export (.xlsx).
"""

from datetime import datetime, timedelta
import math
import os
import re
from tkinter import filedialog, messagebox
from typing import Any, Callable, Dict, List, Optional, Tuple
import customtkinter as ctk

from database.connection import get_db_connection
from hardware.ticket_printer import format_ticket
from views.ticket_preview_modal import TicketPreviewModal
from models.product import ProductModel, format_currency, format_currency_short
from models.sale import SaleModel
from utils.asset_manager import get_ctk_icon, get_tinted_ctk_icon
from utils.excel_exporter import export_sales_async
from utils.sound_manager import sound_manager
from utils.theme import DarkTheme, safe_reset_entry, apply_palette_button
from views.calendar_modal import CalendarPickerModal


# ─────────────────────────────────────────────────────────────────────────────
# 1. VECTOR CANVAS BAR CHART (TENDENCIA DE VENTAS DIARIAS)
# ─────────────────────────────────────────────────────────────────────────────
class SalesTrendsCanvas(ctk.CTkFrame):
    """Custom high-performance vector bar chart drawn with native canvas.
    Renders daily revenue bars with smooth rounded geometry, gridlines,
    peak day highlight, and hover tooltips.
    """

    def __init__(self, parent, height: int = 150):
        super().__init__(
            parent,
            fg_color=DarkTheme.BG_CARD,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=8
        )
        self.chart_height = height
        self.data: List[Dict[str, Any]] = []

        # Top title row
        title_row = ctk.CTkFrame(self, fg_color="transparent")
        title_row.pack(fill="x", padx=12, pady=(8, 6))

        chart_icon = get_ctk_icon("stats_white", size=(16, 16)) or get_ctk_icon("chart_column_white", size=(16, 16))
        ctk.CTkLabel(
            title_row,
            image=chart_icon,
            compound="left",
            text="  Evolución de Ventas Diarias",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#FFFFFF"
        ).pack(side="left")

        # Sleek executive peak badge pill
        self.peak_pill = ctk.CTkFrame(
            title_row,
            fg_color="#062E22",
            border_color="#10B981",
            border_width=1,
            corner_radius=12
        )
        self.peak_pill.pack(side="right")

        self.peak_lbl = ctk.CTkLabel(
            self.peak_pill,
            text="▲ Pico: COP $ 0",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#34D399",
            padx=10,
            pady=3
        )
        self.peak_lbl.pack()

        # Native Drawing Canvas
        self.canvas = ctk.CTkCanvas(
            self,
            bg="#0B0F1D",
            highlightthickness=0,
            bd=0,
            height=height
        )
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.canvas.bind("<Configure>", lambda e: self.draw_chart())

    def set_data(self, data: List[Dict[str, Any]]) -> None:
        """Data format: list of {'label': '03 Oct', 'amount': 1000000.0, 'count': 68, 'sub': 'Sáb'}"""
        self.data = data
        if data:
            max_amt = max(d["amount"] for d in data)
            self.peak_lbl.configure(text=f"▲ Pico: {format_currency(max_amt)}")
        else:
            self.peak_lbl.configure(text="▲ Pico: Sin datos")
        self.draw_chart()

    def draw_chart(self) -> None:
        """Render gridlines, bars, labels, and peak indicators."""
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()

        if w <= 10 or h <= 10:
            return

        if not self.data:
            self.canvas.create_text(
                w / 2, h / 2,
                text="Sin registros de ventas para el período seleccionado",
                fill=DarkTheme.TEXT_MUTED,
                font=("Segoe UI", 11, "italic")
            )
            return

        margin_left = 60
        margin_right = 16
        margin_top = 20
        margin_bottom = 28

        plot_w = w - margin_left - margin_right
        plot_h = h - margin_top - margin_bottom

        if plot_w <= 20 or plot_h <= 20:
            return

        max_val = max(d["amount"] for d in self.data)
        if max_val <= 0:
            max_val = 100_000.0

        # Round up max_val to pleasant ceiling
        magnitude = 10 ** math.floor(math.log10(max_val))
        normalized = max_val / magnitude
        if normalized <= 1.5:
            ceil_mult = 1.5
        elif normalized <= 2:
            ceil_mult = 2
        elif normalized <= 5:
            ceil_mult = 5
        else:
            ceil_mult = 10
        y_max = ceil_mult * magnitude

        # 3 horizontal gridlines
        grid_steps = 3
        for i in range(grid_steps + 1):
            val = (y_max / grid_steps) * i
            y_pos = margin_top + plot_h - (plot_h * (val / y_max))

            self.canvas.create_line(
                margin_left, y_pos,
                w - margin_right, y_pos,
                fill="#1E293B" if i > 0 else "#334155",
                dash=(2, 4) if (0 < i < grid_steps) else (),
                width=1
            )

            if val >= 1_000_000:
                y_label = f"${val/1_000_000:.1f}M"
            elif val >= 1_000:
                y_label = f"${val/1_000:.0f}K"
            else:
                y_label = f"${val:.0f}"

            self.canvas.create_text(
                margin_left - 8, y_pos,
                text=y_label,
                fill=DarkTheme.TEXT_MUTED,
                font=("Segoe UI", 8),
                anchor="e"
            )

        n_bars = len(self.data)
        slot_w = plot_w / n_bars
        bar_w = max(10, min(38, slot_w * 0.58))

        peak_amount = max(d["amount"] for d in self.data)

        for idx, item in enumerate(self.data):
            amt = item["amount"]
            cx = margin_left + (idx * slot_w) + (slot_w / 2)
            bx1 = cx - (bar_w / 2)
            bx2 = cx + (bar_w / 2)

            bar_h = (amt / y_max) * plot_h if y_max > 0 else 0
            by1 = margin_top + plot_h - bar_h
            by2 = margin_top + plot_h

            is_peak = (amt == peak_amount and amt > 0)
            fill_col = "#10B981" if is_peak else ("#3B82F6" if amt > 0 else "#1E293B")
            outline_col = "#34D399" if is_peak else ("#60A5FA" if amt > 0 else "#334155")

            if bar_h > 0:
                self.canvas.create_rectangle(
                    bx1, by1, bx2, by2,
                    fill=fill_col,
                    outline=outline_col,
                    width=1
                )

            if amt > 0:
                if amt >= 1_000_000:
                    amt_text = f"${amt/1_000_000:.1f}M"
                elif amt >= 1_000:
                    amt_text = f"${amt/1_000:.0f}K"
                else:
                    amt_text = f"${amt:.0f}"

                self.canvas.create_text(
                    cx, by1 - 7,
                    text=amt_text,
                    fill="#34D399" if is_peak else "#93C5FD",
                    font=("Segoe UI", 8, "bold")
                )

            lbl_text = item.get("label", "")
            sub_text = item.get("sub", "")
            full_lbl = f"{lbl_text}\n{sub_text}" if sub_text else lbl_text

            self.canvas.create_text(
                cx, by2 + 12,
                text=full_lbl,
                fill=DarkTheme.TEXT_SECONDARY if amt > 0 else DarkTheme.TEXT_MUTED,
                font=("Segoe UI", 8, "bold" if is_peak else "normal")
            )


def resolve_pm_info(raw_method: str) -> Dict[str, Any]:
    """Resolve human-readable name, dedicated icon, and aesthetic color for payment methods."""
    m = str(raw_method or "").upper().strip()
    if "NEQUI" in m:
        return {
            "name": "Nequi",
            "icon": get_ctk_icon("nequi", size=(14, 14)) or get_ctk_icon("mobile_green", size=(14, 14)),
            "color": "#34D399"
        }
    elif "DAVIPLATA" in m:
        return {
            "name": "Daviplata",
            "icon": get_ctk_icon("daviplata", size=(14, 14)) or get_ctk_icon("mobile_green", size=(14, 14)),
            "color": "#6EE7B7"
        }
    elif "BANCOLOMBIA" in m:
        return {
            "name": "Bancolombia",
            "icon": get_ctk_icon("bancolombia", size=(14, 14)) or get_ctk_icon("mobile_green", size=(14, 14)),
            "color": "#FBBF24"
        }
    elif "EFECTIVO" in m:
        return {
            "name": "Efectivo",
            "icon": get_ctk_icon("money_white", size=(14, 14)) or get_ctk_icon("money_green", size=(14, 14)),
            "color": "#10B981"
        }
    elif "TARJETA" in m:
        return {
            "name": "Tarjeta",
            "icon": get_ctk_icon("credit_card_white", size=(14, 14)) or get_ctk_icon("credit_card_green", size=(14, 14)),
            "color": "#059669"
        }
    elif "FIADO" in m:
        return {
            "name": "Fiado",
            "icon": get_ctk_icon("building_user_white", size=(14, 14)) or get_ctk_icon("meat_white", size=(14, 14)),
            "color": "#38BDF8"
        }
    elif "TRANSFERENCIA" in m:
        return {
            "name": "Transferencia",
            "icon": get_ctk_icon("mobile_white", size=(14, 14)) or get_ctk_icon("mobile_green", size=(14, 14)),
            "color": "#34D399"
        }
    else:
        return {
            "name": raw_method.capitalize(),
            "icon": None,
            "color": "#10B981"
        }


# ─────────────────────────────────────────────────────────────────────────────
# 2. BREAKDOWN CHARTS (MEDIOS DE PAGO Y TOP CATEGORÍAS)
# ─────────────────────────────────────────────────────────────────────────────
class BreakdownChartWidget(ctk.CTkFrame):
    """Visual breakdown displaying payment method distribution and top product categories.
    - Payment methods feature dedicated icons (money, phone, card) rendered in scales of green.
    - Top Categories are presented cleanly without emojis and in a harmonious single-color amber gradient.
    """

    def __init__(self, parent):
        super().__init__(
            parent,
            fg_color=DarkTheme.BG_CARD,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=8
        )

        # Header Title
        title_row = ctk.CTkFrame(self, fg_color="transparent")
        title_row.pack(fill="x", padx=12, pady=(8, 4))

        pm_header_icon = get_ctk_icon("credit_card_white", size=(15, 15)) or get_ctk_icon("money_white", size=(15, 15))
        ctk.CTkLabel(
            title_row,
            image=pm_header_icon,
            compound="left",
            text="  Medios de Pago y Top Categorías",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#FFFFFF"
        ).pack(side="left")

        # Container with two parallel columns
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)

        # Left Column: Payment Methods
        self.pm_frame = ctk.CTkFrame(content, fg_color="transparent")
        self.pm_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        ctk.CTkLabel(
            self.pm_frame,
            text="DISTRIBUCIÓN POR PAGO",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=DarkTheme.TEXT_MUTED
        ).pack(anchor="w", pady=(0, 4))

        self.pm_rows_container = ctk.CTkFrame(self.pm_frame, fg_color="transparent")
        self.pm_rows_container.pack(fill="both", expand=True)

        # Right Column: Top Categories
        self.cat_frame = ctk.CTkFrame(content, fg_color="transparent")
        self.cat_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        ctk.CTkLabel(
            self.cat_frame,
            text="TOP CATEGORÍAS EN VENTAS",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=DarkTheme.TEXT_MUTED
        ).pack(anchor="w", pady=(0, 4))

        self.cat_rows_container = ctk.CTkFrame(self.cat_frame, fg_color="transparent")
        self.cat_rows_container.pack(fill="both", expand=True)

    def set_data(self, payment_methods: List[Dict[str, Any]], categories: List[Dict[str, Any]]) -> None:
        """Update both payment methods progress bars and categories bars."""
        # 1. Payment Methods (Green monochromatic scale with dedicated icons)
        for w in self.pm_rows_container.winfo_children():
            w.destroy()

        # Aggregate payment methods by resolved platform name (Nequi, Daviplata, Bancolombia, etc.)
        agg_pm: Dict[str, Dict[str, Any]] = {}
        for pm in payment_methods:
            cfg = resolve_pm_info(pm.get("payment_method", ""))
            k = cfg["name"]
            if k not in agg_pm:
                agg_pm[k] = {
                    "name": k,
                    "icon": cfg["icon"],
                    "color": cfg["color"],
                    "tot": 0.0,
                    "cnt": 0
                }
            agg_pm[k]["tot"] += float(pm.get("tot", 0.0) or 0.0)
            agg_pm[k]["cnt"] += int(pm.get("cnt", 0) or 0)

        sorted_pm = sorted(agg_pm.values(), key=lambda x: x["tot"], reverse=True)
        total_pm = sum(pm["tot"] for pm in sorted_pm) or 1.0

        if not sorted_pm:
            ctk.CTkLabel(
                self.pm_rows_container,
                text="Sin datos de pago",
                font=ctk.CTkFont(family="Segoe UI", size=10, slant="italic"),
                text_color=DarkTheme.TEXT_MUTED
            ).pack(pady=10)
        else:
            pm_bar_palette = ["#C084FC", "#9333EA", "#6B21A8"]  # Lila claro, lila medio, lila oscuro
            pm_val_col = "#C084FC"  # Todos los valores en lila claro

            for idx, pm in enumerate(sorted_pm[:3]):
                cfg = pm
                bar_col = pm_bar_palette[idx % len(pm_bar_palette)]
                amt = pm["tot"]
                pct = (amt / total_pm) * 100.0

                row = ctk.CTkFrame(self.pm_rows_container, fg_color="transparent")
                row.pack(fill="x", pady=2)

                lbl_box = ctk.CTkFrame(row, fg_color="transparent")
                lbl_box.pack(fill="x")

                # Pack right value first so it is guaranteed flush on right edge without overlap
                ctk.CTkLabel(
                    lbl_box,
                    text=f"$ {amt:,.0f}".replace(",", "."),
                    font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                    text_color=pm_val_col
                ).pack(side="right")

                left_sub = ctk.CTkFrame(lbl_box, fg_color="transparent")
                left_sub.pack(side="left")

                if cfg["icon"]:
                    ctk.CTkLabel(left_sub, image=cfg["icon"], text="").pack(side="left", padx=(0, 4))
                
                disp_name = cfg["name"]
                if len(disp_name) > 17:
                    disp_name = f"{disp_name[:15]}..."
                
                ctk.CTkLabel(
                    left_sub,
                    text=disp_name,
                    font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                    text_color=DarkTheme.TEXT_PRIMARY
                ).pack(side="left")

                ctk.CTkLabel(
                    left_sub,
                    text=f" ({pct:.1f}%)",
                    font=ctk.CTkFont(family="Segoe UI", size=9),
                    text_color=DarkTheme.TEXT_MUTED
                ).pack(side="left", padx=(2, 0))

                prog = ctk.CTkProgressBar(row, height=5, corner_radius=3, fg_color="#1E293B", progress_color=bar_col)
                prog.pack(fill="x", pady=(2, 0))
                prog.set(max(0.02, pct / 100.0))

        # 2. Top Categories (Mint green monochromatic scale, all values in verde menta claro)
        for w in self.cat_rows_container.winfo_children():
            w.destroy()

        total_cat = sum(c["tot"] for c in categories) or 1.0
        cat_bar_palette = ["#2DD4BF", "#0D9488", "#115E59"]  # Verde menta claro, medio, oscuro
        cat_val_col = "#2DD4BF"  # Todos los valores en verde menta claro

        if not categories:
            ctk.CTkLabel(
                self.cat_rows_container,
                text="Sin datos de categorías",
                font=ctk.CTkFont(family="Segoe UI", size=10, slant="italic"),
                text_color=DarkTheme.TEXT_MUTED
            ).pack(pady=10)
        else:
            for idx, c in enumerate(categories[:3]):
                bar_col = cat_bar_palette[idx % len(cat_bar_palette)]
                amt = c["tot"]
                pct = (amt / total_cat) * 100.0

                row = ctk.CTkFrame(self.cat_rows_container, fg_color="transparent")
                row.pack(fill="x", pady=2)

                lbl_box = ctk.CTkFrame(row, fg_color="transparent")
                lbl_box.pack(fill="x")

                # Pack right value first so it is guaranteed flush on right edge without overlap
                ctk.CTkLabel(
                    lbl_box,
                    text=f"$ {amt:,.0f}".replace(",", "."),
                    font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                    text_color=cat_val_col
                ).pack(side="right")

                left_sub = ctk.CTkFrame(lbl_box, fg_color="transparent")
                left_sub.pack(side="left")

                disp_cat = c["category_name"]
                if len(disp_cat) > 17:
                    disp_cat = f"{disp_cat[:15]}..."

                ctk.CTkLabel(
                    left_sub,
                    text=disp_cat,
                    font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                    text_color=DarkTheme.TEXT_PRIMARY
                ).pack(side="left")

                ctk.CTkLabel(
                    left_sub,
                    text=f" ({pct:.1f}%)",
                    font=ctk.CTkFont(family="Segoe UI", size=9),
                    text_color=DarkTheme.TEXT_MUTED
                ).pack(side="left", padx=(2, 0))

                prog = ctk.CTkProgressBar(row, height=5, corner_radius=3, fg_color="#1E293B", progress_color=bar_col)
                prog.pack(fill="x", pady=(2, 0))
                prog.set(max(0.02, pct / 100.0))


# ─────────────────────────────────────────────────────────────────────────────
# 3. MAIN STATISTICS FRAME
# ─────────────────────────────────────────────────────────────────────────────
class StatsFrame(ctk.CTkFrame):
    """Comprehensive Statistics & Sales Reporting View.
    Structured in an executive split dashboard:
    - Top full-width controls bar (100% width): Presets with calendar icons, search, dates, category, min/max price, purple lupita search button, reset, and Excel export.
    - Left column (50%): Compact 4-card KPI summary (2x2 grid) with white titles and larger legible text, Sales Trends Bar Chart, and Breakdown Chart.
    - Right column (50%): Full vertical height Sales Invoices Table with fast pagination, icon-only payment pill, and blue 'Ver factura' action button.
    """

    def __init__(self, parent):
        super().__init__(parent, fg_color=DarkTheme.BG_ROOT, corner_radius=0)

        self.invoices_list: List[Dict[str, Any]] = []
        self.filtered_invoices: List[Dict[str, Any]] = []

        # Sorting state: (col_key, direction: 'asc' | 'desc')
        self.sort_column: str = "timestamp"
        self.sort_direction: str = "desc"

        # Pagination state
        self.current_page: int = 1
        self.page_size: int = 25
        self.total_pages: int = 1

        # Debounce state for live search and price inputs
        self._search_debounce_job: Optional[str] = None
        self.SEARCH_DEBOUNCE_MS: int = 300

        # Preset date filter buttons for active state tracking
        self._preset_btns: Dict[str, ctk.CTkButton] = {}
        self._active_preset: Optional[str] = None

        # Table row selection & keyboard navigation state
        self.rendered_row_data: List[Tuple[ctk.CTkFrame, int]] = []
        self.selected_row_idx: Optional[int] = None

        # Columns: Factura, Fecha y Hora, Cajero, Cliente, Ítems, Método (only icon), Total Factura, Acciones
        # (Efectivo and Cambio columns removed as requested)
        self.columns_def = [
            ("invoice_number", "Factura", 85, "center", True, 0),
            ("timestamp", "Fecha y Hora", 120, "center", True, 0),
            ("cashier", "Cajero", 100, "w", True, 0),
            ("customer", "Cliente", 120, "w", True, 1),
            ("item_count", "Ítems", 55, "center", True, 0),
            ("payment_method", "Método", 45, "center", True, 0),
            ("total", "Total Factura", 110, "center", True, 0),
            ("actions", "Acciones", 115, "center", False, 0),
        ]
        self.header_buttons: Dict[str, ctk.CTkLabel] = {}

        self._build_ui()
        self._setup_keyboard_navigation()
        self.refresh_stats()

    def _build_ui(self) -> None:
        """Build the full-width controls topbar (100% width) and 50-50 split body."""

        # ─────────────────────────────────────────────────────────────────────
        # 1. TOP FULL-WIDTH CONTROLS & FILTER BAR (100% WIDTH)
        # ─────────────────────────────────────────────────────────────────────
        self.controls_bar = ctk.CTkFrame(
            self,
            fg_color=DarkTheme.BG_CARD,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=8
        )
        self.controls_bar.pack(fill="x", padx=10, pady=(4, 6))

        # Row 1 of controls: Search + Touch Keyboard + Magenta Lupita + Desde + Hasta + Categoria
        row_c1 = ctk.CTkFrame(self.controls_bar, fg_color="transparent")
        row_c1.pack(fill="x", padx=10, pady=(8, 4))

        # Search box with touch keypad button [⌨] and magenta lupita [🔍]
        search_box = ctk.CTkFrame(row_c1, fg_color="transparent")
        search_box.pack(side="left", padx=(0, 10))

        self.search_entry = ctk.CTkEntry(
            search_box,
            width=280,
            height=34,
            placeholder_text="Buscar por factura, cliente o cajero...",
            placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=DarkTheme.INPUT_BG,
            border_color="#3B4A66",
            border_width=1.5,
            text_color=DarkTheme.INPUT_TEXT,
            corner_radius=8
        )
        self.search_entry.pack(side="left", padx=(0, 4))
        self.search_entry.bind("<KeyRelease>", self._on_search_key_debounced)
        self.search_entry.bind("<Return>", lambda e: self._on_search_enter())
        self.search_entry.bind("<KP_Enter>", lambda e: self._on_search_enter())

        kb_img = get_ctk_icon("keyboard_white", size=(15, 15)) or get_ctk_icon("keyboard_slate", size=(15, 15))
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
            corner_radius=8,
            cursor="hand2",
            command=self._open_touch_keyboard
        )
        self.touch_kb_btn.pack(side="left", padx=(0, 4))

        search_magenta_img = get_ctk_icon("search_magenta", size=(16, 16))
        self.filter_btn = ctk.CTkButton(
            search_box,
            image=search_magenta_img,
            text="",
            width=36,
            height=34,
            fg_color="#191126",
            border_color="#C026D3",
            border_width=1.5,
            hover_color="#2A163B",
            corner_radius=8,
            cursor="hand2",
            command=self._on_search_enter
        )
        self.filter_btn.pack(side="left")

        # Date Range Entries (Desde & Hasta with rounded containers and interactive calendar modals)
        cal_icon = get_ctk_icon("calendar_regular_white", size=(14, 14))

        ctk.CTkLabel(
            row_c1,
            text="Desde:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(side="left", padx=(4, 4))

        self.d_from_box = ctk.CTkFrame(
            row_c1,
            fg_color=DarkTheme.INPUT_BG,
            border_color="#3B4A66",
            border_width=1.5,
            corner_radius=8,
            height=34,
            width=145
        )
        self.d_from_box.pack(side="left", padx=(0, 10))
        self.d_from_box.pack_propagate(False)

        self.start_date_entry = ctk.CTkEntry(
            self.d_from_box,
            width=95,
            height=28,
            fg_color="transparent",
            border_width=0,
            text_color=DarkTheme.INPUT_TEXT,
            placeholder_text="AAAA-MM-DD",
            placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=0
        )
        self.start_date_entry.pack(side="left", padx=(8, 0), pady=3)
        self.start_date_entry.bind("<KeyRelease>", lambda e: self._on_date_entry_key())
        self.start_date_entry.bind("<Return>", lambda e: self._apply_filters())

        cal_from_btn = ctk.CTkButton(
            self.d_from_box,
            image=cal_icon,
            text="",
            width=28,
            height=28,
            fg_color="transparent",
            hover_color="#1E293B",
            corner_radius=6,
            cursor="hand2",
            command=lambda: self._open_calendar_picker("start")
        )
        cal_from_btn.pack(side="right", padx=(0, 4), pady=3)

        ctk.CTkLabel(
            row_c1,
            text="Hasta:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(side="left", padx=(0, 4))

        self.d_to_box = ctk.CTkFrame(
            row_c1,
            fg_color=DarkTheme.INPUT_BG,
            border_color="#3B4A66",
            border_width=1.5,
            corner_radius=8,
            height=34,
            width=145
        )
        self.d_to_box.pack(side="left", padx=(0, 10))
        self.d_to_box.pack_propagate(False)

        self.end_date_entry = ctk.CTkEntry(
            self.d_to_box,
            width=95,
            height=28,
            fg_color="transparent",
            border_width=0,
            text_color=DarkTheme.INPUT_TEXT,
            placeholder_text="AAAA-MM-DD",
            placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=0
        )
        self.end_date_entry.pack(side="left", padx=(8, 0), pady=3)
        self.end_date_entry.bind("<KeyRelease>", lambda e: self._on_date_entry_key())
        self.end_date_entry.bind("<Return>", lambda e: self._apply_filters())

        cal_to_btn = ctk.CTkButton(
            self.d_to_box,
            image=cal_icon,
            text="",
            width=28,
            height=28,
            fg_color="transparent",
            hover_color="#1E293B",
            corner_radius=6,
            cursor="hand2",
            command=lambda: self._open_calendar_picker("end")
        )
        cal_to_btn.pack(side="right", padx=(0, 4), pady=3)

        # Category Dropdown
        ctk.CTkLabel(
            row_c1,
            text="Categoria:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(side="left", padx=(0, 4))

        self.cat_filter = ctk.CTkComboBox(
            row_c1,
            width=165,
            height=34,
            values=["Todas las categorías"],
            command=lambda v: self._apply_filters(),
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
        self.cat_filter.set("Todas las categorías")
        self.cat_filter.pack(side="left", padx=(0, 10))

        # Minimo and Maximo price filter entries on row 1
        ctk.CTkLabel(
            row_c1,
            text="Minimo:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(side="left", padx=(0, 4))

        self.min_price_entry = ctk.CTkEntry(
            row_c1,
            width=85,
            height=34,
            placeholder_text="$ 0",
            placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
            fg_color=DarkTheme.INPUT_BG,
            border_color="#3B4A66",
            border_width=1.5,
            text_color=DarkTheme.INPUT_TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=6
        )
        self.min_price_entry.pack(side="left", padx=(0, 8))
        self.min_price_entry.bind("<KeyRelease>", self._on_search_key_debounced)
        self.min_price_entry.bind("<Return>", lambda e: self._on_search_enter())
        self.min_price_entry.bind("<KP_Enter>", lambda e: self._on_search_enter())

        ctk.CTkLabel(
            row_c1,
            text="Maximo:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=DarkTheme.TEXT_SECONDARY
        ).pack(side="left", padx=(0, 4))

        self.max_price_entry = ctk.CTkEntry(
            row_c1,
            width=85,
            height=34,
            placeholder_text="$ 0",
            placeholder_text_color=DarkTheme.TEXT_PLACEHOLDER,
            fg_color=DarkTheme.INPUT_BG,
            border_color="#3B4A66",
            border_width=1.5,
            text_color=DarkTheme.INPUT_TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=6
        )
        self.max_price_entry.pack(side="left")
        self.max_price_entry.bind("<KeyRelease>", self._on_search_key_debounced)
        self.max_price_entry.bind("<Return>", lambda e: self._on_search_enter())
        self.max_price_entry.bind("<KP_Enter>", lambda e: self._on_search_enter())

        # Row 2 of controls: Action buttons aligned dynamically with 'Factura' column
        self.row_c2 = ctk.CTkFrame(self.controls_bar, fg_color="transparent")
        self.row_c2.pack(fill="x", padx=10, pady=(2, 8))

        # Dynamic spacer that aligns self.excel_btn directly with 'Factura' table column
        self.c2_left_spacer = ctk.CTkFrame(self.row_c2, fg_color="transparent", width=460, height=36)
        self.c2_left_spacer.pack(side="left")
        self.c2_left_spacer.pack_propagate(False)

        # Exportar Excel: Aligned on the left edge of right column (flush with 'Factura' table column)
        excel_img = get_ctk_icon("excel_white", size=(15, 15))
        self.excel_btn = ctk.CTkButton(
            self.row_c2,
            image=excel_img,
            compound="left",
            text=" Exportar excel (.xlsx)",
            height=36,
            fg_color="#022C22",
            hover_color="#064E3B",
            border_color="#10B981",
            border_width=1.5,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=18,
            cursor="hand2",
            command=self._export_excel
        )
        self.excel_btn.pack(side="left")

        # Far right: Data Reload Button [Two-arrows repeat icon + text "Recargar"]
        repeat_icon = get_ctk_icon("repeat_blue", size=(14, 14)) or get_ctk_icon("repeat_white", size=(14, 14))
        self.reload_btn = ctk.CTkButton(
            self.row_c2,
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
            command=self._on_reload_stats_click
        )
        self.reload_btn.pack(side="right", padx=(6, 6))

        # Far right: Filter Reset Button [Eraser icon + text "Limpiar"]
        eraser_icon = get_ctk_icon("eraser_slate", size=(14, 14)) or get_ctk_icon("eraser_white", size=(14, 14)) or get_ctk_icon("eraser-solid-full", size=(14, 14))
        self.clear_btn = ctk.CTkButton(
            self.row_c2,
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
            command=self._on_clear_filters_click
        )
        self.clear_btn.pack(side="right", padx=(0, 6))
        self.reset_btn = self.clear_btn

        # ─────────────────────────────────────────────────────────────────────
        # 2. MAIN 50/50 SPLIT BODY (LEFT: STATS & CHARTS; RIGHT: TABLE)
        # ─────────────────────────────────────────────────────────────────────
        self.split_container = ctk.CTkFrame(self, fg_color="transparent")
        self.split_container.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        self.split_container.grid_columnconfigure(0, weight=1, minsize=460)
        self.split_container.grid_columnconfigure(1, weight=1, minsize=520)
        self.split_container.grid_rowconfigure(0, weight=1)

        # ── LEFT COLUMN: STATS & CHARTS (50% WIDTH, SCROLLABLE FOR FULL VISIBILITY) ──
        self.left_column = ctk.CTkScrollableFrame(self.split_container, fg_color="transparent")
        self.left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        # 1. Four Compact Executive KPI Cards (2x2 Grid)
        self.kpis_container = ctk.CTkFrame(self.left_column, fg_color="transparent")
        self.kpis_container.pack(fill="x", pady=(0, 4))

        self.kpis_container.grid_columnconfigure(0, weight=1, uniform="kpi_col")
        self.kpis_container.grid_columnconfigure(1, weight=1, uniform="kpi_col")

        # Card 1: Hoy (Emerald header, tinted icon, ticket button)
        self.card_day_val, self.card_day_sub = self._create_compact_kpi_card(
            self.kpis_container, row=0, col=0, title="HOY", icon_name="calendar_day_white",
            text_col="#10B981", badge_bg="#062A1F", def_val="$ 0", def_sub="0 ventas • Prom: $ 0",
            card_bg="#071B14", border_col="#065F46", hover_border="#10B981",
            command=self._preset_today,
            ticket_command=self._on_print_kpi_day,
            ticket_col="#34D399", ticket_bg="#062A1F", ticket_border="#10B981",
            val_size=17
        )
        # Card 2: 7 Días (Sky header, tinted icon, ticket button)
        self.card_week_val, self.card_week_sub = self._create_compact_kpi_card(
            self.kpis_container, row=0, col=1, title="7 DÍAS", icon_name="calendar_week_white",
            text_col="#38BDF8", badge_bg="#081E2E", def_val="$ 0", def_sub="0 ventas • Prom: $ 0",
            card_bg="#08182B", border_col="#0369A1", hover_border="#38BDF8",
            command=self._preset_week,
            ticket_command=self._on_print_kpi_week,
            ticket_col="#38BDF8", ticket_bg="#081E2E", ticket_border="#0EA5E9",
            val_size=17
        )
        # Card 3: Este Mes (Purple header, tinted icon, ticket button)
        self.card_month_val, self.card_month_sub = self._create_compact_kpi_card(
            self.kpis_container, row=1, col=0, title="ESTE MES", icon_name="calendar_regular_white",
            text_col="#C084FC", badge_bg="#25103A", def_val="$ 0", def_sub="0 ventas • Prom: $ 0",
            card_bg="#170C2A", border_col="#6B21A8", hover_border="#A855F7",
            command=self._preset_month,
            ticket_command=self._on_print_kpi_month,
            ticket_col="#C084FC", ticket_bg="#25103A", ticket_border="#8B5CF6",
            val_size=17
        )
        # Card 4: Producto Estrella (Amber header, star icon, NO TICKET BUTTON)
        self.card_top_val, self.card_top_sub = self._create_compact_kpi_card(
            self.kpis_container, row=1, col=1, title="PRODUCTO ESTRELLA", icon_name="star_gold",
            text_col="#FBBF24", badge_bg="#2D1606", def_val="Sin ventas", def_sub="Recaudo: $ 0",
            card_bg="#211406", border_col="#92400E", hover_border="#F59E0B",
            val_size=13
        )

        # Backward compatibility aliases for unit tests
        self.bal_day_tot_lbl = self.card_day_val
        self.bal_week_tot_lbl = self.card_week_val
        self.bal_month_tot_lbl = self.card_month_val
        self.top_day_name_lbl = self.card_top_val
        self.top_week_name_lbl = self.card_top_val
        self.top_month_name_lbl = self.card_top_val

        # KPI Cards registry for inspection & testing
        self.kpi_cards = {
            "today": {
                "val": self.card_day_val,
                "sub": self.card_day_sub,
                "has_ticket_btn": True,
                "ticket_btn": getattr(self.card_day_val.master, "ticket_btn", None)
            },
            "week": {
                "val": self.card_week_val,
                "sub": self.card_week_sub,
                "has_ticket_btn": True,
                "ticket_btn": getattr(self.card_week_val.master, "ticket_btn", None)
            },
            "month": {
                "val": self.card_month_val,
                "sub": self.card_month_sub,
                "has_ticket_btn": True,
                "ticket_btn": getattr(self.card_month_val.master, "ticket_btn", None)
            },
            "top_prod": {
                "val": self.card_top_val,
                "sub": self.card_top_sub,
                "has_ticket_btn": False,
                "ticket_btn": None
            },
        }

        # Horizontal separator 1 between 4 cards and Daily Sales Trends
        self.sep_kpis_chart = ctk.CTkFrame(self.left_column, fg_color="#1E293B", height=1)
        self.sep_kpis_chart.pack(fill="x", padx=4, pady=(6, 8))

        # 2. Daily Sales Trends Bar Chart
        self.sales_chart = SalesTrendsCanvas(self.left_column, height=135)
        self.sales_chart.pack(fill="x", pady=(0, 4))

        # Horizontal separator 2 between Daily Sales Trends and Breakdown
        self.sep_chart_breakdown = ctk.CTkFrame(self.left_column, fg_color="#1E293B", height=1)
        self.sep_chart_breakdown.pack(fill="x", padx=4, pady=(6, 8))

        # 3. Payment Methods and Top Categories Breakdown
        self.breakdown_chart = BreakdownChartWidget(self.left_column)
        self.breakdown_chart.pack(fill="x", pady=(0, 6))

        # Filtered Invoices Summary Strip (Kept unmapped for backwards compatibility with tests)
        self.invoices_summary_strip = ctk.CTkFrame(self.left_column, fg_color="transparent")
        self.invoices_summary_strip.grid_columnconfigure(0, weight=1, uniform="inv_kpi")
        self.invoices_summary_strip.grid_columnconfigure(1, weight=1, uniform="inv_kpi")
        self.invoices_summary_strip.grid_columnconfigure(2, weight=1, uniform="inv_kpi")

        c_fact = ctk.CTkFrame(self.invoices_summary_strip, fg_color="#091326", border_color="#2563EB", border_width=1.5, corner_radius=8, height=36)
        c_fact.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        receipt_icon = get_ctk_icon("receipt_blue", size=(14, 14))
        self.kpi_count_lbl = ctk.CTkLabel(c_fact, image=receipt_icon, compound="left", text=" 0 Facturas", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#60A5FA")
        self.kpi_count_lbl.pack(padx=6, pady=6)

        c_rec = ctk.CTkFrame(self.invoices_summary_strip, fg_color="#062319", border_color="#10B981", border_width=1.5, corner_radius=8, height=36)
        c_rec.grid(row=0, column=1, sticky="ew", padx=2)
        sack_icon = get_ctk_icon("sack_dollar_green", size=(14, 14))
        self.kpi_total_lbl = ctk.CTkLabel(c_rec, image=sack_icon, compound="left", text=" Recaudo: $ 0", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#34D399")
        self.kpi_total_lbl.pack(padx=6, pady=6)

        c_tkt = ctk.CTkFrame(self.invoices_summary_strip, fg_color="#241804", border_color="#F59E0B", border_width=1.5, corner_radius=8, height=36)
        c_tkt.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        coins_icon = get_ctk_icon("coins_gold", size=(14, 14))
        self.kpi_ticket_lbl = ctk.CTkLabel(c_tkt, image=coins_icon, compound="left", text=" Promedio: $ 0", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#FBBF24")
        self.kpi_ticket_lbl.pack(padx=6, pady=6)

        # ── RIGHT COLUMN: SALES HISTORY TABLE (50% WIDTH) ────────────────────
        self.right_column = ctk.CTkFrame(
            self.split_container,
            fg_color=DarkTheme.BG_CARD,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=8
        )
        self.right_column.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        # Table Header Row
        self.header_row = ctk.CTkFrame(
            self.right_column,
            fg_color=DarkTheme.BG_ELEVATED,
            border_color=DarkTheme.BORDER_SUBTLE,
            border_width=1,
            corner_radius=6,
            height=32
        )
        self.header_row.pack(fill="x", padx=6, pady=(6, 4))
        self.header_row.pack_propagate(False)

        for col_idx, (col_key, label, width, anchor, sortable, weight) in enumerate(self.columns_def):
            self.header_row.grid_columnconfigure(col_idx, weight=weight, minsize=width if weight == 0 else 0)
            cell_padx = (8, 4) if anchor == "w" else 2

            lbl = ctk.CTkLabel(
                self.header_row,
                text=f"{label}  ⇅" if sortable else label,
                width=width,
                height=26,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=DarkTheme.TEXT_SECONDARY,
                anchor=anchor,
                cursor="hand2" if sortable else ""
            )
            lbl.grid(row=0, column=col_idx, sticky="nsew", padx=cell_padx)

            if sortable:
                def _bind_hdr(k, w):
                    def _enter(e):
                        if k != self.sort_column:
                            w.configure(text_color=DarkTheme.TEXT_PRIMARY)
                    def _leave(e):
                        if k != self.sort_column:
                            w.configure(text_color=DarkTheme.TEXT_SECONDARY)
                    return _enter, _leave

                h_enter, h_leave = _bind_hdr(col_key, lbl)
                lbl.bind("<Enter>", h_enter)
                lbl.bind("<Leave>", h_leave)
                lbl.bind("<Button-1>", lambda e, k=col_key: self._on_header_click(k))
                self.header_buttons[col_key] = lbl

        # Scrollable Rows Body (Full vertical height on right pane)
        self.rows_scroll = ctk.CTkScrollableFrame(
            self.right_column,
            fg_color="transparent",
            corner_radius=6
        )
        self.rows_scroll.pack(fill="both", expand=True, padx=6, pady=(0, 4))

        # Bottom Pagination Bar
        self.pagination_bar = ctk.CTkFrame(self.right_column, fg_color="transparent", height=32)
        self.pagination_bar.pack(fill="x", padx=10, pady=(2, 6))

        self.prev_page_btn = ctk.CTkButton(
            self.pagination_bar,
            text="◀ Anterior",
            width=75,
            height=26,
            fg_color="#111624",
            border_color="#283347",
            border_width=1,
            hover_color="#1E293B",
            text_color=DarkTheme.TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=5,
            cursor="hand2",
            command=self._prev_page
        )
        self.prev_page_btn.pack(side="left")

        self.page_info_lbl = ctk.CTkLabel(
            self.pagination_bar,
            text="Página 1 de 1 (0 facturas)",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=DarkTheme.TEXT_MUTED
        )
        self.page_info_lbl.pack(side="left", padx=12)

        self.next_page_btn = ctk.CTkButton(
            self.pagination_bar,
            text="Siguiente ▶",
            width=75,
            height=26,
            fg_color="#111624",
            border_color="#283347",
            border_width=1,
            hover_color="#1E293B",
            text_color=DarkTheme.TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=5,
            cursor="hand2",
            command=self._next_page
        )
        self.next_page_btn.pack(side="left")

        self.sort_info_lbl = ctk.CTkLabel(
            self.pagination_bar,
            text="⇅  Ordenado: Fecha (Desc)",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=DarkTheme.TEXT_MUTED
        )
        self.sort_info_lbl.pack(side="right")

        # Sync Excel button alignment directly above Factura column
        self.bind("<Configure>", self._sync_excel_btn_pos, add="+")
        self.after(50, self._sync_excel_btn_pos)
        self.after(150, self._sync_excel_btn_pos)
        self.after(400, self._sync_excel_btn_pos)

    def _sync_excel_btn_pos(self, event=None) -> None:
        """Keep Exportar Excel button pixel-perfectly aligned directly above 'Factura' table column."""
        try:
            if not hasattr(self, "c2_left_spacer") or not hasattr(self, "header_row") or not hasattr(self, "row_c2"):
                return
            h_rx = self.header_row.winfo_rootx()
            r_rx = self.row_c2.winfo_rootx()
            if h_rx > 0 and r_rx > 0:
                needed_w = max(0, h_rx - r_rx)
                curr_w = self.c2_left_spacer.cget("width")
                if abs(curr_w - needed_w) > 1:
                    self.c2_left_spacer.configure(width=needed_w)
        except Exception:
            pass

    def _open_touch_keyboard(self) -> None:
        """Open on-screen keypad to type numeric ID or code into search bar."""
        try:
            from views.pos_frame import TouchKeypadModal
            if TouchKeypadModal:
                init_val = self.search_entry.get().strip()
                TouchKeypadModal(
                    parent=self,
                    title="Búsqueda Rápida",
                    subtitle="Digite código, factura o valor",
                    initial_value=init_val,
                    on_confirm=lambda val: (
                        self.search_entry.delete(0, "end"),
                        self.search_entry.insert(0, val) if val else safe_reset_entry(self.search_entry),
                        self._apply_filters()
                    )
                )
        except Exception:
            pass

    def _on_date_entry_key(self) -> None:
        """Handle typing in date entries and apply filters when complete."""
        s = self.start_date_entry.get().strip()
        e = self.end_date_entry.get().strip()
        if (not s and not e) or len(s) == 10 or len(e) == 10:
            self._apply_filters()

    def _open_calendar_picker(self, target: str) -> None:
        """Open modal calendar date picker for start or end date filter."""
        entry = self.start_date_entry if target == "start" else self.end_date_entry
        curr_val = entry.get().strip()
        title = "Fecha Inicial (Desde)" if target == "start" else "Fecha Final (Hasta)"

        def _on_picked(date_str: str) -> None:
            if date_str:
                entry.delete(0, "end")
                entry.insert(0, date_str)
            else:
                safe_reset_entry(entry)
            self._set_active_preset(None)
            self._apply_filters()

        CalendarPickerModal(
            parent=self,
            title=title,
            initial_date=curr_val if curr_val else None,
            on_select=_on_picked
        )

    def _create_compact_kpi_card(
        self, parent, row: int, col: int, title: str, icon_name: str,
        text_col: str, badge_bg: str, def_val: str, def_sub: str,
        card_bg: str = DarkTheme.BG_CARD, border_col: str = DarkTheme.BORDER_SUBTLE,
        hover_border: Optional[str] = None,
        command: Optional[Callable] = None,
        ticket_command: Optional[Callable] = None,
        ticket_col: str = "#38BDF8",
        ticket_bg: str = "#081E2E",
        ticket_border: str = "#0EA5E9",
        val_size: int = 17
    ) -> Tuple[ctk.CTkLabel, ctk.CTkLabel]:
        """Create a compact balance summary card with themed border, dedicated icon, and enlarged legible text."""
        card = ctk.CTkFrame(
            parent,
            fg_color=card_bg,
            border_color=border_col,
            border_width=1.5,
            corner_radius=8,
            height=72,
            cursor="hand2" if command else "arrow"
        )
        card.grid(row=row, column=col, padx=3, pady=3, sticky="nsew")

        if hover_border:
            card.bind("<Enter>", lambda e: card.configure(border_color=hover_border), add="+")
            card.bind("<Leave>", lambda e: card.configure(border_color=border_col), add="+")

        if command:
            def _click_handler(e=None):
                sound_manager.play_click()
                command()
            card.bind("<Button-1>", _click_handler, add="+")

        top = ctk.CTkFrame(card, fg_color="transparent", cursor="hand2" if command else "arrow")
        top.pack(fill="x", padx=8, pady=(5, 1))
        if command:
            top.bind("<Button-1>", _click_handler, add="+")
        if hover_border:
            top.bind("<Enter>", lambda e: card.configure(border_color=hover_border), add="+")
            top.bind("<Leave>", lambda e: card.configure(border_color=border_col), add="+")

        icon_img = get_tinted_ctk_icon(icon_name, text_col, size=(14, 14)) or get_ctk_icon(icon_name, size=(14, 14))
        badge = ctk.CTkFrame(top, fg_color=badge_bg, border_color=border_col, border_width=1, corner_radius=4, cursor="hand2" if command else "arrow")
        badge.pack(side="left")
        if command:
            badge.bind("<Button-1>", _click_handler, add="+")
        if hover_border:
            badge.bind("<Enter>", lambda e: card.configure(border_color=hover_border), add="+")
            badge.bind("<Leave>", lambda e: card.configure(border_color=border_col), add="+")

        if icon_img:
            i_lbl = ctk.CTkLabel(badge, image=icon_img, text="", cursor="hand2" if command else "arrow")
            i_lbl.pack(side="left", padx=(5, 2), pady=1)
            if command:
                i_lbl.bind("<Button-1>", _click_handler, add="+")
            if hover_border:
                i_lbl.bind("<Enter>", lambda e: card.configure(border_color=hover_border), add="+")
                i_lbl.bind("<Leave>", lambda e: card.configure(border_color=border_col), add="+")

        title_color = text_col
        t_lbl = ctk.CTkLabel(
            badge,
            text=f" {title} " if icon_img else title,
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color=title_color,
            cursor="hand2" if command else "arrow"
        )
        t_lbl.pack(side="left", padx=(0, 4), pady=1)
        if command:
            t_lbl.bind("<Button-1>", _click_handler, add="+")
        if hover_border:
            t_lbl.bind("<Enter>", lambda e: card.configure(border_color=hover_border), add="+")
            t_lbl.bind("<Leave>", lambda e: card.configure(border_color=border_col), add="+")

        # Ticket Button on top-right (Only when ticket_command is provided)
        btn_tkt = None
        if ticket_command:
            tkt_img = get_tinted_ctk_icon("ticket_white", ticket_col, size=(13, 13)) or get_ctk_icon("ticket_white", size=(13, 13))
            btn_tkt = ctk.CTkButton(
                top,
                image=tkt_img,
                text="",
                width=28,
                height=22,
                fg_color=ticket_bg,
                border_color=ticket_border,
                border_width=1,
                hover_color=hover_border or "#1E293B",
                corner_radius=5,
                cursor="hand2",
                command=ticket_command
            )
            btn_tkt.pack(side="right")
        card.ticket_btn = btn_tkt

        val_lbl = ctk.CTkLabel(
            card,
            text=def_val,
            font=ctk.CTkFont(family="Segoe UI", size=val_size, weight="bold"),
            text_color=text_col,
            cursor="hand2" if command else "arrow"
        )
        val_lbl.pack(anchor="w", padx=8, pady=(1, 0))
        if command:
            val_lbl.bind("<Button-1>", _click_handler, add="+")
        if hover_border:
            val_lbl.bind("<Enter>", lambda e: card.configure(border_color=hover_border), add="+")
            val_lbl.bind("<Leave>", lambda e: card.configure(border_color=border_col), add="+")

        # Larger legible font for sales count and average as requested
        sub_lbl = ctk.CTkLabel(
            card,
            text=def_sub,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#CBD5E1",
            cursor="hand2" if command else "arrow"
        )
        sub_lbl.pack(anchor="w", padx=8, pady=(0, 4))
        if command:
            sub_lbl.bind("<Button-1>", _click_handler, add="+")
        if hover_border:
            sub_lbl.bind("<Enter>", lambda e: card.configure(border_color=hover_border), add="+")
            sub_lbl.bind("<Leave>", lambda e: card.configure(border_color=border_col), add="+")

        return val_lbl, sub_lbl

    # ── Ticket Reporting Callbacks ───────────────────────────────────────────
    def _on_print_kpi_day(self) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        CalendarPickerModal(
            parent=self,
            title="Imprimir Ventas de un Día",
            initial_date=today_str,
            mode="day",
            on_select=lambda picked_date: self._generate_and_show_sales_report_ticket(
                picked_date, picked_date, "REPORTE DIARIO DE VENTAS"
            ) if picked_date else None
        )

    def _on_print_kpi_week(self) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        CalendarPickerModal(
            parent=self,
            title="Imprimir Ventas de la Semana",
            initial_date=today_str,
            mode="week",
            on_select=lambda start_date, end_date: self._generate_and_show_sales_report_ticket(
                start_date, end_date, "REPORTE SEMANAL DE VENTAS"
            ) if start_date and end_date else None
        )

    def _on_print_kpi_month(self) -> None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        CalendarPickerModal(
            parent=self,
            title="Imprimir Ventas del Mes",
            initial_date=today_str,
            mode="month",
            on_select=lambda start_date, end_date: self._generate_and_show_sales_report_ticket(
                start_date, end_date, "REPORTE MENSUAL DE VENTAS"
            ) if start_date and end_date else None
        )

    def _generate_and_show_sales_report_ticket(self, start_date: str, end_date: str, report_title: str) -> None:
        """Query DB for sales in selected range, format a clean thermal 40-char ASCII report ticket,
        and open TicketPreviewModal for preview and instant thermal printing."""
        try:
            with get_db_connection() as conn:
                summary = SaleModel.get_sales_summary(conn, start_date=start_date, end_date=end_date)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT s.payment_method, COUNT(s.id) as cnt, SUM(s.total) as tot
                    FROM sales s
                    WHERE date(s.timestamp) >= date(?) AND date(s.timestamp) <= date(?)
                      AND COALESCE(s.status, 'COMPLETADA') != 'ANULADA'
                    GROUP BY s.payment_method
                    ORDER BY tot DESC
                """, (start_date, end_date))
                pm_rows = cursor.fetchall()

                cursor.execute("""
                    SELECT COALESCE(c.name, 'Sin Categoría') as cat_name, SUM(si.total_price) as tot
                    FROM sale_items si
                    JOIN sales s ON si.sale_id = s.id
                    JOIN products p ON si.product_id = p.id
                    LEFT JOIN categories c ON p.category_id = c.id
                    WHERE date(s.timestamp) >= date(?) AND date(s.timestamp) <= date(?)
                      AND COALESCE(s.status, 'COMPLETADA') != 'ANULADA'
                    GROUP BY c.id
                    ORDER BY tot DESC
                    LIMIT 5
                """, (start_date, end_date))
                cat_rows = cursor.fetchall()
        except Exception as e:
            messagebox.showerror("Error", f"Error consultando datos para el reporte: {e}", parent=self)
            return

        total_sold = summary.get("total_sold", 0.0)
        sales_count = summary.get("sales_count", 0)
        avg_ticket = summary.get("avg_ticket", 0.0)
        best_product = summary.get("best_product", "Sin ventas")

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Build 40-character ASCII receipt
        from hardware.ticket_printer import box_line, center_line, left_right_line
        border = "+" + ("-" * 38) + "+"
        div = "|" + ("-" * 38) + "|"

        lines = [
            border,
            box_line(center_line("XL BURGUER", 38)),
            box_line(center_line("COMIDAS RAPIDAS & HAMBURGUESAS", 38)),
            border,
            box_line(center_line(report_title, 38)),
            div,
            box_line(left_right_line("DESDE:", start_date, 38)),
            box_line(left_right_line("HASTA:", end_date, 38)),
            box_line(left_right_line("EMISION:", now_str, 38)),
            border,
            box_line(center_line("RESUMEN DE VENTAS", 38)),
            div,
            box_line(left_right_line("FACTURAS EMITIDAS:", str(sales_count), 38)),
            box_line(left_right_line("TOTAL RECAUDADO:", f"${total_sold:,.0f}".replace(",", "."), 38)),
            box_line(left_right_line("TICKET PROMEDIO:", f"${avg_ticket:,.0f}".replace(",", "."), 38)),
            border,
            box_line(center_line("DESGLOSE POR METODO DE PAGO", 38)),
            div,
        ]

        if not pm_rows:
            lines.append(box_line(center_line("Sin ventas en el periodo", 38)))
        else:
            for pm in pm_rows:
                m_name = (pm["payment_method"] or "EFECTIVO").upper()
                m_tot = float(pm["tot"] or 0.0)
                m_cnt = int(pm["cnt"] or 0)
                lines.append(box_line(left_right_line(f"{m_name} ({m_cnt}):", f"${m_tot:,.0f}".replace(",", "."), 38)))

        lines.append(border)
        lines.append(box_line(center_line("TOP CATEGORIAS", 38)))
        lines.append(div)

        if not cat_rows:
            lines.append(box_line(center_line("Sin datos de categorias", 38)))
        else:
            for cat in cat_rows:
                c_name = str(cat["cat_name"] or "General")[:18].upper()
                c_tot = float(cat["tot"] or 0.0)
                lines.append(box_line(left_right_line(c_name, f"${c_tot:,.0f}".replace(",", "."), 38)))

        lines.append(border)
        lines.append(box_line(center_line("PRODUCTO ESTRELLA", 38)))
        lines.append(div)
        bp_clean = str(best_product)[:36].upper()
        lines.append(box_line(center_line(bp_clean, 38)))
        lines.append(border)
        lines.append(box_line(center_line("*** FIN DEL REPORTE ***", 38)))
        lines.append(border)

        ticket_text = "\n".join(lines)
        TicketPreviewModal(parent=self, ticket_text=ticket_text)

    # ── Presets ──────────────────────────────────────────────────────────────
    def _set_active_preset(self, key: Optional[str]) -> None:
        self._active_preset = key
        for k, btn in self._preset_btns.items():
            try:
                if k == key:
                    btn.configure(
                        fg_color="#1E3A8A",
                        border_color="#3B82F6",
                        border_width=1.5,
                        text_color="#FFFFFF",
                    )
                else:
                    btn.configure(
                        fg_color=DarkTheme.BG_ELEVATED,
                        border_color=DarkTheme.BORDER_SUBTLE,
                        border_width=1.2,
                        text_color=DarkTheme.TEXT_SECONDARY,
                    )
            except Exception:
                pass

    def _preset_today(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        self.start_date_entry.delete(0, "end")
        self.start_date_entry.insert(0, today)
        self.end_date_entry.delete(0, "end")
        self.end_date_entry.insert(0, today)
        self._set_active_preset("hoy")
        self._apply_filters()

    def _preset_week(self) -> None:
        end = datetime.now()
        start = end - timedelta(days=6)
        self.start_date_entry.delete(0, "end")
        self.start_date_entry.insert(0, start.strftime("%Y-%m-%d"))
        self.end_date_entry.delete(0, "end")
        self.end_date_entry.insert(0, end.strftime("%Y-%m-%d"))
        self._set_active_preset("7dias")
        self._apply_filters()

    def _preset_month(self) -> None:
        now = datetime.now()
        start = now.replace(day=1)
        self.start_date_entry.delete(0, "end")
        self.start_date_entry.insert(0, start.strftime("%Y-%m-%d"))
        self.end_date_entry.delete(0, "end")
        self.end_date_entry.insert(0, now.strftime("%Y-%m-%d"))
        self._set_active_preset("mes")
        self._apply_filters()

    def _preset_all(self) -> None:
        safe_reset_entry(self.start_date_entry)
        safe_reset_entry(self.end_date_entry)
        self._set_active_preset("all")
        self._apply_filters()

    # ── Filtering & Pagination ───────────────────────────────────────────────
    def _cancel_search_debounce(self) -> None:
        """Safely cancel any pending debounced search timer."""
        if self._search_debounce_job is not None:
            try:
                self.after_cancel(self._search_debounce_job)
            except Exception:
                pass
            self._search_debounce_job = None

    def _on_search_key_debounced(self, event=None) -> None:
        """Debounce search queries when typing in search or price filters (300ms).
        Suppresses rapid sequential requests until the user finishes typing.
        """
        if event and event.keysym in (
            "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
            "Caps_Lock", "Tab", "ISO_Left_Tab", "Up", "Down", "Left", "Right",
            "Home", "End", "Prior", "Next", "Escape", "Return", "KP_Enter"
        ):
            return

        self._cancel_search_debounce()

        # If all search/price entries are empty, update immediately for responsive feel
        q = self.search_entry.get().strip() if hasattr(self, "search_entry") else ""
        min_p = self.min_price_entry.get().strip() if hasattr(self, "min_price_entry") else ""
        max_p = self.max_price_entry.get().strip() if hasattr(self, "max_price_entry") else ""
        if not q and not min_p and not max_p:
            self._on_search_key()
            return

        self._search_debounce_job = self.after(self.SEARCH_DEBOUNCE_MS, self._execute_debounced_search)

    def _execute_debounced_search(self) -> None:
        self._search_debounce_job = None
        self._on_search_key()

    def _on_search_enter(self) -> None:
        """Immediate search execution upon pressing Enter or clicking Search button."""
        self._cancel_search_debounce()
        self._apply_filters()

    def _on_search_key(self) -> None:
        self.current_page = 1
        self._filter_and_sort_invoices()

    def _clear_search(self) -> None:
        self._cancel_search_debounce()
        safe_reset_entry(self.search_entry)
        self.current_page = 1
        self._filter_and_sort_invoices()

    def _apply_filters(self) -> None:
        self._cancel_search_debounce()
        self._fetch_invoices()
        self.current_page = 1
        self._filter_and_sort_invoices()

    def _on_clear_filters_click(self) -> None:
        """Clear all search inputs, date bounds, and category filters."""
        self._cancel_search_debounce()
        try:
            sound_manager.play_click()
        except Exception:
            pass
        self._reset_filters()

    def _on_reload_stats_click(self) -> None:
        """Reload fresh analytics, charts, and sales from the database."""
        self._cancel_search_debounce()
        try:
            sound_manager.play_click()
        except Exception:
            pass
        self.current_page = 1
        self.refresh_stats()

    def _reset_filters(self) -> None:
        self._cancel_search_debounce()
        safe_reset_entry(self.search_entry)
        safe_reset_entry(self.start_date_entry)
        safe_reset_entry(self.end_date_entry)
        self.cat_filter.set("Todas las categorías")
        safe_reset_entry(self.min_price_entry)
        safe_reset_entry(self.max_price_entry)
        self._set_active_preset(None)
        self._apply_filters()

    # ── Keyboard Navigation & Focus Helpers ─────────────────────────────────
    def _focus_search_entry(self) -> None:
        try:
            self.search_entry.focus_set()
            self.search_entry.select_range(0, "end")
        except Exception:
            pass

    def _focus_start_date(self) -> None:
        try:
            self.start_date_entry.focus_set()
            self.start_date_entry.select_range(0, "end")
        except Exception:
            pass

    def _focus_end_date(self) -> None:
        try:
            self.end_date_entry.focus_set()
            self.end_date_entry.select_range(0, "end")
        except Exception:
            pass

    def _focus_cat_filter(self) -> None:
        try:
            if hasattr(self.cat_filter, "_entry") and self.cat_filter._entry:
                self.cat_filter._entry.focus_set()
            else:
                self.cat_filter.focus_set()
        except Exception:
            pass

    def _focus_min_price(self) -> None:
        try:
            self.min_price_entry.focus_set()
            self.min_price_entry.select_range(0, "end")
        except Exception:
            pass

    def _focus_max_price(self) -> None:
        try:
            self.max_price_entry.focus_set()
            self.max_price_entry.select_range(0, "end")
        except Exception:
            pass

    def _focus_clear_btn(self) -> None:
        try:
            self.clear_btn.focus_set()
        except Exception:
            pass

    def _focus_reload_btn(self) -> None:
        try:
            self.reload_btn.focus_set()
        except Exception:
            pass

    def _focus_excel_btn(self) -> None:
        try:
            self.excel_btn.focus_set()
        except Exception:
            pass

    def _focus_prev_btn(self) -> None:
        try:
            self.prev_page_btn.focus_set()
        except Exception:
            pass

    def _focus_next_btn(self) -> None:
        try:
            self.next_page_btn.focus_set()
        except Exception:
            pass

    def _select_table_row(self, idx: int) -> None:
        """Select a table row by index and apply high-contrast selection highlight."""
        if not self.rendered_row_data:
            return
        idx = max(0, min(idx, len(self.rendered_row_data) - 1))
        # Clear previous selection
        if self.selected_row_idx is not None and 0 <= self.selected_row_idx < len(self.rendered_row_data):
            prev_rf, _ = self.rendered_row_data[self.selected_row_idx]
            prev_bg = DarkTheme.BG_CARD if (self.selected_row_idx % 2 == 0) else DarkTheme.BG_ROW_ALT
            try:
                prev_rf.configure(fg_color=prev_bg, border_color=DarkTheme.BORDER_SUBTLE)
            except Exception:
                pass

        self.selected_row_idx = idx
        cur_rf, inv_id = self.rendered_row_data[idx]
        try:
            cur_rf.configure(fg_color="#1E293B", border_color="#38BDF8")
            cur_rf.focus_set()
        except Exception:
            pass

    def _on_table_key_down(self, event=None):
        if not self.rendered_row_data:
            return "break"
        if self.selected_row_idx is None:
            self._select_table_row(0)
        elif self.selected_row_idx < len(self.rendered_row_data) - 1:
            self._select_table_row(self.selected_row_idx + 1)
        return "break"

    def _on_table_key_up(self, event=None):
        if not self.rendered_row_data:
            return "break"
        if self.selected_row_idx is None or self.selected_row_idx <= 0:
            self.selected_row_idx = None
            self._focus_search_entry()
        else:
            self._select_table_row(self.selected_row_idx - 1)
        return "break"

    def _on_table_enter_space(self, event=None):
        if self.selected_row_idx is not None and 0 <= self.selected_row_idx < len(self.rendered_row_data):
            _, inv_id = self.rendered_row_data[self.selected_row_idx]
            self._reprint_ticket(inv_id)
            return "break"
        return None

    def _setup_keyboard_navigation(self) -> None:
        """Bind Tab, Shift-Tab, Enter, Space and shortcuts for seamless keyboard operation."""
        # 1. Search Entry
        self.search_entry.bind("<Tab>", lambda e: (self._focus_start_date(), "break")[1])
        self.search_entry.bind("<Shift-Tab>", lambda e: (self._focus_next_btn(), "break")[1])
        self.search_entry.bind("<ISO_Left_Tab>", lambda e: (self._focus_next_btn(), "break")[1])
        self.search_entry.bind("<Down>", lambda e: (self._select_table_row(0), "break")[1])
        self.search_entry.bind("<FocusIn>", lambda e: self.search_entry.configure(border_color="#3B82F6"), add="+")
        self.search_entry.bind("<FocusOut>", lambda e: self.search_entry.configure(border_color="#3B4A66"), add="+")

        # 2. Start Date Entry (Desde)
        self.start_date_entry.bind("<Tab>", lambda e: (self._focus_end_date(), "break")[1])
        self.start_date_entry.bind("<Shift-Tab>", lambda e: (self._focus_search_entry(), "break")[1])
        self.start_date_entry.bind("<ISO_Left_Tab>", lambda e: (self._focus_search_entry(), "break")[1])
        self.start_date_entry.bind("<Down>", lambda e: (self._select_table_row(0), "break")[1])
        self.start_date_entry.bind("<FocusIn>", lambda e: getattr(self, "d_from_box", None) and self.d_from_box.configure(border_color="#3B82F6"), add="+")
        self.start_date_entry.bind("<FocusOut>", lambda e: getattr(self, "d_from_box", None) and self.d_from_box.configure(border_color="#3B4A66"), add="+")

        # 3. End Date Entry (Hasta)
        self.end_date_entry.bind("<Tab>", lambda e: (self._focus_cat_filter(), "break")[1])
        self.end_date_entry.bind("<Shift-Tab>", lambda e: (self._focus_start_date(), "break")[1])
        self.end_date_entry.bind("<ISO_Left_Tab>", lambda e: (self._focus_start_date(), "break")[1])
        self.end_date_entry.bind("<Down>", lambda e: (self._select_table_row(0), "break")[1])
        self.end_date_entry.bind("<FocusIn>", lambda e: getattr(self, "d_to_box", None) and self.d_to_box.configure(border_color="#3B82F6"), add="+")
        self.end_date_entry.bind("<FocusOut>", lambda e: getattr(self, "d_to_box", None) and self.d_to_box.configure(border_color="#3B4A66"), add="+")

        # 4. Category Dropdown
        def _open_cat_menu(e=None):
            try:
                self.cat_filter._open_dropdown_menu()
            except Exception:
                pass
            return "break"

        def _on_cat_tab(e=None):
            self._focus_min_price()
            return "break"

        def _on_cat_shift_tab(e=None):
            self._focus_end_date()
            return "break"

        self.cat_filter.bind("<Tab>", _on_cat_tab)
        self.cat_filter.bind("<Shift-Tab>", _on_cat_shift_tab)
        self.cat_filter.bind("<ISO_Left_Tab>", _on_cat_shift_tab)
        self.cat_filter.bind("<Return>", _open_cat_menu)
        self.cat_filter.bind("<KP_Enter>", _open_cat_menu)
        self.cat_filter.bind("<space>", _open_cat_menu)
        self.cat_filter.bind("<Down>", _open_cat_menu)
        self.cat_filter.bind("<FocusIn>", lambda e: self.cat_filter.configure(border_color="#3B82F6"), add="+")
        self.cat_filter.bind("<FocusOut>", lambda e: self.cat_filter.configure(border_color="#3B4A66"), add="+")

        if hasattr(self.cat_filter, "_entry") and self.cat_filter._entry:
            self.cat_filter._entry.bind("<Tab>", _on_cat_tab)
            self.cat_filter._entry.bind("<Shift-Tab>", _on_cat_shift_tab)
            self.cat_filter._entry.bind("<ISO_Left_Tab>", _on_cat_shift_tab)
            self.cat_filter._entry.bind("<Return>", _open_cat_menu)
            self.cat_filter._entry.bind("<KP_Enter>", _open_cat_menu)
            self.cat_filter._entry.bind("<space>", _open_cat_menu)
            self.cat_filter._entry.bind("<Down>", _open_cat_menu)

        # 5. Min Price Entry
        self.min_price_entry.bind("<Tab>", lambda e: (self._focus_max_price(), "break")[1])
        self.min_price_entry.bind("<Shift-Tab>", lambda e: (self._focus_cat_filter(), "break")[1])
        self.min_price_entry.bind("<ISO_Left_Tab>", lambda e: (self._focus_cat_filter(), "break")[1])
        self.min_price_entry.bind("<Down>", lambda e: (self._select_table_row(0), "break")[1])
        self.min_price_entry.bind("<Return>", lambda e: (self._apply_filters(), "break")[1])
        self.min_price_entry.bind("<KP_Enter>", lambda e: (self._apply_filters(), "break")[1])
        self.min_price_entry.bind("<FocusIn>", lambda e: self.min_price_entry.configure(border_color="#3B82F6"), add="+")
        self.min_price_entry.bind("<FocusOut>", lambda e: self.min_price_entry.configure(border_color="#3B4A66"), add="+")

        # 6. Max Price Entry
        self.max_price_entry.bind("<Tab>", lambda e: (self._focus_clear_btn(), "break")[1])
        self.max_price_entry.bind("<Shift-Tab>", lambda e: (self._focus_min_price(), "break")[1])
        self.max_price_entry.bind("<ISO_Left_Tab>", lambda e: (self._focus_min_price(), "break")[1])
        self.max_price_entry.bind("<Down>", lambda e: (self._select_table_row(0), "break")[1])
        self.max_price_entry.bind("<Return>", lambda e: (self._apply_filters(), "break")[1])
        self.max_price_entry.bind("<KP_Enter>", lambda e: (self._apply_filters(), "break")[1])
        self.max_price_entry.bind("<FocusIn>", lambda e: self.max_price_entry.configure(border_color="#3B82F6"), add="+")
        self.max_price_entry.bind("<FocusOut>", lambda e: self.max_price_entry.configure(border_color="#3B4A66"), add="+")

        # 7. Clear / Limpiar Button
        self.clear_btn.bind("<Tab>", lambda e: (self._focus_reload_btn(), "break")[1])
        self.clear_btn.bind("<Shift-Tab>", lambda e: (self._focus_max_price(), "break")[1])
        self.clear_btn.bind("<ISO_Left_Tab>", lambda e: (self._focus_max_price(), "break")[1])
        self.clear_btn.bind("<Down>", lambda e: (self._select_table_row(0), "break")[1])
        self.clear_btn.bind("<Return>", lambda e: (self._on_clear_filters_click(), "break")[1])
        self.clear_btn.bind("<KP_Enter>", lambda e: (self._on_clear_filters_click(), "break")[1])
        self.clear_btn.bind("<space>", lambda e: (self._on_clear_filters_click(), "break")[1])
        self.clear_btn.bind("<FocusIn>", lambda e: self.clear_btn.configure(border_color="#38BDF8"), add="+")
        self.clear_btn.bind("<FocusOut>", lambda e: self.clear_btn.configure(border_color="#475569"), add="+")

        # 8. Reload Button
        self.reload_btn.bind("<Tab>", lambda e: (self._focus_excel_btn(), "break")[1])
        self.reload_btn.bind("<Shift-Tab>", lambda e: (self._focus_clear_btn(), "break")[1])
        self.reload_btn.bind("<ISO_Left_Tab>", lambda e: (self._focus_clear_btn(), "break")[1])
        self.reload_btn.bind("<Down>", lambda e: (self._select_table_row(0), "break")[1])
        self.reload_btn.bind("<Return>", lambda e: (self._on_reload_stats_click(), "break")[1])
        self.reload_btn.bind("<KP_Enter>", lambda e: (self._on_reload_stats_click(), "break")[1])
        self.reload_btn.bind("<space>", lambda e: (self._on_reload_stats_click(), "break")[1])
        self.reload_btn.bind("<FocusIn>", lambda e: self.reload_btn.configure(border_color="#60A5FA"), add="+")
        self.reload_btn.bind("<FocusOut>", lambda e: self.reload_btn.configure(border_color="#2563EB"), add="+")

        # 9. Excel Export Button
        self.excel_btn.bind("<Tab>", lambda e: (self._focus_prev_btn(), "break")[1])
        self.excel_btn.bind("<Shift-Tab>", lambda e: (self._focus_reload_btn(), "break")[1])
        self.excel_btn.bind("<ISO_Left_Tab>", lambda e: (self._focus_reload_btn(), "break")[1])
        self.excel_btn.bind("<Down>", lambda e: (self._select_table_row(0), "break")[1])
        self.excel_btn.bind("<Return>", lambda e: (self._export_excel(), "break")[1])
        self.excel_btn.bind("<KP_Enter>", lambda e: (self._export_excel(), "break")[1])
        self.excel_btn.bind("<space>", lambda e: (self._export_excel(), "break")[1])
        self.excel_btn.bind("<FocusIn>", lambda e: self.excel_btn.configure(border_color="#34D399"), add="+")
        self.excel_btn.bind("<FocusOut>", lambda e: self.excel_btn.configure(border_color="#10B981"), add="+")

        # 10. Pagination Bar Buttons
        self.prev_page_btn.bind("<Tab>", lambda e: (self._focus_next_btn(), "break")[1])
        self.prev_page_btn.bind("<Shift-Tab>", lambda e: (self._focus_excel_btn(), "break")[1])
        self.prev_page_btn.bind("<ISO_Left_Tab>", lambda e: (self._focus_excel_btn(), "break")[1])
        self.prev_page_btn.bind("<Up>", lambda e: (self._select_table_row(0), "break")[1])
        self.prev_page_btn.bind("<Return>", lambda e: (self._prev_page(), "break")[1])
        self.prev_page_btn.bind("<KP_Enter>", lambda e: (self._prev_page(), "break")[1])
        self.prev_page_btn.bind("<space>", lambda e: (self._prev_page(), "break")[1])
        self.prev_page_btn.bind("<FocusIn>", lambda e: self.prev_page_btn.configure(border_color="#38BDF8"), add="+")
        self.prev_page_btn.bind("<FocusOut>", lambda e: self.prev_page_btn.configure(border_color="#283347"), add="+")

        self.next_page_btn.bind("<Tab>", lambda e: (self._focus_search_entry(), "break")[1])
        self.next_page_btn.bind("<Shift-Tab>", lambda e: (self._focus_prev_btn(), "break")[1])
        self.next_page_btn.bind("<ISO_Left_Tab>", lambda e: (self._focus_prev_btn(), "break")[1])
        self.next_page_btn.bind("<Up>", lambda e: (self._select_table_row(0), "break")[1])
        self.next_page_btn.bind("<Return>", lambda e: (self._next_page(), "break")[1])
        self.next_page_btn.bind("<KP_Enter>", lambda e: (self._next_page(), "break")[1])
        self.next_page_btn.bind("<space>", lambda e: (self._next_page(), "break")[1])
        self.next_page_btn.bind("<FocusIn>", lambda e: self.next_page_btn.configure(border_color="#38BDF8"), add="+")
        self.next_page_btn.bind("<FocusOut>", lambda e: self.next_page_btn.configure(border_color="#283347"), add="+")

        # 11. Global Shortcuts bound across main frame and inputs
        all_inputs = [
            self, self.search_entry, self.start_date_entry, self.end_date_entry,
            self.min_price_entry, self.max_price_entry, self.clear_btn, self.reload_btn,
            self.excel_btn, self.prev_page_btn, self.next_page_btn
        ]
        for w in all_inputs:
            w.bind("<F5>", lambda e: (self._on_reload_stats_click(), "break")[1])
            w.bind("<Control-f>", lambda e: (self._focus_search_entry(), "break")[1])
            w.bind("<Control-F>", lambda e: (self._focus_search_entry(), "break")[1])
            w.bind("<Control-l>", lambda e: (self._on_clear_filters_click(), "break")[1])
            w.bind("<Control-L>", lambda e: (self._on_clear_filters_click(), "break")[1])
            w.bind("<Control-e>", lambda e: (self._export_excel(), "break")[1])
            w.bind("<Control-E>", lambda e: (self._export_excel(), "break")[1])
            w.bind("<Escape>", lambda e: (self._on_clear_filters_click(), "break")[1])

    def _prev_page(self) -> None:
        if self.current_page > 1:
            self.current_page -= 1
            self._render_table_rows()
            self._update_kpi_summary()

    def _next_page(self) -> None:
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._render_table_rows()
            self._update_kpi_summary()

    # ── Data Fetching ────────────────────────────────────────────────────────
    def refresh_stats(self) -> None:
        """Fetch fresh analytics KPIs, trends, categories, and payment methods."""
        with get_db_connection() as conn:
            # 1. Executive Summary
            analytics = SaleModel.get_periodic_analytics(conn)

            cur = conn.cursor()

            # 2. Daily Trends for last 7 days
            daily_trends = []
            now = datetime.now()
            for i in range(6, -1, -1):
                day_dt = now - timedelta(days=i)
                day_str = day_dt.strftime("%Y-%m-%d")
                day_lbl = day_dt.strftime("%d %b")
                day_sub = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"][day_dt.weekday()]
                cur.execute(
                    """
                    SELECT COALESCE(SUM(total), 0) as tot, COUNT(*) as cnt
                    FROM sales
                    WHERE date(timestamp) = date(?)
                    """,
                    (day_str,)
                )
                r = cur.fetchone()
                tot_amt = float(r["tot"]) if r else 0.0
                cnt_val = int(r["cnt"]) if r else 0
                daily_trends.append({
                    "label": day_lbl,
                    "sub": day_sub,
                    "amount": tot_amt,
                    "count": cnt_val
                })
            cur.execute(
                """
                SELECT payment_method, COALESCE(SUM(total), 0) as tot, COUNT(*) as cnt
                FROM sales
                GROUP BY payment_method
                ORDER BY tot DESC
                """
            )
            pm_breakdown = [dict(r) for r in cur.fetchall()]

            # 4. Top Categories
            cur.execute(
                """
                SELECT c.name as category_name, COALESCE(SUM(si.total_price), 0) as tot, COUNT(si.id) as cnt
                FROM sale_items si
                JOIN products p ON si.product_id = p.id
                JOIN categories c ON p.category_id = c.id
                GROUP BY c.id
                ORDER BY tot DESC
                LIMIT 5
                """
            )
            top_categories = [dict(r) for r in cur.fetchall()]

            # 5. Populate Categories dropdown
            cur.execute("SELECT name FROM categories ORDER BY name ASC")
            cat_rows = cur.fetchall()
            cat_list = ["Todas las categorías"] + [r["name"] for r in cat_rows]
            self.cat_filter.configure(values=cat_list)

        # Update 4 KPI Cards
        # Card 1: Hoy
        d = analytics["daily"]
        self.card_day_val.configure(text=format_currency_short(d["total_sold"]))
        self.card_day_sub.configure(text=f"{d['sales_count']} ventas • Prom: {format_currency_short(d['avg_ticket'])}")

        # Card 2: 7 Días
        w = analytics["weekly"]
        self.card_week_val.configure(text=format_currency_short(w["total_sold"]))
        self.card_week_sub.configure(text=f"{w['sales_count']} ventas • Prom: {format_currency_short(w['avg_ticket'])}")

        # Card 3: Este Mes
        m = analytics["monthly"]
        self.card_month_val.configure(text=format_currency_short(m["total_sold"]))
        self.card_month_sub.configure(text=f"{m['sales_count']} ventas • Prom: {format_currency_short(m['avg_ticket'])}")

        # Card 4: Top Product (Producto Estrella)
        # Prioritize current active period with sales: Hoy -> 7 Días -> Este Mes
        top_name = None
        top_rev = 0.0

        for candidate in (d, w, m):
            cand_name = candidate.get("top_product_name")
            cand_rev = float(candidate.get("top_product_revenue", 0.0) or 0.0)
            if cand_name and cand_rev > 0:
                top_name = cand_name
                top_rev = cand_rev
                break

        # If no sales registered in Day, Week, or Month, look up all-time top product in DB
        if not top_name:
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT p.name as product_name, COALESCE(SUM(si.total_price), 0) as top_revenue
                    FROM sale_items si
                    JOIN products p ON si.product_id = p.id
                    GROUP BY p.id
                    HAVING top_revenue > 0
                    ORDER BY top_revenue DESC
                    LIMIT 1
                """)
                all_time_top = cur.fetchone()
                if all_time_top and all_time_top["top_revenue"] > 0:
                    top_name = all_time_top["product_name"]
                    top_rev = float(all_time_top["top_revenue"])
                else:
                    top_name = "Sin ventas"
                    top_rev = 0.0

        self.card_top_val.configure(text=top_name if len(top_name) <= 24 else f"{top_name[:22]}...")
        self.card_top_sub.configure(text=f"Recaudo: {format_currency_short(top_rev)}")

        # Update Visual Charts
        self.sales_chart.set_data(daily_trends)
        self.breakdown_chart.set_data(pm_breakdown, top_categories)

        # Initial fetch of invoices
        self._fetch_invoices()
        self._filter_and_sort_invoices()
        self._update_kpi_summary()

    def _fetch_invoices(self) -> None:
        """Fetch all sales within the date boundaries."""
        start_raw = self.start_date_entry.get().strip()
        end_raw = self.end_date_entry.get().strip()

        start_d = start_raw if re.match(r"^\d{4}-\d{2}-\d{2}$", start_raw) else "1970-01-01"
        end_d = end_raw if re.match(r"^\d{4}-\d{2}-\d{2}$", end_raw) else "2099-12-31"

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT 
                    s.id,
                    s.invoice_number,
                    s.timestamp,
                    s.total,
                    s.cash_received,
                    s.cash_change,
                    s.payment_method,
                    COALESCE(u.full_name, 'Diego') AS cashier,
                    COALESCE(c.first_name || ' ' || c.last_name, 'Consumidor Final') AS customer,
                    COUNT(si.id) AS item_count,
                    GROUP_CONCAT(DISTINCT cat.name) AS category_names
                FROM sales s
                LEFT JOIN users u ON s.user_id = u.id
                LEFT JOIN customers c ON s.customer_id = c.id
                LEFT JOIN sale_items si ON si.sale_id = s.id
                LEFT JOIN products p ON si.product_id = p.id
                LEFT JOIN categories cat ON p.category_id = cat.id
                WHERE date(s.timestamp) >= date(?) AND date(s.timestamp) <= date(?)
                GROUP BY s.id
                HAVING COUNT(si.id) > 0
                ORDER BY s.timestamp DESC
                """,
                (start_d, end_d)
            )
            rows = cur.fetchall()

        self.invoices_list = [dict(r) for r in rows]

    def _filter_and_sort_invoices(self) -> None:
        """Filter self.invoices_list in-memory and sort."""
        q = self.search_entry.get().strip().lower()
        cat = self.cat_filter.get()
        min_p_str = self.min_price_entry.get().strip().replace("$", "").replace(".", "").replace(",", "").strip()
        max_p_str = self.max_price_entry.get().strip().replace("$", "").replace(".", "").replace(",", "").strip()

        try:
            min_p = float(min_p_str) if min_p_str else None
        except ValueError:
            min_p = None

        try:
            max_p = float(max_p_str) if max_p_str else None
        except ValueError:
            max_p = None

        res = []
        for inv in self.invoices_list:
            if q:
                inv_num = str(inv["invoice_number"]).lower()
                c_name = str(inv["cashier"]).lower()
                cust_name = str(inv["customer"]).lower()
                inv_id = str(inv["id"]).lower()
                if (q not in inv_num) and (q not in c_name) and (q not in cust_name) and (q not in inv_id):
                    continue

            if cat and cat not in ("Todas las categorías", "Seleccionar"):
                cats = str(inv.get("category_names") or "").lower()
                if cat.lower() not in cats:
                    continue

            tot = float(inv["total"])
            if min_p is not None and tot < min_p:
                continue
            if max_p is not None and tot > max_p:
                continue

            res.append(inv)

        # Sort
        reverse = (self.sort_direction == "desc")
        key = self.sort_column

        if key in ("total", "cash_received", "cash_change", "item_count", "id"):
            res.sort(key=lambda x: float(x.get(key, 0) or 0), reverse=reverse)
        else:
            res.sort(key=lambda x: str(x.get(key, "") or "").lower(), reverse=reverse)

        self.filtered_invoices = res

        # Calculate pages
        total_items = len(self.filtered_invoices)
        self.total_pages = max(1, math.ceil(total_items / self.page_size))
        if self.current_page > self.total_pages:
            self.current_page = self.total_pages

        self._render_table_rows()
        self._update_kpi_summary()

    def _update_kpi_summary(self) -> None:
        """Update KPI count, revenue, and ticket chips."""
        count = len(self.filtered_invoices)
        tot = sum(inv["total"] for inv in self.filtered_invoices)
        avg = (tot / count) if count > 0 else 0.0

        self.kpi_count_lbl.configure(text=f" {count} Facturas")
        self.kpi_total_lbl.configure(text=f" Recaudo: {format_currency_short(tot)}")
        self.kpi_ticket_lbl.configure(text=f" Promedio: {format_currency_short(avg)}")

        col_name = next((lbl for k, lbl, *_ in self.columns_def if k == self.sort_column), self.sort_column)
        dir_txt = "Desc" if self.sort_direction == "desc" else "Asc"
        if hasattr(self, "sort_info_lbl"):
            self.sort_info_lbl.configure(text=f"⇅  Ordenado: {col_name} ({dir_txt})")

        # Update page label
        self.page_info_lbl.configure(text=f"Página {self.current_page} de {self.total_pages} ({count} facturas)")
        self.prev_page_btn.configure(state="normal" if self.current_page > 1 else "disabled")
        self.next_page_btn.configure(state="normal" if self.current_page < self.total_pages else "disabled")

    def _on_header_click(self, col_key: str) -> None:
        """Toggle sorting on column."""
        if self.sort_column == col_key:
            self.sort_direction = "asc" if self.sort_direction == "desc" else "desc"
        else:
            self.sort_column = col_key
            self.sort_direction = "desc" if col_key in ("total", "timestamp") else "asc"

        for k, lbl in self.header_buttons.items():
            base = next((label for key, label, *_ in self.columns_def if key == k), k)
            if k == self.sort_column:
                arrow = "▼" if self.sort_direction == "desc" else "▲"
                lbl.configure(text=f"{base} {arrow}", text_color=DarkTheme.TEXT_PRIMARY)
            else:
                lbl.configure(text=f"{base}  ⇅", text_color=DarkTheme.TEXT_SECONDARY)

        self._filter_and_sort_invoices()

    def _render_table_rows(self) -> None:
        """Render paginated rows in the right-hand scrollable table."""
        self.rendered_row_data = []
        self.selected_row_idx = None

        for w in self.rows_scroll.winfo_children():
            w.destroy()

        if not self.filtered_invoices:
            empty = ctk.CTkFrame(self.rows_scroll, fg_color="transparent")
            empty.pack(fill="x", pady=40)
            ctk.CTkLabel(
                empty,
                text="No hay facturas que coincidan con los filtros seleccionados.",
                font=ctk.CTkFont(family="Segoe UI", size=11, slant="italic"),
                text_color=DarkTheme.TEXT_MUTED
            ).pack()
            return

        # Slice current page
        start_idx = (self.current_page - 1) * self.page_size
        end_idx = start_idx + self.page_size
        page_invoices = self.filtered_invoices[start_idx:end_idx]

        ticket_img = get_tinted_ctk_icon("ticket_white", "#666BC5", size=(12, 12)) or get_ctk_icon("ticket_white", size=(12, 12))
        money_icon = get_ctk_icon("money_white", size=(18, 18))
        mobile_icon = get_ctk_icon("mobile_white", size=(18, 18))
        card_icon = get_ctk_icon("credit_card_white", size=(18, 18))

        for idx, inv in enumerate(page_invoices):
            row_bg = DarkTheme.BG_CARD if (idx % 2 == 0) else DarkTheme.BG_ROW_ALT
            row_frame = ctk.CTkFrame(
                self.rows_scroll,
                fg_color=row_bg,
                border_color=DarkTheme.BORDER_SUBTLE,
                border_width=1,
                corner_radius=4,
                height=34
            )
            row_frame.pack(fill="x", pady=1.5)
            row_frame.pack_propagate(False)

            self.rendered_row_data.append((row_frame, inv["id"]))

            for col_idx, (_, _, width, _, _, weight) in enumerate(self.columns_def):
                row_frame.grid_columnconfigure(col_idx, weight=weight, minsize=width if weight == 0 else 0)

            def _hover_enter(e, rf=row_frame, i=idx):
                try:
                    if self.selected_row_idx != i:
                        rf.configure(fg_color=DarkTheme.BG_ROW_HOVER, border_color="#3B82F6")
                except Exception:
                    pass

            def _hover_leave(e, rf=row_frame, bg=row_bg, i=idx):
                try:
                    if self.selected_row_idx != i:
                        rf.configure(fg_color=bg, border_color=DarkTheme.BORDER_SUBTLE)
                except Exception:
                    pass

            def _on_row_click(e, i=idx):
                self._select_table_row(i)

            def _on_row_double_click(e, inv_id=inv["id"]):
                self._reprint_ticket(inv_id)

            row_frame.bind("<Enter>", _hover_enter)
            row_frame.bind("<Leave>", _hover_leave)
            row_frame.bind("<Button-1>", _on_row_click)
            row_frame.bind("<Double-Button-1>", _on_row_double_click)

            # Keyboard navigation on row_frame
            row_frame.bind("<Up>", self._on_table_key_up)
            row_frame.bind("<Down>", self._on_table_key_down)
            row_frame.bind("<Return>", self._on_table_enter_space)
            row_frame.bind("<KP_Enter>", self._on_table_enter_space)
            row_frame.bind("<space>", self._on_table_enter_space)
            row_frame.bind("<Left>", lambda e: (self._prev_page(), "break")[1])
            row_frame.bind("<Right>", lambda e: (self._next_page(), "break")[1])
            row_frame.bind("<Prior>", lambda e: (self._prev_page(), "break")[1])
            row_frame.bind("<Next>", lambda e: (self._next_page(), "break")[1])
            row_frame.bind("<Tab>", lambda e: (self._focus_prev_btn(), "break")[1])
            row_frame.bind("<Shift-Tab>", lambda e: (self._focus_excel_btn(), "break")[1])
            row_frame.bind("<ISO_Left_Tab>", lambda e: (self._focus_excel_btn(), "break")[1])

            # Payment method icon-only setup (pure colorful icon, NO container/recuadro as requested)
            pm_raw = str(inv["payment_method"]).upper()
            if "NEQUI" in pm_raw:
                pm_icon = get_ctk_icon("nequi", size=(16, 16)) or mobile_icon
            elif "DAVIPLATA" in pm_raw:
                pm_icon = get_ctk_icon("daviplata", size=(16, 16)) or mobile_icon
            elif "BANCOLOMBIA" in pm_raw:
                pm_icon = get_ctk_icon("bancolombia", size=(16, 16)) or mobile_icon
            elif "TARJETA" in pm_raw:
                pm_icon = card_icon
            elif "FIADO" in pm_raw:
                pm_icon = get_ctk_icon("building_user_white", size=(16, 16)) or money_icon
            elif "TRANSFER" in pm_raw:
                pm_icon = mobile_icon
            else:
                pm_icon = money_icon

            # Cells: 0: Factura, 1: Fecha y Hora, 2: Cajero, 3: Cliente, 4: Ítems
            cells = [
                (0, inv["invoice_number"], DarkTheme.TEXT_PRIMARY, True, "center"),
                (1, inv["timestamp"][:16], DarkTheme.TEXT_MUTED, False, "center"),
                (2, inv["cashier"][:14], DarkTheme.TEXT_SECONDARY, False, "w"),
                (3, inv["customer"][:16], DarkTheme.TEXT_PRIMARY, False, "w"),
                (4, f"{inv['item_count']} und", DarkTheme.TEXT_SECONDARY, False, "center"),
            ]

            for col_idx, val_text, text_color, is_bold, anchor in cells:
                cell_padx = (8, 4) if anchor == "w" else 2
                lbl = ctk.CTkLabel(
                    row_frame,
                    text=val_text,
                    width=self.columns_def[col_idx][2],
                    font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold" if is_bold else "normal"),
                    text_color=text_color,
                    anchor=anchor
                )
                lbl.grid(row=0, column=col_idx, sticky="nsew", padx=cell_padx)
                lbl.bind("<Enter>", _hover_enter)
                lbl.bind("<Leave>", _hover_leave)
                lbl.bind("<Button-1>", _on_row_click)
                lbl.bind("<Double-Button-1>", _on_row_double_click)

            # Col 5: Payment method icon-only (NO box/recuadro, pure colorful icon)
            pm_frame = ctk.CTkFrame(row_frame, width=self.columns_def[5][2], fg_color="transparent")
            pm_frame.grid(row=0, column=5, sticky="nsew", padx=2)
            pm_frame.bind("<Enter>", _hover_enter)
            pm_frame.bind("<Leave>", _hover_leave)
            pm_frame.bind("<Button-1>", _on_row_click)
            pm_frame.bind("<Double-Button-1>", _on_row_double_click)

            if pm_icon:
                pm_lbl = ctk.CTkLabel(pm_frame, image=pm_icon, text="", fg_color="transparent")
                pm_lbl.pack(expand=True)
                pm_lbl.bind("<Enter>", _hover_enter)
                pm_lbl.bind("<Leave>", _hover_leave)
                pm_lbl.bind("<Button-1>", _on_row_click)
                pm_lbl.bind("<Double-Button-1>", _on_row_double_click)

            # Col 6: Total Factura
            lbl_tot = ctk.CTkLabel(
                row_frame,
                text=format_currency(inv["total"]),
                width=self.columns_def[6][2],
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=DarkTheme.SUCCESS_TEXT,
                anchor="center"
            )
            lbl_tot.grid(row=0, column=6, sticky="nsew", padx=2)
            lbl_tot.bind("<Enter>", _hover_enter)
            lbl_tot.bind("<Leave>", _hover_leave)
            lbl_tot.bind("<Button-1>", _on_row_click)
            lbl_tot.bind("<Double-Button-1>", _on_row_double_click)

            # Col 7: Acciones -> 'Ver factura' (icon-only, variant="ver") & 'Eliminar factura' (icon-only, variant="eliminar")
            act_frame = ctk.CTkFrame(row_frame, width=self.columns_def[7][2], fg_color="transparent")
            act_frame.grid(row=0, column=7, sticky="nsew", padx=2)
            act_frame.bind("<Enter>", _hover_enter)
            act_frame.bind("<Leave>", _hover_leave)

            btn_box = ctk.CTkFrame(act_frame, fg_color="transparent")
            btn_box.pack(expand=True)

            reprint_btn = ctk.CTkButton(
                btn_box,
                text="",
                width=30,
                height=24,
                corner_radius=4,
                cursor="hand2",
                command=lambda inv_id=inv["id"]: self._reprint_ticket(inv_id)
            )
            apply_palette_button(reprint_btn, variant="ver", icon_name="ticket_white", icon_size=(13, 13))
            reprint_btn.pack(side="left", padx=2)

            del_inv_btn = ctk.CTkButton(
                btn_box,
                text="",
                width=30,
                height=24,
                corner_radius=4,
                cursor="hand2",
                command=lambda inv_id=inv["id"], inv_num=inv["invoice_number"]: self._delete_invoice(inv_id, inv_num)
            )
            apply_palette_button(del_inv_btn, variant="eliminar", icon_name="trash_red", icon_size=(13, 13))
            del_inv_btn.pack(side="left", padx=2)

    def _delete_invoice(self, sale_id: int, invoice_number: str) -> None:
        """Prompt confirmation and delete sale, reverting inventory stock."""
        ans = messagebox.askyesno(
            "Confirmar Eliminación",
            f"¿Está seguro de que desea eliminar la factura '{invoice_number}'?\n\n"
            "Esta acción eliminará el registro de venta y reintegrará automáticamente "
            "las cantidades vendidas al stock del inventario.",
            parent=self
        )
        if not ans:
            return

        try:
            with get_db_connection() as conn:
                success = SaleModel.delete_sale(conn, sale_id)
            if success:
                try:
                    sound_manager.play_success()
                except Exception:
                    pass
                messagebox.showinfo(
                    "Factura Eliminada",
                    f"La factura '{invoice_number}' fue eliminada correctamente y el stock ha sido restaurado.",
                    parent=self
                )
                self.refresh_stats()
            else:
                messagebox.showerror(
                    "Error",
                    f"No se pudo encontrar la factura con ID {sale_id}.",
                    parent=self
                )
        except Exception as e:
            import logging
            logging.error("Error eliminando factura %s: %s", sale_id, e)
            messagebox.showerror(
                "Error al Eliminar",
                f"Ocurrió un error inesperado al eliminar la factura:\n{e}",
                parent=self
            )

    def _reprint_ticket(self, sale_id: int) -> None:
        """Fetch sale detail and display reprint ticket modal without crashing."""
        try:
            with get_db_connection() as conn:
                sale = SaleModel.get_sale_by_id(conn, sale_id)
            if not sale:
                messagebox.showerror("Error", "No se encontró el detalle de la venta solicitada.", parent=self)
                return

            ticket_text = format_ticket(sale)
            sound_manager.play_success()
            TicketPreviewModal(parent=self, ticket_text=ticket_text)
        except Exception as e:
            messagebox.showerror("Error al mostrar factura", f"Ocurrió un error al cargar el recibo de la factura:\n{e}", parent=self)

    # ── Excel Export ─────────────────────────────────────────────────────────
    def _export_excel(self) -> None:
        """Export current filtered sales list to formatted Excel file."""
        if not self.filtered_invoices:
            messagebox.showwarning("Sin datos", "No hay facturas para exportar con los filtros actuales.", parent=self)
            return

        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"Ventas_XLBurguer_{date_str}.xlsx"

        file_path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".xlsx",
            filetypes=[("Excel Spreadsheet", "*.xlsx")],
            initialfile=default_filename,
            title="Guardar Reporte de Ventas"
        )
        if not file_path:
            return

        self.excel_btn.configure(text="  Generando...", state="disabled")

        def _on_export_done(success: bool, err_msg: Optional[str]) -> None:
            def _ui_callback():
                try:
                    self.excel_btn.configure(text=" Exportar excel (.xlsx)", state="normal")
                except Exception:
                    pass
                if success:
                    sound_manager.play_success()
                    if messagebox.askyesno(
                        "Exportación Exitosa",
                        f"Reporte exportado exitosamente a:\n{file_path}\n\n¿Desea abrir el archivo ahora?",
                        parent=self
                    ):
                        try:
                            os.startfile(file_path)
                        except Exception:
                            pass
                else:
                    sound_manager.play_error()
                    messagebox.showerror("Error de Exportación", f"No se pudo generar el archivo Excel:\n{err_msg}", parent=self)

            try:
                self.after(0, _ui_callback)
            except Exception:
                _ui_callback()

        start_d = self.start_date_entry.get().strip() or "2000-01-01"
        end_d = self.end_date_entry.get().strip() or "2099-12-31"
        cat_d = self.cat_filter.get() if hasattr(self, "cat_filter") else "Todas las categorías"
        min_p = self.min_price_entry.get().strip() if hasattr(self, "min_price_entry") else "0"
        max_p = self.max_price_entry.get().strip() if hasattr(self, "max_price_entry") else "Sin límite"

        filters_summary = {
            "start_date": start_d,
            "end_date": end_d,
            "category_name": cat_d,
            "min_price": min_p or 0,
            "max_price": max_p or "Sin límite"
        }

        export_sales_async(
            file_path=file_path,
            start_date=start_d,
            end_date=end_d,
            invoices_data=self.filtered_invoices,
            filters_summary=filters_summary,
            on_complete=_on_export_done
        )
