-- 레시피 표에 칸 추가 (Phase 3, 팀원 B)
-- 실행: python scripts/migrate.py   (fridge_app 계정, search_path = fridge, public)
--
-- source_id : 원본 데이터의 레시피 번호. 식품안전나라 COOKRCP01 의 RCP_SEQ 를 'foodsafety:28' 처럼 넣어요.
--             scripts/seed_recipes.py 가 이 칸으로 upsert 해서, 시드를 다시 돌려도 레시피가 중복되지 않아요.
-- image_url : 완성 사진 주소 (https). 레시피 카드에 보여요. 없으면 null.
--
-- 레시피별 출처 칸(source_name, source_url)은 0001 에 있지만 쓰지 않아요 (PLAN 5장 ③).

alter table recipes add column if not exists source_id text;
alter table recipes add column if not exists image_url text;

-- source_id 가 같은 레시피는 하나만 (null 은 여러 개 가능)
create unique index if not exists recipes_source_id_key on recipes (source_id);
