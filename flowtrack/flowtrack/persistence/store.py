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
        conn.executescript(
            """\
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                app_name TEXT NOT NULL,
                window_title TEXT NOT NULL,
                category TEXT NOT NULL,
                sub_category TEXT NOT NULL DEFAULT '',
                session_id TEXT
            );

            CREATE TABLE IF NOT EXISTS pomodoro_sessions (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                sub_category TEXT NOT NULL DEFAULT '',
                start_time TEXT NOT NULL,
                elapsed_seconds REAL NOT NULL,
                status TEXT NOT NULL,
                completed_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_activity_timestamp
                ON activity_logs(timestamp);

            CREATE INDEX IF NOT EXISTS idx_session_start
                ON pomodoro_sessions(start_time);

            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                done INTEGER NOT NULL DEFAULT 0,
                auto_generated INTEGER NOT NULL DEFAULT 0,
                parent_id INTEGER DEFAULT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (parent_id) REFERENCES todos(id) ON DELETE SET NULL
            );
            """
        )
        conn.commit()

        # Migrate: add parent_id column if missing (existing DBs)
        try:
            conn.execute("SELECT parent_id FROM todos LIMIT 1")
        except Exception:
            try:
                conn.execute("ALTER TABLE todos ADD COLUMN parent_id INTEGER DEFAULT NULL")
                conn.commit()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Activity log operations
    # ------------------------------------------------------------------

    def save_activity(self, record: ActivityRecord) -> int:
        """Persist an activity record.

        If ``record.id`` is 0 or negative the database assigns an
        auto-incremented id.  Returns the row id of the inserted record.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            """\
            INSERT INTO activity_logs
                (timestamp, app_name, window_title, category, sub_category, session_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.timestamp.isoformat(),
                record.app_name,
                record.window_title,
                record.category,
                record.sub_category,
                record.session_id,
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
                 status, completed_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.id,
                session.category,
                session.sub_category,
                session.start_time.isoformat(),
                session.elapsed.total_seconds(),
                session.status.value,
                session.completed_count,
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
            "INSERT INTO todos (title, category, done, auto_generated, parent_id, created_at) VALUES (?, ?, 0, ?, ?, ?)",
            (title, category, 1 if auto else 0, parent_id, datetime.now().isoformat()),
        )
        conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_todos(self, include_done: bool = False) -> list[dict]:
        conn = self._get_conn()
        if include_done:
            rows = conn.execute("SELECT * FROM todos ORDER BY done, id DESC").fetchall()
        else:
            rows = conn.execute("SELECT * FROM todos WHERE done = 0 ORDER BY id DESC").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d.setdefault("parent_id", None)
            result.append(d)
        return result

    def move_todo(self, todo_id: int, parent_id: int | None) -> None:
        conn = self._get_conn()
        conn.execute("UPDATE todos SET parent_id = ? WHERE id = ?", (parent_id, todo_id))
        conn.commit()

    def toggle_todo(self, todo_id: int) -> None:
        conn = self._get_conn()
        conn.execute("UPDATE todos SET done = CASE WHEN done = 0 THEN 1 ELSE 0 END WHERE id = ?", (todo_id,))
        conn.commit()

    def delete_todo(self, todo_id: int) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        conn.commit()

    def clear_all_todos(self) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM todos")
        conn.commit()

    def clear_auto_todos(self) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM todos WHERE auto_generated = 1")
        conn.commit()

    def merge_buckets(self, source_id: int, target_id: int) -> None:
        """Move all children of source_id to target_id, then delete source."""
        conn = self._get_conn()
        conn.execute("UPDATE todos SET parent_id = ? WHERE parent_id = ?", (target_id, source_id))
        conn.execute("DELETE FROM todos WHERE id = ?", (source_id,))
        conn.commit()

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
        )
