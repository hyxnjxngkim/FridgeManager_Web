"""재고 페이지 — 재료 추가 + 표에서 바로 수정/처리."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib.catalog import estimate_expiry, match_catalog
from lib.dates import parse_date, today_kst
from lib.inventory import (
    add_item,
    days_left,
    delete_item,
    get_catalog,
    get_inventory,
    set_status,
    update_item,
)
from lib.inventory_rules import ItemInput
from lib.ui import expiry_label

UNITS = ["개", "g", "kg", "ml", "L", "팩", "봉", "모", "단", "통", "캔", "병", "줄", "마리"]
STORAGE_LABEL = {"fridge": "냉장", "freezer": "냉동", "room": "실온"}
SOURCE_LABEL = {"estimated": "추정", "label": "라벨", "manual": "직접 입력"}
ACTIONS = ["다 먹음", "버림", "삭제"]

today = today_kst()
catalog = get_catalog()
items = get_inventory()

# 지난 실행에서 남긴 결과 메시지
if msg := st.session_state.pop("inventory_msg", None):
    st.toast(msg, icon="✅")

st.title("재고")
urgent = sum(1 for i in items if 0 <= days_left(i, today) <= 3)
st.caption(
    f"재료 {len(items)}개 · 3일 안에 써야 할 재료 {urgent}개"
    if items
    else "냉장고 속 재료와 유통기한을 관리해요."
)

# ── 재료 추가 ────────────────────────────────
ADD_DEFAULTS = {
    "add_name": None,
    "add_qty": 1.0,
    "add_unit": None,
    "add_purchased": today,
    "add_expires": None,
}
# 입력칸 기본값은 여기서만 정해요 (위젯에 value= 를 같이 주면 Streamlit 경고가 나요)
for key, default in ADD_DEFAULTS.items():
    st.session_state.setdefault(key, default)


def on_add() -> None:
    """추가 버튼 콜백 — 콜백 안에서는 입력칸 값을 비울 수 있어요."""
    s = st.session_state
    try:
        add_item(
            ItemInput(
                name=s.add_name or "",
                quantity=s.add_qty,
                unit=s.add_unit,
                purchased_at=s.add_purchased,
                expires_at=s.add_expires,
            )
        )
    except ValueError as e:
        s.add_error = str(e)
        return
    s.inventory_msg = f"'{s.add_name}'을(를) 추가했어요."
    for key, default in ADD_DEFAULTS.items():
        s[key] = default


with st.container(border=True):
    st.subheader("재료 추가")
    c1, c2, c3 = st.columns([2, 1, 1])
    name = c1.selectbox(
        "이름",
        [c.name for c in catalog],
        placeholder="예: 두부 (목록에 없으면 직접 입력)",
        accept_new_options=True,
        key="add_name",
    )
    c2.number_input("수량", min_value=0.0, step=1.0, key="add_qty")
    c3.selectbox("단위", UNITS, placeholder="개", accept_new_options=True, key="add_unit")

    c4, c5 = st.columns(2)
    purchased = c4.date_input("구입일", key="add_purchased", format="YYYY-MM-DD")
    c5.date_input("유통기한 (선택)", key="add_expires", format="YYYY-MM-DD")

    # 입력하는 동안 추정 유통기한 미리 보여주기
    if name:
        match = match_catalog(name, catalog)
        if match:
            st.caption(
                f"{STORAGE_LABEL[match.storage]} 보통 {match.default_shelf_days}일 → "
                f"**{estimate_expiry(purchased, match)}**까지로 추정해요. (유통기한을 넣으면 그 날짜를 써요)"
            )
        else:
            st.caption("카탈로그에 없는 재료예요. 유통기한을 직접 입력해 주세요.")

    if error := st.session_state.pop("add_error", None):
        st.error(error)
    st.button("추가", type="primary", on_click=on_add)

# ── 재고 목록 ────────────────────────────────
st.subheader("냉장고 속 재료")
if not items:
    st.info("냉장고가 비어 있어요. 위에서 재료를 추가해 보세요.")
    st.stop()

original = pd.DataFrame(
    [
        {
            "id": i.id,
            "남은 기간": expiry_label(days_left(i, today)),
            "이름": i.name,
            "수량": i.quantity,
            "단위": i.unit or "",
            "구입일": i.purchased_at,
            "유통기한": i.expires_at,
            "출처": SOURCE_LABEL[i.expiry_source],
            "처리": None,
        }
        for i in items
    ]
)

edited = st.data_editor(
    original,
    key="inventory_editor",
    hide_index=True,
    width="stretch",
    disabled=["남은 기간", "출처"],
    column_config={
        "id": None,  # 숨김
        "이름": st.column_config.TextColumn(required=True, max_chars=50),
        "수량": st.column_config.NumberColumn(min_value=0.0, step=0.1, required=True),
        "단위": st.column_config.TextColumn(max_chars=10),
        "구입일": st.column_config.DateColumn(format="YYYY-MM-DD", required=True),
        "유통기한": st.column_config.DateColumn(format="YYYY-MM-DD", required=True),
        "처리": st.column_config.SelectboxColumn(
            options=ACTIONS, help="다 먹음·버림은 통계에 남고, 삭제는 잘못 등록한 재료를 지워요."
        ),
    },
)
st.caption("칸을 눌러 바로 고칠 수 있어요. 고친 뒤 아래 **변경 저장**을 눌러야 반영돼요.")

# 바뀐 내용 모으기
by_id = {i.id: i for i in items}
actions: list[tuple[str, str]] = []  # (id, 처리)
updates: list[tuple[str, ItemInput]] = []
for (_, before), (_, after) in zip(original.iterrows(), edited.iterrows()):
    item = by_id[before["id"]]
    if after["처리"] in ACTIONS:
        actions.append((item.id, after["처리"]))
        continue
    changed = ItemInput(
        name=str(after["이름"] or ""),
        quantity=float(after["수량"]) if pd.notna(after["수량"]) else 0.0,
        unit=str(after["단위"] or "") or None,
        purchased_at=parse_date(after["구입일"]),
        expires_at=parse_date(after["유통기한"]),
    )
    if (
        changed.name != item.name
        or changed.quantity != item.quantity
        or (changed.unit or None) != (item.unit or None)
        or changed.purchased_at != item.purchased_at
        or changed.expires_at != item.expires_at
    ):
        updates.append((item.id, changed))

if actions or updates:
    summary = [f"- {by_id[i].name}: **{a}**" for i, a in actions]
    summary += [f"- {by_id[i].name}: 수정" for i, _ in updates]
    st.warning("저장하면 다음이 반영돼요:\n" + "\n".join(summary))

    if st.button("변경 저장", type="primary"):
        errors = []
        for item_id, action in actions:
            if action == "삭제":
                delete_item(item_id)
            else:
                set_status(item_id, "used" if action == "다 먹음" else "discarded")
        for item_id, changed in updates:
            try:
                update_item(by_id[item_id], changed)
            except ValueError as e:
                errors.append(f"{by_id[item_id].name}: {e}")
        if errors:
            st.session_state.inventory_msg = None
            st.error("\n".join(errors))
        else:
            st.session_state.inventory_msg = "변경 내용을 저장했어요."
            st.session_state.pop("inventory_editor", None)
            st.rerun()
