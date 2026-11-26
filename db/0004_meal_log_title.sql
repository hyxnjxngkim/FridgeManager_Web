-- 요리 기록에 레시피 이름을 남겨요 (Phase 4, A)
-- 레시피가 나중에 지워지거나(recipe_id → null) 아직 DB에 없는 예시 레시피여도
-- 대시보드의 "자주 먹은 요리"에 이름을 보여줄 수 있게.
alter table meal_logs add column if not exists recipe_title text;
