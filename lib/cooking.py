"""재고 빼기 실제 적용 + 요리 기록 (DB). 계획은 lib/cooking_rules.py."""
from __future__ import annotations

import uuid

from lib.cooking_rules import CookPlan
from lib.db import transaction


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


def apply_cook(user_id: str, plan: CookPlan) -> int:
    """계획대로 재고를 빼고 meal_logs 에 기록. 구출한 임박 재료 수를 돌려줘요.

    한 번에(트랜잭션) 처리해서, 중간에 오류가 나면 아무것도 빠지지 않아요.
    0 이하가 된 재료는 status='used' 로 바뀌어요.
    """
    rescued = plan.rescued_count()
    with transaction() as conn:
        for line in plan.lines:
            if line.amount <= 0:
                continue
            conn.execute(
                "update inventory"
                " set quantity = greatest(quantity - %s, 0),"
                "     status = case when quantity - %s <= 0 then 'used' else status end"
                " where id = %s and user_id = %s and status = 'active'",
                (line.amount, line.amount, line.item_id, user_id),
            )
        recipe_id = None
        if _is_uuid(plan.recipe_id):
            row = conn.execute("select 1 from recipes where id = %s", (plan.recipe_id,)).fetchone()
            recipe_id = plan.recipe_id if row else None
        conn.execute(
            "insert into meal_logs (user_id, recipe_id, recipe_title, servings, rescued_items)"
            " values (%s, %s, %s, %s, %s)",
            (user_id, recipe_id, plan.recipe_title, plan.servings, rescued),
        )
    return rescued
