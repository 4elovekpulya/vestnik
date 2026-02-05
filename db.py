import sqlite3
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Event:
    id: int
    start_at: datetime
    text: str
    image_file_id: str | None
    reminder_minutes: int


class Database:
    def __init__(self, path: str):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        cur = self._db.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_at TEXT NOT NULL,
                text TEXT NOT NULL,
                image_file_id TEXT,
                reminder_minutes INTEGER NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL,
                subscribed_at TEXT NOT NULL,
                PRIMARY KEY (user_id, event_id),
                FOREIGN KEY (event_id) REFERENCES events (id)
            )
            """
        )
        self._db.commit()

    def create_event(
        self,
        start_at: datetime,
        text: str,
        reminder_minutes: int,
        image_file_id: str | None = None,
    ) -> int:
        cur = self._db.cursor()
        cur.execute(
            """
            INSERT INTO events (start_at, text, image_file_id, reminder_minutes)
            VALUES (?, ?, ?, ?)
            """,
            (start_at.isoformat(), text, image_file_id, reminder_minutes),
        )
        self._db.commit()
        return int(cur.lastrowid)

    def update_event(
        self,
        event_id: int,
        *,
        start_at: datetime | None = None,
        text: str | None = None,
        reminder_minutes: int | None = None,
        image_file_id: str | None = None,
    ) -> None:
        fields = []
        values: list[object] = []
        if start_at is not None:
            fields.append("start_at = ?")
            values.append(start_at.isoformat())
        if text is not None:
            fields.append("text = ?")
            values.append(text)
        if reminder_minutes is not None:
            fields.append("reminder_minutes = ?")
            values.append(reminder_minutes)
        if image_file_id is not None:
            fields.append("image_file_id = ?")
            values.append(image_file_id)
        if not fields:
            return
        values.append(event_id)
        query = f"UPDATE events SET {', '.join(fields)} WHERE id = ?"
        cur = self._db.cursor()
        cur.execute(query, values)
        self._db.commit()

    def delete_event(self, event_id: int) -> None:
        cur = self._db.cursor()
        cur.execute("DELETE FROM subscriptions WHERE event_id = ?", (event_id,))
        cur.execute("DELETE FROM events WHERE id = ?", (event_id,))
        self._db.commit()

    def get_event(self, event_id: int) -> Event | None:
        cur = self._db.cursor()
        cur.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        row = cur.fetchone()
        if not row:
            return None
        return Event(
            id=row["id"],
            start_at=datetime.fromisoformat(row["start_at"]),
            text=row["text"],
            image_file_id=row["image_file_id"],
            reminder_minutes=row["reminder_minutes"],
        )

    def list_future_events(self, now: datetime) -> list[Event]:
        cur = self._db.cursor()
        cur.execute(
            """
            SELECT * FROM events
            WHERE start_at > ?
            ORDER BY start_at
            """,
            (now.isoformat(),),
        )
        return [
            Event(
                id=row["id"],
                start_at=datetime.fromisoformat(row["start_at"]),
                text=row["text"],
                image_file_id=row["image_file_id"],
                reminder_minutes=row["reminder_minutes"],
            )
            for row in cur.fetchall()
        ]

    def count_subscriptions(self, event_id: int) -> int:
        cur = self._db.cursor()
        cur.execute(
            "SELECT COUNT(*) as cnt FROM subscriptions WHERE event_id = ?",
            (event_id,),
        )
        row = cur.fetchone()
        return int(row["cnt"]) if row else 0

    def is_subscribed(self, user_id: int, event_id: int) -> bool:
        cur = self._db.cursor()
        cur.execute(
            "SELECT 1 FROM subscriptions WHERE user_id = ? AND event_id = ?",
            (user_id, event_id),
        )
        return cur.fetchone() is not None

    def add_subscription(self, user_id: int, event_id: int, now: datetime) -> None:
        cur = self._db.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO subscriptions (user_id, event_id, subscribed_at)
            VALUES (?, ?, ?)
            """,
            (user_id, event_id, now.isoformat()),
        )
        self._db.commit()

    def remove_subscription(self, user_id: int, event_id: int) -> None:
        cur = self._db.cursor()
        cur.execute(
            "DELETE FROM subscriptions WHERE user_id = ? AND event_id = ?",
            (user_id, event_id),
        )
        self._db.commit()

    def list_subscribers(self, event_id: int) -> list[int]:
        cur = self._db.cursor()
        cur.execute(
            "SELECT user_id FROM subscriptions WHERE event_id = ?",
            (event_id,),
        )
        return [row["user_id"] for row in cur.fetchall()]
