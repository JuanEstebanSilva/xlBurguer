"""Database migration script for Carnicería San Diego.
Consolidates beef categories into 'Cortes de Res', removes obsolete Cocción Lenta / Delantero / Trasero duplicates,
and adds 'Cortes de Cerdo' and 'Pollo y Aves' with stock for Pechuga, Carne Molida, and Chuleta.
"""

import sqlite3
import os

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sandiego.db"))

def migrate():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("PRAGMA foreign_keys = ON;")

    # 1. Ensure 'Cortes de Res' exists
    cur.execute("SELECT id FROM categories WHERE name = 'Cortes de Res'")
    row = cur.fetchone()
    if row:
        res_cat_id = row["id"]
    else:
        # Check if 'Cortes de Res (Delantero)' exists to rename it
        cur.execute("SELECT id FROM categories WHERE name = 'Cortes de Res (Delantero)'")
        del_row = cur.fetchone()
        if del_row:
            res_cat_id = del_row["id"]
            cur.execute("UPDATE categories SET name = 'Cortes de Res' WHERE id = ?", (res_cat_id,))
        else:
            cur.execute("INSERT INTO categories (name) VALUES ('Cortes de Res')")
            res_cat_id = cur.lastrowid

    # 2. Get old categories to merge: 'Cortes de Res (Trasero)', 'Cortes para Cocción Lenta'
    cur.execute("SELECT id, name FROM categories WHERE name IN ('Cortes de Res (Trasero)', 'Cortes para Cocción Lenta')")
    old_cats = cur.fetchall()
    old_cat_ids = [r["id"] for r in old_cats]

    if old_cat_ids:
        # Move all products in old categories to res_cat_id
        placeholders = ",".join("?" * len(old_cat_ids))
        cur.execute(f"UPDATE products SET category_id = ? WHERE category_id IN ({placeholders})", [res_cat_id] + old_cat_ids)

        # Remove duplicate products with 0 sales from former Cocción Lenta
        cur.execute("""
            DELETE FROM products 
            WHERE id IN (44, 46, 47, 48, 49, 50, 51)
              AND id NOT IN (SELECT product_id FROM sale_items)
              AND id NOT IN (SELECT product_id FROM company_product_quotas)
        """)

        # Delete the obsolete categories
        cur.execute(f"DELETE FROM categories WHERE id IN ({placeholders})", old_cat_ids)

    # 3. Rename "Sobrebarriga Gruesa" to "Sobrebarriga" if present
    cur.execute("UPDATE products SET name = 'Sobrebarriga' WHERE name = 'Sobrebarriga Gruesa'")
    cur.execute("UPDATE products SET name = 'Falda' WHERE name = 'Falda de Res'")

    # 4. Ensure 'Cortes de Cerdo' exists
    cur.execute("SELECT id FROM categories WHERE name = 'Cortes de Cerdo'")
    cerdo_row = cur.fetchone()
    if not cerdo_row:
        cur.execute("INSERT INTO categories (name) VALUES ('Cortes de Cerdo')")
        cerdo_cat_id = cur.lastrowid
    else:
        cerdo_cat_id = cerdo_row["id"]

    # 5. Ensure 'Pollo y Aves' exists
    cur.execute("SELECT id FROM categories WHERE name = 'Pollo y Aves'")
    pollo_row = cur.fetchone()
    if not pollo_row:
        cur.execute("INSERT INTO categories (name) VALUES ('Pollo y Aves')")
        pollo_cat_id = cur.lastrowid
    else:
        pollo_cat_id = pollo_row["id"]

    # 6. Insert Carne Molida if missing
    cur.execute("SELECT id FROM products WHERE lower(name) = 'carne molida' OR lower(name) = 'carne molida de res'")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO products (barcode, name, category_id, sale_type, price_base, cost, iva, unit_measure, stock, min_stock)
            VALUES ('7701015', 'Carne Molida', ?, 'PESO', 22.0, 15.0, 0.0, 'kg', 25000.0, 5000.0)
        """, (res_cat_id,))

    # 7. Insert Chuleta and Cerdo cuts if missing
    cur.execute("SELECT id FROM products WHERE lower(name) LIKE '%chuleta%'")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO products (barcode, name, category_id, sale_type, price_base, cost, iva, unit_measure, stock, min_stock)
            VALUES ('7708001', 'Chuleta de Cerdo', ?, 'PESO', 24.0, 16.0, 0.0, 'kg', 20000.0, 4000.0)
        """, (cerdo_cat_id,))
    cur.execute("SELECT id FROM products WHERE lower(name) LIKE '%costilla de cerdo%'")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO products (barcode, name, category_id, sale_type, price_base, cost, iva, unit_measure, stock, min_stock)
            VALUES ('7708002', 'Costilla de Cerdo', ?, 'PESO', 26.0, 18.0, 0.0, 'kg', 18000.0, 3500.0)
        """, (cerdo_cat_id,))
    cur.execute("SELECT id FROM products WHERE lower(name) LIKE '%lomo de cerdo%'")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO products (barcode, name, category_id, sale_type, price_base, cost, iva, unit_measure, stock, min_stock)
            VALUES ('7708003', 'Lomo de Cerdo', ?, 'PESO', 25.0, 17.0, 0.0, 'kg', 15000.0, 3000.0)
        """, (cerdo_cat_id,))

    # 8. Insert Pechuga and Pollo cuts if missing
    cur.execute("SELECT id FROM products WHERE lower(name) LIKE '%pechuga%'")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO products (barcode, name, category_id, sale_type, price_base, cost, iva, unit_measure, stock, min_stock)
            VALUES ('7709001', 'Pechuga Campesina', ?, 'PESO', 18.0, 12.0, 0.0, 'kg', 25000.0, 5000.0)
        """, (pollo_cat_id,))
    cur.execute("SELECT id FROM products WHERE lower(name) LIKE '%alas campesinas%'")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO products (barcode, name, category_id, sale_type, price_base, cost, iva, unit_measure, stock, min_stock)
            VALUES ('7709002', 'Alas Campesinas', ?, 'PESO', 14.0, 9.5, 0.0, 'kg', 18000.0, 4000.0)
        """, (pollo_cat_id,))

    conn.commit()
    print("Migration completed successfully.")
    
    # Print summary
    cur.execute("SELECT id, name FROM categories")
    print("Categories:", cur.fetchall())
    cur.execute("SELECT count(*) FROM products")
    print("Total products:", cur.fetchone()[0])
    conn.close()

if __name__ == "__main__":
    migrate()
