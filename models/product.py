"""Product model and stock management for XL Burguer.
Implements weight conversions (g, kg, lb), catalog management, margins, and inventory operations.
"""

import sqlite3
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Product:
    id: int
    barcode: Optional[str]
    name: str
    category_id: int
    category_name: str
    sale_type: str  # 'PESO' | 'UNIDAD'
    price_base: float  # Price per gram (PESO) or unit price (UNIDAD)
    stock: float  # Grams (PESO) or units (UNIDAD)
    min_stock: float  # Grams (PESO) or units (UNIDAD)
    cost: float = 0.0  # Cost per gram (PESO) or unit cost (UNIDAD)
    iva: float = 0.0  # IVA percentage (e.g. 0, 5, 19)
    unit_measure: str = "kg"  # 'kg', 'g', 'lb', 'und', 'pqte', 'cubeta', 'botella', 'pza'
    is_active: bool = True

    @property
    def low_stock_threshold(self) -> float:
        """Threshold where product triggers preventive low stock warning (min_stock + ~20% safety buffer in whole numbers)."""
        import math
        if self.min_stock <= 0:
            return 0.0
        if self.sale_type == "PESO":
            u = self.unit_measure.lower().strip()
            if u == "kg":
                min_kg = self.min_stock / 1000.0
                threshold_kg = math.ceil(round(min_kg * 1.2, 4))
                return threshold_kg * 1000.0
            elif u == "lb":
                min_lb = self.min_stock / 500.0
                threshold_lb = math.ceil(round(min_lb * 1.2, 4))
                return threshold_lb * 500.0
            else:
                return float(math.ceil(self.min_stock * 1.2))
        else:
            return float(math.ceil(round(self.min_stock * 1.2, 4)))

    @property
    def is_out_of_stock(self) -> bool:
        """True if stock is zero or depleted."""
        return self.stock <= 0

    @property
    def is_low_stock(self) -> bool:
        """True if stock is depleted or within the preventive low stock threshold."""
        return self.stock <= self.low_stock_threshold

    @property
    def status(self) -> str:
        """Automatic inventory status based on stock and preventive min_stock threshold."""
        if self.stock <= 0:
            return "Agotado"
        elif self.stock <= self.low_stock_threshold:
            return "Bajo"
        else:
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
        else:
            return ("🟢 Normal", DarkTheme.SUCCESS_BG, DarkTheme.SUCCESS_BORDER, DarkTheme.SUCCESS_TEXT)

    @property
    def display_sale_type(self) -> str:
        """Friendly commercialization type label."""
        return "Peso" if self.sale_type == "PESO" else "Unidad"

    @property
    def display_price_sale(self) -> str:
        """Formatted selling price in COP with proper commercial unit."""
        if self.sale_type == "PESO":
            u = self.unit_measure.lower().strip()
            if u == "kg":
                return f"{format_currency_short(self.price_base * 1000)}/kg"
            elif u == "lb":
                return f"{format_currency_short(self.price_base * 500)}/lb"
            else:
                return f"{format_currency_short(self.price_base)}/g"
        u_norm = self.unit_measure.strip().lower()
        if u_norm in ("botella", "botellas", "und", "unidad", "unidades"):
            return f"{format_currency_short(self.price_base)}/und"
        return f"{format_currency_short(self.price_base)}/{self.unit_measure}"

    @property
    def display_cost(self) -> str:
        """Formatted purchase cost in COP with proper commercial unit."""
        if self.sale_type == "PESO":
            u = self.unit_measure.lower().strip()
            if u == "kg":
                return f"{format_currency_short(self.cost * 1000)}/kg"
            elif u == "lb":
                return f"{format_currency_short(self.cost * 500)}/lb"
            else:
                return f"{format_currency_short(self.cost)}/g"
        u_norm = self.unit_measure.strip().lower()
        if u_norm in ("botella", "botellas", "und", "unidad", "unidades"):
            return f"{format_currency_short(self.cost)}/und"
        return f"{format_currency_short(self.cost)}/{self.unit_measure}"

    @property
    def display_iva(self) -> str:
        """Formatted IVA percentage."""
        if float(self.iva).is_integer():
            return f"{int(self.iva)}%"
        return f"{self.iva:.1f}%"

    @property
    def display_stock(self) -> str:
        """Formatted stock representation for tables and displays."""
        return format_stock_display(self.stock, self.sale_type, self.unit_measure)

    @property
    def display_min_stock(self) -> str:
        """Formatted minimum stock representation for tables and displays."""
        return format_stock_display(self.min_stock, self.sale_type, self.unit_measure)

    @property
    def unit_selling_price_commercial(self) -> float:
        """Selling price in commercial unit (COP/kg if kg, COP/lb if lb, COP/und if unit)."""
        if self.sale_type == "PESO":
            u = self.unit_measure.lower().strip()
            if u == "kg":
                return self.price_base * 1000.0
            elif u == "lb":
                return self.price_base * 500.0
            return self.price_base
        return self.price_base

    @property
    def unit_cost_commercial(self) -> float:
        """Cost in commercial unit (COP/kg if kg, COP/lb if lb, COP/und if unit)."""
        if self.sale_type == "PESO":
            u = self.unit_measure.lower().strip()
            if u == "kg":
                return self.cost * 1000.0
            elif u == "lb":
                return self.cost * 500.0
            return self.cost
        return self.cost

    @property
    def profit_margin_amount(self) -> float:
        """Gross profit margin in COP per commercial unit."""
        return self.unit_selling_price_commercial - self.unit_cost_commercial

    @property
    def profit_margin_pct(self) -> float:
        """Gross profit margin percentage relative to selling price."""
        if self.price_base > 0:
            return ((self.price_base - self.cost) / self.price_base) * 100.0
        return 0.0

    @property
    def total_inventory_valuation_cost(self) -> float:
        """Total inventory value evaluated at cost price (COP)."""
        return max(0.0, self.stock) * self.cost

    @property
    def total_inventory_valuation_sale(self) -> float:
        """Total inventory value evaluated at selling price (COP)."""
        return max(0.0, self.stock) * self.price_base

    @property
    def formatted_stock(self) -> str:
        return format_stock_display(self.stock, self.sale_type, self.unit_measure)

    @property
    def fixed_package_info(self) -> Optional[Tuple[float, str]]:
        """Returns (quantity, unit) if product is a fixed-measure package,
        such as wine bottles (750 ml). The user cannot edit this quantity at POS.
        """
        import re
        if self.sale_type != "PESO":
            m = re.search(r'(\d+(?:\.\d+)?)\s*(ml|cc)', self.name, re.IGNORECASE)
            if m:
                return (float(m.group(1)), "ml")
            if "vino" in self.name.lower() or (self.category_name and "vino" in self.category_name.lower()):
                return (750.0, "ml")
        return None

    @property
    def formatted_price_base(self) -> str:
        if self.sale_type == "PESO":
            price_lb = self.price_base * 500
            price_kg = self.price_base * 1000
            return f"{format_currency_short(self.price_base)}/g ({format_currency_short(price_kg)}/kg)"
        pkg = self.fixed_package_info
        if pkg:
            qty, unit = pkg
            return f"{format_currency_short(self.price_base)}/und ({int(qty)} {unit})"
        return f"{format_currency_short(self.price_base)}/{self.unit_measure}"


def format_currency(amount: float) -> str:
    """Format numeric values into strict Colombian currency: COP $ #.### (no decimals)."""
    val = round(amount)
    formatted = f"{val:,}".replace(",", ".")
    return f"COP $ {formatted}"


def format_currency_short(amount: float) -> str:
    """Short currency format for tables and tickets: $ #.###"""
    val = round(amount)
    formatted = f"{val:,}".replace(",", ".")
    return f"$ {formatted}"


def convert_quantity_to_base(quantity: float, unit: str, sale_type: str) -> float:
    """Convert input quantity into base inventory units.
    For PESO: converts g, kg, lb into base Grams (g).
    For UNIDAD: returns quantity as float/int.
    If unit is 'ml' (e.g. 750 ml fixed bottle), selling the item deducts 1 unit (1 bottle) from inventory.
    Equivalences: 1 kg = 1000 g, 1 lb = 500 g.
    """
    if sale_type == "PESO":
        unit_lower = unit.lower().strip()
        if unit_lower == "kg":
            return quantity * 1000.0
        elif unit_lower == "lb":
            return quantity * 500.0
        elif unit_lower == "g":
            return quantity
        else:
            raise ValueError(f"Unidad de peso no válida: {unit}")
    unit_lower = unit.lower().strip()
    if unit_lower == "ml":
        for pkg in (500.0, 750.0, 350.0, 355.0, 330.0, 250.0, 400.0, 1000.0):
            if quantity >= pkg and (quantity % pkg == 0 or abs(quantity % pkg) < 1e-3):
                return float(round(quantity / pkg))
        bottles = round(quantity / 500.0) if quantity >= 500 else 1.0
        return float(max(1.0, bottles))
    return float(quantity)


def calculate_item_price(price_base: float, quantity: float, unit: str, sale_type: str) -> float:
    """Calculate total price in COP for an item based on unit selected and price base."""
    unit_lower = unit.lower().strip()
    if unit_lower == "ml":
        for pkg in (500.0, 750.0, 350.0, 355.0, 330.0, 250.0, 400.0, 1000.0):
            if quantity >= pkg and (quantity % pkg == 0 or abs(quantity % pkg) < 1e-3):
                return round(round(quantity / pkg) * price_base)
        bottles = round(quantity / 500.0) if quantity >= 500 else 1.0
        return round(max(1.0, bottles) * price_base)
    base_qty = convert_quantity_to_base(quantity, unit, sale_type)
    return round(base_qty * price_base)


def format_stock_display(stock: float, sale_type: str, unit_measure: str = "kg") -> str:
    """Format stock for clear user interface representation."""
    safe_stock = max(0.0, float(stock))
    if sale_type == "PESO":
        u = unit_measure.lower().strip()
        if u == "kg":
            kg_val = safe_stock / 1000.0
            if kg_val.is_integer():
                return f"{int(kg_val)} kg"
            return f"{kg_val:.2f} kg"
        elif u == "lb":
            lb_val = safe_stock / 500.0
            if lb_val.is_integer():
                return f"{int(lb_val)} lb"
            return f"{lb_val:.2f} lb"
        else:
            return f"{safe_stock:.0f} g"
    val_str = f"{int(safe_stock)}" if float(safe_stock).is_integer() else f"{safe_stock:.1f}"
    u_norm = unit_measure.strip()
    if u_norm.lower() in ("und", "unidad", "unidades", "botella", "botellas"):
        return f"{val_str} und"
    return f"{val_str} {u_norm}"


class ProductModel:
    """Data access layer for Products and Categories with complete catalog management."""

    @staticmethod
    def _row_to_product(row: sqlite3.Row) -> Product:
        """Helper to construct Product dataclass from sqlite3.Row safely."""
        keys = row.keys()
        return Product(
            id=row["id"],
            barcode=row["barcode"],
            name=row["name"],
            category_id=row["category_id"],
            category_name=row["category_name"] if "category_name" in keys else "",
            sale_type=row["sale_type"],
            price_base=float(row["price_base"]),
            stock=float(row["stock"]),
            min_stock=float(row["min_stock"]),
            cost=float(row["cost"]) if "cost" in keys and row["cost"] is not None else 0.0,
            iva=float(row["iva"]) if "iva" in keys and row["iva"] is not None else 0.0,
            unit_measure=row["unit_measure"] if "unit_measure" in keys and row["unit_measure"] else ("kg" if row["sale_type"] == "PESO" else "und"),
            is_active=bool(row["is_active"]) if "is_active" in keys and row["is_active"] is not None else True
        )

    @staticmethod
    def get_all(
        conn: sqlite3.Connection,
        search_query: str = "",
        category_id: Optional[int] = None,
        status_filter: Optional[str] = None,
        sale_type_filter: Optional[str] = None
    ) -> List[Product]:
        """Fetch all products matching search terms and multi-filters (category, status, sale_type)."""
        cursor = conn.cursor()
        sql = """
            SELECT p.id, p.barcode, p.name, p.category_id, c.name as category_name,
                   p.sale_type, p.price_base, p.cost, p.iva, p.unit_measure,
                   p.stock, p.min_stock, p.is_active
            FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE 1=1
        """
        params = []
        if category_id:
            sql += " AND p.category_id = ?"
            params.append(category_id)

        if sale_type_filter and sale_type_filter in ("PESO", "UNIDAD"):
            sql += " AND p.sale_type = ?"
            params.append(sale_type_filter)

        if search_query.strip():
            from database.connection import normalize_text
            norm_term = f"%{normalize_text(search_query)}%"
            raw_term = f"%{search_query.strip()}%"
            sql += """ AND (
                NORMALIZE_TEXT(p.name) LIKE ?
                OR p.barcode LIKE ?
                OR CAST(p.id AS TEXT) = ?
                OR NORMALIZE_TEXT(c.name) LIKE ?
            )"""
            params.extend([norm_term, raw_term, search_query.strip(), norm_term])

        sql += " ORDER BY c.name ASC, p.name ASC"
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        products = [ProductModel._row_to_product(row) for row in rows]

        # In-memory filter for calculated inventory status (Agotado, Bajo, Normal)
        if status_filter and status_filter in ("Agotado", "Bajo", "Normal"):
            products = [p for p in products if p.status == status_filter]

        return products

    @staticmethod
    def search(conn: sqlite3.Connection, query: str) -> List[Product]:
        """Search products by name, barcode, id or category using normalized matching."""
        return ProductModel.get_all(conn, search_query=query)

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, product_id: int) -> Optional[Product]:
        """Fetch single product by its primary key ID."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.id, p.barcode, p.name, p.category_id, c.name as category_name,
                   p.sale_type, p.price_base, p.cost, p.iva, p.unit_measure,
                   p.stock, p.min_stock, p.is_active
            FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE p.id = ?
            """,
            (product_id,)
        )
        row = cursor.fetchone()
        if row:
            return ProductModel._row_to_product(row)
        return None

    @staticmethod
    def get_by_barcode(conn: sqlite3.Connection, barcode: str) -> Optional[Product]:
        """Find product by exact barcode match, EAN-13 candidate, or ID fallback."""
        b = barcode.strip()
        if not b:
            return None
        cursor = conn.cursor()
        ean_candidate = f"7701234{int(b):06d}" if (b.isdigit() and len(b) < 6) else b
        cursor.execute(
            """
            SELECT p.id, p.barcode, p.name, p.category_id, c.name as category_name,
                   p.sale_type, p.price_base, p.cost, p.iva, p.unit_measure,
                   p.stock, p.min_stock, p.is_active
            FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE p.barcode = ? OR p.barcode = ? OR CAST(p.id AS TEXT) = ?
            """,
            (b, ean_candidate, b)
        )
        row = cursor.fetchone()
        if row:
            return ProductModel._row_to_product(row)
        return None

    @staticmethod
    def get_by_barcode_or_id(conn: sqlite3.Connection, query: str) -> Optional[Product]:
        """Find product by exact barcode match, numeric ID, or name match (omni-search for POS)."""
        q = query.strip()
        if not q:
            return None
        cursor = conn.cursor()

        # 1. Try exact barcode match first
        cursor.execute(
            """
            SELECT p.id, p.barcode, p.name, p.category_id, c.name as category_name,
                   p.sale_type, p.price_base, p.cost, p.iva, p.unit_measure,
                   p.stock, p.min_stock, p.is_active
            FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE p.barcode = ?
            """,
            (q,)
        )
        row = cursor.fetchone()

        # 2. If not found and query is numeric, check by normalized integer barcode or primary key ID
        if not row and q.isdigit():
            norm_num_str = str(int(q))
            cursor.execute(
                """
                SELECT p.id, p.barcode, p.name, p.category_id, c.name as category_name,
                       p.sale_type, p.price_base, p.cost, p.iva, p.unit_measure,
                       p.stock, p.min_stock, p.is_active
                FROM products p
                JOIN categories c ON p.category_id = c.id
                WHERE p.barcode = ? OR p.id = ?
                """,
                (norm_num_str, int(q))
            )
            row = cursor.fetchone()

        # 3. Fallback: Search by product name (accent and case-insensitive)
        if not row:
            from database.connection import normalize_text
            norm_q = normalize_text(q)
            if norm_q:
                # Exact name match
                cursor.execute(
                    """
                    SELECT p.id, p.barcode, p.name, p.category_id, c.name as category_name,
                           p.sale_type, p.price_base, p.cost, p.iva, p.unit_measure,
                           p.stock, p.min_stock, p.is_active
                    FROM products p
                    JOIN categories c ON p.category_id = c.id
                    WHERE NORMALIZE_TEXT(p.name) = ?
                    """,
                    (norm_q,)
                )
                row = cursor.fetchone()

                # Prefix / partial match
                if not row:
                    cursor.execute(
                        """
                        SELECT p.id, p.barcode, p.name, p.category_id, c.name as category_name,
                               p.sale_type, p.price_base, p.cost, p.iva, p.unit_measure,
                               p.stock, p.min_stock, p.is_active
                        FROM products p
                        JOIN categories c ON p.category_id = c.id
                        WHERE NORMALIZE_TEXT(p.name) LIKE ?
                        ORDER BY CASE WHEN NORMALIZE_TEXT(p.name) LIKE ? THEN 0 ELSE 1 END, p.name ASC
                        LIMIT 1
                        """,
                        (f"%{norm_q}%", f"{norm_q}%")
                    )
                    row = cursor.fetchone()

        if row:
            return ProductModel._row_to_product(row)
        return None

    @staticmethod
    def check_barcode_exists(conn: sqlite3.Connection, barcode: str, exclude_id: Optional[int] = None) -> bool:
        """Check if barcode is already assigned to another product."""
        b = barcode.strip()
        if not b:
            return False
        cursor = conn.cursor()
        if exclude_id is not None:
            cursor.execute("SELECT 1 FROM products WHERE barcode = ? AND id != ?", (b, exclude_id))
        else:
            cursor.execute("SELECT 1 FROM products WHERE barcode = ?", (b,))
        return cursor.fetchone() is not None

    @staticmethod
    def check_id_exists(conn: sqlite3.Connection, product_id: int, exclude_id: Optional[int] = None) -> bool:
        """Check if numeric product ID is already in use by another product."""
        cursor = conn.cursor()
        if exclude_id is not None:
            cursor.execute("SELECT 1 FROM products WHERE id = ? AND id != ?", (int(product_id), int(exclude_id)))
        else:
            cursor.execute("SELECT 1 FROM products WHERE id = ?", (int(product_id),))
        return cursor.fetchone() is not None

    @staticmethod
    def get_max_id(conn: sqlite3.Connection) -> int:
        """Get the maximum product ID currently registered in the database."""
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(id) FROM products")
        row = cursor.fetchone()
        return int(row[0]) if (row and row[0] is not None) else 0

    @staticmethod
    def get_next_available_barcode(conn: sqlite3.Connection) -> str:
        """Find the next available EAN-13 barcode (7701234xxxxxx) based on max product ID."""
        next_id = ProductModel.get_max_id(conn) + 1
        return f"7701234{next_id:06d}"

    @staticmethod
    def create_category(conn: sqlite3.Connection, name: str) -> int:
        """Create a new category if it doesn't already exist and return its ID."""
        cursor = conn.cursor()
        clean_name = name.strip()
        cursor.execute("SELECT id FROM categories WHERE LOWER(name) = LOWER(?)", (clean_name,))
        row = cursor.fetchone()
        if row:
            return int(row["id"])
        cursor.execute("INSERT INTO categories (name) VALUES (?)", (clean_name,))
        conn.commit()
        return int(cursor.lastrowid)

    @staticmethod
    def create(
        conn: sqlite3.Connection,
        barcode: Optional[str],
        name: str,
        category_id: int,
        sale_type: str,
        price_base: float,
        cost: float = 0.0,
        iva: float = 0.0,
        unit_measure: str = "kg",
        stock: float = 0.0,
        min_stock: float = 0.0,
        custom_id: Optional[int] = None,
        is_active: bool = True
    ) -> int:
        """Insert a new product record with optional user-specified ID."""
        cursor = conn.cursor()
        clean_barcode = barcode.strip() if barcode and barcode.strip() else None
        clean_name = name.strip()
        clean_sale_type = sale_type.strip().upper()
        clean_unit = unit_measure.strip().lower() if unit_measure and unit_measure.strip() else ("kg" if clean_sale_type == "PESO" else "und")

        if custom_id is not None:
            cursor.execute(
                """
                INSERT INTO products (id, barcode, name, category_id, sale_type, price_base, cost, iva, unit_measure, stock, min_stock, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(custom_id),
                    clean_barcode,
                    clean_name,
                    int(category_id),
                    clean_sale_type,
                    float(price_base),
                    float(cost),
                    float(iva),
                    clean_unit,
                    max(0.0, float(stock)),
                    max(0.0, float(min_stock)),
                    1 if is_active else 0
                )
            )
            conn.commit()
            return int(custom_id)
        else:
            cursor.execute(
                """
                INSERT INTO products (barcode, name, category_id, sale_type, price_base, cost, iva, unit_measure, stock, min_stock, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_barcode,
                    clean_name,
                    int(category_id),
                    clean_sale_type,
                    float(price_base),
                    float(cost),
                    float(iva),
                    clean_unit,
                    max(0.0, float(stock)),
                    max(0.0, float(min_stock)),
                    1 if is_active else 0
                )
            )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def update(
        conn: sqlite3.Connection,
        product_id: int,
        barcode: Optional[str],
        name: str,
        category_id: int,
        sale_type: str,
        price_base: float,
        cost: float = 0.0,
        iva: float = 0.0,
        unit_measure: str = "kg",
        stock: float = 0.0,
        min_stock: float = 0.0,
        is_active: Optional[bool] = None
    ) -> None:
        """Update an existing product record."""
        cursor = conn.cursor()
        clean_barcode = barcode.strip() if barcode and barcode.strip() else None
        clean_name = name.strip()
        clean_sale_type = sale_type.strip().upper()
        clean_unit = unit_measure.strip().lower() if unit_measure and unit_measure.strip() else ("kg" if clean_sale_type == "PESO" else "und")

        if is_active is not None:
            cursor.execute(
                """
                UPDATE products
                SET barcode = ?, name = ?, category_id = ?, sale_type = ?,
                    price_base = ?, cost = ?, iva = ?, unit_measure = ?,
                    stock = ?, min_stock = ?, is_active = ?
                WHERE id = ?
                """,
                (
                    clean_barcode,
                    clean_name,
                    int(category_id),
                    clean_sale_type,
                    float(price_base),
                    float(cost),
                    float(iva),
                    clean_unit,
                    max(0.0, float(stock)),
                    max(0.0, float(min_stock)),
                    1 if is_active else 0,
                    int(product_id)
                )
            )
        else:
            cursor.execute(
                """
                UPDATE products
                SET barcode = ?, name = ?, category_id = ?, sale_type = ?,
                    price_base = ?, cost = ?, iva = ?, unit_measure = ?,
                    stock = ?, min_stock = ?
                WHERE id = ?
                """,
                (
                    clean_barcode,
                    clean_name,
                    int(category_id),
                    clean_sale_type,
                    float(price_base),
                    float(cost),
                    float(iva),
                    clean_unit,
                    max(0.0, float(stock)),
                    max(0.0, float(min_stock)),
                    int(product_id)
                )
            )
        conn.commit()

    @staticmethod
    def delete(conn: sqlite3.Connection, product_id: int) -> None:
        """Delete a product by ID. Raises sqlite3.IntegrityError if product has sales records."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id = ?", (int(product_id),))
        conn.commit()

    @staticmethod
    def get_categories(conn: sqlite3.Connection) -> List[Tuple[int, str]]:
        """Get all categories as (id, name) tuples."""
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM categories ORDER BY name ASC")
        return [(row["id"], row["name"]) for row in cursor.fetchall()]

    @staticmethod
    def add_stock(conn: sqlite3.Connection, product_id: int, quantity_to_add: float) -> None:
        """Atomically increment a product's stock in base units (grams for PESO, units for UNIDAD)."""
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE products
            SET stock = stock + ?
            WHERE id = ?
            """,
            (float(quantity_to_add), int(product_id))
        )
        conn.commit()

    @staticmethod
    def add_stock_batch(conn: sqlite3.Connection, items: List[Tuple[int, float]]) -> None:
        """Atomically increment stock for multiple products in a single transaction.
        items is a list of (product_id, quantity_to_add_in_base_units).
        """
        cursor = conn.cursor()
        for pid, qty in items:
            cursor.execute(
                """
                UPDATE products
                SET stock = stock + ?
                WHERE id = ?
                """,
                (float(qty), int(pid))
            )
        conn.commit()

    @staticmethod
    def update_stock(conn: sqlite3.Connection, product_id: int, new_stock: float) -> bool:
        """Update a product's stock directly."""
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET stock = ? WHERE id = ?", (float(new_stock), int(product_id)))
        conn.commit()
        return cursor.rowcount > 0
