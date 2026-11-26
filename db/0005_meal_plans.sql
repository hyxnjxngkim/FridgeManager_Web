-- 주간 식단 + 장보기 목록 보강 (Phase 5, A)

-- 하루 한 끼(저녁) 식단. 레시피 내용은 그때 모습 그대로 저장해요(recipe jsonb):
-- B의 레시피가 바뀌거나 지워져도 짜 둔 식단과 장보기 목록은 그대로 보이게.
create table if not exists meal_plans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users on delete cascade,
  date date not null,
  recipe_id text,                 -- B의 레시피 id (가짜 레시피는 uuid가 아니라 text)
  recipe_title text not null,
  recipe jsonb not null,          -- lib/models.Recipe 를 그대로 담은 것
  servings int,
  reason text,                    -- 왜 이 메뉴인지 (바쁜 날·운동·손님·구출 재료)
  created_at timestamptz not null default now(),
  unique (user_id, date)
);
create index if not exists meal_plans_user_date_idx on meal_plans (user_id, date);

-- 장보기 항목이 어느 메뉴 때문에 필요한지, 식단에서 만든 건지(plan) 직접 넣은 건지(manual)
alter table shopping_items add column if not exists recipe_title text;
alter table shopping_items add column if not exists source text not null default 'manual'
  check (source in ('plan', 'manual'));
