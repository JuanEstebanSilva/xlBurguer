"""Comprehensive Automated Test Suite for Carnicería San Diego.
Verifies database integrity, models, atomic checkout transactions, weight conversions,
hardware drivers, ticket formatting, and Excel exports.
"""

import os
import sqlite3
import sys
import unittest
import openpyxl

# Add root directory to sys.path
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.connection import get_db_connection, initialize_database
from database.seed_data import seed_database
from hardware.barcode_scanner import BarcodeScannerListener
from hardware.scale_service import SerialScaleDriver
from hardware.ticket_printer import format_ticket
from models.product import (
    ProductModel,
    calculate_item_price,
    convert_quantity_to_base,
    format_currency,
    format_stock_display,
)
from models.sale import CartItem, SaleModel
from models.user import UserModel, hash_password, verify_password
from utils.asset_manager import ensure_assets
from utils.excel_exporter import export_sales_to_excel


class TestSanDiegoSystem(unittest.TestCase):
    """Test suite covering core business rules, database, and hardware layers."""

    @classmethod
    def setUpClass(cls):
        # Ensure test assets and database exist
        ensure_assets()
        initialize_database()

    def test_01_assets_generation(self):
        """Verify that visual assets are created with proper extensions and resolve via asset manager."""
        from utils.asset_manager import get_asset_path
        self.assertTrue(os.path.exists(get_asset_path("icono.ico")))
        self.assertTrue(os.path.exists(get_asset_path("fondo login.jpg")))
        self.assertTrue(os.path.exists(get_asset_path("icono principal.jpg")))
        self.assertTrue(os.path.exists(get_asset_path("icono San Diego")))
        self.assertTrue(os.path.exists(get_asset_path("logo San Diego")))

        # Legacy compatibility assertions
        img_dir = os.path.join(_PROJECT_ROOT, "img")
        self.assertTrue(os.path.exists(os.path.join(img_dir, "logo.png")) or os.path.exists(get_asset_path("logo.png")))
        self.assertTrue(os.path.exists(get_asset_path("asadorLogin.jpg")))
        self.assertTrue(os.path.exists(get_asset_path("logo.ico")))

    def test_02_user_authentication(self):
        """Verify PBKDF2 hashing and authentication."""
        raw_pw = "secretPass123"
        hashed = hash_password(raw_pw)
        self.assertTrue(verify_password(hashed, raw_pw))
        self.assertFalse(verify_password(hashed, "wrongPassword"))

        # Verify seeded admin
        with get_db_connection() as conn:
            admin = UserModel.authenticate(conn, "admin", "admin")
            self.assertIsNotNone(admin)
            self.assertEqual(admin.username, "admin")
            self.assertTrue(admin.is_admin)

    def test_03_weight_conversions(self):
        """Verify Colombian butcher shop weight conversions: 1 kg = 1000 g, 1 lb = 500 g."""
        # 1.5 kg -> 1500 g
        self.assertEqual(convert_quantity_to_base(1.5, "kg", "PESO"), 1500.0)
        # 2 lb -> 1000 g
        self.assertEqual(convert_quantity_to_base(2.0, "lb", "PESO"), 1000.0)
        # 500 g -> 500 g
        self.assertEqual(convert_quantity_to_base(500.0, "g", "PESO"), 500.0)
        # 5 units -> 5
        self.assertEqual(convert_quantity_to_base(5.0, "und", "UNIDAD"), 5.0)

        # Price calculations
        # Chatas: $38/g -> 1.5 kg (1500 g) = $57.000
        price_chatas = calculate_item_price(38.0, 1.5, "kg", "PESO")
        self.assertEqual(price_chatas, 57000.0)

        # Ribeye: $45/g -> 500 g = $22.500
        price_ribeye = calculate_item_price(45.0, 500.0, "g", "PESO")
        self.assertEqual(price_ribeye, 22500.0)

        # Currency formatting: COP $ 57.000
        self.assertEqual(format_currency(57000.0), "COP $ 57.000")

    def test_04_product_catalog_crud(self):
        """Verify product CRUD operations and low stock detection."""
        with get_db_connection() as conn:
            # Create test product
            new_id = ProductModel.create(
                conn=conn,
                barcode="9999001",
                name="Corte Especial Prueba",
                category_id=1,
                sale_type="PESO",
                price_base=40.0,
                stock=5000.0,
                min_stock=1000.0
            )
            prod = ProductModel.get_by_id(conn, new_id)
            self.assertIsNotNone(prod)
            self.assertEqual(prod.name, "Corte Especial Prueba")
            self.assertFalse(prod.is_low_stock)

            # Update stock below minimum
            ProductModel.update(
                conn=conn,
                product_id=new_id,
                barcode="9999001",
                name="Corte Especial Prueba",
                category_id=1,
                sale_type="PESO",
                price_base=40.0,
                stock=500.0,
                min_stock=1000.0
            )
            updated_prod = ProductModel.get_by_id(conn, new_id)
            self.assertTrue(updated_prod.is_low_stock)

            # Cleanup
            ProductModel.delete(conn, new_id)
            self.assertIsNone(ProductModel.get_by_id(conn, new_id))

    def test_05_atomic_sale_transaction_and_ticket(self):
        """Verify complete atomic checkout, inventory deduction, and ticket generation."""
        with get_db_connection() as conn:
            # Ensure sufficient test stock
            conn.execute("UPDATE products SET stock = 10000.0 WHERE id = 1 OR barcode = '1' OR barcode = '7701234000001'")
            conn.execute("UPDATE products SET stock = 20.0 WHERE id = 63 OR barcode = '63' OR barcode = '7701234000063'")
            conn.commit()

            # Pick Ribeye and Queso Paipa
            ribeye = ProductModel.get_by_barcode_or_id(conn, "1")
            queso = ProductModel.get_by_barcode_or_id(conn, "63")
            self.assertIsNotNone(ribeye)
            self.assertIsNotNone(queso)

            stock_ribeye_before = ribeye.stock
            stock_queso_before = queso.stock

            # Create cart items
            # 500g Ribeye @ $45/g = $22.500
            item1 = CartItem(
                product_id=ribeye.id,
                product_name=ribeye.name,
                category_id=ribeye.category_id,
                category_name=ribeye.category_name,
                sale_type=ribeye.sale_type,
                quantity=500.0,
                unit_selected="g",
                price_base=ribeye.price_base,
                total_price=22500.0
            )

            # 2 und Queso Paipa @ $18.000/und = $36.000
            item2 = CartItem(
                product_id=queso.id,
                product_name=queso.name,
                category_id=queso.category_id,
                category_name=queso.category_name,
                sale_type=queso.sale_type,
                quantity=2.0,
                unit_selected="und",
                price_base=queso.price_base,
                total_price=36000.0
            )

            cart = [item1, item2]
            total_expected = 58500.0
            cash_given = 60000.0

            # Test failure if cash is insufficient
            with self.assertRaises(ValueError):
                SaleModel.process_sale(conn, 1, cart, cash_received=20000.0)

            # Process valid transaction
            sale_detail = SaleModel.process_sale(conn, 1, cart, cash_received=cash_given)
            self.assertEqual(sale_detail.total, total_expected)
            self.assertEqual(sale_detail.cash_change, 1500.0)

            # Verify stock deduction
            ribeye_after = ProductModel.get_by_id(conn, ribeye.id)
            queso_after = ProductModel.get_by_id(conn, queso.id)
            self.assertEqual(ribeye_after.stock, stock_ribeye_before - 500.0)
            self.assertEqual(queso_after.stock, stock_queso_before - 2.0)

            # Generate and verify 40-col ASCII ticket
            ticket_text = format_ticket(
                invoice_number=sale_detail.invoice_number,
                timestamp=sale_detail.timestamp,
                cashier_name="Administrador",
                items=sale_detail.items,
                subtotal=sale_detail.subtotal,
                total=sale_detail.total,
                cash_received=sale_detail.cash_received,
                cash_change=sale_detail.cash_change
            )

            self.assertTrue("CARNICERIA SAN DIEGO" in ticket_text or "CARNICERÍA SAN DIEGO" in ticket_text)
            self.assertIn("TOTAL A PAGAR", ticket_text)
            self.assertIn("$ 58.500", ticket_text)
            self.assertIn(sale_detail.invoice_number, ticket_text)

    def test_06_hardware_scale_driver_and_mock(self):
        """Verify non-blocking scale driver returns realistic weight in mock mode."""
        driver = SerialScaleDriver(allow_mock=True)
        weight, unit = driver.read_weight()
        self.assertGreater(weight, 0.0)
        self.assertIn(unit, ["kg", "g"])
        driver.close()

    def test_07_barcode_scanner_burst_detection(self):
        """Verify barcode scanner fast typing detection."""
        scanned_codes = []
        listener = BarcodeScannerListener(on_scan_callback=lambda c: scanned_codes.append(c))

        # Simulate fast typing from scanner
        code = "7701001"
        for ch in code:
            listener.handle_key_press(ch, ch)
        listener.handle_key_press("", "Return")

        self.assertEqual(len(scanned_codes), 1)
        self.assertEqual(scanned_codes[0], "7701001")

    def test_08_excel_export(self):
        """Verify openpyxl spreadsheet generation with styling and formulas."""
        test_file = os.path.join(_PROJECT_ROOT, "test_report.xlsx")
        items = [
            {
                "invoice_number": "SD-000001",
                "timestamp": "2026-09-14 10:00:00",
                "cashier_name": "Admin",
                "category_name": "Carnes de Res",
                "product_name": "Chatas de Res",
                "quantity": 1.5,
                "unit_selected": "kg",
                "unit_price": 38000.0,
                "item_total": 57000.0,
                "invoice_total": 57000.0
            }
        ]
        filters = {"start_date": "2026-09-01", "end_date": "2026-09-14", "category_name": "Carnes de Res"}

        export_sales_to_excel(test_file, items, filters)
        self.assertTrue(os.path.exists(test_file))

        # Inspect generated workbook
        wb = openpyxl.load_workbook(test_file)
        ws = wb.active
        self.assertEqual(ws["A1"].value, "CARNICERÍA SAN DIEGO - VILLA DE LEYVA")
        self.assertEqual(ws["E6"].value, "Chatas de Res")
        self.assertEqual(ws["I6"].value, 57000.0)
        self.assertEqual(ws["I7"].value, "=SUM(I6:I6)")
        wb.close()

        # Clean test file
        if os.path.exists(test_file):
            os.remove(test_file)

    def test_09_model_lookups(self):
        """Verify get_by_barcode and get_sale_by_id methods work correctly."""
        with get_db_connection() as conn:
            # Test get_by_barcode
            prod = ProductModel.get_by_barcode(conn, "1")
            self.assertIsNotNone(prod)
            self.assertEqual(prod.name, "Ribeye Choice")

            # Non-existent barcode
            self.assertIsNone(ProductModel.get_by_barcode(conn, "0000000"))

            # Test get_sale_by_id
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM sales LIMIT 1")
            row = cursor.fetchone()
            if row:
                sale = SaleModel.get_sale_by_id(conn, row["id"])
                self.assertIsNotNone(sale)
                self.assertEqual(sale.id, row["id"])
                self.assertTrue(len(sale.items) > 0)


if __name__ == "__main__":
    unittest.main()
