"""Seed database with initial categories, default fast-food catalog, ingredients in grams,
and base recipes for XL Burguer.
Guarantees clean baseline initialization without demo carnicería data or dummy customers.
"""

import logging
import sqlite3
from models.user import hash_password

CATEGORIES = [
    "HAMBURGUESAS",
    "PERROS CALIENTES",
    "COMBOS",
    "SALCHIPAPAS",
    "ACOMPAÑAMIENTOS",
    "BEBIDAS",
    "ADICIONALES"
]

# Baseline ingredients stored in grams (g)
# (name, description, stock_g, min_stock_g, cost_per_g)
INITIAL_INGREDIENTS = [
    ("Carne de Hamburguesa (125g)", "Carne de res seleccionada para hamburguesa (porción estándar 125g)", 10000.0, 2500.0, 24.0),
    ("Pan de Hamburguesa", "Pan artesanal con ajonjolí (80g aprox)", 8000.0, 2000.0, 12.5),
    ("Queso Cheddar", "Queso cheddar fundente tajado", 4000.0, 1000.0, 35.0),
    ("Tocineta Ahumada", "Tocineta ahumada premium", 3000.0, 800.0, 45.0),
    ("Lechuga Crespa", "Lechuga crespa fresca hidropónica", 2500.0, 600.0, 10.0),
    ("Tomate Fresco", "Tomate chonto seleccionado", 3500.0, 800.0, 8.0),
    ("Cebolla Caramelizada", "Cebolla sofrita caramelizada de la casa", 3000.0, 600.0, 9.0),
    ("Pan Perro Caliente", "Pan suave para perro americano (70g)", 5000.0, 1400.0, 12.0),
    ("Salchicha Americana", "Salchicha premium jumbo", 6000.0, 1800.0, 22.0),
    ("Papas Ripio", "Papas ripio crocantes para perro", 2000.0, 500.0, 15.0),
    ("Papa Francesa Congelada", "Papas a la francesa corte fino", 12000.0, 3000.0, 14.0),
    ("Salsas Especiales XL", "Mezcla de salsas gourmet XL Burguer", 6000.0, 1500.0, 10.0),
    ("Costilla BBQ Desmechada", "Costilla de cerdo ahumada desmechada", 4000.0, 1000.0, 38.0),
]

# Commercial fast food products for XL Burguer
# (barcode, name, category, price_base, cost, iva, unit_measure, stock, min_stock)
INITIAL_PRODUCTS = [
    ("101", "Hamburguesa Clásica XL", "HAMBURGUESAS", 18000.0, 6500.0, 0.0, "und", 0.0, 0.0),
    ("102", "Hamburguesa Doble Carne XL", "HAMBURGUESAS", 26000.0, 10800.0, 0.0, "und", 0.0, 0.0),
    ("103", "Hamburguesa BBQ Bacon XL", "HAMBURGUESAS", 23000.0, 8500.0, 0.0, "und", 0.0, 0.0),
    ("104", "Hamburguesa Monster XL", "HAMBURGUESAS", 30000.0, 13200.0, 0.0, "und", 0.0, 0.0),
    ("201", "Perro Caliente Tradicional XL", "PERROS CALIENTES", 14000.0, 5200.0, 0.0, "und", 0.0, 0.0),
    ("202", "Perro Especial con Tocineta", "PERROS CALIENTES", 18000.0, 6800.0, 0.0, "und", 0.0, 0.0),
    ("301", "Combo Clásico XL", "COMBOS", 25000.0, 9500.0, 0.0, "und", 0.0, 0.0),
    ("401", "Salchipapa Tradicional XL", "SALCHIPAPAS", 16000.0, 6100.0, 0.0, "und", 0.0, 0.0),
    ("402", "Salchipapa Especial Mixta", "SALCHIPAPAS", 22000.0, 9400.0, 0.0, "und", 0.0, 0.0),
    ("501", "Porción Papas a la Francesa", "ACOMPAÑAMIENTOS", 7000.0, 3100.0, 0.0, "und", 0.0, 0.0),
    ("601", "Coca-Cola 400ml", "BEBIDAS", 5000.0, 2800.0, 0.0, "und", 50.0, 10.0),
    ("602", "Postobón Manzana 400ml", "BEBIDAS", 4500.0, 2400.0, 0.0, "und", 40.0, 10.0),
    ("603", "Agua Mineral Cristal 500ml", "BEBIDAS", 3500.0, 1500.0, 0.0, "und", 30.0, 10.0),
    ("701", "Adicional Carne 125g", "ADICIONALES", 6000.0, 3000.0, 0.0, "und", 0.0, 0.0),
    ("702", "Adicional Tocineta 30g", "ADICIONALES", 3500.0, 1350.0, 0.0, "und", 0.0, 0.0),
    ("703", "Adicional Queso Cheddar 25g", "ADICIONALES", 2500.0, 875.0, 0.0, "und", 0.0, 0.0),
]

# Baseline recipes: product_name -> list of (ingredient_name, grams)
INITIAL_RECIPES = {
    "Hamburguesa Clásica XL": [
        ("Pan de Hamburguesa", 80.0),
        ("Carne de Hamburguesa (125g)", 125.0),
        ("Queso Cheddar", 25.0),
        ("Lechuga Crespa", 20.0),
        ("Tomate Fresco", 30.0),
        ("Cebolla Caramelizada", 25.0),
        ("Salsas Especiales XL", 30.0),
    ],
    "Hamburguesa Doble Carne XL": [
        ("Pan de Hamburguesa", 80.0),
        ("Carne de Hamburguesa (125g)", 250.0),
        ("Queso Cheddar", 50.0),
        ("Tocineta Ahumada", 30.0),
        ("Lechuga Crespa", 20.0),
        ("Tomate Fresco", 30.0),
        ("Cebolla Caramelizada", 25.0),
        ("Salsas Especiales XL", 30.0),
    ],
    "Hamburguesa BBQ Bacon XL": [
        ("Pan de Hamburguesa", 80.0),
        ("Carne de Hamburguesa (125g)", 125.0),
        ("Queso Cheddar", 25.0),
        ("Tocineta Ahumada", 45.0),
        ("Cebolla Caramelizada", 30.0),
        ("Salsas Especiales XL", 35.0),
    ],
    "Hamburguesa Monster XL": [
        ("Pan de Hamburguesa", 80.0),
        ("Carne de Hamburguesa (125g)", 250.0),
        ("Costilla BBQ Desmechada", 100.0),
        ("Queso Cheddar", 50.0),
        ("Tocineta Ahumada", 30.0),
        ("Salsas Especiales XL", 40.0),
    ],
    "Perro Caliente Tradicional XL": [
        ("Pan Perro Caliente", 70.0),
        ("Salchicha Americana", 90.0),
        ("Queso Cheddar", 25.0),
        ("Papas Ripio", 20.0),
        ("Salsas Especiales XL", 30.0),
    ],
    "Perro Especial con Tocineta": [
        ("Pan Perro Caliente", 70.0),
        ("Salchicha Americana", 90.0),
        ("Queso Cheddar", 30.0),
        ("Tocineta Ahumada", 30.0),
        ("Papas Ripio", 20.0),
        ("Salsas Especiales XL", 30.0),
    ],
    "Combo Clásico XL": [
        ("Pan de Hamburguesa", 80.0),
        ("Carne de Hamburguesa (125g)", 125.0),
        ("Queso Cheddar", 25.0),
        ("Lechuga Crespa", 20.0),
        ("Tomate Fresco", 30.0),
        ("Papa Francesa Congelada", 150.0),
        ("Salsas Especiales XL", 40.0),
    ],
    "Salchipapa Tradicional XL": [
        ("Papa Francesa Congelada", 200.0),
        ("Salchicha Americana", 90.0),
        ("Queso Cheddar", 30.0),
        ("Salsas Especiales XL", 30.0),
    ],
    "Salchipapa Especial Mixta": [
        ("Papa Francesa Congelada", 250.0),
        ("Salchicha Americana", 90.0),
        ("Costilla BBQ Desmechada", 80.0),
        ("Queso Cheddar", 40.0),
        ("Tocineta Ahumada", 30.0),
        ("Salsas Especiales XL", 40.0),
    ],
    "Porción Papas a la Francesa": [
        ("Papa Francesa Congelada", 200.0),
        ("Salsas Especiales XL", 30.0),
    ],
    "Adicional Carne 125g": [
        ("Carne de Hamburguesa (125g)", 125.0),
    ],
    "Adicional Tocineta 30g": [
        ("Tocineta Ahumada", 30.0),
    ],
    "Adicional Queso Cheddar 25g": [
        ("Queso Cheddar", 25.0),
    ],
}


def seed_database(conn: sqlite3.Connection) -> None:
    """Seed baseline categories, ingredients, products, recipes and admin user for XL Burguer.
    Does not duplicate existing data.
    """
    cursor = conn.cursor()

    # 1. Categories
    for cat_name in CATEGORIES:
        cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat_name,))

    cursor.execute("SELECT id, name FROM categories")
    cat_map = {row["name"]: row["id"] for row in cursor.fetchall()}

    # 2. Ingredients (in grams)
    cursor.execute("SELECT COUNT(*) as count FROM ingredients")
    if cursor.fetchone()["count"] == 0:
        logging.info("Inicializando inventario base de ingredientes en gramos...")
        for name, desc, stock_g, min_stock_g, cost_per_g in INITIAL_INGREDIENTS:
            cursor.execute(
                """
                INSERT INTO ingredients (name, description, stock_g, min_stock_g, cost_per_g, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (name, desc, stock_g, min_stock_g, cost_per_g)
            )
            ing_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO inventory_movements (
                    ingredient_id, movement_type, quantity, previous_stock, new_stock, notes
                ) VALUES (?, 'INICIAL', ?, 0, ?, 'Inventario inicial de apertura')
                """,
                (ing_id, stock_g, stock_g)
            )

    cursor.execute("SELECT id, name FROM ingredients")
    ing_map = {row["name"]: row["id"] for row in cursor.fetchall()}

    # 3. Admin User
    cursor.execute("SELECT id FROM users WHERE UPPER(role) = 'ADMIN' LIMIT 1")
    if not cursor.fetchone():
        admin_hash = hash_password("admin123")
        cursor.execute(
            """
            INSERT INTO users (username, password_hash, full_name, role)
            VALUES (?, ?, ?, 'ADMIN')
            """,
            ("admin", admin_hash, "Administrador XL Burguer")
        )
        logging.info("Creado usuario administrador inicial (admin).")

    # 4. Products
    cursor.execute("SELECT COUNT(*) as count FROM products")
    if cursor.fetchone()["count"] == 0:
        logging.info("Inicializando catálogo base de productos XL Burguer...")
        for barcode, name, cat_name, price_base, cost, iva, unit_measure, stock, min_stock in INITIAL_PRODUCTS:
            cat_id = cat_map.get(cat_name)
            if cat_id:
                cursor.execute(
                    """
                    INSERT INTO products (barcode, name, category_id, sale_type, price_base, cost, iva, unit_measure, stock, min_stock, is_active)
                    VALUES (?, ?, ?, 'UNIDAD', ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (barcode, name, cat_id, price_base, cost, iva, unit_measure, stock, min_stock)
                )

    cursor.execute("SELECT id, name FROM products")
    prod_map = {row["name"]: row["id"] for row in cursor.fetchall()}

    # 5. Recipes
    cursor.execute("SELECT COUNT(*) as count FROM product_recipes")
    if cursor.fetchone()["count"] == 0:
        logging.info("Vinculando recetas estándar a los productos...")
        for prod_name, recipe_items in INITIAL_RECIPES.items():
            p_id = prod_map.get(prod_name)
            if not p_id:
                continue
            for ing_name, qty_g in recipe_items:
                i_id = ing_map.get(ing_name)
                if i_id:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO product_recipes (product_id, ingredient_id, quantity_g)
                        VALUES (?, ?, ?)
                        """,
                        (p_id, i_id, qty_g)
                    )

            # Recalculate cost based on recipe ingredients
            cursor.execute(
                """
                SELECT SUM(pr.quantity_g * i.cost_per_g) as total_cost
                FROM product_recipes pr
                JOIN ingredients i ON pr.ingredient_id = i.id
                WHERE pr.product_id = ?
                """,
                (p_id,)
            )
            cost_row = cursor.fetchone()
            if cost_row and cost_row["total_cost"]:
                cursor.execute(
                    "UPDATE products SET cost = ? WHERE id = ?",
                    (round(float(cost_row["total_cost"]), 2), p_id)
                )

    # 6. Default Customers (Persona & Empresa)
    cursor.execute("SELECT COUNT(*) as count FROM customers WHERE customer_type = 'PERSONA'")
    if cursor.fetchone()["count"] == 0:
        cursor.execute(
            """
            INSERT INTO customers (first_name, last_name, document_id, phone, customer_type, discount_percent)
            VALUES ('Cliente', 'General (Mostrador)', '222222222', '0000000000', 'PERSONA', 0.0)
            """
        )

    cursor.execute("SELECT COUNT(*) as count FROM customers WHERE customer_type = 'EMPRESA'")
    if cursor.fetchone()["count"] == 0:
        cursor.execute(
            """
            INSERT INTO customers (first_name, last_name, document_id, phone, customer_type, discount_percent)
            VALUES ('Empresa Corporativa', 'Convenio XL', '901555666-1', '3105556677', 'EMPRESA', 10.0)
            """
        )

    conn.commit()
    logging.info("Inicialización y sembrado de XL Burguer completado exitosamente.")
