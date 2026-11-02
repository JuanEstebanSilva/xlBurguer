"""Excel Sales Report Exporter for Carnicería San Diego.
Generates executive-styled .xlsx spreadsheets using openpyxl with clean obsidian & slate headers,
accounting currency formatting ($ #,##0), auto-fitted columns, freeze panes, and =SUM() formulas.
Designed to deliver a modern corporate report presentation without visual clutter.
"""

from datetime import datetime
import os
import threading
from typing import Any, Callable, Dict, List, Optional
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def export_sales_to_excel(
    file_path: str,
    items: List[Dict[str, Any]],
    filters_summary: Dict[str, Any]
) -> None:
    """Generate executive Excel report workbook from sales items list."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ventas San Diego"

    # Ensure grid lines are visible
    ws.views.sheetView[0].showGridLines = True

    # ── Color Palette & Professional Styling ─────────────────────────────────
    # Primary header: Deep Obsidian Charcoal
    header_navy_fill = PatternFill(start_color="181A22", end_color="181A22", fill_type="solid")
    # Subtitle / Accent: Dark Slate
    sub_slate_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    # Table column header: Executive Charcoal Navy
    th_fill = PatternFill(start_color="242A38", end_color="242A38", fill_type="solid")
    # Alternating data row fill: Soft Slate Ice
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    # Metadata container fill: Warm Subtle Off-White
    meta_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    # Total row fill: Elegant Soft Slate
    total_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")

    # Typography
    font_family = "Segoe UI"
    title_font = Font(name=font_family, size=14, bold=True, color="FFFFFF")
    subtitle_font = Font(name=font_family, size=10, bold=True, color="CBD5E1")
    meta_font = Font(name=font_family, size=9, bold=False, color="334155")
    th_font = Font(name=font_family, size=10, bold=True, color="FFFFFF")
    regular_font = Font(name=font_family, size=9, color="0F172A")
    prod_font = Font(name=font_family, size=9, bold=True, color="0F172A")
    inv_font = Font(name=font_family, size=9, bold=True, color="1E293B")
    total_font = Font(name=font_family, size=10, bold=True, color="0F172A")

    # Borders
    thin_gray = Side(border_style="thin", color="E2E8F0")
    data_border = Border(left=thin_gray, right=thin_gray, top=thin_gray, bottom=thin_gray)
    th_border = Border(
        left=Side(border_style="thin", color="3A4156"),
        right=Side(border_style="thin", color="3A4156"),
        top=Side(border_style="thin", color="3A4156"),
        bottom=Side(border_style="medium", color="0F172A")
    )
    total_border = Border(
        top=Side(border_style="thin", color="94A3B8"),
        bottom=Side(border_style="double", color="0F172A"),
        left=thin_gray,
        right=thin_gray
    )

    currency_format = '"$"#,##0'
    number_format = '#,##0.00'

    # ── 1. Main Title Banner (Row 1) ─────────────────────────────────────────
    ws.merge_cells("A1:J1")
    title_cell = ws["A1"]
    title_cell.value = "CARNICERÍA SAN DIEGO - VILLA DE LEYVA"
    title_cell.font = title_font
    title_cell.fill = header_navy_fill
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32

    # ── 2. Report Subtitle Banner (Row 2) ────────────────────────────────────
    ws.merge_cells("A2:J2")
    sub_cell = ws["A2"]
    sub_cell.value = "REPORTE DETALLADO DE VENTAS E INVENTARIO"
    sub_cell.font = subtitle_font
    sub_cell.fill = sub_slate_fill
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    # ── 3. Executive Metadata & Filter Bar (Row 3) ───────────────────────────
    now_str = datetime.now().strftime("%d/%m/%Y %I:%M %p")
    start_d = filters_summary.get('start_date') or "Inicio"
    end_d = filters_summary.get('end_date') or "Hoy"
    cat_d = filters_summary.get('category_name') or "Todas las categorías"
    min_d = filters_summary.get('min_price', 0)
    max_d = filters_summary.get('max_price', 'Sin límite')

    min_disp = f"${min_d:,.0f}" if isinstance(min_d, (int, float)) and min_d > 0 else "$0"
    max_disp = f"${max_d:,.0f}" if isinstance(max_d, (int, float)) and max_d > 0 else str(max_d)

    meta_text = (
        f"Emisión: {now_str}   |   "
        f"Período: {start_d} a {end_d}   |   "
        f"Categoría: {cat_d}   |   "
        f"Rango de Montos: {min_disp} - {max_disp}   |   "
        f"Total Registros: {len(items):,d} ítems"
    )
    ws.merge_cells("A3:J3")
    meta_cell = ws["A3"]
    meta_cell.value = meta_text
    meta_cell.font = meta_font
    meta_cell.fill = meta_fill
    meta_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[3].height = 20

    # ── 4. Clean Spacer Row (Row 4) ──────────────────────────────────────────
    ws.row_dimensions[4].height = 10

    # ── 5. Column Headers (Row 5) ────────────────────────────────────────────
    headers = [
        "Factura",
        "Fecha / Hora",
        "Cajero",
        "Categoría",
        "Producto",
        "Cantidad",
        "Unidad",
        "Precio Unitario",
        "Total Ítem",
        "Total Factura"
    ]

    header_row = 5
    ws.row_dimensions[header_row].height = 26
    for col_idx, h_text in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=h_text)
        cell.font = th_font
        cell.fill = th_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = th_border

    # Freeze panes right below headers so row 1-5 remain visible on scroll
    ws.freeze_panes = "A6"

    # ── 6. Populate Data Rows (Row 6 onward) ─────────────────────────────────
    current_row = 6
    for idx, item in enumerate(items):
        ws.row_dimensions[current_row].height = 20
        row_fill = zebra_fill if (idx % 2 == 1) else None

        c_inv = ws.cell(row=current_row, column=1, value=item.get("invoice_number", ""))
        c_date = ws.cell(row=current_row, column=2, value=item.get("timestamp", ""))
        c_cashier = ws.cell(row=current_row, column=3, value=item.get("cashier_name", ""))
        c_cat = ws.cell(row=current_row, column=4, value=item.get("category_name", ""))
        c_prod = ws.cell(row=current_row, column=5, value=item.get("product_name", ""))

        qty_val = float(item.get("quantity", 0))
        c_qty = ws.cell(row=current_row, column=6, value=qty_val)
        c_qty.number_format = number_format

        c_unit = ws.cell(row=current_row, column=7, value=item.get("unit_selected", ""))

        unit_price_val = float(item.get("unit_price", 0))
        c_uprice = ws.cell(row=current_row, column=8, value=unit_price_val)
        c_uprice.number_format = currency_format

        item_total_val = float(item.get("item_total", 0))
        c_itotal = ws.cell(row=current_row, column=9, value=item_total_val)
        c_itotal.number_format = currency_format

        inv_total_val = float(item.get("invoice_total", 0))
        c_invtotal = ws.cell(row=current_row, column=10, value=inv_total_val)
        c_invtotal.number_format = currency_format

        # Alignments
        c_inv.alignment = Alignment(horizontal="center", vertical="center")
        c_date.alignment = Alignment(horizontal="center", vertical="center")
        c_cashier.alignment = Alignment(horizontal="left", vertical="center")
        c_cat.alignment = Alignment(horizontal="left", vertical="center")
        c_prod.alignment = Alignment(horizontal="left", vertical="center")
        c_qty.alignment = Alignment(horizontal="right", vertical="center")
        c_unit.alignment = Alignment(horizontal="center", vertical="center")
        c_uprice.alignment = Alignment(horizontal="right", vertical="center")
        c_itotal.alignment = Alignment(horizontal="right", vertical="center")
        c_invtotal.alignment = Alignment(horizontal="right", vertical="center")

        # Fonts & borders
        c_inv.font = inv_font
        c_prod.font = prod_font
        for c in [c_date, c_cashier, c_cat, c_qty, c_unit, c_uprice, c_itotal, c_invtotal]:
            c.font = regular_font

        for c in [c_inv, c_date, c_cashier, c_cat, c_prod, c_qty, c_unit, c_uprice, c_itotal, c_invtotal]:
            c.border = data_border
            if row_fill:
                c.fill = row_fill

        current_row += 1

    # ── 7. Total Summary Row with Accounting Double Underline ────────────────
    summary_row = current_row
    ws.row_dimensions[summary_row].height = 25

    ws.merge_cells(start_row=summary_row, start_column=1, end_row=summary_row, end_column=8)
    sum_label = ws.cell(row=summary_row, column=1, value="TOTAL GENERAL RECAUDADO:")
    sum_label.font = total_font
    sum_label.alignment = Alignment(horizontal="right", vertical="center")

    # Formula on Total Item column (column 9 -> I)
    total_cell = ws.cell(row=summary_row, column=9)
    if len(items) > 0:
        total_cell.value = f"=SUM(I6:I{summary_row - 1})"
    else:
        total_cell.value = 0.0
    total_cell.font = total_font
    total_cell.number_format = currency_format
    total_cell.alignment = Alignment(horizontal="right", vertical="center")

    # Final cell column 10
    ws.cell(row=summary_row, column=10, value="")

    for col in range(1, 11):
        c = ws.cell(row=summary_row, column=col)
        c.fill = total_fill
        c.border = total_border

    # ── 8. Precise Auto-fit Column Widths ────────────────────────────────────
    col_min_widths = {
        1: 14,  # Factura
        2: 20,  # Fecha/Hora
        3: 18,  # Cajero
        4: 18,  # Categoría
        5: 28,  # Producto
        6: 12,  # Cantidad
        7: 10,  # Unidad
        8: 15,  # Precio Unitario
        9: 16,  # Total Ítem
        10: 16, # Total Factura
    }

    for col_idx, col in enumerate(ws.columns, start=1):
        col_letter = get_column_letter(col_idx)
        max_len = col_min_widths.get(col_idx, 12)
        for cell in col:
            # Skip merged title and subtitle rows
            if cell.row < 5:
                continue
            val_str = str(cell.value or '')
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 3, col_min_widths.get(col_idx, 12))

    # Save workbook to destination path
    wb.save(file_path)


def export_sales_async(
    file_path: str,
    items: Optional[List[Dict[str, Any]]] = None,
    filters_summary: Optional[Dict[str, Any]] = None,
    on_success: Optional[Callable[[str], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    invoices_data: Optional[List[Dict[str, Any]]] = None,
    on_complete: Optional[Callable[[bool, Optional[str]], None]] = None,
    **kwargs
) -> None:
    """Run Excel generation in a background thread to prevent UI freezing.
    Supports both direct items list and raw invoices_data from database.
    """
    def worker():
        try:
            resolved_items = items
            if resolved_items is None and invoices_data is not None:
                # Resolve detailed sale items from database
                sale_ids = [inv["id"] for inv in invoices_data if isinstance(inv, dict) and "id" in inv]
                if sale_ids:
                    from database.connection import get_db_connection
                    with get_db_connection() as conn:
                        cur = conn.cursor()
                        placeholders = ",".join("?" for _ in sale_ids)
                        query = f"""
                            SELECT 
                                s.invoice_number,
                                s.timestamp,
                                COALESCE(u.full_name, 'Diego Amador') AS cashier_name,
                                COALESCE(cat.name, 'General') AS category_name,
                                COALESCE(p.name, 'Producto') AS product_name,
                                si.quantity,
                                si.unit_selected,
                                si.unit_price,
                                si.total_price AS item_total,
                                s.total AS invoice_total
                            FROM sale_items si
                            JOIN sales s ON si.sale_id = s.id
                            LEFT JOIN users u ON s.user_id = u.id
                            LEFT JOIN products p ON si.product_id = p.id
                            LEFT JOIN categories cat ON p.category_id = cat.id
                            WHERE s.id IN ({placeholders})
                            ORDER BY s.timestamp DESC, s.id DESC, si.id ASC
                        """
                        cur.execute(query, sale_ids)
                        resolved_items = [dict(r) for r in cur.fetchall()]
                else:
                    resolved_items = []
            elif resolved_items is None:
                resolved_items = []

            resolved_summary = filters_summary or {}
            if start_date and "start_date" not in resolved_summary:
                resolved_summary["start_date"] = start_date
            if end_date and "end_date" not in resolved_summary:
                resolved_summary["end_date"] = end_date

            export_sales_to_excel(file_path, resolved_items, resolved_summary)
            if on_success:
                on_success(file_path)
            if on_complete:
                on_complete(True, None)
        except Exception as e:
            if on_error:
                on_error(e)
            if on_complete:
                on_complete(False, str(e))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

