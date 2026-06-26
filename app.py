from __future__ import annotations

import calendar as py_calendar
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from ai import agent_chat, extract_handout_with_ai, explain_reschedule_with_ai, has_agnes_key
from parser_utils import SUPPORTED_EXTENSIONS, extract_text, simple_deadline_fallback
from scheduler import (
    build_default_availability,
    day_load,
    reschedule_tasks,
    schedule_snapshot,
)
from storage import (
    connect,
    delete_all,
    events_df,
    init_db,
    insert_extracted_events,
    tasks_df,
    update_task_hours,
    update_task_status,
)


st.set_page_config(
    page_title="Terminus",
    page_icon="🎯",
    layout="wide",
)


st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/icon?family=Material+Icons');

    /* ══════════════════════════════════════════════
       TERMINUS — Terminal Theme
       Palette:
         --bg        #0d0d0d   main canvas
         --surface   #141414   cards / sidebar
         --border    #2a2a2a   borders
         --green     #39ff14   phosphor accent
         --green-dim #1a7a0a   dimmed green
         --amber     #ffb700   warnings / amber
         --red       #ff3333   deadlines / errors
         --blue      #3b82f6   study blocks
         --fg        #e2e2e2   primary text
         --muted     #6b6b6b   secondary text
    ══════════════════════════════════════════════ */

    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap');

    /* ── Global canvas ── */
    html, body,
    [data-testid="stAppViewContainer"],
    [data-testid="stAppViewBlockContainer"],
    .main,
    .block-container {
        background-color: #0d0d0d !important;
        color: #e2e2e2 !important;
        font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace !important;
    }

    /* ── Hide Streamlit chrome ── */
    #MainMenu, footer, header { visibility: hidden; }
    .block-container {
        padding-top: 1.8rem !important;
        padding-bottom: 2rem !important;
        max-width: 1200px;
    }

    /* ── All text elements inherit mono + colour ── */
    p, label, li,
    .stMarkdown, .stText,
    [data-testid="stMarkdownContainer"] {
        font-family: 'JetBrains Mono', monospace !important;
        color: #e2e2e2 !important;
    }
    /* Keep Material Icons glyphs intact — do NOT override their font */
    .material-icons, span.material-icons, i.material-icons {
        font-family: 'Material Icons' !important;
        color: #6b6b6b !important;
    }

    /* ── App wordmark ── */
    .terminus-wordmark {
        font-size: 1.6rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        color: #39ff14 !important;
        margin: 0;
        line-height: 1.2;
        text-shadow: 0 0 18px rgba(57,255,20,0.35);
        font-family: 'JetBrains Mono', monospace !important;
    }
    .terminus-tagline {
        font-size: 0.78rem;
        color: #6b6b6b !important;
        margin-top: 0.15rem;
        letter-spacing: 0.04em;
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* ── Headings ── */
    h1, h2, h3, h4 {
        font-family: 'JetBrains Mono', monospace !important;
        color: #39ff14 !important;
        font-weight: 600;
        letter-spacing: 0.04em;
        text-shadow: 0 0 10px rgba(57,255,20,0.2);
    }
    h1 { font-size: 1.3rem !important; }
    h2 { font-size: 1.0rem !important; margin-top: 1.4rem !important; }
    h3 { font-size: 0.9rem !important; margin-top: 1.1rem !important; }
    h4 { font-size: 0.85rem !important; }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        border-bottom: 1px solid #2a2a2a;
        background: transparent;
        padding: 0;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 0.75rem !important;
        font-weight: 500 !important;
        font-family: 'JetBrains Mono', monospace !important;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #6b6b6b !important;
        padding: 0.6rem 1.2rem;
        border: none;
        border-bottom: 2px solid transparent;
        background: transparent !important;
        margin-bottom: -1px;
    }
    .stTabs [aria-selected="true"] {
        color: #39ff14 !important;
        border-bottom: 2px solid #39ff14 !important;
        background: transparent !important;
        text-shadow: 0 0 8px rgba(57,255,20,0.4);
    }
    .stTabs [data-baseweb="tab"]:hover { color: #b0b0b0 !important; }
    .stTabs [data-baseweb="tab-highlight"] { display: none; }
    .stTabs [data-baseweb="tab-border"]    { display: none; }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"],
    section[data-testid="stSidebar"] > div,
    section[data-testid="stSidebar"] .block-container {
        background-color: #141414 !important;
        border-right: 1px solid #2a2a2a !important;
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1.4rem !important;
    }
    section[data-testid="stSidebar"] * {
        font-family: 'JetBrains Mono', monospace !important;
        color: #e2e2e2 !important;
    }
    .sidebar-label {
        font-size: 0.65rem;
        font-weight: 600;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #39ff14 !important;
        margin-bottom: 0.7rem;
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* ── API pill ── */
    .api-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        font-size: 0.7rem;
        font-weight: 500;
        padding: 0.18rem 0.55rem;
        border-radius: 3px;
        margin-bottom: 1rem;
        font-family: 'JetBrains Mono', monospace !important;
        letter-spacing: 0.03em;
    }
    .api-pill.ok  { background: #0a1f0a; color: #39ff14 !important; border: 1px solid #1a7a0a; }
    .api-pill.err { background: #1f1000; color: #ffb700 !important; border: 1px solid #6b4200; }

    /* ── Inputs, selects, sliders ── */
    input, textarea, select,
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stNumberInput"] input {
        background-color: #141414 !important;
        color: #e2e2e2 !important;
        border: 1px solid #2a2a2a !important;
        border-radius: 3px !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.8rem !important;
        caret-color: #39ff14 !important;
    }
    input:focus, textarea:focus {
        border-color: #39ff14 !important;
        outline: none !important;
        box-shadow: 0 0 0 2px rgba(57,255,20,0.1) !important;
    }

    /* Slider track & thumb */
    [data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {
        background: #39ff14 !important;
        border-color: #39ff14 !important;
    }
    [data-testid="stSlider"] div[data-testid="stTickBar"] {
        color: #6b6b6b !important;
    }

    /* Selectbox */
    [data-testid="stSelectbox"] > div > div {
        background: #141414 !important;
        border: 1px solid #2a2a2a !important;
        color: #e2e2e2 !important;
        border-radius: 3px !important;
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* ── Buttons ── */
    .stButton > button,
    .stDownloadButton > button {
        font-size: 0.78rem !important;
        font-weight: 500 !important;
        font-family: 'JetBrains Mono', monospace !important;
        letter-spacing: 0.06em !important;
        border-radius: 3px !important;
        padding: 0.4rem 1rem !important;
        transition: all 0.12s !important;
        text-transform: uppercase !important;
    }
    .stButton > button[kind="primary"],
    .stButton > button[data-testid="baseButton-primary"] {
        background: #0a1f0a !important;
        color: #39ff14 !important;
        border: 1px solid #39ff14 !important;
        text-shadow: 0 0 6px rgba(57,255,20,0.5) !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: #39ff14 !important;
        color: #0d0d0d !important;
        text-shadow: none !important;
    }
    .stButton > button:not([kind="primary"]),
    .stDownloadButton > button {
        background: transparent !important;
        border: 1px solid #2a2a2a !important;
        color: #6b6b6b !important;
    }
    .stButton > button:not([kind="primary"]):hover,
    .stDownloadButton > button:hover {
        border-color: #6b6b6b !important;
        color: #e2e2e2 !important;
    }

    /* ── Expanders ── */
    details,
    [data-testid="stExpander"],
    div[data-testid="stExpander"] > details {
        background: #141414 !important;
        border: 1px solid #2a2a2a !important;
        border-radius: 4px !important;
    }
    details summary,
    [data-testid="stExpander"] summary {
        background: #141414 !important;
        color: #e2e2e2 !important;
        font-size: 0.8rem !important;
        font-family: 'JetBrains Mono', monospace !important;
        padding: 0.5rem 0.75rem !important;
        border-radius: 4px !important;
    }
    details summary:hover { color: #39ff14 !important; }
    details[open] summary { border-bottom: 1px solid #2a2a2a !important; border-radius: 4px 4px 0 0 !important; }
    .streamlit-expanderHeader {
        background: #141414 !important;
        color: #e2e2e2 !important;
        font-size: 0.8rem !important;
        font-family: 'JetBrains Mono', monospace !important;
        border: 1px solid #2a2a2a !important;
        border-radius: 4px !important;
        padding: 0.5rem 0.75rem !important;
    }
    .streamlit-expanderHeader:hover { color: #39ff14 !important; }
    .streamlit-expanderContent {
        background: #141414 !important;
        border: 1px solid #2a2a2a !important;
        border-top: none !important;
        border-radius: 0 0 4px 4px !important;
        padding: 0.8rem !important;
    }
    /* Expander chevron */
    [data-testid="stExpander"] svg { stroke: #6b6b6b !important; }

    /* ── Progress bars ── */
    .stProgress > div > div > div {
        background: #39ff14 !important;
        border-radius: 2px !important;
        box-shadow: 0 0 6px rgba(57,255,20,0.4) !important;
    }
    .stProgress > div > div {
        background: #1e1e1e !important;
        border-radius: 2px !important;
        height: 4px !important;
    }
    [data-testid="stProgressBar"] p {
        color: #6b6b6b !important;
        font-size: 0.72rem !important;
    }

    /* ── Dataframes / tables ── */
    .stDataFrame,
    [data-testid="stDataFrame"] {
        border: 1px solid #2a2a2a !important;
        border-radius: 4px !important;
        background: #141414 !important;
    }
    .stDataFrame th, .stDataFrame td {
        background: #141414 !important;
        color: #e2e2e2 !important;
        border-color: #2a2a2a !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.75rem !important;
    }

    /* ── Dividers ── */
    hr { border-color: #2a2a2a !important; margin: 1.4rem 0 !important; }

    /* ── Alerts ── */
    .stAlert {
        border-radius: 3px !important;
        font-size: 0.78rem !important;
        font-family: 'JetBrains Mono', monospace !important;
        border-left-width: 3px !important;
        background: #141414 !important;
    }
    /* success */
    [data-testid="stSuccess"],
    div[data-baseweb="notification"][kind="positive"] {
        background: #0a1f0a !important;
        border-left-color: #39ff14 !important;
        color: #39ff14 !important;
    }
    /* warning */
    [data-testid="stWarning"],
    div[data-baseweb="notification"][kind="warning"] {
        background: #1f1600 !important;
        border-left-color: #ffb700 !important;
        color: #ffb700 !important;
    }
    /* error */
    [data-testid="stException"],
    div[data-baseweb="notification"][kind="negative"] {
        background: #1f0000 !important;
        border-left-color: #ff3333 !important;
        color: #ff3333 !important;
    }
    /* info */
    [data-testid="stInfo"],
    div[data-baseweb="notification"][kind="info"] {
        background: #001a2f !important;
        border-left-color: #3b82f6 !important;
        color: #93c5fd !important;
    }

    /* ── File uploader ── */
    [data-testid="stFileUploader"] {
        background: #141414 !important;
        border: 1.5px dashed #2a2a2a !important;
        border-radius: 4px !important;
    }
    [data-testid="stFileUploader"]:hover {
        border-color: #39ff14 !important;
    }
    [data-testid="stFileUploader"] * {
        color: #6b6b6b !important;
        font-family: 'JetBrains Mono', monospace !important;
    }
    [data-testid="stFileUploaderDropzoneInstructions"] span {
        color: #6b6b6b !important;
    }

    /* ── Calendar grid ── */
    .cal-weekday {
        font-size: 0.65rem;
        font-weight: 600;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #39ff14 !important;
        padding-bottom: 0.4rem;
        font-family: 'JetBrains Mono', monospace !important;
        opacity: 0.7;
    }
    .calendar-day {
        border: 1px solid #2a2a2a;
        border-radius: 4px;
        padding: 0.5rem;
        min-height: 110px;
        background: #141414;
    }
    .calendar-day-empty {
        border: 1px solid #191919;
        border-radius: 4px;
        padding: 0.5rem;
        min-height: 110px;
        background: #0d0d0d;
    }
    .day-num {
        font-size: 0.7rem;
        font-weight: 600;
        color: #6b6b6b;
        margin-bottom: 0.2rem;
        font-family: 'JetBrains Mono', monospace !important;
    }
    .deadline-card {
        border-left: 2px solid #ff3333;
        padding: 0.12rem 0.3rem;
        margin: 0.18rem 0;
        font-size: 0.68rem;
        border-radius: 0 2px 2px 0;
        background: #1f0505;
        color: #ff9999 !important;
        line-height: 1.35;
        font-family: 'JetBrains Mono', monospace !important;
    }
    .study-card {
        border-left: 2px solid #3b82f6;
        padding: 0.12rem 0.3rem;
        margin: 0.18rem 0;
        font-size: 0.68rem;
        border-radius: 0 2px 2px 0;
        background: #020d1f;
        color: #93c5fd !important;
        line-height: 1.35;
        font-family: 'JetBrains Mono', monospace !important;
    }
    .small-muted {
        color: #4a4a4a !important;
        font-size: 0.68rem;
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* ── Module section header ── */
    .module-header {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        margin-bottom: 0.3rem;
        margin-top: 1.6rem;
        padding-bottom: 0.4rem;
        border-bottom: 1px solid #2a2a2a;
    }
    .module-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #39ff14 !important;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        text-shadow: 0 0 8px rgba(57,255,20,0.25);
        font-family: 'JetBrains Mono', monospace !important;
    }
    .module-badge {
        font-size: 0.65rem;
        font-weight: 500;
        color: #6b6b6b !important;
        background: #1a1a1a;
        border: 1px solid #2a2a2a;
        border-radius: 2px;
        padding: 0.08rem 0.45rem;
        font-family: 'JetBrains Mono', monospace !important;
        letter-spacing: 0.04em;
    }

    /* ── Caption / small text helpers ── */
    .stCaption, [data-testid="stCaptionContainer"] {
        color: #6b6b6b !important;
        font-size: 0.72rem !important;
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* ── Chat messages (Agent tab) ── */
    [data-testid="stChatMessage"] {
        background: #141414 !important;
        border: 1px solid #2a2a2a !important;
        border-radius: 4px !important;
        padding: 0.6rem 0.8rem !important;
        margin-bottom: 0.5rem !important;
        font-family: 'JetBrains Mono', monospace !important;
    }
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
        border-left: 3px solid #39ff14 !important;
    }
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
        border-left: 3px solid #2563eb !important;
    }
    [data-testid="stChatMessage"] p,
    [data-testid="stChatMessage"] li,
    [data-testid="stChatMessage"] code {
        font-family: 'JetBrains Mono', monospace !important;
        color: #e2e2e2 !important;
        font-size: 0.82rem !important;
    }
    [data-testid="chatAvatarIcon-user"],
    [data-testid="chatAvatarIcon-assistant"] {
        background: #1a1a1a !important;
        border: 1px solid #2a2a2a !important;
        color: #39ff14 !important;
    }
    [data-testid="stChatInput"] {
        background: #141414 !important;
        border: 1px solid #2a2a2a !important;
        border-radius: 4px !important;
    }
    [data-testid="stChatInput"] textarea {
        background: #141414 !important;
        color: #e2e2e2 !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.82rem !important;
        caret-color: #39ff14 !important;
    }
    [data-testid="stChatInput"] textarea::placeholder { color: #4a4a4a !important; }
    [data-testid="stChatInput"] button { color: #39ff14 !important; }
    [data-testid="stSpinner"] p {
        color: #39ff14 !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.75rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_connection():
    con = connect()
    init_db(con)
    return con


con = get_connection()


def student_context_from_sidebar() -> tuple[str, float, float]:
    # Sidebar wordmark
    st.sidebar.markdown(
        "<p style='font-size:1.1rem;font-weight:700;letter-spacing:0.08em;"
        "color:#39ff14;text-shadow:0 0 14px rgba(57,255,20,0.35);"
        "font-family:JetBrains Mono,monospace;margin-bottom:0.1rem;'>TERMINUS</p>"
        "<p style='font-size:0.68rem;color:#6b6b6b;margin-top:0;margin-bottom:1.2rem;"
        "font-family:JetBrains Mono,monospace;letter-spacing:0.06em;'>"
        "// AI STUDY PLANNER</p>",
        unsafe_allow_html=True,
    )

    if has_agnes_key():
        st.sidebar.markdown(
            "<span class='api-pill ok'>● Agnes AI connected</span>",
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(
            "<span class='api-pill err'>● Agnes AI not connected</span>",
            unsafe_allow_html=True,
        )
        st.sidebar.warning("Set AGNES_API_KEY in your .env file for AI extraction.")

    st.sidebar.markdown(
        "<p class='sidebar-label'>// Study hours</p>", unsafe_allow_html=True
    )

    weekday_hours = st.sidebar.slider(
        "Weekdays",
        min_value=0.0,
        max_value=8.0,
        value=2.0,
        step=0.5,
    )

    weekend_hours = st.sidebar.slider(
        "Weekends",
        min_value=0.0,
        max_value=10.0,
        value=3.0,
        step=0.5,
    )

    st.sidebar.markdown(
        "<p class='sidebar-label' style='margin-top:1.2rem;'>// Planning</p>",
        unsafe_allow_html=True,
    )

    learning_style = st.sidebar.selectbox(
        "Style",
        [
            "balanced",
            "small daily chunks",
            "heavy weekend blocks",
            "last-minute rescue mode",
        ],
    )

    support_needs = st.sidebar.text_area(
        "Notes",
        placeholder=(
            "e.g. I prefer 1h blocks, I have CCA on Tuesdays."
        ),
        height=80,
    )

    context = f"Planning style: {learning_style}. Notes: {support_needs}".strip()
    return context, weekday_hours, weekend_hours


student_context, default_weekday_hours, default_weekend_hours = student_context_from_sidebar()

st.markdown(
    "<p class='terminus-wordmark'>TERMINUS</p>"
    "<p class='terminus-tagline'>"
    "// upload handouts · extract deadlines · reshuffle your study plan"
    "</p>",
    unsafe_allow_html=True,
)


def _ics_escape(value: object) -> str:
    """
    Escape text for a simple .ics calendar file.
    This avoids needing the third-party `icalendar` package.
    """
    text = str(value or "")
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _ics_dt(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


def _ics_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def build_calendar_ics(events: pd.DataFrame, blocks: pd.DataFrame) -> bytes:
    """
    Builds an .ics export using only normal Python strings.
    No `icalendar` module needed.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Terminus//student-planner//EN",
        "CALSCALE:GREGORIAN",
    ]

    now_stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    for idx, row in events.iterrows():
        due_date = datetime.strptime(str(row["due_date"]).split("T")[0], "%Y-%m-%d").date()
        uid = f"deadline-{idx}-{_ics_date(due_date)}@terminus.local"

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_stamp}",
                f"SUMMARY:{_ics_escape('Deadline: ' + str(row['title']))}",
            ]
        )

        if pd.notna(row.get("due_time")) and row.get("due_time"):
            try:
                due_time = datetime.strptime(str(row["due_time"]), "%H:%M").time()
                start = datetime.combine(due_date, due_time)
                end = start + timedelta(minutes=30)

                lines.append(f"DTSTART:{_ics_dt(start)}")
                lines.append(f"DTEND:{_ics_dt(end)}")

            except Exception:
                lines.append(f"DTSTART;VALUE=DATE:{_ics_date(due_date)}")
        else:
            lines.append(f"DTSTART;VALUE=DATE:{_ics_date(due_date)}")

        lines.append(f"DESCRIPTION:{_ics_escape(row.get('description') or '')}")
        lines.append("END:VEVENT")

    for idx, row in blocks.iterrows():
        block_date = datetime.strptime(str(row["date"]), "%Y-%m-%d").date()

        start = datetime.combine(block_date, time(9, 0))
        duration = timedelta(hours=float(row["hours"]))
        end = start + duration

        uid = f"study-{idx}-{_ics_dt(start)}@terminus.local"

        description = (
            f"For: {row['event_title']}\n"
            f"Due: {row['due_date']}\n"
            f"Priority: {row['priority']}"
        )

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_stamp}",
                f"SUMMARY:{_ics_escape('Study: ' + str(row['title']))}",
                f"DTSTART:{_ics_dt(start)}",
                f"DTEND:{_ics_dt(end)}",
                f"DESCRIPTION:{_ics_escape(description)}",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def render_month_calendar(
    year: int,
    month: int,
    events: pd.DataFrame,
    blocks: pd.DataFrame,
) -> None:
    st.markdown(
        f"<p style='font-size:0.85rem;font-weight:600;color:#39ff14;"
        f"letter-spacing:0.06em;text-transform:uppercase;"
        f"font-family:JetBrains Mono,monospace;margin-bottom:0.8rem;'>"
        f"{py_calendar.month_name[month]} {year}</p>",
        unsafe_allow_html=True,
    )

    week_days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    header_cols = st.columns(7)

    for col, name in zip(header_cols, week_days):
        col.markdown(f"<div class='cal-weekday'>{name}</div>", unsafe_allow_html=True)

    month_matrix = py_calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)

    for week in month_matrix:
        cols = st.columns(7)

        for col, day_num in zip(cols, week):
            if day_num == 0:
                col.markdown(
                    "<div class='calendar-day-empty'></div>",
                    unsafe_allow_html=True,
                )
                continue

            day = date(year, month, day_num).isoformat()

            if not events.empty:
                day_events = events[events["due_date"].astype(str).eq(day)]
            else:
                day_events = pd.DataFrame()

            if not blocks.empty:
                day_blocks = blocks[blocks["date"].astype(str).eq(day)]
            else:
                day_blocks = pd.DataFrame()

            html = [f"<div class='calendar-day'><div class='day-num'>{day_num}</div>"]

            for _, ev in day_events.iterrows():
                html.append(
                    f"<div class='deadline-card'>"
                    f"<strong>{str(ev['kind']).title()}</strong><br>"
                    f"{ev['title']}<br>"
                    f"<span class='small-muted'>Due</span>"
                    f"</div>"
                )

            for _, block in day_blocks.iterrows():
                html.append(
                    f"<div class='study-card'>"
                    f"<strong>{float(block['hours']):.1f}h</strong> "
                    f"{block['title']}<br>"
                    f"<span class='small-muted'>{block['event_title']}</span>"
                    f"</div>"
                )

            html.append("</div>")
            col.markdown("".join(html), unsafe_allow_html=True)


def ensure_availability(
    events: pd.DataFrame,
    weekday_hours: float,
    weekend_hours: float,
) -> dict[str, float]:
    today = date.today()

    if events.empty:
        end = today + timedelta(days=30)
    else:
        max_due = pd.to_datetime(events["due_date"], errors="coerce").max()

        if pd.notna(max_due):
            end = max(today + timedelta(days=30), max_due.date())
        else:
            end = today + timedelta(days=30)

    desired_range = build_default_availability(
        start=today,
        end=end,
        weekday_hours=weekday_hours,
        weekend_hours=weekend_hours,
    )

    if "availability" not in st.session_state:
        st.session_state.availability = desired_range
    else:
        for key, value in desired_range.items():
            st.session_state.availability.setdefault(key, value)

    return st.session_state.availability


def make_extracted_payload(text: str, filename: str) -> tuple[dict, list[str]]:
    warnings: list[str] = []

    if has_agnes_key():
        extracted = extract_handout_with_ai(
            document_text=text,
            filename=filename,
            student_context=student_context,
        )

        payload = extracted.model_dump()
        warnings.extend(payload.get("warnings", []))
        return payload, warnings

    fallback_events = simple_deadline_fallback(text, filename)
    warnings.append(
        "Used basic regex fallback because AGNES_API_KEY is not set. "
        "Extraction may miss items."
    )

    return {
        "course_code": None,
        "course_name": None,
        "confidence": "low",
        "warnings": warnings,
        "events": fallback_events,
    }, warnings


upload_tab, calendar_tab, checklist_tab, data_tab, agent_tab = st.tabs(
    ["Upload", "Calendar", "Progress", "Data", "Agent"]
)


with upload_tab:
    st.markdown("#### Import handouts")
    st.markdown(
        "<p style='font-size:0.75rem;color:#6b6b6b;margin-top:-0.4rem;"
        "margin-bottom:0.8rem;font-family:JetBrains Mono,monospace;'>"
        "// PDF · DOCX · TXT · MD — AI extracts every deadline.</p>",
        unsafe_allow_html=True,
    )

    files = st.file_uploader(
        "Upload one or more course documents",
        type=[ext.replace(".", "") for ext in SUPPORTED_EXTENSIONS],
        accept_multiple_files=True,
    )

    if st.button(
        "Extract deadlines and build planner",
        type="primary",
        disabled=not files,
    ):
        total_inserted = 0

        for uploaded in files or []:
            try:
                text = extract_text(uploaded, uploaded.name)

                if not text or len(text.strip()) < 50:
                    st.warning(
                        f"{uploaded.name}: I could not extract much text. "
                        "If it is a scanned PDF, use OCR first."
                    )
                    continue

                payload, warnings = make_extracted_payload(text, uploaded.name)

                inserted = insert_extracted_events(
                    con=con,
                    extracted=payload,
                    source_file=uploaded.name,
                )

                total_inserted += inserted

                st.success(
                    f"{uploaded.name}: added {inserted} event(s). "
                    f"Confidence: {payload.get('confidence', 'unknown')}"
                )

                for warning in warnings:
                    st.warning(warning)

            except Exception as exc:
                st.error(f"{uploaded.name}: {exc}")

        if total_inserted:
            st.rerun()

    st.divider()

    st.markdown(
        "<p style='font-size:0.68rem;color:#ff3333;letter-spacing:0.08em;"
        "text-transform:uppercase;font-family:JetBrains Mono,monospace;"
        "margin-top:0.5rem;'>// Danger zone</p>",
        unsafe_allow_html=True,
    )
    if st.button("Delete all planner data"):
        delete_all(con)
        st.session_state.pop("availability", None)
        st.success("Planner data cleared.")
        st.rerun()


all_events = events_df(con)
all_tasks = tasks_df(con)

availability = ensure_availability(
    events=all_events,
    weekday_hours=default_weekday_hours,
    weekend_hours=default_weekend_hours,
)

if not all_tasks.empty:
    blocks, schedule_warnings = reschedule_tasks(
        tasks_df=all_tasks,
        availability=availability,
        start_day=date.today(),
    )
else:
    blocks, schedule_warnings = pd.DataFrame(), []


with calendar_tab:
    if all_events.empty:
        st.info("Upload a handout first to create calendar items.")

    else:
        c1, c2, c3 = st.columns([1, 1, 2])
        today = date.today()

        with c1:
            selected_month = st.selectbox(
                "Month",
                list(range(1, 13)),
                index=today.month - 1,
                format_func=lambda m: py_calendar.month_name[m],
            )

        with c2:
            selected_year = st.number_input(
                "Year",
                min_value=today.year - 1,
                max_value=today.year + 5,
                value=today.year,
            )

        with c3:
            st.markdown(
                "<p style='font-size:0.68rem;font-weight:600;color:#6b6b6b;"
                "letter-spacing:0.1em;text-transform:uppercase;margin-bottom:0.2rem;"
                "font-family:JetBrains Mono,monospace;'>// Adjust availability</p>",
                unsafe_allow_html=True,
            )
            selected_day = st.date_input("Day", value=today)
            key = selected_day.isoformat()

            old_hours = float(availability.get(key, default_weekday_hours))

            new_hours = st.number_input(
                "Available study hours on that day",
                min_value=0.0,
                max_value=12.0,
                value=old_hours,
                step=0.5,
            )

            if st.button("Apply change and reshuffle"):
                st.session_state.availability[key] = float(new_hours)
                availability = st.session_state.availability

                if not all_tasks.empty:
                    blocks, schedule_warnings = reschedule_tasks(
                        tasks_df=all_tasks,
                        availability=availability,
                        start_day=date.today(),
                    )

                st.success(f"Updated {key}: {old_hours:.1f}h → {new_hours:.1f}h.")

                advice = explain_reschedule_with_ai(
                    changed_day=key,
                    old_hours=old_hours,
                    new_hours=float(new_hours),
                    schedule_snapshot=schedule_snapshot(blocks),
                    student_context=student_context,
                )

                st.info(advice.summary)

                if advice.risks:
                    st.write("Risks:", "; ".join(advice.risks))

                if advice.next_best_actions:
                    st.write("Next best action:", advice.next_best_actions[0])

        load_df = day_load(blocks)

        if not load_df.empty:
            next_7 = load_df[
                pd.to_datetime(load_df["date"])
                .dt.date.between(today, today + timedelta(days=7))
            ]

            st.markdown(
                "<p style='font-size:0.68rem;font-weight:600;color:#6b6b6b;"
                "letter-spacing:0.1em;text-transform:uppercase;margin-bottom:0.3rem;"
                "font-family:JetBrains Mono,monospace;'>// Next 7 days</p>",
                unsafe_allow_html=True,
            )
            st.dataframe(next_7, use_container_width=True, hide_index=True)

        for warning in schedule_warnings:
            st.warning(warning)

        render_month_calendar(
            year=int(selected_year),
            month=int(selected_month),
            events=all_events,
            blocks=blocks,
        )

        st.download_button(
            "Download calendar as .ics",
            data=build_calendar_ics(all_events, blocks),
            file_name="terminus_calendar.ics",
            mime="text/calendar",
        )


with checklist_tab:
    if all_tasks.empty:
        st.info("No tasks yet. Upload a handout first.")

    else:
        # Build a human-readable module label for grouping
        def _module_label(code: object, name: object) -> str:
            code = str(code).strip() if code and str(code) not in ("None", "") else ""
            name = str(name).strip() if name and str(name) not in ("None", "") else ""
            if code and name:
                return f"{code} — {name}"
            return code or name or "Unknown module"

        all_tasks["_module"] = all_tasks.apply(
            lambda r: _module_label(r.get("course_code"), r.get("course_name")),
            axis=1,
        )

        # Sort modules: named ones first, then "Unknown module"
        module_order = sorted(
            all_tasks["_module"].unique(),
            key=lambda m: (m == "Unknown module", m),
        )

        for module in module_order:
            module_tasks = all_tasks[all_tasks["_module"] == module]

            mod_done = int((module_tasks["status"] == "done").sum())
            mod_total = len(module_tasks)
            mod_pct = 0 if mod_total == 0 else mod_done / mod_total

            st.markdown(
                f"<div class='module-header'>"
                f"<span class='module-title'>{module}</span>"
                f"<span class='module-badge'>{mod_done}/{mod_total} done</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.progress(mod_pct)

            event_groups = module_tasks.groupby(
                ["event_id", "event_title", "due_date", "kind"],
                sort=False,
            )

            for (event_id, event_title, due_date, kind), group in event_groups:
                done = int((group["status"] == "done").sum())
                total = len(group)
                pct = 0 if total == 0 else done / total

                with st.expander(
                    f"{event_title} — {str(kind).title()} — due {str(due_date).split('T')[0]} "
                    f"({done}/{total} done)",
                    expanded=True,
                ):
                    st.progress(pct)

                    for _, task in group.iterrows():
                        c1, c2, c3 = st.columns([3, 1, 1])

                        with c1:
                            st.markdown(f"**{task['task_title']}**")
                            st.caption(task.get("details") or "")

                        with c2:
                            status = st.selectbox(
                                "Status",
                                ["todo", "doing", "done"],
                                index=["todo", "doing", "done"].index(task["status"]),
                                key=f"status_{task['task_id']}",
                            )

                            if status != task["status"]:
                                update_task_status(
                                    con=con,
                                    task_id=int(task["task_id"]),
                                    status=status,
                                )
                                st.rerun()

                        with c3:
                            hours = st.number_input(
                                "Hours",
                                min_value=0.0,
                                max_value=80.0,
                                value=float(task["estimated_hours"]),
                                step=0.5,
                                key=f"hours_{task['task_id']}",
                            )

                            if abs(float(hours) - float(task["estimated_hours"])) > 1e-9:
                                update_task_hours(
                                    con=con,
                                    task_id=int(task["task_id"]),
                                    hours=float(hours),
                                )
                                st.rerun()

            st.divider()


with data_tab:

    st.subheader("Events")
    st.dataframe(all_events, use_container_width=True, hide_index=True)

    st.subheader("Tasks")
    st.dataframe(all_tasks, use_container_width=True, hide_index=True)

    st.subheader("Scheduled blocks")
    st.dataframe(blocks, use_container_width=True, hide_index=True)


with agent_tab:
    # ── Suggested prompts shown before any conversation ───────────────────
    SUGGESTED_PROMPTS = [
        "What is due this week?",
        "What tasks are still pending?",
        "Am I on track to finish everything on time?",
        "What is overdue?",
        "How busy is my schedule this week?",
        "Mark task 1 as done",
        "I'm busy on Saturday, set my hours to 0",
        "Increase the hours for task 3 to 4h",
        "Set task 5 to high priority and reshuffle my plan",
    ]

    # ── Initialise chat history in session state ──────────────────────────
    if "agent_messages" not in st.session_state:
        st.session_state.agent_messages: list[dict] = []

    # ── Header ────────────────────────────────────────────────────────────
    st.markdown(
        "<p class='terminus-wordmark' style='font-size:1.1rem;'>// TERMINUS AGENT</p>"
        "<p class='terminus-tagline'>Ask anything about your deadlines, tasks, "
        "and schedule. I can also update your plan.</p>",
        unsafe_allow_html=True,
    )

    if not has_agnes_key():
        st.warning("Set AGNES_API_KEY in your .env file to use the agent.")
    elif all_events.empty:
        st.info("Upload a handout first so the agent has data to work with.")

    # ── Suggested prompts (only shown when chat is empty) ─────────────────
    if not st.session_state.agent_messages:
        st.markdown(
            "<p style='font-size:0.7rem;color:#6b6b6b;letter-spacing:0.08em;"
            "text-transform:uppercase;font-family:JetBrains Mono,monospace;"
            "margin-bottom:0.5rem;'>// Try asking</p>",
            unsafe_allow_html=True,
        )
        prompt_cols = st.columns(3)
        for i, prompt in enumerate(SUGGESTED_PROMPTS):
            if prompt_cols[i % 3].button(
                prompt,
                key=f"suggestion_{i}",
                use_container_width=True,
            ):
                st.session_state.agent_messages.append(
                    {"role": "user", "content": prompt}
                )
                st.rerun()

    st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)

    # ── Render existing messages ──────────────────────────────────────────
    for msg in st.session_state.agent_messages:
        role = msg["role"]
        if role not in ("user", "assistant"):
            continue
        with st.chat_message(role):
            st.markdown(msg["content"])

    # ── Chat input ────────────────────────────────────────────────────────
    user_input = st.chat_input("Ask the agent…", disabled=not has_agnes_key())

    if user_input:
        # Append user message and display it immediately
        st.session_state.agent_messages.append(
            {"role": "user", "content": user_input}
        )
        with st.chat_message("user"):
            st.markdown(user_input)

        # Build context bundle from current app state
        context_bundle = {
            "events_df": all_events,
            "tasks_df": all_tasks,
            "blocks_df": blocks,
            "availability": availability,
            "con": con,
            "today": date.today(),
            "student_context": student_context,
        }

        with st.chat_message("assistant"):
            with st.spinner(""):
                try:
                    reply, mutations = agent_chat(
                        messages=st.session_state.agent_messages,
                        context_bundle=context_bundle,
                    )
                except Exception as exc:
                    reply = f"Error: {exc}"
                    mutations = []

            st.markdown(reply)

        # Append assistant reply to history
        st.session_state.agent_messages.append(
            {"role": "assistant", "content": reply}
        )

        # ── Apply any mutations the agent made ───────────────────────────
        needs_rerun = False
        needs_reschedule = False

        for m in mutations:
            if m["type"] in ("task_hours", "task_status", "task_priority"):
                needs_rerun = True
            elif m["type"] == "availability":
                if "availability" not in st.session_state:
                    st.session_state.availability = {}
                st.session_state.availability[m["date"]] = m["hours"]
                needs_reschedule = True
                needs_rerun = True
            elif m["type"] == "reschedule":
                needs_reschedule = True
                needs_rerun = True

        if needs_reschedule and not all_tasks.empty:
            reschedule_tasks(
                tasks_df=all_tasks,
                availability=st.session_state.get("availability", availability),
                start_day=date.today(),
            )

        if needs_rerun:
            st.rerun()

    # ── Clear chat button ─────────────────────────────────────────────────
    if st.session_state.agent_messages:
        st.markdown("<div style='height:0.3rem;'></div>", unsafe_allow_html=True)
        if st.button("Clear conversation", key="clear_agent_chat"):
            st.session_state.agent_messages = []
            st.rerun()
