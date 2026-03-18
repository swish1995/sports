#!/usr/bin/env python3
"""기출문제 PDF 파싱 → JSON 변환 스크립트"""
import fitz  # PyMuPDF
import re
import json
import os
import sys
import unicodedata

ARCHIVE_DIR = os.path.join(os.path.dirname(__file__), 'archive')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'questions')

# 과목 코드 매핑
SUBJECT_CODES = {
    '11': '스포츠사회학', '22': '스포츠교육학', '33': '스포츠심리학',
    '44': '한국체육사', '55': '운동생리학', '66': '운동역학', '77': '스포츠윤리',
    '01': '특수체육론', '02': '유아체육론', '03': '노인체육론',
}

# 2급 생활스포츠지도사 관련 과목만
VALID_SUBJECTS = ['스포츠사회학', '스포츠교육학', '스포츠심리학', '한국체육사',
                   '운동생리학', '운동역학', '스포츠윤리']

# 정답 데이터 (정답 PDF에서 수동 추출 - A형 기준)
# 0 = 복수정답(전부 인정)
ANSWER_KEYS = {
    '2018': {
        '스포츠사회학': [1,1,3,1,3,4,2,4,3,2,1,3,2,4,4,2,2,4,2,3],
        '스포츠교육학': [3,1,2,4,3,4,4,1,1,3,4,2,2,1,3,4,1,2,2,3],
        '스포츠심리학': [2,3,3,4,2,2,4,1,4,1,4,3,4,1,3,1,4,2,1,3],
        '스포츠윤리':   [2,4,2,3,2,4,2,2,4,1,1,4,3,1,4,3,0,1,3,4],  # 17=①③
        '운동생리학':   [4,1,1,1,3,1,3,2,4,2,2,2,4,2,1,1,3,2,4,3],
        '운동역학':     [4,2,3,1,3,4,3,3,1,2,4,2,4,1,4,2,4,3,2,1],
        '한국체육사':   [1,4,2,3,1,4,3,1,4,2,1,3,3,4,2,2,4,2,3,1],
    },
    '2019': {
        '스포츠사회학': [4,1,2,2,4,2,1,3,1,2,3,1,2,3,1,3,3,4,4,4],
        '스포츠교육학': [2,1,4,3,2,1,3,1,4,4,4,4,3,2,1,4,1,3,3,2],
        '스포츠심리학': [1,1,1,1,1,2,2,1,4,4,4,3,1,3,2,4,1,2,1,3],
        '한국체육사':   [4,3,4,3,1,3,1,2,2,3,4,1,4,1,1,4,3,4,3,2],
        '운동생리학':   [3,4,2,3,4,1,3,1,1,3,3,4,2,2,2,4,1,4,2,1],
        '운동역학':     [3,3,4,4,3,3,4,1,4,4,4,2,2,2,1,3,4,1,1,3],
        '스포츠윤리':   [3,2,3,1,2,1,2,3,4,1,4,4,2,1,4,4,1,3,2,4],
    },
    '2020': {
        '스포츠사회학': [2,1,3,2,4,4,4,2,1,4,3,3,4,2,2,1,3,1,3,1],
        '스포츠교육학': [4,3,1,3,1,1,2,4,1,2,2,4,1,3,3,2,2,3,4,4],
        '스포츠심리학': [3,1,2,3,4,4,3,2,2,4,1,4,2,3,4,1,1,3,3,1],
        '한국체육사':   [4,2,4,2,1,3,3,4,3,4,1,4,2,1,1,4,2,1,2,3],
        '운동생리학':   [2,3,4,3,4,1,4,3,1,1,3,2,3,1,2,1,4,2,2,4],
        '운동역학':     [1,1,4,4,1,1,4,1,3,3,3,4,4,2,3,2,4,2,3,3],
        '스포츠윤리':   [1,1,3,2,3,2,3,4,4,1,2,4,2,1,4,2,4,4,1,3],
    },
    '2021': {
        '스포츠사회학': [2,1,4,2,4,2,4,3,1,3,1,3,1,3,4,2,2,3,1,4],
        '스포츠교육학': [3,1,1,2,4,2,2,3,4,3,1,2,2,3,4,3,1,4,4,1],
        '스포츠심리학': [4,4,1,2,1,3,4,3,2,1,3,1,2,2,3,2,4,3,4,1],
        '한국체육사':   [2,1,2,4,3,1,2,2,3,4,1,4,1,1,4,3,4,3,2,3],
        '운동생리학':   [4,3,1,2,2,2,1,3,2,4,1,4,1,1,4,3,2,4,1,4],
        '운동역학':     [2,1,3,2,3,2,2,4,3,2,1,2,1,2,1,1,4,2,1,3],
        '스포츠윤리':   [2,1,4,4,3,3,2,4,4,3,2,1,3,2,1,2,4,3,1,1],
    },
    '2022': {
        '스포츠사회학': [1,4,1,3,2,3,3,4,1,1,2,1,2,4,3,4,2,2,3,2],
        '스포츠교육학': [1,3,3,4,3,4,4,1,2,2,2,1,0,4,3,4,2,2,3,1],  # 13=①④
        '스포츠심리학': [1,3,3,4,1,3,1,3,4,1,2,4,4,2,2,1,2,3,4,4],
        '한국체육사':   [4,3,2,4,2,1,4,4,3,3,1,1,2,1,2,1,4,2,3,3],
        '운동생리학':   [1,4,3,3,4,1,2,3,2,4,3,2,4,1,2,1,1,3,4,2],
        '운동역학':     [4,3,2,3,3,4,2,1,3,1,2,4,1,4,2,2,4,4,3,3],
        '스포츠윤리':   [4,3,0,1,2,2,1,0,1,4,1,2,2,4,2,3,3,3,1,3],  # 3=①②③, 8=③④
    },
    '2023': {
        '스포츠사회학': [1,2,1,0,3,1,4,2,1,2,1,3,2,4,3,4,4,3,0,3],  # 4=②③④, 20=①②③④
        '스포츠교육학': [1,3,1,4,4,2,3,2,1,2,3,1,4,4,1,2,3,4,3],
        '스포츠심리학': [3,1,4,4,3,4,2,2,1,2,3,2,1,3,1,1,2,3,1,4],
        '한국체육사':   [4,1,3,4,2,2,2,3,1,3,1,4,3,0,1,4,3,0,4,1],  # 14=②③, 18=②④
        '운동생리학':   [2,1,4,1,3,4,4,1,2,3,3,1,2,2,3,3,2,1,4,4],
        '운동역학':     [4,2,1,4,1,4,2,3,4,1,1,3,1,3,2,4,2,3,2,3],
        '스포츠윤리':   [1,3,1,3,2,2,4,4,1,1,3,2,2,3,1,2,2,3,4,4],
    },
    '2024': {
        '스포츠사회학': [4,1,4,3,3,1,4,2,1,2,1,3,2,4,4,4,3,2,0,2],  # 19=①③
        '스포츠교육학': [1,4,3,2,2,4,3,1,2,4,3,1,4,2,3,2,3,1,4,1],
        '스포츠심리학': [2,1,2,2,3,3,2,3,1,4,2,3,3,4,1,1,3,2,4,4],
        '한국체육사':   [2,2,3,1,4,1,1,3,3,3,1,4,2,2,4,1,4,3,2,4],
        '운동생리학':   [2,3,1,4,4,1,4,4,2,3,2,2,0,4,3,3,1,1,1,2],  # 13=①③
        '운동역학':     [0,3,1,2,1,2,4,3,3,4,4,3,4,0,4,4,3,3,2,4],  # 1=①②③④, 14=②③
        '스포츠윤리':   [2,4,4,1,1,2,2,2,3,1,4,4,0,1,3,1,3,3,3,2],  # 13=①②③④
    },
    '2025': {
        '스포츠사회학': [1,2,1,3,3,2,3,4,4,1,1,3,3,1,4,2,2,2,4,4],
        '스포츠교육학': [1,3,1,4,2,4,3,2,2,3,2,1,4,4,2,3,4,3,1,2],
        '스포츠심리학': [2,4,1,1,2,2,3,2,4,2,3,1,1,4,3,3,3,4,1,4],
        '한국체육사':   [2,4,1,3,2,3,1,1,4,2,2,2,3,2,4,1,4,3,3,4],
        '운동생리학':   [1,1,2,2,3,4,4,4,4,1,2,2,1,3,3,1,3,3,4,2],
        '운동역학':     [4,1,2,4,1,2,2,1,3,3,2,3,2,4,3,4,4,3,1,2],
        '스포츠윤리':   [2,3,2,3,1,1,2,0,1,3,1,4,2,3,4,2,4,3,2,2],  # 8=①②③④
    },
}


def extract_text_from_pdf(filepath):
    """PDF에서 전체 텍스트 추출"""
    doc = fitz.open(filepath)
    pages = []
    for page in doc:
        pages.append(page.get_text("text"))
    doc.close()
    return pages


def parse_answer_pdf(filepath):
    """정답 PDF 파싱 시도"""
    pages = extract_text_from_pdf(filepath)
    full_text = '\n'.join(pages)
    # 정답 PDF는 이미지 기반인 경우가 많아 텍스트 추출이 어려울 수 있음
    return full_text


def parse_questions_from_text(full_text, year, exam_type='A'):
    """문제 텍스트를 파싱하여 과목별 문제 리스트 반환"""
    questions = {}
    current_subject = None
    current_question = None
    current_options = []
    current_q_num = 0

    lines = full_text.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        i += 1

        if not line:
            continue

        # 비관련 과목 감지 (특수체육론, 유아체육론, 노인체육론) → 파싱 중단
        skip_match = re.match(r'^(특수체육론|유아체육론|노인체육론)', line)
        if skip_match:
            if current_subject and current_question:
                save_question(questions, current_subject, current_q_num, current_question, current_options)
            current_subject = None
            current_question = None
            current_options = []
            continue

        # 과목 헤더 감지: "스포츠사회학 (11)" 또는 "스포츠사회학（11）" 또는 "스포츠사회학"
        subject_match = re.match(r'^(스포츠사회학|스포츠교육학|스포츠심리학|한국체육사|운동생리학|운동역학|스포츠윤리)\s*(?:[\(（]\s*\d+\s*[\)）])?', line)
        if subject_match:
            # 이전 문제 저장
            if current_subject and current_question:
                save_question(questions, current_subject, current_q_num, current_question, current_options)

            current_subject = subject_match.group(1)
            if current_subject not in questions:
                questions[current_subject] = []
            current_question = None
            current_options = []
            current_q_num = 0
            continue

        if not current_subject:
            continue

        # 페이지 헤더/푸터 스킵
        if re.match(r'^\d+\s*면$', line) or '2급 스포츠지도사 필기시험' in line:
            continue

        # 문제 번호 감지: "1." "2." ... "20."
        q_match = re.match(r'^(\d{1,2})\s*\.\s*(.+)', line)
        if q_match and current_subject:
            q_num = int(q_match.group(1))
            if 1 <= q_num <= 20 and (current_q_num == 0 or q_num == current_q_num + 1 or q_num == 1):
                # 이전 문제 저장
                if current_question:
                    save_question(questions, current_subject, current_q_num, current_question, current_options)

                current_q_num = q_num
                current_question = q_match.group(2).strip()
                current_options = []
                continue

        # 보기 감지: ① ② ③ ④
        opt_match = re.match(r'^([①②③④])\s*(.+)', line)
        if opt_match and current_question is not None:
            current_options.append(opt_match.group(2).strip())
            continue

        # 보기가 한 줄에 여러 개: "① xxx  ② yyy"
        multi_opt = re.findall(r'[①②③④]\s*([^①②③④]+)', line)
        if multi_opt and len(multi_opt) >= 2 and current_question is not None:
            for opt in multi_opt:
                opt_text = opt.strip()
                if opt_text:
                    current_options.append(opt_text)
            continue

        # 문제 텍스트 이어짐 (보기 전)
        if current_question is not None and len(current_options) == 0:
            current_question += ' ' + line
        # 보기 텍스트 이어짐
        elif current_question is not None and len(current_options) > 0:
            # 마지막 보기에 이어붙이기 (테이블 등의 경우)
            if current_options:
                current_options[-1] += ' ' + line

    # 마지막 문제 저장
    if current_subject and current_question:
        save_question(questions, current_subject, current_q_num, current_question, current_options)

    return questions


def save_question(questions, subject, q_num, question_text, options):
    """문제를 리스트에 추가"""
    if subject not in questions:
        questions[subject] = []

    # 옵션 4개로 맞추기
    while len(options) < 4:
        options.append('')
    options = options[:4]

    questions[subject].append({
        'number': q_num,
        'question': question_text.strip(),
        'options': options,
    })


def merge_with_answers(questions, year):
    """문제에 정답 매칭"""
    if year not in ANSWER_KEYS:
        return questions

    answers = ANSWER_KEYS[year]
    for subject, q_list in questions.items():
        if subject not in answers:
            continue
        ans_list = answers[subject]
        for q in q_list:
            idx = q['number'] - 1
            if 0 <= idx < len(ans_list):
                ans_num = ans_list[idx]
                answer_map = {1: 'A', 2: 'B', 3: 'C', 4: 'D', 0: 'ALL'}
                q['answer'] = answer_map.get(ans_num, 'A')
            else:
                q['answer'] = ''

    return questions


def convert_to_import_format(questions, year, exam_type):
    """DB 임포트용 JSON 형식으로 변환"""
    result = []
    for subject, q_list in questions.items():
        if subject not in VALID_SUBJECTS:
            continue
        for q in q_list:
            entry = {
                'subject': subject,
                'type': 'multiple_choice',
                'question': q['question'],
                'options': q['options'],
                'answer': q.get('answer', ''),
                'explanation': '',
                'exam_year': year,
                'exam_type': exam_type,
                'question_number': q['number'],
            }
            result.append(entry)
    return result


def process_exam_pdf(pdf_path, year, exam_type='A'):
    """단일 시험 PDF 처리"""
    print(f"  파싱 중: {os.path.basename(pdf_path)}")
    pages = extract_text_from_pdf(pdf_path)
    full_text = '\n'.join(pages)
    questions = parse_questions_from_text(full_text, year, exam_type)

    # 통계
    total = sum(len(qs) for qs in questions.values())
    for subj, qs in questions.items():
        print(f"    {subj}: {len(qs)}문제")

    return questions


def find_exam_files():
    """archive 디렉토리에서 시험 파일 매칭"""
    files = os.listdir(ARCHIVE_DIR)
    exams = {}

    for f in sorted(files):
        if not f.endswith('.pdf'):
            continue

        # macOS NFD → NFC 정규화
        nf = unicodedata.normalize('NFC', f)

        # 연도 추출
        year_match = re.search(r'(20\d{2})', nf)
        if not year_match:
            continue
        year = year_match.group(1)

        if year not in exams:
            exams[year] = {'questions': [], 'answers': None}

        if '정답' in nf:
            exams[year]['answers'] = f
        elif 'A형' in nf or 'A형' in nf:
            exams[year]['questions'].insert(0, f)  # A형 우선
        elif 'B형' in nf or 'B형' in nf:
            exams[year]['questions'].append(f)
        elif '문제' in nf:
            exams[year]['questions'].insert(0, f)
        elif '필기시험' in nf and '정답' not in nf:
            exams[year]['questions'].append(f)

    # 디버그 출력
    for year, info in sorted(exams.items()):
        q_files = [os.path.basename(f) for f in info['questions']]
        a_file = info['answers'] or '없음'
        print(f"  {year}: 문제={q_files}, 정답={a_file}")

    return exams


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    exams = find_exam_files()
    all_questions = []

    for year in sorted(exams.keys()):
        info = exams[year]
        print(f"\n=== {year}년 ===")

        if not info['questions']:
            print("  문제 파일 없음, 건너뜀")
            continue

        # A형 우선 사용
        pdf_file = info['questions'][0]
        exam_type = 'A' if ('A형' in pdf_file or '문제' in pdf_file) else 'B'
        pdf_path = os.path.join(ARCHIVE_DIR, pdf_file)

        questions = process_exam_pdf(pdf_path, year, exam_type)

        # 정답 매칭
        if year in ANSWER_KEYS:
            questions = merge_with_answers(questions, year)
            print(f"  정답 매칭 완료 (하드코딩)")
        elif info['answers']:
            print(f"  정답 파일: {info['answers']} (수동 입력 필요)")

        converted = convert_to_import_format(questions, year, exam_type)
        all_questions.extend(converted)

    # JSON 저장
    output_path = os.path.join(OUTPUT_DIR, 'archive_questions.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_questions, f, ensure_ascii=False, indent=2)

    print(f"\n총 {len(all_questions)}개 문제 → {output_path}")

    # 연도별 통계
    by_year = {}
    for q in all_questions:
        y = q.get('exam_year', '?')
        by_year[y] = by_year.get(y, 0) + 1
    print("\n연도별:")
    for y in sorted(by_year.keys()):
        print(f"  {y}년: {by_year[y]}문제")

    # 정답 있는 문제 수
    with_answer = sum(1 for q in all_questions if q.get('answer'))
    print(f"\n정답 있는 문제: {with_answer}/{len(all_questions)}")


if __name__ == '__main__':
    main()
