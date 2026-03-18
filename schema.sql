-- 과목
CREATE TABLE IF NOT EXISTS subjects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    category    TEXT NOT NULL CHECK(category IN ('written', 'oral')),
    description TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- 문제
CREATE TABLE IF NOT EXISTS questions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id      INTEGER NOT NULL REFERENCES subjects(id),
    question_type   TEXT NOT NULL CHECK(question_type IN ('multiple_choice', 'oral')),
    question_text   TEXT NOT NULL,
    option_a        TEXT,
    option_b        TEXT,
    option_c        TEXT,
    option_d        TEXT,
    correct_answer  TEXT NOT NULL,
    explanation     TEXT,
    difficulty      INTEGER DEFAULT 2 CHECK(difficulty BETWEEN 1 AND 3),
    exam_year       TEXT,
    exam_type       TEXT,
    question_number INTEGER,
    comment         TEXT,
    source          TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- 시험 세션
CREATE TABLE IF NOT EXISTS test_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    test_type       TEXT NOT NULL CHECK(test_type IN ('written', 'oral')),
    selected_subjects TEXT NOT NULL,
    total_questions INTEGER NOT NULL,
    correct_count   INTEGER DEFAULT 0,
    score_percent   REAL DEFAULT 0,
    time_limit_sec  INTEGER,
    time_spent_sec  INTEGER,
    is_passed       INTEGER DEFAULT 0,
    completed       INTEGER DEFAULT 0,
    started_at      TEXT DEFAULT (datetime('now')),
    finished_at     TEXT
);

-- 개별 답변
CREATE TABLE IF NOT EXISTS user_answers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE,
    question_id     INTEGER NOT NULL REFERENCES questions(id),
    subject_id      INTEGER NOT NULL REFERENCES subjects(id),
    user_answer     TEXT,
    is_correct      INTEGER DEFAULT 0,
    answered_at     TEXT DEFAULT (datetime('now'))
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_questions_subject ON questions(subject_id);
CREATE INDEX IF NOT EXISTS idx_questions_type ON questions(subject_id, question_type);
CREATE INDEX IF NOT EXISTS idx_questions_exam ON questions(exam_year, exam_type);
CREATE INDEX IF NOT EXISTS idx_answers_session ON user_answers(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_type ON test_sessions(test_type);
