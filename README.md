# FridgeManager_Web
냉장고를 부탁해 — 유통기한 임박 재료부터 쓰는 레시피를 추천하는 냉장고 에이전트.
기획은 [PLAN.md](PLAN.md), 팀 작업 방식은 PLAN.md 11장을 보세요.

## 스택
Python 3.9+ · Streamlit · AWS RDS PostgreSQL 18 + pgvector (`fridge` 스키마) · psycopg 3 · bcrypt · Claude on AWS Bedrock (Haiku 4.5 기본, Sonnet 4.6은 아껴서) · pytest
배포: AWS EC2 (systemd, `deploy/fridge-app.service`)

## 처음 실행하기
1. 가상환경을 만들고 패키지를 설치해요.
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements-dev.txt
   ```
   > Anaconda(Intel 모드) Python에서 `cryptography`/`bcrypt` 설치가 실패하면:
   > `pip install --only-binary=:all: -r requirements-dev.txt`
2. 환경변수 파일을 만들고 값을 채워요. DB 비밀번호(`fridge_app` 계정)는 팀 리더에게 안전한 경로로 받아요.
   ```bash
   cp .env.example .env
   ```
3. RDS는 EC2에서만 접속되므로, **다른 터미널에서 SSH 터널을 열어 둬요** (`localhost:5433` → RDS).
   ```bash
   ./scripts/tunnel.sh
   ```
4. 테이블을 만들어요 (이미 만들어져 있으면 "모두 최신이에요"만 나와요).
   ```bash
   python scripts/migrate.py
   ```
5. (채팅 에이전트를 쓰려면) AWS 자격증명이 필요해요. EC2에서는 서버 역할로 자동이고, 로컬에서는 `aws login`으로 로그인해요. 없으면 채팅 입력이 꺼지고 "임박 재료로 바로 추천" 버튼만 동작해요.
6. 실행 → http://localhost:8501
   ```bash
   streamlit run app.py
   ```

## 레시피 넣기 (Phase 3)
식품안전나라 레시피 약 1,150개를 임베딩(Amazon Titan Text Embeddings V2, Bedrock)과 함께 `recipes` 표에 넣어요.
먼저 `python scripts/migrate.py`로 `db/0003_recipes.sql`을 실행해 두세요.

- **나눠서 할 때** (임베딩 만드는 사람과 DB에 넣는 사람이 다를 때)
  ```bash
  # 1) 임베딩 만드는 사람: API → 변환 → 임베딩 → 파일 (DB 필요 없음)
  #    .env: RECIPE_API_KEY, BEDROCK_REGION(Titan V2가 있는 리전), AWS_PROFILE
  python scripts/seed_recipes.py --dry-run --out db/seed/recipes_seed.jsonl.gz
  # 2) DB에 넣는 사람: 파일 → DB (API 키·Bedrock 필요 없음, 로컬은 터널 먼저)
  python scripts/seed_recipes.py --load-file db/seed/recipes_seed.jsonl.gz
  ```
- **한 번에 할 때**: `python scripts/seed_recipes.py`
- 여러 번 실행해도 레시피 수는 늘지 않아요 (`source_id`로 덮어씀).
- 검색할 때도 같은 모델로 검색어를 임베딩해요. 앱이 도는 곳(로컬은 AWS 로그인, EC2는 서버 역할의 `bedrock:InvokeModel` 권한)과 `.env`의 `BEDROCK_REGION`이 필요해요. Bedrock을 못 부르면 재료 이름 글자 검색으로 대신해요.

## 테스트
```bash
pytest
```
DB 없이 돌아가요 (터널 불필요).
- `tests/test_dates.py`, `tests/test_inventory_rules.py`: 날짜·유통기한 계산 규칙
- `tests/test_passwords.py`: 비밀번호 암호화
- `tests/test_inventory_page.py`: 재고 화면을 가짜 데이터로 실행
- `tests/test_recipe_import.py`, `tests/test_recipe_rules.py`: 레시피 변환·알레르기·점수 규칙
- `tests/test_recipes_search.py`, `tests/test_home_page.py`, `tests/test_seed_recipes.py`: 검색·홈 카드·시드 (DB·Bedrock은 가짜)

## DB 구조 바꾸기
1. `db/`에 다음 번호 파일을 만들어요 (예: `db/0003_recipes_search.sql`). **이미 실행된 파일은 고치지 않아요.**
2. `python scripts/migrate.py`로 실행해요. `--status`로 실행 여부를 볼 수 있어요.
3. 사용자 데이터 테이블은 RLS가 없으니, 코드에서 항상 `where user_id = %s`로 걸러요.

## 폴더 구조
```
app.py                 시작 파일: 로그인 확인 + 메뉴(st.navigation)
views/                 화면 (페이지 하나 = 파일 하나)
  home.py inventory.py upload.py chat.py plan.py calendar.py dashboard.py settings.py login.py
lib/                   로직
  config.py            .env 읽기
  db.py                PostgreSQL 연결 풀, fetch_all / fetch_one / execute
  auth.py              로그인·회원가입·로그아웃, require_user()
  passwords.py         bcrypt 해시 — 순수 함수
  models.py            팀 공용 데이터 모양 (AppUser, InventoryItem, Recipe, RecipeMatch …)
  dates.py             날짜 계산 (한국 시간 기준) — 순수 함수
  catalog.py           재료 카탈로그 매칭 — 순수 함수
  inventory_rules.py   입력 검사·유통기한 결정 — 순수 함수
  inventory.py         재고 DB 읽기·쓰기, get_expiring()
  preferences.py       취향·알레르기 기억
  cooking_rules.py     "이거 만들게" 재고 빼기 계획 (FEFO, 단위 환산) — 순수 함수
  cooking.py           재고 빼기 적용 + 요리 기록
  llm.py               Claude 클라이언트 (AWS Bedrock)
  agent.py             냉장고 에이전트 (도구 7개, 스트리밍)
  recipe_source.py     레시피 검색 연결점 (B의 search_recipes + 알레르기 이중 안전장치)
  schedule.py          일정 (바쁜 날·운동·손님)
  meal_plan_rules.py   주간 식단 짜기 규칙 (Claude 없이) — 순수 함수
  meal_plan.py         주간 식단 저장·조회
  shopping_rules.py    장보기 목록 계산 (식단 재료 − 재고) — 순수 함수
  shopping.py          장보기 목록 저장, 산 것 → 재고
  ui.py                공용 화면 조각
db/                    SQL 마이그레이션 (번호 순서)
scripts/
  migrate.py           db/*.sql 실행
  tunnel.sh            로컬 개발용 SSH 터널
tests/                 pytest
deploy/                EC2 systemd 서비스 파일
```

## EC2 배포 (main 브랜치만)
서버의 `.env`는 로컬과 두 줄이 달라요: `PG_HOST=<RDS 주소>`, `PG_PORT=5432` (터널 없이 바로 접속).
```bash
rsync -az --exclude .venv --exclude .git --exclude .env ./ ec2-user@<서버>:/home/ec2-user/fridge-manager/
ssh ec2-user@<서버> 'cd ~/fridge-manager && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python scripts/migrate.py && sudo systemctl restart fridge-app'
```
서비스 파일 설치는 `deploy/fridge-app.service` 참고.
