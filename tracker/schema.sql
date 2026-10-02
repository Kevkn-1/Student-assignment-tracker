-- Student Assignment Tracker schema (SQLite)
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (
        length(trim(name)) BETWEEN 1 AND 100
    ),
    code TEXT CHECK (
        code IS NULL
        OR length(code) <= 20
    ),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE RESTRICT,
    title TEXT NOT NULL CHECK (
        length(trim(title)) BETWEEN 1 AND 150
    ),
    description TEXT CHECK (
        description IS NULL
        OR length(description) <= 2000
    ),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'in_progress', 'completed')
    ),
    deadline TEXT NOT NULL -- ISO date, YYYY-MM-DD
    CHECK (
        date(deadline) IS NOT NULL
        AND date(deadline) = deadline
    ),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_assignments_subject ON assignments(subject_id);
CREATE INDEX IF NOT EXISTS idx_assignments_status ON assignments(status);
CREATE INDEX IF NOT EXISTS idx_assignments_deadline ON assignments(deadline);