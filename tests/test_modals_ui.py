import os
import sys
import unittest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import customtkinter as ctk
from database.connection import initialize_database, get_db_connection
from models.product import ProductModel, Product
from utils.asset_manager import ensure_assets
from views.inventory_frame import ProductDetailModal, ProductFormModal

class TestModalsUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_assets()
        initialize_database()
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_product_detail_modal(self):
        with get_db_connection() as conn:
            prods = ProductModel.get_all(conn)
        self.assertTrue(len(prods) > 0)
        p = prods[0]

        modal = ProductDetailModal(self.root, p)
        modal.update()

        # Check background and safe height (<= 600)
        self.assertEqual(modal.cget("fg_color"), "#15171F")
        self.assertLessEqual(modal.winfo_height(), 600)

        # Check that footer buttons exist and are placed outside scrollable area
        self.assertTrue(hasattr(modal, "destroy"))

        # Destroy modal
        modal.destroy()

    def test_product_form_modal_create(self):
        modal = ProductFormModal(self.root)
        modal.update()

        # Check background and safe height (<= 600)
        self.assertEqual(modal.cget("fg_color"), "#15171F")
        self.assertLessEqual(modal.winfo_height(), 600)

        # Check scrollable frame presence
        self.assertTrue(hasattr(modal, "form_frame"))
        self.assertIsInstance(modal.form_frame, ctk.CTkScrollableFrame)

        # Check compact IVA width
        self.assertEqual(modal.iva_entry.cget("justify"), "center")

        # Check compact ID entry width (110)
        self.assertEqual(modal.id_entry.cget("width"), 110)

        # Check status chip label starts as Agotado when initial stock is empty (0)
        self.assertIn("Agotado", modal.live_status_lbl.cget("text"))
        modal.stock_entry.delete(0, "end")
        modal.stock_entry.insert(0, "10")
        modal.min_stock_entry.delete(0, "end")
        modal.min_stock_entry.insert(0, "2")
        modal._update_live_status()
        self.assertIn("Normal", modal.live_status_lbl.cget("text"))

        # Check cancel and save buttons are anchored and visible
        self.assertIsNotNone(modal.cancel_btn)
        self.assertIsNotNone(modal.save_btn)
        self.assertEqual(modal.cancel_btn.master, modal.save_btn.master)
        # Verify action row is not a child of the scrollable frame
        self.assertNotEqual(modal.cancel_btn.master, modal.form_frame)

        modal.destroy()

    def test_product_form_modal_edit(self):
        with get_db_connection() as conn:
            prods = ProductModel.get_all(conn)
        p = prods[0]

        modal = ProductFormModal(self.root, p)
        modal.update()

        self.assertEqual(modal.cget("fg_color"), "#15171F")
        self.assertEqual(modal.name_entry.get(), p.name)
        self.assertLessEqual(modal.winfo_height(), 600)
        self.assertIn("Editar", modal.save_btn.cget("text"))

        modal.destroy()

if __name__ == "__main__":
    unittest.main()
