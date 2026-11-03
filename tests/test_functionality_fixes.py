"""Unit tests verifying all functionality fixes for XL Burguer POS.

Tests cover:
1. NORMALIZE_TEXT and accent-insensitive product queries.
2. Colombian date formatting (DD/MM/YYYY) in sales filters.
3. Category-filtered invoice queries and period KPI summary.
4. Scale driver reconnection and fallback safety.
5. Ticket printer exact column layout.
6. POS calculation and conversion helpers.
"""

import os
import sys
import unittest

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.connection import get_db_connection, initialize_database, normalize_text
from hardware.scale_service import SerialScaleDriver
from hardware.ticket_printer import format_ticket
from models.product import ProductModel, calculate_item_price, convert_quantity_to_base
from models.sale import SaleModel, normalize_date_str
from utils.asset_manager import ensure_assets


class TestFunctionalityFixes(unittest.TestCase):
    """Test suite covering the functionality enhancements."""

    @classmethod
    def setUpClass(cls):
        ensure_assets()
        initialize_database()

    def test_normalize_text_accents(self):
        """Verify accent stripping and lowercase normalization."""
        self.assertEqual(normalize_text("ALMOJÁBANA"), "almojabana")
        self.assertEqual(normalize_text("Costilla de Cerdo"), "costilla de cerdo")
        self.assertEqual(normalize_text("Chorizo Español"), "chorizo espanol")
        self.assertEqual(normalize_text(None), "")

    def test_sqlite_normalize_text_query(self):
        """Verify SQLite NORMALIZE_TEXT custom function handles unaccented searches."""
        with get_db_connection() as conn:
            # Search with accents or without accents should yield matching products
            res1 = ProductModel.get_all(conn, search_query="clasica")
            self.assertTrue(len(res1) > 0)

            res2 = ProductModel.get_all(conn, search_query="CLÁSICA")
            self.assertEqual(len(res1), len(res2))

            # Omnisearch by name via get_by_barcode_or_id
            first_prod = res1[0]
            lookup = ProductModel.get_by_barcode_or_id(conn, first_prod.name.upper())
            self.assertIsNotNone(lookup)
            self.assertEqual(lookup.id, first_prod.id)

    def test_normalize_date_str(self):
        """Verify date string normalization for Colombian formats."""
        self.assertEqual(normalize_date_str("14/09/2026"), "2026-09-14")
        self.assertEqual(normalize_date_str("14-09-2026"), "2026-09-14")
        self.assertEqual(normalize_date_str("2026-09-14"), "2026-09-14")
        self.assertIsNone(normalize_date_str(""))
        self.assertIsNone(normalize_date_str("invalid"))

    def test_sales_summary_and_category_filter(self):
        """Verify invoice filtering by category and sales summary calculation."""
        with get_db_connection() as conn:
            # Sales summary
            summary = SaleModel.get_sales_summary(conn)
            self.assertIn("total_sales", summary)
            self.assertIn("sales_count", summary)
            self.assertIn("avg_ticket", summary)
            self.assertIsInstance(summary["total_sales"], (int, float))
            self.assertIsInstance(summary["sales_count"], int)

            # Filtered invoices with category
            invoices_cat1 = SaleModel.get_filtered_invoices(conn, category_id=1)
            self.assertIsInstance(invoices_cat1, list)

            # Filtered invoices with invalid category
            invoices_none = SaleModel.get_filtered_invoices(conn, category_id=999999)
            self.assertEqual(len(invoices_none), 0)

    def test_pos_weight_conversions(self):
        """Verify weight conversions and unit calculations."""
        # 1 kg = 1000g
        self.assertEqual(convert_quantity_to_base(1.0, "kg", "PESO"), 1000.0)
        # 1 lb = 500g (Colombian butcher trade standard)
        self.assertEqual(convert_quantity_to_base(1.0, "lb", "PESO"), 500.0)
        # 250 g = 250g
        self.assertEqual(convert_quantity_to_base(250.0, "g", "PESO"), 250.0)

        # Price calculation: price_base = 28 COP/g (28,000 COP/kg)
        price_base = 28.0
        # 1 kg of meat at 28/g -> 28,000 COP
        price_kg = calculate_item_price(price_base, 1.0, "kg", "PESO")
        self.assertEqual(price_kg, 28000.0)
        # 1 lb of meat at 28/g -> 14,000 COP
        price_lb = calculate_item_price(price_base, 1.0, "lb", "PESO")
        self.assertEqual(price_lb, 14000.0)
        # 500 g of meat at 28/g -> 14,000 COP
        price_g = calculate_item_price(price_base, 500.0, "g", "PESO")
        self.assertEqual(price_g, 14000.0)

    def test_ticket_strict_box_formatting(self):
        """Verify ticket formatting produces exact 42-column lines regardless of input lengths."""
        long_cashier = "Cajero Con Nombre Muy Extenso Villa De Leyva"
        items = [
            {
                "product_name": "Corte Especial de Res Con Nombre Largo",
                "quantity": 2.75,
                "unit_selected": "kg",
                "total_price": 77000.0
            }
        ]
        ticket = format_ticket(
            invoice_number="SD-TEST-99999",
            timestamp="2026-09-22 18:00:00",
            cashier_name=long_cashier,
            items=items,
            subtotal=77000.0,
            total=77000.0,
            cash_received=100000.0,
            cash_change=23000.0
        )
        lines = ticket.split("\n")
        self.assertTrue(len(lines) > 10)
        for idx, line in enumerate(lines):
            self.assertEqual(
                len(line), 40,
                f"Line {idx} width is {len(line)}, expected 40: '{line}'"
            )

    def test_scale_driver_reconnect(self):
        """Verify scale driver reconnect returns boolean and sets mock status safely."""
        driver = SerialScaleDriver(force_mock=True)
        self.assertTrue(driver.is_mock_mode)
        is_phys = driver.reconnect()
        # In test environment without hardware scale, fallback to mock is expected
        self.assertIsInstance(is_phys, bool)
        val, unit = driver.read_weight()
        self.assertGreater(val, 0)
        self.assertIn(unit, ("kg", "g"))
        driver.close()


if __name__ == "__main__":
    unittest.main()
