"""
NeuroPulse — Database Manager
==============================
Handles all SQLite persistence for the NeuroPulse backend.

Schema
------
  system_logs   — time-series record of every sensor step
  anomaly_events — coarser records of detected anomaly windows

Design notes
------------
* Uses a single shared connection with WAL journal mode so background
  threads can write without blocking the FastAPI event loop.
* All public write functions accept plain Python types so callers never
  need to import sqlite3 directly.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = Path(__file__).parent / "neuropulse.db"

# One shared connection is safe in WAL mode with check_same_thread=False
# as long as we serialise writes via a threading.Lock (done below).
_conn: Optional[sqlite3.Connection] = None
_write_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    """
    Return (and lazily create) the module-level SQLite connection.
    WAL mode is enabled for concurrent read/write performance.
    """
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(
            str(DB_PATH),
            check_same_thread=False,   # We guard writes with _write_lock
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        _conn.row_factory = sqlite3.Row  # Rows accessible by column name
        _conn.execute("PRAGMA journal_mode=WAL;")
        _conn.execute("PRAGMA synchronous=NORMAL;")
        _conn.commit()
    return _conn


def init_db() -> None:
    """
    Create all required tables if they do not already exist.
    Call once at application start-up (inside FastAPI's lifespan hook).
    """
    conn = get_connection()
    with _write_lock:
        conn.executescript(
            """
            -- ---------------------------------------------------------------
            -- system_logs
            -- One row per sensor time-step tick.
            -- ---------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS system_logs (
                id                          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp                   REAL    NOT NULL,   -- Unix epoch (float)
                node_id                     TEXT    NOT NULL,   -- Sensor node identifier
                sensor_value                REAL    NOT NULL,   -- Raw normalised input current
                membrane_potential          REAL    NOT NULL,   -- U(t) after this step
                spike_fired                 INTEGER NOT NULL,   -- 1 = spike, 0 = silent (BOOLEAN)
                estimated_power_saved_pct   REAL    NOT NULL    -- Running % power saved
            );

            -- ---------------------------------------------------------------
            -- anomaly_events
            -- One row per detected anomaly burst (high-frequency spike window).
            -- ---------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS anomaly_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                detected_at     REAL    NOT NULL,   -- Unix epoch when burst started
                node_id         TEXT    NOT NULL,
                peak_potential  REAL    NOT NULL,   -- Highest U(t) seen in the burst
                spike_count     INTEGER NOT NULL,   -- Spikes fired during the burst
                duration_secs   REAL,               -- NULL until burst closes
                resolved        INTEGER DEFAULT 0   -- 0 = active, 1 = resolved
            );

            -- Fast queries by time and node
            CREATE INDEX IF NOT EXISTS idx_logs_node_time
                ON system_logs (node_id, timestamp);

            CREATE INDEX IF NOT EXISTS idx_anomaly_node
                ON anomaly_events (node_id, detected_at);
            """
        )
        conn.commit()
    print("[DB] Tables initialised ✓")


# ---------------------------------------------------------------------------
# Write helpers — called from the background simulation loop
# ---------------------------------------------------------------------------

def log_sensor_step(
    node_id: str,
    sensor_value: float,
    membrane_potential: float,
    spike_fired: bool,
    estimated_power_saved_pct: float,
    timestamp: Optional[float] = None,
) -> None:
    """
    Append one time-step record to system_logs.

    This is the hot path — called every simulation tick per sensor node.
    The _write_lock ensures thread safety without blocking the asyncio loop
    for more than microseconds.
    """
    ts = timestamp if timestamp is not None else time.time()
    conn = get_connection()
    with _write_lock:
        conn.execute(
            """
            INSERT INTO system_logs
                (timestamp, node_id, sensor_value, membrane_potential,
                 spike_fired, estimated_power_saved_pct)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                node_id,
                round(sensor_value, 6),
                round(membrane_potential, 6),
                int(spike_fired),
                round(estimated_power_saved_pct, 2),
            ),
        )
        conn.commit()


def open_anomaly_event(
    node_id: str,
    peak_potential: float,
    spike_count: int,
    detected_at: Optional[float] = None,
) -> int:
    """
    Record the start of an anomaly burst.

    Returns
    -------
    int
        The new anomaly_events row id (use to close the event later).
    """
    ts = detected_at if detected_at is not None else time.time()
    conn = get_connection()
    with _write_lock:
        cur = conn.execute(
            """
            INSERT INTO anomaly_events
                (detected_at, node_id, peak_potential, spike_count, resolved)
            VALUES (?, ?, ?, ?, 0)
            """,
            (ts, node_id, round(peak_potential, 6), spike_count),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]


def close_anomaly_event(
    event_id: int,
    peak_potential: float,
    spike_count: int,
    duration_secs: float,
) -> None:
    """Mark an open anomaly event as resolved and fill in final metrics."""
    conn = get_connection()
    with _write_lock:
        conn.execute(
            """
            UPDATE anomaly_events
            SET    peak_potential = ?,
                   spike_count    = ?,
                   duration_secs  = ?,
                   resolved       = 1
            WHERE  id = ?
            """,
            (
                round(peak_potential, 6),
                spike_count,
                round(duration_secs, 3),
                event_id,
            ),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Read helpers — used by REST endpoints to serve the frontend
# ---------------------------------------------------------------------------

def fetch_recent_logs(
    node_id: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    """
    Return the most recent system_log rows, optionally filtered by node.

    Returns list of dicts (column → value) suitable for JSON serialisation.
    """
    conn = get_connection()
    if node_id:
        rows = conn.execute(
            """
            SELECT * FROM system_logs
            WHERE  node_id = ?
            ORDER  BY timestamp DESC
            LIMIT  ?
            """,
            (node_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM system_logs
            ORDER  BY timestamp DESC
            LIMIT  ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]  # chronological order


def fetch_anomaly_events(resolved: Optional[bool] = None, limit: int = 50) -> list[dict]:
    """Return anomaly events, optionally filtered by resolved state."""
    conn = get_connection()
    if resolved is None:
        rows = conn.execute(
            "SELECT * FROM anomaly_events ORDER BY detected_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM anomaly_events
            WHERE  resolved = ?
            ORDER  BY detected_at DESC
            LIMIT  ?
            """,
            (int(resolved), limit),
        ).fetchall()
    return [dict(r) for r in rows]


def fetch_power_savings_summary() -> dict:
    """
    Aggregate power-saving stats across all nodes.

    Returns a dict with overall average and per-node breakdown.
    """
    conn = get_connection()
    overall = conn.execute(
        "SELECT AVG(estimated_power_saved_pct) AS avg_saving FROM system_logs"
    ).fetchone()
    per_node = conn.execute(
        """
        SELECT   node_id,
                 AVG(estimated_power_saved_pct) AS avg_saving,
                 SUM(spike_fired)               AS total_spikes,
                 COUNT(*)                       AS total_steps
        FROM     system_logs
        GROUP BY node_id
        """
    ).fetchall()

    return {
        "overall_avg_power_saved_pct": round(overall["avg_saving"] or 0.0, 2),
        "per_node": [dict(r) for r in per_node],
    }


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------

def prune_old_logs(older_than_secs: float = 3600.0) -> int:
    """
    Delete system_log rows older than `older_than_secs` seconds.
    Useful to keep the DB compact during a long hackathon demo session.

    Returns the number of rows deleted.
    """
    cutoff = time.time() - older_than_secs
    conn = get_connection()
    with _write_lock:
        cur = conn.execute(
            "DELETE FROM system_logs WHERE timestamp < ?", (cutoff,)
        )
        conn.commit()
    return cur.rowcount


def close_db() -> None:
    """Gracefully close the shared connection (call in shutdown hook)."""
    global _conn
    if _conn:
        _conn.close()
        _conn = None
    print("[DB] Connection closed ✓")