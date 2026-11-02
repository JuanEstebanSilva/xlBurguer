"""Comprehensive Automated Test Suite for XL Burguer.
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


class TestXLBurguerSystem(unittest.TestCase):
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
        self.assertTrue(os.path.exists(get_asset_path("icono XL Burguer")))
        self.assertTrue(os.path.exists(get_asset_path("logo XL Burguer")))

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
            admin = UserModel.authenticate(conn, "admin", "admin123")
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
        """Verify complete atomic checkout, inventory deduction, and ticket generation for XL Burguer."""
        with get_db_connection() as conn:
            burger = ProductModel.get_by_barcode(conn, "101")  # Hamburguesa Clásica XL (18,000)
            coca = ProductModel.get_by_barcode(conn, "601")    # Coca-Cola 400ml (5,000)
            self.assertIsNotNone(burger)
            self.assertIsNotNone(coca)

            coca_stock_before = coca.stock

            # 1 und Hamburguesa Clásica XL @ $18.000
            item1 = CartItem(
                product_id=burger.id,
                product_name=burger.name,
                category_id=burger.category_id,
                category_name=burger.category_name,
                sale_type=burger.sale_type,
                quantity=1.0,
                unit_selected="und",
                price_base=burger.price_base,
                total_price=18000.0
            )

            # 2 und Coca-Cola @ $5.000 = $10.000
            item2 = CartItem(
                product_id=coca.id,
                product_name=coca.name,
                category_id=coca.category_id,
                category_name=coca.category_name,
                sale_type=coca.sale_type,
                quantity=2.0,
                unit_selected="und",
                price_base=coca.price_base,
                total_price=10000.0
            )

            cart = [item1, item2]
            total_expected = 28000.0
            cash_given = 30000.0

            # Test failure if cash is insufficient
            with self.assertRaises(ValueError):
                SaleModel.process_sale(conn, 1, cart, cash_received=10000.0)

            # Process valid transaction
            sale_detail = SaleModel.process_sale(conn, 1, cart, cash_received=cash_given)
            self.assertEqual(sale_detail.total, total_expected)
            self.assertEqual(sale_detail.cash_change, 2000.0)

            # Verify direct stock deduction for drink without recipe
            coca_after = ProductModel.get_by_id(conn, coca.id)
            self.assertEqual(coca_after.stock, coca_stock_before - 2.0)

            # Generate and verify 40-col ASCII ticket with XL Burguer branding
            ticket_text = format_ticket(sale_detail)

            self.assertIn("XL BURGUER", ticket_text)
            self.assertNotIn("CARNICERIA", ticket_text)
            self.assertIn("TOTAL A PAGAR", ticket_text)
            self.assertIn(sale_detail.invoice_number, ticket_text)
            self.assertTrue(sale_detail.invoice_number.startswith("XL-"))

    def test_06_fast_food_recipe_ingredient_grams_deduction(self):
        """Verify that prepared products track ingredients in grams (software inventory, no physical scale)."""
        from models.ingredient import IngredientModel
        with get_db_connection() as conn:
            # Check burger recipe: requires carne (125g) and pan (80g)
            meat_ing = next(i for i in IngredientModel.get_all(conn) if "Carne" in i.name)
            stock_before = meat_ing.stock_g
            burger = ProductModel.get_by_barcode(conn, "101")

            cart = [CartItem(
                product_id=burger.id,
                product_name=burger.name,
                category_id=burger.category_id,
                category_name=burger.category_name,
                sale_type="UNIDAD",
                quantity=2.0,
                unit_selected="und",
                price_base=burger.price_base,
                total_price=burger.price_base * 2.0
            )]

            sale = SaleModel.process_sale(conn, 1, cart, cash_received=burger.price_base * 2.0)
            meat_ing_after = IngredientModel.get_by_id(conn, meat_ing.id)

            # 2 burgers * 125g = 250g deducted
            self.assertEqual(meat_ing_after.stock_g, stock_before - 250.0)

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
                "invoice_number": "XL-000001",
                "timestamp": "2026-09-14 10:00:00",
                "cashier_name": "Admin",
                "category_name": "HAMBURGUESAS",
                "product_name": "Hamburguesa Clásica XL",
                "quantity": 1.5,
                "unit_selected": "kg",
                "unit_price": 38000.0,
                "item_total": 57000.0,
                "invoice_total": 57000.0
            }
        ]
        filters = {"start_date": "2026-09-01", "end_date": "2026-09-14", "category_name": "HAMBURGUESAS"}

        export_sales_to_excel(test_file, items, filters)
        self.assertTrue(os.path.exists(test_file))

        # Inspect generated workbook
        wb = openpyxl.load_workbook(test_file)
        ws = wb.active
        self.assertEqual(ws["A1"].value, "XL BURGUER - SISTEMA POS & GESTIÓN")
        self.assertEqual(ws["E6"].value, "Hamburguesa Clásica XL")
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
            prod = ProductModel.get_by_barcode(conn, "101")
            self.assertIsNotNone(prod)
            self.assertEqual(prod.name, "Hamburguesa Clásica XL")

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
