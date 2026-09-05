"""
Audit trail: every state change in the money-flow gets logged here.
This is queried live by the dashboard during the demo.
"""
import sqlite3
import json
import time
import os
from contextlib import contextmanager

DB_PATH = os.environ.get("AUDIT_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "audit.db"))


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                event_type TEXT NOT NULL,
                order_ref TEXT,
                amount_paise INTEGER,
                decision TEXT NOT NULL,
                reason TEXT,
                payload_json TEXT
            )
            """
        )


def log_event(event_type: str, decision: str, reason: str = "",
              order_ref: str = None, amount_paise: int = None, payload: dict = None):
    """
    event_type: e.g. 'intent_received', 'envelope_check', 'razorpay_order_created',
                'payment_captured', 'payment_failed', 'halted_for_approval'
    decision:   e.g. 'allowed', 'blocked', 'success', 'failure', 'pending_approval'
    """
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO audit_log (timestamp, event_type, order_ref, amount_paise, decision, reason, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                time.time(),
                event_type,
                order_ref,
                amount_paise,
                decision,
                reason,
                json.dumps(payload or {}),
            ),
        )


def get_recent_events(limit: int = 50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
