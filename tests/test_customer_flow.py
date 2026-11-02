"""Tests for Customer Identification, Inline Quick Registration,
Multi-payment checkout, and Receipt Customer formatting.
"""

import os
import sqlite3
import sys
import unittest
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.connection import get_db_connection, initialize_database
from hardware.ticket_printer import format_ticket
from models.customer import Customer, CustomerModel
from models.product import ProductModel
from models.sale import CartItem, SaleModel
from views.pos_frame import CheckoutModal, POSFrame


class TestCustomerFlowAndPayment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()

    def setUp(self):
        self.test_doc = "1098765432"

    def test_01_customer_crud_and_search(self):
        """Test CustomerModel creation, retrieval by document/id, and search."""
        with get_db_connection() as conn:
            # Clean up if existing
            conn.execute("DELETE FROM customers WHERE document_id = ?", (self.test_doc,))
            conn.commit()

            # Create customer
            cust = CustomerModel.create(
                conn=conn,
                document_id=self.test_doc,
                first_name="Carlos",
                last_name="Gómez",
                phone="3101234567"
            )
            self.assertIsNotNone(cust.id)
            self.assertEqual(cust.first_name, "Carlos")
            self.assertEqual(cust.last_name, "Gómez")
            self.assertEqual(cust.full_name, "Carlos Gómez")
            self.assertIn("Carlos Gómez", cust.display_label)
            self.assertIn(self.test_doc, cust.display_label)

            # Retrieve by document
            fetched = CustomerModel.get_by_document(conn, self.test_doc)
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched.id, cust.id)

            # Retrieve by ID
            fetched_by_id = CustomerModel.get_by_id(conn, cust.id)
            self.assertIsNotNone(fetched_by_id)
            self.assertEqual(fetched_by_id.document_id, self.test_doc)

            # Search by name
            search_results = CustomerModel.search(conn, "Gómez")
            self.assertTrue(any(c.id == cust.id for c in search_results))

    def test_02_sale_with_customer_and_payment_methods(self):
        """Test processing sales with customer_id and electronic payment methods."""
        with get_db_connection() as conn:
            # Ensure a customer exists
            cust = CustomerModel.get_by_document(conn, self.test_doc)
            if not cust:
                cust = CustomerModel.create(conn, self.test_doc, "Carlos", "Gómez", "3101234567")

            products = ProductModel.get_all(conn)
            self.assertTrue(len(products) > 0)
            p = next((x for x in products if x.stock >= 2000.0), None)
            if not p:
                p = products[0]
                ProductModel.add_stock(conn, p.id, 10000.0)
                p = ProductModel.get_by_id(conn, p.id)

            cart_item = CartItem(
                product_id=p.id,
                product_name=p.name,
                category_id=p.category_id,
                category_name=p.category_name,
                sale_type=p.sale_type,
                quantity=1.0,
                unit_selected="kg" if p.sale_type == "PESO" else "und",
                price_base=p.price_base,
                total_price=p.price_base * 1.0
            )

            # 1. Sale with customer and EFECTIVO
            sale_cash = SaleModel.process_sale(
                conn=conn,
                user_id=1,
                cart_items=[cart_item],
                cash_received=p.price_base * 2.0,
                customer_id=cust.id,
                payment_method="EFECTIVO"
            )
            self.assertEqual(sale_cash.customer_id, cust.id)
            self.assertEqual(sale_cash.customer_name, "Carlos Gómez")
            self.assertEqual(sale_cash.customer_document, self.test_doc)
            self.assertEqual(sale_cash.payment_method, "EFECTIVO")
            self.assertEqual(sale_cash.cash_change, p.price_base * 1.0)

            # 2. Sale with TRANSFERENCIA (Nequi/Daviplata)
            sale_trans = SaleModel.process_sale(
                conn=conn,
                user_id=1,
                cart_items=[cart_item],
                cash_received=cart_item.total_price,
                customer_id=cust.id,
                payment_method="TRANSFERENCIA"
            )
            self.assertEqual(sale_trans.payment_method, "TRANSFERENCIA")
            self.assertEqual(sale_trans.cash_change, 0.0)

            # 3. Sale with TARJETA and Anonymous customer (customer_id=None)
            sale_card = SaleModel.process_sale(
                conn=conn,
                user_id=1,
                cart_items=[cart_item],
                cash_received=cart_item.total_price,
                customer_id=None,
                payment_method="TARJETA"
            )
            self.assertIsNone(sale_card.customer_id)
            self.assertEqual(sale_card.payment_method, "TARJETA")

            # 4. Verify get_sale_by_invoice retrieves customer and payment_method
            detail = SaleModel.get_sale_by_invoice(conn, sale_cash.invoice_number)
            self.assertIsNotNone(detail)
            self.assertEqual(detail.customer_id, cust.id)
            self.assertEqual(detail.customer_name, "Carlos Gómez")
            self.assertEqual(detail.payment_method, "EFECTIVO")

    def test_03_ticket_format_customer_and_payment(self):
        """Test that format_ticket displays customer details and payment method cleanly."""
        items = [{
            "product_name": "Lomo Fino",
            "quantity": 1.5,
            "unit_selected": "kg",
            "total_price": 57000.0
        }]

        # Test Cash Ticket with Customer
        ticket_cash = format_ticket(
            invoice_number="SD-000999",
            timestamp="2026-09-23 10:30:00",
            cashier_name="Don Pedro",
            items=items,
            subtotal=57000.0,
            total=57000.0,
            cash_received=60000.0,
            cash_change=3000.0,
            customer_name="Juan Silva",
            customer_document="10203040",
            payment_method="EFECTIVO"
        )
        self.assertIn("Juan Silva", ticket_cash)
        self.assertIn("10203040", ticket_cash)
        self.assertIn("EFECTIVO", ticket_cash)
        self.assertTrue("CAMBIO:" in ticket_cash or "CAMBIO / VUELTAS:" in ticket_cash)

        # Test Transfer Ticket Anonymous
        ticket_trans = format_ticket(
            invoice_number="SD-001000",
            timestamp="2026-09-23 10:35:00",
            cashier_name="Don Pedro",
            items=items,
            subtotal=57000.0,
            total=57000.0,
            cash_received=57000.0,
            cash_change=0.0,
            customer_name=None,
            payment_method="TRANSFERENCIA"
        )
        self.assertIn("Consumidor Final", ticket_trans)
        self.assertIn("TRANSFERENCIA", ticket_trans)
        self.assertIn("ESTADO PAGO:", ticket_trans)

    def test_04_pos_frame_customer_and_cut_interaction(self):
        """Test POSFrame customer search, quick cut selection, keypad, and add item without modals."""
        import customtkinter as ctk
        app = ctk.CTk()
        app.withdraw()

        try:
            pos = POSFrame(parent=app)
            app.update_idletasks()

            # 1. Search existing customer
            pos.customer_doc_entry.insert(0, self.test_doc)
            pos._on_customer_search()
            app.update_idletasks()
            self.assertIsNotNone(pos.current_customer)
            self.assertEqual(pos.current_customer.document_id, self.test_doc)

            # 2. Clear customer
            pos._clear_customer()
            app.update_idletasks()
            self.assertIsNone(pos.current_customer)
            self.assertEqual(pos.keypad_frame.winfo_manager(), "pack")

            # 2b. Test keypad hides during quick registration and restores on cancel
            pos.customer_doc_entry.delete(0, "end")
            pos.customer_doc_entry.insert(0, "999999999999")
            pos._on_customer_search()
            app.update_idletasks()
            self.assertEqual(pos.keypad_frame.winfo_manager(), "", "Keypad must be unpacked during quick_reg")

            pos._clear_customer()
            app.update_idletasks()
            self.assertEqual(pos.keypad_frame.winfo_manager(), "pack", "Keypad must be re-packed after cancelling quick_reg")

            # 3. Test Anonymous button
            pos._set_anonymous_customer()
            self.assertIsNone(pos.current_customer)

            # 4. Test Quick Cut Pill button
            frequent = pos._get_top_frequent_products()
            if frequent:
                pos._on_quick_cut_click(frequent[0])
                app.update_idletasks()
                self.assertIsNotNone(pos.active_product)
                self.assertEqual(pos.active_product.id, frequent[0].id)

            # 5. Keypad entry: type '2' and '.' and '5'
            pos._on_keypad_press("2")
            pos._on_keypad_press(".")
            pos._on_keypad_press("5")
            self.assertEqual(pos.quantity_var.get(), "2.5")

            # 5b. Keypad layout - confirm scale button is retired in XL Burguer
            self.assertIsNone(pos.scale_btn)
            self.assertGreaterEqual(pos.product_selector.cget("width"), 150)
            self.assertIn("Precio", pos.active_prod_price_lbl.cget("text"))

            # 6. Add to cart
            pos._add_active_product_to_cart()
            app.update_idletasks()
            self.assertEqual(len(pos.cart_items), 1)
            self.assertAlmostEqual(pos.cart_items[0].quantity, 2.5)

            # 7. Clean up
            pos.cart_items.clear()
            pos._render_cart()
        finally:
            app.destroy()
            try:
                app.update()
            except Exception:
                pass

    def test_05_checkout_modal_centering_and_order(self):
        """Test that CheckoutModal centers on screen/parent and maintains change_card above confirm_btn."""
        import customtkinter as ctk
        app = ctk.CTk()
        app.geometry("1024x768+100+100")
        app.withdraw()

        try:
            callback_mock = MagicMock()
            modal = CheckoutModal(
                parent=app,
                total_amount=50000.0,
                on_complete_sale_callback=callback_mock
            )
            app.update_idletasks()

            # 1. Verify window geometry has centered offsets (+x+y)
            geom = modal.geometry()
            self.assertIn("+", geom)

            # 2. Verify change_card is above confirm_btn inside bottom_frame
            children = modal.bottom_frame.winfo_children()
            self.assertIn(modal.change_card, children)
            self.assertIn(modal.confirm_btn, children)
            idx_change = children.index(modal.change_card)
            idx_confirm = children.index(modal.confirm_btn)
            self.assertLess(idx_change, idx_confirm, "change_card must be placed before confirm_btn")

            # 3. Toggle to Transferencia
            modal._set_payment_method("TRANSFERENCIA")
            app.update_idletasks()
            self.assertEqual(modal.payment_method, "TRANSFERENCIA")
            self.assertEqual(modal.confirm_btn.cget("state"), "normal")

            # 4. Toggle back to Efectivo
            modal._set_payment_method("EFECTIVO")
            app.update_idletasks()
            self.assertEqual(modal.payment_method, "EFECTIVO")
            # Verify change_card is still before confirm_btn
            children_after = modal.bottom_frame.winfo_children()
            idx_change2 = children_after.index(modal.change_card)
            idx_confirm2 = children_after.index(modal.confirm_btn)
            self.assertLess(idx_change2, idx_confirm2, "change_card must remain placed before confirm_btn")

            # 5. Denominations
            modal._on_denom_click(20000)
            self.assertEqual(modal.cash_var.get(), "20000")
            modal._on_denom_click(50000)
            self.assertEqual(modal.cash_var.get(), "70000")
            self.assertIn("20.000", modal.change_var.get())

            modal._on_denom_click("exact")
            self.assertEqual(modal.cash_var.get(), "50000")

            # 6. Confirm sale
            modal._on_confirm_payment()
            callback_mock.assert_called_once()
        finally:
            app.destroy()
            try:
                app.update()
            except Exception:
                pass

    def test_06_quick_registration_validations(self):
        """Test strict validation rules for Persona and Empresa quick registration in POSFrame:
        - Doc/NIT allows letters, numbers, hyphens without restrictive validation.
        - Persona name and apellido cannot contain numbers.
        - Empresa company name can contain numbers, but representative cannot contain numbers.
        - Phone must start with 3 and have exactly 10 digits.
        """
        import customtkinter as ctk
        app = ctk.CTk()
        app.withdraw()

        try:
            pos = POSFrame(parent=app)
            app.update_idletasks()

            # Render quick registration card
            pos._render_customer_section(mode="quick_reg", doc_prefill="900.123.456-7")
            app.update_idletasks()

            with patch("tkinter.messagebox.showwarning") as mock_warn:
                # 1. Persona with numbers in first name
                pos.reg_type_seg.set("Persona")
                pos._on_quick_reg_type_toggle("Persona")
                pos.new_first_name_entry.delete(0, "end")
                pos.new_first_name_entry.insert(0, "Juan123")
                pos.new_last_name_entry.delete(0, "end")
                pos.new_last_name_entry.insert(0, "Pérez")
                pos.new_phone_entry.delete(0, "end")
                pos.new_phone_entry.insert(0, "3001234567")
                pos._quick_register_customer("900.123.456-7")
                mock_warn.assert_called()
                self.assertIn("nombre", mock_warn.call_args[0][1].lower())
                self.assertIn("números", mock_warn.call_args[0][1].lower())

                # 2. Persona with numbers in apellido
                mock_warn.reset_mock()
                pos.new_first_name_entry.delete(0, "end")
                pos.new_first_name_entry.insert(0, "Juan")
                pos.new_last_name_entry.delete(0, "end")
                pos.new_last_name_entry.insert(0, "Pérez99")
                pos._quick_register_customer("900.123.456-7")
                mock_warn.assert_called()
                self.assertIn("apellido", mock_warn.call_args[0][1].lower())
                self.assertIn("números", mock_warn.call_args[0][1].lower())

                # 3. Phone missing / empty
                mock_warn.reset_mock()
                pos.new_last_name_entry.delete(0, "end")
                pos.new_last_name_entry.insert(0, "Pérez")
                pos.new_phone_entry.delete(0, "end")
                pos._quick_register_customer("900.123.456-7")
                mock_warn.assert_called()
                self.assertIn("teléfono", mock_warn.call_args[0][1].lower())

                # 4. Phone not starting with 3
                mock_warn.reset_mock()
                pos.new_phone_entry.delete(0, "end")
                pos.new_phone_entry.insert(0, "6011234567")
                pos._quick_register_customer("900.123.456-7")
                mock_warn.assert_called()
                self.assertIn("3", mock_warn.call_args[0][1])

                # 5. Phone not 10 digits (e.g. 8 digits)
                mock_warn.reset_mock()
                pos.new_phone_entry.delete(0, "end")
                pos.new_phone_entry.insert(0, "30012345")
                pos._quick_register_customer("900.123.456-7")
                mock_warn.assert_called()
                self.assertIn("10 dígitos", mock_warn.call_args[0][1].lower())

                # 6. Phone with letters
                mock_warn.reset_mock()
                pos.new_phone_entry.delete(0, "end")
                pos.new_phone_entry.insert(0, "300abc4567")
                pos._quick_register_customer("900.123.456-7")
                mock_warn.assert_called()
                self.assertIn("número de teléfono está mal escrito", mock_warn.call_args[0][1].lower())

                # 7. Empresa with numbers in representative
                mock_warn.reset_mock()
                pos.reg_type_seg.set("Empresa")
                pos._on_quick_reg_type_toggle("Empresa")
                pos.new_first_name_entry.delete(0, "end")
                pos.new_first_name_entry.insert(0, "Frigorífico 24 Horas SAS")
                pos.new_last_name_entry.delete(0, "end")
                pos.new_last_name_entry.insert(0, "Carlos 2")
                pos.new_phone_entry.delete(0, "end")
                pos.new_phone_entry.insert(0, "3151234567")
                pos._quick_register_customer("NIT-800-ABC")
                mock_warn.assert_called()
                self.assertIn("representante", mock_warn.call_args[0][1].lower())
                self.assertIn("números", mock_warn.call_args[0][1].lower())

                # 8. Valid Empresa registration (numbers in company allowed, valid rep, valid phone, non-numeric NIT allowed)
                test_nit = "NIT-800-TEST-X"
                pos.new_last_name_entry.delete(0, "end")
                pos.new_last_name_entry.insert(0, "Carlos Rodríguez")
                pos._quick_register_customer(test_nit)
                self.assertIsNotNone(pos.current_customer)
                self.assertEqual(pos.current_customer.document_id, test_nit)
                self.assertEqual(pos.current_customer.phone, "3151234567")
                self.assertTrue(pos.current_customer.is_company)

                # Clean up test customer
                with get_db_connection() as conn:
                    conn.execute("DELETE FROM customers WHERE document_id = ?", (test_nit,))
                    conn.commit()

        finally:
            app.destroy()
            try:
                app.update()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()

