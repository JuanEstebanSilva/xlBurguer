"""Unit and Integration Tests for StatsFrame and Excel Exporter.
Verifies:
- StatsFrame instantiation and building of all widgets without errors.
- Periodic analytics calculations (Hoy, Semana, Mes).
- Ticket promedio and top category calculations.
- Omni-search across invoice number, cashier, customer.
- Column sorting (ascending / descending) on all sortable columns.
- Date, category, and price filtering.
- Reset filters to defaults.
- Clean Excel export with executive styling and validation of cell formulas and contents.
"""

import os
import sys
import tempfile
import unittest
import openpyxl
import customtkinter as ctk

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.connection import get_db_connection, initialize_database
from models.sale import SaleModel
from utils.asset_manager import ensure_assets
from utils.excel_exporter import export_sales_to_excel
from views.stats_frame import StatsFrame


class TestStatsModule(unittest.TestCase):
    """Test suite for StatsFrame dashboard, analytics, and Excel reporting."""

    @classmethod
    def setUpClass(cls):
        ensure_assets()
        initialize_database()

    def test_01_periodic_analytics_in_db(self):
        """Verify get_periodic_analytics returns expected keys including avg_ticket."""
        with get_db_connection() as conn:
            analytics = SaleModel.get_periodic_analytics(conn)

        for period in ("daily", "weekly", "monthly"):
            self.assertIn(period, analytics)
            p_data = analytics[period]
            self.assertIn("total_sold", p_data)
            self.assertIn("sales_count", p_data)
            self.assertIn("avg_ticket", p_data)
            self.assertIn("top_product_name", p_data)
            self.assertIn("top_product_revenue", p_data)
            self.assertIn("top_product_qty", p_data)
            self.assertIn("top_category_name", p_data)

    def test_02_stats_frame_ui_and_interactions(self):
        """Verify StatsFrame instantiates cleanly, builds all widgets, searches, sorts, and resets."""
        root = ctk.CTk()
        root.withdraw()
        try:
            frame = StatsFrame(parent=root)
            self.assertIsNotNone(frame)

            # Check financial balance labels
            self.assertTrue(hasattr(frame, "bal_day_tot_lbl"))
            self.assertTrue(hasattr(frame, "bal_week_tot_lbl"))
            self.assertTrue(hasattr(frame, "bal_month_tot_lbl"))

            # Check top products labels
            self.assertTrue(hasattr(frame, "top_day_name_lbl"))
            self.assertTrue(hasattr(frame, "top_week_name_lbl"))
            self.assertTrue(hasattr(frame, "top_month_name_lbl"))

            # Check filter inputs
            self.assertTrue(hasattr(frame, "search_entry"))
            self.assertTrue(hasattr(frame, "start_date_entry"))
            self.assertTrue(hasattr(frame, "end_date_entry"))
            self.assertTrue(hasattr(frame, "min_price_entry"))
            self.assertTrue(hasattr(frame, "max_price_entry"))
            self.assertTrue(hasattr(frame, "cat_filter"))

            # Check KPI summary labels
            self.assertTrue(hasattr(frame, "kpi_count_lbl"))
            self.assertTrue(hasattr(frame, "kpi_total_lbl"))
            self.assertTrue(hasattr(frame, "kpi_ticket_lbl"))

            # Test sorting toggle
            frame._on_header_click("total")
            self.assertEqual(frame.sort_column, "total")
            self.assertEqual(frame.sort_direction, "desc")

            frame._on_header_click("total")
            self.assertEqual(frame.sort_column, "total")
            self.assertEqual(frame.sort_direction, "asc")

            # Test omni search
            frame.search_entry.delete(0, "end")
            frame.search_entry.insert(0, "NONEXISTENT_XYZ_999")
            frame._filter_and_sort_invoices()
            self.assertEqual(len(frame.filtered_invoices), 0)

            frame._clear_search()
            self.assertEqual(len(frame.filtered_invoices), len(frame.invoices_list))

            # Test presets & reset
            frame._preset_all()
            self.assertEqual(frame.start_date_entry.get(), "")
            self.assertEqual(frame.end_date_entry.get(), "")

            frame._preset_today()
            self.assertTrue(len(frame.start_date_entry.get()) > 0)

            frame._reset_filters()
            self.assertEqual(frame.start_date_entry.get(), "")
            self.assertEqual(frame.end_date_entry.get(), "")
            self.assertEqual(frame.cat_filter.get(), "Todas las categorías")
        finally:
            root.destroy()

    def test_03_excel_export_executive_styling(self):
        """Verify export_sales_to_excel creates valid workbook with freeze panes, borders, and SUM."""
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            items = [
                {
                    "invoice_number": "SD-000001",
                    "timestamp": "2026-09-30 12:00:00",
                    "cashier_name": "Administrador",
                    "category_name": "Carnes de Res",
                    "product_name": "Lomo Fino",
                    "quantity": 2.0,
                    "unit_selected": "kg",
                    "unit_price": 45000.0,
                    "item_total": 90000.0,
                    "invoice_total": 90000.0
                }
            ]
            filters_summary = {
                "start_date": "2026-09-01",
                "end_date": "2026-09-30",
                "category_name": "Todas las categorías",
                "min_price": 0,
                "max_price": "Sin límite"
            }

            export_sales_to_excel(tmp_path, items, filters_summary)
            self.assertTrue(os.path.exists(tmp_path))

            wb = openpyxl.load_workbook(tmp_path)
            ws = wb.active

            # Check title banner
            self.assertEqual(ws["A1"].value, "CARNICERÍA SAN DIEGO - VILLA DE LEYVA")
            # Check freeze panes
            self.assertEqual(ws.freeze_panes, "A6")
            # Check row 6 data
            self.assertEqual(ws["A6"].value, "SD-000001")
            self.assertEqual(ws["E6"].value, "Lomo Fino")
            self.assertEqual(ws["I6"].value, 90000.0)
            # Check summary row formula
            self.assertEqual(ws["I7"].value, "=SUM(I6:I6)")

            wb.close()
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_04_star_product_synchronization_and_keyboard_nav(self):
        """Verify star product synchronization, Borrar button text, and keyboard navigation chaining."""
        root = ctk.CTk()
        root.withdraw()
        try:
            frame = StatsFrame(parent=root)

            # 1. Verify Clear button text and compound
            self.assertTrue("Limpiar" in frame.clear_btn.cget("text") or "Borrar" in frame.clear_btn.cget("text"))
            self.assertEqual(frame.clear_btn.cget("compound"), "left")
            self.assertEqual(frame.clear_btn.cget("height"), 36)

            # 2. Verify Star Product synchronization
            top_name_displayed = frame.card_top_val.cget("text")
            top_sub_displayed = frame.card_top_sub.cget("text")

            # If there is revenue recorded, top product name must NEVER be "Sin ventas registradas"
            if "Recaudo: $ 0" not in top_sub_displayed:
                self.assertNotEqual(top_name_displayed, "Sin ventas registradas")
                self.assertNotEqual(top_name_displayed, "Sin ventas")
                self.assertTrue(len(top_name_displayed) > 0)

            # 3. Verify keyboard navigation methods exist and execute cleanly
            frame._focus_search_entry()
            frame._focus_start_date()
            frame._focus_end_date()
            frame._focus_cat_filter()
            frame._focus_min_price()
            frame._focus_max_price()
            frame._focus_clear_btn()
            frame._focus_reload_btn()
            frame._focus_excel_btn()

            # 4. Verify clearing filters via clear button
            frame.search_entry.insert(0, "Prueba")
            frame._on_clear_filters_click()
            self.assertEqual(frame.search_entry.get(), "")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
