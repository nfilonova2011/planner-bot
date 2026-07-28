"""
Работа с базой данных SQLite.
Хранит пользователей и их задачи/напоминания.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = "planner.db"


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Создаёт таблицы, если их ещё нет."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                remind_time TEXT NOT NULL,   -- формат "HH:MM"
                remind_date TEXT,            -- формат "YYYY-MM-DD", NULL = каждый день
                is_done INTEGER DEFAULT 0,
                is_sent INTEGER DEFAULT 0,   -- отправлено ли сегодняшнее напоминание
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)


def add_task(user_id: int, chat_id: int, text: str, remind_time: str, remind_date: str | None = None) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (user_id, chat_id, text, remind_time, remind_date) VALUES (?, ?, ?, ?, ?)",
            (user_id, chat_id, text, remind_time, remind_date),
        )
        return cur.lastrowid


def get_tasks_for_today(user_id: int, today: str):
    """Возвращает незавершённые задачи пользователя на сегодня (и повторяющиеся)."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM tasks
               WHERE user_id = ? AND is_done = 0
               AND (remind_date = ? OR remind_date IS NULL)
               ORDER BY remind_time""",
            (user_id, today),
        ).fetchall()
        return rows


def get_due_tasks(current_time: str, today: str):
    """Задачи, которые нужно отправить прямо сейчас (для планировщика)."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM tasks
               WHERE is_done = 0 AND is_sent = 0 AND remind_time = ?
               AND (remind_date = ? OR remind_date IS NULL)""",
            (current_time, today),
        ).fetchall()
        return rows


def mark_sent(task_id: int):
    with get_connection() as conn:
        conn.execute("UPDATE tasks SET is_sent = 1 WHERE id = ?", (task_id,))


def reset_daily_sent_flags():
    """Каждую полночь сбрасываем флаг is_sent для повторяющихся задач."""
    with get_connection() as conn:
        conn.execute("UPDATE tasks SET is_sent = 0 WHERE remind_date IS NULL")


def mark_done(task_id: int, user_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE tasks SET is_done = 1 WHERE id = ? AND user_id = ?", (task_id, user_id)
        )
        return cur.rowcount > 0


def delete_task(task_id: int, user_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
        return cur.rowcount > 0
