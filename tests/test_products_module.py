"""Unit and integration test suite for the Products & Inventory Module in Carnicería San Diego.
Validates:
- Product model dataclass attributes (ID, barcode, name, category, unit_measure, price_base, cost, iva, stock, min_stock).
- Automated inventory status (Agotado, Bajo, Normal) derived strictly from stock vs min_stock.
- Profit margin calculation ($ and %) and inventory valuations.
- ProductModel CRUD operations (create, update, get_all, get_by_id, search, multi-filters, delete).
- Barcode uniqueness checks.
- InventoryFrame UI smoke tests (filtering, sorting asc/desc, modals launch).
"""

import os
import sys
import sqlite3
import unittest
import customtkinter as ctk

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.connection import get_db_connection, initialize_database
from models.product import (
    Product,
    ProductModel,
    format_currency,
    format_currency_short,
    format_stock_display
)
from views.inventory_frame import InventoryFrame, ProductDetailModal, ProductFormModal, AddStockModal


class TestProductsModule(unittest.TestCase):
    """Test suite covering the complete Products and Inventory module."""

    @classmethod
    def setUpClass(cls):
        initialize_database()

    def setUp(self):
        # Create an in-memory SQLite database replicating the production schema for isolated testing
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")

        from database.connection import normalize_text
        self.conn.create_function("NORMALIZE_TEXT", 1, normalize_text)

        # Build schema
        self.conn.executescript("""
            CREATE TABLE categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                barcode TEXT UNIQUE,
                name TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                sale_type TEXT CHECK (sale_type IN ('PESO', 'UNIDAD')) NOT NULL,
                price_base REAL NOT NULL,
                cost REAL NOT NULL DEFAULT 0,
                iva REAL NOT NULL DEFAULT 0,
                unit_measure TEXT NOT NULL DEFAULT 'kg',
                stock REAL NOT NULL DEFAULT 0,
                min_stock REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE RESTRICT
            );

            INSERT INTO categories (id, name) VALUES (1, 'Carnes de Res');
            INSERT INTO categories (id, name) VALUES (2, 'Vinos y Licores');
            INSERT INTO categories (id, name) VALUES (3, 'Amasijos de Boyacá');
        """)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_01_automated_inventory_status(self):
        """Verify that product status is automatically determined: Agotado, Bajo, Normal."""
        # 1. Normal stock: stock > min_stock
        p_normal = Product(
            id=1, barcode="1001", name="Lomo Fino", category_id=1, category_name="Carnes de Res",
            sale_type="PESO", price_base=55.0, cost=38.0, iva=0.0, unit_measure="kg",
            stock=15000.0, min_stock=3000.0
        )
        self.assertEqual(p_normal.status, "Normal")
        self.assertFalse(p_normal.is_low_stock)
        self.assertFalse(p_normal.is_out_of_stock)
        badge_lbl, badge_bg, _, badge_fg = p_normal.status_badge
        self.assertIn("Normal", badge_lbl)

        # 2. Low stock: 0 < stock <= min_stock
        p_low = Product(
            id=2, barcode="1002", name="Chatas", category_id=1, category_name="Carnes de Res",
            sale_type="PESO", price_base=40.0, cost=28.0, iva=0.0, unit_measure="kg",
            stock=2500.0, min_stock=3000.0
        )
        self.assertEqual(p_low.status, "Bajo")
        self.assertTrue(p_low.is_low_stock)
        self.assertFalse(p_low.is_out_of_stock)
        badge_lbl, _, _, _ = p_low.status_badge
        self.assertIn("Bajo", badge_lbl)

        # 3. Out of stock: stock <= 0
        p_out = Product(
            id=3, barcode="1003", name="Ribeye", category_id=1, category_name="Carnes de Res",
            sale_type="PESO", price_base=45.0, cost=32.0, iva=0.0, unit_measure="kg",
            stock=0.0, min_stock=3000.0
        )
        self.assertEqual(p_out.status, "Agotado")
        self.assertTrue(p_out.is_out_of_stock)
        badge_lbl, _, _, _ = p_out.status_badge
        self.assertIn("Agotado", badge_lbl)

        # Negative stock also resolves to Agotado
        p_neg = Product(
            id=4, barcode="1004", name="Costilla", category_id=1, category_name="Carnes de Res",
            sale_type="PESO", price_base=25.0, cost=18.0, iva=0.0, unit_measure="kg",
            stock=-500.0, min_stock=2000.0
        )
        self.assertEqual(p_neg.status, "Agotado")

    def test_02_pricing_margins_and_valuations(self):
        """Verify commercial pricing displays, profit margins, and inventory valuation."""
        # Weight product (PESO): price_base = 45 $/g = 45.000 $/kg. Cost = 32 $/g = 32.000 $/kg.
        p_peso = Product(
            id=1, barcode="7701", name="Ribeye Choice", category_id=1, category_name="Carnes de Res",
            sale_type="PESO", price_base=45.0, cost=32.0, iva=0.0, unit_measure="kg",
            stock=10000.0, min_stock=2000.0  # 10 kg
        )
        self.assertEqual(p_peso.display_price_sale, "$ 45.000/kg")
        self.assertEqual(p_peso.display_cost, "$ 32.000/kg")
        self.assertEqual(p_peso.profit_margin_amount, 13000.0)  # 45000 - 32000
        self.assertAlmostEqual(p_peso.profit_margin_pct, (13000.0 / 45000.0) * 100.0, places=2)
        self.assertEqual(p_peso.total_inventory_valuation_cost, 10000.0 * 32.0)  # 320.000 COP
        self.assertEqual(p_peso.total_inventory_valuation_sale, 10000.0 * 45.0)  # 450.000 COP
        self.assertEqual(p_peso.display_stock, "10 kg")
        self.assertEqual(p_peso.display_min_stock, "2 kg")

        # Unit product (UNIDAD) with IVA 19%
        p_unit = Product(
            id=2, barcode="7702", name="Vino Tinto Reserva", category_id=2, category_name="Vinos y Licores",
            sale_type="UNIDAD", price_base=65000.0, cost=42000.0, iva=19.0, unit_measure="und",
            stock=20.0, min_stock=5.0
        )
        self.assertEqual(p_unit.display_price_sale, "$ 65.000/und")
        self.assertEqual(p_unit.display_cost, "$ 42.000/und")
        self.assertEqual(p_unit.profit_margin_amount, 23000.0)
        self.assertEqual(p_unit.display_iva, "19%")
        self.assertEqual(p_unit.display_stock, "20 und")
        self.assertEqual(p_unit.total_inventory_valuation_cost, 20.0 * 42000.0)
        self.assertEqual(p_unit.total_inventory_valuation_sale, 20.0 * 65000.0)

    def test_03_product_crud_operations(self):
        """Test creating, reading, updating, and deleting products in the database."""
        # 1. Create
        pid = ProductModel.create(
            conn=self.conn,
            barcode="99001",
            name="Punta de Anca Premium",
            category_id=1,
            sale_type="PESO",
            price_base=48.0,
            cost=34.0,
            iva=0.0,
            unit_measure="kg",
            stock=15000.0,
            min_stock=3000.0
        )
        self.assertGreater(pid, 0)

        # 2. Read by ID
        prod = ProductModel.get_by_id(self.conn, pid)
        self.assertIsNotNone(prod)
        self.assertEqual(prod.name, "Punta de Anca Premium")
        self.assertEqual(prod.price_base, 48.0)
        self.assertEqual(prod.cost, 34.0)
        self.assertEqual(prod.unit_measure, "kg")
        self.assertEqual(prod.status, "Normal")

        # 3. Read by Barcode
        prod_bar = ProductModel.get_by_barcode(self.conn, "99001")
        self.assertIsNotNone(prod_bar)
        self.assertEqual(prod_bar.id, pid)

        # 4. Update
        ProductModel.update(
            conn=self.conn,
            product_id=pid,
            barcode="99001-MOD",
            name="Punta de Anca Madurada",
            category_id=1,
            sale_type="PESO",
            price_base=52.0,
            cost=36.0,
            iva=0.0,
            unit_measure="kg",
            stock=2000.0,  # Now stock <= min_stock (3000) -> status should become 'Bajo'
            min_stock=3000.0
        )
        updated = ProductModel.get_by_id(self.conn, pid)
        self.assertEqual(updated.name, "Punta de Anca Madurada")
        self.assertEqual(updated.barcode, "99001-MOD")
        self.assertEqual(updated.price_base, 52.0)
        self.assertEqual(updated.cost, 36.0)
        self.assertEqual(updated.status, "Bajo")

        # 5. Delete
        ProductModel.delete(self.conn, pid)
        self.assertIsNone(ProductModel.get_by_id(self.conn, pid))

    def test_04_barcode_uniqueness_check(self):
        """Verify barcode conflict detection helper."""
        ProductModel.create(
            conn=self.conn,
            barcode="BAR-12345",
            name="Queso Campesino",
            category_id=1,
            sale_type="PESO",
            price_base=25.0,
            cost=18.0,
            iva=0.0,
            unit_measure="kg",
            stock=5000.0,
            min_stock=1000.0
        )

        # Check existing barcode
        self.assertTrue(ProductModel.check_barcode_exists(self.conn, "BAR-12345"))
        # Check non-existing barcode
        self.assertFalse(ProductModel.check_barcode_exists(self.conn, "BAR-99999"))

        # Check with exclude_id (e.g. editing the same product)
        prod = ProductModel.get_by_barcode(self.conn, "BAR-12345")
        self.assertFalse(ProductModel.check_barcode_exists(self.conn, "BAR-12345", exclude_id=prod.id))

    def test_05_search_and_multi_filtering(self):
        """Test searching and multi-filtering across categories, status, and sale_type."""
        # Insert test products
        ProductModel.create(self.conn, "B1", "Carne Moler", 1, "PESO", 26.0, 18.0, 0.0, "kg", 20000.0, 5000.0)  # Normal
        ProductModel.create(self.conn, "B2", "Costilla Cerdo", 1, "PESO", 28.0, 20.0, 0.0, "kg", 2000.0, 4000.0)  # Bajo
        ProductModel.create(self.conn, "B3", "Trucha Fresca", 1, "PESO", 32.0, 22.0, 0.0, "kg", 0.0, 2000.0)      # Agotado
        ProductModel.create(self.conn, "B4", "Vino Tinto", 2, "UNIDAD", 65000.0, 40000.0, 19.0, "botella", 15.0, 3.0)  # Normal
        ProductModel.create(self.conn, "B5", "Almojabana", 3, "UNIDAD", 2500.0, 1500.0, 0.0, "und", 5.0, 10.0)  # Bajo

        # 1. Search by name
        res = ProductModel.get_all(self.conn, search_query="moler")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].name, "Carne Moler")

        # 2. Search by category name
        res_cat = ProductModel.get_all(self.conn, search_query="vinos")
        self.assertEqual(len(res_cat), 1)
        self.assertEqual(res_cat[0].name, "Vino Tinto")

        # 3. Filter by category_id
        res_beef = ProductModel.get_all(self.conn, category_id=1)
        self.assertEqual(len(res_beef), 3)

        # 4. Filter by sale_type
        res_peso = ProductModel.get_all(self.conn, sale_type_filter="PESO")
        self.assertEqual(len(res_peso), 3)
        res_und = ProductModel.get_all(self.conn, sale_type_filter="UNIDAD")
        self.assertEqual(len(res_und), 2)

        # 5. Filter by calculated status
        res_agotado = ProductModel.get_all(self.conn, status_filter="Agotado")
        self.assertEqual(len(res_agotado), 1)
        self.assertEqual(res_agotado[0].name, "Trucha Fresca")

        res_bajo = ProductModel.get_all(self.conn, status_filter="Bajo")
        self.assertEqual(len(res_bajo), 2)

        res_normal = ProductModel.get_all(self.conn, status_filter="Normal")
        self.assertEqual(len(res_normal), 2)

    def test_06_ui_frame_and_sorting(self):
        """Smoke test verifying InventoryFrame initialization, sorting and filtering."""
        root = ctk.CTk()
        root.withdraw()
        try:
            frame = InventoryFrame(parent=root)
            self.assertIsNotNone(frame.controls_bar)
            self.assertIsNotNone(frame.header_row)
            self.assertIsNotNone(frame.rows_scroll)

            # Test sorting toggle
            frame.sort_column = "price_base"
            frame.sort_direction = "asc"
            frame._apply_filters_and_render()
            self.assertEqual(frame.sort_column, "price_base")

            # Header click on price_base should flip to desc
            frame._on_header_click("price_base")
            self.assertEqual(frame.sort_direction, "desc")

            # Header click on name should switch column and reset to asc
            frame._on_header_click("name")
            self.assertEqual(frame.sort_column, "name")
            self.assertEqual(frame.sort_direction, "asc")

            # Test search entry clear
            frame.search_entry.insert(0, "Hamburguesa")
            frame._on_filter_changed()
            self.assertGreaterEqual(len(frame.filtered_products), 1)
            frame._clear_search()
            self.assertEqual(frame.search_entry.get(), "")
        finally:
            root.destroy()

    def test_07_add_stock_model_methods(self):
        """Test ProductModel.add_stock and ProductModel.add_stock_batch atomic updates."""
        pid1 = ProductModel.create(
            self.conn,
            barcode="7701",
            name="Ribeye Choice",
            category_id=1,
            sale_type="PESO",
            price_base=45.0,
            cost=30.0,
            stock=15000.0,
            min_stock=3000.0
        )
        pid2 = ProductModel.create(
            self.conn,
            barcode="7702",
            name="Queso Paipa",
            category_id=3,
            sale_type="UNIDAD",
            price_base=25000.0,
            cost=18000.0,
            stock=20.0,
            min_stock=5.0
        )

        p1 = ProductModel.get_by_id(self.conn, pid1)
        self.assertEqual(p1.stock, 15000.0)

        p2 = ProductModel.get_by_id(self.conn, pid2)
        self.assertEqual(p2.stock, 20.0)

        # Single add_stock
        ProductModel.add_stock(self.conn, pid1, 5000.0)  # +5 kg
        p1_updated = ProductModel.get_by_id(self.conn, pid1)
        self.assertEqual(p1_updated.stock, 20000.0)

        ProductModel.add_stock(self.conn, pid2, 5.0)  # +5 und
        p2_updated = ProductModel.get_by_id(self.conn, pid2)
        self.assertEqual(p2_updated.stock, 25.0)

        # Batch add_stock
        batch = [
            (pid1, 2500.0),  # +2.5 kg
            (pid2, 10.0)     # +10 und
        ]
        ProductModel.add_stock_batch(self.conn, batch)

        p1_final = ProductModel.get_by_id(self.conn, pid1)
        self.assertEqual(p1_final.stock, 22500.0)

        p2_final = ProductModel.get_by_id(self.conn, pid2)
        self.assertEqual(p2_final.stock, 35.0)

    def test_08_inventory_frame_add_stock_button_and_permissions(self):
        """Verify that the 'Agregar Stock' button is visible for Admin and hidden for Cashier."""
        from models.user import User
        root = ctk.CTk()
        root.withdraw()
        try:
            admin_user = User(id=1, username="admin", password_hash="dummy_hash", full_name="Admin", role="ADMIN")
            cashier_user = User(id=2, username="cajero", password_hash="dummy_hash", full_name="Cajero", role="CASHIER")

            # As Admin
            frame = InventoryFrame(parent=root, current_user=admin_user)
            self.assertTrue(hasattr(frame, "add_stock_btn"))
            self.assertEqual(frame.add_stock_btn.cget("text"), " Agregar stock")
            self.assertEqual(frame.add_stock_btn.winfo_manager(), "pack")

            # Switch to Cashier
            frame.set_current_user(cashier_user)
            self.assertEqual(frame.add_stock_btn.winfo_manager(), "")

            # Switch back to Admin
            frame.set_current_user(admin_user)
            self.assertEqual(frame.add_stock_btn.winfo_manager(), "pack")
        finally:
            root.destroy()

    def test_09_add_stock_modal_staging_and_batch_logic(self):
        """Test AddStockModal product selection, quantity entry, staging, and accumulation."""
        root = ctk.CTk()
        root.withdraw()
        try:
            saved = False
            def on_save():
                nonlocal saved
                saved = True

            modal = AddStockModal(parent=root, on_save_callback=on_save)
            self.assertIsNotNone(modal.product_combo)
            self.assertIsNotNone(modal.qty_entry)
            self.assertIsNotNone(modal.unit_combo)
            self.assertIsNotNone(modal.batch_scroll)

            if modal.all_products:
                p = modal.all_products[0]
                modal._select_product(p)
                self.assertEqual(modal.selected_product.id, p.id)

                # Enter quantity
                modal.qty_entry.insert(0, "3")
                modal.unit_combo.set("kg" if p.sale_type == "PESO" else p.unit_measure)
                modal._on_qty_change()

                # Add to batch
                modal._add_current_to_batch()
                self.assertEqual(len(modal.batch_items), 1)
                self.assertEqual(modal.batch_items[0]["product_id"], p.id)
                self.assertEqual(modal.batch_items[0]["input_qty"], 3.0)

                # Add same product again (should accumulate)
                modal._select_product(p)
                modal.qty_entry.insert(0, "2")
                modal._add_current_to_batch()
                self.assertEqual(len(modal.batch_items), 1)
                self.assertEqual(modal.batch_items[0]["input_qty"], 5.0)

                # Remove from batch
                modal._remove_from_batch(0)
                self.assertEqual(len(modal.batch_items), 0)

            modal.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
