from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Literal

from dotenv import load_dotenv
try:
    # pyrefly: ignore [missing-import]
    from openai import OpenAI
except ModuleNotFoundError:
    OpenAI = None

from pydantic import BaseModel, Field


load_dotenv()

_AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
_AGNES_MODEL = "agnes-2.0-flash"


class ChecklistItem(BaseModel):
    title: str = Field(description="Short student-facing task title")
    details: str = Field(description="Concrete steps for doing the task")
    estimated_hours: float = Field(
        ge=0,
        le=80,
        description="Realistic hours needed",
    )
    priority: Literal["low", "medium", "high"]


class CourseEvent(BaseModel):
    course_code: str | None = Field(
        default=None,
        description=(
            "Course code exactly as it appears (e.g. '10.020', 'DDW', 'ST4H'). "
            "Inherit from the top-level course_code if not repeated per event."
        ),
    )
    course_name: str | None = Field(
        default=None,
        description=(
            "Full course or module name exactly as printed in the handout "
            "(e.g. 'Data Driven World', 'Science Technology and Humanity'). "
            "Inherit from the top-level course_name if not repeated per event."
        ),
    )
    title: str
    kind: Literal[
        "assignment",
        "exam",
        "quiz",
        "project",
        "presentation",
        "lab",
        "reading",
        "other",
    ]
    due_date: str = Field(
        description="ISO date YYYY-MM-DD. Use best supported date only."
    )
    due_time: str | None = Field(
        default=None,
        description="HH:MM 24-hour time if visible, otherwise null",
    )
    weight: str | None = Field(
        default=None,
        description="Grade weight if visible",
    )
    description: str = Field(
        description="Brief description of the deliverable or exam"
    )
    source_quote: str = Field(
        description="Short phrase from the handout supporting this extraction"
    )
    total_estimated_hours: float = Field(ge=0, le=200)
    checklist: list[ChecklistItem]


class ExtractedHandout(BaseModel):
    course_code: str | None = Field(
        default=None,
        description=(
            "Primary course code for this handout exactly as printed "
            "(e.g. '10.020', 'DDW', 'ST4H'). Look in the title, header, "
            "footer, and course information table."
        ),
    )
    course_name: str | None = Field(
        default=None,
        description=(
            "Primary course or module name for this handout exactly as printed. "
            "Look in the title, header, first page, and course information table."
        ),
    )
    confidence: Literal["low", "medium", "high"]
    warnings: list[str]
    events: list[CourseEvent]


class TimelineAdvice(BaseModel):
    summary: str
    risks: list[str]
    next_best_actions: list[str]


def has_agnes_key() -> bool:
    return OpenAI is not None and bool(os.getenv("AGNES_API_KEY"))


def _client() -> OpenAI:
    if OpenAI is None:
        raise RuntimeError(
            "openai package is not installed. Run: python -m pip install openai"
        )
    return OpenAI(
        api_key=os.getenv("AGNES_API_KEY"),
        base_url=_AGNES_BASE_URL,
    )


def _model() -> str:
    return os.getenv("AGNES_MODEL", _AGNES_MODEL)


def _parse_json_response(content: str, model_class: type) -> object:
    """Parse the JSON string from the model response into a Pydantic model."""
    # Strip markdown code fences if present
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
    return model_class.model_validate(json.loads(text))


def extract_handout_with_ai(
    document_text: str,
    filename: str,
    student_context: str = "",
) -> ExtractedHandout:
    """
    Extract deadline and exam data from course handout text using Agnes AI.
    """
    if not has_agnes_key():
        raise RuntimeError("AGNES_API_KEY is not set.")

    trimmed = document_text[:55_000]
    today = date.today().isoformat()

    schema = ExtractedHandout.model_json_schema()

    response = _client().chat.completions.create(
        model=_model(),
        messages=[
            {
                "role": "system",
                "content": (
                    "You extract student planner data from course handouts. "
                    "Return only events with real evidence in the document. "
                    "Do not invent deadlines. "
                    "If a date is ambiguous, add a warning. "
                    "For each assignment or exam, create a realistic checklist. "
                    "Checklist steps should be tailored to the student's context. "
                    "Use Singapore date conventions when interpreting dates. "
                    "\n\n"
                    "IMPORTANT — course identification:\n"
                    "1. Carefully read the entire document for the course code and "
                    "course name. They are usually on the first page, in the header, "
                    "footer, title block, or a course-information table.\n"
                    "2. Set the top-level course_code and course_name fields.\n"
                    "3. For EVERY event, copy the same course_code and course_name "
                    "down into that event's fields — do not leave them null unless "
                    "the document genuinely contains no course identification.\n"
                    "4. Common SUTD course-code patterns: numeric like '10.020', "
                    "or short alpha codes like 'DDW', 'ST4H', 'DES', 'HUM'.\n"
                    "\n"
                    "Respond with valid JSON matching the provided schema exactly."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Current date: {today}\n"
                    f"Filename: {filename}\n"
                    f"Student context/preferences: {student_context or 'Not provided'}\n\n"
                    "Course handout/document text:\n"
                    f"{trimmed}"
                ),
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "ExtractedHandout", "schema": schema, "strict": True},
        },
    )

    return _parse_json_response(response.choices[0].message.content, ExtractedHandout)


def explain_reschedule_with_ai(
    changed_day: str,
    old_hours: float,
    new_hours: float,
    schedule_snapshot: str,
    student_context: str = "",
) -> TimelineAdvice:
    """
    Explain the new timeline after a student changes their availability.
    """
    if not has_agnes_key():
        return TimelineAdvice(
            summary="Your timeline was recalculated using your new available hours.",
            risks=[],
            next_best_actions=["Start with the highest-priority task due soonest."],
        )

    schema = TimelineAdvice.model_json_schema()

    response = _client().chat.completions.create(
        model=_model(),
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a study planner coach. "
                    "Explain the calendar shuffle clearly and practically. "
                    "Do not guilt the student. "
                    "Focus on what changed, risks, and the next useful action. "
                    "Respond with valid JSON matching the provided schema exactly."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Student context/preferences: {student_context or 'Not provided'}\n"
                    f"Changed day: {changed_day}\n"
                    f"Old available hours: {old_hours}\n"
                    f"New available hours: {new_hours}\n\n"
                    "New schedule snapshot:\n"
                    f"{schedule_snapshot}"
                ),
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "TimelineAdvice", "schema": schema, "strict": True},
        },
    )

    return _parse_json_response(response.choices[0].message.content, TimelineAdvice)

# ── Agent chat (tool-calling) ──────────────────────────────────────────────

# Tool schemas the agent can call
AGENT_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_deadlines",
            "description": (
                "Return events/deadlines due within the next N days. "
                "Use this to answer questions like 'what is due this week?'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Look-ahead window in days (default 7).",
                        "default": 7,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_task_progress",
            "description": (
                "Return a summary of all tasks grouped by module and status "
                "(todo / doing / done). Use this to answer 'how am I doing?' "
                "or 'what tasks are still pending?'"
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_schedule_load",
            "description": (
                "Return daily scheduled study hours for the next N days. "
                "Use this to answer 'how busy is my week?' or 'when do I have free time?'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Look-ahead window in days (default 7).",
                        "default": 7,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task_hours",
            "description": (
                "Change the estimated hours for a specific task by task_id. "
                "Use this when the student says a task will take more or less time "
                "than currently estimated."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "ID of the task to update."},
                    "hours": {"type": "number", "description": "New estimated hours (0–80)."},
                },
                "required": ["task_id", "hours"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task_status",
            "description": (
                "Mark a task as todo, doing, or done. "
                "Use this when the student says they've started or finished something."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "ID of the task."},
                    "status": {
                        "type": "string",
                        "enum": ["todo", "doing", "done"],
                        "description": "New status.",
                    },
                },
                "required": ["task_id", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_availability",
            "description": (
                "Set the available study hours for a specific date. "
                "Use this when the student says they are busy, free, or want "
                "to change how much time they have on a particular day."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "ISO date YYYY-MM-DD.",
                    },
                    "hours": {
                        "type": "number",
                        "description": "Available study hours for that day (0–12).",
                    },
                },
                "required": ["date", "hours"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reschedule_all",
            "description": (
                "Trigger a full calendar reshuffle with the current availability. "
                "Call this after making multiple availability or hour changes so "
                "the student sees the updated plan."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_overdue_tasks",
            "description": (
                "Return all tasks whose deadline has already passed and are not done. "
                "Use this when the student asks what they have missed or what is overdue."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prioritise_task",
            "description": (
                "Change the priority of a task to low, medium, or high. "
                "Use this when the student says something is more or less important."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "ID of the task."},
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "New priority.",
                    },
                },
                "required": ["task_id", "priority"],
            },
        },
    },
]


def agent_chat(
    messages: list[dict],
    context_bundle: dict,
) -> tuple[str, list[dict]]:
    """
    Run one agent turn with tool-calling.

    `context_bundle` must contain:
        events_df       – pd.DataFrame from storage.events_df()
        tasks_df        – pd.DataFrame from storage.tasks_df()
        blocks_df       – pd.DataFrame of scheduled blocks (may be empty)
        availability    – dict[str, float]
        con             – sqlite3.Connection
        today           – date
        student_context – str

    Returns (assistant_text, mutations) where mutations is a list of dicts
    describing what was changed so the caller can rebuild state:
        {"type": "task_hours",   "task_id": int, "hours": float}
        {"type": "task_status",  "task_id": int, "status": str}
        {"type": "task_priority","task_id": int, "priority": str}
        {"type": "availability", "date": str,    "hours": float}
        {"type": "reschedule"}
    """
    if not has_agnes_key():
        return (
            "Agnes AI API key is not set. I can't respond without it.",
            [],
        )

    events = context_bundle["events_df"]
    tasks = context_bundle["tasks_df"]
    blocks = context_bundle["blocks_df"]
    availability: dict[str, float] = context_bundle["availability"]
    con = context_bundle["con"]
    today: date = context_bundle["today"]
    student_ctx: str = context_bundle.get("student_context", "")

    mutations: list[dict] = []

    # ── Tool implementations ──────────────────────────────────────────────

    def _get_upcoming_deadlines(days: int = 7) -> str:
        if events.empty:
            return "No deadlines found in the planner."
        cutoff = (today + timedelta(days=days)).isoformat()
        upcoming = events[events["due_date"].astype(str).str[:10] <= cutoff].copy()
        upcoming = upcoming[upcoming["due_date"].astype(str).str[:10] >= today.isoformat()]
        if upcoming.empty:
            return f"No deadlines in the next {days} days."
        lines = []
        for _, r in upcoming.iterrows():
            course = r.get("course_code") or r.get("course_name") or "?"
            lines.append(
                f"[{r['due_date'][:10]}] {r['title']} ({r['kind']}) — {course}"
                + (f" | weight: {r['weight']}" if r.get("weight") else "")
            )
        return "\n".join(lines)

    def _get_task_progress() -> str:
        if tasks.empty:
            return "No tasks in planner."
        summary: list[str] = []
        for module, grp in tasks.groupby(
            tasks.apply(
                lambda r: (r.get("course_code") or r.get("course_name") or "Unknown"), axis=1
            )
        ):
            todo = int((grp["status"] == "todo").sum())
            doing = int((grp["status"] == "doing").sum())
            done = int((grp["status"] == "done").sum())
            total = len(grp)
            summary.append(
                f"{module}: {done}/{total} done  ({doing} in-progress, {todo} todo)"
            )
            # include task IDs so agent can reference them
            for _, t in grp.iterrows():
                summary.append(
                    f"  task_id={t['task_id']}  [{t['status']:6s}]  {t['task_title']}"
                    f"  ({t['estimated_hours']:.1f}h, {t['priority']} priority)"
                )
        return "\n".join(summary)

    def _get_schedule_load(days: int = 7) -> str:
        if blocks.empty:
            return "No study blocks scheduled."
        cutoff = (today + timedelta(days=days)).isoformat()
        view = blocks[
            (blocks["date"].astype(str) >= today.isoformat())
            & (blocks["date"].astype(str) <= cutoff)
        ]
        if view.empty:
            return f"No study blocks in the next {days} days."
        daily = (
            view.groupby("date")["hours"].sum().reset_index().sort_values("date")
        )
        lines = []
        for _, r in daily.iterrows():
            avail = availability.get(str(r["date"]), 0)
            lines.append(
                f"{r['date']}  {r['hours']:.1f}h scheduled / {avail:.1f}h available"
            )
        return "\n".join(lines)

    def _get_overdue_tasks() -> str:
        if tasks.empty:
            return "No tasks in planner."
        overdue = tasks[
            (tasks["status"] != "done")
            & (tasks["due_date"].astype(str).str[:10] < today.isoformat())
        ]
        if overdue.empty:
            return "No overdue tasks."
        lines = []
        for _, t in overdue.iterrows():
            lines.append(
                f"task_id={t['task_id']}  {t['task_title']}  "
                f"due {t['due_date'][:10]}  [{t['status']}]  "
                f"({t['estimated_hours']:.1f}h)"
            )
        return "\n".join(lines)

    def _update_task_hours_fn(task_id: int, hours: float) -> str:
        from storage import update_task_hours as _uth
        _uth(con, task_id, hours)
        mutations.append({"type": "task_hours", "task_id": task_id, "hours": hours})
        return f"Updated task {task_id} estimated hours to {hours:.1f}h."

    def _update_task_status_fn(task_id: int, status: str) -> str:
        from storage import update_task_status as _uts
        _uts(con, task_id, status)
        mutations.append({"type": "task_status", "task_id": task_id, "status": status})
        return f"Marked task {task_id} as {status}."

    def _set_availability(date_str: str, hours: float) -> str:
        hours = max(0.0, min(12.0, hours))
        availability[date_str] = hours
        mutations.append({"type": "availability", "date": date_str, "hours": hours})
        return f"Set availability on {date_str} to {hours:.1f}h."

    def _reschedule_all() -> str:
        mutations.append({"type": "reschedule"})
        return "Reshuffle queued — calendar will update after this response."

    def _prioritise_task(task_id: int, priority: str) -> str:
        con.execute(
            "UPDATE tasks SET priority = ? WHERE task_id = ?",
            (priority, task_id),
        )
        con.commit()
        mutations.append({"type": "task_priority", "task_id": task_id, "priority": priority})
        return f"Set task {task_id} priority to {priority}."

    tool_dispatch = {
        "get_upcoming_deadlines": lambda args: _get_upcoming_deadlines(**args),
        "get_task_progress":      lambda args: _get_task_progress(),
        "get_schedule_load":      lambda args: _get_schedule_load(**args),
        "get_overdue_tasks":      lambda args: _get_overdue_tasks(),
        "update_task_hours":      lambda args: _update_task_hours_fn(**args),
        "update_task_status":     lambda args: _update_task_status_fn(**args),
        "set_availability":       lambda args: _set_availability(**args),
        "reschedule_all":         lambda args: _reschedule_all(),
        "prioritise_task":        lambda args: _prioritise_task(**args),
    }

    # ── System prompt ─────────────────────────────────────────────────────

    system = (
        "You are Terminus, an AI study planner assistant embedded in a student planning app. "
        "You have access to the student's deadlines, task checklist, schedule, and availability. "
        "Use the provided tools to answer questions and make changes — never fabricate data. "
        "When the student asks to change their plan, call the appropriate tool(s), then "
        "summarise what you did in plain language. "
        "Always be concise and direct. Use a helpful but no-nonsense tone. "
        "When listing tasks or deadlines, include their task_id so the student knows what you're referring to. "
        f"\nToday: {today.isoformat()}"
        f"\nStudent context: {student_ctx or 'not provided'}"
        f"\nTotal events: {len(events)}  |  Total tasks: {len(tasks)}"
        f"\nScheduled blocks: {len(blocks)}"
    )

    run_messages: list[dict] = [{"role": "system", "content": system}] + list(messages)

    # ── Agentic tool-call loop (max 6 rounds) ─────────────────────────────

    client = _client()
    model = _model()

    for _round in range(6):
        response = client.chat.completions.create(
            model=model,
            messages=run_messages,
            tools=AGENT_TOOLS,
            tool_choice="auto",
        )

        msg = response.choices[0].message
        run_messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            return msg.content or "", mutations

        # Execute each tool call
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                fn_args = {}

            if fn_name in tool_dispatch:
                result = tool_dispatch[fn_name](fn_args)
            else:
                result = f"Unknown tool: {fn_name}"

            run_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    return "I reached the maximum number of steps. Please try a simpler request.", mutations
