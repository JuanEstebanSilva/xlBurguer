"""Comprehensive Unit Tests for the Latest UI and UX Refinements:
- StatsFrame control bar reorganization (Search + Filters on Row 1; KPIs + Actions on Row 2)
- Clean currency formatting without redundant 'COP' prefix across KPIs, Cards, and Breakdown Bars
- Unified Excel export pill and icon-only eraser buttons between Inventory and Stats
- Modal dialog centering and modal backdrop overlay
- UsersFrame layout proportions and icon consistency
"""

import os
import sys
import unittest
import customtkinter as ctk

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.connection import initialize_database
from models.user import User
from utils.asset_manager import ensure_assets, center_modal
from views.inventory_frame import InventoryFrame
from views.stats_frame import StatsFrame, BreakdownChartWidget
from views.users_frame import UsersFrame


class TestLatestUIRefinements(unittest.TestCase):
    """Verify newly introduced UI architecture, layout rows, and styling rules."""

    @classmethod
    def setUpClass(cls):
        ensure_assets()
        initialize_database()

    def setUp(self):
        self.root = ctk.CTk()
        self.root.withdraw()
        self.admin = User(id=1, username="admin", password_hash="", full_name="Admin", role="ADMIN")

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_stats_controls_reorganization(self):
        """Test that StatsFrame has Row 1 with all search/filters and Row 2 with KPIs and action buttons."""
        frame = StatsFrame(parent=self.root)

        # Row 1 components: Search entry, keyboard, search filter btn, date entries, category combo, min/max
        self.assertTrue(hasattr(frame, "search_entry"))
        self.assertTrue(hasattr(frame, "filter_btn"))
        self.assertTrue(hasattr(frame, "start_date_entry"))
        self.assertTrue(hasattr(frame, "end_date_entry"))
        self.assertTrue(hasattr(frame, "cat_filter"))
        self.assertTrue(hasattr(frame, "min_price_entry"))
        self.assertTrue(hasattr(frame, "max_price_entry"))

        # Row 2 components: KPI pills
        self.assertTrue(hasattr(frame, "kpi_count_lbl"))
        self.assertTrue(hasattr(frame, "kpi_total_lbl"))
        self.assertTrue(hasattr(frame, "kpi_ticket_lbl"))

        # Row 2 Action buttons
        self.assertTrue(hasattr(frame, "clear_btn"))
        self.assertTrue(hasattr(frame, "reload_btn"))
        self.assertTrue(hasattr(frame, "excel_btn"))

        # Verify button aesthetics
        self.assertIn("Limpiar", frame.clear_btn.cget("text"))
        self.assertEqual(frame.reload_btn.cget("text"), "  Recargar")
        self.assertEqual(frame.excel_btn.cget("text"), " Exportar excel (.xlsx)")

        # Verify currency strings in KPIs do not have redundant COP
        total_text = frame.kpi_total_lbl.cget("text")
        ticket_text = frame.kpi_ticket_lbl.cget("text")
        self.assertNotIn("COP", total_text, "KPI total should not have 'COP'")
        self.assertNotIn("COP", ticket_text, "KPI ticket should not have 'COP'")

    def test_breakdown_chart_widget_formatting(self):
        """Test BreakdownChartWidget layout and currency format without COP."""
        widget = BreakdownChartWidget(parent=self.root)
        self.assertIsNotNone(widget)

        payment_data = [
            {"payment_method": "EFECTIVO", "tot": 2131014.0},
            {"payment_method": "TRANSFERENCIA", "tot": 570000.0}
        ]
        category_data = [
            {"category_name": "Bebidas y Gaseosas", "tot": 986000.0},
            {"category_name": "Hamburguesas Clásicas", "tot": 675000.0}
        ]
        widget.set_data(payment_data, category_data)
        self.root.update_idletasks()

        # Check all child labels inside BreakdownChartWidget to confirm no "COP" text exists
        def check_no_cop(w):
            if isinstance(w, ctk.CTkLabel):
                txt = w.cget("text")
                self.assertNotIn("COP", txt, f"Chart label must not contain COP: '{txt}'")
            for ch in w.winfo_children():
                check_no_cop(ch)

        check_no_cop(widget)

    def test_inventory_buttons_consistency(self):
        """Test that InventoryFrame export and clear buttons share the exact styling as StatsFrame."""
        frame = InventoryFrame(parent=self.root, current_user=self.admin)

        self.assertIn("Limpiar", frame.clear_filters_btn.cget("text"))
        self.assertEqual(frame.clear_filters_btn.cget("width"), 92)
        self.assertEqual(frame.clear_filters_btn.cget("height"), 36)

        self.assertEqual(frame.export_excel_btn.cget("text"), " Exportar excel (.xlsx)")
        self.assertEqual(frame.export_excel_btn.cget("fg_color"), "#022C22")
        self.assertEqual(frame.export_excel_btn.cget("border_color"), "#10B981")
        self.assertEqual(frame.export_excel_btn.cget("corner_radius"), 16)

    def test_users_frame_formatting_and_icons(self):
        """Test that UsersFrame displays cleanly and buttons match standard."""
        frame = UsersFrame(parent=self.root)
        self.assertTrue(hasattr(frame, "clear_btn"))
        self.assertTrue(hasattr(frame, "reload_btn"))

        # Verify badges have high-contrast styling
        self.assertEqual(frame.personas_count_badge.cget("text_color"), "#38BDF8")
        self.assertEqual(frame.personas_count_badge.cget("fg_color"), "#0C2340")
        self.assertEqual(frame.empresas_count_badge.cget("text_color"), "#FBBF24")
        self.assertEqual(frame.empresas_count_badge.cget("fg_color"), "#3B1C04")

        # Verify KPI chips do not contain COP
        spent_txt = frame.chip_total_spent.cget("text")
        avg_txt = frame.chip_avg_ticket.cget("text")
        self.assertNotIn("COP", spent_txt)
        self.assertNotIn("COP", avg_txt)

    def test_center_modal_backdrop(self):
        """Test center_modal handles backdrop cleanly without exceptions."""
        modal = ctk.CTkToplevel(self.root)
        center_modal(modal, width=500, height=400, parent=self.root)
        modal.update_idletasks()
        self.assertTrue(modal.winfo_exists())
        modal.destroy()

    def test_kpi_cards_and_ticket_buttons(self):
        """Test that StatsFrame KPI cards have ticket print buttons for HOY, 7 DÍAS, ESTE MES and not for PRODUCTO ESTRELLA."""
        frame = StatsFrame(parent=self.root)
        self.assertIn("today", frame.kpi_cards)
        self.assertIn("week", frame.kpi_cards)
        self.assertIn("month", frame.kpi_cards)
        self.assertIn("top_prod", frame.kpi_cards)

        today_card = frame.kpi_cards["today"]
        self.assertTrue(today_card.get("has_ticket_btn"))
        self.assertIsNotNone(today_card.get("ticket_btn"))

        week_card = frame.kpi_cards["week"]
        self.assertTrue(week_card.get("has_ticket_btn"))
        self.assertIsNotNone(week_card.get("ticket_btn"))

        month_card = frame.kpi_cards["month"]
        self.assertTrue(month_card.get("has_ticket_btn"))
        self.assertIsNotNone(month_card.get("ticket_btn"))

        top_prod_card = frame.kpi_cards["top_prod"]
        self.assertFalse(top_prod_card.get("has_ticket_btn"))
        self.assertIsNone(top_prod_card.get("ticket_btn"))

        # Verify separators in left column
        self.assertTrue(hasattr(frame, "sep_kpis_chart"))
        self.assertTrue(hasattr(frame, "sep_chart_breakdown"))

    def test_calendar_modal_modes(self):
        """Test CalendarPickerModal modes ('day', 'week', 'month')."""
        from views.calendar_modal import CalendarPickerModal
        
        # Test day mode
        m_day = CalendarPickerModal(self.root, mode="day")
        self.assertEqual(m_day.mode, "day")
        m_day.destroy()

        # Test week mode
        m_week = CalendarPickerModal(self.root, mode="week")
        self.assertEqual(m_week.mode, "week")
        m_week.destroy()

        # Test month mode
        m_month = CalendarPickerModal(self.root, mode="month")
        self.assertEqual(m_month.mode, "month")
        m_month.destroy()

    def test_users_frame_kpi_unmapped(self):
        """Test that UsersFrame row_kpis and kpi_divider are unmapped from UI, moving tables up."""
        frame = UsersFrame(parent=self.root)
        self.root.update_idletasks()
        
        # Attribute compatibility maintained
        self.assertTrue(hasattr(frame, "kpi_divider"))
        self.assertTrue(hasattr(frame, "row_kpis"))
        self.assertTrue(hasattr(frame, "chip_total_spent"))
        self.assertTrue(hasattr(frame, "chip_avg_ticket"))

        # Ensure they are not packed/mapped in layout
        self.assertEqual(frame.kpi_divider.winfo_manager(), "")
        self.assertEqual(frame.row_kpis.winfo_manager(), "")

    def test_customer_detail_modal_metadata_chips(self):
        """Test that CustomerDetailModal displays metadata in chips (Cédula, Registrado, Tel)."""
        from views.users_frame import CustomerDetailModal
        dummy_customer = {
            "id": 999,
            "document_id": "1051064446",
            "first_name": "Juan E",
            "last_name": "Silva E",
            "full_name": "Juan E Silva E",
            "phone": "3214057036",
            "created_at": "2026-10-16 10:00:00",
            "customer_type": "PERSONA",
            "ranking": 1
        }
        modal = CustomerDetailModal(parent=self.root, customer=dummy_customer)
        modal.update_idletasks()
        self.assertTrue(modal.winfo_exists())
        modal.destroy()


if __name__ == "__main__":
    unittest.main()


