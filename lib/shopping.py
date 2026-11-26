"""장보기 목록 (shopping_items). 모든 함수는 user_id 의 항목만 다뤄요."""
from __future__ import annotations

from typing import Optional

from lib.db import execute, fetch_all, transaction
from lib.dates import today_kst
from lib.inventory import add_item
from lib.inventory_rules import ItemInput
from lib.models import ShoppingItem
from lib.shopping_rules import ShoppingNeed


def get_items(user_id: str) -> list[ShoppingItem]:
    rows = fetch_all(
        "select id, name, quantity, unit, checked, source, recipe_title from shopping_items"
        " where user_id = %s order by checked, source, name",
        (user_id,),
    )
    return [
        ShoppingItem(str(r["id"]), r["name"], float(r["quantity"]) if r["quantity"] is not None else None,
                     r["unit"], r["checked"], r["source"], r["recipe_title"])
        for r in rows
    ]


def replace_plan_items(user_id: str, needs: list[ShoppingNeed]) -> None:
    """식단에서 만든 '아직 안 산' 항목을 새 목록으로 바꿔요. 직접 넣은 것·산 것은 그대로 둬요."""
    with transaction() as conn:
        conn.execute(
            "delete from shopping_items where user_id = %s and source = 'plan' and not checked", (user_id,)
        )
        for n in needs:
            conn.execute(
                "insert into shopping_items (user_id, name, quantity, unit, source, recipe_title)"
                " values (%s, %s, %s, %s, 'plan', %s)",
                (user_id, n.name, n.quantity, n.unit, ", ".join(n.recipes)[:200]),
            )


def add_manual(user_id: str, name: str, quantity: Optional[float] = None, unit: Optional[str] = None) -> None:
    name = (name or "").strip()
    if not name or len(name) > 50:
        raise ValueError("이름을 1~50자로 입력해 주세요.")
    execute(
        "insert into shopping_items (user_id, name, quantity, unit, source) values (%s, %s, %s, %s, 'manual')",
        (user_id, name, quantity, (unit or "").strip() or None),
    )


def set_checked(user_id: str, item_id: str, checked: bool) -> None:
    execute("update shopping_items set checked = %s where id = %s and user_id = %s", (checked, item_id, user_id))


def delete_item(user_id: str, item_id: str) -> None:
    execute("delete from shopping_items where id = %s and user_id = %s", (item_id, user_id))


def move_checked_to_inventory(user_id: str) -> tuple[list[str], list[str]]:
    """산 것(체크한 것)을 오늘 구입한 재고로 넣고 목록에서 지워요.

    유통기한은 재료 카탈로그로 추정해요. 카탈로그에 없는 재료는 넣지 못하고 남겨 둬요
    (재고 페이지에서 유통기한을 직접 넣어 추가하면 돼요).
    돌려주는 값: (넣은 이름들, 못 넣은 이름들)
    """
    added, failed = [], []
    for item in [i for i in get_items(user_id) if i.checked]:
        try:
            add_item(user_id, ItemInput(item.name, item.quantity or 1, item.unit, today_kst()))
        except ValueError:
            failed.append(item.name)
            continue
        delete_item(user_id, item.id)
        added.append(item.name)
    return added, failed
