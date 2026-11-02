"""Seed database with initial categories, default catalog, and essential baseline records.
Guarantees clean baseline initialization without re-injecting mock customers or dummy cashiers on production boot.
Demo/mock customer records are strictly isolated into `seed_demo_data()` and only run with `--demo`.
"""

import logging
import sqlite3
import sys
from models.user import hash_password

CATEGORIES = [
    "CORTES FINOS",
    "CERDO",
    "POLLO",
    "EMBUTIDOS Y PROCESADOS",
    "VÍVERES Y LÁCTEOS"
]

# Standard baseline butcher products for San Diego
INITIAL_PRODUCTS = [
    # (barcode, name, category, sale_type, price_base, cost, iva, unit_measure, stock, min_stock)
    # Price base: $/g for PESO, $/und for UNIDAD
    ("1", "Lomo Fino", "CORTES FINOS", "PESO", 57.0, 42.0, 0.0, "kg", 15000.0, 5000.0),
    ("2", "Punta de Anca", "CORTES FINOS", "PESO", 48.0, 36.0, 0.0, "kg", 20000.0, 6000.0),
    ("3", "Baby Beef", "CORTES FINOS", "PESO", 46.0, 34.0, 0.0, "kg", 12000.0, 4000.0),
    ("4", "Bife de Chorizo", "CORTES FINOS", "PESO", 46.0, 34.0, 0.0, "kg", 14000.0, 4000.0),
    ("5", "Churrasco", "CORTES FINOS", "PESO", 44.0, 32.0, 0.0, "kg", 18000.0, 5000.0),
    ("6", "Tomahawk", "CORTES FINOS", "PESO", 58.0, 44.0, 0.0, "kg", 8000.0, 3000.0),
    ("7", "Rib Eye", "CORTES FINOS", "PESO", 52.0, 39.0, 0.0, "kg", 10000.0, 3000.0),
    ("8", "T-Bone Steak", "CORTES FINOS", "PESO", 50.0, 37.0, 0.0, "kg", 9000.0, 3000.0),
    ("9", "Costilla de Res", "CORTES FINOS", "PESO", 28.0, 20.0, 0.0, "kg", 25000.0, 8000.0),
    ("10", "Sobrebarriga Gruesa", "CORTES FINOS", "PESO", 34.0, 25.0, 0.0, "kg", 16000.0, 5000.0),
    ("11", "Muchacho", "CORTES FINOS", "PESO", 36.0, 26.0, 0.0, "kg", 15000.0, 5000.0),
    ("12", "Carne Molida Especial", "CORTES FINOS", "PESO", 26.0, 19.0, 0.0, "kg", 30000.0, 10000.0),
    ("13", "Costilla de Cerdo BBQ", "CERDO", "PESO", 32.0, 23.0, 0.0, "kg", 20000.0, 6000.0),
    ("14", "Lomo de Cerdo", "CERDO", "PESO", 28.0, 20.0, 0.0, "kg", 18000.0, 5000.0),
    ("15", "Bondiola de Cerdo", "CERDO", "PESO", 30.0, 22.0, 0.0, "kg", 15000.0, 4000.0),
    ("16", "Tocino Barriguero", "CERDO", "PESO", 24.0, 17.0, 0.0, "kg", 22000.0, 7000.0),
    ("17", "Chuleta de Cerdo", "CERDO", "PESO", 26.0, 19.0, 0.0, "kg", 16000.0, 5000.0),
    ("18", "Pernil de Cerdo Ahumado", "CERDO", "PESO", 34.0, 25.0, 0.0, "kg", 12000.0, 4000.0),
    ("19", "Pollo Campesino Entero", "POLLO", "PESO", 16.0, 11.5, 0.0, "kg", 25000.0, 8000.0),
    ("20", "Pechuga de Pollo Deshuesada", "POLLO", "PESO", 24.0, 17.5, 0.0, "kg", 30000.0, 10000.0),
    ("21", "Muslos y Contramuslos", "POLLO", "PESO", 15.0, 10.5, 0.0, "kg", 22000.0, 7000.0),
    ("22", "Alitas de Pollo", "POLLO", "PESO", 18.0, 13.0, 0.0, "kg", 18000.0, 5000.0),
    ("23", "Chorizo Artesanal Boyacense", "EMBUTIDOS Y PROCESADOS", "PESO", 32.0, 22.0, 0.0, "kg", 15000.0, 5000.0),
    ("24", "Longaniza de Sutamarchán", "EMBUTIDOS Y PROCESADOS", "PESO", 36.0, 25.0, 0.0, "kg", 20000.0, 6000.0),
    ("25", "Morcilla Tradicional", "EMBUTIDOS Y PROCESADOS", "PESO", 22.0, 15.0, 0.0, "kg", 14000.0, 4000.0),
    ("26", "Salchicha Suiza Artesanal", "EMBUTIDOS Y PROCESADOS", "PESO", 30.0, 21.0, 0.0, "kg", 10000.0, 3000.0),
    ("27", "Jamón Ahumado de Pierna", "EMBUTIDOS Y PROCESADOS", "PESO", 38.0, 27.0, 0.0, "kg", 12000.0, 4000.0),
    ("28", "Queso Paipa Tradicional", "VÍVERES Y LÁCTEOS", "PESO", 42.0, 30.0, 0.0, "kg", 15000.0, 5000.0),
    ("29", "Queso Paipa Maduro Artesanal", "VÍVERES Y LÁCTEOS", "PESO", 48.0, 34.0, 0.0, "kg", 10000.0, 3000.0),
    ("30", "Queso Campesino Fresco", "VÍVERES Y LÁCTEOS", "PESO", 22.0, 15.0, 0.0, "kg", 20000.0, 6000.0),
    ("31", "Huevos Criollos AA (Panal x30)", "VÍVERES Y LÁCTEOS", "UNIDAD", 22000.0, 16000.0, 0.0, "und", 20.0, 5.0),
    ("32", "Carbón Vegetal Bulto 5kg", "VÍVERES Y LÁCTEOS", "UNIDAD", 18000.0, 12000.0, 0.0, "und", 30.0, 10.0),
    ("33", "Sal Marina para Asados 500g", "VÍVERES Y LÁCTEOS", "UNIDAD", 8000.0, 5000.0, 0.0, "und", 40.0, 10.0),
    ("34", "Salsa BBQ Ahumada Artesanal 300g", "VÍVERES Y LÁCTEOS", "UNIDAD", 14000.0, 9000.0, 0.0, "und", 25.0, 8.0),
    ("35", "Chimichurri Casero 250ml", "VÍVERES Y LÁCTEOS", "UNIDAD", 12000.0, 7500.0, 0.0, "und", 30.0, 8.0),
    ("36", "Vino Tinto Gran Reserva 750ml", "VÍVERES Y LÁCTEOS", "UNIDAD", 68000.0, 45000.0, 19.0, "und", 15.0, 4.0),
    ("37", "Vino Blanco Sauvignon 750ml", "VÍVERES Y LÁCTEOS", "UNIDAD", 58000.0, 38000.0, 19.0, "und", 12.0, 4.0),
    ("38", "Vino Tinto Cabernet 375ml", "VÍVERES Y LÁCTEOS", "UNIDAD", 38000.0, 24000.0, 19.0, "und", 18.0, 5.0),
]


def seed_database(conn: sqlite3.Connection) -> None:
    """Seed baseline categories, products, admin and generic customer if database is empty.
    Never re-creates deleted cashiers, never injects mock customers, and never overwrites real data.
    """
    cursor = conn.cursor()

    # 1. Seed Categories if empty
    for cat_name in CATEGORIES:
        cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat_name,))

    cursor.execute("SELECT id, name FROM categories")
    cat_map = {row["name"]: row["id"] for row in cursor.fetchall()}

    # 2. Seed Admin User ONLY if no administrator exists in the entire database
    cursor.execute("SELECT id FROM users WHERE UPPER(role) = 'ADMIN' LIMIT 1")
    if not cursor.fetchone():
        admin_hash = hash_password("admin123")
        cursor.execute(
            """
            INSERT INTO users (username, password_hash, full_name, role)
            VALUES (?, ?, ?, 'ADMIN')
            """,
            ("admin", admin_hash, "Administrador")
        )
        logging.info("Creado usuario administrador inicial (admin).")

    # 3. Seed Baseline Products ONLY if products table is completely empty
    cursor.execute("SELECT COUNT(*) as count FROM products")
    if cursor.fetchone()["count"] == 0:
        logging.info("Inicializando catálogo base de productos...")
        for barcode, name, cat_name, sale_type, price_base, cost, iva, unit_measure, stock, min_stock in INITIAL_PRODUCTS:
            cat_id = cat_map.get(cat_name)
            if cat_id:
                ean_barcode = f"7701234{int(barcode):06d}" if (barcode and barcode.isdigit() and len(barcode) < 6) else barcode
                cursor.execute(
                    """
                    INSERT INTO products (barcode, name, category_id, sale_type, price_base, cost, iva, unit_measure, stock, min_stock)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (ean_barcode, name, cat_id, sale_type, price_base, cost, iva, unit_measure, stock, min_stock)
                )

    # 4. Seed Standard Generic Customer ONLY if customers table is completely empty
    cursor.execute("SELECT COUNT(*) as count FROM customers")
    if cursor.fetchone()["count"] == 0:
        cursor.execute(
            """
            INSERT INTO customers (id, document_id, first_name, last_name, phone, customer_type)
            VALUES (1, '222222222222', 'Consumidor', 'Final', '3000000000', 'PERSONA')
            """
        )
        logging.info("Creado cliente estándar Consumidor Final.")

    conn.commit()


def seed_demo_data(conn: sqlite3.Connection) -> None:
    """Explicitly seed demo customers and enterprise quotas for testing or demonstrations.
    This function is NEVER executed automatically during production boot.
    """
    cursor = conn.cursor()
    logging.info("Sembrando datos de demostración (clientes y convenios empresariales)...")

    demo_customers = [
        ("1049628190", "Carlos", "Gómez", "3101234567"),
        ("1052489211", "María Elena", "Rodríguez", "3124567890"),
        ("1053782910", "Juan David", "Pérez", "3157891234"),
        ("1048992100", "Andrea Carolina", "Moreno", "3209876543"),
        ("1056781290", "Pedro Antonio", "Ramírez", "3112345678"),
        ("1057891234", "Claudia Patricia", "Martínez", "3148901234"),
    ]
    for doc, fn, ln, ph in demo_customers:
        cursor.execute(
            """
            INSERT OR IGNORE INTO customers (document_id, first_name, last_name, phone, customer_type)
            VALUES (?, ?, ?, ?, 'PERSONA')
            """,
            (doc, fn, ln, ph)
        )

    demo_companies = [
        ("900876543-1", "El Claustro", "Mauricio Vargas", "3154443322", "EMPRESA", 10.0),
        ("901234567-2", "San Antonio", "Diana Castro", "3187776655", "EMPRESA", 15.0),
        ("900345678-3", "Villa Real", "Hernando Ruiz", "3118889900", "EMPRESA", 10.0),
        ("901987654-4", "Los Portales", "Carlos Méndez", "3125554411", "EMPRESA", 20.0),
    ]
    for doc, fn, ln, ph, ctype, disc in demo_companies:
        cursor.execute(
            """
            INSERT OR IGNORE INTO customers (document_id, first_name, last_name, phone, customer_type, discount_percent)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (doc, fn, ln, ph, ctype, disc)
        )

    conn.commit()
    logging.info("Datos demo sembrados exitosamente.")


if __name__ == "__main__":
    from database.connection import get_db_connection
    with get_db_connection() as c:
        if "--demo" in sys.argv:
            seed_demo_data(c)
        else:
            seed_database(c)
        print("Operación de siembra completada.")
