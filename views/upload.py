"""재료 등록 — 영수증·냉장고 사진에서 재료를 뽑아 확인 후 재고에 저장 (Phase 2)."""
from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from lib.auth import require_user
from lib.dates import parse_date, today_kst
from lib.ingest import IngestError, extract_items, model_for, save_drafts
from lib.ingest_rules import DraftItem
from lib.inventory import get_catalog
from lib.llm import get_client, llm_unavailable_reason

KINDS = {"receipt": "🧾 영수증", "fridge": "🧊 냉장고 사진"}
HINTS = {
    "receipt": "영수증 전체가 나오게, 글자가 흐리지 않게 찍어 주세요. 빠르고 싼 모델(Haiku 4.5)이라 "
               "비슷한 글자를 잘못 읽을 수 있어요 (예: 고수 → 고추). 저장 전에 이름을 꼭 확인해 주세요.",
    "fridge": "칸마다 재료가 잘 보이게 찍어 주세요. 여러 재료를 알아봐야 해서 더 강한 모델을 써요. (Sonnet 4.6)",
}

user = require_user()
today = today_kst()

if msg := st.session_state.pop("ingest_msg", None):
    st.toast(msg, icon="✅")

st.title("재료 등록")
st.caption("사진을 올리면 Claude 가 재료·수량·구입일을 뽑아요. 확인 표에서 고친 뒤 저장해요.")

unavailable = llm_unavailable_reason()
if unavailable:
    st.warning(f"지금은 사진 인식을 쓸 수 없어요. {unavailable}\n\n재료는 왼쪽 메뉴의 **재고** 페이지에서 직접 추가할 수 있어요.")
    st.stop()

kind = st.radio("무엇을 올릴까요?", list(KINDS), format_func=KINDS.get, horizontal=True, key="ingest_kind")
st.caption(HINTS[kind])

source = st.radio("사진", ["파일 올리기", "카메라로 찍기"], horizontal=True, label_visibility="collapsed", key="ingest_source")
if source == "파일 올리기":
    photo = st.file_uploader("사진 파일", type=["jpg", "jpeg", "png", "webp"], key="ingest_file")
else:
    photo = st.camera_input("사진 찍기", key="ingest_camera")

if st.button("🔍 재료 뽑기", type="primary", disabled=photo is None):
    with st.spinner("사진에서 재료를 찾고 있어요…"):
        try:
            catalog_names = [c.name for c in get_catalog()]
            st.session_state.ingest_drafts = extract_items(get_client(), photo.getvalue(), kind, catalog_names, today)
            st.session_state.ingest_model = model_for(kind)
        except IngestError as e:
            st.error(str(e))

drafts: list[DraftItem] | None = st.session_state.get("ingest_drafts")
if drafts is None:
    st.stop()
if not drafts:
    st.info("사진에서 식재료를 찾지 못했어요. 더 밝고 가까이 찍어 보세요.")
    st.stop()

st.subheader(f"찾은 재료 {len(drafts)}개")
st.caption(
    "⚠️ 표시는 Claude 가 확실하지 않은 항목이에요. 확인하고 고쳐 주세요. "
    "유통기한을 비우면 재료별 보통 보관 기간으로 추정해요. 줄을 추가하거나 지울 수도 있어요."
)
df = pd.DataFrame(
    [
        {
            "저장": True,
            "확인": "⚠️" if d.is_low_confidence else "✅",
            "이름": d.name,
            "수량": d.quantity,
            "단위": d.unit or "",
            "구입일": d.purchased_at,
            "유통기한": d.expires_at,
        }
        for d in drafts
    ]
)
edited = st.data_editor(
    df,
    key="ingest_editor",
    num_rows="dynamic",
    hide_index=True,
    width="stretch",
    disabled=["확인"],
    column_config={
        "저장": st.column_config.CheckboxColumn(width="small"),
        "확인": st.column_config.TextColumn(width="small", help="⚠️ = 확실하지 않음"),
        "이름": st.column_config.TextColumn(required=True, max_chars=50),
        "수량": st.column_config.NumberColumn(min_value=0.0, step=0.1),
        "단위": st.column_config.TextColumn(max_chars=10),
        "구입일": st.column_config.DateColumn(format="YYYY-MM-DD"),
        "유통기한": st.column_config.DateColumn(format="YYYY-MM-DD", help="비우면 추정"),
    },
)


def _is_blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or (hasattr(pd, "isna") and pd.isna(v))


def rows_to_items(frame: pd.DataFrame) -> list[DraftItem]:
    items = []
    for _, r in frame.iterrows():
        name = "" if _is_blank(r["이름"]) else str(r["이름"]).strip()
        if not name or (not _is_blank(r["저장"]) and not bool(r["저장"])):
            continue
        qty = 1.0 if _is_blank(r["수량"]) or float(r["수량"]) <= 0 else float(r["수량"])
        unit = None if _is_blank(r["단위"]) else (str(r["단위"]).strip() or None)
        purchased = today if _is_blank(r["구입일"]) else parse_date(r["구입일"])
        expires = None if _is_blank(r["유통기한"]) else parse_date(r["유통기한"])
        items.append(DraftItem(name, qty, unit, purchased, expires, 1.0))
    return items


c1, c2 = st.columns(2)
if c1.button("재고에 저장", type="primary", width="stretch"):
    items = rows_to_items(edited)
    if not items:
        st.error("저장할 재료가 없어요. '저장' 칸을 확인해 주세요.")
    else:
        with st.spinner("저장하는 중… (처음 보는 재료는 보관 기간을 추정해요)"):
            saved, failed = save_drafts(user.id, items, get_client())
        for name, reason in failed:
            st.error(f"{name}: {reason}")
        if saved:
            st.session_state.ingest_msg = f"재고에 {len(saved)}개를 넣었어요: {', '.join(saved)}"
            if not failed:
                for key in ("ingest_drafts", "ingest_editor", "ingest_file", "ingest_camera"):
                    st.session_state.pop(key, None)
                st.rerun()
if c2.button("다시 하기", width="stretch"):
    for key in ("ingest_drafts", "ingest_editor", "ingest_file", "ingest_camera"):
        st.session_state.pop(key, None)
    st.rerun()
