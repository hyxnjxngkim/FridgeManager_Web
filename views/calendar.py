"""달력 — 내 일정 + 유통기한 + 짜 둔 식단을 한눈에 (Phase 5)."""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st
from streamlit_calendar import calendar

from lib.auth import require_user
from lib.dates import d_day_label, expiry_level, today_kst
from lib.inventory import get_inventory
from lib.meal_plan import get_plans_between
from lib.meal_plan_rules import day_label
from lib.schedule import KIND_ICONS, KIND_LABELS, add_event, delete_event, event_label, get_events

KIND_COLORS = {"busy": "#e07b39", "workout": "#3b82f6", "guests": "#8b5cf6", "normal": "#6b7280"}
EXPIRY_COLORS = {"expired": "#9ca3af", "urgent": "#dc2626", "soon": "#f59e0b", "ok": "#94a3b8"}
PLAN_COLOR = "#2f8f5b"

user = require_user()
today = today_kst()
range_start, range_end = today - timedelta(days=45), today + timedelta(days=75)

events = get_events(user.id, range_start, range_end)
items = get_inventory(user.id)
plans = get_plans_between(user.id, range_start, range_end)

st.title("달력")
st.caption("일정(⏰ 바쁜 날 · 💪 운동 · 👥 손님), 유통기한(⚠️), 짜 둔 식단(🍽)을 한눈에 봐요. 날짜를 누르면 그날 내용을 볼 수 있어요.")

cal_events = []
for e in events:
    cal_events.append({"title": event_label(e), "start": e.date.isoformat(), "allDay": True, "color": KIND_COLORS[e.kind]})
for i in items:
    if range_start <= i.expires_at <= range_end:
        level = expiry_level((i.expires_at - today).days)
        cal_events.append({"title": f"⚠️ {i.name}", "start": i.expires_at.isoformat(), "allDay": True, "color": EXPIRY_COLORS[level]})
for d, title in plans:
    cal_events.append({"title": f"🍽 {title}", "start": d.isoformat(), "allDay": True, "color": PLAN_COLOR})

result = calendar(
    events=cal_events,
    options={
        "initialView": "dayGridMonth",
        "locale": "ko",
        "timeZone": "UTC",  # 날짜만 다루므로 시간대 때문에 하루 밀리지 않게
        "height": 640,
        "dayMaxEvents": 3,
        "headerToolbar": {"left": "prev,next today", "center": "title", "right": ""},
    },
    callbacks=["dateClick", "eventClick"],
    key="fridge-calendar",
)

if isinstance(result, dict):
    if result.get("callback") == "dateClick":
        st.session_state.cal_selected = result["dateClick"]["date"][:10]
    elif result.get("callback") == "eventClick":
        st.session_state.cal_selected = result["eventClick"]["event"]["start"][:10]
selected = date.fromisoformat(st.session_state.get("cal_selected", today.isoformat()))

# ── 선택한 날 ────────────────────────────────
st.subheader(f"{day_label(selected)}" + (" · 오늘" if selected == today else ""))
day_events = [e for e in events if e.date == selected]
day_items = [i for i in items if i.expires_at == selected]
day_plans = [t for d, t in plans if d == selected]

if not (day_events or day_items or day_plans):
    st.caption("이날은 아무것도 없어요.")
for e in day_events:
    c1, c2 = st.columns([5, 1])
    c1.markdown(event_label(e))
    if c2.button("삭제", key=f"del-ev-{e.id}"):
        delete_event(user.id, e.id)
        st.rerun()
for t in day_plans:
    st.markdown(f"🍽 식단: **{t}**")
for i in day_items:
    st.markdown(f"⚠️ {i.name} 유통기한 ({d_day_label((i.expires_at - today).days)})")

# ── 일정 추가 ────────────────────────────────
with st.form("add-event", clear_on_submit=True):
    st.markdown("**일정 추가** · 식단을 짤 때 반영돼요")
    c1, c2 = st.columns(2)
    day = c1.date_input("날짜", value=selected, format="YYYY-MM-DD")
    kind = c2.selectbox("종류", list(KIND_LABELS), format_func=lambda k: f"{KIND_ICONS[k]} {KIND_LABELS[k]}")
    c3, c4 = st.columns(2)
    title = c3.text_input("메모 (선택)", placeholder="예: 야근, 헬스, 집들이")
    guests = c4.number_input("손님 수 (손님일 때)", min_value=0, max_value=30, value=0, step=1)
    if st.form_submit_button("추가", type="primary"):
        try:
            add_event(user.id, day, kind, title, int(guests) or None)
            st.session_state.cal_selected = day.isoformat()
            st.rerun()
        except ValueError as e:
            st.error(str(e))
