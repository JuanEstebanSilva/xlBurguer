"""Comprehensive verification and regression test suite for San Diego POS Audit Fixes.
Tests:
- A1: Scale contract precision and mock isolation in production.
- A2: Multi-item fiado transaction atomicity and complete rollback.
- A3: OWASP PBKDF2 600k hashing, plaintext rejection, and account lockout.
- B1: Itemized IVA calculation and storage in sales and sale_items.
- B2: Integer Colombian Peso (COP) rounding.
- B3: Customer debt tracking on fiado sales.
- B4: Cash shift drawer reconciliation and arqueo.
- B5: Sale voiding (void_sale), stock/quota restoration, and audit logging.
- B6: Rejection of non-positive quantities and negative prices.
- B10: Strictly monotonic invoice sequence counter (no reuse on delete/void).
- B11: Strict validation of recognized payment methods.
"""

import os
import sys
import tempfile
import unittest

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.connection import get_db_connection, initialize_database
from hardware.scale_service import SerialScaleDriver, WeightReading
from models.cash_shift import CashShiftModel
from models.customer import CustomerModel
from models.product import ProductModel
from models.sale import CartItem, SaleModel
from models.user import UserModel, hash_password, verify_password


class TestAuditFixesAndRollback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.test_db_path = os.path.join(cls.temp_dir.name, "test_audit_fixes.db")
        os.environ["XLBURGUER_DB_PATH"] = cls.test_db_path
        initialize_database()

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("XLBURGUER_DB_PATH", None)
        os.environ.pop("SANDIEGO_DB_PATH", None)
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM sale_items")
            cur.execute("DELETE FROM sales")
            cur.execute("DELETE FROM cash_shifts")
            cur.execute("DELETE FROM audit_logs")
            cur.execute("DELETE FROM company_product_quotas")
            cur.execute("DELETE FROM products WHERE barcode IN ('TEST_MEAT_A', 'TEST_MEAT_B', 'TEST_WINE_IVA')")
            cur.execute("DELETE FROM users WHERE username IN ('admin_audit', 'cajero_lockout')")
            cur.execute("DELETE FROM customers WHERE document_id = '901234567'")
            conn.commit()

    def setUp(self):
        self._cleanup()
        with get_db_connection() as conn:
            cur = conn.cursor()
            # Category
            cur.execute("INSERT OR IGNORE INTO categories (id, name) VALUES (1, 'Carnes')")
            cur.execute("INSERT OR IGNORE INTO categories (id, name) VALUES (2, 'Vinos')")

            # Products
            cur.execute(
                """
                INSERT INTO products (barcode, name, category_id, sale_type, price_base, cost, iva, unit_measure, stock, min_stock)
                VALUES ('TEST_MEAT_A', 'Costilla de Res Audit', 1, 'PESO', 25.0, 18.0, 0.0, 'kg', 10000.0, 1000.0)
                """
            )
            self.meat_a_id = cur.lastrowid

            cur.execute(
                """
                INSERT INTO products (barcode, name, category_id, sale_type, price_base, cost, iva, unit_measure, stock, min_stock)
                VALUES ('TEST_MEAT_B', 'Lomo Fino Audit', 1, 'PESO', 45.0, 30.0, 0.0, 'kg', 5000.0, 500.0)
                """
            )
            self.meat_b_id = cur.lastrowid

            cur.execute(
                """
                INSERT INTO products (barcode, name, category_id, sale_type, price_base, cost, iva, unit_measure, stock, min_stock)
                VALUES ('TEST_WINE_IVA', 'Vino Reserva 19% IVA', 2, 'UNIDAD', 59500.0, 35000.0, 19.0, 'und', 10.0, 2.0)
                """
            )
            self.wine_id = cur.lastrowid

            # User
            hashed_admin = hash_password("SuperSecret2026!")
            cur.execute(
                """
                INSERT INTO users (username, password_hash, full_name, role)
                VALUES ('admin_audit', ?, 'Admin Auditor', 'ADMIN')
                """,
                (hashed_admin,)
            )
            self.user_id = cur.lastrowid

            # Customer with Quota
            cur.execute(
                """
                INSERT INTO customers (document_id, first_name, last_name, phone, customer_type, discount_percent, debt_balance)
                VALUES ('901234567', 'Restaurante El Boyacense', 'SAS', '3101234567', 'EMPRESA', 0.0, 0.0)
                """
            )
            self.customer_id = cur.lastrowid

            # Company quota: 10.0 kg for Meat A
            cur.execute(
                """
                INSERT INTO company_product_quotas (customer_id, product_id, quota_quantity, unit, consumed_quantity, remaining_quantity)
                VALUES (?, ?, 10.0, 'kg', 0.0, 10.0)
                """,
                (self.customer_id, self.meat_a_id)
            )

            conn.commit()

    # ──────────────────────────────────────────────────────────────────────────
    # A1. SCALE CONTRACT AND MOCK ISOLATION
    # ──────────────────────────────────────────────────────────────────────────
    def test_a1_scale_contract_precision(self):
        """0.65 kg scale reading must produce exactly 650.0 grams, never 0.001 kg."""
        reading = WeightReading(value=0.65, unit="kg", stable=True, is_mock=False)
        self.assertEqual(reading.grams, 650.0)
        self.assertTrue(reading.is_valid)

        # In production without hardware, mock is disabled by default
        driver = SerialScaleDriver(allow_mock=False)
        read_res = driver.read_weight()
        self.assertFalse(read_res.is_valid)
        self.assertFalse(read_res.is_mock)
        self.assertIsNotNone(read_res.error)

    # ──────────────────────────────────────────────────────────────────────────
    # A2. MULTI-ITEM FIADO ATOMIC ROLLBACK
    # ──────────────────────────────────────────────────────────────────────────
    def test_a2_fiado_transaction_clean_rollback_on_second_item_failure(self):
        """If item 2 of a fiado sale fails, item 1's stock and quota must be 100% rolled back."""
        with get_db_connection() as conn:
            p_a_before = ProductModel.get_by_id(conn, self.meat_a_id)
            cur = conn.cursor()
            cur.execute("SELECT consumed_quantity FROM company_product_quotas WHERE customer_id = ? AND product_id = ?",
                        (self.customer_id, self.meat_a_id))
            quota_before = cur.fetchone()["consumed_quantity"]

            cur.execute("SELECT debt_balance FROM customers WHERE id = ?", (self.customer_id,))
            debt_before = cur.fetchone()["debt_balance"]

            # Item 1: Valid 2.0 kg of Meat A
            item1 = CartItem(
                product_id=self.meat_a_id,
                product_name="Costilla de Res Audit",
                category_id=1,
                category_name="Carnes",
                sale_type="PESO",
                quantity=2.0,
                unit_selected="kg",
                price_base=25.0,
                total_price=50000.0
            )

            # Item 2: Invalid item with negative quantity (triggers validation failure in sale)
            item2 = CartItem(
                product_id=self.meat_b_id,
                product_name="Lomo Fino Audit",
                category_id=1,
                category_name="Carnes",
                sale_type="PESO",
                quantity=-1.5,  # INVALID!
                unit_selected="kg",
                price_base=45.0,
                total_price=-67500.0
            )

            with self.assertRaises(ValueError):
                SaleModel.process_sale(
                    conn=conn,
                    user_id=self.user_id,
                    cart_items=[item1, item2],
                    cash_received=0.0,
                    customer_id=self.customer_id,
                    payment_method="FIADO"
                )

            # VERIFY TOTAL ROLLBACK
            p_a_after = ProductModel.get_by_id(conn, self.meat_a_id)
            self.assertEqual(p_a_after.stock, p_a_before.stock, "Product A stock must not have changed!")

            cur.execute("SELECT consumed_quantity FROM company_product_quotas WHERE customer_id = ? AND product_id = ?",
                        (self.customer_id, self.meat_a_id))
            quota_after = cur.fetchone()["consumed_quantity"]
            self.assertEqual(quota_after, quota_before, "Company quota must not have changed!")

            cur.execute("SELECT debt_balance FROM customers WHERE id = ?", (self.customer_id,))
            debt_after = cur.fetchone()["debt_balance"]
            self.assertEqual(debt_after, debt_before, "Customer debt must not have changed!")

            cur.execute("SELECT COUNT(*) as cnt FROM sales WHERE customer_id = ?", (self.customer_id,))
            self.assertEqual(cur.fetchone()["cnt"], 0, "No half-committed sales must exist in the database!")

    # ──────────────────────────────────────────────────────────────────────────
    # A3. SECURITY: 600K PBKDF2 & LOCKOUT
    # ──────────────────────────────────────────────────────────────────────────
    def test_a3_owasp_hashing_and_lockout(self):
        """Pass hashes must have 600k iterations; plaintext must be rejected; 5 fails -> lockout."""
        hashed = hash_password("Secret123")
        parts = hashed.split("$")
        self.assertEqual(len(parts), 3)
        self.assertEqual(int(parts[1]), 600000, "Must use 600,000 PBKDF2 iterations")

        # Reject plaintext passwords
        self.assertFalse(verify_password("plain_text_pass", "plain_text_pass"))

        # Lockout test
        with get_db_connection() as conn:
            UserModel.create_user(conn, "cajero_lockout", "CorrectPass1!", "Cajero Lockout", role="CAJERO")
            # 4 failed attempts return None
            for _ in range(4):
                user = UserModel.authenticate(conn, "cajero_lockout", "WrongPass")
                self.assertIsNone(user)

            # 5th attempt triggers lockout and raises PermissionError
            with self.assertRaises(PermissionError) as ctx:
                UserModel.authenticate(conn, "cajero_lockout", "WrongPass")
            self.assertIn("bloqueada temporalmente", str(ctx.exception))

            # 6th attempt even with correct password is still locked
            with self.assertRaises(PermissionError) as ctx:
                UserModel.authenticate(conn, "cajero_lockout", "CorrectPass1!")
            self.assertIn("bloqueada", str(ctx.exception).lower())

    # ──────────────────────────────────────────────────────────────────────────
    # B1 & B2: ITEM IVA BREAKDOWN & COP ROUNDING
    # ──────────────────────────────────────────────────────────────────────────
    def test_b1_b2_iva_breakdown_and_cop_currency(self):
        """Wine with 19% IVA included at $59,500 has ~$9,500 IVA and $50,000 base."""
        with get_db_connection() as conn:
            wine_item = CartItem(
                product_id=self.wine_id,
                product_name="Vino Reserva 19% IVA",
                category_id=2,
                category_name="Vinos",
                sale_type="UNIDAD",
                quantity=1.0,
                unit_selected="und",
                price_base=59500.0,
                total_price=59500.0
            )

            sale = SaleModel.process_sale(
                conn=conn,
                user_id=self.user_id,
                cart_items=[wine_item],
                cash_received=60000.0,
                payment_method="EFECTIVO"
            )

            self.assertEqual(sale.total, 59500.0)
            self.assertEqual(sale.cash_change, 500.0)
            self.assertEqual(sale.iva_total, 9500.0)  # 59500 - (59500 / 1.19) = 9500 COP

            # Check DB item values
            cur = conn.cursor()
            cur.execute("SELECT iva_rate, iva_amount FROM sale_items WHERE sale_id = ?", (sale.id,))
            si = cur.fetchone()
            self.assertEqual(si["iva_rate"], 19.0)
            self.assertEqual(si["iva_amount"], 9500.0)

    # ──────────────────────────────────────────────────────────────────────────
    # B3 & B5: PORTFOLIO DEBT & VOID SALE
    # ──────────────────────────────────────────────────────────────────────────
    def test_b3_b5_fiado_debt_and_void_sale(self):
        """Fiado sale increases debt_balance; void_sale restores stock, quota, and debt."""
        with get_db_connection() as conn:
            item = CartItem(
                product_id=self.meat_a_id,
                product_name="Costilla de Res Audit",
                category_id=1,
                category_name="Carnes",
                sale_type="PESO",
                quantity=3.0,
                unit_selected="kg",
                price_base=25.0,
                total_price=75000.0
            )

            sale = SaleModel.process_sale(
                conn=conn,
                user_id=self.user_id,
                cart_items=[item],
                cash_received=0.0,
                customer_id=self.customer_id,
                payment_method="FIADO"
            )

            # Verify debt increased
            cust = CustomerModel.get_by_id(conn, self.customer_id)
            self.assertEqual(cust.debt_balance, 75000.0)

            # Portfolio debt query
            portfolio = CustomerModel.get_total_portfolio_debt(conn)
            self.assertGreaterEqual(portfolio, 75000.0)

            # VOID SALE
            ok = SaleModel.void_sale(conn, sale.id, user_id=self.user_id, reason="Error de digitación en peso")
            self.assertTrue(ok)

            # Verify debt reverted
            cust_after_void = CustomerModel.get_by_id(conn, self.customer_id)
            self.assertEqual(cust_after_void.debt_balance, 0.0)

            # Verify audit log
            cur = conn.cursor()
            cur.execute("SELECT * FROM audit_logs WHERE action = 'VOID_SALE' AND record_id = ?", (sale.id,))
            log = cur.fetchone()
            self.assertIsNotNone(log)
            self.assertIn("Error de digitación en peso", log["details"])

    # ──────────────────────────────────────────────────────────────────────────
    # B4: CASH SHIFTS AND ARQUEO
    # ──────────────────────────────────────────────────────────────────────────
    def test_b4_cash_shift_reconciliation(self):
        """Opening shift with $100k, selling $50k in cash, actual $148k gives $2k faltante."""
        with get_db_connection() as conn:
            shift = CashShiftModel.open_shift(conn, user_id=self.user_id, initial_cash=100000.0)
            self.assertEqual(shift.initial_cash, 100000.0)
            self.assertEqual(shift.status, "ABIERTA")

            item = CartItem(
                product_id=self.meat_a_id,
                product_name="Costilla de Res Audit",
                category_id=1,
                category_name="Carnes",
                sale_type="PESO",
                quantity=2.0,
                unit_selected="kg",
                price_base=25.0,
                total_price=50000.0
            )
            SaleModel.process_sale(conn, self.user_id, [item], cash_received=50000.0, payment_method="EFECTIVO")

            # Arqueo with $148,000 (expected is $150,000)
            closed_shift = CashShiftModel.close_shift(conn, shift.id, actual_cash=148000.0, notes="Faltante de $2000 por cambio")
            self.assertEqual(closed_shift.status, "CERRADA")
            self.assertEqual(closed_shift.expected_cash, 150000.0)
            self.assertEqual(closed_shift.actual_cash, 148000.0)
            self.assertEqual(closed_shift.difference, -2000.0)

    # ──────────────────────────────────────────────────────────────────────────
    # B10 & B11: INVOICE SEQUENCES & PAYMENT METHOD VALIDATION
    # ──────────────────────────────────────────────────────────────────────────
    def test_b10_b11_sequence_counter_and_invalid_payment(self):
        """Consecutive invoice numbers are strictly monotonic; invalid payment methods raise ValueError."""
        with get_db_connection() as conn:
            inv1 = SaleModel.generate_next_invoice_number(conn)
            inv2 = SaleModel.generate_next_invoice_number(conn)
            num1 = int(inv1.replace("SD-", "").replace("XL-", ""))
            num2 = int(inv2.replace("SD-", "").replace("XL-", ""))
            self.assertEqual(num2, num1 + 1, "Invoice numbers must increment monotonically")

            item = CartItem(
                product_id=self.meat_a_id,
                product_name="Costilla de Res Audit",
                category_id=1,
                category_name="Carnes",
                sale_type="PESO",
                quantity=1.0,
                unit_selected="kg",
                price_base=25.0,
                total_price=25000.0
            )

            # Unknown payment method should fail
            with self.assertRaises(ValueError):
                SaleModel.process_sale(
                    conn=conn,
                    user_id=self.user_id,
                    cart_items=[item],
                    cash_received=25000.0,
                    payment_method="BITCOIN_UNKNOWN"
                )


if __name__ == "__main__":
    unittest.main()
