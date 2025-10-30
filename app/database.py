import sqlite3
import pymssql
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional
import os
import time
from functools import wraps
import threading

# Global lock to serialize all SQLite write operations
_sqlite_write_lock = threading.RLock()


def retry_on_locked(max_retries=5, initial_delay=0.1):
    """Decorator to retry database operations when database is locked"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e) and attempt < max_retries - 1:
                        print(f"Database locked, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        delay *= 2  # Exponential backoff
                    else:
                        raise
            return func(*args, **kwargs)
        return wrapper
    return decorator


class SQLiteManager:
    def __init__(self, db_path: str = "/app/data/app.db"):
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database with required tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Config table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    id INTEGER PRIMARY KEY,
                    shipper_host TEXT,
                    shipper_port INTEGER,
                    shipper_user TEXT,
                    shipper_password TEXT,
                    shipper_database TEXT,
                    backoffice_host TEXT,
                    backoffice_port INTEGER,
                    backoffice_user TEXT,
                    backoffice_password TEXT,
                    backoffice_database TEXT,
                    inventory_host TEXT,
                    inventory_port INTEGER,
                    inventory_user TEXT,
                    inventory_password TEXT,
                    inventory_database TEXT,
                    inventory_enabled INTEGER DEFAULT 0
                )
            """)

            # Migrate existing config table to add inventory fields if they don't exist
            cursor.execute("PRAGMA table_info(config)")
            columns = {row[1] for row in cursor.fetchall()}
            if 'inventory_host' not in columns:
                cursor.execute("ALTER TABLE config ADD COLUMN inventory_host TEXT")
            if 'inventory_port' not in columns:
                cursor.execute("ALTER TABLE config ADD COLUMN inventory_port INTEGER")
            if 'inventory_user' not in columns:
                cursor.execute("ALTER TABLE config ADD COLUMN inventory_user TEXT")
            if 'inventory_password' not in columns:
                cursor.execute("ALTER TABLE config ADD COLUMN inventory_password TEXT")
            if 'inventory_database' not in columns:
                cursor.execute("ALTER TABLE config ADD COLUMN inventory_database TEXT")
            if 'inventory_enabled' not in columns:
                cursor.execute("ALTER TABLE config ADD COLUMN inventory_enabled INTEGER DEFAULT 0")

            # Quotation defaults table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS quotation_defaults (
                    id INTEGER PRIMARY KEY,
                    customer_id INTEGER,
                    default_status INTEGER,
                    quotation_title_prefix TEXT,
                    polling_interval_seconds INTEGER DEFAULT 60
                )
            """)

            # Conversion tracking table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversion_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pick_list_id INTEGER UNIQUE,
                    quotation_id INTEGER,
                    quotation_number TEXT,
                    converted_at DATETIME,
                    success BOOLEAN,
                    error_message TEXT
                )
            """)

            # Archived picklists table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS archived_picklists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pick_list_id INTEGER UNIQUE,
                    archived_at DATETIME,
                    archived_by TEXT
                )
            """)

            conn.commit()

    @contextmanager
    def get_connection(self):
        """Context manager for SQLite connections"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrent access
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=30000')
        try:
            yield conn
        finally:
            conn.close()

    def get_config(self) -> Optional[dict]:
        """Get MS SQL Server connection configuration"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM config WHERE id = 1")
            row = cursor.fetchone()
            return dict(row) if row else None

    def save_config(self, config: dict):
        """Save MS SQL Server connection configuration"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM config WHERE id = 1")
            exists = cursor.fetchone()[0] > 0

            if exists:
                cursor.execute("""
                    UPDATE config SET
                        shipper_host = ?,
                        shipper_port = ?,
                        shipper_user = ?,
                        shipper_password = ?,
                        shipper_database = ?,
                        backoffice_host = ?,
                        backoffice_port = ?,
                        backoffice_user = ?,
                        backoffice_password = ?,
                        backoffice_database = ?,
                        inventory_host = ?,
                        inventory_port = ?,
                        inventory_user = ?,
                        inventory_password = ?,
                        inventory_database = ?,
                        inventory_enabled = ?
                    WHERE id = 1
                """, (
                    config.get('shipper_host'),
                    config.get('shipper_port'),
                    config.get('shipper_user'),
                    config.get('shipper_password'),
                    config.get('shipper_database'),
                    config.get('backoffice_host'),
                    config.get('backoffice_port'),
                    config.get('backoffice_user'),
                    config.get('backoffice_password'),
                    config.get('backoffice_database'),
                    config.get('inventory_host'),
                    config.get('inventory_port'),
                    config.get('inventory_user'),
                    config.get('inventory_password'),
                    config.get('inventory_database'),
                    config.get('inventory_enabled', 0)
                ))
            else:
                cursor.execute("""
                    INSERT INTO config (id, shipper_host, shipper_port, shipper_user,
                        shipper_password, shipper_database, backoffice_host, backoffice_port,
                        backoffice_user, backoffice_password, backoffice_database,
                        inventory_host, inventory_port, inventory_user, inventory_password,
                        inventory_database, inventory_enabled)
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    config.get('shipper_host'),
                    config.get('shipper_port'),
                    config.get('shipper_user'),
                    config.get('shipper_password'),
                    config.get('shipper_database'),
                    config.get('backoffice_host'),
                    config.get('backoffice_port'),
                    config.get('backoffice_user'),
                    config.get('backoffice_password'),
                    config.get('backoffice_database'),
                    config.get('inventory_host'),
                    config.get('inventory_port'),
                    config.get('inventory_user'),
                    config.get('inventory_password'),
                    config.get('inventory_database'),
                    config.get('inventory_enabled', 0)
                ))

            conn.commit()

    def get_quotation_defaults(self) -> Optional[dict]:
        """Get quotation default settings"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM quotation_defaults WHERE id = 1")
            row = cursor.fetchone()
            return dict(row) if row else None

    def save_quotation_defaults(self, defaults: dict):
        """Save quotation default settings"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM quotation_defaults WHERE id = 1")
            exists = cursor.fetchone()[0] > 0

            if exists:
                cursor.execute("""
                    UPDATE quotation_defaults SET
                        customer_id = ?,
                        default_status = ?,
                        quotation_title_prefix = ?,
                        polling_interval_seconds = ?
                    WHERE id = 1
                """, (
                    defaults.get('customer_id'),
                    defaults.get('default_status'),
                    defaults.get('quotation_title_prefix'),
                    defaults.get('polling_interval_seconds', 60)
                ))
            else:
                cursor.execute("""
                    INSERT INTO quotation_defaults (id, customer_id, default_status,
                        quotation_title_prefix, polling_interval_seconds)
                    VALUES (1, ?, ?, ?, ?)
                """, (
                    defaults.get('customer_id'),
                    defaults.get('default_status'),
                    defaults.get('quotation_title_prefix'),
                    defaults.get('polling_interval_seconds', 60)
                ))

            conn.commit()

    @retry_on_locked(max_retries=10, initial_delay=0.1)
    def log_conversion(self, pick_list_id: int, success: bool, quotation_id: Optional[int] = None,
                      quotation_number: Optional[str] = None, error_message: Optional[str] = None):
        """Log a conversion attempt"""
        with _sqlite_write_lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO conversion_tracking
                    (pick_list_id, quotation_id, quotation_number, converted_at, success, error_message)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    pick_list_id,
                    quotation_id,
                    quotation_number,
                    datetime.now(ZoneInfo("America/Chicago")).isoformat(),
                    success,
                    error_message
                ))
                conn.commit()

    def get_converted_picklist_ids(self) -> set:
        """Get set of already converted picklist IDs"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT pick_list_id FROM conversion_tracking WHERE success = 1")
            return {row[0] for row in cursor.fetchall()}

    def get_conversion_history(self, limit: int = 100, offset: int = 0, status: str = 'all') -> list:
        """Get conversion history with pagination and optional status filter"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if status == 'success':
                query = """
                    SELECT * FROM conversion_tracking
                    WHERE success = 1
                    ORDER BY converted_at DESC
                    LIMIT ? OFFSET ?
                """
            elif status == 'failed':
                query = """
                    SELECT * FROM conversion_tracking
                    WHERE success = 0
                    ORDER BY converted_at DESC
                    LIMIT ? OFFSET ?
                """
            else:  # 'all'
                query = """
                    SELECT * FROM conversion_tracking
                    ORDER BY converted_at DESC
                    LIMIT ? OFFSET ?
                """

            cursor.execute(query, (limit, offset))
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> dict:
        """Get conversion statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM conversion_tracking WHERE success = 1")
            total_converted = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM conversion_tracking WHERE success = 0")
            total_failed = cursor.fetchone()[0]

            return {
                'total_converted': total_converted,
                'total_failed': total_failed,
                'total_attempts': total_converted + total_failed
            }

    def delete_conversion_records(self, record_ids: list) -> int:
        """Delete specific conversion tracking records by ID"""
        with _sqlite_write_lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ','.join(['?'] * len(record_ids))
                cursor.execute(f"DELETE FROM conversion_tracking WHERE id IN ({placeholders})", tuple(record_ids))
                deleted_count = cursor.rowcount
                conn.commit()
                return deleted_count

    def delete_all_failed_conversions(self) -> int:
        """Delete all failed conversion records (success = 0)"""
        with _sqlite_write_lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM conversion_tracking WHERE success = 0")
                deleted_count = cursor.rowcount
                conn.commit()
                return deleted_count

    def archive_picklist(self, pick_list_id: int):
        """Archive a picklist"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO archived_picklists
                (pick_list_id, archived_at, archived_by)
                VALUES (?, ?, ?)
            """, (
                pick_list_id,
                datetime.now(ZoneInfo("America/Chicago")).isoformat(),
                'user'
            ))
            conn.commit()

    def unarchive_picklist(self, pick_list_id: int):
        """Unarchive a picklist"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM archived_picklists WHERE pick_list_id = ?", (pick_list_id,))
            conn.commit()

    def get_archived_picklist_ids(self) -> set:
        """Get set of archived picklist IDs"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT pick_list_id FROM archived_picklists")
            return {row[0] for row in cursor.fetchall()}

    def get_archived_picklists(self, limit: int = 100, offset: int = 0) -> list:
        """Get archived picklists with pagination"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM archived_picklists
                ORDER BY archived_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            return [dict(row) for row in cursor.fetchall()]


class SQLServerManager:
    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database

    @contextmanager
    def get_connection(self):
        """Context manager for MS SQL Server connections"""
        conn = pymssql.connect(
            server=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            as_dict=True
        )
        try:
            yield conn
        finally:
            conn.close()

    def test_connection(self) -> tuple[bool, Optional[str]]:
        """Test MS SQL Server connection"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 AS test")
                result = cursor.fetchone()
                return (True, None)
        except Exception as e:
            return (False, str(e))
