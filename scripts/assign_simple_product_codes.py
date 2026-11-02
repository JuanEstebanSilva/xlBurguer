"""Assign sequential, clean, simple product codes (1, 2, 3... N) to products.
Carnicería San Diego POS.
"""

import os
import sqlite3

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

CAT_ORDER = {
    'Cortes de Res': 1,
    'Cortes de Cerdo': 2,
    'Pollo y Aves': 3,
    'Cortes Madurados & Parrilla': 4,
    'Vísceras y Menudencias': 5,
    'Quesos Artesanales': 6,
    'Vinos de Villa de Leyva': 7
}

def update_db(db_path: str):
    if not os.path.exists(db_path):
        print(f"Skipping non-existent db: {db_path}")
        return

    print(f"\nUpdating product codes in: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    rows = cursor.execute("""
        SELECT p.id, p.barcode, p.name, c.name as cat_name 
        FROM products p 
        JOIN categories c ON p.category_id = c.id
    """).fetchall()

    sorted_rows = sorted(rows, key=lambda r: (CAT_ORDER.get(r['cat_name'], 99), r['id']))

    # To avoid UNIQUE constraint collisions while renumbering,
    # first assign temporary negative strings, then final 1..N
    for i, r in enumerate(sorted_rows, 1):
        cursor.execute("UPDATE products SET barcode = ? WHERE id = ?", (f"TMP_{i}", r['id']))
    conn.commit()

    # Now assign clean consecutive string integers '1', '2', ...
    for i, r in enumerate(sorted_rows, 1):
        code_str = str(i)
        cursor.execute("UPDATE products SET barcode = ? WHERE id = ?", (code_str, r['id']))
    conn.commit()

    # Verify
    assigned = cursor.execute("SELECT id, barcode, name FROM products ORDER BY CAST(barcode AS INTEGER)").fetchall()
    for row in assigned:
        print(f"  [Code {row['barcode']:>2}] -> (ID {row['id']:>3}) {row['name']}")

    conn.close()
    print(f"Successfully updated {len(assigned)} products in {db_path}!")

def main():
    root_db = os.path.join(_PROJECT_ROOT, "sandiego.db")
    dist_db = os.path.join(_PROJECT_ROOT, "dist", "CarniceriaSanDiego", "sandiego.db")
    update_db(root_db)
    if os.path.exists(dist_db):
        update_db(dist_db)

if __name__ == "__main__":
    main()
