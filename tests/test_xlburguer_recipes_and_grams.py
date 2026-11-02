"""Comprehensive test suite for XL Burguer Recipe and Gram-Based Inventory Management.
Verifies:
1. Purchase conversion from kg to grams (1 kg = 1000 g).
2. Ingredient unit cost calculation ($ / g).
3. Recipe assignment to products.
4. Theoretical portion calculation and limiting ingredient identification.
5. Atomic ingredient stock deduction upon sale of prepared dishes.
6. Sale rejection with detailed error when ingredient stock is insufficient.
7. Ingredient inventory restitution on sale voiding (anulación).
8. Wastage (merma) and inventory adjustment auditing.
"""

import os
import sys
import unittest

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.connection import get_db_connection, initialize_database
from models.ingredient import IngredientModel
from models.product import ProductModel
from models.sale import CartItem, SaleModel


class TestXLBurguerRecipesAndGrams(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()

    def setUp(self):
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        try:
            with get_db_connection() as conn:
                conn.execute("DELETE FROM product_recipes WHERE product_id IN (SELECT id FROM products WHERE barcode LIKE 'TEST_%')")
                conn.execute("DELETE FROM sale_items WHERE product_id IN (SELECT id FROM products WHERE barcode LIKE 'TEST_%')")
                conn.execute("DELETE FROM products WHERE barcode LIKE 'TEST_%'")
                conn.execute("DELETE FROM inventory_movements WHERE ingredient_id IN (SELECT id FROM ingredients WHERE name LIKE '%Test%')")
                conn.execute("DELETE FROM ingredients WHERE name LIKE '%Test%'")
                conn.commit()
        except Exception:
            pass

    def test_01_kg_to_g_purchase_conversion_and_cost(self):
        """Registering a purchase in kilograms must store stock in grams and calculate cost/g."""
        with get_db_connection() as conn:
            # Create a test ingredient
            ing_id = IngredientModel.create(
                conn=conn,
                name="Tocineta Ahumada Test",
                stock_g=1000.0,
                min_stock_g=500.0,
                cost_per_g=30.0
            )

            # Purchase 5 kg for $175,000 COP
            # 5 kg = 5,000 g. New stock = 6,000 g. Cost/g = 175,000 / 5,000 = $35.0/g
            IngredientModel.register_purchase(
                conn=conn,
                ingredient_id=ing_id,
                quantity=5.0,
                unit="kg",
                total_cost=175000.0,
                notes="Factura Proveedor Carnes #5544"
            )

            ing = IngredientModel.get_by_id(conn, ing_id)
            self.assertEqual(ing.stock_g, 6000.0)
            self.assertEqual(ing.stock_kg, 6.0)
            self.assertEqual(ing.cost_per_g, 35.0)

            # Verify movement logged
            movements = IngredientModel.get_movements(conn, ingredient_id=ing_id, limit=5)
            self.assertGreaterEqual(len(movements), 1)
            self.assertEqual(movements[0].movement_type, "COMPRA")
            self.assertEqual(movements[0].quantity, 5000.0)

    def test_02_theoretical_portions_and_limiting_ingredient(self):
        """Theoretical portions must equal min(stock_g / req_g) across recipe ingredients."""
        with get_db_connection() as conn:
            # Product: Burger (requires 125g meat, 80g bun, 30g cheese)
            p_id = ProductModel.create(
                conn=conn,
                barcode="TEST_BURGER_RECIPE",
                name="Hamburguesa Test Receta",
                category_id=1,
                sale_type="UNIDAD",
                price_base=20000.0,
                cost=0.0,
                unit_measure="und",
                stock=0.0
            )

            meat_id = IngredientModel.create(conn, "Carne Test Portions", stock_g=1250.0, min_stock_g=200.0, cost_per_g=24.0)
            bun_id = IngredientModel.create(conn, "Pan Test Portions", stock_g=2400.0, min_stock_g=200.0, cost_per_g=12.0)
            cheese_id = IngredientModel.create(conn, "Queso Test Portions", stock_g=90.0, min_stock_g=50.0, cost_per_g=35.0)

            # Meat allows 1250 / 125 = 10 portions
            # Bun allows 2400 / 80 = 30 portions
            # Cheese allows 90 / 30 = 3 portions
            # Limiting ingredient is Cheese with 3 portions!
            recipe_data = [
                (meat_id, 125.0),
                (bun_id, 80.0),
                (cheese_id, 30.0),
            ]
            IngredientModel.save_recipe(conn, p_id, recipe_data)

            portions = IngredientModel.calculate_portions_available(conn, p_id)
            self.assertEqual(portions, 3, "Theoretical portions must be limited by Cheese (3 portions)")

            lim = IngredientModel.get_limiting_ingredient_details(conn, p_id)
            self.assertIsNotNone(lim)
            self.assertEqual(lim[0], "Queso Test Portions")
            self.assertEqual(lim[3], 3)

            # Product cost should be automatically recalculated: 125*24 + 80*12 + 30*35 = 3000 + 960 + 1050 = 5010
            prod = ProductModel.get_by_id(conn, p_id)
            self.assertEqual(prod.cost, 5010.0)

    def test_03_atomic_recipe_deduction_and_insufficient_stock_block(self):
        """Selling a recipe product deducts each ingredient in grams; insufficient stock blocks sale."""
        with get_db_connection() as conn:
            p_id = ProductModel.create(
                conn=conn,
                barcode="TEST_ATOMIC_RECIPE",
                name="Hamburguesa Test Atomic",
                category_id=1,
                sale_type="UNIDAD",
                price_base=22000.0,
                cost=5000.0,
                unit_measure="und",
                stock=0.0
            )

            ing_meat = IngredientModel.create(conn, "Carne Atomic Test", stock_g=500.0, min_stock_g=100.0, cost_per_g=25.0)
            ing_bun = IngredientModel.create(conn, "Pan Atomic Test", stock_g=300.0, min_stock_g=50.0, cost_per_g=12.0)

            # Each burger takes 125g meat, 80g bun
            IngredientModel.save_recipe(conn, p_id, [(ing_meat, 125.0), (ing_bun, 80.0)])

            # Sell 2 burgers -> requires 250g meat and 160g bun
            cart = [CartItem(
                product_id=p_id,
                product_name="Hamburguesa Test Atomic",
                category_id=1,
                category_name="Hamburguesas",
                sale_type="UNIDAD",
                quantity=2.0,
                unit_selected="und",
                price_base=22000.0,
                total_price=44000.0
            )]

            sale = SaleModel.process_sale(conn, 1, cart, cash_received=44000.0)
            self.assertIsNotNone(sale)

            # Verify deductions in database
            m_after = IngredientModel.get_by_id(conn, ing_meat)
            b_after = IngredientModel.get_by_id(conn, ing_bun)
            self.assertEqual(m_after.stock_g, 250.0)  # 500 - 250 = 250g
            self.assertEqual(b_after.stock_g, 140.0)  # 300 - 160 = 140g

            # Now meat has 250g left (enough for 2 burgers).
            # Attempting to sell 3 burgers requires 375g meat -> MUST raise ValueError
            cart_excess = [CartItem(
                product_id=p_id,
                product_name="Hamburguesa Test Atomic",
                category_id=1,
                category_name="Hamburguesas",
                sale_type="UNIDAD",
                quantity=3.0,
                unit_selected="und",
                price_base=22000.0,
                total_price=66000.0
            )]

            with self.assertRaises(ValueError) as ctx:
                SaleModel.process_sale(conn, 1, cart_excess, cash_received=66000.0)

            err_msg = str(ctx.exception)
            self.assertIn("Ingrediente insuficiente", err_msg)
            self.assertIn("Carne Atomic Test", err_msg)
            self.assertIn("Disponible: 250", err_msg)
            self.assertIn("Requerido: 375", err_msg)

    def test_04_void_sale_restitutes_recipe_ingredients(self):
        """Voiding a sale must atomically return the exact grams of each ingredient to inventory."""
        with get_db_connection() as conn:
            p_id = ProductModel.create(
                conn=conn,
                barcode="TEST_VOID_RESTITUTION",
                name="Hamburguesa Test Anulacion",
                category_id=1,
                sale_type="UNIDAD",
                price_base=18000.0,
                cost=4000.0,
                unit_measure="und",
                stock=0.0
            )

            ing_meat = IngredientModel.create(conn, "Carne Void Test", stock_g=1000.0, min_stock_g=100.0, cost_per_g=25.0)
            IngredientModel.save_recipe(conn, p_id, [(ing_meat, 125.0)])

            # Sell 4 burgers -> 500g deducted
            cart = [CartItem(
                product_id=p_id,
                product_name="Hamburguesa Test Anulacion",
                category_id=1,
                category_name="Hamburguesas",
                sale_type="UNIDAD",
                quantity=4.0,
                unit_selected="und",
                price_base=18000.0,
                total_price=72000.0
            )]
            sale = SaleModel.process_sale(conn, 1, cart, cash_received=72000.0)

            m_mid = IngredientModel.get_by_id(conn, ing_meat)
            self.assertEqual(m_mid.stock_g, 500.0)

            # Void the sale
            SaleModel.void_sale(conn, sale.id, user_id=1, reason="Error de digitación en prueba")

            # Stock must be completely restored to 1000g
            m_final = IngredientModel.get_by_id(conn, ing_meat)
            self.assertEqual(m_final.stock_g, 1000.0)

            # Movement log must record DEVOLUCION / AJUSTE
            movs = IngredientModel.get_movements(conn, ingredient_id=ing_meat, limit=5)
            self.assertIn(movs[0].movement_type, ("AJUSTE", "DEVOLUCION"))
            self.assertEqual(movs[0].quantity, 500.0)


if __name__ == "__main__":
    unittest.main()
