"""SQLite-backed persistence for activity logs and Pomodoro sessions."""

import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from flowtrack.core.models import ActivityRecord, PomodoroSession, SessionStatus


class ActivityStore:
    """Read/write interface to the local SQLite database.

    Stores activity observations and Pomodoro session state.  Timestamps are
    persisted as ISO 8601 text and ``timedelta`` values as total seconds
    (REAL) so that round-trip fidelity is preserved.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Schema initialisation
    # ------------------------------------------------------------------

    def init_db(self) -> None:
        """Create tables and indexes if they don't already exist."""
        conn = self._get_conn()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """\
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                app_name TEXT NOT NULL,
                window_title TEXT NOT NULL,
                category TEXT NOT NULL,
                sub_category TEXT NOT NULL DEFAULT '',
                session_id TEXT,
                active_task_id INTEGER,
                activity_summary TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS pomodoro_sessions (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                sub_category TEXT NOT NULL DEFAULT '',
                start_time TEXT NOT NULL,
                elapsed_seconds REAL NOT NULL,
                status TEXT NOT NULL,
                completed_count INTEGER NOT NULL DEFAULT 0,
                active_task_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS focus_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                parent_id INTEGER,
                done INTEGER NOT NULL DEFAULT 0,
                auto_generated INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (parent_id) REFERENCES focus_tasks(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_activity_timestamp
                ON activity_logs(timestamp);

            CREATE INDEX IF NOT EXISTS idx_session_start
                ON pomodoro_sessions(start_time);

            CREATE INDEX IF NOT EXISTS idx_activity_task
                ON activity_logs(active_task_id);

            CREATE INDEX IF NOT EXISTS idx_focus_parent
                ON focus_tasks(parent_id);
            """
        )
        conn.commit()

        # Migrate: add columns if missing (existing DBs)
        self._migrate_add_column(conn, "activity_logs", "active_task_id", "INTEGER")
        self._migrate_add_column(conn, "activity_logs", "activity_summary", "TEXT NOT NULL DEFAULT ''")
        self._migrate_add_column(conn, "pomodoro_sessions", "active_task_id", "INTEGER")
        self._migrate_add_column(conn, "focus_tasks", "sort_order", "INTEGER NOT NULL DEFAULT 0")

    @staticmethod
    def _migrate_add_column(conn, table: str, column: str, col_type: str) -> None:
        """Add a column to a table if it doesn't exist yet."""
        try:
            conn.execute(f"SELECT {column} FROM {table} LIMIT 1")
        except Exception:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                conn.commit()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Activity log operations
    # ------------------------------------------------------------------

    def save_activity(self, record: ActivityRecord) -> int:
        """Persist an activity record. Returns the row id."""
        conn = self._get_conn()
        cursor = conn.execute(
            """\
            INSERT INTO activity_logs
                (timestamp, app_name, window_title, category, sub_category,
                 session_id, active_task_id, activity_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.timestamp.isoformat(),
                record.app_name,
                record.window_title,
                record.category,
                record.sub_category,
                record.session_id,
                record.active_task_id,
                record.activity_summary,
            ),
        )
        conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_activity_by_id(self, record_id: int) -> Optional[ActivityRecord]:
        """Return a single activity record by primary key, or ``None``."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM activity_logs WHERE id = ?", (record_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_activity(row)

    def get_activities(
        self, start: datetime, end: datetime
    ) -> list[ActivityRecord]:
        """Return all activity records whose timestamp falls in [start, end)."""
        conn = self._get_conn()
        rows = conn.execute(
            """\
            SELECT * FROM activity_logs
            WHERE timestamp >= ? AND timestamp < ?
            ORDER BY timestamp
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return [self._row_to_activity(r) for r in rows]

    # ------------------------------------------------------------------
    # Pomodoro session operations
    # ------------------------------------------------------------------

    def save_session(self, session: PomodoroSession) -> None:
        """Insert or update a Pomodoro session (upsert by id)."""
        conn = self._get_conn()
        conn.execute(
            """\
            INSERT OR REPLACE INTO pomodoro_sessions
                (id, category, sub_category, start_time, elapsed_seconds,
                 status, completed_count, active_task_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.id,
                session.category,
                session.sub_category,
                session.start_time.isoformat(),
                session.elapsed.total_seconds(),
                session.status.value,
                session.completed_count,
                session.active_task_id,
            ),
        )
        conn.commit()

    def get_session_by_id(self, session_id: str) -> Optional[PomodoroSession]:
        """Return a single Pomodoro session by id, or ``None``."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM pomodoro_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def get_sessions(
        self, start: datetime, end: datetime
    ) -> list[PomodoroSession]:
        """Return all sessions whose start_time falls in [start, end)."""
        conn = self._get_conn()
        rows = conn.execute(
            """\
            SELECT * FROM pomodoro_sessions
            WHERE start_time >= ? AND start_time < ?
            ORDER BY start_time
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    # ------------------------------------------------------------------
    # Todo operations
    # ------------------------------------------------------------------

    def add_todo(self, title: str, category: str = "", auto: bool = False, parent_id: int | None = None) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO focus_tasks (title, category, done, auto_generated, parent_id, created_at, sort_order) VALUES (?, ?, 0, ?, ?, ?, 0)",
            (title, category, 1 if auto else 0, parent_id, datetime.now().isoformat()),
        )
        conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_todos(self, include_done: bool = False) -> list[dict]:
        conn = self._get_conn()
        if include_done:
            rows = conn.execute("SELECT * FROM focus_tasks ORDER BY sort_order, done, id DESC").fetchall()
        else:
            rows = conn.execute("SELECT * FROM focus_tasks WHERE done = 0 ORDER BY sort_order, id DESC").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d.setdefault("parent_id", None)
            result.append(d)
        return result

    def move_todo(self, todo_id: int, parent_id: int | None) -> None:
        conn = self._get_conn()
        conn.execute("UPDATE focus_tasks SET parent_id = ? WHERE id = ?", (parent_id, todo_id))
        conn.commit()

    def toggle_todo(self, todo_id: int) -> None:
        conn = self._get_conn()
        conn.execute("UPDATE focus_tasks SET done = CASE WHEN done = 0 THEN 1 ELSE 0 END WHERE id = ?", (todo_id,))
        conn.commit()

    def delete_todo(self, todo_id: int) -> None:
        conn = self._get_conn()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM focus_tasks WHERE id = ?", (todo_id,))
        conn.commit()

    def clear_all_todos(self) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM focus_tasks")
        conn.commit()

    def clear_auto_todos(self) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM focus_tasks WHERE auto_generated = 1")
        conn.commit()

    def merge_buckets(self, source_id: int, target_id: int) -> None:
        """Move all children of source_id to target_id, then delete source."""
        conn = self._get_conn()
        conn.execute("UPDATE focus_tasks SET parent_id = ? WHERE parent_id = ?", (target_id, source_id))
        conn.execute("DELETE FROM focus_tasks WHERE id = ?", (source_id,))
        conn.commit()
    def get_activities_by_task(self, task_id: int, start: datetime, end: datetime) -> list[ActivityRecord]:
        """Get all auto-tracked activities associated with a specific task."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM activity_logs WHERE active_task_id = ? AND timestamp >= ? AND timestamp < ? ORDER BY timestamp",
            (task_id, start.isoformat(), end.isoformat()),
        ).fetchall()
        return [self._row_to_activity(r) for r in rows]

    def get_activity_summary_by_task(self, task_id: int, start: datetime, end: datetime, poll_interval: int = 5) -> list[dict]:
        """Get aggregated activity entries for a task, grouped by app+summary with time totals."""
        conn = self._get_conn()
        rows = conn.execute(
            """\
            SELECT app_name, activity_summary, category, sub_category, COUNT(*) as count,
                   MIN(timestamp) as first_seen, MAX(timestamp) as last_seen
            FROM activity_logs
            WHERE active_task_id = ? AND timestamp >= ? AND timestamp < ?
            GROUP BY app_name, activity_summary
            ORDER BY count DESC
            """,
            (task_id, start.isoformat(), end.isoformat()),
        ).fetchall()
        result = []
        for r in rows:
            result.append({
                "app_name": r["app_name"],
                "activity_summary": r["activity_summary"],
                "category": r["category"],
                "sub_category": r["sub_category"],
                "count": r["count"],
                "time_seconds": r["count"] * poll_interval,
                "first_seen": r["first_seen"],
                "last_seen": r["last_seen"],
            })
        return result

    # ------------------------------------------------------------------
    # Row mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_activity(row: sqlite3.Row) -> ActivityRecord:
        return ActivityRecord(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            app_name=row["app_name"],
            window_title=row["window_title"],
            category=row["category"],
            sub_category=row["sub_category"],
            session_id=row["session_id"],
            active_task_id=row["active_task_id"] if "active_task_id" in row.keys() else None,
            activity_summary=row["activity_summary"] if "activity_summary" in row.keys() else "",
        )

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> PomodoroSession:
        return PomodoroSession(
            id=row["id"],
            category=row["category"],
            sub_category=row["sub_category"],
            start_time=datetime.fromisoformat(row["start_time"]),
            elapsed=timedelta(seconds=row["elapsed_seconds"]),
            status=SessionStatus(row["status"]),
            completed_count=row["completed_count"],
            active_task_id=row["active_task_id"] if "active_task_id" in row.keys() else None,
        )
