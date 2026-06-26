from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd


DB_PATH = Path("terminus.db")


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(db_path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_code TEXT,
            course_name TEXT,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,
            due_date TEXT NOT NULL,
            due_time TEXT,
            weight TEXT,
            description TEXT,
            source_quote TEXT,
            source_file TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            task_title TEXT NOT NULL,
            details TEXT,
            estimated_hours REAL NOT NULL DEFAULT 1,
            priority TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'todo',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(event_id) REFERENCES events(event_id) ON DELETE CASCADE
        );
        """
    )

    con.commit()


def insert_extracted_events(
    con: sqlite3.Connection,
    extracted: dict[str, Any],
    source_file: str,
) -> int:
    count = 0

    for event in extracted.get("events", []):
        cursor = con.execute(
            """
            INSERT INTO events
            (
                course_code,
                course_name,
                title,
                kind,
                due_date,
                due_time,
                weight,
                description,
                source_quote,
                source_file
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.get("course_code") or extracted.get("course_code"),
                event.get("course_name") or extracted.get("course_name"),
                event["title"],
                event["kind"],
                event["due_date"],
                event.get("due_time"),
                event.get("weight"),
                event.get("description"),
                event.get("source_quote"),
                source_file,
            ),
        )

        event_id = int(cursor.lastrowid)

        for item in event.get("checklist", []):
            con.execute(
                """
                INSERT INTO tasks
                (
                    event_id,
                    task_title,
                    details,
                    estimated_hours,
                    priority,
                    status
                )
                VALUES (?, ?, ?, ?, ?, 'todo')
                """,
                (
                    event_id,
                    item["title"],
                    item.get("details"),
                    float(item.get("estimated_hours", 1)),
                    item.get("priority", "medium"),
                ),
            )

        count += 1

    con.commit()
    return count


def events_df(con: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT
            event_id,
            course_code,
            course_name,
            title,
            kind,
            due_date,
            due_time,
            weight,
            description,
            source_quote,
            source_file,
            created_at
        FROM events
        ORDER BY due_date ASC, due_time ASC
        """,
        con,
    )


def tasks_df(con: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT
            t.task_id,
            t.event_id,
            t.task_title,
            t.details,
            t.estimated_hours,
            t.priority,
            t.status,
            e.title AS event_title,
            e.kind,
            e.due_date,
            e.due_time,
            e.course_code,
            e.course_name
        FROM tasks t
        JOIN events e ON e.event_id = t.event_id
        ORDER BY
            e.due_date ASC,
            CASE t.priority
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                ELSE 3
            END,
            t.task_id ASC
        """,
        con,
    )


def update_task_status(
    con: sqlite3.Connection,
    task_id: int,
    status: str,
) -> None:
    if status not in {"todo", "doing", "done"}:
        raise ValueError("status must be todo, doing, or done")

    con.execute(
        "UPDATE tasks SET status = ? WHERE task_id = ?",
        (status, task_id),
    )

    con.commit()


def update_task_hours(
    con: sqlite3.Connection,
    task_id: int,
    hours: float,
) -> None:
    con.execute(
        "UPDATE tasks SET estimated_hours = ? WHERE task_id = ?",
        (float(hours), task_id),
    )

    con.commit()


def delete_all(con: sqlite3.Connection) -> None:
    con.execute("DELETE FROM tasks")
    con.execute("DELETE FROM events")
    con.commit()