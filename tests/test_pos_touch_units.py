"""Unit and integration tests for touch-friendly unit toggles, stock alerts, and fixed packages (wine 750ml)."""

import os
import sys
import unittest
from unittest.mock import patch

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.connection import initialize_database, get_db_connection
from main import App
from models.user import User
from models.product import ProductModel, convert_quantity_to_base, calculate_item_price
from utils.asset_manager import ensure_assets
from utils.theme import DarkTheme


class TestPOSTouchUnitsAndFixedPackages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_assets()
        initialize_database()

    def setUp(self):
        self.patcher_err = patch("tkinter.messagebox.showerror")
        self.patcher_warn = patch("tkinter.messagebox.showwarning")
        self.mock_err = self.patcher_err.start()
        self.mock_warn = self.patcher_warn.start()

        self.app = App()
        self.app.update_idletasks()
        self.test_user = User(id=1, username="admin", password_hash="", full_name="Administrador", role="ADMIN")
        self.app.on_login_success(self.test_user)
        self.app.update_idletasks()
        self.pos = self.app.frames["pos"]

    def tearDown(self):
        try:
            self.patcher_err.stop()
            self.patcher_warn.stop()
        except Exception:
            pass
        try:
            self.app._on_close()
            self.app.update()
        except Exception:
            pass

    def test_peso_product_uniform_touch_buttons(self):
        """Test PESO products have [kg], [lb], [g] uniform touch buttons."""
        with get_db_connection() as conn:
            prods = ProductModel.get_all(conn)
            p_meat = next((p for p in prods if p.sale_type == "PESO"), None)
            if not p_meat:
                pid = ProductModel.create(conn, barcode="TESTPESO1", name="Test Item Peso", category_id=1, sale_type="PESO", price_base=30.0, unit_measure="kg", stock=5000.0)
                p_meat = ProductModel.get_by_id(conn, pid)
        self.pos._select_product(p_meat)
        self.app.update_idletasks()

        # Check buttons
        self.assertEqual(list(self.pos.unit_toggle.buttons.keys()), ["kg", "lb", "g"])
        self.assertEqual(self.pos.unit_toggle.get(), "kg")
        self.assertEqual(self.pos.quantity_var.get(), "1.00")
        self.assertEqual(self.pos.unit_disp_lbl.cget("text"), "kg")
        self.assertEqual(self.pos.qty_entry.cget("state"), "normal")

        # Check button width equality
        widths = [btn.cget("width") for btn in self.pos.unit_toggle.buttons.values()]
        self.assertTrue(all(w == widths[0] for w in widths), f"Buttons must have equal width: {widths}")

        # Toggling units via touch
        self.pos._on_unit_change("lb")
        self.assertEqual(self.pos.current_unit, "lb")
        self.assertEqual(self.pos.unit_disp_lbl.cget("text"), "lb")
        self.pos._on_unit_change("g")
        self.assertEqual(self.pos.current_unit, "g")
        self.assertEqual(self.pos.unit_disp_lbl.cget("text"), "g")

    def test_stock_warning_red_color(self):
        """Test that products with low stock display the stock label in RED."""
        with get_db_connection() as conn:
            prods = ProductModel.get_all(conn)
        p_low = next((p for p in prods if p.is_low_stock), None)
        orig_id = None
        orig_stock = None
        if not p_low:
            p_low = prods[0]
            orig_id = p_low.id
            orig_stock = p_low.stock
            with get_db_connection() as conn:
                ProductModel.update_stock(conn, p_low.id, p_low.min_stock * 0.5)
            with get_db_connection() as conn:
                p_low = ProductModel.get_by_id(conn, p_low.id)

        try:
            self.pos._select_product(p_low)
            self.app.update_idletasks()
            lbl_color = self.pos.active_prod_stock_lbl.cget("text_color")
            self.assertEqual(lbl_color, DarkTheme.DANGER, f"Low stock should be red {DarkTheme.DANGER}, got {lbl_color}")
        finally:
            if orig_id is not None and orig_stock is not None:
                with get_db_connection() as conn:
                    ProductModel.update_stock(conn, orig_id, orig_stock)

    def test_unidad_product_single_clean_button(self):
        """Test standard UNIDAD product displays single clean button without extra borders or artifacts."""
        with get_db_connection() as conn:
            prods = ProductModel.get_all(conn)
        p_unit = next(p for p in prods if p.sale_type == "UNIDAD" and not p.fixed_package_info)
        self.pos._select_product(p_unit)
        self.app.update_idletasks()

        self.assertEqual(list(self.pos.unit_toggle.buttons.keys()), ["und"])
        self.assertEqual(self.pos.unit_toggle.get(), "und")
        self.assertEqual(self.pos.quantity_var.get(), "1")
        self.assertEqual(self.pos.unit_disp_lbl.cget("text"), "und")
        self.assertEqual(self.pos.qty_entry.cget("state"), "normal")
        self.assertFalse(self.pos._is_fixed_qty)

    def test_wine_fixed_package_non_editable_quantity(self):
        """Test wine bottle (750 ml) loads with ml unit, 750 ml quantity, non-editable, and 1 unit inventory deduction."""
        with get_db_connection() as conn:
            prods = ProductModel.get_all(conn)
        p_vino = next((p for p in prods if p.fixed_package_info), None)
        self.assertIsNotNone(p_vino, "Wine product should exist")
        with get_db_connection() as conn:
            ProductModel.update_stock(conn, p_vino.id, 50.0)
        with get_db_connection() as conn:
            p_vino = ProductModel.get_by_id(conn, p_vino.id)

        self.pos._select_product(p_vino)
        self.app.update_idletasks()

        # Check unit button and display
        self.assertEqual(list(self.pos.unit_toggle.buttons.keys()), ["ml"])
        self.assertEqual(self.pos.unit_toggle.get(), "ml")
        self.assertEqual(self.pos.current_unit, "ml")
        pkg_qty = str(int(p_vino.fixed_package_info[0])); self.assertEqual(self.pos.quantity_var.get(), pkg_qty)
        self.assertEqual(self.pos.unit_disp_lbl.cget("text"), "ml")
        self.assertTrue(self.pos._is_fixed_qty)
        self.assertEqual(self.pos.qty_entry.cget("state"), "readonly")
        # ml button is in normal state with bright white text (not dimmed/disabled)
        ml_btn = self.pos.unit_toggle.buttons["ml"]
        self.assertEqual(ml_btn.cget("state"), "normal")
        self.assertEqual(ml_btn.cget("text_color"), "#FFFFFF")

        # Test keypad inputs are ignored for fixed package products
        self.pos._on_keypad_press("5")
        pkg_qty = str(int(p_vino.fixed_package_info[0])); self.assertEqual(self.pos.quantity_var.get(), pkg_qty)
        self.pos._on_keypad_press("C")
        pkg_qty = str(int(p_vino.fixed_package_info[0])); self.assertEqual(self.pos.quantity_var.get(), pkg_qty)
        self.pos._on_keypad_press("⌫")
        pkg_qty = str(int(p_vino.fixed_package_info[0])); self.assertEqual(self.pos.quantity_var.get(), pkg_qty)
        self.pos._on_keypad_press("± Unid")
        pkg_qty = str(int(p_vino.fixed_package_info[0])); self.assertEqual(self.pos.quantity_var.get(), pkg_qty)
        self.assertEqual(self.pos.current_unit, "ml")

        # Check price is formatted correctly in subtotal
        price_fmt = f"{int(p_vino.price_base):,}".replace(",", ".")
        self.assertIn(price_fmt, self.pos.item_subtotal_var.get())

        # Test adding to cart
        cart_len_before = len(self.pos.cart_items)
        self.pos._add_active_product_to_cart()
        self.assertEqual(len(self.pos.cart_items), cart_len_before + 1)

        item = self.pos.cart_items[-1]
        self.assertEqual(item.unit_selected, "ml")
        self.assertEqual(item.quantity, p_vino.fixed_package_info[0])
        self.assertEqual(item.total_price, p_vino.price_base)
        self.assertEqual(item.base_stock_deduction, 1.0)  # Exactly 1 bottle deducted from inventory!

    def test_cart_item_consolidation(self):
        """Test user scenario: adding Wine -> Ribeye -> Wine again consolidates into 2 bottles of Wine and 1 Ribeye."""
        with get_db_connection() as conn:
            prods = ProductModel.get_all(conn)
        p_vino = next((p for p in prods if p.fixed_package_info), None)
        p_meat = next((p for p in prods if p.sale_type == "PESO"), None)
        if not p_meat:
            with get_db_connection() as conn:
                pid = ProductModel.create(conn, barcode="TESTPESO2", name="Test Item Peso", category_id=1, sale_type="PESO", price_base=30.0, unit_measure="kg", stock=50000.0)
                p_meat = ProductModel.get_by_id(conn, pid)
        self.assertIsNotNone(p_vino)
        self.assertIsNotNone(p_meat)

        with get_db_connection() as conn:
            ProductModel.update_stock(conn, p_vino.id, 50.0)
            ProductModel.update_stock(conn, p_meat.id, 50000.0)
        with get_db_connection() as conn:
            p_vino = ProductModel.get_by_id(conn, p_vino.id)
            p_meat = ProductModel.get_by_id(conn, p_meat.id)

        self.pos.cart_items.clear()

        # 1. Add 1 bottle of wine
        self.pos._select_product(p_vino)
        self.pos._add_active_product_to_cart()
        self.assertEqual(len(self.pos.cart_items), 1)
        self.assertEqual(self.pos.cart_items[0].product_id, p_vino.id)
        self.assertEqual(self.pos.cart_items[0].quantity, p_vino.fixed_package_info[0])
        self.assertEqual(self.pos.cart_items[0].total_price, p_vino.price_base)
        self.assertEqual(self.pos.cart_items[0].base_stock_deduction, 1.0)

        # 2. Add 1 lb of meat
        self.pos._select_product(p_meat)
        self.pos._on_unit_change("lb")
        self.pos.quantity_var.set("1.00")
        self.pos._add_active_product_to_cart()
        self.assertEqual(len(self.pos.cart_items), 2)
        self.assertEqual(self.pos.cart_items[1].product_id, p_meat.id)

        # 3. Add 1 bottle of wine again
        self.pos._select_product(p_vino)
        self.pos._add_active_product_to_cart()

        # Should consolidate into 2 rows, not 3 rows!
        self.assertEqual(len(self.pos.cart_items), 2, "Cart must have exactly 2 consolidated rows, not 3 duplicate rows")
        wine_item = next(it for it in self.pos.cart_items if it.product_id == p_vino.id)
        self.assertEqual(wine_item.quantity, p_vino.fixed_package_info[0] * 2.0)
        self.assertEqual(wine_item.total_price, p_vino.price_base * 2.0)
        self.assertEqual(wine_item.base_stock_deduction, 2.0, "2 bottles of wine must deduct 2.0 units from inventory")

    def test_wine_checkout_and_sale_transaction(self):
        """Test full checkout transaction when buying wine (unit_selected='ml') without CHECK constraint failure."""
        with get_db_connection() as conn:
            prods = ProductModel.get_all(conn)
        p_vino = next((p for p in prods if p.fixed_package_info), None)
        self.assertIsNotNone(p_vino)
        with get_db_connection() as conn:
            ProductModel.update_stock(conn, p_vino.id, 50.0)
        with get_db_connection() as conn:
            p_vino = ProductModel.get_by_id(conn, p_vino.id)

        self.pos.cart_items.clear()
        self.pos._select_product(p_vino)
        self.pos._add_active_product_to_cart()
        self.assertEqual(len(self.pos.cart_items), 1)

        # Process checkout with Cash payment
        total = self.pos.cart_items[0].total_price
        with patch("views.pos_frame.print_ticket_raw", return_value=(True, "OK")), \
             patch("hardware.ticket_printer.print_ticket_raw", return_value=(True, "OK")), \
             patch("views.pos_frame.TicketPreviewModal"):
            self.pos._process_checkout(
                cash_received=total,
                payment_method="EFECTIVO"
            )

        # Cart should now be empty after successful sale
        self.assertEqual(len(self.pos.cart_items), 0)

        # Verify last sale in DB was saved in sale_items with unit_selected='ml'
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT si.quantity, si.unit_selected, si.unit_price, si.total_price "
                "FROM sale_items si JOIN sales s ON si.sale_id = s.id "
                "WHERE si.product_id = ? ORDER BY s.id DESC LIMIT 1",
                (p_vino.id,)
            )
            item_row = cur.fetchone()
            self.assertIsNotNone(item_row)
            self.assertEqual(item_row["unit_selected"], "ml")
            self.assertEqual(item_row["quantity"], p_vino.fixed_package_info[0])
            self.assertEqual(item_row["total_price"], p_vino.price_base)


if __name__ == "__main__":
    unittest.main()
