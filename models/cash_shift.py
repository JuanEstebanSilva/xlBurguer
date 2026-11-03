"""Cash Shift and Drawer Management model for XL Burguer.
Implements register opening, cash drawer reconciliation (arqueo),
and closing with difference calculation and audit tracking.
"""

from dataclasses import dataclass
from datetime import datetime
import sqlite3
from typing import Any, Dict, List, Optional


@dataclass
class CashShift:
    id: int
    user_id: int
    user_name: str
    opened_at: str
    initial_cash: float
    status: str  # 'ABIERTA' | 'CERRADA'
    closed_at: Optional[str] = None
    cash_sales: float = 0.0
    electronic_sales: float = 0.0
    credit_sales: float = 0.0
    expected_cash: Optional[float] = None
    actual_cash: Optional[float] = None
    difference: Optional[float] = None
    notes: Optional[str] = None

    @property
    def is_open(self) -> bool:
        return self.status == "ABIERTA"

    @property
    def cash_difference(self) -> Optional[float]:
        """Backward-compatible alias for difference."""
        return self.difference


class CashShiftModel:
    """Manages cash register shifts, drawer counts, and closing reports."""

    @staticmethod
    def open_shift(
        conn: sqlite3.Connection,
        user_id: int,
        initial_cash: float,
        notes: str = ""
    ) -> CashShift:
        """Open a new register shift. If a shift is already open for this user, returns it."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.*, COALESCE(u.full_name, u.username) as user_name
            FROM cash_shifts s
            JOIN users u ON s.user_id = u.id
            WHERE s.user_id = ? AND s.status = 'ABIERTA'
            ORDER BY s.id DESC
            LIMIT 1
            """,
            (user_id,)
        )
        existing = cursor.fetchone()
        if existing:
            return CashShift(
                id=existing["id"],
                user_id=existing["user_id"],
                user_name=existing["user_name"],
                opened_at=str(existing["opened_at"]),
                initial_cash=float(existing["initial_cash"]),
                status=existing["status"],
                closed_at=str(existing["closed_at"]) if existing["closed_at"] else None,
                cash_sales=float(existing["cash_sales"]) if "cash_sales" in existing.keys() and existing["cash_sales"] is not None else 0.0,
                electronic_sales=float(existing["electronic_sales"]) if "electronic_sales" in existing.keys() and existing["electronic_sales"] is not None else 0.0,
                credit_sales=float(existing["credit_sales"]) if "credit_sales" in existing.keys() and existing["credit_sales"] is not None else 0.0,
                expected_cash=float(existing["expected_cash"]) if existing["expected_cash"] is not None else None,
                actual_cash=float(existing["actual_cash"]) if existing["actual_cash"] is not None else None,
                difference=float(existing["difference"]) if existing["difference"] is not None else None,
                notes=existing["notes"]
            )

        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        init_val = int(round(float(initial_cash)))

        cursor.execute(
            """
            INSERT INTO cash_shifts (user_id, opened_at, initial_cash, status, notes)
            VALUES (?, ?, ?, 'ABIERTA', ?)
            """,
            (user_id, now_iso, init_val, notes.strip())
        )
        shift_id = cursor.lastrowid

        cursor.execute("SELECT full_name FROM users WHERE id = ?", (user_id,))
        urow = cursor.fetchone()
        u_name = urow["full_name"] if (urow and urow["full_name"]) else "Administrador XL"

        # Audit log
        cursor.execute(
            """
            INSERT INTO audit_logs (user_id, action, table_name, record_id, details)
            VALUES (?, 'SHIFT_OPEN', 'cash_shifts', ?, ?)
            """,
            (user_id, shift_id, f"Apertura de turno con base de ${init_val:,.0f} COP.")
        )
        conn.commit()

        return CashShift(
            id=shift_id,
            user_id=user_id,
            user_name=u_name,
            opened_at=now_iso,
            initial_cash=init_val,
            status="ABIERTA",
            notes=notes.strip()
        )

    @staticmethod
    def get_active_shift(conn: sqlite3.Connection, user_id: Optional[int] = None) -> Optional[CashShift]:
        """Fetch the current open shift for a specific user, or the latest open shift."""
        cursor = conn.cursor()
        if user_id:
            cursor.execute(
                """
                SELECT s.*, COALESCE(u.full_name, u.username) as user_name
                FROM cash_shifts s
                JOIN users u ON s.user_id = u.id
                WHERE s.user_id = ? AND s.status = 'ABIERTA'
                ORDER BY s.id DESC
                LIMIT 1
                """,
                (user_id,)
            )
        else:
            cursor.execute(
                """
                SELECT s.*, COALESCE(u.full_name, u.username) as user_name
                FROM cash_shifts s
                JOIN users u ON s.user_id = u.id
                WHERE s.status = 'ABIERTA'
                ORDER BY s.id DESC
                LIMIT 1
                """
            )
        row = cursor.fetchone()
        if not row:
            return None
        return CashShift(
            id=row["id"],
            user_id=row["user_id"],
            user_name=row["user_name"],
            opened_at=str(row["opened_at"]),
            initial_cash=float(row["initial_cash"]),
            status=row["status"],
            closed_at=str(row["closed_at"]) if row["closed_at"] else None,
            cash_sales=float(row["cash_sales"]) if "cash_sales" in row.keys() and row["cash_sales"] is not None else 0.0,
            electronic_sales=float(row["electronic_sales"]) if "electronic_sales" in row.keys() and row["electronic_sales"] is not None else 0.0,
            credit_sales=float(row["credit_sales"]) if "credit_sales" in row.keys() and row["credit_sales"] is not None else 0.0,
            expected_cash=float(row["expected_cash"]) if row["expected_cash"] is not None else None,
            actual_cash=float(row["actual_cash"]) if row["actual_cash"] is not None else None,
            difference=float(row["difference"]) if row["difference"] is not None else None,
            notes=row["notes"]
        )

    @staticmethod
    def calculate_shift_balance(conn: sqlite3.Connection, shift_id: int) -> Dict[str, Any]:
        """Calculate sales, cash intake, electronic payments, and expected cash for a shift."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cash_shifts WHERE id = ?", (shift_id,))
        shift = cursor.fetchone()
        if not shift:
            raise ValueError(f"Turno con ID {shift_id} no encontrado.")

        opened_at = shift["opened_at"]
        closed_at = shift["closed_at"] or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        initial_cash = float(shift["initial_cash"])

        # Sales during shift
        cursor.execute(
            """
            SELECT
                COALESCE(SUM(s.total), 0) as total_sold,
                COALESCE(SUM(CASE WHEN UPPER(s.payment_method) = 'EFECTIVO' THEN s.total ELSE 0 END), 0) as cash_sold,
                COALESCE(SUM(CASE WHEN UPPER(s.payment_method) NOT IN ('EFECTIVO', 'FIADO') THEN s.total ELSE 0 END), 0) as electronic_sold,
                COALESCE(SUM(CASE WHEN UPPER(s.payment_method) = 'FIADO' THEN s.total ELSE 0 END), 0) as fiado_sold,
                COUNT(s.id) as sales_count
            FROM sales s
            WHERE s.timestamp >= ? AND s.timestamp <= ?
              AND COALESCE(s.status, 'COMPLETADA') != 'ANULADA'
              AND s.id IN (SELECT DISTINCT sale_id FROM sale_items)
            """,
            (opened_at, closed_at)
        )
        sales_row = cursor.fetchone()
        cash_sales = float(sales_row["cash_sold"]) if sales_row else 0.0
        electronic_sales = float(sales_row["electronic_sold"]) if sales_row else 0.0
        fiado_sales = float(sales_row["fiado_sold"]) if sales_row else 0.0
        total_sales = float(sales_row["total_sold"]) if sales_row else 0.0
        sales_count = int(sales_row["sales_count"]) if sales_row else 0

        expected_cash = initial_cash + cash_sales

        return {
            "shift_id": shift_id,
            "opened_at": opened_at,
            "closed_at": closed_at,
            "initial_cash": initial_cash,
            "cash_sales": cash_sales,
            "electronic_sales": electronic_sales,
            "fiado_sales": fiado_sales,
            "total_sales": total_sales,
            "sales_count": sales_count,
            "expected_cash": expected_cash
        }

    @staticmethod
    def close_shift(
        conn: sqlite3.Connection,
        shift_id: int,
        actual_cash: float,
        notes: str = ""
    ) -> CashShift:
        """Close an active shift with cashier cash count (arqueo) and difference calculation."""
        balance = CashShiftModel.calculate_shift_balance(conn, shift_id)
        expected_cash = balance["expected_cash"]
        actual_val = int(round(float(actual_cash)))
        diff = actual_val - expected_cash

        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE cash_shifts
            SET closed_at = ?,
                cash_sales = ?,
                electronic_sales = ?,
                credit_sales = ?,
                expected_cash = ?,
                actual_cash = ?,
                difference = ?,
                status = 'CERRADA',
                notes = CASE WHEN notes IS NOT NULL AND notes != '' THEN notes || ' | ' || ? ELSE ? END
            WHERE id = ?
            """,
            (now_iso, balance["cash_sales"], balance["electronic_sales"], balance["fiado_sales"],
             expected_cash, actual_val, diff, notes.strip(), notes.strip(), shift_id)
        )

        cursor.execute("SELECT user_id FROM cash_shifts WHERE id = ?", (shift_id,))
        srow = cursor.fetchone()
        u_id = srow["user_id"] if srow else None

        # Audit log
        diff_str = f"Sobrante: +${diff:,.0f}" if diff > 0 else (f"Faltante: -${abs(diff):,.0f}" if diff < 0 else "Cuadre exacto ($0)")
        cursor.execute(
            """
            INSERT INTO audit_logs (user_id, action, table_name, record_id, details)
            VALUES (?, 'SHIFT_CLOSE', 'cash_shifts', ?, ?)
            """,
            (u_id, shift_id,
             f"Cierre de turno. Esperado: ${expected_cash:,.0f}, Arqueo físico: ${actual_val:,.0f}. {diff_str}. {notes}".strip())
        )
        conn.commit()

        cursor.execute(
            """
            SELECT s.*, COALESCE(u.full_name, u.username) as user_name
            FROM cash_shifts s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = ?
            """,
            (shift_id,)
        )
        updated = cursor.fetchone()
        return CashShift(
            id=updated["id"],
            user_id=updated["user_id"],
            user_name=updated["user_name"],
            opened_at=str(updated["opened_at"]),
            initial_cash=float(updated["initial_cash"]),
            status=updated["status"],
            closed_at=str(updated["closed_at"]),
            cash_sales=float(updated["cash_sales"]),
            electronic_sales=float(updated["electronic_sales"]),
            credit_sales=float(updated["credit_sales"]),
            expected_cash=float(updated["expected_cash"]),
            actual_cash=float(updated["actual_cash"]),
            difference=float(updated["difference"]),
            notes=updated["notes"]
        )

    @staticmethod
    def get_shift_history(conn: sqlite3.Connection, limit: int = 30) -> List[Dict[str, Any]]:
        """Fetch list of recent shifts for supervisor/admin review."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.*, COALESCE(u.full_name, u.username) as user_name
            FROM cash_shifts s
            JOIN users u ON s.user_id = u.id
            ORDER BY s.id DESC
            LIMIT ?
            """,
            (limit,)
        )
        return [dict(r) for r in cursor.fetchall()]
