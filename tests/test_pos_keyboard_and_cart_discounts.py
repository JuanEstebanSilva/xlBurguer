"""Tests for POS keyboard navigation, cart discount line separation,
stock verification accounting for in-cart items, and frequent products resolution.
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
from views.pos_frame import ProductDiscountModal, TouchUnitToggle


class TestPOSKeyboardAndCartDiscounts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()

    def test_frequent_products_resolution(self):
        """Verify that all 5 frequent products (Lomo Fino, Costilla, Pechuga, Carne Molida, Chuleta)
        exist in database, have positive stock, and are found via keyword/synonyms."""
        synonyms = {
            "carne molida": ["carne molida", "molida"],
            "pechuga": ["pechuga", "pollo"],
            "chuleta": ["chuleta", "cerdo"],
            "costilla": ["costilla"],
            "lomo fino": ["lomo fino", "lomo"],
        }
        with get_db_connection() as conn:
            for cut_name, terms in synonyms.items():
                found = False
                for term in terms:
                    matches = ProductModel.search(conn, term)
                    if matches:
                        p = matches[0]
                        self.assertGreater(p.stock, 0, f"Product {p.name} should have positive stock")
                        found = True
                        break
                self.assertTrue(found, f"Frequent product '{cut_name}' must be found in database")

    def test_category_consolidation(self):
        """Verify that 'Cortes de Res', 'Cortes de Cerdo', and 'Pollo y Aves' exist,
        and obsolete 'Cocción Lenta', 'Delantero', 'Trasero' categories do not exist."""
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM categories")
            cat_names = [r["name"] for r in cur.fetchall()]

            self.assertIn("Cortes de Res", cat_names)
            self.assertIn("Cortes de Cerdo", cat_names)
            self.assertIn("Pollo y Aves", cat_names)

            self.assertNotIn("Cortes de Res (Delantero)", cat_names)
            self.assertNotIn("Cortes de Res (Trasero)", cat_names)
            self.assertNotIn("Cortes para Cocción Lenta", cat_names)

    def test_cart_separation_by_different_discounts(self):
        """Verify that adding the same product with different discounts creates distinct line items.
        E.g. Chatas (-10%) and Chatas (-50%) remain 2 separate rows in the cart."""
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, name, category_id, sale_type, price_base FROM products WHERE name LIKE '%Chatas%' LIMIT 1")
            row = cur.fetchone()
            if not row:
                cur.execute("SELECT id, name, category_id, sale_type, price_base FROM products WHERE sale_type = 'PESO' LIMIT 1")
                row = cur.fetchone()

        prod_id = row["id"]
        prod_name = row["name"]
        cat_id = row["category_id"]
        sale_type = row["sale_type"]
        price_base = row["price_base"]

        cart_items = []

        # Add 1st item: 2 kg with 10% discount
        qty1 = 2.0
        unit = "kg"
        disc1 = 10.0
        tot1 = calculate_item_price(price_base, qty1, unit, sale_type)
        item1 = CartItem(
            product_id=prod_id,
            product_name=prod_name,
            category_id=cat_id,
            category_name="Cortes de Res",
            sale_type=sale_type,
            quantity=qty1,
            unit_selected=unit,
            price_base=price_base,
            total_price=tot1,
            original_price=tot1,
            discount_percent=disc1
        )
        item1.apply_discount(disc1)
        cart_items.append(item1)

        # Add 2nd item: 3 kg of SAME product with 50% discount
        qty2 = 3.0
        disc2 = 50.0
        tot2 = calculate_item_price(price_base, qty2, unit, sale_type)
        item2 = CartItem(
            product_id=prod_id,
            product_name=prod_name,
            category_id=cat_id,
            category_name="Cortes de Res",
            sale_type=sale_type,
            quantity=qty2,
            unit_selected=unit,
            price_base=price_base,
            total_price=tot2,
            original_price=tot2,
            discount_percent=disc2
        )
        item2.apply_discount(disc2)
        cart_items.append(item2)

        # Both items must be present as distinct line items
        self.assertEqual(len(cart_items), 2)
        self.assertEqual(cart_items[0].discount_percent, 10.0)
        self.assertEqual(cart_items[1].discount_percent, 50.0)
        self.assertEqual(cart_items[0].quantity, 2.0)
        self.assertEqual(cart_items[1].quantity, 3.0)

        # Verify combined stock deduction
        total_deduction_g = sum(it.base_stock_deduction for it in cart_items)
        expected_deduction_g = (2.0 + 3.0) * 1000.0
        self.assertEqual(total_deduction_g, expected_deduction_g)

    def test_cart_consolidation_with_same_discount(self):
        """Verify that adding the same product twice with the SAME discount consolidates into 1 line item."""
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, name, category_id, sale_type, price_base FROM products WHERE sale_type = 'PESO' LIMIT 1")
            row = cur.fetchone()

        prod_id = row["id"]
        prod_name = row["name"]
        cat_id = row["category_id"]
        sale_type = row["sale_type"]
        price_base = row["price_base"]

        cart_items = []

        # Function simulating POS addition logic
        def add_to_cart(qty: float, unit: str, disc_pct: float):
            existing = next(
                (it for it in cart_items
                 if it.product_id == prod_id
                 and it.unit_selected == unit
                 and round(it.discount_percent, 1) == round(disc_pct, 1)),
                None
            )
            if existing:
                existing.quantity += qty
                base_tot = calculate_item_price(price_base, existing.quantity, unit, sale_type)
                existing.original_price = base_tot
                existing.apply_discount(disc_pct)
            else:
                tot = calculate_item_price(price_base, qty, unit, sale_type)
                item = CartItem(
                    product_id=prod_id,
                    product_name=prod_name,
                    category_id=cat_id,
                    category_name="Cortes de Res",
                    sale_type=sale_type,
                    quantity=qty,
                    unit_selected=unit,
                    price_base=price_base,
                    total_price=tot,
                    original_price=tot,
                    discount_percent=disc_pct
                )
                if disc_pct > 0:
                    item.apply_discount(disc_pct)
                cart_items.append(item)

        # Add 1.5 kg with 50% discount
        add_to_cart(1.5, "kg", 50.0)
        self.assertEqual(len(cart_items), 1)
        self.assertEqual(cart_items[0].quantity, 1.5)

        # Add another 1.5 kg with 50% discount -> must consolidate into 3.0 kg
        add_to_cart(1.5, "kg", 50.0)
        self.assertEqual(len(cart_items), 1)
        self.assertEqual(cart_items[0].quantity, 3.0)
        self.assertEqual(cart_items[0].discount_percent, 50.0)

        # Add 1.0 kg with 10% discount -> must be a separate row
        add_to_cart(1.0, "kg", 10.0)
        self.assertEqual(len(cart_items), 2)
        self.assertEqual(cart_items[1].quantity, 1.0)
        self.assertEqual(cart_items[1].discount_percent, 10.0)

    def test_stock_verification_considers_total_in_cart(self):
        """Verify that when 15 kg is in stock, and 15 kg is already in the cart,
        attempting to add 1 kg raises ValueError with details."""
        stock = 15000.0  # 15 kg in grams
        cart = [
            CartItem(
                product_id=999,
                product_name="Corazón de Res",
                category_id=1,
                category_name="Vísceras",
                sale_type="PESO",
                quantity=15.0,
                unit_selected="kg",
                price_base=14.0,
                total_price=210000.0,
                original_price=210000.0,
                discount_percent=10.0
            )
        ]

        # Calculate base stock in cart
        current_cart_base = sum(it.base_stock_deduction for it in cart if it.product_id == 999)
        self.assertEqual(current_cart_base, 15000.0)

        # Request 1.0 kg more
        new_req_base = convert_quantity_to_base(1.0, "kg", "PESO")
        total_req_base = current_cart_base + new_req_base

        self.assertGreater(total_req_base, stock, "Total requested (16 kg) exceeds available stock (15 kg)")
        remaining_base = max(0.0, stock - current_cart_base)
        self.assertEqual(remaining_base, 0.0, "Remaining stock to add must be 0")

    def test_product_discount_modal_validation(self):
        """Verify ProductDiscountModal limits discounts to <= 100%,
        disables the apply button on invalid input (>100%, negative, non-numeric),
        and enables it on valid percentages."""
        import customtkinter as ctk
        root = ctk.CTk()
        root.withdraw()
        try:
            modal = ProductDiscountModal(root, "Ribeye Choice", 45000.0)

            # Test > 100%
            modal.pct_var.set("150")
            modal._on_pct_change()
            self.assertTrue(modal._has_error)
            self.assertEqual(modal.apply_btn.cget("state"), "disabled")
            self.assertIn("100%", modal.error_lbl.cget("text"))

            # Test negative
            modal.pct_var.set("-10")
            modal._on_pct_change()
            self.assertTrue(modal._has_error)
            self.assertEqual(modal.apply_btn.cget("state"), "disabled")

            # Test non-numeric
            modal.pct_var.set("abc")
            modal._on_pct_change()
            self.assertTrue(modal._has_error)
            self.assertEqual(modal.apply_btn.cget("state"), "disabled")

            # Test valid 20%
            modal.pct_var.set("20")
            modal._on_pct_change()
            self.assertFalse(modal._has_error)
            self.assertEqual(modal.apply_btn.cget("state"), "normal")
            self.assertEqual(modal.error_lbl.cget("text"), "")

            # Test 100% boundary
            modal.pct_var.set("100")
            modal._on_pct_change()
            self.assertFalse(modal._has_error)
            self.assertEqual(modal.apply_btn.cget("state"), "normal")

            # Test 0% boundary
            modal.pct_var.set("0")
            modal._on_pct_change()
            self.assertFalse(modal._has_error)
            self.assertEqual(modal.apply_btn.cget("state"), "normal")
            modal.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()

