"""Sales and Sale Items model for XL Burguer.
Implements ACID transactions for checkout, recipe ingredient deductions in grams,
stock deduction for standalone items, and sales reporting.
"""

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from models.product import convert_quantity_to_base


def normalize_date_str(date_str: Optional[str]) -> Optional[str]:
    """Normalize user-entered date string to YYYY-MM-DD for SQLite query compatibility.
    Handles:
    - YYYY-MM-DD / YYYY/MM/DD
    - DD/MM/YYYY / DD-MM-YYYY
    - DD/MM/YY / DD-MM-YY
    """
    if not date_str:
        return None
    d = date_str.strip()
    if not d:
        return None

    # Try ISO YYYY-MM-DD or YYYY/MM/DD
    m_iso = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", d)
    if m_iso:
        y, m, day = m_iso.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(day):02d}"

    # Try Colombian/European DD/MM/YYYY or DD-MM-YYYY
    m_col = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", d)
    if m_col:
        day, m, y = m_col.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(day):02d}"

    # Try DD/MM/YY
    m_short = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{2})$", d)
    if m_short:
        day, m, y = m_short.groups()
        full_year = 2000 + int(y)
        return f"{full_year:04d}-{int(m):02d}-{int(day):02d}"

    return None


@dataclass
class CartItem:
    product_id: int
    product_name: str
    category_id: int
    category_name: str
    sale_type: str  # 'PESO' | 'UNIDAD'
    quantity: float  # Display quantity in unit_selected (e.g., 1.5 for 1.5 kg)
    unit_selected: str  # 'g', 'kg', 'lb', 'und', 'ml'
    price_base: float  # Price per gram or unit
    total_price: float  # Total COP for item
    original_price: float = 0.0  # Base subtotal before discount
    discount_percent: float = 0.0  # Discount percentage (e.g. 50.0 for 50%)
    discount_amount: float = 0.0  # Discount amount in COP

    def __post_init__(self):
        if self.original_price <= 0:
            self.original_price = self.total_price
        if self.discount_percent > 0 and self.discount_amount == 0.0:
            self.apply_discount(self.discount_percent)

    def apply_discount(self, percent: float) -> None:
        """Apply percentage discount (0 to 100) and recalculate total_price."""
        self.discount_percent = max(0.0, min(100.0, float(percent)))
        self.discount_amount = round(self.original_price * (self.discount_percent / 100.0))
        self.total_price = max(0.0, self.original_price - self.discount_amount)

    @property
    def base_stock_deduction(self) -> float:
        """Calculate grams or units to deduct from inventory."""
        return convert_quantity_to_base(self.quantity, self.unit_selected, self.sale_type)


VALID_PAYMENT_METHODS = {"EFECTIVO", "TARJETA", "TRANSFERENCIA", "NEQUI", "DAVIPLATA", "BANCOLOMBIA", "FIADO"}


@dataclass
class SaleDetail:
    id: int
    invoice_number: str
    timestamp: str
    subtotal: float
    total: float
    cash_received: float
    cash_change: float
    user_id: int
    user_name: str
    items: List[Dict[str, Any]]
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_document: Optional[str] = None
    payment_method: str = "EFECTIVO"
    customer_type: Optional[str] = "PERSONA"
    iva_total: float = 0.0
    status: str = "COMPLETADA"


class SaleModel:
    """Handles sales transactions and analytics queries."""

    @staticmethod
    def generate_next_invoice_number(conn: sqlite3.Connection) -> str:
        """Generate non-reusable consecutive invoice number using the invoice_sequences table.
        Format: XL-000001. Consecutive numbers are strictly monotonic and never reused on deletes.
        """
        cursor = conn.cursor()
        cursor.execute("SELECT last_number FROM invoice_sequences WHERE prefix = 'XL'")
        row = cursor.fetchone()
        if not row:
            cursor.execute("SELECT MAX(id) as max_id FROM sales")
            m_row = cursor.fetchone()
            curr = m_row["max_id"] if (m_row and m_row["max_id"] is not None) else 0
            cursor.execute("INSERT OR REPLACE INTO invoice_sequences (prefix, last_number) VALUES ('XL', ?)", (curr,))

        cursor.execute("UPDATE invoice_sequences SET last_number = last_number + 1 WHERE prefix = 'XL'")
        cursor.execute("SELECT last_number FROM invoice_sequences WHERE prefix = 'XL'")
        seq_row = cursor.fetchone()
        next_val = seq_row["last_number"] if seq_row else 1
        return f"XL-{next_val:06d}"

    @staticmethod
    def process_sale(
        conn: sqlite3.Connection,
        user_id: int,
        cart_items: List[CartItem],
        cash_received: float,
        customer_id: Optional[int] = None,
        payment_method: str = "EFECTIVO",
        allow_stock_override: bool = False
    ) -> SaleDetail:
        """Perform ACID sale transaction:
        1. Validate cart integrity, quantities (>0), non-negative prices, and payment method.
        2. BEGIN IMMEDIATE transaction.
        3. Insert into sales table with status 'COMPLETADA' and calculated IVA total.
        4. Insert each item into sale_items table with itemized IVA.
        5. Accurately deduct product stock (without false clipping).
        6. If FIADO, update customer quota and portfolio debt_balance.
        7. Pre-fetch cashier and customer display details BEFORE commit.
        8. Commit as the final DB operation. Rollback completely on any failure.
        """
        if not cart_items:
            raise ValueError("El carrito de compras no puede estar vacío.")

        # 1. Item validations (B6)
        for item in cart_items:
            if item.quantity <= 0:
                raise ValueError(f"La cantidad para el producto '{item.product_name}' debe ser mayor a cero.")
            if item.total_price < 0 or item.price_base < 0:
                raise ValueError(f"El precio del producto '{item.product_name}' no puede ser negativo.")
            if item.discount_percent < 0 or item.discount_percent > 100:
                raise ValueError(f"El porcentaje de descuento para '{item.product_name}' debe estar entre 0% y 100%.")

        # 2. Strict Payment Method Validation (B11)
        raw_method = (payment_method or "EFECTIVO").strip().upper()
        if raw_method in VALID_PAYMENT_METHODS or raw_method.startswith("TRANSFERENCIA"):
            norm_payment_method = raw_method
        else:
            valid_list = ", ".join(sorted(VALID_PAYMENT_METHODS))
            raise ValueError(
                f"Método de pago no reconocido: '{payment_method}'. Métodos válidos: {valid_list}."
            )

        # 3. Currency rounding to integer pesos (COP) (B2)
        subtotal = int(round(sum(float(item.total_price) for item in cart_items)))
        total = subtotal

        if norm_payment_method == "FIADO":
            if not customer_id:
                raise ValueError("Para registrar una venta fiada debe seleccionar un cliente o empresa registrado.")
            cash_received = total
            cash_change = 0.0
        elif norm_payment_method != "EFECTIVO":
            # For electronic methods, cash_received defaults to total and change is 0
            if cash_received < total:
                cash_received = total
            cash_change = 0.0
        else:
            cash_received = int(round(float(cash_received)))
            if cash_received < total:
                raise ValueError(
                    f"El dinero recibido (${cash_received:,.0f}) es inferior al total a pagar (${total:,.0f})."
                )
            cash_change = int(round(cash_received - total))

        cursor = conn.cursor()

        try:
            # 4. Immediate transaction mode (A2)
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE;")

            invoice_number = SaleModel.generate_next_invoice_number(conn)
            now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Calculate IVA breakdown across all items (B1)
            iva_total = 0.0
            prepared_items = []
            from models.customer import CustomerModel
            from models.product import format_stock_display

            # Check if table ingredients exists in schema
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ingredients';")
            has_ingredients_table = cursor.fetchone() is not None

            # Aggregate ingredient requirements and direct product needs across cart items
            needed_ingredients = {}  # ing_id: dict
            needed_products_direct = {}  # prod_id: dict

            for item in cart_items:
                cursor.execute(
                    "SELECT name, stock, sale_type, unit_measure, iva FROM products WHERE id = ?",
                    (item.product_id,)
                )
                p_row = cursor.fetchone()
                if not p_row:
                    raise ValueError(f"El producto con ID {item.product_id} ('{item.product_name}') no existe en el catálogo.")

                # Check if product has associated recipes
                recipes = []
                if has_ingredients_table:
                    cursor.execute(
                        """
                        SELECT pr.ingredient_id, pr.quantity_g, i.name as ing_name, i.stock_g
                        FROM product_recipes pr
                        JOIN ingredients i ON pr.ingredient_id = i.id
                        WHERE pr.product_id = ?
                        """,
                        (item.product_id,)
                    )
                    recipes = cursor.fetchall()

                if recipes:
                    item_qty = float(item.quantity)
                    for r in recipes:
                        ing_id = r["ingredient_id"]
                        req_g = float(r["quantity_g"]) * item_qty
                        if ing_id not in needed_ingredients:
                            needed_ingredients[ing_id] = {
                                "name": r["ing_name"],
                                "required_g": 0.0,
                                "stock_g": float(r["stock_g"]),
                                "product_name": item.product_name
                            }
                        needed_ingredients[ing_id]["required_g"] += req_g
                else:
                    deduction = item.base_stock_deduction
                    p_id = item.product_id
                    if p_id not in needed_products_direct:
                        needed_products_direct[p_id] = {
                            "name": p_row["name"],
                            "required": 0.0,
                            "stock": float(p_row["stock"]),
                            "sale_type": p_row["sale_type"],
                            "unit_measure": p_row["unit_measure"]
                        }
                    needed_products_direct[p_id]["required"] += deduction

                # Calculate item IVA (prices in retail include IVA)
                item_iva_rate = float(p_row["iva"]) if ("iva" in p_row.keys() and p_row["iva"] is not None) else 0.0
                if item_iva_rate > 0:
                    base_val = item.total_price / (1.0 + (item_iva_rate / 100.0))
                    item_iva_amt = int(round(item.total_price - base_val))
                else:
                    item_iva_amt = 0.0
                iva_total += item_iva_amt

                prepared_items.append((item, p_row, item.base_stock_deduction, item_iva_rate, item_iva_amt, recipes))

            # Stock verification: block if override disabled
            if not allow_stock_override:
                for ing_id, ing_data in needed_ingredients.items():
                    if ing_data["stock_g"] < ing_data["required_g"]:
                        shortage_g = ing_data["required_g"] - ing_data["stock_g"]
                        raise ValueError(
                            f"Ingrediente insuficiente: '{ing_data['name']}'. "
                            f"Disponible: {ing_data['stock_g']:,.0f} g, "
                            f"Requerido: {ing_data['required_g']:,.0f} g, "
                            f"Faltante: {shortage_g:,.0f} g."
                        )

                for p_id, p_data in needed_products_direct.items():
                    if p_data["stock"] < p_data["required"]:
                        disp_stk = format_stock_display(p_data["stock"], p_data["sale_type"], p_data["unit_measure"])
                        raise ValueError(f"Stock insuficiente para '{p_data['name']}'. Stock disponible: {disp_stk}.")

            # 5. Insert Sale Header with customer, payment method, IVA, and status (B1, B5)
            cursor.execute(
                """
                INSERT INTO sales (invoice_number, timestamp, subtotal, total, cash_received, cash_change,
                                   user_id, customer_id, payment_method, status, iva_total)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETADA', ?)
                """,
                (invoice_number, now_iso, subtotal, total, cash_received, cash_change,
                 user_id, customer_id, norm_payment_method, iva_total)
            )
            sale_id = cursor.lastrowid

            # 6. Deduct ingredients and standalone stock, insert items and log movements
            # First, deduct aggregated ingredients
            for ing_id, ing_data in needed_ingredients.items():
                cursor.execute("SELECT stock_g FROM ingredients WHERE id = ?", (ing_id,))
                cur_row = cursor.fetchone()
                prev_g = float(cur_row["stock_g"]) if cur_row else 0.0
                new_g = prev_g - ing_data["required_g"]
                cursor.execute("UPDATE ingredients SET stock_g = ? WHERE id = ?", (new_g, ing_id))
                cursor.execute(
                    """
                    INSERT INTO inventory_movements (
                        ingredient_id, movement_type, quantity, previous_stock, new_stock, reference_id, notes
                    ) VALUES (?, 'VENTA', ?, ?, ?, ?, ?)
                    """,
                    (ing_id, ing_data["required_g"], prev_g, new_g, invoice_number, f"Consumo venta {invoice_number}")
                )

            # Deduct standalone direct products
            for p_id, p_data in needed_products_direct.items():
                cursor.execute("SELECT stock FROM products WHERE id = ?", (p_id,))
                cur_row = cursor.fetchone()
                prev_s = float(cur_row["stock"]) if cur_row else 0.0
                new_s = prev_s - p_data["required"]
                cursor.execute("UPDATE products SET stock = ? WHERE id = ?", (new_s, p_id))
                cursor.execute(
                    """
                    INSERT INTO inventory_movements (
                        product_id, movement_type, quantity, previous_stock, new_stock, reference_id, notes
                    ) VALUES (?, 'VENTA', ?, ?, ?, ?, ?)
                    """,
                    (p_id, p_data["required"], prev_s, new_s, invoice_number, f"Venta directa {invoice_number}")
                )

            saved_items = []
            for item, p_row, deduction, item_iva_rate, item_iva_amt, recipes in prepared_items:
                # If product has no recipes and wasn't deducted in needed_products_direct, deduct now
                if not recipes and item.product_id not in needed_products_direct:
                    cursor.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (deduction, item.product_id))

                # If FIADO sale to customer, deduct from company quota
                fiado_rem = None
                if norm_payment_method == "FIADO" and customer_id:
                    fiado_rem = CustomerModel.consume_company_quota(
                        conn=conn,
                        customer_id=customer_id,
                        product_id=item.product_id,
                        quantity=item.quantity,
                        unit=item.unit_selected
                    )

                unit_price_display = (
                    item.price_base if item.sale_type == "UNIDAD"
                    else (item.total_price / item.quantity if item.quantity > 0 else item.price_base)
                )

                cursor.execute(
                    """
                    INSERT INTO sale_items (sale_id, product_id, quantity, unit_selected, unit_price,
                                           total_price, fiado_remaining, discount_percent, discount_amount,
                                           iva_rate, iva_amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (sale_id, item.product_id, item.quantity, item.unit_selected, unit_price_display,
                     item.total_price, fiado_rem, item.discount_percent, item.discount_amount,
                     item_iva_rate, item_iva_amt)
                )

                saved_items.append({
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "category_name": item.category_name,
                    "quantity": item.quantity,
                    "unit_selected": item.unit_selected,
                    "unit_price": unit_price_display,
                    "total_price": item.total_price,
                    "original_price": item.original_price,
                    "discount_percent": item.discount_percent,
                    "discount_amount": item.discount_amount,
                    "fiado_remaining": fiado_rem,
                    "iva_rate": item_iva_rate,
                    "iva_amount": item_iva_amt
                })

            # If FIADO sale, increment customer portfolio debt_balance (B3)
            if norm_payment_method == "FIADO" and customer_id:
                CustomerModel.add_debt(conn, customer_id, total)

            # 7. Query user and customer details BEFORE commit to avoid post-commit exceptions (B8)
            cursor.execute("SELECT full_name FROM users WHERE id = ?", (user_id,))
            user_row = cursor.fetchone()
            user_name = user_row["full_name"] if (user_row and user_row["full_name"]) else "Administrador XL"

            customer_name = None
            customer_document = None
            if customer_id:
                cursor.execute("SELECT first_name, last_name, document_id FROM customers WHERE id = ?", (customer_id,))
                crow = cursor.fetchone()
                if crow:
                    first = crow["first_name"] or ""
                    last = crow["last_name"] or ""
                    customer_name = f"{first} {last}".strip() or None
                    customer_document = crow["document_id"]

            # 8. Commit as the very last operation in the transaction (B8)
            conn.commit()

            return SaleDetail(
                id=sale_id,
                invoice_number=invoice_number,
                timestamp=now_iso,
                subtotal=subtotal,
                total=total,
                cash_received=cash_received,
                cash_change=cash_change,
                user_id=user_id,
                user_name=user_name,
                items=saved_items,
                customer_id=customer_id,
                customer_name=customer_name,
                customer_document=customer_document,
                payment_method=norm_payment_method,
                iva_total=iva_total,
                status="COMPLETADA"
            )

        except ValueError:
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Error procesando la transacción de venta: {e}") from e

    @staticmethod
    def void_sale(
        conn: sqlite3.Connection,
        sale_id: int,
        user_id: Optional[int] = None,
        reason: str = "Anulación por cajero/administrador"
    ) -> bool:
        """Atomically void a completed sale (B5):
        1. Check sale exists and is not already voided.
        2. Restore stock for all products sold in sale_items.
        3. If sale was FIADO, restore company quota and reduce customer debt_balance.
        4. Update sale record with status='ANULADA', voided_at, voided_by, void_reason.
        5. Log action in audit_logs.
        6. Commit cleanly.
        """
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sales WHERE id = ?", (sale_id,))
        sale = cursor.fetchone()
        if not sale:
            return False

        current_status = sale["status"] if "status" in sale.keys() and sale["status"] else "COMPLETADA"
        if current_status == "ANULADA":
            raise ValueError(f"La venta {sale['invoice_number']} ya se encuentra anulada.")

        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE;")

        try:
            # 1. Revert product and ingredient stocks based on sale_items
            cursor.execute(
                "SELECT product_id, quantity, unit_selected FROM sale_items WHERE sale_id = ?",
                (sale_id,)
            )
            items = cursor.fetchall()
            for it in items:
                # Check if product has recipes
                cursor.execute(
                    """
                    SELECT pr.ingredient_id, pr.quantity_g
                    FROM product_recipes pr
                    WHERE pr.product_id = ?
                    """,
                    (it["product_id"],)
                )
                rec_items = cursor.fetchall()
                if rec_items:
                    for rec in rec_items:
                        ing_qty = float(rec["quantity_g"]) * float(it["quantity"])
                        cursor.execute("SELECT stock_g FROM ingredients WHERE id = ?", (rec["ingredient_id"],))
                        cur_r = cursor.fetchone()
                        prev_g = float(cur_r["stock_g"]) if cur_r else 0.0
                        new_g = prev_g + ing_qty
                        cursor.execute("UPDATE ingredients SET stock_g = ? WHERE id = ?", (new_g, rec["ingredient_id"]))
                        cursor.execute(
                            """
                            INSERT INTO inventory_movements (
                                ingredient_id, movement_type, quantity, previous_stock, new_stock, reference_id, notes
                            ) VALUES (?, 'AJUSTE', ?, ?, ?, ?, ?)
                            """,
                            (rec["ingredient_id"], ing_qty, prev_g, new_g, sale["invoice_number"], f"Restitución por anulación {sale['invoice_number']}")
                        )
                else:
                    cursor.execute("SELECT sale_type, stock FROM products WHERE id = ?", (it["product_id"],))
                    p = cursor.fetchone()
                    if p:
                        base_qty = convert_quantity_to_base(it["quantity"], it["unit_selected"], p["sale_type"])
                        prev_s = float(p["stock"])
                        new_s = prev_s + base_qty
                        cursor.execute(
                            "UPDATE products SET stock = ? WHERE id = ?",
                            (new_s, it["product_id"])
                        )
                        cursor.execute(
                            """
                            INSERT INTO inventory_movements (
                                product_id, movement_type, quantity, previous_stock, new_stock, reference_id, notes
                            ) VALUES (?, 'AJUSTE', ?, ?, ?, ?, ?)
                            """,
                            (it["product_id"], base_qty, prev_s, new_s, sale["invoice_number"], f"Restitución por anulación {sale['invoice_number']}")
                        )

            # 2. If FIADO, revert customer quota and portfolio debt
            p_method = (sale["payment_method"] or "EFECTIVO").upper()
            cust_id = sale["customer_id"]
            if p_method == "FIADO" and cust_id:
                from models.customer import CustomerModel
                for it in items:
                    CustomerModel.restore_company_quota(
                        conn=conn,
                        customer_id=cust_id,
                        product_id=it["product_id"],
                        quantity=it["quantity"],
                        unit=it["unit_selected"]
                    )
                CustomerModel.reduce_debt(conn, cust_id, float(sale["total"]))

            # 3. Mark sale as ANULADA
            now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                """
                UPDATE sales
                SET status = 'ANULADA',
                    voided_at = ?,
                    voided_by = ?,
                    void_reason = ?
                WHERE id = ?
                """,
                (now_iso, user_id, reason.strip(), sale_id)
            )

            # 4. Insert into audit_logs
            cursor.execute(
                """
                INSERT INTO audit_logs (user_id, action, table_name, record_id, details)
                VALUES (?, 'VOID_SALE', 'sales', ?, ?)
                """,
                (user_id, sale_id,
                 f"Venta {sale['invoice_number']} por ${sale['total']:,.0f} anulada. Motivo: {reason.strip()}")
            )

            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise

    @staticmethod
    def get_sale_by_invoice(conn: sqlite3.Connection, invoice_number: str) -> Optional[SaleDetail]:
        """Retrieve full sale data by invoice number."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.id, s.invoice_number, s.timestamp, s.subtotal, s.total,
                   s.cash_received, s.cash_change, s.user_id, COALESCE(u.full_name, 'Diego') as user_name,
                   s.customer_id, COALESCE(s.payment_method, 'EFECTIVO') as payment_method,
                   (c.first_name || ' ' || c.last_name) as customer_name,
                   c.document_id as customer_document
            FROM sales s
            LEFT JOIN users u ON s.user_id = u.id
            LEFT JOIN customers c ON s.customer_id = c.id
            WHERE s.invoice_number = ?
            """,
            (invoice_number.strip(),)
        )
        sale_row = cursor.fetchone()
        if not sale_row:
            return None

        cursor.execute(
            """
            SELECT si.product_id, p.name as product_name, c.name as category_name,
                   si.quantity, si.unit_selected, si.unit_price, si.total_price, si.fiado_remaining,
                   COALESCE(si.discount_percent, 0) as discount_percent,
                   COALESCE(si.discount_amount, 0) as discount_amount
            FROM sale_items si
            JOIN products p ON si.product_id = p.id
            JOIN categories c ON p.category_id = c.id
            WHERE si.sale_id = ?
            ORDER BY si.id ASC
            """,
            (sale_row["id"],)
        )
        items = [dict(r) for r in cursor.fetchall()]

        return SaleDetail(
            id=sale_row["id"],
            invoice_number=sale_row["invoice_number"],
            timestamp=sale_row["timestamp"],
            subtotal=sale_row["subtotal"],
            total=sale_row["total"],
            cash_received=sale_row["cash_received"],
            cash_change=sale_row["cash_change"],
            user_id=sale_row["user_id"],
            user_name=sale_row["user_name"],
            items=items,
            customer_id=sale_row["customer_id"],
            customer_name=(sale_row["customer_name"].strip() if sale_row["customer_name"] else None),
            customer_document=sale_row["customer_document"],
            payment_method=sale_row["payment_method"] or "EFECTIVO"
        )

    @staticmethod
    def get_sale_by_id(conn: sqlite3.Connection, sale_id: int) -> Optional[SaleDetail]:
        """Retrieve full sale data by primary key sale ID."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.id, s.invoice_number, s.timestamp, s.subtotal, s.total,
                   s.cash_received, s.cash_change, s.user_id, COALESCE(u.full_name, 'Diego') as user_name,
                   s.customer_id, COALESCE(s.payment_method, 'EFECTIVO') as payment_method,
                   COALESCE(c.customer_type, 'PERSONA') as customer_type,
                   (c.first_name || ' ' || c.last_name) as customer_name,
                   c.document_id as customer_document
            FROM sales s
            LEFT JOIN users u ON s.user_id = u.id
            LEFT JOIN customers c ON s.customer_id = c.id
            WHERE s.id = ?
            """,
            (sale_id,)
        )
        sale_row = cursor.fetchone()
        if not sale_row:
            return None

        cursor.execute(
            """
            SELECT si.product_id, p.name as product_name, c.name as category_name,
                   si.quantity, si.unit_selected, si.unit_price, si.total_price, si.fiado_remaining
            FROM sale_items si
            JOIN products p ON si.product_id = p.id
            JOIN categories c ON p.category_id = c.id
            WHERE si.sale_id = ?
            ORDER BY si.id ASC
            """,
            (sale_row["id"],)
        )
        items = [dict(r) for r in cursor.fetchall()]

        return SaleDetail(
            id=sale_row["id"],
            invoice_number=sale_row["invoice_number"],
            timestamp=sale_row["timestamp"],
            subtotal=sale_row["subtotal"],
            total=sale_row["total"],
            cash_received=sale_row["cash_received"],
            cash_change=sale_row["cash_change"],
            user_id=sale_row["user_id"],
            user_name=sale_row["user_name"],
            items=items,
            customer_id=sale_row["customer_id"],
            customer_name=(sale_row["customer_name"].strip() if sale_row["customer_name"] else None),
            customer_document=sale_row["customer_document"],
            payment_method=sale_row["payment_method"] or "EFECTIVO",
            customer_type=sale_row["customer_type"] or "PERSONA"
        )

    @staticmethod
    def get_daily_summary(conn: sqlite3.Connection) -> Dict[str, Any]:
        """Compute metrics for today's sales, separating physical cash from electronic and fiado."""
        cursor = conn.cursor()
        today_date = datetime.now().strftime("%Y-%m-%d")

        # Revenue and invoice count today separated by payment category
        cursor.execute(
            """
            SELECT 
                COALESCE(SUM(s.total), 0) as total_sold,
                COALESCE(SUM(CASE WHEN UPPER(s.payment_method) = 'EFECTIVO' THEN s.total ELSE 0 END), 0) as cash_sold,
                COALESCE(SUM(CASE WHEN UPPER(s.payment_method) NOT IN ('EFECTIVO', 'FIADO') THEN s.total ELSE 0 END), 0) as electronic_sold,
                COALESCE(SUM(CASE WHEN UPPER(s.payment_method) = 'FIADO' THEN s.total ELSE 0 END), 0) as fiado_sold,
                COUNT(s.id) as sales_count
            FROM sales s
            WHERE date(s.timestamp) = date(?) 
              AND COALESCE(s.status, 'COMPLETADA') != 'ANULADA'
              AND s.id IN (SELECT DISTINCT sale_id FROM sale_items)
            """,
            (today_date,)
        )
        row = cursor.fetchone()
        total_sold = row["total_sold"] if row else 0.0
        cash_sold = row["cash_sold"] if row else 0.0
        electronic_sold = row["electronic_sold"] if row else 0.0
        fiado_sold = row["fiado_sold"] if row else 0.0
        sales_count = row["sales_count"] if row else 0

        # Best selling product today
        cursor.execute(
            """
            SELECT p.name as product_name, SUM(si.total_price) as sum_revenue,
                   COUNT(si.id) as times_sold
            FROM sale_items si
            JOIN sales s ON si.sale_id = s.id
            JOIN products p ON si.product_id = p.id
            WHERE date(s.timestamp) = date(?)
              AND COALESCE(s.status, 'COMPLETADA') != 'ANULADA'
            GROUP BY p.id
            ORDER BY sum_revenue DESC
            LIMIT 1
            """,
            (today_date,)
        )
        best_row = cursor.fetchone()
        best_product = best_row["product_name"] if best_row else "Sin ventas registradas"

        return {
            "total_sold": total_sold,
            "cash_sold": cash_sold,
            "electronic_sold": electronic_sold,
            "fiado_sold": fiado_sold,
            "sales_count": sales_count,
            "best_product": best_product
        }

    @staticmethod
    def get_periodic_analytics(conn: sqlite3.Connection) -> Dict[str, Any]:
        """Compute sales balances and top products across Day, Week, and Month.
        Returns metrics for:
            - daily: today's balance & top product
            - weekly: last 7 days balance & top product
            - monthly: current month balance & top product
        """
        cursor = conn.cursor()
        today_iso = datetime.now().strftime("%Y-%m-%d")
        current_month = datetime.now().strftime("%Y-%m")

        periods = {
            "daily": ("date(s.timestamp) = date(?) AND COALESCE(s.status, 'COMPLETADA') != 'ANULADA'", (today_iso,)),
            "weekly": ("date(s.timestamp) >= date(?, '-6 days') AND date(s.timestamp) <= date(?) AND COALESCE(s.status, 'COMPLETADA') != 'ANULADA'", (today_iso, today_iso)),
            "monthly": ("strftime('%Y-%m', s.timestamp) = ? AND COALESCE(s.status, 'COMPLETADA') != 'ANULADA'", (current_month,)),
        }

        results = {}
        for key, (where_clause, params) in periods.items():
            # 1. Total revenue and invoice count
            cursor.execute(
                f"""
                SELECT COALESCE(SUM(s.total), 0) as total_sold,
                       COUNT(s.id) as sales_count
                FROM sales s
                WHERE {where_clause} AND s.id IN (SELECT DISTINCT sale_id FROM sale_items)
                """,
                params
            )
            row = cursor.fetchone()
            tot = float(row["total_sold"]) if row and row["total_sold"] is not None else 0.0
            cnt = int(row["sales_count"]) if row and row["sales_count"] is not None else 0

            # 2. Top product by revenue in period
            cursor.execute(
                f"""
                SELECT p.name as product_name,
                       COALESCE(SUM(si.total_price), 0) as top_revenue,
                       COALESCE(SUM(si.quantity), 0) as top_qty,
                       p.sale_type
                FROM sale_items si
                JOIN sales s ON si.sale_id = s.id
                JOIN products p ON si.product_id = p.id
                WHERE {where_clause}
                GROUP BY p.id
                ORDER BY top_revenue DESC
                LIMIT 1
                """,
                params
            )
            top_row = cursor.fetchone()
            if top_row and top_row["top_revenue"] > 0:
                p_name = top_row["product_name"]
                p_rev = float(top_row["top_revenue"])
                p_qty = float(top_row["top_qty"])
                p_type = top_row["sale_type"]
                unit_label = "kg" if p_type == "PESO" else "und"
                display_qty = f"{p_qty:,.1f} {unit_label}"
            else:
                p_name = None
                p_rev = 0.0
                display_qty = "-"

            # 3. Top category by revenue in period
            cursor.execute(
                f"""
                SELECT c.name as category_name,
                       COALESCE(SUM(si.total_price), 0) as cat_revenue
                FROM sale_items si
                JOIN sales s ON si.sale_id = s.id
                JOIN products p ON si.product_id = p.id
                JOIN categories c ON p.category_id = c.id
                WHERE {where_clause}
                GROUP BY c.id
                ORDER BY cat_revenue DESC
                LIMIT 1
                """,
                params
            )
            cat_row = cursor.fetchone()
            top_cat_name = cat_row["category_name"] if cat_row and cat_row["cat_revenue"] > 0 else "-"

            results[key] = {
                "total_sold": tot,
                "sales_count": cnt,
                "avg_ticket": (tot / cnt) if cnt > 0 else 0.0,
                "top_product_name": p_name,
                "top_product_revenue": p_rev,
                "top_product_qty": display_qty,
                "top_category_name": top_cat_name,
            }

        return results

    @staticmethod
    def get_sales_summary(
        conn: sqlite3.Connection,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        category_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Compute metrics for the filtered period, excluding voided sales."""
        cursor = conn.cursor()
        norm_start = normalize_date_str(start_date)
        norm_end = normalize_date_str(end_date)

        where_clauses = ["COALESCE(s.status, 'COMPLETADA') != 'ANULADA'"]
        params: List[Any] = []

        if norm_start:
            where_clauses.append("date(s.timestamp) >= date(?)")
            params.append(norm_start)

        if norm_end:
            where_clauses.append("date(s.timestamp) <= date(?)")
            params.append(norm_end)

        if min_price is not None and min_price > 0:
            where_clauses.append("s.total >= ?")
            params.append(min_price)

        if max_price is not None and max_price > 0:
            where_clauses.append("s.total <= ?")
            params.append(max_price)

        if category_id is not None and category_id > 0:
            where_clauses.append("p.category_id = ?")
            params.append(category_id)

        where_sql = " AND ".join(where_clauses)

        # 1. Total revenue and invoice count in period
        summary_sql = f"""
            SELECT COALESCE(SUM(distinct_sales.total), 0) as total_sold,
                   COUNT(distinct_sales.id) as sales_count
            FROM (
                SELECT s.id, s.total
                FROM sales s
                LEFT JOIN sale_items si ON s.id = si.sale_id
                LEFT JOIN products p ON si.product_id = p.id
                WHERE {where_sql}
                GROUP BY s.id
            ) distinct_sales
        """
        cursor.execute(summary_sql, params)
        row = cursor.fetchone()
        total_sold = row["total_sold"] if row else 0.0
        sales_count = row["sales_count"] if row else 0

        # 2. Best selling product in period
        best_sql = f"""
            SELECT p.name as product_name, SUM(si.total_price) as sum_revenue
            FROM sale_items si
            JOIN sales s ON si.sale_id = s.id
            JOIN products p ON si.product_id = p.id
            WHERE {where_sql}
            GROUP BY p.id
            ORDER BY sum_revenue DESC
            LIMIT 1
        """
        cursor.execute(best_sql, params)
        best_row = cursor.fetchone()
        best_product = best_row["product_name"] if best_row else "Sin ventas registradas"

        avg_ticket = (total_sold / sales_count) if sales_count > 0 else 0.0

        return {
            "total_sold": total_sold,
            "total_sales": total_sold,
            "sales_count": sales_count,
            "avg_ticket": avg_ticket,
            "best_product": best_product
        }

    @staticmethod
    def get_filtered_sales_items(
        conn: sqlite3.Connection,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        category_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Fetch granular item-level sales rows with filters for table display and Excel export."""
        cursor = conn.cursor()
        sql = """
            SELECT s.invoice_number, s.timestamp, COALESCE(u.full_name, 'Diego') as cashier_name,
                   c.name as category_name, p.name as product_name,
                   si.quantity, si.unit_selected, si.unit_price, si.total_price as item_total,
                   s.total as invoice_total, COALESCE(s.status, 'COMPLETADA') as status
            FROM sale_items si
            JOIN sales s ON si.sale_id = s.id
            LEFT JOIN users u ON s.user_id = u.id
            JOIN products p ON si.product_id = p.id
            JOIN categories c ON p.category_id = c.id
            WHERE COALESCE(s.status, 'COMPLETADA') != 'ANULADA'
        """
        params: List[Any] = []

        norm_start = normalize_date_str(start_date)
        norm_end = normalize_date_str(end_date)

        if norm_start:
            sql += " AND date(s.timestamp) >= date(?)"
            params.append(norm_start)

        if norm_end:
            sql += " AND date(s.timestamp) <= date(?)"
            params.append(norm_end)

        if min_price is not None and min_price > 0:
            sql += " AND s.total >= ?"
            params.append(min_price)

        if max_price is not None and max_price > 0:
            sql += " AND s.total <= ?"
            params.append(max_price)

        if category_id is not None and category_id > 0:
            sql += " AND p.category_id = ?"
            params.append(category_id)

        sql += " ORDER BY s.timestamp DESC, si.id ASC"
        cursor.execute(sql, params)
        return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def get_filtered_invoices(
        conn: sqlite3.Connection,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        category_id: Optional[int] = None,
        query: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch invoice-level summary for the stats history table, with multi-filters and text search."""
        cursor = conn.cursor()
        sql = """
            SELECT s.id, s.invoice_number, s.timestamp, s.total, s.cash_received, s.cash_change,
                   COALESCE(s.payment_method, 'EFECTIVO') as payment_method,
                   COALESCE(s.status, 'COMPLETADA') as status,
                   COALESCE(u.full_name, 'Diego') as cashier, COUNT(si.id) as item_count,
                   COALESCE(c.first_name || ' ' || c.last_name, '') as customer_name,
                   c.document_id as customer_document
            FROM sales s
            LEFT JOIN users u ON s.user_id = u.id
            LEFT JOIN customers c ON s.customer_id = c.id
            LEFT JOIN sale_items si ON s.id = si.sale_id
            LEFT JOIN products p ON si.product_id = p.id
            WHERE 1=1
        """
        params: List[Any] = []

        norm_start = normalize_date_str(start_date)
        norm_end = normalize_date_str(end_date)

        if norm_start:
            sql += " AND date(s.timestamp) >= date(?)"
            params.append(norm_start)

        if norm_end:
            sql += " AND date(s.timestamp) <= date(?)"
            params.append(norm_end)

        if min_price is not None and min_price > 0:
            sql += " AND s.total >= ?"
            params.append(min_price)

        if max_price is not None and max_price > 0:
            sql += " AND s.total <= ?"
            params.append(max_price)

        if category and str(category).strip() and str(category).strip().lower() not in ("todas", "todas las categorías"):
            cursor.execute("SELECT id FROM categories WHERE name = ?", (str(category).strip(),))
            cat_row = cursor.fetchone()
            if cat_row:
                category_id = cat_row["id"]

        if category_id is not None and category_id > 0:
            sql += " AND p.category_id = ?"
            params.append(category_id)

        if query and str(query).strip():
            q_clean = f"%{str(query).strip()}%"
            sql += " AND (s.invoice_number LIKE ? OR u.full_name LIKE ? OR c.first_name LIKE ? OR c.last_name LIKE ? OR c.document_id LIKE ?)"
            params.extend([q_clean, q_clean, q_clean, q_clean, q_clean])

        sql += " GROUP BY s.id ORDER BY s.timestamp DESC"
        cursor.execute(sql, params)
        return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def delete_sale(conn: sqlite3.Connection, sale_id: int) -> bool:
        """Deletes a sale and all its items, reverting product stock.
        Returns True if successful, False if sale was not found.
        """
        cursor = conn.cursor()
        cursor.execute("SELECT id, invoice_number FROM sales WHERE id = ?", (sale_id,))
        sale_row = cursor.fetchone()
        if not sale_row:
            return False

        # Revert product stocks based on sale_items
        cursor.execute(
            "SELECT product_id, quantity, unit_selected FROM sale_items WHERE sale_id = ?",
            (sale_id,)
        )
        items = cursor.fetchall()
        for it in items:
            cursor.execute("SELECT sale_type FROM products WHERE id = ?", (it["product_id"],))
            p = cursor.fetchone()
            if p:
                base_qty = convert_quantity_to_base(it["quantity"], it["unit_selected"], p["sale_type"])
                cursor.execute(
                    "UPDATE products SET stock = stock + ? WHERE id = ?",
                    (base_qty, it["product_id"])
                )

        cursor.execute("DELETE FROM sale_items WHERE sale_id = ?", (sale_id,))
        cursor.execute("DELETE FROM sales WHERE id = ?", (sale_id,))
        conn.commit()
        return True

