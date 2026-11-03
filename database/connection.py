"""Database Connection and Lifecycle Manager for XL Burguer.
Handles SQLite3 connection lifecycle, foreign keys, versioned migrations via PRAGMA user_version,
atomic online backups with automatic retention rotation, and centralized AppData path resolution.
"""

from contextlib import contextmanager
from datetime import datetime
import glob
import logging
import os
import sqlite3
import sys
from typing import Generator, Optional
import unicodedata

# Ensure project root is in sys.path
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.seed_data import seed_database


def get_resource_path(relative_path: str) -> str:
    """Return absolute path for static, read-only bundled assets (images, schema.sql).
    Handles both development environment and PyInstaller sys._MEIPASS.
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = _PROJECT_ROOT
    return os.path.normpath(os.path.join(base_path, relative_path))


def get_app_data_dir() -> str:
    """Return standard user data directory for XL Burguer.
    In development: returns _PROJECT_ROOT.
    In frozen mode:
      - If .portable file exists next to sys.executable or XLBURGUER_PORTABLE=1, returns exe folder.
      - Otherwise returns %APPDATA%\\XLBurguer (creates if not existing).
    """
    if not getattr(sys, 'frozen', False):
        return _PROJECT_ROOT

    exe_dir = os.path.dirname(sys.executable)
    portable_marker = os.path.join(exe_dir, ".portable")
    if os.path.exists(portable_marker) or os.environ.get("XLBURGUER_PORTABLE") == "1" or os.environ.get("SANDIEGO_PORTABLE") == "1":
        return exe_dir

    app_data = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    if not app_data:
        app_data = os.path.expanduser("~")

    target_dir = os.path.join(app_data, "XLBurguer")
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception:
        pass
    return target_dir


def get_writable_path(filename: str) -> str:
    """Return absolute path for writable persistent files (database, logs, backups, config).
    Uses user AppData directory when installed, or project root in development.
    If the target file does not exist in AppData, automatically seeds it from
    a bundled copy in the application directory.
    """
    target_dir = get_app_data_dir()
    target_path = os.path.normpath(os.path.join(target_dir, filename))

    # If file doesn't exist yet in target directory, check if a template/bundled version exists next to exe
    if not os.path.exists(target_path) and getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        bundled_copy = os.path.join(exe_dir, filename)
        if os.path.exists(bundled_copy):
            try:
                import shutil
                shutil.copy2(bundled_copy, target_path)
                logging.info("Seeded %s from %s to %s", filename, bundled_copy, target_path)
            except Exception as e:
                logging.warning("Could not seed %s from %s: %s", filename, bundled_copy, e)

    return target_path


def get_database_path() -> str:
    """Return writable path to SQLite database.
    Allows test isolation via XLBURGUER_DB_PATH (or SANDIEGO_DB_PATH fallback) environment variable.
    """
    custom_path = os.environ.get("XLBURGUER_DB_PATH") or os.environ.get("SANDIEGO_DB_PATH")
    if custom_path:
        return os.path.abspath(custom_path)
    return get_writable_path("xlburguer.db")


def backup_database(destination_dir: Optional[str] = None, max_backups: int = 10) -> Optional[str]:
    """Create an atomic timestamped backup copy of the SQLite database.
    Uses sqlite3 online backup API, safe to call while the database is actively used in WAL mode.
    Rotates older backups preserving the last `max_backups` copies.
    """
    db_path = get_database_path()
    if not os.path.exists(db_path):
        return None

    if not destination_dir:
        destination_dir = os.path.join(get_app_data_dir(), "backups")
    os.makedirs(destination_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(destination_dir, f"xlburguer_backup_{timestamp}.db")

    try:
        src_conn = sqlite3.connect(db_path)
        # Verify integrity before backup
        check = src_conn.execute("PRAGMA integrity_check;").fetchone()
        if not check or check[0] != "ok":
            logging.error("Database integrity check failed prior to backup: %s", check)

        dst_conn = sqlite3.connect(backup_file)
        with dst_conn:
            src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()
        logging.info("Backup created successfully at: %s", backup_file)

        # Rotate old backups
        backup_pattern = os.path.join(destination_dir, "xlburguer_backup_*.db")
        existing_backups = sorted(glob.glob(backup_pattern), key=os.path.getmtime, reverse=True)
        if len(existing_backups) > max_backups:
            for old_b in existing_backups[max_backups:]:
                try:
                    os.remove(old_b)
                    logging.info("Rotated old backup: %s", old_b)
                except Exception as ex:
                    logging.warning("Could not delete old backup %s: %s", old_b, ex)

        return backup_file
    except Exception as e:
        logging.error("Failed to create database backup: %s", e)
        return None


def get_schema_path() -> str:
    """Return schema.sql location handling PyInstaller bundled data and fallbacks."""
    bundled = get_resource_path(os.path.join("database", "schema.sql"))
    if os.path.exists(bundled):
        return bundled

    bundled_root = get_resource_path("schema.sql")
    if os.path.exists(bundled_root):
        return bundled_root

    local = os.path.abspath(os.path.join(os.path.dirname(__file__), "schema.sql"))
    if os.path.exists(local):
        return local

    return bundled


def normalize_text(text) -> str:
    """Normalize text: strip accents/diacritics and convert to lower case for insensitive search."""
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFKD', str(text))
    return nfkd.encode('ASCII', 'ignore').decode('ASCII').lower().strip()


def create_connection() -> sqlite3.Connection:
    """Create a new SQLite3 connection configured with foreign keys, WAL mode, Row factory, and NORMALIZE_TEXT."""
    db_path = get_database_path()
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.create_function("NORMALIZE_TEXT", 1, normalize_text)
    return conn


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for obtaining a database connection with auto-closing."""
    conn = create_connection()
    try:
        yield conn
    finally:
        conn.close()


def run_versioned_migrations(conn: sqlite3.Connection) -> None:
    """Execute versioned migrations using PRAGMA user_version to ensure idempotent,
    repeatable, and safe schema evolutions.
    """
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version;")
    current_version = cursor.fetchone()[0]

    # Migration 1: Security, Status, Debt Balance and IVA Columns
    if current_version < 1:
        logging.info("Aplicando migración V1 (user_version: 0 -> 1)...")
        # users
        cursor.execute("PRAGMA table_info(users);")
        user_cols = [r["name"] for r in cursor.fetchall()]
        if "document_id" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN document_id TEXT;")
        if "phone" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN phone TEXT;")
        if "email" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN email TEXT;")
        if "is_active" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1;")
        if "failed_attempts" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN failed_attempts INTEGER NOT NULL DEFAULT 0;")
        if "locked_until" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN locked_until DATETIME DEFAULT NULL;")

        # customers
        cursor.execute("PRAGMA table_info(customers);")
        cust_cols = [r["name"] for r in cursor.fetchall()]
        if "customer_type" not in cust_cols:
            cursor.execute("ALTER TABLE customers ADD COLUMN customer_type TEXT NOT NULL DEFAULT 'PERSONA';")
        if "discount_percent" not in cust_cols:
            cursor.execute("ALTER TABLE customers ADD COLUMN discount_percent REAL NOT NULL DEFAULT 0;")
        if "debt_balance" not in cust_cols:
            cursor.execute("ALTER TABLE customers ADD COLUMN debt_balance REAL NOT NULL DEFAULT 0;")

        # products
        cursor.execute("PRAGMA table_info(products);")
        prod_cols = [r["name"] for r in cursor.fetchall()]
        if "cost" not in prod_cols:
            cursor.execute("ALTER TABLE products ADD COLUMN cost REAL NOT NULL DEFAULT 0;")
        if "iva" not in prod_cols:
            cursor.execute("ALTER TABLE products ADD COLUMN iva REAL NOT NULL DEFAULT 0;")
        if "unit_measure" not in prod_cols:
            cursor.execute("ALTER TABLE products ADD COLUMN unit_measure TEXT NOT NULL DEFAULT 'und';")
        if "is_active" not in prod_cols:
            cursor.execute("ALTER TABLE products ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1;")

        # sales
        cursor.execute("PRAGMA table_info(sales);")
        sale_cols = [r["name"] for r in cursor.fetchall()]
        if "customer_id" not in sale_cols:
            cursor.execute("ALTER TABLE sales ADD COLUMN customer_id INTEGER;")
        if "payment_method" not in sale_cols:
            cursor.execute("ALTER TABLE sales ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'EFECTIVO';")
        if "status" not in sale_cols:
            cursor.execute("ALTER TABLE sales ADD COLUMN status TEXT NOT NULL DEFAULT 'COMPLETADA';")
        if "iva_total" not in sale_cols:
            cursor.execute("ALTER TABLE sales ADD COLUMN iva_total REAL NOT NULL DEFAULT 0;")
        if "voided_at" not in sale_cols:
            cursor.execute("ALTER TABLE sales ADD COLUMN voided_at DATETIME DEFAULT NULL;")
        if "voided_by" not in sale_cols:
            cursor.execute("ALTER TABLE sales ADD COLUMN voided_by INTEGER DEFAULT NULL;")
        if "void_reason" not in sale_cols:
            cursor.execute("ALTER TABLE sales ADD COLUMN void_reason TEXT DEFAULT NULL;")

        # sale_items
        cursor.execute("PRAGMA table_info(sale_items);")
        si_cols = [r["name"] for r in cursor.fetchall()]
        if "fiado_remaining" not in si_cols:
            cursor.execute("ALTER TABLE sale_items ADD COLUMN fiado_remaining REAL;")
        if "discount_percent" not in si_cols:
            cursor.execute("ALTER TABLE sale_items ADD COLUMN discount_percent REAL NOT NULL DEFAULT 0;")
        if "discount_amount" not in si_cols:
            cursor.execute("ALTER TABLE sale_items ADD COLUMN discount_amount REAL NOT NULL DEFAULT 0;")
        if "iva_rate" not in si_cols:
            cursor.execute("ALTER TABLE sale_items ADD COLUMN iva_rate REAL NOT NULL DEFAULT 0;")
        if "iva_amount" not in si_cols:
            cursor.execute("ALTER TABLE sale_items ADD COLUMN iva_amount REAL NOT NULL DEFAULT 0;")

        conn.commit()
        conn.execute("PRAGMA user_version = 1;")
        current_version = 1
        logging.info("Migración V1 completada exitosamente.")

    # Migration 2: Invoice Sequences, Cash Shifts and Audit Log tables
    if current_version < 2:
        logging.info("Aplicando migración V2 (user_version: 1 -> 2)...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoice_sequences (
                prefix TEXT PRIMARY KEY,
                last_number INTEGER NOT NULL DEFAULT 0
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cash_shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                opened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                closed_at DATETIME DEFAULT NULL,
                initial_cash REAL NOT NULL DEFAULT 0,
                cash_sales REAL NOT NULL DEFAULT 0,
                electronic_sales REAL NOT NULL DEFAULT 0,
                credit_sales REAL NOT NULL DEFAULT 0,
                cash_withdrawals REAL NOT NULL DEFAULT 0,
                expected_cash REAL NOT NULL DEFAULT 0,
                actual_cash REAL DEFAULT NULL,
                difference REAL DEFAULT NULL,
                notes TEXT DEFAULT NULL,
                status TEXT NOT NULL DEFAULT 'ABIERTA' CHECK (status IN ('ABIERTA', 'CERRADA')),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                table_name TEXT,
                record_id INTEGER,
                details TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cash_shifts_user ON cash_shifts (user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs (action);")

        cursor.execute("INSERT OR IGNORE INTO invoice_sequences (prefix, last_number) VALUES ('XL', 0);")
        conn.commit()
        conn.execute("PRAGMA user_version = 2;")
        current_version = 2
        logging.info("Migración V2 completada exitosamente.")

    # Migration 3: Standardize roles to ADMIN and CAJERO
    if current_version < 3:
        logging.info("Aplicando migración V3 (user_version: 2 -> 3)...")
        cursor.execute("UPDATE users SET role = 'CAJERO' WHERE UPPER(role) = 'CASHIER';")
        cursor.execute("UPDATE users SET role = 'ADMIN' WHERE UPPER(role) = 'ADMIN';")
        conn.commit()
        conn.execute("PRAGMA user_version = 3;")
        current_version = 3
        logging.info("Migración V3 completada exitosamente.")

    # Migration 4: Ingredients, Recipes and Inventory Movements for XL Burguer
    if current_version < 4:
        logging.info("Aplicando migración V4: Ingredientes, Recetas y Movimientos XL Burguer...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ingredients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                stock_g REAL NOT NULL DEFAULT 0,
                min_stock_g REAL NOT NULL DEFAULT 0,
                cost_per_g REAL NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS product_recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                ingredient_id INTEGER NOT NULL,
                quantity_g REAL NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE,
                FOREIGN KEY (ingredient_id) REFERENCES ingredients (id) ON DELETE RESTRICT,
                UNIQUE (product_id, ingredient_id)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ingredient_id INTEGER,
                product_id INTEGER,
                movement_type TEXT NOT NULL CHECK (movement_type IN ('VENTA', 'COMPRA', 'AJUSTE', 'MERMA', 'INICIAL')),
                quantity REAL NOT NULL,
                previous_stock REAL NOT NULL,
                new_stock REAL NOT NULL,
                reference_id TEXT,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ingredient_id) REFERENCES ingredients (id) ON DELETE SET NULL,
                FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE SET NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ingredients_name ON ingredients (name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_product_recipes_prod ON product_recipes (product_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_product_recipes_ing ON product_recipes (ingredient_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_movements_ing ON inventory_movements (ingredient_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_movements_prod ON inventory_movements (product_id);")

        # Initialize XL invoice prefix
        cursor.execute("INSERT OR IGNORE INTO invoice_sequences (prefix, last_number) VALUES ('XL', 0);")

        conn.commit()
        conn.execute("PRAGMA user_version = 4;")
        current_version = 4
        logging.info("Migración V4 completada exitosamente.")

    # Migration 5: Ensure is_active column on products table
    if current_version < 5:
        logging.info("Aplicando migración V5: Verificación columna is_active en products...")
        cursor.execute("PRAGMA table_info(products);")
        prod_cols = [r["name"] for r in cursor.fetchall()]
        if "is_active" not in prod_cols:
            cursor.execute("ALTER TABLE products ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1;")
        conn.commit()
        conn.execute("PRAGMA user_version = 5;")
        current_version = 5
        logging.info("Migración V5 completada exitosamente.")


def initialize_database() -> None:
    """Initialize database tables from schema.sql, apply versioned migrations,
    and seed base catalog if database is empty.
    """
    schema_path = get_schema_path()
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"No se encontró el archivo de esquema en: {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as f:
        ddl_script = f.read()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
        has_existing_db = cursor.fetchone() is not None

        if has_existing_db:
            run_versioned_migrations(conn)

        cursor.executescript(ddl_script)
        conn.commit()

        if not has_existing_db:
            conn.execute("PRAGMA user_version = 5;")
            conn.commit()
        else:
            run_versioned_migrations(conn)

        # Seed catalog and base fast-food items
        seed_database(conn)


if __name__ == "__main__":
    initialize_database()
    print(f"Base de datos inicializada correctamente en: {get_database_path()}")
