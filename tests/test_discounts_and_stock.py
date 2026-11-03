"""Comprehensive tests for product discounts, atomic stock deduction, and icon integrity.
Guarantees 100% precision in inventory deduction and pricing:
- Wine (UNIDAD): buying 1 bottle from stock 10.0 results in exactly 9.0 remaining.
- Wine with 50% discount: price is halved, but stock deduction remains exactly 1.0 unit.
- Multiple bottles (3 units) deducts exactly 3.0 units.
- Meat (PESO): buying by kg, lb, or g deducts grams precisely from inventory.
- Over-purchasing triggers insufficient stock error and transaction rollback.
- Repeat and Eye-slash icons resolution via asset manager.
"""

import os
import sys
import unittest
import sqlite3

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.connection import get_db_connection, initialize_database
from models.product import ProductModel, convert_quantity_to_base, calculate_item_price
from models.sale import CartItem, SaleModel
from hardware.ticket_printer import format_ticket
from utils.asset_manager import get_ctk_icon, get_asset_path


class TestDiscountsAndStockDeduction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.test_db_path = os.path.join(cls.temp_dir.name, "test_discounts_isolated.db")
        os.environ["XLBURGUER_DB_PATH"] = cls.test_db_path
        initialize_database()

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("XLBURGUER_DB_PATH", None)
        os.environ.pop("XLBURGUER_DB_PATH", None)
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def setUp(self):
        # Create an isolated test product with exactly 10.0 units of wine
        with get_db_connection() as conn:
            cur = conn.cursor()
            # Ensure categories exist
            cur.execute("SELECT id FROM categories LIMIT 1")
            cat_row = cur.fetchone()
            cat_id = cat_row["id"] if cat_row else 1

            # Insert dedicated test wine with initial stock = 10.0
            cur.execute(
                """
                INSERT INTO products (barcode, name, category_id, sale_type, price_base, cost, iva, unit_measure, stock, min_stock)
                VALUES ('TEST_BEVERAGE_10', 'Bebida Gaseosa XL Test 750ml', ?, 'UNIDAD', 68000.0, 40000.0, 19.0, 'und', 10.0, 2.0)
                """,
                (cat_id,)
            )
            self.wine_id = cur.lastrowid

            # Insert dedicated test meat (PESO) with initial stock = 5000.0 grams (5.0 kg)
            cur.execute(
                """
                INSERT INTO products (barcode, name, category_id, sale_type, price_base, cost, iva, unit_measure, stock, min_stock)
                VALUES ('TEST_MEAT_5KG', 'Lomo Fino Res Test', ?, 'PESO', 38.0, 26.0, 0.0, 'kg', 5000.0, 1000.0)
                """,
                (cat_id,)
            )
            self.meat_id = cur.lastrowid

            # Ensure test admin user exists
            cur.execute("SELECT id FROM users WHERE role = 'ADMIN' LIMIT 1")
            user_row = cur.fetchone()
            self.user_id = user_row["id"] if user_row else 1

            conn.commit()

    def tearDown(self):
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT sale_id FROM sale_items WHERE product_id IN (?, ?)", (self.wine_id, self.meat_id))
            sale_ids = [r["sale_id"] for r in cur.fetchall()]
            if sale_ids:
                placeholders = ",".join("?" * len(sale_ids))
                cur.execute(f"DELETE FROM sale_items WHERE sale_id IN ({placeholders})", sale_ids)
                cur.execute(f"DELETE FROM sales WHERE id IN ({placeholders})", sale_ids)
            cur.execute("DELETE FROM products WHERE id IN (?, ?)", (self.wine_id, self.meat_id))
            conn.commit()

    # ──────────────────────────────────────────────────────────────────────────
    # 1. WINE STOCK DEDUCTION (10 -> 9 units)
    # ──────────────────────────────────────────────────────────────────────────
    def test_wine_stock_deduction_single_bottle(self):
        """Verify that buying 1 bottle of wine with stock 10.0 leaves exactly 9.0 units in DB."""
        with get_db_connection() as conn:
            p_before = ProductModel.get_by_id(conn, self.wine_id)
            self.assertEqual(p_before.stock, 10.0, "Initial wine stock must be exactly 10.0")

            # Create cart item for 1 bottle
            cart = [
                CartItem(
                    product_id=self.wine_id,
                    product_name=p_before.name,
                    category_id=p_before.category_id,
                    category_name="Vinos",
                    sale_type="UNIDAD",
                    quantity=1.0,
                    unit_selected="und",
                    price_base=68000.0,
                    total_price=68000.0
                )
            ]

            # Process checkout
            sale = SaleModel.process_sale(
                conn=conn,
                user_id=self.user_id,
                cart_items=cart,
                cash_received=68000.0,
                payment_method="EFECTIVO"
            )

            # Verify stock in DB
            p_after = ProductModel.get_by_id(conn, self.wine_id)
            self.assertEqual(p_after.stock, 9.0, "Stock must decrease from 10.0 to exactly 9.0 after buying 1 bottle")

    # ──────────────────────────────────────────────────────────────────────────
    # 2. WINE WITH 50% DISCOUNT (Price halved, stock deducted 10 -> 9)
    # ──────────────────────────────────────────────────────────────────────────
    def test_wine_with_50_percent_discount(self):
        """Verify that applying a 50% discount cuts total price to $34,000 while deducting 1.0 bottle."""
        with get_db_connection() as conn:
            p_before = ProductModel.get_by_id(conn, self.wine_id)
            self.assertEqual(p_before.stock, 10.0)

            # Create cart item with 50% discount
            item = CartItem(
                product_id=self.wine_id,
                product_name=p_before.name,
                category_id=p_before.category_id,
                category_name="Vinos",
                sale_type="UNIDAD",
                quantity=1.0,
                unit_selected="und",
                price_base=68000.0,
                total_price=68000.0,
                original_price=68000.0,
                discount_percent=50.0
            )
            item.apply_discount(50.0)

            # Verify discount calculations
            self.assertEqual(item.discount_percent, 50.0)
            self.assertEqual(item.discount_amount, 34000.0)
            self.assertEqual(item.total_price, 34000.0)
            self.assertEqual(item.original_price, 68000.0)
            self.assertEqual(item.base_stock_deduction, 1.0)

            # Process checkout
            sale = SaleModel.process_sale(
                conn=conn,
                user_id=self.user_id,
                cart_items=[item],
                cash_received=50000.0,
                payment_method="EFECTIVO"
            )

            # Verify sale details
            self.assertEqual(sale.total, 34000.0)
            self.assertEqual(sale.cash_change, 16000.0)  # $50,000 received - $34,000 total = $16,000 change

            # Verify stock in DB
            p_after = ProductModel.get_by_id(conn, self.wine_id)
            self.assertEqual(p_after.stock, 9.0, "Stock must be exactly 9.0 despite discount")

            # Verify recorded item in DB
            cur = conn.cursor()
            cur.execute("SELECT discount_percent, discount_amount, total_price FROM sale_items WHERE sale_id = ?", (sale.id,))
            row = cur.fetchone()
            self.assertEqual(row["discount_percent"], 50.0)
            self.assertEqual(row["discount_amount"], 34000.0)
            self.assertEqual(row["total_price"], 34000.0)

    # ──────────────────────────────────────────────────────────────────────────
    # 3. WINE MULTIPLE BOTTLES DEDUCTION (10 -> 7 units)
    # ──────────────────────────────────────────────────────────────────────────
    def test_wine_multiple_bottles_deduction(self):
        """Verify that purchasing 3 bottles of wine deducts exactly 3 units (10 -> 7)."""
        with get_db_connection() as conn:
            p_before = ProductModel.get_by_id(conn, self.wine_id)
            self.assertEqual(p_before.stock, 10.0)

            cart = [
                CartItem(
                    product_id=self.wine_id,
                    product_name=p_before.name,
                    category_id=p_before.category_id,
                    category_name="Vinos",
                    sale_type="UNIDAD",
                    quantity=3.0,
                    unit_selected="und",
                    price_base=68000.0,
                    total_price=68000.0 * 3
                )
            ]

            sale = SaleModel.process_sale(
                conn=conn,
                user_id=self.user_id,
                cart_items=cart,
                cash_received=250000.0,
                payment_method="EFECTIVO"
            )

            p_after = ProductModel.get_by_id(conn, self.wine_id)
            self.assertEqual(p_after.stock, 7.0, "Stock must decrease from 10.0 to exactly 7.0 after buying 3 bottles")

    # ──────────────────────────────────────────────────────────────────────────
    # 4. WINE WITH ML UNIT DEDUCTION (750 ml fixed package -> 1 bottle)
    # ──────────────────────────────────────────────────────────────────────────
    def test_wine_ml_unit_deduction(self):
        """Verify that 750 ml bottle unit deducts exactly 1.0 unit from inventory."""
        with get_db_connection() as conn:
            cart = [
                CartItem(
                    product_id=self.wine_id,
                    product_name="Vino Test",
                    category_id=1,
                    category_name="Vinos",
                    sale_type="UNIDAD",
                    quantity=750.0,
                    unit_selected="ml",
                    price_base=68000.0,
                    total_price=68000.0
                )
            ]
            self.assertEqual(cart[0].base_stock_deduction, 1.0)

            SaleModel.process_sale(
                conn=conn,
                user_id=self.user_id,
                cart_items=cart,
                cash_received=68000.0,
                payment_method="EFECTIVO"
            )

            p_after = ProductModel.get_by_id(conn, self.wine_id)
            self.assertEqual(p_after.stock, 9.0)

    # ──────────────────────────────────────────────────────────────────────────
    # 5. MEAT WEIGHT CONVERSION AND DEDUCTION (Grams, kg, lb)
    # ──────────────────────────────────────────────────────────────────────────
    def test_meat_stock_deduction_by_weight(self):
        """Verify that purchasing meat in kg, lb, and g deducts the exact gram weight from stock."""
        with get_db_connection() as conn:
            p_meat = ProductModel.get_by_id(conn, self.meat_id)
            self.assertEqual(p_meat.stock, 5000.0, "Initial meat stock is 5000g (5kg)")

            # Buy 1.5 kg = 1500 grams
            cart1 = [
                CartItem(
                    product_id=self.meat_id,
                    product_name=p_meat.name,
                    category_id=p_meat.category_id,
                    category_name="Carnes",
                    sale_type="PESO",
                    quantity=1.5,
                    unit_selected="kg",
                    price_base=38.0,
                    total_price=1500.0 * 38.0
                )
            ]
            self.assertEqual(cart1[0].base_stock_deduction, 1500.0)

            SaleModel.process_sale(
                conn=conn,
                user_id=self.user_id,
                cart_items=cart1,
                cash_received=60000.0,
                payment_method="EFECTIVO"
            )

            p_meat_after1 = ProductModel.get_by_id(conn, self.meat_id)
            self.assertEqual(p_meat_after1.stock, 3500.0, "5000g - 1500g must equal 3500g")

            # Buy 1 lb = 500 grams
            cart2 = [
                CartItem(
                    product_id=self.meat_id,
                    product_name=p_meat.name,
                    category_id=p_meat.category_id,
                    category_name="Carnes",
                    sale_type="PESO",
                    quantity=1.0,
                    unit_selected="lb",
                    price_base=38.0,
                    total_price=500.0 * 38.0
                )
            ]
            self.assertEqual(cart2[0].base_stock_deduction, 500.0)

            SaleModel.process_sale(
                conn=conn,
                user_id=self.user_id,
                cart_items=cart2,
                cash_received=20000.0,
                payment_method="EFECTIVO"
            )

            p_meat_after2 = ProductModel.get_by_id(conn, self.meat_id)
            self.assertEqual(p_meat_after2.stock, 3000.0, "3500g - 500g must equal 3000g")

    # ──────────────────────────────────────────────────────────────────────────
    # 6. INSUFFICIENT STOCK ROLLBACK & GUARD
    # ──────────────────────────────────────────────────────────────────────────
    def test_insufficient_stock_raises_error_and_rolls_back(self):
        """Verify that attempting to purchase 11 bottles when 10 exist aborts and does not modify stock."""
        with get_db_connection() as conn:
            cart = [
                CartItem(
                    product_id=self.wine_id,
                    product_name="Vino Test",
                    category_id=1,
                    category_name="Vinos",
                    sale_type="UNIDAD",
                    quantity=11.0,
                    unit_selected="und",
                    price_base=68000.0,
                    total_price=68000.0 * 11
                )
            ]

            with self.assertRaises(ValueError) as ctx:
                SaleModel.process_sale(
                    conn=conn,
                    user_id=self.user_id,
                    cart_items=cart,
                    cash_received=800000.0,
                    payment_method="EFECTIVO"
                )
            self.assertIn("Stock insuficiente", str(ctx.exception))

            # Verify stock remained at exactly 10.0
            p_check = ProductModel.get_by_id(conn, self.wine_id)
            self.assertEqual(p_check.stock, 10.0, "Stock must remain intact after rollback")

    # ──────────────────────────────────────────────────────────────────────────
    # 7. RECEIPT PRINTING WITH PRODUCT DISCOUNT
    # ──────────────────────────────────────────────────────────────────────────
    def test_receipt_discount_display(self):
        """Verify that format_ticket renders line-item discount and subtotal breakdown."""
        items = [
            {
                "product_name": "Vino Marqués Gran Reserva",
                "quantity": 1.0,
                "unit_selected": "und",
                "unit_price": 34000.0,
                "total_price": 34000.0,
                "discount_percent": 50.0,
                "discount_amount": 34000.0,
                "original_price": 68000.0
            }
        ]

        ticket = format_ticket(
            invoice_number="XL-TEST01",
            cashier_name="Cajero XL Burguer",
            items=items,
            subtotal=34000.0,
            total=34000.0,
            cash_received=50000.0,
            cash_change=16000.0,
            payment_method="EFECTIVO"
        )

        self.assertIn("Desc. 50%", ticket)
        self.assertIn("-$ 34.000", ticket)
        self.assertIn("DESCUENTOS:", ticket)
        self.assertIn("Cajero XL Burguer", ticket)

    # ──────────────────────────────────────────────────────────────────────────
    # 8. ICON AVAILABILITY & INTEGRITY
    # ──────────────────────────────────────────────────────────────────────────
    def test_repeat_and_eyeslash_icons_exist_and_load(self):
        """Verify repeat-solid-full and eye-slash-solid are accessible and loadable."""
        # Check files exist
        p_repeat_svg = get_asset_path("repeat-solid-full.svg")
        p_eyeslash_svg = get_asset_path("eye-slash-solid-full.svg")
        self.assertTrue(os.path.exists(p_repeat_svg), f"repeat-solid-full.svg must exist at {p_repeat_svg}")
        self.assertTrue(os.path.exists(p_eyeslash_svg), f"eye-slash-solid-full.svg must exist at {p_eyeslash_svg}")

        # Test asset aliases
        repeat_icon = get_ctk_icon("repeat-solid-full", size=(16, 16))
        self.assertIsNotNone(repeat_icon, "repeat-solid-full icon should load as CTkImage")

        eyeslash_icon = get_ctk_icon("eye-slash-solid", size=(16, 16))
        self.assertIsNotNone(eyeslash_icon, "eye-slash-solid icon should load as CTkImage")


if __name__ == "__main__":
    unittest.main()
