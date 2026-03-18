# 배포 가이드

## 사전 요구사항

- Docker & Docker Compose 설치
- Git (소스 코드 가져오기용)

## 설치 및 실행

### 1. 소스 코드 가져오기

```bash
git clone https://github.com/swish1995/sports.git
cd sports
```

### 2. Docker로 실행

```bash
docker compose up -d
```

브라우저에서 **http://localhost:8080** 접속.

### 3. 중지

```bash
docker compose down
```

## 데이터 영속성

| 경로 | 설명 | Docker 볼륨 |
|---|---|---|
| `data/quiz.db` | SQLite DB (문제, 시험기록) | `./data:/app/data` |
| `questions/` | 문제 JSON 파일 | `./questions:/app/questions` |

`docker compose down`으로 중지해도 데이터는 로컬 디렉토리에 보존됩니다.

## 기출문제 임포트

### 자동 임포트 (PDF → JSON)

기출 PDF가 있는 경우:

```bash
# 1. archive/ 디렉토리에 PDF 파일 배치
mkdir -p archive
# (PDF 파일 복사)

# 2. 파싱 스크립트 실행 (로컬 Python 필요)
pip install PyMuPDF
python parse_pdf.py

# 3. 생성된 JSON 확인
ls questions/archive_questions.json

# 4. 앱 재시작 (JSON 자동 임포트)
docker compose restart
```

### 수동 임포트 (웹 UI)

1. http://localhost:8080/manage 접속
2. JSON 또는 PDF 파일 업로드
3. 임포트 완료 후 `/edit`에서 확인 및 교정

## 포트 변경

`docker-compose.yml`에서 포트를 변경할 수 있습니다:

```yaml
ports:
  - "3000:8080"  # 로컬 3000번 → 컨테이너 8080번
```

## DB 초기화

문제와 시험 기록을 모두 삭제하고 처음부터 시작하려면:

```bash
rm data/quiz.db
docker compose restart
```

## 백업

```bash
# DB 백업
cp data/quiz.db data/quiz_backup_$(date +%Y%m%d).db

# 문제 데이터 백업
cp -r questions/ questions_backup_$(date +%Y%m%d)/
```

## 문제 해결

### 컨테이너가 시작되지 않을 때
```bash
docker compose logs app
```

### DB 에러 발생 시
```bash
# DB 파일 삭제 후 재시작 (데이터 초기화)
rm data/quiz.db
docker compose restart
```

### 문제가 표시되지 않을 때
```bash
# 컨테이너 내 문제 수 확인
docker exec sports-app-1 python3 -c "
import sqlite3
db = sqlite3.connect('/app/data/quiz.db')
print('문제 수:', db.execute('SELECT COUNT(*) FROM questions').fetchone()[0])
"
```

## Docker 없이 실행 (개발 모드)

```bash
pip install flask PyMuPDF
python app.py
# http://localhost:8080 접속
```
