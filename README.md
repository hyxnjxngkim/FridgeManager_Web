# FridgeManager_Web
냉장고를 부탁해 — 유통기한 임박 재료부터 쓰는 레시피를 추천하는 냉장고 에이전트.
기획은 [PLAN.md](PLAN.md), 팀 작업 방식은 PLAN.md 11장을 보세요.

## 스택
Python 3.9+ · Streamlit · Supabase (Postgres + pgvector + Auth) · Claude API · pytest
배포: AWS EC2 (systemd, `deploy/fridge-app.service`)

## 처음 실행하기
1. 가상환경을 만들고 패키지를 설치해요.
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements-dev.txt
   ```
   > Anaconda(Intel 모드) Python에서 `cryptography` 설치가 실패하면:
   > `pip install --only-binary=cryptography,cffi -r requirements-dev.txt`
2. Supabase 프로젝트를 만들고, SQL Editor에서 `supabase/migrations/`의 SQL 파일을 번호 순서대로(0001 → 0002 …) 실행해요.
   - 개발 중에는 Authentication > Sign In / Providers > Email 에서 **Confirm email**을 꺼 두면 가입하자마자 로그인돼요.
3. 환경변수 파일을 만들고 값을 채워요 (Supabase > Settings > API).
   ```bash
   cp .env.example .env
   ```
4. 실행 → http://localhost:8501
   ```bash
   streamlit run app.py
   ```

## 테스트
```bash
pytest
```
- `tests/test_dates.py`, `tests/test_inventory_rules.py`: 날짜·유통기한 계산 규칙
- `tests/test_inventory_page.py`: 재고 화면을 가짜 데이터로 실행 (Supabase 없이)

## 폴더 구조
```
app.py                 시작 파일: 로그인 확인 + 메뉴(st.navigation)
views/                 화면 (페이지 하나 = 파일 하나)
  home.py inventory.py upload.py chat.py plan.py calendar.py dashboard.py settings.py login.py
lib/                   로직
  config.py            .env 읽기
  db.py                Supabase 클라이언트 (사용자 세션별)
  auth.py              로그인·회원가입·로그아웃
  models.py            팀 공용 데이터 모양 (InventoryItem, Recipe, RecipeMatch …)
  dates.py             날짜 계산 (한국 시간 기준) — 순수 함수
  catalog.py           재료 카탈로그 매칭 — 순수 함수
  inventory_rules.py   입력 검사·유통기한 결정 — 순수 함수
  inventory.py         재고 DB 읽기·쓰기, get_expiring()
  ui.py                공용 화면 조각
tests/                 pytest
supabase/migrations/   DB 스키마 + RLS + 시드
deploy/                EC2 systemd 서비스 파일
```

## EC2 배포 (main 브랜치만)
```bash
rsync -az --exclude .venv --exclude .git --exclude .env ./ ec2-user@<서버>:/home/ec2-user/fridge-manager/
ssh ec2-user@<서버> 'cd ~/fridge-manager && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && sudo systemctl restart fridge-app'
```
서버의 `.env`는 따로 올려요 (git에 없음). 서비스 파일 설치는 `deploy/fridge-app.service` 참고.
