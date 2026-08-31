PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL COLLATE NOCASE,
    max_weekly_hours REAL NOT NULL DEFAULT 40
        CHECK (max_weekly_hours > 0 AND max_weekly_hours <= 168),
    hourly_rate REAL NOT NULL DEFAULT 0 CHECK (hourly_rate >= 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    CHECK (start_time < end_time),
    UNIQUE (employee_id, day_of_week, start_time, end_time)
);

CREATE TABLE IF NOT EXISTS historical_staffing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    workload_score REAL NOT NULL CHECK (workload_score BETWEEN 0 AND 100),
    shift_length_hours REAL NOT NULL CHECK (shift_length_hours > 0),
    required_staff INTEGER NOT NULL CHECK (required_staff > 0),
    UNIQUE (day_of_week, workload_score, shift_length_hours, required_staff)
);

CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    duration_hours REAL NOT NULL CHECK (duration_hours > 0),
    required_role TEXT NOT NULL COLLATE NOCASE,
    workload_score REAL NOT NULL CHECK (workload_score BETWEEN 0 AND 100),
    required_staff INTEGER NOT NULL CHECK (required_staff > 0),
    model_source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'approved', 'rejected')),
    decided_by TEXT,
    manager_note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    decided_at TEXT,
    CHECK (start_time < end_time)
);

CREATE TABLE IF NOT EXISTS shift_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id INTEGER NOT NULL,
    employee_id INTEGER NOT NULL,
    recommendation_score REAL NOT NULL,
    projected_weekly_hours REAL NOT NULL,
    projected_overtime_hours REAL NOT NULL DEFAULT 0,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'recommended'
        CHECK (status IN ('recommended', 'approved', 'rejected')),
    FOREIGN KEY (shift_id) REFERENCES shifts(id) ON DELETE CASCADE,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    UNIQUE (shift_id, employee_id)
);

CREATE INDEX IF NOT EXISTS idx_availability_lookup
    ON availability(day_of_week, start_time, end_time);

CREATE INDEX IF NOT EXISTS idx_shifts_week
    ON shifts(shift_date, status);

