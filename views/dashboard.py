"""통계 대시보드 + 요리 평가 (Phase 6)."""
from __future__ import annotations

import inspect
from datetime import date, timedelta
from typing import Optional

import altair as alt
import pandas as pd
import streamlit as st

from lib.auth import require_user
from lib.dates import today_kst
from lib.feedback import unrated_meals
from lib.feedback_ui import feedback_form
from lib.stats import discard_days, meal_rows, used_count
from lib.stats_rules import rescue_rate, top_recipes, weekly_series

# 분류색 1·2번 (dataviz 검사 통과: 라이트·다크 모두 CVD ΔE ≥ 24). 상태색(빨강·초록)은 쓰지 않아요.
SERIES = ["구출", "폐기"]
COLORS = {"light": ["#2a78d6", "#eb6834"], "dark": ["#3987e5", "#d95926"]}
WEEKS = 8

user = require_user()
today = today_kst()

if msg := st.session_state.pop("feedback_msg", None):
    st.toast(msg, icon="✅")

st.title("통계")
st.caption("요리로 구출한 재료와 버린 재료를 비교해요. 구출률 = 구출 ÷ (구출 + 폐기)")

PERIODS = {"이번 달": today.replace(day=1), "최근 30일": today - timedelta(days=29), "전체": None}
period = st.radio("기간", list(PERIODS), horizontal=True, label_visibility="collapsed", key="dash-period")
since: Optional[date] = PERIODS[period]

meals = meal_rows(user.id, since)
rescued = sum(int(m["rescued"] or 0) for m in meals)
discarded = len(discard_days(user.id, since))
rate = rescue_rate(rescued, discarded)

c1, c2, c3 = st.columns(3)
c1.metric("구출한 재료", f"{rescued}개", help="요리할 때 유통기한 3일 안에 쓴 재료 수")
c2.metric("버린 재료", f"{discarded}개", help="재고에서 '버림'으로 처리한 재료 수")
c3.metric("구출률", f"{rate:.0%}" if rate is not None else "–", help="구출 ÷ (구출 + 폐기)")
st.caption(f"요리 {len(meals)}번 · 다 먹은 재료 {used_count(user.id, since)}개")

# ── 주별 구출 vs 폐기 ─────────────────────────
st.subheader(f"주별 구출 vs 폐기 (최근 {WEEKS}주)")
all_meals = meal_rows(user.id, today - timedelta(weeks=WEEKS))
points = weekly_series(
    [(m["day"], int(m["rescued"] or 0)) for m in all_meals],
    discard_days(user.id, today - timedelta(weeks=WEEKS)),
    today,
    WEEKS,
)
long = pd.DataFrame(
    [{"주": f"{p.week.month}/{p.week.day}~", "종류": s, "개수": v}
     for p in points for s, v in (("구출", p.rescued), ("폐기", p.discarded))]
)
if long["개수"].sum() == 0:
    st.info("아직 기록이 없어요. 채팅에서 요리를 확정하거나 재고에서 '버림'을 누르면 쌓여요.")
else:
    mode = "dark" if getattr(getattr(st.context, "theme", None), "type", "light") == "dark" else "light"
    order = list(dict.fromkeys(long["주"]))
    chart = (
        alt.Chart(long)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("주:N", sort=order, title=None, axis=alt.Axis(labelAngle=0, domain=False, ticks=False)),
            xOffset=alt.XOffset("종류:N", sort=SERIES, scale=alt.Scale(paddingInner=0.06)),
            y=alt.Y("개수:Q", title=None,
                    axis=alt.Axis(format="d", tickCount=max(1, min(int(long["개수"].max()), 5)),
                                  domain=False, ticks=False, gridOpacity=0.35)),  # 개수라 정수 눈금만
            color=alt.Color("종류:N", sort=SERIES, scale=alt.Scale(domain=SERIES, range=COLORS[mode]),
                            legend=alt.Legend(orient="top", title=None)),
            tooltip=[alt.Tooltip("주:N", title="주(월요일)"), alt.Tooltip("종류:N"), alt.Tooltip("개수:Q", title="개수")],
        )
        .properties(height=280)
        .configure_scale(bandPaddingInner=0.3)
        .configure_view(stroke=None)
    )
    # Streamlit 버전마다 너비 옵션 이름이 달라서 (로컬 1.50: use_container_width, 서버 최신: width)
    if "width" in inspect.signature(st.altair_chart).parameters:
        st.altair_chart(chart, width="stretch")
    else:
        st.altair_chart(chart, use_container_width=True)
    with st.expander("표로 보기"):
        st.dataframe(
            pd.DataFrame([{"주(월요일)": p.week.isoformat(), "구출": p.rescued, "폐기": p.discarded} for p in points]),
            hide_index=True,
        )

# ── 자주 먹은 요리 ─────────────────────────────
st.subheader("자주 먹은 요리 TOP 5")
top = top_recipes([(m["title"], m["rating"]) for m in meals])
if not top:
    st.caption("이 기간에 요리한 기록이 없어요.")
for i, s in enumerate(top, 1):
    st.markdown(f"{i}. **{s.title}** · {s.count}번" + (f" · 👍 {s.likes}" if s.likes else "") + (f" · 👎 {s.dislikes}" if s.dislikes else ""))

# ── 평가 기다리는 요리 ─────────────────────────
pending = unrated_meals(user.id)
if pending:
    st.subheader("평가를 기다리는 요리")
    st.caption("평가와 후기는 다음 추천 순서에 반영되고, 후기에서 취향(예: 너무 매웠어 → 매운맛 싫어함)을 기억해요.")
    for m in pending:
        with st.expander(f"{m.title} · {m.day.month}/{m.day.day}"):
            if feedback_form(user.id, m.id, m.title, key=f"dash-fb-{m.id}"):
                st.rerun()
