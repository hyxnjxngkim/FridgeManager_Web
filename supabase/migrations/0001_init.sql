-- 냉장고를 부탁해 — 초기 스키마
-- Supabase SQL Editor 에 통째로 붙여넣고 실행하세요.

create extension if not exists vector;

-- ─────────────────────────────────────────────
-- 재료 기준 정보 (보통 보관 기간 사전) — 모든 사용자 공용
-- ─────────────────────────────────────────────
create table if not exists ingredient_catalog (
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
create table if not exists inventory (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
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
create index if not exists inventory_user_expiry_idx on inventory (user_id, status, expires_at);

-- ─────────────────────────────────────────────
-- 레시피 (RAG 원문) — 모든 사용자 공용
-- 임베딩 차원은 사용할 임베딩 모델에 맞춰 바꾸세요 (기본 1024)
-- ─────────────────────────────────────────────
create table if not exists recipes (
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
create index if not exists recipes_embedding_idx on recipes using hnsw (embedding vector_cosine_ops);
create index if not exists recipes_allergens_idx on recipes using gin (allergens);
create index if not exists recipes_tags_idx on recipes using gin (tags);

-- ─────────────────────────────────────────────
-- 일정
-- ─────────────────────────────────────────────
create table if not exists schedule_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  date date not null,
  title text,
  kind text not null default 'normal' check (kind in ('busy', 'workout', 'guests', 'normal')),
  guests int check (guests is null or guests >= 0),
  created_at timestamptz not null default now()
);
create index if not exists schedule_user_date_idx on schedule_events (user_id, date);

-- ─────────────────────────────────────────────
-- 취향·알레르기 기억
-- ─────────────────────────────────────────────
create table if not exists preferences (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  kind text not null check (kind in ('allergy', 'like', 'dislike', 'diet')),
  value text not null,
  strength int not null default 1,
  created_at timestamptz not null default now(),
  unique (user_id, kind, value)
);

-- ─────────────────────────────────────────────
-- 요리 기록 (대시보드·피드백 학습 원천)
-- ─────────────────────────────────────────────
create table if not exists meal_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  recipe_id uuid references recipes on delete set null,
  cooked_at timestamptz not null default now(),
  servings int,
  rescued_items int not null default 0,
  rating int check (rating is null or rating between -1 and 5),
  feedback text
);
create index if not exists meal_logs_user_idx on meal_logs (user_id, cooked_at desc);

-- ─────────────────────────────────────────────
-- 장보기 목록
-- ─────────────────────────────────────────────
create table if not exists shopping_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
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
create or replace function set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

drop trigger if exists inventory_updated_at on inventory;
create trigger inventory_updated_at before update on inventory
  for each row execute function set_updated_at();

-- ─────────────────────────────────────────────
-- RLS (행 단위 보안)
-- 개인 테이블: 본인 행만 읽기/쓰기
-- 공용 테이블(카탈로그·레시피): 로그인 사용자 읽기만, 쓰기는 service_role(서버/시드 스크립트)만
-- ─────────────────────────────────────────────
alter table inventory        enable row level security;
alter table schedule_events  enable row level security;
alter table preferences      enable row level security;
alter table meal_logs        enable row level security;
alter table shopping_items   enable row level security;
alter table ingredient_catalog enable row level security;
alter table recipes          enable row level security;

do $$
declare t text;
begin
  foreach t in array array['inventory', 'schedule_events', 'preferences', 'meal_logs', 'shopping_items']
  loop
    execute format('drop policy if exists "own rows" on %I', t);
    execute format(
      'create policy "own rows" on %I for all to authenticated
         using (user_id = (select auth.uid()))
         with check (user_id = (select auth.uid()))', t);
  end loop;
end $$;

drop policy if exists "read catalog" on ingredient_catalog;
create policy "read catalog" on ingredient_catalog for select to authenticated using (true);

drop policy if exists "read recipes" on recipes;
create policy "read recipes" on recipes for select to authenticated using (true);
