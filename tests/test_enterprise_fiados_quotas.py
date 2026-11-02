"""Comprehensive automated tests for Enterprise Product Quota Fiados (Carnicería San Diego).
Verifies:
1. Enterprise creation with customer_type = 'EMPRESA'.
2. Setting and editing product quotas (Cupos de Fiado por Producto).
3. Directly updating the remaining balance ('le queda tanto de este producto, se debe poder editar').
4. POS sale with payment_method = 'FIADO' automatically consuming from product quotas.
5. Ticket formatting showing 'FIADO (EMPRESA)', company name, sold product, and remaining quota.
6. 50/50 workspace partition in UsersFrame (Personas vs Empresas).
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
from models.product import ProductModel
from models.sale import SaleModel
from hardware.ticket_printer import format_ticket
from views.users_frame import UsersFrame, CompanyDetailModal, CompanyQuotaEditModal, CustomerFormModal


class TestEnterpriseFiadosQuotas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()

    def setUp(self):
        self.root = ctk.CTk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_01_create_enterprise_and_quotas(self):
        """Test creating an enterprise customer and assigning product agreements/quotas."""
        with get_db_connection() as conn:
            # Clean any previous test data
            test_nit = "901999888-1"
            conn.execute("DELETE FROM customers WHERE document_id = ?", (test_nit,))
            conn.commit()

            # 1. Create company
            company = CustomerModel.create(
                conn=conn,
                document_id=test_nit,
                first_name="Restaurante La Gran Brasa SAS",
                last_name="Carlos Pardo",
                phone="3159998877",
                customer_type="EMPRESA"
            )
            self.assertIsNotNone(company.id)
            self.assertEqual(company.customer_type, "EMPRESA")
            self.assertEqual(company.first_name, "Restaurante La Gran Brasa SAS")

            # 2. Get active meat products to set quotas for
            products = ProductModel.get_all(conn)
            self.assertGreater(len(products), 0)
            prod1 = products[0]

            # 3. Set a quota: 30 kg monthly
            quota_id = CustomerModel.set_company_quota(
                conn=conn,
                customer_id=company.id,
                product_id=prod1.id,
                quota_quantity=30.0,
                unit="kg",
                notes="Convenio 30kg mensuales corte especial"
            )
            self.assertIsNotNone(quota_id)

            # 4. Fetch quotas and verify
            quotas = CustomerModel.get_company_quotas(conn, company.id)
            self.assertEqual(len(quotas), 1)
            q = quotas[0]
            self.assertEqual(q["product_id"], prod1.id)
            self.assertEqual(q["quota_quantity"], 30.0)
            self.assertEqual(q["remaining_quantity"], 30.0)
            self.assertEqual(q["consumed_quantity"], 0.0)
            self.assertEqual(q["unit"], "kg")

            # 5. Clean up
            conn.execute("DELETE FROM customers WHERE id = ?", (company.id,))
            conn.commit()

    def test_02_edit_remaining_quota_directly(self):
        """Test that the remaining quantity ('le queda') can be directly edited as requested by user."""
        with get_db_connection() as conn:
            test_nit = "901888777-2"
            conn.execute("DELETE FROM customers WHERE document_id = ?", (test_nit,))
            conn.commit()

            company = CustomerModel.create(
                conn=conn,
                document_id=test_nit,
                first_name="Hotel Villa Real",
                last_name="María Gómez",
                phone="3201112233",
                customer_type="EMPRESA"
            )
            products = ProductModel.get_all(conn)
            prod = products[0]

            CustomerModel.set_company_quota(
                conn=conn,
                customer_id=company.id,
                product_id=prod.id,
                quota_quantity=20.0,
                unit="kg"
            )

            # Direct edit: User adjusted remaining quota to 14.5 kg
            success = CustomerModel.update_company_quota_remaining(
                conn=conn,
                customer_id=company.id,
                product_id=prod.id,
                new_remaining=14.5,
                new_quota=20.0,
                notes="Ajuste manual acordado con la gerencia"
            )
            self.assertTrue(success)

            quotas = CustomerModel.get_company_quotas(conn, company.id)
            self.assertEqual(len(quotas), 1)
            q = quotas[0]
            self.assertAlmostEqual(q["remaining_quantity"], 14.5, places=2)
            self.assertAlmostEqual(q["consumed_quantity"], 5.5, places=2)
            self.assertIn("Ajuste manual", q["notes"])

            conn.execute("DELETE FROM customers WHERE id = ?", (company.id,))
            conn.commit()

    def test_03_fiado_sale_consumes_quota_and_prints_ticket(self):
        """Test POS sale with payment_method='FIADO' deducting from company product quota and generating ticket."""
        with get_db_connection() as conn:
            test_nit = "901777666-3"
            conn.execute("DELETE FROM customers WHERE document_id = ?", (test_nit,))
            conn.commit()

            company = CustomerModel.create(
                conn=conn,
                document_id=test_nit,
                first_name="Asadero Los Sauces",
                last_name="Héctor Silva",
                phone="3145556677",
                customer_type="EMPRESA"
            )
            products = ProductModel.get_all(conn)
            prod = products[0]
            conn.execute("UPDATE products SET stock = 50000.0 WHERE id = ?", (prod.id,))
            conn.commit()

            # Assign 30 kg quota
            CustomerModel.set_company_quota(
                conn=conn,
                customer_id=company.id,
                product_id=prod.id,
                quota_quantity=30.0,
                unit="kg",
                notes="Pedido semanal fiado"
            )

            # Perform a FIADO sale of 5 kg of this product
            from models.sale import CartItem
            price_kg = prod.price_base * 1000.0 if prod.sale_type == "PESO" else prod.price_base
            cart_items = [CartItem(
                product_id=prod.id,
                product_name=prod.name,
                category_id=prod.category_id,
                category_name=prod.category_name,
                sale_type=prod.sale_type,
                quantity=5.0,
                unit_selected="kg",
                price_base=prod.price_base,
                total_price=5.0 * price_kg
            )]
            total_sale = 5.0 * price_kg

            sale_detail_obj = SaleModel.process_sale(
                conn=conn,
                user_id=1,
                cart_items=cart_items,
                cash_received=total_sale,
                customer_id=company.id,
                payment_method="FIADO"
            )
            sale_id = sale_detail_obj.id
            self.assertIsNotNone(sale_id)

            # Verify that the quota remaining quantity decreased by 5.0 kg -> 25.0 kg
            quotas = CustomerModel.get_company_quotas(conn, company.id)
            self.assertEqual(len(quotas), 1)
            q = quotas[0]
            self.assertAlmostEqual(q["consumed_quantity"], 5.0, places=2)
            self.assertAlmostEqual(q["remaining_quantity"], 25.0, places=2)

            # Fetch sale details and verify sale items record remaining quota
            sale_detail = SaleModel.get_sale_by_id(conn, sale_id)
            self.assertIsNotNone(sale_detail)
            self.assertEqual(sale_detail.payment_method, "FIADO")
            self.assertEqual(sale_detail.customer_type, "EMPRESA")

            items = sale_detail.items
            self.assertEqual(len(items), 1)
            self.assertAlmostEqual(items[0]["fiado_remaining"], 25.0, places=2)

            # Verify formatted ticket text
            ticket_text = format_ticket(sale_detail)
            self.assertIn("FIADO (EMPRESA)", ticket_text)
            self.assertIn("Asadero Los Sauces", ticket_text)
            self.assertIn("Le queda de cupo: 25.00 kg", ticket_text)

            # Cleanup sale and customer
            conn.execute("DELETE FROM sale_items WHERE sale_id = ?", (sale_id,))
            conn.execute("DELETE FROM sales WHERE id = ?", (sale_id,))
            conn.execute("DELETE FROM customers WHERE id = ?", (company.id,))
            conn.commit()

    def test_04_users_frame_50_50_split(self):
        """Test that UsersFrame divides Personas and Empresas into 50/50 workspace."""
        frame = UsersFrame(parent=self.root)
        frame.update_idletasks()

        self.assertGreater(len(frame.all_customers), 0)
        self.assertGreater(len(frame.personas_list), 0)
        self.assertGreater(len(frame.empresas_list), 0)

        # Check that both 50% panels exist and have counts
        self.assertTrue(hasattr(frame, "personas_panel"))
        self.assertTrue(hasattr(frame, "empresas_panel"))
        self.assertTrue(hasattr(frame, "personas_scroll"))
        self.assertTrue(hasattr(frame, "empresas_scroll"))

        # Verify company detail modal opens cleanly for an enterprise
        emp = frame.empresas_list[0]
        comp_modal = CompanyDetailModal(parent=self.root, company=emp)
        comp_modal.update_idletasks()
        comp_modal.destroy()

        # Verify company quota edit modal opens cleanly
        quota_edit = CompanyQuotaEditModal(
            parent=self.root,
            company=emp,
            quota=None
        )
        quota_edit.update_idletasks()
        quota_edit.destroy()

    def test_05_set_company_quota_remaining_param(self):
        """Verify CustomerModel.set_company_quota accepts remaining keyword argument correctly."""
        with get_db_connection() as conn:
            test_nit = "901999111-9"
            conn.execute("DELETE FROM customers WHERE document_id = ?", (test_nit,))
            conn.commit()

            company = CustomerModel.create(
                conn=conn,
                document_id=test_nit,
                first_name="Hacienda El Rosal",
                last_name="Representante Legal",
                phone="3102223344",
                customer_type="EMPRESA"
            )

            products = ProductModel.get_all(conn)
            prod = products[0]

            # Call with remaining parameter as passed by CustomerAssignCompanyQuotaModal
            quota_id = CustomerModel.set_company_quota(
                conn,
                customer_id=company.id,
                product_id=prod.id,
                quota_quantity=50.0,
                unit="kg",
                notes="Convenio institucional",
                remaining=25.0
            )
            self.assertIsNotNone(quota_id)

            quotas = CustomerModel.get_company_quotas(conn, company.id)
            self.assertEqual(len(quotas), 1)
            self.assertEqual(quotas[0]["quota_quantity"], 50.0)
            self.assertEqual(quotas[0]["remaining_quantity"], 25.0)

            # Cleanup
            conn.execute("DELETE FROM customers WHERE id = ?", (company.id,))
            conn.commit()


if __name__ == "__main__":
    unittest.main()
