"""Unit tests for the Users / Customers module (XL Burguer).
Verifies CustomerModel statistical aggregations, customer purchase histories,
receipt linkage, customer updates, and UsersFrame UI initialization.
"""

import os
import sys
import unittest

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.connection import get_db_connection, initialize_database
from models.customer import CustomerModel
from views.users_frame import UsersFrame, CustomerFormModal, UserFormModal, CustomerDetailModal
from models.user import UserModel
import customtkinter as ctk


class TestUsersModule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()

    def test_01_customer_stats_and_purchases(self):
        """Verify get_all_with_stats returns rich customer list with purchase counts."""
        with get_db_connection() as conn:
            customers = CustomerModel.get_all_with_stats(conn)
            self.assertGreater(len(customers), 0)

            first = customers[0]
            self.assertIn("id", first)
            self.assertIn("document_id", first)
            self.assertIn("full_name", first)
            self.assertIn("phone", first)
            self.assertIn("total_purchases", first)
            self.assertIn("total_spent", first)

            # Test filtering by query
            doc_query = first["document_id"]
            filtered = CustomerModel.get_all_with_stats(conn, query=doc_query)
            self.assertGreaterEqual(len(filtered), 1)
            self.assertEqual(filtered[0]["document_id"], doc_query)

            # Test purchases query for this customer
            purchases = CustomerModel.get_customer_purchases(conn, first["id"])
            self.assertIsInstance(purchases, list)
            if purchases:
                sale = purchases[0]
                self.assertIn("invoice_number", sale)
                self.assertIn("total", sale)
                self.assertIn("payment_method", sale)
                self.assertIn("cashier_name", sale)

                # Test sale items query
                items = CustomerModel.get_sale_items(conn, sale["id"])
                self.assertIsInstance(items, list)
                if items:
                    it = items[0]
                    self.assertIn("product_name", it)
                    self.assertIn("quantity", it)
                    self.assertIn("total_price", it)

    def test_02_summary_metrics(self):
        """Verify summary metrics calculation."""
        with get_db_connection() as conn:
            metrics = CustomerModel.get_summary_metrics(conn)
            self.assertIn("total_customers", metrics)
            self.assertIn("active_buyers", metrics)
            self.assertIn("total_spent_customers", metrics)
            self.assertIn("avg_ticket", metrics)
            self.assertGreaterEqual(metrics["total_customers"], 1)

    def test_03_customer_update(self):
        """Verify updating customer name and phone."""
        with get_db_connection() as conn:
            # Create a dedicated temp customer
            test_doc = "9988776655"
            conn.execute("DELETE FROM customers WHERE document_id = ?", (test_doc,))
            conn.commit()

            cust = CustomerModel.create(conn, test_doc, "Original", "Name", "3000000000")
            self.assertEqual(cust.first_name, "Original")

            # Update customer
            CustomerModel.update(conn, cust.id, "Updated", "Customer", "3111111111")

            updated = CustomerModel.get_by_id(conn, cust.id)
            self.assertIsNotNone(updated)
            self.assertEqual(updated.first_name, "Updated")
            self.assertEqual(updated.last_name, "Customer")
            self.assertEqual(updated.phone, "3111111111")

            # Clean up
            conn.execute("DELETE FROM customers WHERE id = ?", (cust.id,))
            conn.commit()

    def test_04_users_frame_instantiation(self):
        """Verify UsersFrame GUI instantiates, loads data, paginates, and switches tabs."""
        root = ctk.CTk()
        root.withdraw()
        try:
            frame = UsersFrame(parent=root)
            self.assertIsNotNone(frame)
            frame.update_idletasks()
            self.assertGreater(len(frame.all_customers), 0)

            # Test search
            frame.search_entry.insert(0, "a")
            frame._do_search()
            frame.update_idletasks()

            # Test tab switch to system users
            frame.tab_selector.set("Usuarios del Sistema")
            frame._on_tab_change("Usuarios del Sistema")
            frame.update_idletasks()

            # Test tab switch back to customers
            frame.tab_selector.set("Clientes")
            frame._on_tab_change("Clientes")
            frame.update_idletasks()

        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_05_customer_and_user_modals(self):
        """Verify CustomerFormModal, CustomerDetailModal, and UserFormModal open cleanly."""
        root = ctk.CTk()
        root.withdraw()
        try:
            with get_db_connection() as conn:
                custs = CustomerModel.get_all_with_stats(conn)
                first_cust = custs[0] if custs else None
                all_u = UserModel.get_all(conn)
                first_user = all_u[0] if all_u else None

            # Test CustomerFormModal (New)
            c_modal_new = CustomerFormModal(parent=root, customer=None)
            c_modal_new.update_idletasks()
            c_modal_new.destroy()

            # Test CustomerFormModal (Edit)
            if first_cust:
                c_modal_edit = CustomerFormModal(parent=root, customer=first_cust)
                c_modal_edit.update_idletasks()
                c_modal_edit.destroy()

                # Test CustomerDetailModal
                d_modal = CustomerDetailModal(parent=root, customer=first_cust)
                d_modal.update_idletasks()
                d_modal.destroy()

            # Test UserFormModal (New)
            u_modal_new = UserFormModal(parent=root, user=None)
            u_modal_new.update_idletasks()
            u_modal_new.destroy()

            # Test UserFormModal (Edit)
            if first_user:
                u_modal_edit = UserFormModal(parent=root, user=first_user)
                u_modal_edit.update_idletasks()
                u_modal_edit.destroy()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_06_admin_protection_and_user_update(self):
        """Verify sole administrator cannot be demoted to cashier."""
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE UPPER(role) = 'ADMIN'")
            admins = cur.fetchall()
            if len(admins) == 1:
                admin_id = admins[0]["id"]
                with self.assertRaises(ValueError):
                    UserModel.update_user(conn, admin_id, "admin", "Admin Test", "CASHIER")

    def test_07_user_form_password_toggle(self):
        """Verify UserFormModal password visibility toggle."""
        root = ctk.CTk()
        root.withdraw()
        try:
            modal = UserFormModal(parent=root, user=None)
            modal.pwd_entry.insert(0, "TestPassword123")
            self.assertEqual(modal.pwd_entry.cget("show"), "•")
            self.assertFalse(modal.pwd_visible)

            # Toggle visibility on
            modal._toggle_pwd_visibility()
            self.assertEqual(modal.pwd_entry.cget("show"), "")
            self.assertTrue(modal.pwd_visible)

            # Toggle visibility off
            modal._toggle_pwd_visibility()
            self.assertEqual(modal.pwd_entry.cget("show"), "•")
            self.assertFalse(modal.pwd_visible)
            modal.destroy()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_08_tab_switching_clears_search_and_refreshes_properly(self):
        """Verify tab switching clears search entry and load_data respects active tab."""
        root = ctk.CTk()
        root.withdraw()
        try:
            frame = UsersFrame(parent=root)
            frame.search_entry.insert(0, "PruebaFiltro")
            self.assertEqual(frame.search_entry.get(), "PruebaFiltro")

            # Switch to system users tab
            frame.tab_selector.set("Usuarios del Sistema")
            frame._on_tab_change("Usuarios del Sistema")
            self.assertEqual(frame.search_entry.get(), "")
            self.assertIn("Registrar Usuario", frame.add_btn.cget("text"))

            # load_data while on Usuarios del Sistema tab
            frame.load_data()
            frame.update_idletasks()

            # Refresh click while on Usuarios del Sistema
            frame._on_refresh_click()
            frame.update_idletasks()

            # Switch back to Clientes
            frame.tab_selector.set("Clientes")
            frame._on_tab_change("Clientes")
            self.assertEqual(frame.search_entry.get(), "")
            self.assertIn("Registrar Cliente", frame.add_btn.cget("text"))
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_09_operator_name_update_reflected_in_ticket(self):
        """Verify changing operator full_name in DB is reflected in printed receipt 'Atendido por:'."""
        from models.sale import SaleModel, CartItem
        from hardware.ticket_printer import format_ticket

        with get_db_connection() as conn:
            # 1. Update user 1 name to Juan Cajero
            UserModel.update_user(conn, 1, "admin", "Juan Cajero", "ADMIN")
            conn.commit()

            # Create a simple sale (2 burgers)
            cart = [
                CartItem(
                    product_id=1,
                    product_name="Hamburguesa Clásica XL",
                    category_id=1,
                    category_name="Hamburguesas",
                    sale_type="UNIDAD",
                    price_base=25000.0,
                    quantity=2.0,
                    unit_selected="und",
                    total_price=50000.0
                )
            ]
            sale_detail = SaleModel.process_sale(
                conn=conn,
                user_id=1,
                cart_items=cart,
                cash_received=50000.0,
                customer_id=None,
                payment_method="EFECTIVO"
            )

            # Ticket formatted directly from sale_detail
            ticket_text = format_ticket(sale_detail)
            self.assertIn("Atendido por: Juan Cajero", ticket_text)

            # 2. Update operator name to a new cashier 'Carlos Perez'
            UserModel.update_user(conn, 1, "admin", "Carlos Perez", "ADMIN")

            # Reprint from DB
            reprint_sale = SaleModel.get_sale_by_id(conn, sale_detail.id)
            reprint_ticket = format_ticket(reprint_sale)
            self.assertIn("Atendido por: Carlos Perez", reprint_ticket)

            # Restore original name
            UserModel.update_user(conn, 1, "admin", "Administrador XL", "ADMIN")

    def test_10_single_administrator_enforcement(self):
        """Verify single-administrator rule at database model level."""
        with get_db_connection() as conn:
            conn.execute("DELETE FROM users WHERE username = 'cajero_test_10'")
            conn.commit()
            # 1. Any user created while an admin exists is assigned CASHIER
            new_uid = UserModel.create_user(
                conn=conn,
                username="cajero_test_10",
                password="password123",
                full_name="Cajero Prueba",
                role="ADMIN"  # Attempt to create as ADMIN
            )
            created_user = UserModel.get_by_id(conn, new_uid)
            self.assertIsNotNone(created_user)
            self.assertEqual(created_user.role, "CASHIER")
            self.assertFalse(created_user.is_admin)

            # 2. Attempting to promote a cashier to ADMIN fails with ValueError
            with self.assertRaises(ValueError):
                UserModel.update_user(
                    conn=conn,
                    user_id=new_uid,
                    username="cajero_test_10",
                    full_name="Cajero Promovido",
                    role="ADMIN"
                )

            # 3. Attempting to delete the administrator is blocked
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE UPPER(role) IN ('ADMIN', 'ADMINISTRADOR')")
            admin_id = cur.fetchone()["id"]
            success, msg = UserModel.delete_user(conn, admin_id)
            self.assertFalse(success)
            self.assertIn("No se puede eliminar al Administrador", msg)

            # Clean up temp test user
            conn.execute("DELETE FROM users WHERE id = ?", (new_uid,))
            conn.commit()

    def test_11_cashier_inventory_restrictions(self):
        """Verify Cajero POS in InventoryFrame has no actions column, no Add Product button, and no Export Excel button."""
        from views.inventory_frame import InventoryFrame
        from models.user import User

        root = ctk.CTk()
        root.withdraw()
        try:
            cashier_user = User(id=99, username="cajero1", password_hash="", full_name="Cajero 1", role="CASHIER")
            inv_frame = InventoryFrame(parent=root, current_user=cashier_user)
            inv_frame.update_idletasks()

            # Verify permissions
            self.assertFalse(inv_frame.is_admin)

            # 'actions' column must NOT be in columns_def
            col_keys = [c[0] for c in inv_frame.columns_def]
            self.assertNotIn("actions", col_keys)

            # Add product and Export Excel buttons must not be packed for cashier
            self.assertEqual(inv_frame.add_prod_btn.winfo_manager(), "")
            self.assertEqual(inv_frame.export_excel_btn.winfo_manager(), "")

            # Switch user to admin dynamically
            admin_user = User(id=1, username="admin", password_hash="", full_name="Administrador XL", role="ADMIN")
            inv_frame.set_current_user(admin_user)
            inv_frame.update_idletasks()

            self.assertTrue(inv_frame.is_admin)
            col_keys_admin = [c[0] for c in inv_frame.columns_def]
            self.assertIn("actions", col_keys_admin)
            self.assertEqual(inv_frame.add_prod_btn.winfo_manager(), "pack")
            self.assertEqual(inv_frame.export_excel_btn.winfo_manager(), "pack")

        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_12_cashier_navigation_restrictions(self):
        """Verify Cajero POS cannot access stats or users views in App and MainWindow."""
        from main import App
        from views.main_window import MainWindow
        from models.user import User

        cashier_user = User(id=99, username="cajero1", password_hash="", full_name="Cajero 1", role="CASHIER")

        # Test in App
        app = App()
        app.update_idletasks()
        try:
            app.on_login_success(cashier_user)
            app.update_idletasks()

            # Only pos and inventory buttons must be packed
            self.assertEqual(app.nav_buttons["pos"].winfo_manager(), "pack")
            self.assertEqual(app.nav_buttons["inventory"].winfo_manager(), "pack")
            self.assertEqual(app.nav_buttons["stats"].winfo_manager(), "")
            self.assertEqual(app.nav_buttons["users"].winfo_manager(), "")

            # Attempting to show stats or users redirects to pos
            app.show_frame("stats")
            app.update_idletasks()
            self.assertEqual(app.frames["pos"].winfo_manager(), "pack")

            app.show_frame("users")
            app.update_idletasks()
            self.assertEqual(app.frames["pos"].winfo_manager(), "pack")
        finally:
            try:
                app.destroy()
            except Exception:
                pass

        # Test in MainWindow
        main_win = MainWindow(current_user=cashier_user, on_logout_callback=lambda: None)
        main_win.update_idletasks()
        try:
            self.assertEqual(main_win.nav_buttons["pos"].winfo_manager(), "pack")
            self.assertEqual(main_win.nav_buttons["inventory"].winfo_manager(), "pack")
            self.assertEqual(main_win.nav_buttons["stats"].winfo_manager(), "")
            self.assertEqual(main_win.nav_buttons["users"].winfo_manager(), "")

            # Attempting to navigate to stats or users stays on pos
            main_win._show_view("stats")
            main_win.update_idletasks()
            self.assertEqual(main_win.current_view_name, "pos")

            main_win._show_view("users")
            main_win.update_idletasks()
            self.assertEqual(main_win.current_view_name, "pos")
        finally:
            try:
                main_win.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    res = unittest.main(exit=False)
    os._exit(0 if res.result.wasSuccessful() else 1)

