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
| 프레임워크 | **Next.js 15 (App Router) + TypeScript** | 프론트·API를 한 프로젝트에서, AI가 가장 잘 아는 스택 |
| UI | **Tailwind CSS + shadcn/ui** | 컴포넌트 복붙 수준으로 빠르게 |
| DB / 인증 / 파일 | **Supabase** (Postgres + **pgvector** + Auth + Storage) | pgvector 내장, 로그인·이미지 저장까지 한 곳에서 |
| LLM | **Claude API** (`@anthropic-ai/sdk`) | 비전 + 툴 사용(에이전트) |
| ├ 영수증 OCR | `claude-haiku-5-5` | 글자 위주라 싸고 빠른 모델로 충분 |
| ├ 냉장고 사진 | `claude-sonnet-5-5` | 여러 재료 동시 인식은 더 강한 모델 |
| └ 추천 에이전트 | `claude-sonnet-5-5` | 툴 호출·추론 |
| 임베딩 | Voyage AI 등 임베딩 API (1024차원 등) | Claude는 임베딩 모델이 없으므로 별도 사용 |
| 달력 | **FullCalendar** (자체 일정) → 2단계에 Google Calendar 연동 | 처음엔 앱 안 일정으로 시작해 OAuth 부담 제거 |
| 차트 | Recharts | 대시보드 |
| 알림 | 앱 내 배너 + (선택) Supabase Cron → 이메일/웹푸시 | |
| 배포 | **AWS** (마지막 단계, standalone 빌드 → App Runner/ECS 또는 Amplify) + Supabase | |

> 💡 처음부터 Google Calendar·푸시 알림까지 하지 말고, **앱 내 달력 + 앱 내 알림**으로 MVP를 먼저 끝내세요.

---

## 3. 전체 구조

```
[브라우저]
  ├─ 재고 페이지 ── 영수증/사진 업로드 ──▶ /api/ingest ──▶ Claude(Haiku/Sonnet) ──▶ 확인 화면 ──▶ inventory 저장
  ├─ 달력 페이지 ── 일정 + 유통기한 임박 표시
  ├─ 채팅(에이전트) ─▶ /api/agent ──▶ Claude Sonnet + Tools
  │                                     ├─ get_inventory / get_expiring
  │                                     ├─ search_recipes (pgvector)
  │                                     ├─ get_schedule / get_preferences
  │                                     ├─ cook_recipe (재고 차감)
  │                                     ├─ save_preference (취향 기억)
  │                                     └─ make_shopping_list
  └─ 대시보드 ── 구출/폐기 통계
[Supabase] Postgres(+pgvector) · Auth · Storage
```

**핵심 설계 원칙**
1. **LLM은 "추출·판단"만, 계산은 코드로.** 유통기한 날짜 계산, 재고 차감, 통계는 전부 SQL/TS 코드가 처리. LLM에 맡기면 숫자가 틀립니다.
2. **AI 결과는 항상 "확인 후 저장".** 영수증 인식 결과는 바로 저장하지 말고 편집 가능한 표로 보여준 뒤 저장 버튼.
3. **에이전트 = Claude + 툴.** 채팅에서 "이거 만들게"라고 하면 Claude가 `cook_recipe` 툴을 호출하는 구조. 기능을 툴 단위로 쪼개면 바이브코딩도 쉬워집니다.

---

## 4. 데이터 모델 (Supabase SQL)

```sql
create extension if not exists vector;

-- 재료 기준 정보 (보통 보관 기간 사전)
create table ingredient_catalog (
  id serial primary key,
  name text unique not null,          -- '두부', '우유'
  category text,                      -- 채소/육류/유제품...
  default_shelf_days int not null,    -- 냉장 기준 보통 보관 일수
  storage text default 'fridge'       -- fridge/freezer/room
);

-- 내 재고
create table inventory (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users not null,
  name text not null,
  catalog_id int references ingredient_catalog,
  quantity numeric not null,
  unit text,                           -- 개/g/ml/팩
  purchased_at date not null,
  expires_at date not null,            -- 추정값 (사용자 수정 가능)
  expiry_source text default 'estimated', -- estimated/label/manual
  status text default 'active',        -- active/used/discarded
  created_at timestamptz default now()
);

-- 레시피 (RAG 원문)
create table recipes (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  ingredients jsonb not null,          -- [{name, qty, unit, optional}]
  steps text not null,
  cook_minutes int,
  servings int,
  tags text[],                         -- {'고단백','매운맛','다이어트'}
  allergens text[],                    -- {'땅콩','우유','갑각류'}
  source_name text,                    -- 출처 이름
  source_url text,                     -- 출처 링크
  embedding vector(1024)
);
create index on recipes using hnsw (embedding vector_cosine_ops);

-- 일정
create table schedule_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users not null,
  date date not null,
  title text,
  kind text,          -- busy/workout/guests/normal
  guests int          -- 손님 수
);

-- 취향·알레르기 기억
create table preferences (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users not null,
  kind text not null,       -- allergy/like/dislike/diet
  value text not null,      -- '땅콩', '매운맛', '다이어트'
  strength int default 1,   -- 피드백으로 증감
  created_at timestamptz default now()
);

-- 요리 기록 (대시보드·피드백 학습 원천)
create table meal_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users not null,
  recipe_id uuid references recipes,
  cooked_at timestamptz default now(),
  rescued_items int default 0,          -- 이번에 구출한 임박 재료 수
  rating int,                           -- 1~5 또는 👍(1)/👎(-1)
  feedback text                         -- "너무 짰어"
);

-- 장보기 목록
create table shopping_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users not null,
  name text, quantity numeric, unit text,
  for_recipe uuid references recipes,
  checked boolean default false
);
```

모든 사용자 테이블에 **RLS(행 단위 보안)** `user_id = auth.uid()` 정책을 켜세요.

---

## 5. 기능별 설계

### ① 재료 등록 (영수증 / 냉장고 사진)
- **흐름**: 업로드 → Supabase Storage 저장 → `/api/ingest` 호출 → Claude가 JSON 반환 → **편집 가능한 확인 표** → 저장
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
1. **레시피 수집**: 저작권 문제 없는 공공데이터(예: 농식품 공공데이터 레시피) 또는 직접 작성/AI 생성 레시피 200~500개로 시작. 반드시 `source_name`, `source_url` 기록
2. **임베딩**: 제목 + 재료 + 태그를 합친 텍스트를 임베딩해 `embedding`에 저장
3. **검색 (하이브리드)**:
   - 임박 재료 이름으로 쿼리 임베딩 → pgvector 상위 30개
   - SQL 필터: 알레르기 재료 포함 레시피 **제외**(하드 필터), 바쁜 날이면 `cook_minutes <= 10`
   - 코드로 점수화: `임박 재료 사용 수 × 3 + 보유 재료 비율 × 2 + 취향 태그 일치 + 평점 보정`
4. **생성**: 상위 3~5개를 Claude에게 넘겨 추천 이유 + 출처 + **없는 재료의 대체재** 제안 (예: 생크림 → 우유+버터)
5. 답변엔 반드시 출처 링크를 카드로 표시

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
| `search_recipes` | `ingredients[]`, `max_minutes?`, `servings?`, `tags?` | 하이브리드 검색 결과 (출처 포함) |
| `get_schedule` | `from`, `to` | 일정 목록 |
| `get_preferences` | – | 취향·알레르기 |
| `save_preference` | `kind`, `value` | 기억 저장 |
| `cook_recipe` | `recipe_id`, `servings` | 차감 미리보기 반환 (확정은 UI 버튼) |
| `make_shopping_list` | `recipe_ids[]` | 부족 재료 목록 생성 |
| `record_feedback` | `meal_log_id`, `rating`, `comment` | 피드백 저장 |

**시스템 프롬프트 핵심**
- 항상 `get_expiring`을 먼저 확인하고 임박 재료를 쓰는 레시피를 우선
- 레시피는 반드시 `search_recipes` 결과에서만 추천하고 출처를 함께 제시 (지어내지 않기)
- 알레르기 재료가 포함된 레시피는 절대 추천하지 않기
- 재고 변경은 사용자 확인 후에만

---

## 7. 화면 구성

| 경로 | 화면 |
|---|---|
| `/` | 홈: 오늘 구해야 할 재료 배너 + 추천 레시피 3개 + 채팅 입력창 |
| `/inventory` | 재고 표 (D-day 색상, 정렬·수정·삭제) + 업로드 버튼 |
| `/inventory/upload` | 영수증/사진 업로드 → 인식 결과 확인 표 |
| `/calendar` | 일정 + 임박 재료 달력, 날짜 클릭 시 그날 추천 |
| `/chat` | 에이전트 채팅 (레시피 카드, "이거 만들게" 버튼) |
| `/plan` | 이번 주 식단 + 장보기 목록 |
| `/dashboard` | 통계 |
| `/settings` | 취향·알레르기 관리, 계정 |

모바일 우선(냉장고 앞에서 폰으로 쓰는 상황)으로 디자인하세요.

---

## 8. 개발 단계 (바이브코딩 순서 + AI에게 줄 프롬프트)

> 한 번에 다 시키지 말고, **단계마다 동작 확인 → 커밋**하세요. 각 단계 시작 시 이 PLAN.md를 함께 보여주면 맥락이 유지됩니다.

### Phase 0. 세팅 (반나절)
> "PLAN.md를 읽고 Next.js 15 + TypeScript + Tailwind + shadcn/ui 프로젝트를 만들어줘. Supabase 클라이언트와 이메일 로그인을 붙이고, `.env.local.example`에 SUPABASE_URL, SUPABASE_ANON_KEY, ANTHROPIC_API_KEY, 임베딩 API 키 자리를 만들어줘. 7장의 페이지들을 빈 화면으로 라우팅해줘."

- Supabase에 4장 SQL 실행 + RLS 설정

### Phase 1. 재고 + 유통기한 (MVP 핵심, 1~2일)
> "inventory 페이지를 만들어줘. 재고 표에 D-day를 계산해 D-3 주황, D-1 빨강으로 표시하고, 직접 추가/수정/삭제할 수 있게. ingredient_catalog에 한국 가정에서 자주 쓰는 재료 150개의 냉장 보관일수 시드 SQL도 만들어줘. expires_at은 코드로 계산해."

### Phase 2. 영수증/사진 인식 (1일)
> "/inventory/upload를 만들어줘. '영수증'이면 claude-haiku-5-5, '냉장고 사진'이면 claude-sonnet-5-5로 이미지를 보내 5장 ①의 JSON 형식으로 재료를 뽑아. 결과는 편집 가능한 표로 보여주고 저장 버튼을 누르면 inventory에 넣어. 카탈로그에 없는 재료는 Haiku에게 보관일수를 물어 카탈로그에 추가해."

### Phase 3. 레시피 RAG (2일)
> "recipes 테이블에 레시피를 넣는 시드 스크립트(scripts/seed-recipes.ts)를 만들어줘. 각 레시피의 제목+재료+태그를 임베딩해 저장해. 그리고 5장 ③의 하이브리드 검색(벡터 검색 → 알레르기 SQL 제외 → 코드 점수화)을 lib/recipes/search.ts로 구현하고, 홈에 임박 재료 기반 추천 3개를 출처 링크와 함께 카드로 보여줘."

### Phase 4. 에이전트 채팅 + 재고 차감 + 취향 기억 (2일)
> "/chat에 Claude claude-sonnet-5-5 기반 에이전트를 만들어줘. 6장의 툴들을 구현하고 스트리밍으로 답해. 레시피 카드에 '이거 만들게' 버튼이 있고, 누르면 차감 미리보기 → 확인 시 FEFO로 재고 차감 + meal_logs 기록. 사용자가 취향/알레르기를 말하면 save_preference로 저장하고 /settings에서 볼 수 있게 해줘."

### Phase 5. 달력 + 일정 맞춤 + 장보기 (2일)
> "/calendar에 FullCalendar로 일정(busy/workout/guests)을 등록하고 임박 재료도 날짜별로 표시해줘. /plan에서 '이번 주 식단 짜기'를 누르면 5장 ④ 규칙으로 7일 식단을 만들고, 5장 ⑦대로 부족 재료 장보기 목록을 만들어줘."

### Phase 6. 대시보드 + 피드백 학습 (1~2일)
> "/dashboard에 Recharts로 구출 수, 폐기 수, 구출률, 자주 먹은 요리 TOP5를 보여줘. 요리 후 👍/👎+코멘트를 받고, 5장 ⑨처럼 평점을 추천 점수에 반영하고 코멘트를 취향으로 변환해 preferences를 갱신해."

### Phase 7. 마무리 (선택)
- Google Calendar 연동, 웹 푸시 알림(Supabase Cron으로 매일 아침 임박 재료 알림), AWS 배포

---

## 9. 주의할 점 / 흔한 실수

| 위험 | 대응 |
|---|---|
| LLM이 레시피를 지어냄 | 반드시 DB 검색 결과만 쓰게 하고, 출처 없는 레시피는 표시 안 함 |
| 알레르기 누락 | SQL 하드 필터 + `allergens` 컬럼 시드 시 꼼꼼히 검수 |
| 재료 이름 불일치 ("대파" vs "파") | 카탈로그 기준 이름 + 별칭(aliases) 컬럼으로 정규화 |
| 유통기한 추정 오차 | "추정" 라벨 표시, 사용자가 쉽게 수정 가능하게 |
| 레시피 저작권 | 공공데이터·직접 작성·라이선스 확인된 출처만 사용 |
| API 비용 | 영수증은 Haiku, 이미지 리사이즈(긴 변 1568px 이하) 후 전송, 카탈로그 캐시 |
| API 키 노출 | Claude/임베딩 호출은 반드시 서버(API Route)에서만 |
| 바이브코딩 중 코드 꼬임 | 단계별 커밋, 한 번에 한 기능만 요청, 에러는 전체 메시지 붙여넣기 |

---

## 10. 일정 요약

| 주차 | 범위 | 결과물 |
|---|---|---|
| 1주차 | Phase 0~2 | 로그인, 재고 관리, 영수증/사진 등록, 유통기한 표시 |
| 2주차 | Phase 3~4 | 구출 레시피 추천(RAG), 에이전트 채팅, 재고 차감, 취향 기억 |
| 3주차 | Phase 5~6 | 달력·일정 맞춤 식단, 장보기, 대시보드, 피드백 학습 |
| 4주차 | Phase 7 + 버그 수정 | 배포 및 시연 준비 |
