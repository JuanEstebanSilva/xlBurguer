"""User model and authentication service for XL Burguer.
Implements PBKDF2-HMAC-SHA256 password hashing with 600,000 iterations (OWASP Standard),
lockout protection after repeated failed attempts, dynamic rehash of legacy hashes,
single-administrator invariant, and strict role validation.
"""

from datetime import datetime, timedelta
import hashlib
import hmac
import logging
import os
import sqlite3
from dataclasses import dataclass
from typing import Optional, Tuple

OWASP_PBKDF2_ITERATIONS = 600000


@dataclass
class User:
    id: int
    username: str
    password_hash: str
    full_name: str
    role: str
    document_id: str = ""
    phone: str = ""
    email: str = ""
    is_active: int = 1
    failed_attempts: int = 0
    locked_until: Optional[str] = None

    @property
    def is_admin(self) -> bool:
        return bool(self.role and self.role.upper() in ("ADMIN", "ADMINISTRADOR"))

    @property
    def active(self) -> bool:
        return bool(self.is_active)


def _row_to_user(row: sqlite3.Row) -> User:
    """Helper to convert SQLite row to User with backward compatibility for extra columns."""
    keys = row.keys()
    return User(
        id=row["id"],
        username=row["username"],
        password_hash=row["password_hash"],
        full_name=row["full_name"],
        role="ADMIN" if row["role"].upper() in ("ADMIN", "ADMINISTRADOR") else "CASHIER",
        document_id=row["document_id"] if "document_id" in keys and row["document_id"] else "",
        phone=row["phone"] if "phone" in keys and row["phone"] else "",
        email=row["email"] if "email" in keys and row["email"] else "",
        is_active=row["is_active"] if "is_active" in keys and row["is_active"] is not None else 1,
        failed_attempts=row["failed_attempts"] if "failed_attempts" in keys and row["failed_attempts"] is not None else 0,
        locked_until=row["locked_until"] if "locked_until" in keys else None
    )


def hash_password(password: str, salt: Optional[bytes] = None, iterations: int = OWASP_PBKDF2_ITERATIONS) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with 600,000 iterations (OWASP standard)."""
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        iterations
    )
    return f"{salt.hex()}${iterations}${key.hex()}"


def verify_password_detail(stored_password: str, provided_password: str) -> Tuple[bool, bool]:
    """Verify password. Returns (is_valid, needs_rehash).
    Rejects plaintext passwords completely (no plaintext fallback allowed).
    """
    try:
        if not stored_password or "$" not in stored_password:
            # Plain text passwords in database are rejected for security
            return False, False

        parts = stored_password.split('$')
        if len(parts) == 2:
            # Legacy format: salt$key with 100,000 iterations
            salt_hex, key_hex = parts
            iterations = 100000
        elif len(parts) == 3:
            # Modern format: salt$iterations$key
            salt_hex, iter_str, key_hex = parts
            iterations = int(iter_str)
        else:
            return False, False

        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
        actual_key = hashlib.pbkdf2_hmac(
            'sha256',
            provided_password.encode('utf-8'),
            salt,
            iterations
        )
        is_valid = hmac.compare_digest(expected_key, actual_key)
        needs_rehash = is_valid and (iterations < OWASP_PBKDF2_ITERATIONS or len(parts) == 2)
        return is_valid, needs_rehash
    except Exception:
        return False, False


def verify_password(stored_password: str, provided_password: str) -> bool:
    """Verify stored password hash against provided password returning boolean."""
    is_valid, _ = verify_password_detail(stored_password, provided_password)
    return is_valid


class UserModel:
    """Repository for User data access and authentication."""

    @staticmethod
    def authenticate(conn: sqlite3.Connection, username: str, password: str) -> Optional[User]:
        """Authenticate user credentials against the database.
        Includes account lockout check (15 mins after 5 failed attempts) and dynamic hash upgrades.
        """
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username.strip(),))
        row = cursor.fetchone()
        if not row:
            return None

        keys = row.keys()
        failed_attempts = row["failed_attempts"] if "failed_attempts" in keys and row["failed_attempts"] is not None else 0
        locked_until_str = row["locked_until"] if "locked_until" in keys else None

        # 1. Check account lockout
        if locked_until_str:
            try:
                locked_until = datetime.strptime(locked_until_str, "%Y-%m-%d %H:%M:%S")
                if datetime.now() < locked_until:
                    rem_mins = int((locked_until - datetime.now()).total_seconds() / 60) + 1
                    raise PermissionError(
                        f"Cuenta bloqueada por múltiples intentos fallidos. Intente de nuevo en {rem_mins} minuto(s)."
                    )
            except ValueError:
                pass

        # 2. Check credentials
        is_valid, needs_rehash = verify_password_detail(row["password_hash"], password)

        if is_valid:
            user = _row_to_user(row)
            if not user.active:
                raise PermissionError(f"La cuenta del operador '{user.username}' está desactivada. Comuníquese con el Administrador.")

            # Reset lockout counters on success
            if failed_attempts > 0 or locked_until_str is not None:
                cursor.execute(
                    "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?",
                    (user.id,)
                )
                conn.commit()

            # Dynamic rehash if legacy iterations were used
            if needs_rehash:
                new_hash = hash_password(password)
                cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user.id))
                conn.commit()
                logging.info("Hash de '%s' actualizado a 600.000 iteraciones PBKDF2.", user.username)

            return user
        else:
            # 3. Failed password attempt: record and lock if threshold reached
            new_attempts = failed_attempts + 1
            if new_attempts >= 5:
                lock_time = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute(
                    "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
                    (new_attempts, lock_time, row["id"])
                )
                conn.commit()
                raise PermissionError("Demasiados intentos fallidos. Su cuenta ha sido bloqueada temporalmente por 15 minutos.")
            else:
                cursor.execute("UPDATE users SET failed_attempts = ? WHERE id = ?", (new_attempts, row["id"]))
                conn.commit()
            return None

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, user_id: int) -> Optional[User]:
        """Fetch user by ID."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return _row_to_user(row)
        return None

    @staticmethod
    def get_all(conn: sqlite3.Connection) -> list[User]:
        """Fetch all system users sorted by id ASC (Admin first, then cashiers)."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users ORDER BY id ASC")
        rows = cursor.fetchall()
        return [_row_to_user(row) for row in rows]

    @staticmethod
    def create_user(
        conn: sqlite3.Connection,
        username: str,
        password: str,
        full_name: str,
        role: str = "CASHIER",
        document_id: str = "",
        phone: str = "",
        email: str = "",
        is_active: int = 1
    ) -> int:
        """Create a new user with 600,000-iteration hashed password.
        Enforces single-administrator rule: if an administrator already exists,
        new users are strictly assigned the CASHIER role.
        """
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE UPPER(role) IN ('ADMIN', 'ADMINISTRADOR')")
        admin_count = cursor.fetchone()["count"]

        req_role = role.strip().upper() if role else "CAJERO"
        if admin_count >= 1 and req_role in ("ADMIN", "ADMINISTRADOR"):
            final_role = "CAJERO"
        else:
            final_role = "ADMIN" if req_role in ("ADMIN", "ADMINISTRADOR") else "CAJERO"

        hashed = hash_password(password)

        cursor.execute("PRAGMA table_info(users);")
        cols = [r["name"] for r in cursor.fetchall()]

        if "failed_attempts" in cols:
            cursor.execute(
                """
                INSERT INTO users (username, password_hash, full_name, role, document_id, phone, email, is_active, failed_attempts, locked_until)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
                """,
                (username.strip(), hashed, full_name.strip(), final_role, document_id.strip() if document_id else "", phone.strip() if phone else "", email.strip() if email else "", is_active)
            )
        elif "document_id" in cols:
            cursor.execute(
                """
                INSERT INTO users (username, password_hash, full_name, role, document_id, phone, email, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (username.strip(), hashed, full_name.strip(), final_role, document_id.strip() if document_id else "", phone.strip() if phone else "", email.strip() if email else "", is_active)
            )
        else:
            cursor.execute(
                """
                INSERT INTO users (username, password_hash, full_name, role)
                VALUES (?, ?, ?, ?)
                """,
                (username.strip(), hashed, full_name.strip(), final_role)
            )
        conn.commit()
        return cursor.lastrowid

    @staticmethod
    def update_user(
        conn: sqlite3.Connection,
        user_id: int,
        username: str,
        full_name: str,
        role: str,
        password: Optional[str] = None,
        document_id: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        is_active: Optional[int] = None
    ) -> bool:
        """Update user info. If password is provided and non-empty, rehash and update."""
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        curr = cursor.fetchone()
        if not curr:
            return False

        curr_is_admin = curr["role"].upper() in ("ADMIN", "ADMINISTRADOR")
        new_is_admin = role.strip().upper() in ("ADMIN", "ADMINISTRADOR")

        # 1. Protect against removing or demoting the last administrator
        if curr_is_admin and not new_is_admin:
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE UPPER(role) IN ('ADMIN', 'ADMINISTRADOR') AND id != ?", (user_id,))
            other_admins = cursor.fetchone()["count"]
            if other_admins == 0:
                raise ValueError("No se puede revocar el rol de Administrador al único administrador del sistema.")

        # 2. Prevent promoting another user to Administrator when an admin already exists
        if not curr_is_admin and new_is_admin:
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE UPPER(role) IN ('ADMIN', 'ADMINISTRADOR') AND id != ?", (user_id,))
            existing_admins = cursor.fetchone()["count"]
            if existing_admins >= 1:
                raise ValueError("Solo puede existir un Administrador en el sistema. Los demás usuarios deben ser Cajero.")

        # 3. Protect Administrator from being deactivated
        if curr_is_admin and is_active is not None and is_active == 0:
            raise ValueError("El Administrador del sistema no puede ser desactivado.")

        cursor.execute("PRAGMA table_info(users);")
        cols = [r["name"] for r in cursor.fetchall()]

        fields = ["username = ?", "full_name = ?", "role = ?"]
        params = [username.strip(), full_name.strip(), "ADMIN" if new_is_admin else "CAJERO"]

        if password and password.strip():
            fields.append("password_hash = ?")
            params.append(hash_password(password.strip()))

        if "document_id" in cols and document_id is not None:
            fields.append("document_id = ?")
            params.append(document_id.strip())

        if "phone" in cols and phone is not None:
            fields.append("phone = ?")
            params.append(phone.strip())

        if "email" in cols and email is not None:
            fields.append("email = ?")
            params.append(email.strip())

        if "is_active" in cols and is_active is not None:
            fields.append("is_active = ?")
            params.append(is_active)

        params.append(user_id)
        sql = f"UPDATE users SET {', '.join(fields)} WHERE id = ?"
        cursor.execute(sql, tuple(params))
        conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def toggle_active(conn: sqlite3.Connection, user_id: int) -> tuple[bool, str, int]:
        """Toggle user active status. Administrator cannot be deactivated."""
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, role, is_active FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return False, "Usuario no encontrado.", 0

        if row["role"].upper() in ("ADMIN", "ADMINISTRADOR"):
            return False, "El Administrador del sistema no puede ser desactivado.", 1

        curr_active = row["is_active"] if "is_active" in row.keys() and row["is_active"] is not None else 1
        new_active = 0 if curr_active == 1 else 1

        cursor.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_active, user_id))
        conn.commit()
        status_str = "activado" if new_active == 1 else "desactivado"
        return True, f"Operador '{row['username']}' {status_str} exitosamente.", new_active

    @staticmethod
    def delete_user(conn: sqlite3.Connection, user_id: int) -> tuple[bool, str]:
        """Delete user by ID with validation (cannot delete administrator or users with sales)."""
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            return False, "Usuario no encontrado."

        if user["role"].upper() in ("ADMIN", "ADMINISTRADOR"):
            return False, "No se puede eliminar al Administrador del sistema."

        # Check if user has sales
        cursor.execute("SELECT COUNT(*) as count FROM sales WHERE user_id = ?", (user_id,))
        sales_count = cursor.fetchone()["count"]
        if sales_count > 0:
            return False, f"No se puede eliminar: el usuario tiene {sales_count} ventas registradas."

        try:
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return True, "Usuario eliminado correctamente."
        except Exception as e:
            conn.rollback()
            return False, f"Error al eliminar: {str(e)}"
