"""Test POS checkout modal lifecycle and sale flow without Tkinter TclError crashes."""

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
from models.product import ProductModel
from utils.asset_manager import ensure_assets
from views.pos_frame import CartItem, CheckoutModal


class TestPOSCheckoutFlow(unittest.TestCase):
    """Ensure POS cart checkout and modal lifecycle execute without invalid command TclErrors."""

    @classmethod
    def setUpClass(cls):
        ensure_assets()
        initialize_database()

    def test_full_checkout_flow_and_modal_lifecycle(self):
        app = App()
        app.update_idletasks()

        test_user = User(id=1, username="admin", password_hash="", full_name="Administrador", role="ADMIN")
        app.on_login_success(test_user)
        app.update_idletasks()

        pos = app.frames["pos"]

        # Fetch first product from DB
        with get_db_connection() as conn:
            prods = ProductModel.get_all(conn)
        self.assertTrue(len(prods) > 0)
        p = prods[0]

        # Add item to cart
        cart_item = CartItem(
            product_id=p.id,
            product_name=p.name,
            category_id=p.category_id,
            category_name=p.category_name,
            sale_type=p.sale_type,
            quantity=2.0,
            unit_selected="kg" if p.sale_type == "PESO" else "und",
            price_base=p.price_base,
            total_price=p.price_base * 2.0
        )
        pos.cart_items.append(cart_item)
        pos._render_cart()
        app.update_idletasks()

        # Open CheckoutModal
        total = sum(i.total_price for i in pos.cart_items)
        modal = CheckoutModal(
            parent=pos,
            total_amount=total,
            on_complete_sale_callback=pos._process_checkout
        )
        app.update_idletasks()

        # Set exact cash
        modal.cash_var.set(str(int(total)))
        modal._update_change()
        app.update_idletasks()

        # Confirm payment (this executes modal._on_confirm_payment, destroys CheckoutModal,
        # processes DB sale, prints ticket, and triggers TicketPreviewModal)
        with patch("views.pos_frame.print_ticket_raw", return_value=(True, "OK")), \
             patch("hardware.ticket_printer.print_ticket_raw", return_value=(True, "OK")), \
             patch("views.pos_frame.TicketPreviewModal") as mock_preview:
            modal._on_confirm_payment()
            app.update_idletasks()
            app.update()
            mock_preview.assert_called_once()

        # Check that cart is now empty
        self.assertEqual(len(pos.cart_items), 0)

        # Close any open toplevel preview modals and Close App
        try:
            for widget in app.winfo_children():
                if hasattr(widget, "destroy"):
                    try:
                        widget.destroy()
                    except Exception:
                        pass
            app._on_close()
            app.update()
        except Exception:
            pass

    def test_add_product_button_visibility_and_mapping(self):
        """Verify the 'Agregar Producto' button is permanently mapped and visible on screen."""
        app = App()
        app.update_idletasks()
        test_user = User(id=1, username="admin", password_hash="", full_name="Administrador", role="ADMIN")
        app.on_login_success(test_user)
        app.update()

        pos = app.frames["pos"]
        self.assertTrue(hasattr(pos, "add_item_btn"))
        self.assertTrue(pos.add_item_btn.winfo_ismapped(), "El botón de agregar producto debe estar visible y mapeado")
        self.assertIn("AGREGAR PRODUCTO", pos.add_item_btn.cget("text").upper())
        self.assertIn("ENTER", pos.add_item_btn.cget("text").upper())
        self.assertTrue(hasattr(pos, "_open_new_product_from_pos"))

        try:
            app._on_close()
            app.update()
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
