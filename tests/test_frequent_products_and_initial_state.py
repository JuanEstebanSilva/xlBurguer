"""Unit tests for POSFrame initial empty state and dynamic frequent products.
"""

import os
import sys
import unittest
import customtkinter as ctk

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.connection import get_db_connection, initialize_database
from models.product import ProductModel, Product
from utils.asset_manager import ensure_assets
from views.pos_frame import POSFrame, abbreviate_product_name


class TestFrequentProductsAndInitialState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_assets()
        initialize_database()

    def test_abbreviate_product_name(self):
        # Test size / volume
        self.assertEqual(abbreviate_product_name("Vino Tinto Reserva 750 ml"), "Vino 750")
        self.assertEqual(abbreviate_product_name("Cerveza Corona 355 ml"), "Cerveza 355")

        # Test filler words
        self.assertEqual(abbreviate_product_name("Costilla de Res Especial"), "Costilla")
        self.assertEqual(abbreviate_product_name("Pechuga de Pollo"), "Pechuga")
        self.assertEqual(abbreviate_product_name("Chuleta de Cerdo"), "Chuleta")

        # Test short names remain intact
        self.assertEqual(abbreviate_product_name("Lomo Fino"), "Lomo Fino")

    def test_pos_initial_state_empty(self):
        app = ctk.CTk()
        app.withdraw()
        try:
            pos = POSFrame(parent=app)
            app.update_idletasks()

            # Active product must be None on startup
            self.assertIsNone(pos.active_product)

            # Barcode entry must be empty
            self.assertEqual(pos.barcode_entry.get().strip(), "")

            # Display labels must show placeholders
            self.assertEqual(pos.active_prod_lbl.cget("text"), "--")
            self.assertEqual(pos.active_prod_price_lbl.cget("text"), "Precio Base: --")
            self.assertEqual(pos.active_prod_stock_lbl.cget("text"), "Stock: --")
            self.assertEqual(pos.unit_disp_lbl.cget("text"), "--")

            # Quantity and Subtotal must show placeholder "-" and "COP $ --"
            self.assertEqual(pos.quantity_var.get(), "-")
            self.assertEqual(pos.item_subtotal_var.get(), "COP $ --")

            # Scale button must be None in XL Burguer (no hardware scale)
            self.assertIsNone(pos.scale_btn)

            # Frequent products must have buttons rendered
            frequent = pos._get_top_frequent_products()
            self.assertTrue(len(frequent) > 0)
            self.assertLessEqual(len(frequent), 5)

            # Test selecting a cut via _on_quick_cut_click
            pos._on_quick_cut_click(frequent[0])
            app.update_idletasks()

            # Now active product should be populated
            self.assertIsNotNone(pos.active_product)
            self.assertEqual(pos.active_product.id, frequent[0].id)
            self.assertEqual(pos.active_prod_lbl.cget("text"), frequent[0].name)
            self.assertIn("Precio Base:", pos.active_prod_price_lbl.cget("text"))
            self.assertNotEqual(pos.quantity_var.get(), "-")
            self.assertIn("COP $", pos.item_subtotal_var.get())
            self.assertNotIn("--", pos.item_subtotal_var.get())
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
