-- 냉장고를 부탁해 — 초기 스키마 (AWS RDS PostgreSQL, fridge 스키마)
-- 실행: python scripts/migrate.py   (fridge_app 계정, search_path = fridge, public)
-- pgvector 확장은 관리자가 public 스키마에 이미 설치해 두었습니다.
--
-- ⚠️ RLS(행 단위 보안)를 쓰지 않으므로, 사용자 데이터 조회·수정은
--    코드에서 반드시 "where user_id = 현재 사용자"를 붙여야 합니다.

-- ─────────────────────────────────────────────
-- 사용자 (로그인)
-- ─────────────────────────────────────────────
create table users (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  password_hash text not null,                -- bcrypt
  created_at timestamptz not null default now()
);

-- ─────────────────────────────────────────────
-- 재료 기준 정보 (보통 보관 기간 사전) — 모든 사용자 공용
-- ─────────────────────────────────────────────
create table ingredient_catalog (
  id serial primary key,
  name text unique not null,                 -- '두부', '우유'
  aliases text[] not null default '{}',      -- {'파'} → '대파' 로 정규화
  category text,                             -- 채소/육류/유제품…
  default_shelf_days int not null check (default_shelf_days > 0),
  storage text not null default 'fridge' check (storage in ('fridge', 'freezer', 'room')),
  created_at timestamptz not null default now()
);

-- ─────────────────────────────────────────────
-- 내 재고
-- ─────────────────────────────────────────────
create table inventory (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users on delete cascade,
  name text not null,
  catalog_id int references ingredient_catalog,
  quantity numeric not null check (quantity >= 0),
  unit text,
  purchased_at date not null default current_date,
  expires_at date not null,
  expiry_source text not null default 'estimated' check (expiry_source in ('estimated', 'label', 'manual')),
  status text not null default 'active' check (status in ('active', 'used', 'discarded')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index inventory_user_expiry_idx on inventory (user_id, status, expires_at);

-- ─────────────────────────────────────────────
-- 레시피 (RAG 원문) — 모든 사용자 공용
-- 임베딩 차원은 사용할 임베딩 모델에 맞춰 바꾸세요 (기본 1024)
-- ─────────────────────────────────────────────
create table recipes (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  ingredients jsonb not null,                -- [{name, qty, unit, optional}]
  steps text not null,
  cook_minutes int,
  servings int,
  tags text[] not null default '{}',         -- {'고단백','매운맛','다이어트'}
  allergens text[] not null default '{}',    -- {'땅콩','우유','갑각류'}
  source_name text,
  source_url text,
  embedding vector(1024),
  created_at timestamptz not null default now()
);
create index recipes_embedding_idx on recipes using hnsw (embedding vector_cosine_ops);
create index recipes_allergens_idx on recipes using gin (allergens);
create index recipes_tags_idx on recipes using gin (tags);

-- ─────────────────────────────────────────────
-- 일정
-- ─────────────────────────────────────────────
create table schedule_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users on delete cascade,
  date date not null,
  title text,
  kind text not null default 'normal' check (kind in ('busy', 'workout', 'guests', 'normal')),
  guests int check (guests is null or guests >= 0),
  created_at timestamptz not null default now()
);
create index schedule_user_date_idx on schedule_events (user_id, date);

-- ─────────────────────────────────────────────
-- 취향·알레르기 기억
-- ─────────────────────────────────────────────
create table preferences (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users on delete cascade,
  kind text not null check (kind in ('allergy', 'like', 'dislike', 'diet')),
  value text not null,
  strength int not null default 1,
  created_at timestamptz not null default now(),
  unique (user_id, kind, value)
);

-- ─────────────────────────────────────────────
-- 요리 기록 (대시보드·피드백 학습 원천)
-- ─────────────────────────────────────────────
create table meal_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users on delete cascade,
  recipe_id uuid references recipes on delete set null,
  cooked_at timestamptz not null default now(),
  servings int,
  rescued_items int not null default 0,
  rating int check (rating is null or rating between -1 and 5),
  feedback text
);
create index meal_logs_user_idx on meal_logs (user_id, cooked_at desc);

-- ─────────────────────────────────────────────
-- 장보기 목록
-- ─────────────────────────────────────────────
create table shopping_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users on delete cascade,
  name text not null,
  quantity numeric,
  unit text,
  for_recipe uuid references recipes on delete set null,
  checked boolean not null default false,
  created_at timestamptz not null default now()
);

-- ─────────────────────────────────────────────
-- updated_at 자동 갱신
-- ─────────────────────────────────────────────
create function set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

create trigger inventory_updated_at before update on inventory
  for each row execute function set_updated_at();
