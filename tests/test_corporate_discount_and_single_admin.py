"""Unit tests for single admin constraint, format_encargado, corporate discount,
and FiadosDashboardModal in XL Burguer.
"""

import os
import sys
import unittest
import customtkinter as ctk

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.connection import get_db_connection, initialize_database
from models.customer import CustomerModel
from models.user import UserModel, User
from views.users_frame import format_encargado, FiadosDashboardModal, UsersFrame


class TestCorporateDiscountAndSingleAdmin(unittest.TestCase):
    """Test suite covering corporate discount, encargado formatting, and single admin constraint."""

    @classmethod
    def setUpClass(cls):
        initialize_database()
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_01_format_encargado(self):
        """Test formatting contact names to strictly first name and first surname."""
        self.assertEqual(format_encargado("Juan Esteban Silva Gómez"), "Juan Silva")
        self.assertEqual(format_encargado("Chef Mauricio Vargas"), "Mauricio Vargas")
        self.assertEqual(format_encargado("Don Carlos Méndez"), "Carlos Méndez")
        self.assertEqual(format_encargado("Diego Martínez"), "Diego Martínez")
        self.assertEqual(format_encargado("Hernando Ruiz"), "Hernando Ruiz")
        self.assertEqual(format_encargado("Maria"), "Maria")
        self.assertIn(format_encargado(""), ("—", ""))
        self.assertIn(format_encargado(None), ("—", ""))

    def test_02_single_admin_constraint(self):
        """Verify that system enforces single administrator constraint."""
        with get_db_connection() as conn:
            admins = [u for u in UserModel.get_all(conn) if u.is_admin]
            self.assertGreaterEqual(len(admins), 1)

            # Check if there is more than 1 admin in the system
            self.assertEqual(len(admins), 1, "There must be exactly ONE administrator in the system.")

    def test_03_corporate_discount_persistence(self):
        """Verify corporate discount percentage is saved and loaded correctly."""
        with get_db_connection() as conn:
            test_comp = CustomerModel.create(
                conn,
                first_name="Restaurante La Casona",
                last_name="Carlos Gomez",
                document_id="900999888-7",
                phone="3119998877",
                customer_type="EMPRESA",
                discount_percent=15.5
            )
            self.assertIsNotNone(test_comp.id)

            fetched = CustomerModel.get_by_id(conn, test_comp.id)
            self.assertIsNotNone(fetched)
            self.assertAlmostEqual(fetched.discount_percent, 15.5, places=2)

            # Update discount
            CustomerModel.update(
                conn,
                customer_id=test_comp.id,
                first_name="La Casona",
                last_name="Carlos Gomez",
                document_id="900999888-7",
                phone="3119998877",
                customer_type="EMPRESA",
                discount_percent=20.0
            )
            updated = CustomerModel.get_by_id(conn, test_comp.id)
            self.assertAlmostEqual(updated.discount_percent, 20.0, places=2)

            # Clean up
            CustomerModel.delete(conn, test_comp.id)

    def test_04_fiados_dashboard_modal(self):
        """Verify FiadosDashboardModal instantiates and renders company data cleanly."""
        with get_db_connection() as conn:
            comp = CustomerModel.create(
                conn,
                first_name="Empresa Test XL",
                last_name="NIT 901000111",
                document_id="901000111-2",
                phone="3101112233",
                customer_type="EMPRESA",
                discount_percent=10.0
            )
        try:
            modal = FiadosDashboardModal(parent=self.root)
            modal.update_idletasks()
            self.assertIsNotNone(modal)
            self.assertGreater(len(modal.companies), 0)
            self.assertIsNotNone(modal.selected_company)
            modal.destroy()
        finally:
            with get_db_connection() as conn:
                CustomerModel.delete(conn, comp.id)


if __name__ == "__main__":
    unittest.main()
