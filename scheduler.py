from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd


@dataclass
class ScheduledBlock:
    task_id: int
    event_id: int
    date: str
    hours: float
    title: str
    event_title: str
    kind: str
    priority: str
    due_date: str


def parse_date(value: str | date) -> date | None:
    if isinstance(value, date):
        return value

    # Handle empty or None values
    if not value or str(value).strip() == "":
        return None

    # Strip time/timezone component if model returned a full ISO datetime
    return datetime.strptime(str(value).split("T")[0], "%Y-%m-%d").date()


def date_range(start: date, end: date) -> list[date]:
    if end < start:
        return []

    days = []
    current = start

    while current <= end:
        days.append(current)
        current += timedelta(days=1)

    return days


def build_default_availability(
    start: date,
    end: date,
    weekday_hours: float,
    weekend_hours: float,
) -> dict[str, float]:
    availability: dict[str, float] = {}

    for d in date_range(start, end):
        if d.weekday() >= 5:
            availability[d.isoformat()] = float(weekend_hours)
        else:
            availability[d.isoformat()] = float(weekday_hours)

    return availability


def priority_weight(priority: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(priority, 1)


def normalise_hours(hours: float) -> float:
    return round(max(0.0, float(hours)), 2)


def reschedule_tasks(
    tasks_df: pd.DataFrame,
    availability: dict[str, float],
    start_day: date | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Greedy scheduler.

    It:
    - schedules only incomplete tasks
    - prioritises earlier due dates
    - prioritises higher-priority tasks
    - splits big tasks into smaller study blocks
    - avoids putting more work on a day than the student says they can do
    """
    if start_day is None:
        start_day = date.today()

    if tasks_df.empty:
        return pd.DataFrame(), []

    required_cols = {
        "task_id",
        "event_id",
        "task_title",
        "event_title",
        "kind",
        "priority",
        "due_date",
        "estimated_hours",
        "status",
    }

    missing = required_cols - set(tasks_df.columns)

    if missing:
        raise ValueError(f"tasks_df missing columns: {sorted(missing)}")

    remaining_capacity = {
        key: normalise_hours(value)
        for key, value in availability.items()
    }

    blocks: list[ScheduledBlock] = []
    warnings: list[str] = []

    active = tasks_df[tasks_df["status"].ne("done")].copy()

    active["due_sort"] = pd.to_datetime(active["due_date"], errors="coerce")
    active["priority_sort"] = active["priority"].map(priority_weight)

    active = active.sort_values(
        ["due_sort", "priority_sort", "estimated_hours"],
        ascending=[True, True, False],
    )

    for _, task in active.iterrows():
        due = parse_date(str(task["due_date"]))

        # Skip tasks with invalid or missing due dates
        if due is None:
            warnings.append(
                f"Skipping task '{task['task_title']}' for '{task['event_title']}' "
                f"due to missing or invalid due date."
            )
            continue

        possible_days = [
            d
            for d in date_range(start_day, due)
            if d.isoformat() in remaining_capacity
        ]

        hours_left = normalise_hours(task["estimated_hours"])

        for d in possible_days:
            if hours_left <= 0:
                break

            key = d.isoformat()
            cap = remaining_capacity.get(key, 0.0)

            if cap <= 0:
                continue

            allocation = min(cap, hours_left, 3.0)

            remaining_capacity[key] = normalise_hours(cap - allocation)
            hours_left = normalise_hours(hours_left - allocation)

            blocks.append(
                ScheduledBlock(
                    task_id=int(task["task_id"]),
                    event_id=int(task["event_id"]),
                    date=key,
                    hours=allocation,
                    title=str(task["task_title"]),
                    event_title=str(task["event_title"]),
                    kind=str(task["kind"]),
                    priority=str(task["priority"]),
                    due_date=str(task["due_date"]),
                )
            )

        if hours_left > 0:
            warnings.append(
                f"Not enough study time to fully schedule '{task['task_title']}' "
                f"for '{task['event_title']}'. "
                f"Still short by {hours_left:.1f}h before {task['due_date']}."
            )

    return pd.DataFrame([block.__dict__ for block in blocks]), warnings


def schedule_snapshot(blocks_df: pd.DataFrame, max_rows: int = 20) -> str:
    if blocks_df.empty:
        return "No scheduled blocks."

    cols = ["date", "hours", "title", "event_title", "due_date", "priority"]
    return blocks_df[cols].head(max_rows).to_string(index=False)


def day_load(blocks_df: pd.DataFrame) -> pd.DataFrame:
    if blocks_df.empty:
        return pd.DataFrame(columns=["date", "scheduled_hours"])

    return (
        blocks_df.groupby("date", as_index=False)["hours"]
        .sum()
        .rename(columns={"hours": "scheduled_hours"})
    )