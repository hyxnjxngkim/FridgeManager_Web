"""apply_cook 을 진짜 DB 연결과 같은 모양(dict 행)을 돌려주는 가짜 연결로 검사.

실제 서비스에서 row[0] 으로 꺼내다 KeyError 가 났던 문제의 회귀 테스트예요
(lib/db.py 의 연결 풀은 row_factory=dict_row 라 행이 dict).
"""
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace as NS

import lib.cooking as cooking
from lib.cooking_rules import CookPlan, DeductionLine

TODAY = date(2026, 11, 26)


class DictRowConn:
    def __init__(self, recipe_exists=True):
        self.sql = []
        self.recipe_exists = recipe_exists

    def execute(self, sql, params=()):
        self.sql.append((sql, params))
        if sql.startswith("select 1 from recipes"):
            return NS(fetchone=lambda: {"?column?": 1} if self.recipe_exists else None)
        if "returning id" in sql:
            return NS(fetchone=lambda: {"id": "meal-uuid-1"})  # dict 행 — row[0] 이면 KeyError
        return NS(fetchone=lambda: None, rowcount=1)


def plan(recipe_id="fake-28"):
    lines = [
        DeductionLine("i1", "귤", "귤", 9, "개", 1, date(2026, 11, 27), 1),
        DeductionLine("i2", "소금", "소금", 1, "봉", 0, date(2027, 5, 1), 156),  # 0 은 건너뜀
    ]
    return CookPlan(recipe_id, "감귤 김치", 1, lines, [])


def test_apply_cook_reads_dict_row_and_records(monkeypatch):
    conn = DictRowConn()

    @contextmanager
    def fake_tx():
        yield conn

    monkeypatch.setattr(cooking, "transaction", fake_tx)
    result = cooking.apply_cook("u1", plan())
    assert result.meal_log_id == "meal-uuid-1" and result.rescued == 1
    updates = [p for s, p in conn.sql if s.startswith("update inventory")]
    assert updates == [(1, 1, "i1", "u1")]  # 뺄 양 0 인 소금은 안 건드림, user_id 조건 포함
    insert = next(p for s, p in conn.sql if s.startswith("insert into meal_logs"))
    assert insert == ("u1", None, "감귤 김치", 1, 1)  # uuid 가 아닌 레시피 id 는 null


def test_apply_cook_keeps_real_recipe_id(monkeypatch):
    conn = DictRowConn(recipe_exists=True)

    @contextmanager
    def fake_tx():
        yield conn

    monkeypatch.setattr(cooking, "transaction", fake_tx)
    rid = "0b7e7f1c-2a3d-4c5e-8f90-123456789abc"
    cooking.apply_cook("u1", plan(rid))
    insert = next(p for s, p in conn.sql if s.startswith("insert into meal_logs"))
    assert insert[1] == rid
