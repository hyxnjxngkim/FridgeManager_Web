"""이번 주 식단 + 장보기 목록 (Phase 5). 식단은 Claude 없이 코드 규칙으로 짜요 (비용 0)."""
from __future__ import annotations

from datetime import timedelta

import streamlit as st

from lib.auth import require_user
from lib.dates import today_kst
from lib.inventory import get_catalog, get_expiring, get_inventory
from lib.meal_plan import get_week, save_week
from lib.meal_plan_rules import day_label, plan_week
from lib.models import RecipeMatch
from lib.recipe_source import search_recipes
from lib.schedule import event_label, get_events
from lib.shopping import add_manual, delete_item, get_items, move_checked_to_inventory, replace_plan_items, set_checked
from lib.shopping_rules import build_shopping_list
from lib.ui import recipe_card  # 팀원 B

DAYS = 7

user = require_user()
start = today_kst()
end = start + timedelta(days=DAYS - 1)

if msg := st.session_state.pop("plan_msg", None):
    st.toast(msg, icon="✅")

st.title("이번 주 식단")
st.caption(
    "달력의 일정을 보고 오늘부터 7일 저녁 메뉴를 짜요. "
    "⏰ 바쁜 날은 15분 이하 요리, 💪 운동한 날은 고단백, 👥 손님 오는 날은 인원수만큼. "
    "유통기한이 빠른 재료가 앞쪽 날에 오도록 골라요."
)


def make_plan() -> None:
    events = get_events(user.id, start, end)
    expiring = get_expiring(user.id, DAYS)

    def search(names, max_minutes, servings, tags):
        return search_recipes(user.id, names, max_minutes=max_minutes, servings=servings, tags=tags)

    meals = plan_week(start, events, expiring, search, days=DAYS)
    save_week(user.id, start, meals, days=DAYS)
    st.session_state.plan_msg = f"{sum(1 for m in meals if m.match)}일치 식단을 짰어요."


st.button("🗓 이번 주 식단 짜기", type="primary", on_click=make_plan)

week = {m.day: m for m in get_week(user.id, start, DAYS)}
events = get_events(user.id, start, end)
if not week:
    st.info("아직 식단이 없어요. 위 버튼을 눌러 짜 보세요. 달력에 일정을 먼저 넣으면 반영돼요.")
else:
    for offset in range(DAYS):
        day = start + timedelta(days=offset)
        meal = week.get(day)
        day_events = [event_label(e) for e in events if e.date == day]
        with st.container(border=True):
            head = f"**{day_label(day)}**" + (" · 오늘" if offset == 0 else "")
            if day_events:
                head += "  " + " ".join(f"`{x}`" for x in day_events)
            st.markdown(head)
            if meal is None:
                st.caption("조건에 맞는 레시피가 없었어요.")
                continue
            st.markdown(f"🍽 **{meal.recipe.title}**" + (f" · {meal.servings}인분" if meal.servings else ""))
            if meal.reason:
                st.caption(meal.reason)
            with st.expander("레시피 보기"):
                recipe_card(RecipeMatch(recipe=meal.recipe, score=0))

# ── 장보기 목록 ──────────────────────────────
st.divider()
st.subheader("🛒 장보기 목록")
st.caption("식단에 필요한데 냉장고에 없는(또는 모자란) 재료만 모아요. 산 것은 체크한 뒤 재고에 넣으세요.")


def make_shopping() -> None:
    meals = [(m.recipe, m.servings) for m in get_week(user.id, start, DAYS)]
    needs = build_shopping_list(meals, get_inventory(user.id), get_catalog())
    replace_plan_items(user.id, needs)
    st.session_state.plan_msg = f"장보기 목록을 만들었어요 ({len(needs)}개)."


st.button("식단으로 장보기 목록 만들기", on_click=make_shopping, disabled=not week)

items = get_items(user.id)
if not items:
    st.caption("목록이 비어 있어요.")
for it in items:
    c1, c2 = st.columns([6, 1])
    qty = f" {it.quantity:g}{it.unit or ''}" if it.quantity else ""
    c1.checkbox(
        f"{it.name}{qty}",
        value=it.checked,
        key=f"shop-{it.id}",
        on_change=set_checked,
        args=(user.id, it.id, not it.checked),
        help=f"필요한 메뉴: {it.recipe_title}" if it.recipe_title else "직접 넣은 항목",
    )
    if c2.button("삭제", key=f"del-shop-{it.id}"):
        delete_item(user.id, it.id)
        st.rerun()

with st.form("add-shop", clear_on_submit=True):
    c1, c2, c3 = st.columns([3, 1, 1])
    name = c1.text_input("직접 추가", placeholder="예: 달걀")
    qty = c2.number_input("수량", min_value=0.0, value=0.0, step=1.0)
    unit = c3.text_input("단위", placeholder="개")
    if st.form_submit_button("추가"):
        try:
            add_manual(user.id, name, qty or None, unit)
            st.rerun()
        except ValueError as e:
            st.error(str(e))

if st.button("✅ 산 것 재고에 넣기", disabled=not any(i.checked for i in items)):
    added, failed = move_checked_to_inventory(user.id)
    msg = f"재고에 넣었어요: {', '.join(added)}." if added else ""
    if failed:
        st.warning(f"유통기한을 몰라서 넣지 못했어요: {', '.join(failed)}. 재고 페이지에서 유통기한을 넣어 추가해 주세요.")
    if added:
        st.session_state.plan_msg = msg
        st.rerun()
