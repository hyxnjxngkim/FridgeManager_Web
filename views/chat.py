"""냉장고 에이전트 채팅 (Phase 4)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib.agent import AgentState, run_turn
from lib.auth import require_user
from lib.config import CLAUDE_MODEL
from lib.cooking import apply_cook
from lib.cooking_rules import plan_cook
from lib.dates import d_day_label, today_kst
from lib.inventory import get_catalog, get_expiring, get_inventory
from lib.llm import get_client, llm_unavailable_reason
from lib.models import RecipeMatch
from lib.recipe_source import search_recipes
from lib.ui import recipe_card  # 팀원 B (PLAN.md 11-2)


user = require_user()

# ── 상태 (사용자별) ───────────────────────────
if st.session_state.get("agent_user") != user.id:
    st.session_state.agent_user = user.id
    st.session_state.agent_state = AgentState()
    st.session_state.chat_log = []
state: AgentState = st.session_state.agent_state
log: list[dict] = st.session_state.chat_log

st.title("냉장고 에이전트")
st.caption("임박한 재료로 뭘 만들지, 알레르기·취향까지 기억해서 추천해요.")

unavailable = llm_unavailable_reason()
if unavailable:
    st.warning(f"지금은 Claude 와 대화할 수 없어요. {unavailable}\n\n아래 **임박 재료로 바로 추천** 버튼은 쓸 수 있어요.")


def start_cooking(match: RecipeMatch) -> None:
    """카드의 '이거 만들게' — Claude 없이 바로 미리보기를 만들어요."""
    state.pending_cook = plan_cook(match.recipe, get_inventory(user.id), get_catalog(), today_kst())


def quick_recommend() -> None:
    """Claude 없이: 임박 재료(3일)로 바로 검색."""
    names = [i.name for i in get_expiring(user.id, 3)]
    matches = search_recipes(user.id, names)[:3]
    for m in matches:
        state.recipes[m.recipe.id] = m
    text = (
        f"임박 재료({', '.join(names)})로 만들 수 있는 요리예요." if names and matches
        else "3일 안에 끝나는 재료가 없어서, 지금 재고로 만들 수 있는 요리를 골랐어요." if matches
        else "추천할 레시피를 찾지 못했어요."
    )
    log.append({"role": "assistant", "text": text, "matches": matches})


# ── 대화 기록 ─────────────────────────────────
for idx, entry in enumerate(log):
    with st.chat_message(entry["role"]):
        st.markdown(entry["text"])
        for m in entry.get("matches", []):
            recipe_card(m)
            st.button("🍳 이거 만들게", key=f"cook-{idx}-{m.recipe.id}", on_click=start_cooking, args=(m,))
        if entry.get("tools"):
            st.caption("사용한 도구: " + ", ".join(dict.fromkeys(entry["tools"])))

if not log:
    st.button("✨ 임박 재료로 바로 추천", on_click=quick_recommend)

# ── 재고 빼기 확인 ─────────────────────────────
plan = state.pending_cook
if plan:
    with st.container(border=True):
        st.subheader(f"🍳 {plan.recipe_title} — 재고 빼기 확인")
        st.caption("뺄 양을 고칠 수 있어요. **확정**을 눌러야 재고에서 빠져요.")
        if plan.lines:
            df = pd.DataFrame(
                [
                    {
                        "레시피 재료": ln.ingredient,
                        "재고": ln.item_name,
                        "남은 양": ln.available,
                        "뺄 양": ln.amount,
                        "단위": ln.unit or "",
                        "유통기한": d_day_label(ln.days_left),
                        "메모": ln.note,
                    }
                    for ln in plan.lines
                ]
            )
            edited = st.data_editor(
                df,
                key=f"cook-editor-{plan.recipe_id}",
                hide_index=True,
                width="stretch",
                disabled=["레시피 재료", "재고", "남은 양", "단위", "유통기한", "메모"],
                column_config={"뺄 양": st.column_config.NumberColumn(min_value=0.0, step=0.1)},
            )
        else:
            edited = None
            st.info("재고에서 뺄 재료가 없어요.")
        if plan.missing:
            st.caption("재고에 없는 재료: " + ", ".join(plan.missing))

        c1, c2 = st.columns(2)
        if c1.button("확정 — 재고에서 빼기", type="primary", width="stretch", disabled=not plan.lines):
            for ln, (_, row) in zip(plan.lines, edited.iterrows()):
                ln.amount = max(0.0, min(float(row["뺄 양"] or 0), ln.available))
            rescued = apply_cook(user.id, plan)
            msg = f"'{plan.recipe_title}' 재료를 재고에서 뺐어요." + (f" 임박 재료 {rescued}개를 구출했어요! 🎉" if rescued else "")
            log.append({"role": "assistant", "text": msg})
            state.notes.append(f"사용자가 '{plan.recipe_title}'을(를) 만들어 재고를 뺐어요 (구출 {rescued}개).")
            state.pending_cook = None
            st.rerun()
        if c2.button("취소", width="stretch"):
            state.pending_cook = None
            st.rerun()

# ── 입력 ──────────────────────────────────────
prompt = st.chat_input(
    "예: 오늘 뭐 해 먹지? / 나 땅콩 알레르기 있어 / 두부조림 만들게",
    disabled=bool(unavailable),
)
if prompt:
    log.append({"role": "user", "text": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        text = st.write_stream(run_turn(get_client(), state, user.id, prompt, model=CLAUDE_MODEL))
    log.append({"role": "assistant", "text": text or "", "matches": list(state.shown_matches), "tools": list(state.tools_used)})
    st.rerun()
