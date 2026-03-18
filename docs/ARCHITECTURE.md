# 아키텍처

## 개요

단일 Docker 컨테이너로 동작하는 Flask 웹 애플리케이션입니다.
로컬 전용이며 동시 사용자 1명을 가정합니다.

```
┌─────────────────────────────────────────┐
│              Docker Container           │
│                                         │
│  ┌───────────┐     ┌────────────────┐   │
│  │  Flask     │────▶│  SQLite DB     │   │
│  │  (app.py)  │     │  (data/quiz.db)│   │
│  └─────┬─────┘     └────────────────┘   │
│        │                                │
│  ┌─────▼─────┐     ┌────────────────┐   │
│  │  Jinja2   │     │  Static Files  │   │
│  │ Templates │     │  (CSS/JS)      │   │
│  └───────────┘     └────────────────┘   │
│                                         │
│  Port 8080                              │
└─────────────────────────────────────────┘
```

## 디렉토리 구조

```
sports/
├── app.py                  # Flask 앱 (전체 백엔드, 단일 파일)
├── schema.sql              # DB 스키마 정의
├── parse_pdf.py            # 기출 PDF → JSON 변환 스크립트
├── docker-compose.yml
├── Dockerfile
├── requirements.txt        # flask, PyMuPDF
│
├── data/                   # SQLite DB (Docker volume, .gitignore)
│   └── quiz.db
├── questions/              # 문제 데이터 JSON (Docker volume)
│   └── archive_questions.json
├── archive/                # 기출 PDF 원본 (.gitignore)
│
├── static/
│   ├── style.css           # 전체 스타일 (반응형)
│   └── app.js              # 클라이언트 유틸리티
│
├── templates/
│   ├── base.html           # 공통 레이아웃, 네비게이션
│   ├── index.html          # 메인: 과목 선택, 시험 시작
│   ├── quiz.html           # 필기시험 진행 (타이머, 과목탭)
│   ├── oral.html           # 구술시험 진행 (자기채점)
│   ├── result.html         # 채점 결과, 과목별 성적
│   ├── history.html        # 시험 기록, 통계
│   ├── wrong.html          # 오답노트, 재시험
│   ├── edit.html           # 문제 목록 (필터, 페이지네이션)
│   ├── edit_detail.html    # 문제 상세 편집
│   └── manage.html         # 문제 관리 (임포트, 수동 추가)
│
└── docs/
    ├── ARCHITECTURE.md     # 이 문서
    └── DEPLOY.md           # 배포 가이드
```

## DB 스키마

### subjects (과목)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT UNIQUE | 과목명 (예: 스포츠윤리) |
| category | TEXT | written / oral |

### questions (문제)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| subject_id | INTEGER FK | 과목 |
| question_type | TEXT | multiple_choice / oral |
| question_text | TEXT | 지문 (\n으로 줄바꿈) |
| option_a~d | TEXT | 보기 4개 |
| correct_answer | TEXT | A/B/C/D/ALL |
| comment | TEXT | 코멘트/힌트 (시험 중 💡 표시) |
| exam_year | TEXT | 기출 연도 |
| exam_type | TEXT | A/B형 |
| question_number | INTEGER | 문항 번호 |

### test_sessions (시험 세션)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| test_type | TEXT | written / oral |
| selected_subjects | TEXT | 선택 과목 (쉼표 구분) |
| total_questions | INTEGER | 총 문항 수 |
| correct_count | INTEGER | 정답 수 |
| score_percent | REAL | 점수 (%) |
| is_passed | INTEGER | 합격 여부 (0/1) |
| time_limit_sec | INTEGER | 제한 시간 (초) |
| time_spent_sec | INTEGER | 소요 시간 (초) |

### user_answers (답변)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | |
| session_id | INTEGER FK | 시험 세션 |
| question_id | INTEGER FK | 문제 |
| user_answer | TEXT | 사용자 답변 |
| is_correct | INTEGER | 정답 여부 (0/1) |

## 라우트 맵

| 경로 | 메서드 | 설명 |
|---|---|---|
| `/` | GET | 메인 (과목 선택, 통계) |
| `/written/start` | POST | 필기시험 시작 |
| `/quiz/<id>` | GET | 시험 진행 |
| `/quiz/<id>/submit` | POST | 답안 제출, 채점 |
| `/oral/start` | POST | 구술시험 시작 |
| `/oral/<id>` | GET | 구술시험 진행 |
| `/oral/<id>/submit` | POST | 구술 자기채점 제출 |
| `/result/<id>` | GET | 시험 결과 |
| `/history` | GET | 기록, 통계 |
| `/wrong` | GET | 오답노트 |
| `/wrong/retry` | POST | 오답 재시험 |
| `/edit` | GET | 문제 목록 (필터) |
| `/edit/<id>` | GET | 문제 편집 |
| `/edit/<id>/save` | POST | 문제 저장 |
| `/edit/<id>/delete` | POST | 문제 삭제 |
| `/manage` | GET | 문제 관리 |
| `/manage/add` | POST | 문제 수동 추가 |
| `/manage/import` | POST | JSON/PDF 임포트 |

## 데이터 흐름

### 문제 등록
```
기출 PDF (archive/) → parse_pdf.py → questions/archive_questions.json
                                            ↓
앱 시작 시 자동 임포트 ──────────────▶ SQLite DB
                                            ↑
웹 UI (/manage, /edit) ─────────────────────┘
```

### 시험 진행
```
과목 선택 → 세션 생성 → 랜덤 문제 추출 (과목당 20문항)
                              ↓
                     시험 진행 (타이머)
                              ↓
                     답안 제출 → 자동 채점
                              ↓
                     결과 표시 (과목별 성적, 합격 판정)
                              ↓
                     오답노트에 기록
```

## 줄바꿈 처리

문제 지문과 코멘트의 줄바꿈은 `\n` 문자로 저장됩니다.
화면 표시 시 Jinja2 필터(`format_question`, `nl2br`)가 `\n` → `<br>`로 변환합니다.
편집 페이지의 textarea에서 Enter 키로 줄바꿈을 입력합니다.
