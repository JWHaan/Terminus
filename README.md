# StudyFlow AI Planner

A local web app prototype for students. It lets you upload course handouts, extracts deadlines/exams, creates checklist tasks, and reshuffles the study calendar when your available study time changes.

## Features

- Upload PDF, DOCX, TXT, or MD course handouts.
- Extract assignments, quizzes, exams, presentations, labs, and deadlines.
- Generate progress-check checklist items for each deliverable.
- Calendar view with deadline cards and study blocks.
- Change available study hours for a day and automatically reshuffle unfinished work.
- Mark checklist items as `todo`, `doing`, or `done`.
- Export deadlines and planned study blocks as an `.ics` calendar file.
- Uses Agnes AI (Agnes 2.0 Flash) structured outputs when `AGNES_API_KEY` is set.
- Has a simple regex fallback if no API key is available.

## Folder structure

```text
student_planner_ai/
  app.py             # Streamlit UI
  ai.py              # Agnes AI extraction + reschedule explanation
  parser_utils.py    # PDF/DOCX/TXT text extraction and fallback parser
  scheduler.py       # deterministic rescheduling algorithm
  storage.py         # SQLite storage
  requirements.txt
  .env.example
```

## Setup

```bash
cd student_planner_ai
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and add your key:

```bash
AGNES_API_KEY=your_agnes_api_key_here
AGNES_MODEL=agnes-2.0-flash
```

Run the app:

```bash
streamlit run app.py
```

## How to use

1. Open the app in your browser.
2. Set your default weekday/weekend study hours in the sidebar.
3. Add tailoring notes, for example: `I prefer 1h blocks and need more time for coding.`
4. Upload a course handout PDF/DOCX/TXT/MD.
5. Click **Extract deadlines and build planner**.
6. Go to **Calendar** to view the plan.
7. When plans change, select a date, set your available hours, and click **Apply change and reshuffle**.
8. Go to **Progress check** to mark checklist items as done.
9. Download the `.ics` file if you want to import it into Google Calendar or Apple Calendar.

## Notes

- For scanned PDFs, normal text extraction may fail. Run OCR first, then upload the OCR text/PDF.
- The scheduler is deterministic and deadline-first. The OpenAI call is used to extract structured course data and explain rescheduling in a student-friendly way.
- The SQLite database is created locally as `student_planner.db`.
- Do not commit `.env` to GitHub.
