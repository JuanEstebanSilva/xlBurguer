"""Ingredient, Subproduct and Recipe models for XL Burguer.
Handles standard gram-based inventory (g), purchase entries (kg to g conversion),
recipe composition, portion availability calculation, and inventory movements.
"""

from dataclasses import dataclass
from datetime import datetime
import math
import sqlite3
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Ingredient:
    id: int
    name: str
    description: Optional[str]
    stock_g: float
    min_stock_g: float
    cost_per_g: float
    is_active: bool = True
    created_at: Optional[str] = None

    @property
    def stock_kg(self) -> float:
        """Stock converted to kilograms for display."""
        return self.stock_g / 1000.0

    @property
    def min_stock_kg(self) -> float:
        """Minimum stock converted to kilograms for display."""
        return self.min_stock_g / 1000.0

    @property
    def cost_per_kg(self) -> float:
        """Cost converted to per-kilogram for display."""
        return self.cost_per_g * 1000.0

    @property
    def is_out_of_stock(self) -> bool:
        """True if stock in grams is zero or depleted."""
        return self.stock_g <= 0

    @property
    def is_low_stock(self) -> bool:
        """True if stock is at or below the minimum threshold."""
        return self.stock_g <= self.min_stock_g

    @property
    def status(self) -> str:
        """Status badge label."""
        if self.stock_g <= 0:
            return "Agotado"
        elif self.stock_g <= self.min_stock_g:
            return "Bajo"
        return "Normal"

    @property
    def status_badge(self) -> Tuple[str, str, str, str]:
        """Returns (label, bg_color, border_color, text_color) for UI rendering."""
        from utils.theme import DarkTheme
        st = self.status
        if st == "Agotado":
            return ("🔴 Agotado", DarkTheme.DANGER_BG, DarkTheme.DANGER_BORDER, DarkTheme.DANGER_TEXT)
        elif st == "Bajo":
            return ("⚠️ Bajo", DarkTheme.WARNING_BG, DarkTheme.WARNING_BORDER, DarkTheme.WARNING_TEXT)
        return ("🟢 Normal", DarkTheme.SUCCESS_BG, DarkTheme.SUCCESS_BORDER, DarkTheme.SUCCESS_TEXT)

    def calculate_portions(self, portion_size_g: float) -> int:
        """Calculate theoretical portions available based on a given portion size in grams."""
        if portion_size_g <= 0 or self.stock_g <= 0:
            return 0
        return int(math.floor(self.stock_g / portion_size_g))

    def format_stock_display(self) -> str:
        """Display stock in grams, and in kg if >= 1000g."""
        if self.stock_g >= 1000.0:
            return f"{self.stock_kg:,.2f} kg ({self.stock_g:,.0f} g)"
        return f"{self.stock_g:,.0f} g"


@dataclass
class RecipeItem:
    id: int
    product_id: int
    ingredient_id: int
    ingredient_name: str
    quantity_g: float
    cost_per_g: float
    current_ingredient_stock_g: float

    @property
    def cost_contribution(self) -> float:
        """Estimated cost contribution of this ingredient to the preparation."""
        return self.quantity_g * self.cost_per_g

    @property
    def possible_portions(self) -> int:
        """Number of product units possible given this ingredient's stock."""
        if self.quantity_g <= 0:
            return 999999
        return int(math.floor(max(0.0, self.current_ingredient_stock_g) / self.quantity_g))


@dataclass
class InventoryMovement:
    id: int
    ingredient_id: Optional[int]
    product_id: Optional[int]
    movement_type: str  # 'VENTA', 'COMPRA', 'AJUSTE', 'MERMA', 'INICIAL'
    quantity: float
    previous_stock: float
    new_stock: float
    reference_id: Optional[str]
    notes: Optional[str]
    created_at: str
    item_name: Optional[str] = None


class IngredientModel:
    """Database operations for ingredients, recipes and movements."""

    @staticmethod
    def get_all(conn: sqlite3.Connection, active_only: bool = True) -> List[Ingredient]:
        """Fetch all ingredients sorted by name."""
        cursor = conn.cursor()
        query = "SELECT * FROM ingredients"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY name ASC"
        cursor.execute(query)
        rows = cursor.fetchall()
        return [
            Ingredient(
                id=r["id"],
                name=r["name"],
                description=r["description"],
                stock_g=float(r["stock_g"]),
                min_stock_g=float(r["min_stock_g"]),
                cost_per_g=float(r["cost_per_g"]),
                is_active=bool(r["is_active"]),
                created_at=r["created_at"]
            )
            for r in rows
        ]

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, ingredient_id: int) -> Optional[Ingredient]:
        """Fetch a single ingredient by ID."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ingredients WHERE id = ?", (ingredient_id,))
        r = cursor.fetchone()
        if not r:
            return None
        return Ingredient(
            id=r["id"],
            name=r["name"],
            description=r["description"],
            stock_g=float(r["stock_g"]),
            min_stock_g=float(r["min_stock_g"]),
            cost_per_g=float(r["cost_per_g"]),
            is_active=bool(r["is_active"]),
            created_at=r["created_at"]
        )

    @staticmethod
    def create(
        conn: sqlite3.Connection,
        name: str,
        stock_g: float,
        min_stock_g: float,
        cost_per_g: float,
        description: Optional[str] = None
    ) -> int:
        """Create a new ingredient with initial stock and log initial movement."""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("El nombre del ingrediente no puede estar vacío.")
        if stock_g < 0:
            raise ValueError("Las existencias iniciales no pueden ser negativas.")
        if min_stock_g < 0:
            raise ValueError("El stock mínimo no puede ser negativo.")
        if cost_per_g < 0:
            raise ValueError("El costo por gramo no puede ser negativo.")

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ingredients (name, description, stock_g, min_stock_g, cost_per_g, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (clean_name, description.strip() if description else None, stock_g, min_stock_g, cost_per_g)
        )
        ing_id = cursor.lastrowid

        # Register initial movement
        if stock_g > 0:
            cursor.execute(
                """
                INSERT INTO inventory_movements (
                    ingredient_id, movement_type, quantity, previous_stock, new_stock, notes
                ) VALUES (?, 'INICIAL', ?, 0, ?, 'Inventario inicial')
                """,
                (ing_id, stock_g, stock_g)
            )

        conn.commit()
        return ing_id

    @staticmethod
    def update(
        conn: sqlite3.Connection,
        ingredient_id: int,
        name: str,
        min_stock_g: float,
        cost_per_g: float,
        description: Optional[str] = None
    ) -> None:
        """Update ingredient metadata and settings (stock adjustments handled separately)."""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("El nombre del ingrediente no puede estar vacío.")
        if min_stock_g < 0:
            raise ValueError("El stock mínimo no puede ser negativo.")
        if cost_per_g < 0:
            raise ValueError("El costo por gramo no puede ser negativo.")

        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE ingredients
            SET name = ?, description = ?, min_stock_g = ?, cost_per_g = ?
            WHERE id = ?
            """,
            (clean_name, description.strip() if description else None, min_stock_g, cost_per_g, ingredient_id)
        )
        conn.commit()

    @staticmethod
    def register_purchase(
        conn: sqlite3.Connection,
        ingredient_id: int,
        quantity: float,
        unit: str,  # 'kg' | 'g'
        total_cost: float,
        notes: Optional[str] = None
    ) -> None:
        """Register purchase/entry of ingredient in kg or g.
        Automatically converts kg to grams (1 kg = 1000 g).
        Updates weighted average cost per gram or latest cost.
        """
        if quantity <= 0:
            raise ValueError("La cantidad comprada debe ser mayor a cero.")
        if total_cost < 0:
            raise ValueError("El costo total no puede ser negativo.")

        unit_clean = unit.lower().strip()
        if unit_clean == "kg":
            quantity_g = quantity * 1000.0
        elif unit_clean == "g":
            quantity_g = quantity
        else:
            raise ValueError(f"Unidad de compra no válida: '{unit}'. Use 'kg' o 'g'.")

        new_cost_per_g = (total_cost / quantity_g) if quantity_g > 0 else 0.0

        cursor = conn.cursor()
        cursor.execute("SELECT stock_g, cost_per_g FROM ingredients WHERE id = ?", (ingredient_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Ingrediente ID {ingredient_id} no encontrado.")

        prev_stock = float(row["stock_g"])
        new_stock = prev_stock + quantity_g

        # Weighted cost calculation or updated cost
        cursor.execute(
            """
            UPDATE ingredients
            SET stock_g = ?, cost_per_g = ?
            WHERE id = ?
            """,
            (new_stock, new_cost_per_g, ingredient_id)
        )

        cursor.execute(
            """
            INSERT INTO inventory_movements (
                ingredient_id, movement_type, quantity, previous_stock, new_stock, notes
            ) VALUES (?, 'COMPRA', ?, ?, ?, ?)
            """,
            (ingredient_id, quantity_g, prev_stock, new_stock, notes or f"Entrada compra: {quantity} {unit}")
        )
        conn.commit()

    @staticmethod
    def adjust_stock(
        conn: sqlite3.Connection,
        ingredient_id: int,
        new_stock_g: float,
        movement_type: str = "AJUSTE",  # 'AJUSTE' | 'MERMA'
        notes: Optional[str] = None
    ) -> None:
        """Adjust stock manually or record wastage (merma)."""
        if new_stock_g < 0:
            raise ValueError("El nuevo stock no puede ser negativo.")

        cursor = conn.cursor()
        cursor.execute("SELECT stock_g FROM ingredients WHERE id = ?", (ingredient_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Ingrediente ID {ingredient_id} no encontrado.")

        prev_stock = float(row["stock_g"])
        diff = new_stock_g - prev_stock

        cursor.execute("UPDATE ingredients SET stock_g = ? WHERE id = ?", (new_stock_g, ingredient_id))

        cursor.execute(
            """
            INSERT INTO inventory_movements (
                ingredient_id, movement_type, quantity, previous_stock, new_stock, notes
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ingredient_id, movement_type, abs(diff), prev_stock, new_stock_g, notes or f"Ajuste manual de inventario")
        )
        conn.commit()

    @staticmethod
    def get_recipe_for_product(conn: sqlite3.Connection, product_id: int) -> List[RecipeItem]:
        """Fetch all ingredients associated with a product."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT pr.id, pr.product_id, pr.ingredient_id, pr.quantity_g,
                   i.name as ingredient_name, i.cost_per_g, i.stock_g
            FROM product_recipes pr
            JOIN ingredients i ON pr.ingredient_id = i.id
            WHERE pr.product_id = ?
            ORDER BY i.name ASC
            """,
            (product_id,)
        )
        rows = cursor.fetchall()
        return [
            RecipeItem(
                id=r["id"],
                product_id=r["product_id"],
                ingredient_id=r["ingredient_id"],
                ingredient_name=r["ingredient_name"],
                quantity_g=float(r["quantity_g"]),
                cost_per_g=float(r["cost_per_g"]),
                current_ingredient_stock_g=float(r["stock_g"])
            )
            for r in rows
        ]

    @staticmethod
    def save_recipe(
        conn: sqlite3.Connection,
        product_id: int,
        ingredients_data: List[Tuple[int, float]]  # List of (ingredient_id, quantity_g)
    ) -> None:
        """Replace product recipe with new ingredients and quantities in grams."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM product_recipes WHERE product_id = ?", (product_id,))

        for ing_id, qty_g in ingredients_data:
            if qty_g > 0:
                cursor.execute(
                    """
                    INSERT INTO product_recipes (product_id, ingredient_id, quantity_g)
                    VALUES (?, ?, ?)
                    """,
                    (product_id, ing_id, float(qty_g))
                )

        # Update product calculated cost based on recipe
        cursor.execute(
            """
            SELECT SUM(pr.quantity_g * i.cost_per_g) as total_cost
            FROM product_recipes pr
            JOIN ingredients i ON pr.ingredient_id = i.id
            WHERE pr.product_id = ?
            """,
            (product_id,)
        )
        cost_row = cursor.fetchone()
        calc_cost = float(cost_row["total_cost"]) if (cost_row and cost_row["total_cost"]) else 0.0

        if calc_cost > 0:
            cursor.execute("UPDATE products SET cost = ? WHERE id = ?", (round(calc_cost, 2), product_id))

        conn.commit()

    @staticmethod
    def calculate_portions_available(conn: sqlite3.Connection, product_id: int) -> int:
        """Calculate maximum product preparations possible based on limiting ingredient.
        If product has no recipe, returns its direct stock.
        """
        recipe = IngredientModel.get_recipe_for_product(conn, product_id)
        if not recipe:
            cursor = conn.cursor()
            cursor.execute("SELECT stock FROM products WHERE id = ?", (product_id,))
            r = cursor.fetchone()
            return int(r["stock"]) if r else 0

        min_portions = 999999
        for item in recipe:
            portions = item.possible_portions
            if portions < min_portions:
                min_portions = portions

        return max(0, min_portions)

    @staticmethod
    def delete(conn: sqlite3.Connection, ingredient_id: int) -> None:
        """Deactivate or delete an ingredient.
        Blocks deletion if used in active recipes.
        """
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.name FROM product_recipes pr
            JOIN products p ON pr.product_id = p.id
            WHERE pr.ingredient_id = ?
            """,
            (ingredient_id,)
        )
        used_in = [r["name"] for r in cursor.fetchall()]
        if used_in:
            raise ValueError(
                f"No se puede eliminar el ingrediente porque está presente en la receta de: {', '.join(used_in[:3])}"
            )

        cursor.execute("UPDATE ingredients SET is_active = 0 WHERE id = ?", (ingredient_id,))
        conn.commit()

    @staticmethod
    def get_limiting_ingredient_details(
        conn: sqlite3.Connection, product_id: int
    ) -> Optional[Tuple[str, float, float, int]]:
        """Returns (ingredient_name, current_stock_g, quantity_required_g, portions_possible)
        for the ingredient that limits product production.
        """
        recipe = IngredientModel.get_recipe_for_product(conn, product_id)
        if not recipe:
            return None

        limiting_item: Optional[RecipeItem] = None
        min_portions = 999999

        for item in recipe:
            portions = item.possible_portions
            if portions < min_portions:
                min_portions = portions
                limiting_item = item

        if limiting_item:
            return (
                limiting_item.ingredient_name,
                limiting_item.current_ingredient_stock_g,
                limiting_item.quantity_g,
                max(0, min_portions)
            )
        return None

    @staticmethod
    def get_movements(
        conn: sqlite3.Connection,
        ingredient_id: Optional[int] = None,
        limit: int = 100
    ) -> List[InventoryMovement]:
        """Fetch recent inventory movements."""
        cursor = conn.cursor()
        query = """
            SELECT m.*, i.name as ingredient_name, p.name as product_name
            FROM inventory_movements m
            LEFT JOIN ingredients i ON m.ingredient_id = i.id
            LEFT JOIN products p ON m.product_id = p.id
        """
        params = []
        if ingredient_id:
            query += " WHERE m.ingredient_id = ?"
            params.append(ingredient_id)
        query += " ORDER BY m.created_at DESC, m.id DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [
            InventoryMovement(
                id=r["id"],
                ingredient_id=r["ingredient_id"],
                product_id=r["product_id"],
                movement_type=r["movement_type"],
                quantity=float(r["quantity"]),
                previous_stock=float(r["previous_stock"]),
                new_stock=float(r["new_stock"]),
                reference_id=r["reference_id"],
                notes=r["notes"],
                created_at=r["created_at"],
                item_name=r["ingredient_name"] or r["product_name"] or "Item"
            )
            for r in rows
        ]
