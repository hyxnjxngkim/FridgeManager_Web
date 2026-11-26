# 냉장고를 부탁해 — 기획안

> 냉장고 재료·유통기한·내 일정·취향을 보고, **버릴 뻔한 재료부터 쓰는 레시피**를 추천하는 AI 에이전트 웹앱
> 이 문서는 바이브코딩(AI에게 단계별로 시키며 만드는 방식)을 전제로 작성했습니다. 8장의 단계별 프롬프트를 순서대로 AI에게 주면 됩니다.

---

## 1. 한 줄 목표와 핵심 지표

- **목표**: "냉장고에서 썩어서 버리는 재료를 0개로"
- **북극성 지표**: 구출률 = 구출한 재료 수 ÷ (구출 + 버린 재료 수)
- **MVP 성공 기준**: 영수증 1장 업로드 → 재고 등록 → 임박 재료 확인 → 레시피 추천 → "이거 만들게" → 재고 차감까지 한 흐름이 끊김 없이 동작

---

## 2. 기술 스택 (바이브코딩에 유리한 조합)

| 영역 | 선택 | 이유 |
|---|---|---|
| 언어 | **Python 3.9+** | 팀이 아는 언어. 바이브코딩이라도 코드를 읽고 고칠 수 있어야 함 |
| 화면 | **Streamlit** (`st.navigation` 멀티 페이지) | Python만으로 표·폼·채팅·차트·사진 업로드까지 기본 제공 |
| DB | **AWS RDS PostgreSQL 18** + **pgvector**, `psycopg` 3 (연결 풀) | 이미 있는 RDS 재사용, 레시피 벡터 검색까지 한 DB에서 |
| 로그인 | `users` 테이블 + **bcrypt** 비밀번호 해시 | 외부 서비스 없이 간단하게 |
| LLM | **Claude API** (`anthropic` 파이썬 SDK) | 비전 + 툴 사용(에이전트) |
| ├ 영수증 OCR | `claude-haiku-5-5` | 글자 위주라 싸고 빠른 모델로 충분 |
| ├ 냉장고 사진 | `claude-sonnet-5-5` | 여러 재료 동시 인식은 더 강한 모델 |
| └ 추천 에이전트 | `claude-sonnet-5-5` | 툴 호출·추론 |
| 임베딩 | Voyage AI 등 임베딩 API (1024차원 등) | Claude는 임베딩 모델이 없으므로 별도 사용 |
| 달력 | **streamlit-calendar** 컴포넌트 (자체 일정) → 나중에 Google Calendar 연동 | 처음엔 앱 안 일정으로 시작해 OAuth 부담 제거 |
| 차트 | Streamlit 기본 차트 (`st.bar_chart` 등) | 대시보드 |
| 알림 | 앱 내 배너 + (선택) EC2 cron → 이메일 | |
| 테스트 | **pytest** + Streamlit `AppTest` | 계산 로직과 화면을 DB 없이 검사 |
| 배포 | **AWS EC2** (`streamlit run` + systemd, `deploy/fridge-app.service`) + RDS | |

> 💡 처음부터 Google Calendar·푸시 알림까지 하지 말고, **앱 내 달력 + 앱 내 알림**으로 MVP를 먼저 끝내세요.

---

## 3. 전체 구조

```
[브라우저] ⇄ [Streamlit 서버 (Python)]  ← 화면과 로직이 모두 서버의 Python 코드
  ├─ views/inventory.py, upload.py ── 영수증/사진 ──▶ lib/ingest.py ──▶ Claude(Haiku/Sonnet) ──▶ 확인 표 ──▶ inventory 저장
  ├─ views/calendar.py ── 일정 + 유통기한 임박 표시
  ├─ views/chat.py ─▶ lib/agent.py ──▶ Claude Sonnet + Tools
  │                                     ├─ get_inventory / get_expiring
  │                                     ├─ search_recipes (pgvector)
  │                                     ├─ get_schedule / get_preferences
  │                                     ├─ cook_recipe (재고 차감)
  │                                     ├─ save_preference (취향 기억)
  │                                     └─ make_shopping_list
  └─ 대시보드 ── 구출/폐기 통계
[AWS RDS] PostgreSQL(+pgvector), fridge 스키마  ← EC2에서만 접속 가능 (로컬은 SSH 터널)
```

**핵심 설계 원칙**
1. **LLM은 "추출·판단"만, 계산은 코드로.** 유통기한 날짜 계산, 재고 차감, 통계는 전부 SQL/Python 코드가 처리. LLM에 맡기면 숫자가 틀립니다.
2. **AI 결과는 항상 "확인 후 저장".** 영수증 인식 결과는 바로 저장하지 말고 편집 가능한 표로 보여준 뒤 저장 버튼.
3. **에이전트 = Claude + 툴.** 채팅에서 "이거 만들게"라고 하면 Claude가 `cook_recipe` 툴을 호출하는 구조. 기능을 툴 단위로 쪼개면 바이브코딩도 쉬워집니다.

---

## 4. 데이터 모델 (AWS RDS PostgreSQL)

- **DB**: 기존 RDS(`vibedb`) 안의 **`fridge` 스키마**. 같은 DB의 Campus 앱 테이블(`public`)과 분리돼 있어요.
- **계정**: 앱 전용 계정 `fridge_app` — `fridge` 스키마만 쓸 수 있고 Campus 테이블은 읽을 수 없어요.
- **pgvector**: 관리자가 `public`에 설치해 둠 (0.8.1). `search_path = fridge, public`이라 `vector` 타입을 그대로 써요.
- **정의 파일**: `db/0001_init.sql` (테이블), `db/0002_seed_catalog.sql` (카탈로그 147개). 실행은 `python scripts/migrate.py`.

| 테이블 | 내용 | 사용자별 |
|---|---|---|
| `users` | 이메일 + bcrypt 비밀번호 해시 | – |
| `ingredient_catalog` | 재료별 보통 보관 일수, 별칭 | 공용 |
| `inventory` | 내 재고 (수량, 구입일, 유통기한, 상태 active/used/discarded) | ✅ |
| `recipes` | 레시피 원문 + `embedding vector(1024)` | 공용 |
| `schedule_events` | 일정 (busy/workout/guests) | ✅ |
| `preferences` | 취향·알레르기 | ✅ |
| `meal_logs` | 요리 기록, 평점, 피드백 | ✅ |
| `shopping_items` | 장보기 목록 | ✅ |
| `schema_migrations` | 실행한 SQL 파일 기록 (migrate.py가 관리) | – |

> ⚠️ **RLS(행 단위 보안)를 쓰지 않아요.** "사용자별 ✅" 테이블을 다루는 SQL에는 코드에서 반드시 `where user_id = %s`를 붙이세요. `lib/inventory.py`의 함수들처럼 **첫 번째 인자로 `user_id`를 받는** 모양을 지켜요.

---

## 5. 기능별 설계

### ① 재료 등록 (영수증 / 냉장고 사진)
- **흐름**: `st.file_uploader`/`st.camera_input`으로 업로드 → `lib/ingest.py`가 Claude 호출 → JSON 반환 → **`st.data_editor` 확인 표** → 저장
- **모델 분기**: 업로드 시 "영수증 / 냉장고 사진" 탭을 사용자가 고르게 하면 분기 로직이 단순 (자동 판별은 나중에)
- **출력 형식 고정**: 툴 사용(또는 JSON 스키마)으로 아래 형태만 받도록
  ```json
  { "items": [ { "name": "두부", "quantity": 1, "unit": "모", "purchased_at": "2026-11-26", "confidence": 0.9 } ] }
  ```
- 영수증에 없는 구입일은 오늘 날짜, 사진은 수량 추정이 부정확하니 `confidence` 낮은 항목은 노란색 표시
- 영수증의 "봉투", "할인" 같은 비식품 줄은 프롬프트에서 제외 지시

### ② 유통기한 관리
- `expires_at = purchased_at + ingredient_catalog.default_shelf_days` (**코드로 계산**)
- 카탈로그에 없는 재료만 Claude(Haiku)에게 보관일수 추정 요청 → 결과를 카탈로그에 캐시
- 카탈로그 초기 데이터: 자주 쓰는 재료 100~200개를 미리 시드 (AI에게 생성시키고 사람이 검토)
- **임박 기준**: D-3 이하 주황, D-1 이하 빨강, 지남 회색
- 달력에 임박 재료를 날짜별 뱃지로 표시, 첫 화면 상단에 "오늘 구해야 할 재료" 배너

### ③ 구출 레시피 추천 (RAG)
1. **레시피 수집**: 저작권 문제 없는 공공데이터(예: 농식품 공공데이터 레시피) 또는 직접 작성/AI 생성 레시피 200~500개로 시작. 레시피별 출처(`source_name`, `source_url`)는 기록·표시하지 않고, 앱 전체에 **"레시피 데이터: 식품안전나라" 한 줄**만 고정으로 표시 (공공누리 출처표시)
2. **임베딩**: 제목 + 재료 + 태그를 합친 텍스트를 임베딩해 `embedding`에 저장
3. **검색 (하이브리드)**:
   - 임박 재료 이름으로 쿼리 임베딩 → pgvector 상위 30개
   - SQL 필터: 알레르기 재료 포함 레시피 **제외**(하드 필터), 바쁜 날이면 `cook_minutes <= 10`
   - 코드로 점수화: `임박 재료 사용 수 × 3 + 보유 재료 비율 × 2 + 취향 태그 일치 + 평점 보정`
4. **생성**: 상위 3~5개를 Claude에게 넘겨 추천 이유 + **없는 재료의 대체재** 제안 (예: 생크림 → 우유+버터)
5. 추천 결과는 레시피 카드(`recipe_card()`)로 표시 (레시피별 출처 링크는 없음)

### ④ 일정 맞춤 식단
- `schedule_events.kind`로 규칙 매핑 (코드):
  | kind | 규칙 |
  |---|---|
  | busy | `cook_minutes <= 10` |
  | workout | `'고단백'` 태그 가중치 ↑ |
  | guests | `servings`를 손님 수+본인으로 스케일, 재료량 배수 계산 |
- "이번 주 식단 짜줘" → 7일 일정을 읽고 날짜별 추천, 임박 재료가 이른 날짜에 배치되게

### ⑤ 취향·알레르기 기억
- 채팅 중 "나 땅콩 알레르기야" → Claude가 `save_preference` 툴 호출 → DB 저장
- 설정 페이지에서 직접 보고/삭제 가능해야 함 (기억 투명성)
- **알레르기는 LLM 판단에 맡기지 말고 SQL로 제외**. 추가로 결과에 "알레르기 성분 확인" 문구

### ⑥ 재고 자동 빼기
- "이거 만들게" → `cook_recipe(recipe_id, servings)` 툴
- 코드가 레시피 재료와 재고를 이름으로 매칭(카탈로그 ID 우선, 없으면 유사 이름) → **차감 미리보기** 보여주고 확인 후 적용
- 임박 재료를 먼저 차감(FEFO: 먼저 만료되는 것부터), 0 이하가 되면 `status='used'`
- `meal_logs`에 기록, `rescued_items` 카운트

### ⑦ 장보기 목록
- 이번 주 식단 레시피의 재료 합계 − 현재 재고 = 부족분 (코드 계산)
- 같은 재료는 합치고, 체크박스로 구매 완료 → 체크한 항목을 바로 재고로 등록하는 버튼

### ⑧ 대시보드
- 카드: 이번 달 구출한 재료 수 / 버린 재료 수 / 구출률
- 차트: 주별 구출 vs 폐기 막대, 자주 먹은 요리 TOP 5
- 폐기 기록: 유통기한 지난 재료를 "버렸어요 / 아직 괜찮아요" 버튼으로 정리 → `status='discarded'`

### ⑨ 피드백 학습
- 요리 후 👍/👎 + 한 줄 코멘트 ("너무 매웠어")
- 학습 방식(모델 재학습 아님, **데이터 기반 개인화**):
  1. 평점을 레시피 점수에 반영 (좋았던 레시피·태그 가중치 ↑, 싫었던 것 ↓)
  2. 코멘트는 Claude가 요약해 취향으로 변환 → `preferences` 갱신 (예: "매운맛" strength −1)
  3. 같은 레시피 연속 추천 방지 (최근 7일 먹은 요리 감점)

---

## 6. 에이전트 툴 정의 (Claude Tool Use)

| 툴 | 입력 | 하는 일 |
|---|---|---|
| `get_inventory` | – | 활성 재고 목록 |
| `get_expiring` | `days` | D-n 이내 재료 |
| `search_recipes` | `ingredients[]`, `max_minutes?`, `servings?`, `tags?` | 하이브리드 검색 결과 |
| `get_schedule` | `from`, `to` | 일정 목록 |
| `get_preferences` | – | 취향·알레르기 |
| `save_preference` | `kind`, `value` | 기억 저장 |
| `cook_recipe` | `recipe_id`, `servings` | 차감 미리보기 반환 (확정은 UI 버튼) |
| `make_shopping_list` | `recipe_ids[]` | 부족 재료 목록 생성 |
| `record_feedback` | `meal_log_id`, `rating`, `comment` | 피드백 저장 |

**시스템 프롬프트 핵심**
- 항상 `get_expiring`을 먼저 확인하고 임박 재료를 쓰는 레시피를 우선
- 레시피는 반드시 `search_recipes` 결과에서만 추천 (지어내지 않기)
- 알레르기 재료가 포함된 레시피는 절대 추천하지 않기
- 재고 변경은 사용자 확인 후에만

---

## 7. 화면 구성

메뉴(페이지 목록)는 `app.py`의 `st.navigation`에서 정해요.

| 파일 | 화면 |
|---|---|
| `views/home.py` | 홈: 오늘 구해야 할 재료 배너 + 추천 레시피 3개 + 채팅 입력창 |
| `views/inventory.py` | 재고 표 (D-day 표시, `st.data_editor`로 바로 수정·처리) + 재료 추가 |
| `views/upload.py` | 영수증/사진 업로드 → 인식 결과 확인 표 |
| `views/calendar.py` | 일정 + 임박 재료 달력, 날짜 클릭 시 그날 추천 |
| `views/chat.py` | 에이전트 채팅 (`st.chat_message`, 레시피 카드, "이거 만들게" 버튼) |
| `views/plan.py` | 이번 주 식단 + 장보기 목록 |
| `views/dashboard.py` | 통계 |
| `views/settings.py` | 취향·알레르기 관리, 계정 |
| `views/login.py` | 로그인·회원가입 (로그인 전에만 보임) |

폰에서도 쓰기 좋게 한 화면에 너무 많은 열을 두지 마세요 (냉장고 앞에서 폰으로 쓰는 상황).

---

## 8. 개발 단계 (바이브코딩 순서 + AI에게 줄 프롬프트)

> 한 번에 다 시키지 말고, **단계마다 동작 확인 → 커밋**하세요. 각 단계 시작 시 이 PLAN.md를 함께 보여주면 맥락이 유지됩니다.

### Phase 0. 세팅 (반나절) ✅ 완료
> "PLAN.md를 읽고 Streamlit 프로젝트를 만들어줘. RDS PostgreSQL(fridge 스키마)에 psycopg로 연결하고, users 테이블 + bcrypt로 이메일 로그인을 만들어줘. `.env.example`에 PG_*, ANTHROPIC_API_KEY 자리를 만들어줘. 7장의 페이지들을 빈 화면으로 `st.navigation`에 등록해줘."

- `python scripts/migrate.py` → `db/0001_init.sql` 실행 (테이블)

### Phase 1. 재고 + 유통기한 (MVP 핵심, 1~2일) ✅ 완료
> "views/inventory.py를 만들어줘. 재고 표에 D-day를 계산해 D-3 주황, D-1 빨강으로 표시하고, 직접 추가/수정/삭제할 수 있게. ingredient_catalog에 한국 가정에서 자주 쓰는 재료 150개의 냉장 보관일수 시드 SQL도 만들어줘. expires_at은 코드로 계산하고, 계산 로직은 pytest로 테스트해줘."

- `python scripts/migrate.py` → `db/0002_seed_catalog.sql` 실행 (카탈로그 147개)

### Phase 2. 영수증/사진 인식 (1일)
> "views/upload.py를 만들어줘. '영수증'이면 claude-haiku-5-5, '냉장고 사진'이면 claude-sonnet-5-5로 이미지를 보내 5장 ①의 JSON 형식으로 재료를 뽑아. 결과는 편집 가능한 표로 보여주고 저장 버튼을 누르면 inventory에 넣어. 카탈로그에 없는 재료는 Haiku에게 보관일수를 물어 카탈로그에 추가해."

### Phase 3. 레시피 RAG (2일)
> "recipes 테이블에 레시피를 넣는 시드 스크립트(scripts/seed_recipes.py)를 만들어줘. 각 레시피의 제목+재료+태그를 임베딩해 저장해. 그리고 5장 ③의 하이브리드 검색(벡터 검색 → 알레르기 SQL 제외 → 코드 점수화)을 lib/recipes.py의 search_recipes()로 구현하고, 홈에 임박 재료 기반 추천 3개를 카드로 보여주고, 홈 아래에 '레시피 데이터: 식품안전나라' 한 줄을 표시해줘. 벡터 검색은 pgvector의 `embedding <=> %s` 거리 정렬 SQL로 하고, 필요한 인덱스·함수는 db/0003_... 새 파일에 넣어줘."

### Phase 4. 에이전트 채팅 + 재고 차감 + 취향 기억 (2일)
> "views/chat.py에 claude-sonnet-5-5 기반 에이전트를 만들어줘 (로직은 lib/agent.py). 6장의 툴들을 구현하고 st.write_stream으로 스트리밍해서 답해. 레시피 카드에 '이거 만들게' 버튼이 있고, 누르면 차감 미리보기 → 확인 시 FEFO로 재고 차감 + meal_logs 기록. 사용자가 취향/알레르기를 말하면 save_preference로 저장하고 views/settings.py에서 볼 수 있게 해줘."

### Phase 5. 달력 + 일정 맞춤 + 장보기 (2일)
> "views/calendar.py에 streamlit-calendar로 일정(busy/workout/guests)을 등록하고 임박 재료도 날짜별로 표시해줘. views/plan.py에서 '이번 주 식단 짜기'를 누르면 5장 ④ 규칙으로 7일 식단을 만들고, 5장 ⑦대로 부족 재료 장보기 목록을 만들어줘."

### Phase 6. 대시보드 + 피드백 학습 (1~2일)
> "views/dashboard.py에 st.metric과 Streamlit 차트로 구출 수, 폐기 수, 구출률, 자주 먹은 요리 TOP5를 보여줘. 요리 후 👍/👎+코멘트를 받고, 5장 ⑨처럼 평점을 추천 점수에 반영하고 코멘트를 취향으로 변환해 preferences를 갱신해."

### Phase 7. 마무리 (선택)
- Google Calendar 연동, 알림(EC2 cron으로 매일 아침 임박 재료 이메일), AWS EC2 배포 (`deploy/fridge-app.service`)

---

## 9. 주의할 점 / 흔한 실수

| 위험 | 대응 |
|---|---|
| LLM이 레시피를 지어냄 | 반드시 DB 검색 결과만 쓰게 하고, `search_recipes`가 돌려준 레시피만 카드로 표시 |
| 알레르기 누락 | SQL 하드 필터 + `allergens` 컬럼 시드 시 꼼꼼히 검수 |
| 재료 이름 불일치 ("대파" vs "파") | 카탈로그 기준 이름 + 별칭(aliases) 컬럼으로 정규화 |
| 유통기한 추정 오차 | "추정" 라벨 표시, 사용자가 쉽게 수정 가능하게 |
| 레시피 저작권 | 공공데이터·직접 작성·라이선스 확인된 출처만 사용. 공공데이터는 앱에 "레시피 데이터: 식품안전나라" 한 줄로 출처표시 |
| API 비용 | 영수증은 Haiku, 이미지 리사이즈(긴 변 1568px 이하) 후 전송, 카탈로그 캐시 |
| API 키 노출 | 키는 `.env`에만 두고 git에 올리지 않기. Streamlit 코드는 서버에서 돌아서 브라우저에 키가 가지 않음 |
| 새로고침하면 로그아웃됨 | Streamlit 세션은 브라우저 탭 단위라 새로고침하면 다시 로그인해야 함 (MVP에선 감수, 필요하면 나중에 쿠키 저장 추가) |
| 바이브코딩 중 코드 꼬임 | 단계별 커밋, 한 번에 한 기능만 요청, 에러는 전체 메시지 붙여넣기 |

---

## 10. 일정 요약

| 주차 | 범위 | 결과물 |
|---|---|---|
| 1주차 | Phase 0~2 | 로그인, 재고 관리, 영수증/사진 등록, 유통기한 표시 |
| 2주차 | Phase 3~4 | 구출 레시피 추천(RAG), 에이전트 채팅, 재고 차감, 취향 기억 |
| 3주차 | Phase 5~6 | 달력·일정 맞춤 식단, 장보기, 대시보드, 피드백 학습 |
| 4주차 | Phase 7 + 버그 수정 | 배포 및 시연 준비 |

> 2인 동시 작업 시에는 11장의 분담·합치기 일정을 따르세요.

---

## 11. 팀 작업 방식 (2인 동시 작업)

기능 영역이 아니라 **의존 관계**로 나눕니다. Phase 1(재고)과 Phase 3(레시피 검색)은 서로 기다릴 필요가 없어서 첫날부터 동시에 시작할 수 있어요.

### 11-1. 역할 분담

> 2026-11-26 변경: Phase 2는 **보류**(담당은 나중에 정함). A가 Phase 4(에이전트)를 맡고, B는 Phase 3(레시피 검색)과 레시피 카드·홈 추천에 집중해요.

| | 팀원 A: 재고·에이전트 라인 | 팀원 B: 레시피 라인 |
|---|---|---|
| 1단계 | **Phase 1** 재고 표, 유통기한 계산, 재료 카탈로그 ✅ | **Phase 3** 레시피 수집, 임베딩, 검색 |
| 2단계 | **Phase 4** 에이전트 채팅, 재고 빼기, 취향 기억 | **Phase 3 마무리** 홈 추천 카드, `recipe_card()` |
| 3단계 | **Phase 5 앞부분** 달력, 일정 등록 | **Phase 5 뒷부분** 주간 식단, 장보기 목록 |
| 4단계 | **Phase 6 앞부분** 대시보드 통계·차트 | **Phase 6 뒷부분** 피드백 학습 |
| 보류 | **Phase 2** 영수증·사진 인식 — 담당 미정 | |

각자 맡은 화면과 폴더가 거의 겹치지 않아 충돌이 적어요.

| 담당 | 주로 만지는 곳 |
|---|---|
| A | `views/inventory.py`, `views/chat.py`, `views/settings.py`, `views/calendar.py`, `views/dashboard.py`, `lib/inventory*.py`, `lib/agent.py`, `lib/preferences.py` |
| B | `views/home.py`, `views/plan.py`, `lib/recipes.py`, `lib/ui.py`의 `recipe_card()`, `scripts/` (레시피 시드) |

### 11-2. 시작 전에 같이 할 일 (반나절)

1. `streamlit-migration` PR을 `main`에 합치고, 둘 다 `main`에서 브랜치를 만들어 시작해요.
2. 서로 부를 함수의 **모양(입력·출력)만** 먼저 정해서 `main`에 올려요. 처음엔 가짜 데이터를 돌려줘도 돼요.
   - A 담당 ✅: `get_expiring(user_id: str, days: int, include_expired: bool = False) -> list[InventoryItem]` — 임박 재료 목록 (`lib/inventory.py`)
   - B 담당: `search_recipes(user_id: str, ingredients: list[str], max_minutes=None, servings=None, tags=None) -> list[RecipeMatch]` (알레르기 제외를 위해 user_id 필요) — 추천 레시피 목록 (`lib/recipes.py`)
   - B 담당: `recipe_card(match: RecipeMatch)` — 레시피 카드 화면 조각 (`lib/ui.py`). 홈(B)과 채팅(A)이 같이 써요. A는 직접 만들지 않고 가져다 써요.
   - 같이 쓰는 데이터 모양(`InventoryItem`, `Recipe`, `RecipeMatch` 등)은 `lib/models.py`에 모아요.
3. 이렇게 하면 B는 A의 재고 기능이 끝나기 전에도 가짜 임박 재료로 레시피 검색을 개발할 수 있어요.
4. **Phase 4(A) ↔ Phase 3(B) 약속**
   - A는 B가 끝내기 전까지 같은 모양의 가짜 `search_recipes()` / `recipe_card()`로 개발하고, B의 PR이 합쳐지면 진짜로 바꿔요. 모양을 바꿀 땐 바로 알려요.
   - 레시피 재료 목록은 `Recipe.ingredients: list[RecipeIngredient]`(이름·수량·단위·선택 여부) 형식을 지켜요. "이거 만들게" 재고 차감이 이 형식을 읽어요.
   - 취향·알레르기 저장 형식(`preferences` 테이블): `kind`는 `allergy` / `like` / `dislike` / `diet`, `value`는 재료·맛 이름 하나 (예: `allergy` + `땅콩`). A의 에이전트가 쓰고, B의 검색이 읽어요.
   - Claude 호출 방식(Anthropic API 키 / AWS Bedrock)은 둘이 같은 방식으로 정해요.

### 11-3. 합치는 시점

| 시점 | 합치는 것 | 합친 뒤 확인할 것 |
|---|---|---|
| **1차 (1주차 끝)** | Phase 1 + 3 | 홈 화면에 진짜 임박 재료와 그 재료로 만든 추천 레시피가 나와요 |
| **2차 (2주차 끝)** | Phase 3 마무리 + 4 | **MVP 완성**: 재료 등록(직접 입력) → 레시피 추천 → "이거 만들게" → 재고 차감까지 한 흐름 |
| **3차 (3주차 중반)** | Phase 5 | 일정을 반영한 주간 식단과 장보기 목록 |
| **4차 (3주차 끝)** | Phase 6 | 통계와 피드백 학습 |

큰 합치기는 네 번이지만, **작은 PR은 하루~이틀마다 `main`에 넣어요.** 브랜치를 일주일씩 들고 있으면 마지막에 충돌이 크게 나요.

### 11-4. 충돌 막는 규칙

- **DB 변경은 새 파일로**: `0001_init.sql`은 고치지 말고 `0002_...sql`, `0003_...sql`처럼 새 파일을 추가해요. 번호가 겹치지 않게 만들기 전에 서로 알려요.
- **DB 번호 현황**: `db/0001`(테이블), `db/0002`(카탈로그, A)까지 사용·실행 완료. `0003`은 B(Phase 3), A가 필요하면 `0004`부터.
- **공용 파일은 조심**: `requirements.txt`, 메뉴(`app.py`), `lib/models.py`, `lib/db.py`, `lib/ui.py`는 고칠 때 미리 알리고 바로 PR로 올려요.
- **아침마다 `main` 받기**: 작업 시작 전에 `main`의 최신 내용을 자기 브랜치로 가져와요.
- **브랜치 이름 통일**: `phase1-inventory`, `phase3-recipe-search`처럼 `phase번호-내용`으로 지어요.
- **리뷰는 서로**: PR은 상대가 보고 합쳐요. 2차 합치기 때는 둘이 같이 전체 흐름을 직접 눌러 봐요.
- **배포는 `main`에서만**: EC2에는 `main`만 올려요. 각자 브랜치는 각자 컴퓨터(`streamlit run app.py`)에서 확인해요.
- **PR 전에 테스트**: `pytest`가 통과해야 PR을 올려요. 계산 로직은 Streamlit·DB와 분리된 순수 함수로 만들어 테스트해요 (예: `lib/dates.py`, `lib/inventory_rules.py`).
- **DB 구조는 마이그레이션 파일로만**: 같은 RDS(`fridge` 스키마)를 둘이 같이 써요. 테이블은 반드시 `db/` 파일 + `python scripts/migrate.py`로만 바꿔요. 직접 SQL로 고치면 상대 쪽과 어긋나요. 이미 실행된 파일은 고치지 말고 새 번호 파일을 만들어요.
- **DB 접속은 SSH 터널로**: RDS는 EC2에서만 열려 있어요. 각자 `./scripts/tunnel.sh`를 켜 두고 개발해요. 팀원은 EC2 키(.pem)를 직접 주고받지 말고, 팀원의 공개키를 EC2에 등록하는 방식이 안전해요.
- **사용자 데이터 SQL엔 항상 user_id**: RLS가 없으니 `where user_id = %s`를 빠뜨리면 남의 데이터가 보여요. PR 리뷰 때 꼭 확인해요.
- **비밀값 공유 금지**: `.env`는 git에 올리지 않아요. 키는 각자 받거나 안전한 경로(비밀번호 관리자 등)로 공유해요.
