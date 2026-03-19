import json
import os
import re
import sqlite3
import random
from datetime import datetime
from markupsafe import Markup
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, g

app = Flask(__name__)
app.secret_key = 'sports-instructor-local-2026'

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'quiz.db')
QUESTIONS_DIR = os.path.join(os.path.dirname(__file__), 'questions')

WRITTEN_SUBJECTS = [
    '스포츠사회학', '스포츠교육학', '스포츠심리학',
    '한국체육사', '운동생리학', '운동역학', '스포츠윤리'
]

ORAL_SUBJECTS = ['보디빌딩', '육상']


# ── Jinja2 필터: 문제 텍스트 줄바꿈 ──

@app.template_filter('nl2br')
def nl2br(text):
    """\\n을 <br>로 변환 (HTML escape 포함)"""
    if not text:
        return ''
    import html as html_mod
    text = html_mod.escape(str(text))
    text = text.replace('\n', '<br>')
    return Markup(text)


@app.template_filter('format_question')
def format_question(text):
    """\\n → <br>, |가 포함된 줄 → <table> 변환"""
    if not text:
        return ''
    import html as html_mod

    lines = str(text).split('\n')
    result = []
    table_lines = []

    def flush_table():
        if not table_lines:
            return
        html_out = '<table class="q-table">'
        for i, row in enumerate(table_lines):
            raw_cells = [c.strip() for c in row.split('|')]
            # 앞뒤 빈 셀 제거 (선행/후행 | 때문에 생기는 빈 문자열)
            while raw_cells and raw_cells[0] == '':
                raw_cells.pop(0)
            while raw_cells and raw_cells[-1] == '':
                raw_cells.pop()
            tag = 'th' if i == 0 else 'td'
            # colspan 처리: - 이면 앞 셀에 병합
            merged = []
            for cell in raw_cells:
                if cell == '-' and merged:
                    merged[-1]['span'] += 1
                else:
                    merged.append({'text': html_mod.escape(cell), 'span': 1})
            html_out += '<tr>'
            for m in merged:
                cs = f' colspan="{m["span"]}"' if m['span'] > 1 else ''
                html_out += f'<{tag}{cs}>{m["text"]}</{tag}>'
            html_out += '</tr>'
        html_out += '</table>'
        result.append(html_out)
        table_lines.clear()

    for line in lines:
        if line.count('|') >= 2:
            table_lines.append(line)
        else:
            flush_table()
            # [img:파일명] → <img> 태그 변환
            escaped = html_mod.escape(line)
            escaped = re.sub(
                r'\[img:([^\]]+)\]',
                r'<img src="/static/images/\1" class="q-img" alt="문제 이미지">',
                escaped
            )
            result.append(escaped)

    flush_table()
    return Markup('<br>'.join(result))


# ── DB 연결 ──

def get_db():
    if 'db' not in g:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db:
        db.close()


def init_db():
    db = get_db()
    with app.open_resource('schema.sql', mode='r') as f:
        db.executescript(f.read())

    # 마이그레이션: comment 컬럼 추가 (기존 DB 호환)
    try:
        db.execute('ALTER TABLE questions ADD COLUMN comment TEXT')
    except sqlite3.OperationalError:
        pass  # 이미 존재

    for name in WRITTEN_SUBJECTS:
        db.execute('INSERT OR IGNORE INTO subjects (name, category) VALUES (?, ?)', (name, 'written'))
    for name in ORAL_SUBJECTS:
        db.execute('INSERT OR IGNORE INTO subjects (name, category) VALUES (?, ?)', (name, 'oral'))
    db.commit()


# ── 문제 임포트 ──

def import_questions_from_simple_json(filepath):
    """JSON 파일에서 문제 임포트 (archive_questions.json 형식 지원)"""
    db = get_db()
    with open(filepath, 'r', encoding='utf-8') as f:
        questions = json.load(f)

    count = 0
    for q in questions:
        sub = db.execute('SELECT id FROM subjects WHERE name = ?', (q['subject'],)).fetchone()
        if not sub:
            continue

        # 중복 체크: 같은 과목 + 같은 연도 + 같은 문항번호
        if q.get('exam_year') and q.get('question_number'):
            exists = db.execute(
                'SELECT id FROM questions WHERE subject_id = ? AND exam_year = ? AND question_number = ?',
                (sub['id'], q['exam_year'], q['question_number'])
            ).fetchone()
        else:
            exists = db.execute(
                'SELECT id FROM questions WHERE question_text = ? AND subject_id = ?',
                (q['question'], sub['id'])
            ).fetchone()
        if exists:
            continue

        opts = q.get('options', [])
        db.execute('''
            INSERT INTO questions
            (subject_id, question_type, question_text, option_a, option_b, option_c, option_d,
             correct_answer, explanation, difficulty, exam_year, exam_type, question_number, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            sub['id'], q.get('type', 'multiple_choice'), q['question'],
            opts[0] if len(opts) > 0 else None,
            opts[1] if len(opts) > 1 else None,
            opts[2] if len(opts) > 2 else None,
            opts[3] if len(opts) > 3 else None,
            q.get('answer', ''),
            q.get('explanation', ''),
            q.get('difficulty', 2),
            q.get('exam_year', None),
            q.get('exam_type', None),
            q.get('question_number', None),
            q.get('source', '')
        ))
        count += 1

    db.commit()
    return count


# ── 라우트: 메인 ──

@app.route('/')
def index():
    db = get_db()
    subjects = db.execute(
        'SELECT s.*, COUNT(q.id) as question_count '
        'FROM subjects s LEFT JOIN questions q ON s.id = q.subject_id '
        'GROUP BY s.id ORDER BY s.category, s.id'
    ).fetchall()

    written = [s for s in subjects if s['category'] == 'written']
    oral = [s for s in subjects if s['category'] == 'oral']

    recent = db.execute(
        'SELECT * FROM test_sessions ORDER BY started_at DESC LIMIT 5'
    ).fetchall()

    stats = db.execute('''
        SELECT COUNT(*) as total_sessions,
               SUM(CASE WHEN is_passed = 1 THEN 1 ELSE 0 END) as passed,
               ROUND(AVG(score_percent), 1) as avg_score
        FROM test_sessions WHERE completed = 1
    ''').fetchone()

    return render_template('index.html',
                           written_subjects=written, oral_subjects=oral,
                           recent=recent, stats=stats)


# ── 라우트: 필기시험 ──

@app.route('/written/start', methods=['POST'])
def written_start():
    selected = request.form.getlist('subjects')
    if len(selected) != 5:
        flash('5과목을 선택해주세요.', 'error')
        return redirect(url_for('index'))

    db = get_db()
    all_questions = []
    for subject_name in selected:
        sub = db.execute('SELECT id FROM subjects WHERE name = ?', (subject_name,)).fetchone()
        if not sub:
            flash(f'과목을 찾을 수 없습니다: {subject_name}', 'error')
            return redirect(url_for('index'))

        questions = db.execute(
            'SELECT * FROM questions WHERE subject_id = ? AND question_type = ? ORDER BY RANDOM() LIMIT 20',
            (sub['id'], 'multiple_choice')
        ).fetchall()

        if len(questions) < 1:
            flash(f'{subject_name}: 문제가 없습니다.', 'error')
            return redirect(url_for('index'))

        all_questions.extend(questions)

    session = db.execute(
        'INSERT INTO test_sessions (test_type, selected_subjects, total_questions, time_limit_sec) VALUES (?, ?, ?, ?)',
        ('written', ','.join(selected), len(all_questions), 6000)
    )
    session_id = session.lastrowid

    for q in all_questions:
        db.execute(
            'INSERT INTO user_answers (session_id, question_id, subject_id) VALUES (?, ?, ?)',
            (session_id, q['id'], q['subject_id'])
        )
    db.commit()
    return redirect(url_for('quiz', session_id=session_id))


@app.route('/quiz/<int:session_id>')
def quiz(session_id):
    db = get_db()
    session = db.execute('SELECT * FROM test_sessions WHERE id = ?', (session_id,)).fetchone()
    if not session:
        flash('시험을 찾을 수 없습니다.', 'error')
        return redirect(url_for('index'))

    if session['completed']:
        return redirect(url_for('result', session_id=session_id))

    answers = db.execute('''
        SELECT ua.*, q.question_text, q.option_a, q.option_b, q.option_c, q.option_d,
               q.correct_answer, q.exam_year, q.exam_type, q.question_number, q.comment,
               s.name as subject_name
        FROM user_answers ua
        JOIN questions q ON ua.question_id = q.id
        JOIN subjects s ON ua.subject_id = s.id
        WHERE ua.session_id = ?
        ORDER BY s.name, ua.id
    ''', (session_id,)).fetchall()

    return render_template('quiz.html', session=session, answers=answers)


@app.route('/quiz/<int:session_id>/submit', methods=['POST'])
def submit_quiz(session_id):
    db = get_db()
    session = db.execute('SELECT * FROM test_sessions WHERE id = ?', (session_id,)).fetchone()
    if not session or session['completed']:
        return redirect(url_for('index'))

    time_spent = request.form.get('time_spent', 0, type=int)

    answers = db.execute('''
        SELECT ua.id, ua.question_id, q.correct_answer
        FROM user_answers ua
        JOIN questions q ON ua.question_id = q.id
        WHERE ua.session_id = ?
    ''', (session_id,)).fetchall()

    correct_count = 0
    for a in answers:
        user_answer = request.form.get(f'q_{a["question_id"]}', '')
        correct_ans = a['correct_answer'].upper()
        # 복수정답(ALL) 처리: 어떤 답이든 정답
        if correct_ans == 'ALL':
            is_correct = 1 if user_answer else 0
        else:
            is_correct = 1 if user_answer.upper() == correct_ans else 0
        if is_correct:
            correct_count += 1
        db.execute(
            'UPDATE user_answers SET user_answer = ?, is_correct = ?, answered_at = ? WHERE id = ?',
            (user_answer, is_correct, datetime.now().isoformat(), a['id'])
        )

    total = len(answers)
    score = round((correct_count / total * 100), 1) if total > 0 else 0

    is_passed = 1
    subjects = session['selected_subjects'].split(',')
    for subject_name in subjects:
        sub = db.execute('SELECT id FROM subjects WHERE name = ?', (subject_name,)).fetchone()
        if not sub:
            continue
        sub_result = db.execute('''
            SELECT COUNT(*) as total, SUM(is_correct) as correct
            FROM user_answers WHERE session_id = ? AND subject_id = ?
        ''', (session_id, sub['id'])).fetchone()
        if sub_result['total'] > 0:
            sub_score = (sub_result['correct'] or 0) / sub_result['total'] * 100
            if sub_score < 40:
                is_passed = 0
                break

    if score < 60:
        is_passed = 0

    db.execute('''
        UPDATE test_sessions
        SET correct_count = ?, score_percent = ?, time_spent_sec = ?,
            is_passed = ?, completed = 1, finished_at = ?
        WHERE id = ?
    ''', (correct_count, score, time_spent, is_passed, datetime.now().isoformat(), session_id))
    db.commit()

    return redirect(url_for('result', session_id=session_id))


# ── 라우트: 결과 ──

@app.route('/result/<int:session_id>')
def result(session_id):
    db = get_db()
    session = db.execute('SELECT * FROM test_sessions WHERE id = ?', (session_id,)).fetchone()
    if not session:
        flash('시험 결과를 찾을 수 없습니다.', 'error')
        return redirect(url_for('index'))

    answers = db.execute('''
        SELECT ua.*, q.question_text, q.option_a, q.option_b, q.option_c, q.option_d,
               q.correct_answer, q.explanation, q.exam_year, q.exam_type, q.question_number,
               s.name as subject_name
        FROM user_answers ua
        JOIN questions q ON ua.question_id = q.id
        JOIN subjects s ON ua.subject_id = s.id
        WHERE ua.session_id = ?
        ORDER BY s.name, ua.id
    ''', (session_id,)).fetchall()

    subject_scores = {}
    for a in answers:
        name = a['subject_name']
        if name not in subject_scores:
            subject_scores[name] = {'total': 0, 'correct': 0}
        subject_scores[name]['total'] += 1
        subject_scores[name]['correct'] += a['is_correct']

    for name in subject_scores:
        s = subject_scores[name]
        s['score'] = round(s['correct'] / s['total'] * 100, 1) if s['total'] > 0 else 0
        s['passed'] = s['score'] >= 40

    return render_template('result.html', session=session, answers=answers, subject_scores=subject_scores)


# ── 라우트: 구술시험 ──

@app.route('/oral/start', methods=['POST'])
def oral_start():
    subject_name = request.form.get('oral_subject', '보디빌딩')
    db = get_db()

    sub = db.execute('SELECT id FROM subjects WHERE name = ?', (subject_name,)).fetchone()
    if not sub:
        flash(f'종목을 찾을 수 없습니다: {subject_name}', 'error')
        return redirect(url_for('index'))

    questions = db.execute(
        'SELECT * FROM questions WHERE subject_id = ? AND question_type = ? ORDER BY RANDOM() LIMIT 4',
        (sub['id'], 'oral')
    ).fetchall()

    if len(questions) < 1:
        flash(f'{subject_name}: 구술 문제가 없습니다.', 'error')
        return redirect(url_for('index'))

    session = db.execute(
        'INSERT INTO test_sessions (test_type, selected_subjects, total_questions) VALUES (?, ?, ?)',
        ('oral', subject_name, len(questions))
    )
    session_id = session.lastrowid

    for q in questions:
        db.execute(
            'INSERT INTO user_answers (session_id, question_id, subject_id) VALUES (?, ?, ?)',
            (session_id, q['id'], q['subject_id'])
        )
    db.commit()
    return redirect(url_for('oral_quiz', session_id=session_id))


@app.route('/oral/<int:session_id>')
def oral_quiz(session_id):
    db = get_db()
    session = db.execute('SELECT * FROM test_sessions WHERE id = ?', (session_id,)).fetchone()
    if not session:
        flash('시험을 찾을 수 없습니다.', 'error')
        return redirect(url_for('index'))
    if session['completed']:
        return redirect(url_for('result', session_id=session_id))

    answers = db.execute('''
        SELECT ua.*, q.question_text, q.correct_answer, q.explanation, s.name as subject_name
        FROM user_answers ua
        JOIN questions q ON ua.question_id = q.id
        JOIN subjects s ON ua.subject_id = s.id
        WHERE ua.session_id = ?
        ORDER BY ua.id
    ''', (session_id,)).fetchall()

    return render_template('oral.html', session=session, answers=answers)


@app.route('/oral/<int:session_id>/submit', methods=['POST'])
def submit_oral(session_id):
    db = get_db()
    session = db.execute('SELECT * FROM test_sessions WHERE id = ?', (session_id,)).fetchone()
    if not session or session['completed']:
        return redirect(url_for('index'))

    answers = db.execute(
        'SELECT id, question_id FROM user_answers WHERE session_id = ?', (session_id,)
    ).fetchall()

    correct_count = 0
    for a in answers:
        user_answer = request.form.get(f'answer_{a["question_id"]}', '')
        self_score = request.form.get(f'score_{a["question_id"]}', '0')
        is_correct = 1 if self_score == '1' else 0
        if is_correct:
            correct_count += 1
        db.execute(
            'UPDATE user_answers SET user_answer = ?, is_correct = ?, answered_at = ? WHERE id = ?',
            (user_answer, is_correct, datetime.now().isoformat(), a['id'])
        )

    total = len(answers)
    score = round((correct_count / total * 100), 1) if total > 0 else 0
    is_passed = 1 if score >= 70 else 0

    db.execute('''
        UPDATE test_sessions
        SET correct_count = ?, score_percent = ?, is_passed = ?, completed = 1, finished_at = ?
        WHERE id = ?
    ''', (correct_count, score, is_passed, datetime.now().isoformat(), session_id))
    db.commit()
    return redirect(url_for('result', session_id=session_id))


# ── 라우트: 기록/통계 ──

@app.route('/history')
def history():
    db = get_db()
    sessions = db.execute(
        'SELECT * FROM test_sessions WHERE completed = 1 ORDER BY finished_at DESC'
    ).fetchall()

    subject_stats = db.execute('''
        SELECT s.name,
               COUNT(DISTINCT ua.session_id) as attempts,
               COUNT(ua.id) as total_questions,
               SUM(ua.is_correct) as correct,
               ROUND(AVG(ua.is_correct) * 100, 1) as avg_score
        FROM user_answers ua
        JOIN subjects s ON ua.subject_id = s.id
        JOIN test_sessions ts ON ua.session_id = ts.id
        WHERE ts.completed = 1
        GROUP BY s.name ORDER BY avg_score ASC
    ''').fetchall()

    return render_template('history.html', sessions=sessions, subject_stats=subject_stats)


# ── 라우트: 오답노트 ──

@app.route('/wrong')
def wrong_notes():
    db = get_db()
    subject_filter = request.args.get('subject', '')

    query = '''
        SELECT q.*, s.name as subject_name,
               COUNT(ua.id) as attempt_count,
               SUM(CASE WHEN ua.is_correct = 0 THEN 1 ELSE 0 END) as wrong_count
        FROM questions q
        JOIN subjects s ON q.subject_id = s.id
        JOIN user_answers ua ON q.id = ua.question_id
        JOIN test_sessions ts ON ua.session_id = ts.id
        WHERE ts.completed = 1 AND ua.is_correct = 0
    '''
    params = []
    if subject_filter:
        query += ' AND s.name = ?'
        params.append(subject_filter)

    query += ' GROUP BY q.id ORDER BY wrong_count DESC, q.subject_id'
    wrong_questions = db.execute(query, params).fetchall()

    subjects = db.execute('SELECT DISTINCT name FROM subjects WHERE category = "written"').fetchall()

    return render_template('wrong.html', questions=wrong_questions,
                           subjects=subjects, current_filter=subject_filter)


@app.route('/wrong/retry', methods=['POST'])
def wrong_retry():
    db = get_db()
    question_ids = request.form.getlist('question_ids')
    if not question_ids:
        flash('재시험할 문제를 선택해주세요.', 'error')
        return redirect(url_for('wrong_notes'))

    placeholders = ','.join(['?' for _ in question_ids])
    questions = db.execute(f'''
        SELECT q.*, s.name as subject_name
        FROM questions q JOIN subjects s ON q.subject_id = s.id
        WHERE q.id IN ({placeholders})
    ''', question_ids).fetchall()

    subjects = set(q['subject_name'] for q in questions)
    session = db.execute(
        'INSERT INTO test_sessions (test_type, selected_subjects, total_questions) VALUES (?, ?, ?)',
        ('written', ','.join(subjects), len(questions))
    )
    session_id = session.lastrowid

    for q in questions:
        db.execute(
            'INSERT INTO user_answers (session_id, question_id, subject_id) VALUES (?, ?, ?)',
            (session_id, q['id'], q['subject_id'])
        )
    db.commit()
    return redirect(url_for('quiz', session_id=session_id))


# ── 라우트: 문제 관리 ──

@app.route('/manage')
def manage():
    db = get_db()
    subjects = db.execute(
        'SELECT s.*, COUNT(q.id) as question_count '
        'FROM subjects s LEFT JOIN questions q ON s.id = q.subject_id '
        'GROUP BY s.id ORDER BY s.category, s.id'
    ).fetchall()
    return render_template('manage.html', subjects=subjects)


@app.route('/manage/add', methods=['POST'])
def manage_add():
    db = get_db()
    subject_name = request.form.get('subject')
    q_type = request.form.get('question_type', 'multiple_choice')
    question_text = request.form.get('question_text', '').strip()

    if not question_text:
        flash('문제를 입력해주세요.', 'error')
        return redirect(url_for('manage'))

    sub = db.execute('SELECT id FROM subjects WHERE name = ?', (subject_name,)).fetchone()
    if not sub:
        flash('과목을 찾을 수 없습니다.', 'error')
        return redirect(url_for('manage'))

    if q_type == 'multiple_choice':
        db.execute('''
            INSERT INTO questions
            (subject_id, question_type, question_text, option_a, option_b, option_c, option_d,
             correct_answer, explanation, exam_year, exam_type, question_number)
            VALUES (?, 'multiple_choice', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            sub['id'], question_text,
            request.form.get('option_a', ''),
            request.form.get('option_b', ''),
            request.form.get('option_c', ''),
            request.form.get('option_d', ''),
            request.form.get('correct_answer', 'A'),
            request.form.get('explanation', ''),
            request.form.get('exam_year', ''),
            request.form.get('exam_type', ''),
            request.form.get('question_number', None),
        ))
    else:
        db.execute('''
            INSERT INTO questions
            (subject_id, question_type, question_text, correct_answer, explanation)
            VALUES (?, 'oral', ?, ?, ?)
        ''', (sub['id'], question_text,
              request.form.get('correct_answer', ''),
              request.form.get('explanation', '')))

    db.commit()
    flash('문제가 추가되었습니다.', 'success')
    return redirect(url_for('manage'))


@app.route('/manage/import', methods=['POST'])
def manage_import():
    if 'file' not in request.files:
        flash('파일을 선택해주세요.', 'error')
        return redirect(url_for('manage'))

    file = request.files['file']
    if not file.filename:
        flash('파일을 선택해주세요.', 'error')
        return redirect(url_for('manage'))

    filename = file.filename.lower()
    upload_path = os.path.join(QUESTIONS_DIR, file.filename)
    os.makedirs(QUESTIONS_DIR, exist_ok=True)
    file.save(upload_path)

    try:
        if filename.endswith('.json'):
            count = import_questions_from_simple_json(upload_path)
            flash(f'JSON에서 {count}개 문제를 가져왔습니다.', 'success')
        elif filename.endswith('.pdf'):
            count = import_questions_from_pdf(upload_path)
            flash(f'PDF에서 {count}개 문제를 가져왔습니다.', 'success')
        else:
            flash('지원하지 않는 파일 형식입니다. (JSON, PDF만 가능)', 'error')
    except Exception as e:
        flash(f'임포트 오류: {str(e)}', 'error')

    return redirect(url_for('manage'))


# ── 라우트: 문제 편집 ──

@app.route('/edit')
def edit_list():
    db = get_db()
    subject_filter = request.args.get('subject', '')
    year_filter = request.args.get('year', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # 필터용 데이터
    subjects = db.execute('SELECT DISTINCT name FROM subjects WHERE category = "written" ORDER BY name').fetchall()
    years = db.execute('SELECT DISTINCT exam_year FROM questions WHERE exam_year IS NOT NULL AND exam_year != "" ORDER BY exam_year DESC').fetchall()

    query = '''
        SELECT q.*, s.name as subject_name
        FROM questions q
        JOIN subjects s ON q.subject_id = s.id
        WHERE 1=1
    '''
    count_query = 'SELECT COUNT(*) FROM questions q JOIN subjects s ON q.subject_id = s.id WHERE 1=1'
    params = []

    if subject_filter:
        query += ' AND s.name = ?'
        count_query += ' AND s.name = ?'
        params.append(subject_filter)
    if year_filter:
        query += ' AND q.exam_year = ?'
        count_query += ' AND q.exam_year = ?'
        params.append(year_filter)

    total = db.execute(count_query, params).fetchone()[0]
    total_pages = (total + per_page - 1) // per_page

    query += ' ORDER BY q.exam_year DESC, s.name, q.question_number LIMIT ? OFFSET ?'
    questions = db.execute(query, params + [per_page, (page - 1) * per_page]).fetchall()

    return render_template('edit.html',
                           questions=questions, subjects=subjects, years=years,
                           current_subject=subject_filter, current_year=year_filter,
                           page=page, total_pages=total_pages, total=total)


@app.route('/edit/<int:question_id>')
def edit_question(question_id):
    db = get_db()
    q = db.execute('''
        SELECT q.*, s.name as subject_name
        FROM questions q JOIN subjects s ON q.subject_id = s.id
        WHERE q.id = ?
    ''', (question_id,)).fetchone()
    if not q:
        flash('문제를 찾을 수 없습니다.', 'error')
        return redirect(url_for('edit_list'))

    subjects = db.execute('SELECT * FROM subjects ORDER BY category, name').fetchall()
    return render_template('edit_detail.html', q=q, subjects=subjects)


@app.route('/edit/<int:question_id>/save', methods=['POST'])
def save_question(question_id):
    db = get_db()
    q = db.execute('SELECT * FROM questions WHERE id = ?', (question_id,)).fetchone()
    if not q:
        flash('문제를 찾을 수 없습니다.', 'error')
        return redirect(url_for('edit_list'))

    subject_name = request.form.get('subject', '')
    sub = db.execute('SELECT id FROM subjects WHERE name = ?', (subject_name,)).fetchone()

    db.execute('''
        UPDATE questions SET
            subject_id = ?,
            question_text = ?,
            option_a = ?,
            option_b = ?,
            option_c = ?,
            option_d = ?,
            correct_answer = ?,
            comment = ?,
            exam_year = ?,
            exam_type = ?,
            question_number = ?
        WHERE id = ?
    ''', (
        sub['id'] if sub else q['subject_id'],
        request.form.get('question_text', ''),
        request.form.get('option_a', ''),
        request.form.get('option_b', ''),
        request.form.get('option_c', ''),
        request.form.get('option_d', ''),
        request.form.get('correct_answer', ''),
        request.form.get('comment', ''),
        request.form.get('exam_year', ''),
        request.form.get('exam_type', ''),
        request.form.get('question_number', None),
        question_id
    ))
    db.commit()

    flash('문제가 수정되었습니다.', 'success')
    # 필터 유지하여 목록으로 돌아가기
    return redirect(request.form.get('return_url', url_for('edit_list')))


@app.route('/edit/<int:question_id>/delete', methods=['POST'])
def delete_question(question_id):
    db = get_db()
    db.execute('DELETE FROM questions WHERE id = ?', (question_id,))
    db.commit()
    flash('문제가 삭제되었습니다.', 'success')
    return redirect(request.form.get('return_url', url_for('edit_list')))


@app.route('/api/preview', methods=['POST'])
def api_preview():
    """문제 미리보기 API — format_question 필터 적용 결과 반환"""
    data = request.get_json()
    text = data.get('text', '')
    return jsonify({'html': format_question(text)})


def import_questions_from_pdf(filepath):
    """PDF에서 문제 추출 - PyMuPDF 사용"""
    import fitz
    import re

    doc = fitz.open(filepath)
    full_text = ''
    for page in doc:
        full_text += page.get_text() + '\n'
    doc.close()

    questions = []
    lines = full_text.split('\n')
    current_q = None
    db = get_db()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        q_match = re.match(r'^(\d+)\s*[.·)]\s*(.+)', line)
        if q_match and len(q_match.group(2)) > 10:
            if current_q and current_q.get('question'):
                questions.append(current_q)
            current_q = {'question': q_match.group(2).strip(), 'options': [], 'answer': '', 'explanation': ''}
            continue

        if current_q:
            opt_match = re.match(r'^[①②③④]\s*(.+)', line)
            if opt_match:
                current_q['options'].append(opt_match.group(1).strip())
                continue

            multi_opt = re.findall(r'[①②③④]\s*([^①②③④]+)', line)
            if multi_opt and len(multi_opt) >= 2:
                for opt in multi_opt:
                    if opt.strip():
                        current_q['options'].append(opt.strip())
                continue

            ans_match = re.match(r'^정답\s*[:：]\s*([1-4①②③④ABCDabcd])', line)
            if ans_match:
                ans = ans_match.group(1)
                answer_map = {'1': 'A', '2': 'B', '3': 'C', '4': 'D',
                              '①': 'A', '②': 'B', '③': 'C', '④': 'D'}
                current_q['answer'] = answer_map.get(ans, ans.upper())
                continue

            exp_match = re.match(r'^해설\s*[:：]\s*(.+)', line)
            if exp_match:
                current_q['explanation'] = exp_match.group(1).strip()

    if current_q and current_q.get('question'):
        questions.append(current_q)

    count = 0
    default_sub = db.execute("SELECT id FROM subjects WHERE category = 'written' LIMIT 1").fetchone()
    if not default_sub:
        return 0

    for q in questions:
        if not q.get('answer'):
            continue
        opts = q.get('options', [])
        db.execute('''
            INSERT INTO questions
            (subject_id, question_type, question_text, option_a, option_b, option_c, option_d,
             correct_answer, explanation, source)
            VALUES (?, 'multiple_choice', ?, ?, ?, ?, ?, ?, ?, 'PDF 임포트')
        ''', (
            default_sub['id'], q['question'],
            opts[0] if len(opts) > 0 else '',
            opts[1] if len(opts) > 1 else '',
            opts[2] if len(opts) > 2 else '',
            opts[3] if len(opts) > 3 else '',
            q['answer'], q.get('explanation', '')
        ))
        count += 1

    db.commit()
    return count


# ── 초기화 및 실행 ──

with app.app_context():
    init_db()
    # questions/ 디렉토리의 JSON 파일 임포트
    if os.path.exists(QUESTIONS_DIR):
        for fname in sorted(os.listdir(QUESTIONS_DIR)):
            if fname.endswith('.json'):
                fpath = os.path.join(QUESTIONS_DIR, fname)
                try:
                    c = import_questions_from_simple_json(fpath)
                    if c > 0:
                        print(f'{fname}에서 {c}개 문제 임포트 완료')
                except Exception as e:
                    print(f'{fname} 임포트 실패: {e}')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
