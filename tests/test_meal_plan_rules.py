from datetime import date

from lib.meal_plan_rules import day_label, day_rule, plan_week
from lib.models import InventoryItem, Recipe, RecipeIngredient as I, RecipeMatch, ScheduleEvent

MON = date(2026, 11, 30)


def inv(name, expires):
    return InventoryItem(name, name, None, 1, "개", MON, expires, "estimated", "active")


def rec(id, title, ings, minutes=20, servings=2, tags=()):
    return Recipe(id, title, [I(n, 1, "개") for n in ings], "", cook_minutes=minutes, servings=servings, tags=list(tags))


RECIPES = [
    rec("tofu", "두부조림", ["두부"], minutes=15),
    rec("sprout", "콩나물국", ["콩나물"], minutes=10),
    rec("egg", "계란말이", ["달걀"], minutes=10, tags=["고단백"]),
    rec("rice", "볶음밥", ["밥"], minutes=20),
]


def fake_search(calls=None):
    def search(names, max_minutes, servings, tags):
        if calls is not None:
            calls.append((tuple(names), max_minutes, servings, tuple(tags or ())))
        out = []
        for r in RECIPES:
            if max_minutes and r.cook_minutes > max_minutes:
                continue
            uses = [n for n in names if any(n == i.name for i in r.ingredients)]
            score = len(uses) * 3 + len(set(tags or []) & set(r.tags))
            out.append(RecipeMatch(r, score, uses, []))
        return sorted(out, key=lambda m: -m.score)
    return search


def test_day_rule_labels():
    events = [ScheduleEvent("1", MON, "busy"), ScheduleEvent("2", MON, "guests", guests=3), ScheduleEvent("3", MON, "workout")]
    r = day_rule(MON, events)
    assert (r.max_minutes, r.servings, r.tags) == (15, 4, ["고단백"])
    assert len(r.labels) == 3
    assert day_rule(date(2026, 12, 1), events).labels == []
    assert day_label(MON) == "11/30(월)"


def test_earliest_expiring_goes_first_and_no_repeats():
    expiring = [inv("콩나물", date(2026, 12, 1)), inv("두부", date(2026, 11, 30))]
    plan = plan_week(MON, [], expiring, fake_search(), days=4)
    titles = [m.match.recipe.title for m in plan]
    assert titles[0] == "두부조림"  # 두부가 오늘 끝남
    assert titles[1] == "콩나물국"
    assert len(set(titles)) == 4  # 한 주에 한 번씩
    assert "구출: 두부" in plan[0].reason


def test_expired_by_that_day_is_not_used():
    plan = plan_week(MON, [], [inv("두부", date(2026, 11, 30))], fake_search(), days=2)
    assert plan[1].match.uses_expiring == []  # 화요일엔 두부가 이미 지남


def test_busy_day_passes_max_minutes_and_guests_scale_servings():
    calls = []
    events = [ScheduleEvent("1", MON, "busy"), ScheduleEvent("2", date(2026, 12, 1), "guests", guests=5)]
    plan = plan_week(MON, events, [inv("두부", date(2026, 12, 5))], fake_search(calls), days=2)
    assert calls[0][1] == 15
    assert plan[0].match.recipe.cook_minutes <= 15
    assert plan[1].servings == 6 and "손님 5명" in plan[1].reason


def test_no_recipe_and_repeat_when_short():
    empty = plan_week(MON, [], [], lambda *a: [], days=1)
    assert empty[0].match is None and "없어요" in empty[0].reason
    plan = plan_week(MON, [], [], fake_search(), days=6)
    assert "반복" in plan[-1].reason


def test_busy_allows_15_minutes_but_not_20():
    events = [ScheduleEvent("1", MON, "busy")]
    plan = plan_week(MON, events, [inv("두부", date(2026, 12, 5))], fake_search(), days=1)
    assert plan[0].match.recipe.title == "두부조림"  # 15분 → 바쁜 날에도 OK
    assert "15분" in plan[0].reason
    plan = plan_week(MON, events, [inv("밥", date(2026, 12, 5))], fake_search(), days=1)
    assert plan[0].match.recipe.title != "볶음밥"  # 20분 → 바쁜 날엔 빠짐


def b_like_search(calls=None):
    """B의 진짜 검색처럼: 재료가 비면 빈 결과, 넘긴 재료를 하나도 안 쓰는 레시피는 빼요."""
    inner = fake_search(calls)

    def search(names, max_minutes, servings, tags):
        if not names:
            return []
        return [m for m in inner(names, max_minutes, servings, tags) if m.uses_expiring]
    return search


def test_falls_back_to_stock_when_expiring_runs_out():
    expiring = [inv("두부", date(2026, 11, 30))]
    stock = expiring + [inv("콩나물", date(2026, 12, 10)), inv("달걀", date(2026, 12, 20))]
    plan = plan_week(MON, [], expiring, b_like_search(), days=3, stock=stock)
    assert [m.match.recipe.title for m in plan] == ["두부조림", "콩나물국", "계란말이"]
    assert "구출: 두부" in plan[0].reason
    assert plan[1].reason == "냉장고 재료: 콩나물"  # 임박 재료가 아니니 '구출'로 세지 않아요


def test_without_stock_days_stay_empty_with_b_like_search():
    plan = plan_week(MON, [], [inv("두부", date(2026, 11, 30))], b_like_search(), days=2)
    assert plan[0].match and plan[1].match is None  # stock 을 안 주면 예전처럼 비어요 (그래서 화면은 stock 을 넘겨요)
