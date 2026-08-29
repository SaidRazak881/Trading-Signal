"""SQLite database layer."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional

from app.config import DB_PATH, DATA_DIR


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL DEFAULT '15m',
                direction TEXT NOT NULL,
                strategy_type TEXT NOT NULL DEFAULT 'trend_pullback',
                signal_score REAL NOT NULL,
                trigger_price REAL NOT NULL,
                tp_price REAL NOT NULL,
                sl_price REAL NOT NULL,
                current_price REAL,
                atr REAL,
                risk_reward REAL,
                reasons TEXT,
                snapshot_json TEXT,
                detected_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                close_price REAL,
                closed_at TEXT,
                notes TEXT,
                UNIQUE(symbol, direction, detected_at)
            );

            CREATE TABLE IF NOT EXISTS signal_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                event_time TEXT NOT NULL,
                price REAL,
                meta_json TEXT,
                FOREIGN KEY(signal_id) REFERENCES signals(id)
            );

            CREATE TABLE IF NOT EXISTS scan_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                pairs_scanned INTEGER DEFAULT 0,
                signals_found INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running',
                message TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
            CREATE INDEX IF NOT EXISTS idx_signals_detected ON signals(detected_at DESC);
            CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
            """
        )


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(str(DB_PATH), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    d = dict(row)
    if d.get("reasons") and isinstance(d["reasons"], str):
        try:
            d["reasons"] = json.loads(d["reasons"])
        except json.JSONDecodeError:
            d["reasons"] = [d["reasons"]]
    if d.get("snapshot_json") and isinstance(d["snapshot_json"], str):
        try:
            d["snapshot"] = json.loads(d["snapshot_json"])
        except json.JSONDecodeError:
            d["snapshot"] = {}
        del d["snapshot_json"]
    return d


# ── Signal CRUD ──────────────────────────────────────────────

def insert_signal(data: dict) -> int:
    reasons = data.get("reasons", [])
    if isinstance(reasons, list):
        reasons = json.dumps(reasons)
    snapshot = data.get("snapshot", {})
    if isinstance(snapshot, dict):
        snapshot = json.dumps(snapshot)

    with get_conn() as conn:
        # Avoid duplicate active signal for same symbol+direction within last hour
        existing = conn.execute(
            """
            SELECT id FROM signals
            WHERE symbol = ? AND direction = ? AND status = 'active'
            ORDER BY detected_at DESC LIMIT 1
            """,
            (data["symbol"], data["direction"]),
        ).fetchone()
        if existing:
            return existing["id"]

        cur = conn.execute(
            """
            INSERT INTO signals (
                symbol, timeframe, direction, strategy_type, signal_score,
                trigger_price, tp_price, sl_price, current_price, atr,
                risk_reward, reasons, snapshot_json, detected_at, expires_at, status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                data["symbol"],
                data.get("timeframe", "15m"),
                data["direction"],
                data.get("strategy_type", "trend_pullback"),
                data["signal_score"],
                data["trigger_price"],
                data["tp_price"],
                data["sl_price"],
                data.get("current_price", data["trigger_price"]),
                data.get("atr"),
                data.get("risk_reward"),
                reasons,
                snapshot,
                data["detected_at"],
                data["expires_at"],
                "active",
            ),
        )
        signal_id = cur.lastrowid
        conn.execute(
            """
            INSERT INTO signal_events (signal_id, event_type, event_time, price, meta_json)
            VALUES (?,?,?,?,?)
            """,
            (signal_id, "created", data["detected_at"], data["trigger_price"], reasons),
        )
        return signal_id


def get_active_signals() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM signals WHERE status = 'active' ORDER BY signal_score DESC, detected_at DESC"
        ).fetchall()
    return [row_to_dict(r) for r in rows]


def get_signals(
    status: Optional[str] = None,
    direction: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if status and status != "all":
        clauses.append("status = ?")
        params.append(status)
    if direction and direction != "all":
        clauses.append("direction = ?")
        params.append(direction.upper())
    if symbol:
        clauses.append("symbol LIKE ?")
        params.append(f"%{symbol.upper()}%")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.extend([limit, offset])
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM signals {where} ORDER BY detected_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
    return [row_to_dict(r) for r in rows]


def get_signal(signal_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
    return row_to_dict(row)


def update_signal_price(signal_id: int, price: float) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE signals SET current_price = ? WHERE id = ? AND status = 'active'",
            (price, signal_id),
        )


def close_signal(
    signal_id: int,
    status: str,
    close_price: float,
    notes: str = "",
) -> None:
    now = utcnow()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE signals
            SET status = ?, close_price = ?, closed_at = ?, current_price = ?, notes = ?
            WHERE id = ? AND status = 'active'
            """,
            (status, close_price, now, close_price, notes, signal_id),
        )
        conn.execute(
            """
            INSERT INTO signal_events (signal_id, event_type, event_time, price, meta_json)
            VALUES (?,?,?,?,?)
            """,
            (signal_id, status, now, close_price, json.dumps({"notes": notes})),
        )


def get_stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM signals").fetchone()["c"]
        active = conn.execute(
            "SELECT COUNT(*) AS c FROM signals WHERE status = 'active'"
        ).fetchone()["c"]
        wins = conn.execute(
            "SELECT COUNT(*) AS c FROM signals WHERE status = 'win'"
        ).fetchone()["c"]
        losses = conn.execute(
            "SELECT COUNT(*) AS c FROM signals WHERE status = 'loss'"
        ).fetchone()["c"]
        expired = conn.execute(
            "SELECT COUNT(*) AS c FROM signals WHERE status = 'expired'"
        ).fetchone()["c"]
        closed = wins + losses
        win_rate = round((wins / closed) * 100, 1) if closed else 0.0

        avg_score = conn.execute(
            "SELECT AVG(signal_score) AS a FROM signals"
        ).fetchone()["a"]
        avg_rr = conn.execute(
            "SELECT AVG(risk_reward) AS a FROM signals WHERE risk_reward IS NOT NULL"
        ).fetchone()["a"]

        by_dir = conn.execute(
            """
            SELECT direction,
                   SUM(CASE WHEN status='win' THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN status='loss' THEN 1 ELSE 0 END) AS losses,
                   COUNT(*) AS total
            FROM signals GROUP BY direction
            """
        ).fetchall()

        top_pairs = conn.execute(
            """
            SELECT symbol,
                   SUM(CASE WHEN status='win' THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN status='loss' THEN 1 ELSE 0 END) AS losses,
                   COUNT(*) AS total,
                   AVG(signal_score) AS avg_score
            FROM signals
            GROUP BY symbol
            ORDER BY wins DESC, total DESC
            LIMIT 10
            """
        ).fetchall()

        recent_scan = conn.execute(
            "SELECT * FROM scan_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()

        strongest = conn.execute(
            """
            SELECT * FROM signals WHERE status = 'active'
            ORDER BY signal_score DESC LIMIT 1
            """
        ).fetchone()

    return {
        "total_signals": total,
        "active": active,
        "wins": wins,
        "losses": losses,
        "expired": expired,
        "win_rate": win_rate,
        "avg_score": round(avg_score or 0, 1),
        "avg_rr": round(avg_rr or 0, 2),
        "by_direction": [dict(r) for r in by_dir],
        "top_pairs": [dict(r) for r in top_pairs],
        "last_scan": row_to_dict(recent_scan) if recent_scan else None,
        "strongest": row_to_dict(strongest) if strongest else None,
    }


def start_scan_log() -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO scan_logs (started_at, status) VALUES (?, 'running')",
            (utcnow(),),
        )
        return cur.lastrowid


def finish_scan_log(
    log_id: int,
    pairs: int,
    found: int,
    status: str = "ok",
    message: str = "",
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE scan_logs
            SET finished_at = ?, pairs_scanned = ?, signals_found = ?, status = ?, message = ?
            WHERE id = ?
            """,
            (utcnow(), pairs, found, status, message, log_id),
        )


def get_events(signal_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM signal_events WHERE signal_id = ? ORDER BY id ASC",
            (signal_id,),
        ).fetchall()
    return [dict(r) for r in rows]
