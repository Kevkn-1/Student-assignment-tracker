# Student Assignment Tracker

A Flask + SQLite web application for managing university assignments: deadlines,
priorities, statuses, subjects and progress tracking.

**Live:** https://Kevin9.pythonanywhere.com/

## Features

- **Dashboard** — status totals, completion percentage with an overall progress
  bar, "Today's focus", due-today / upcoming / overdue summaries, priority
  breakdown, progress by subject, and links into filtered assignment lists.
- **Assignments** — full CRUD with validation, deadlines, overdue detection,
  priority and status.
- **Search, filter and sort** — keyword search over title/description, plus
  subject, status, priority and overdue filters and multiple sort orders.
- **Quick status update** — change an assignment's status straight from the
  list or detail view.
- **Subjects** — CRUD with duplicate-name protection; deletion is blocked while
  a subject still has assignments.

## Technology

| Layer | Technology |
| --- | --- |
| Presentation | HTML, CSS, JavaScript |
| Web framework | Python / Flask |
| Business logic | Service modules |
| Data access | Repository modules |
| Database | SQLite |

## Architecture

```
Presentation → Flask Views → Services → Repositories → SQLite
```

Business logic and SQL never live in templates. Views call services, services
call repositories, repositories own all SQL.

## Running locally

```bash
pip install -r requirements.txt
python app.py
```

The SQLite database is created automatically at `instance/tracker.sqlite3`.

To reset the database:

```bash
flask --app app init-db --reset
```

## Tests

```bash
python -m unittest discover -s tests
```

The suite covers services, routes, validation, filtering/sorting and dashboard
statistics.

## Project structure

```
tracker/
  views/          Flask routes (presentation layer)
  services/       Business logic and validation
  repositories/   Parameterised SQL
  templates/      Jinja templates
  static/         CSS and JavaScript
  schema.sql      Database schema
tests/            Automated test suite
```

