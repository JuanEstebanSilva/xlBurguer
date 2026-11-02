"""Customer Data Model and Persistence for XL Burguer.
Manages customer identification by national ID (Cédula de Ciudadanía / NIT),
fast cashier registration, customer directory management, and purchase history.
"""

import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Customer:
    id: int
    document_id: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    created_at: Optional[str] = None
    customer_type: str = "PERSONA"
    discount_percent: float = 0.0
    debt_balance: float = 0.0

    @property
    def is_company(self) -> bool:
        return (self.customer_type or "").upper() == "EMPRESA"

    @property
    def full_name(self) -> str:
        if self.is_company:
            if self.last_name and self.last_name.strip():
                return f"{self.first_name.strip()} ({self.last_name.strip()})"
            return self.first_name.strip()
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display_label(self) -> str:
        prefix = "NIT" if self.is_company else "CC"
        return f"{self.full_name} ({prefix} {self.document_id})"

    @property
    def phone_display(self) -> str:
        return self.phone if self.phone and self.phone.strip() else "Sin registrar"


class CustomerModel:
    """Data Access Object for Customer entities, Company Quotas, and Purchase History."""

    @staticmethod
    def get_by_document(conn: sqlite3.Connection, document_id: str) -> Optional[Customer]:
        """Fetch customer by exact document/cédula/NIT."""
        doc_clean = str(document_id).strip()
        if not doc_clean:
            return None
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, document_id, first_name, last_name, phone, customer_type, discount_percent, created_at,
                   COALESCE(debt_balance, 0.0) as debt_balance
            FROM customers
            WHERE document_id = ? OR phone = ?
            LIMIT 1
            """,
            (doc_clean, doc_clean)
        )
        row = cursor.fetchone()
        if not row:
            return None
        ctype = row["customer_type"] if "customer_type" in row.keys() and row["customer_type"] else "PERSONA"
        disc = float(row["discount_percent"]) if "discount_percent" in row.keys() and row["discount_percent"] is not None else 0.0
        debt = float(row["debt_balance"]) if "debt_balance" in row.keys() and row["debt_balance"] is not None else 0.0
        return Customer(
            id=row["id"],
            document_id=row["document_id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            phone=row["phone"],
            created_at=str(row["created_at"]) if row["created_at"] else None,
            customer_type=ctype,
            discount_percent=disc,
            debt_balance=debt
        )

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, customer_id: int) -> Optional[Customer]:
        """Fetch customer by database primary key."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, document_id, first_name, last_name, phone, customer_type, discount_percent, created_at,
                   COALESCE(debt_balance, 0.0) as debt_balance
            FROM customers
            WHERE id = ?
            """,
            (customer_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        ctype = row["customer_type"] if "customer_type" in row.keys() and row["customer_type"] else "PERSONA"
        disc = float(row["discount_percent"]) if "discount_percent" in row.keys() and row["discount_percent"] is not None else 0.0
        debt = float(row["debt_balance"]) if "debt_balance" in row.keys() and row["debt_balance"] is not None else 0.0
        return Customer(
            id=row["id"],
            document_id=row["document_id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            phone=row["phone"],
            created_at=str(row["created_at"]) if row["created_at"] else None,
            customer_type=ctype,
            discount_percent=disc,
            debt_balance=debt
        )

    @staticmethod
    def create(
        conn: sqlite3.Connection,
        document_id: str,
        first_name: str,
        last_name: str,
        phone: Optional[str] = None,
        customer_type: str = "PERSONA",
        discount_percent: float = 0.0
    ) -> Customer:
        """Register a new customer/company and return instantiated Customer dataclass."""
        doc_clean = str(document_id).strip()
        first_clean = str(first_name).strip()
        last_clean = str(last_name).strip()
        phone_clean = str(phone).strip() if phone else None
        ctype_clean = (customer_type or "PERSONA").strip().upper()
        if ctype_clean not in ("PERSONA", "EMPRESA"):
            ctype_clean = "PERSONA"
        disc_clean = max(0.0, min(100.0, float(discount_percent or 0.0)))

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO customers (document_id, first_name, last_name, phone, customer_type, discount_percent)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (doc_clean, first_clean, last_clean, phone_clean, ctype_clean, disc_clean)
        )
        conn.commit()
        customer_id = cursor.lastrowid
        return Customer(
            id=customer_id,
            document_id=doc_clean,
            first_name=first_clean,
            last_name=last_clean,
            phone=phone_clean,
            customer_type=ctype_clean,
            discount_percent=disc_clean
        )

    @staticmethod
    def update(
        conn: sqlite3.Connection,
        customer_id: int,
        first_name: str,
        last_name: str,
        phone: Optional[str] = None,
        document_id: Optional[str] = None,
        customer_type: Optional[str] = None,
        discount_percent: Optional[float] = None
    ) -> None:
        """Update existing customer details."""
        cursor = conn.cursor()
        first_clean = str(first_name).strip()
        last_clean = str(last_name).strip()
        phone_clean = str(phone).strip() if phone else None

        fields = ["first_name = ?", "last_name = ?", "phone = ?"]
        params = [first_clean, last_clean, phone_clean]

        if document_id is not None:
            fields.append("document_id = ?")
            params.append(str(document_id).strip())

        if customer_type is not None:
            ctype_clean = str(customer_type).strip().upper()
            if ctype_clean in ("PERSONA", "EMPRESA"):
                fields.append("customer_type = ?")
                params.append(ctype_clean)

        if discount_percent is not None:
            disc_clean = max(0.0, min(100.0, float(discount_percent)))
            fields.append("discount_percent = ?")
            params.append(disc_clean)

        params.append(customer_id)
        sql = f"UPDATE customers SET {', '.join(fields)} WHERE id = ?"
        cursor.execute(sql, tuple(params))
        conn.commit()

    @staticmethod
    def search(
        conn: sqlite3.Connection,
        query: str,
        limit: int = 10,
        customer_type: Optional[str] = None
    ) -> List[Customer]:
        """Search customers by document, first name, or last name, optionally filtered by type."""
        q = query.strip()
        if not q:
            return []
        from database.connection import normalize_text
        norm_q = f"%{normalize_text(q)}%"
        cursor = conn.cursor()

        if customer_type:
            cursor.execute(
                """
                SELECT id, document_id, first_name, last_name, phone, customer_type, discount_percent, created_at
                FROM customers
                WHERE (document_id LIKE ? OR NORMALIZE_TEXT(first_name) LIKE ? OR NORMALIZE_TEXT(last_name) LIKE ? OR phone LIKE ?)
                  AND customer_type = ?
                LIMIT ?
                """,
                (f"%{q}%", norm_q, norm_q, f"%{q}%", customer_type.upper(), limit)
            )
        else:
            cursor.execute(
                """
                SELECT id, document_id, first_name, last_name, phone, customer_type, discount_percent, created_at
                FROM customers
                WHERE document_id LIKE ? OR NORMALIZE_TEXT(first_name) LIKE ? OR NORMALIZE_TEXT(last_name) LIKE ? OR phone LIKE ?
                LIMIT ?
                """,
                (f"%{q}%", norm_q, norm_q, f"%{q}%", limit)
            )

        rows = cursor.fetchall()
        return [
            Customer(
                id=r["id"],
                document_id=r["document_id"],
                first_name=r["first_name"],
                last_name=r["last_name"],
                phone=r["phone"],
                created_at=str(r["created_at"]) if r["created_at"] else None,
                customer_type=r["customer_type"] if "customer_type" in r.keys() and r["customer_type"] else "PERSONA",
                discount_percent=float(r["discount_percent"]) if "discount_percent" in r.keys() and r["discount_percent"] is not None else 0.0
            )
            for r in rows
        ]

    @staticmethod
    def get_all_with_stats(
        conn: sqlite3.Connection,
        query: str = "",
        customer_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch all customers annotated with purchase count, total spent, and last purchase date."""
        from database.connection import normalize_text
        q = query.strip()
        cursor = conn.cursor()

        where_clauses = []
        params = []

        if q:
            norm_q = f"%{normalize_text(q)}%"
            doc_q = f"%{q}%"
            where_clauses.append(
                "(c.document_id LIKE ? OR NORMALIZE_TEXT(c.first_name) LIKE ? OR NORMALIZE_TEXT(c.last_name) LIKE ? OR COALESCE(c.phone, '') LIKE ?)"
            )
            params.extend([doc_q, norm_q, norm_q, doc_q])

        if customer_type:
            where_clauses.append("c.customer_type = ?")
            params.append(customer_type.upper())

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        sql = f"""
            SELECT 
                c.id,
                c.document_id,
                c.first_name,
                c.last_name,
                c.phone,
                COALESCE(c.customer_type, 'PERSONA') AS customer_type,
                COALESCE(c.discount_percent, 0.0) AS discount_percent,
                c.created_at,
                COUNT(s.id) AS total_purchases,
                COALESCE(SUM(s.total), 0.0) AS total_spent,
                MAX(s.timestamp) AS last_purchase_date,
                SUM(CASE WHEN s.payment_method = 'FIADO' THEN 1 ELSE 0 END) AS fiado_purchases,
                COALESCE(SUM(CASE WHEN s.payment_method = 'FIADO' THEN s.total ELSE 0.0 END), 0.0) AS fiado_spent
            FROM customers c
            LEFT JOIN sales s ON s.customer_id = c.id
            {where_sql}
            GROUP BY c.id
            ORDER BY total_spent DESC, total_purchases DESC, c.id DESC
        """
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            ctype = r["customer_type"] or "PERSONA"
            is_comp = (ctype == "EMPRESA")
            if is_comp:
                if r["last_name"] and r["last_name"].strip():
                    full_name = f"{r['first_name'].strip()} ({r['last_name'].strip()})"
                else:
                    full_name = r["first_name"].strip()
            else:
                full_name = f"{r['first_name']} {r['last_name']}".strip()

            result.append({
                "id": r["id"],
                "document_id": r["document_id"],
                "first_name": r["first_name"],
                "last_name": r["last_name"],
                "full_name": full_name,
                "phone": r["phone"] or "",
                "customer_type": ctype,
                "is_company": is_comp,
                "discount_percent": float(r["discount_percent"]) if "discount_percent" in r.keys() and r["discount_percent"] is not None else 0.0,
                "created_at": str(r["created_at"]) if r["created_at"] else "",
                "total_purchases": int(r["total_purchases"]),
                "total_spent": float(r["total_spent"]),
                "last_purchase_date": str(r["last_purchase_date"]) if r["last_purchase_date"] else None,
                "fiado_purchases": int(r["fiado_purchases"]) if "fiado_purchases" in r.keys() and r["fiado_purchases"] else 0,
                "fiado_spent": float(r["fiado_spent"]) if "fiado_spent" in r.keys() and r["fiado_spent"] else 0.0,
            })
        return result

    @staticmethod
    def get_customer_purchases(
        conn: sqlite3.Connection,
        customer_id: int,
        only_fiados: bool = False
    ) -> List[Dict[str, Any]]:
        """Retrieve full list of sales completed by a specific customer."""
        cursor = conn.cursor()
        fiado_filter = "AND s.payment_method = 'FIADO'" if only_fiados else ""
        cursor.execute(
            f"""
            SELECT 
                s.id,
                s.invoice_number,
                s.timestamp,
                s.subtotal,
                s.total,
                s.cash_received,
                s.cash_change,
                s.payment_method,
                s.user_id,
                COALESCE(u.full_name, u.username, 'Diego') AS cashier_name,
                COUNT(si.id) AS item_count
            FROM sales s
            LEFT JOIN users u ON s.user_id = u.id
            LEFT JOIN sale_items si ON si.sale_id = s.id
            WHERE s.customer_id = ? {fiado_filter}
            GROUP BY s.id
            ORDER BY s.timestamp DESC, s.id DESC
            """,
            (customer_id,)
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r["id"],
                "invoice_number": r["invoice_number"],
                "timestamp": str(r["timestamp"]),
                "subtotal": float(r["subtotal"]),
                "total": float(r["total"]),
                "cash_received": float(r["cash_received"]),
                "cash_change": float(r["cash_change"]),
                "payment_method": r["payment_method"],
                "cashier_name": r["cashier_name"],
                "item_count": int(r["item_count"])
            })
        return result

    @staticmethod
    def get_sale_items(conn: sqlite3.Connection, sale_id: int) -> List[Dict[str, Any]]:
        """Retrieve itemized product lines for a given sale."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                si.id,
                si.product_id,
                p.name AS product_name,
                p.sale_type,
                si.quantity,
                si.unit_selected,
                si.unit_price,
                si.total_price,
                si.fiado_remaining
            FROM sale_items si
            JOIN products p ON si.product_id = p.id
            WHERE si.sale_id = ?
            ORDER BY si.id ASC
            """,
            (sale_id,)
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r["id"],
                "product_id": r["product_id"],
                "product_name": r["product_name"],
                "sale_type": r["sale_type"],
                "quantity": float(r["quantity"]),
                "unit_selected": r["unit_selected"],
                "unit_price": float(r["unit_price"]),
                "total_price": float(r["total_price"]),
                "fiado_remaining": float(r["fiado_remaining"]) if r["fiado_remaining"] is not None else None
            })
        return result

    @staticmethod
    def get_summary_metrics(conn: sqlite3.Connection, customer_type: Optional[str] = None) -> Dict[str, Any]:
        """Calculate high-level KPIs for the clients/companies module."""
        cursor = conn.cursor()

        type_filter = "WHERE customer_type = ?" if customer_type else ""
        type_params = (customer_type.upper(),) if customer_type else ()

        cursor.execute(f"SELECT COUNT(*) FROM customers {type_filter}", type_params)
        total_customers = cursor.fetchone()[0]

        if customer_type:
            cursor.execute(
                """
                SELECT COUNT(DISTINCT s.customer_id) 
                FROM sales s
                JOIN customers c ON s.customer_id = c.id
                WHERE c.customer_type = ?
                """,
                type_params
            )
            active_buyers = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT COALESCE(SUM(s.total), 0.0), COUNT(s.id)
                FROM sales s
                JOIN customers c ON s.customer_id = c.id
                WHERE c.customer_type = ?
                """,
                type_params
            )
            r = cursor.fetchone()
            total_spent_customers = float(r[0] or 0.0)
            total_sales_customers = int(r[1] or 0)
        else:
            cursor.execute("SELECT COUNT(DISTINCT customer_id) FROM sales WHERE customer_id IS NOT NULL")
            active_buyers = cursor.fetchone()[0]

            cursor.execute("SELECT COALESCE(SUM(total), 0.0), COUNT(*) FROM sales WHERE customer_id IS NOT NULL")
            r = cursor.fetchone()
            total_spent_customers = float(r[0] or 0.0)
            total_sales_customers = int(r[1] or 0)

        avg_ticket = (total_spent_customers / total_sales_customers) if total_sales_customers > 0 else 0.0

        return {
            "total_customers": total_customers,
            "active_buyers": active_buyers,
            "total_spent_customers": total_spent_customers,
            "total_sales_customers": total_sales_customers,
            "avg_ticket": avg_ticket
        }

    @staticmethod
    def delete(conn: sqlite3.Connection, customer_id: int) -> None:
        """Delete customer record if they have no associated sales."""
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sales WHERE customer_id = ?", (customer_id,))
        if cursor.fetchone()[0] > 0:
            raise sqlite3.IntegrityError("El cliente tiene ventas registradas y no puede ser eliminado.")
        # Delete any associated quotas first
        cursor.execute("DELETE FROM company_product_quotas WHERE customer_id = ?", (customer_id,))
        cursor.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        conn.commit()

    # ──────────────────────────────────────────────────────────────────────────
    # COMPANY PRODUCT QUOTAS & FIADOS MANAGEMENT
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def get_company_quotas(conn: sqlite3.Connection, customer_id: int) -> List[Dict[str, Any]]:
        """Retrieve all product agreements and quota balances for an enterprise."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                cpq.id,
                cpq.customer_id,
                cpq.product_id,
                p.name AS product_name,
                cat.name AS category_name,
                p.sale_type,
                p.unit_measure,
                p.price_base,
                cpq.quota_quantity,
                cpq.unit,
                cpq.consumed_quantity,
                cpq.remaining_quantity,
                cpq.notes,
                cpq.updated_at
            FROM company_product_quotas cpq
            JOIN products p ON cpq.product_id = p.id
            LEFT JOIN categories cat ON p.category_id = cat.id
            WHERE cpq.customer_id = ?
            ORDER BY p.name ASC
            """,
            (customer_id,)
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r["id"],
                "customer_id": r["customer_id"],
                "product_id": r["product_id"],
                "product_name": r["product_name"],
                "category_name": r["category_name"] or "General",
                "sale_type": r["sale_type"],
                "unit_measure": r["unit_measure"],
                "price_base": float(r["price_base"]),
                "quota_quantity": float(r["quota_quantity"]),
                "unit": r["unit"] or "kg",
                "consumed_quantity": float(r["consumed_quantity"]),
                "remaining_quantity": float(r["remaining_quantity"]),
                "notes": r["notes"] or "",
                "updated_at": str(r["updated_at"]) if r["updated_at"] else ""
            })
        return result

    @staticmethod
    def get_company_quota_by_product(
        conn: sqlite3.Connection,
        customer_id: int,
        product_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get single company quota for a specific product if it exists."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, customer_id, product_id, quota_quantity, unit, consumed_quantity, remaining_quantity, notes
            FROM company_product_quotas
            WHERE customer_id = ? AND product_id = ?
            """,
            (customer_id, product_id)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "customer_id": row["customer_id"],
            "product_id": row["product_id"],
            "quota_quantity": float(row["quota_quantity"]),
            "unit": row["unit"] or "kg",
            "consumed_quantity": float(row["consumed_quantity"]),
            "remaining_quantity": float(row["remaining_quantity"]),
            "notes": row["notes"] or ""
        }

    @staticmethod
    def set_company_quota(
        conn: sqlite3.Connection,
        customer_id: int,
        product_id: int,
        quota_quantity: float,
        unit: str = "kg",
        remaining_quantity: Optional[float] = None,
        notes: str = "",
        remaining: Optional[float] = None,
        **kwargs
    ) -> int:
        """Create or update a company product quota agreement."""
        cursor = conn.cursor()
        quota_qty = float(quota_quantity)
        if remaining is not None and remaining_quantity is None:
            remaining_quantity = remaining
        rem_qty = float(remaining_quantity) if remaining_quantity is not None else quota_qty

        notes_str = str(notes or "").strip()

        cursor.execute(
            """
            INSERT INTO company_product_quotas (customer_id, product_id, quota_quantity, unit, consumed_quantity, remaining_quantity, notes, updated_at)
            VALUES (?, ?, ?, ?, 0.0, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(customer_id, product_id) DO UPDATE SET
                quota_quantity = excluded.quota_quantity,
                unit = excluded.unit,
                remaining_quantity = excluded.remaining_quantity,
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
            """,
            (customer_id, product_id, quota_qty, unit, rem_qty, notes_str)
        )
        conn.commit()
        return cursor.lastrowid

    @staticmethod
    def update_company_quota_remaining(
        conn: sqlite3.Connection,
        quota_id: Optional[int] = None,
        new_remaining: float = 0.0,
        new_quota: Optional[float] = None,
        notes: Optional[str] = None,
        customer_id: Optional[int] = None,
        product_id: Optional[int] = None
    ) -> bool:
        """Directly adjust remaining balance ('le queda tanto de este producto') or quota quantity.
        Supports lookup either by quota_id or by (customer_id, product_id).
        """
        cursor = conn.cursor()
        target_id = quota_id
        if target_id is None:
            if customer_id is None or product_id is None:
                raise ValueError("Must provide either quota_id or (customer_id, product_id)")
            cursor.execute(
                "SELECT id FROM company_product_quotas WHERE customer_id = ? AND product_id = ?",
                (customer_id, product_id)
            )
            row = cursor.fetchone()
            if not row:
                return False
            target_id = row["id"]

        cursor.execute(
            "SELECT quota_quantity FROM company_product_quotas WHERE id = ?",
            (target_id,)
        )
        curr_row = cursor.fetchone()
        curr_quota = float(new_quota) if new_quota is not None else (float(curr_row["quota_quantity"]) if curr_row else float(new_remaining))
        consumed = max(0.0, curr_quota - float(new_remaining))

        fields = [
            "remaining_quantity = ?",
            "consumed_quantity = ?",
            "updated_at = CURRENT_TIMESTAMP"
        ]
        params = [float(new_remaining), float(consumed)]

        if new_quota is not None:
            fields.append("quota_quantity = ?")
            params.append(float(new_quota))

        if notes is not None:
            fields.append("notes = ?")
            params.append(str(notes).strip())

        params.append(target_id)
        sql = f"UPDATE company_product_quotas SET {', '.join(fields)} WHERE id = ?"
        cursor.execute(sql, tuple(params))
        conn.commit()
        return True

    @staticmethod
    def delete_company_quota(conn: sqlite3.Connection, quota_id: int) -> None:
        """Delete a quota agreement row."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM company_product_quotas WHERE id = ?", (quota_id,))
        conn.commit()

    @staticmethod
    def consume_company_quota(
        conn: sqlite3.Connection,
        customer_id: int,
        product_id: int,
        quantity: float,
        unit: str
    ) -> float:
        """Deduct sold quantity from company quota and return remaining balance.
        If no agreement exists, creates one dynamically to track the fiado delivery.
        """
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, quota_quantity, unit, consumed_quantity, remaining_quantity
            FROM company_product_quotas
            WHERE customer_id = ? AND product_id = ?
            """,
            (customer_id, product_id)
        )
        row = cursor.fetchone()

        sold_qty = float(quantity)
        sold_unit = (unit or "kg").lower()

        if row:
            quota_id = row["id"]
            quota_unit = (row["unit"] or "kg").lower()
            cur_consumed = float(row["consumed_quantity"])
            cur_remaining = float(row["remaining_quantity"])

            # Normalize units if one is g and other is kg
            normalized_qty = sold_qty
            if quota_unit == "kg" and sold_unit == "g":
                normalized_qty = sold_qty / 1000.0
            elif quota_unit == "g" and sold_unit == "kg":
                normalized_qty = sold_qty * 1000.0
            elif quota_unit == "kg" and sold_unit == "lb":
                normalized_qty = sold_qty * 0.5
            elif quota_unit == "lb" and sold_unit == "kg":
                normalized_qty = sold_qty * 2.0

            new_consumed = cur_consumed + normalized_qty
            new_remaining = max(0.0, cur_remaining - normalized_qty)

            cursor.execute(
                """
                UPDATE company_product_quotas
                SET consumed_quantity = ?, remaining_quantity = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_consumed, new_remaining, quota_id)
            )
            return new_remaining
        else:
            # Dynamic registration of product fiado for this company
            cursor.execute(
                """
                INSERT INTO company_product_quotas
                (customer_id, product_id, quota_quantity, unit, consumed_quantity, remaining_quantity, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, 0.0, 'Fiado directo en caja', CURRENT_TIMESTAMP)
                """,
                (customer_id, product_id, sold_qty, sold_unit, sold_qty)
            )
            return 0.0

    @staticmethod
    def settle_company_quotas(
        conn: sqlite3.Connection,
        customer_id: int,
        reset_for_new_period: bool = True
    ) -> None:
        """Reset or settle company quotas after monthly payment."""
        cursor = conn.cursor()
        if reset_for_new_period:
            cursor.execute(
                """
                UPDATE company_product_quotas
                SET consumed_quantity = 0.0,
                    remaining_quantity = quota_quantity,
                    updated_at = CURRENT_TIMESTAMP
                WHERE customer_id = ?
                """,
                (customer_id,)
            )
        else:
            cursor.execute(
                """
                UPDATE company_product_quotas
                SET consumed_quantity = 0.0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE customer_id = ?
                """,
                (customer_id,)
            )
        conn.commit()

    @staticmethod
    def get_company_fiados_summary(conn: sqlite3.Connection, customer_id: int) -> Dict[str, Any]:
        """Aggregate summary of fiado products, delivered kg, remaining kg, and monetary balance."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                COUNT(*) as total_quotas,
                COALESCE(SUM(quota_quantity), 0.0) as total_quota_qty,
                COALESCE(SUM(consumed_quantity), 0.0) as total_consumed_qty,
                COALESCE(SUM(remaining_quantity), 0.0) as total_remaining_qty
            FROM company_product_quotas
            WHERE customer_id = ?
            """,
            (customer_id,)
        )
        q_row = cursor.fetchone()

        cursor.execute(
            """
            SELECT 
                COUNT(*) as count_fiado_sales,
                COALESCE(SUM(total), 0.0) as total_fiado_amount,
                MAX(timestamp) as last_fiado_date
            FROM sales
            WHERE customer_id = ? AND payment_method = 'FIADO'
            """,
            (customer_id,)
        )
        s_row = cursor.fetchone()

        return {
            "total_quotas": int(q_row["total_quotas"]) if q_row else 0,
            "total_quota_qty": float(q_row["total_quota_qty"]) if q_row else 0.0,
            "total_consumed_qty": float(q_row["total_consumed_qty"]) if q_row else 0.0,
            "total_remaining_qty": float(q_row["total_remaining_qty"]) if q_row else 0.0,
            "count_fiado_sales": int(s_row["count_fiado_sales"]) if s_row else 0,
            "total_fiado_amount": float(s_row["total_fiado_amount"]) if s_row else 0.0,
            "last_fiado_date": str(s_row["last_fiado_date"]) if s_row and s_row["last_fiado_date"] else None
        }

    @staticmethod
    def restore_company_quota(
        conn: sqlite3.Connection,
        customer_id: int,
        product_id: int,
        quantity: float,
        unit: str
    ) -> None:
        """Revert quota deduction when a fiado sale is voided."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, quota_quantity, consumed_quantity, remaining_quantity, unit
            FROM company_product_quotas
            WHERE customer_id = ? AND product_id = ?
            LIMIT 1
            """,
            (customer_id, product_id)
        )
        row = cursor.fetchone()
        if not row:
            return

        quota_id = row["id"]
        quota_unit = (row["unit"] or "kg").lower()
        sold_qty = float(quantity)
        sold_unit = (unit or "kg").lower()

        normalized_qty = sold_qty
        if quota_unit == "kg" and sold_unit == "g":
            normalized_qty = sold_qty / 1000.0
        elif quota_unit == "g" and sold_unit == "kg":
            normalized_qty = sold_qty * 1000.0
        elif quota_unit == "kg" and sold_unit == "lb":
            normalized_qty = sold_qty * 0.5
        elif quota_unit == "lb" and sold_unit == "kg":
            normalized_qty = sold_qty * 2.0

        cur_consumed = float(row["consumed_quantity"])
        cur_remaining = float(row["remaining_quantity"])
        max_quota = float(row["quota_quantity"])

        new_consumed = max(0.0, cur_consumed - normalized_qty)
        new_remaining = min(max_quota, cur_remaining + normalized_qty) if max_quota > 0 else (cur_remaining + normalized_qty)

        cursor.execute(
            """
            UPDATE company_product_quotas
            SET consumed_quantity = ?, remaining_quantity = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_consumed, new_remaining, quota_id)
        )

    @staticmethod
    def add_debt(conn: sqlite3.Connection, customer_id: int, amount: float) -> float:
        """Increment customer's debt balance on fiado purchase."""
        cursor = conn.cursor()
        amt = int(round(float(amount)))
        cursor.execute(
            "UPDATE customers SET debt_balance = COALESCE(debt_balance, 0.0) + ? WHERE id = ?",
            (amt, customer_id)
        )
        cursor.execute("SELECT debt_balance FROM customers WHERE id = ?", (customer_id,))
        row = cursor.fetchone()
        return float(row["debt_balance"]) if row and row["debt_balance"] is not None else 0.0

    @staticmethod
    def reduce_debt(conn: sqlite3.Connection, customer_id: int, amount: float) -> float:
        """Reduce customer's debt balance on void or debt payment."""
        cursor = conn.cursor()
        amt = int(round(float(amount)))
        cursor.execute(
            "UPDATE customers SET debt_balance = MAX(0.0, COALESCE(debt_balance, 0.0) - ?) WHERE id = ?",
            (amt, customer_id)
        )
        cursor.execute("SELECT debt_balance FROM customers WHERE id = ?", (customer_id,))
        row = cursor.fetchone()
        return float(row["debt_balance"]) if row and row["debt_balance"] is not None else 0.0

    @staticmethod
    def register_debt_payment(
        conn: sqlite3.Connection,
        customer_id: int,
        amount: float,
        payment_method: str = "EFECTIVO",
        notes: str = "",
        user_id: Optional[int] = None
    ) -> float:
        """Register a payment towards outstanding customer debt and log to audit_logs."""
        if amount <= 0:
            raise ValueError("El monto del abono debe ser mayor a cero.")
        cursor = conn.cursor()
        new_balance = CustomerModel.reduce_debt(conn, customer_id, amount)
        cursor.execute(
            """
            INSERT INTO audit_logs (user_id, action, table_name, record_id, details)
            VALUES (?, 'DEBT_PAYMENT', 'customers', ?, ?)
            """,
            (user_id, customer_id, f"Abono de ${int(round(amount)):,.0f} ({payment_method}). Saldo restante: ${int(round(new_balance)):,.0f}. {notes}".strip())
        )
        conn.commit()
        return new_balance

    @staticmethod
    def get_total_portfolio_debt(conn: sqlite3.Connection) -> float:
        """Calculate total outstanding debt across all customers in the portfolio."""
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(debt_balance), 0.0) as total_debt FROM customers")
        row = cursor.fetchone()
        return float(row["total_debt"]) if row and row["total_debt"] is not None else 0.0

    @staticmethod
    def get_customers_with_debt(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        """Fetch list of customers with positive debt balance."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, document_id, first_name, last_name, customer_type, phone, debt_balance
            FROM customers
            WHERE debt_balance > 0
            ORDER BY debt_balance DESC
            """
        )
        return [dict(r) for r in cursor.fetchall()]

