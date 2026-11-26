from datetime import date

from lib.stats_rules import rescue_rate, top_recipes, week_start, weekly_series

TODAY = date(2026, 11, 26)  # 목요일


def test_week_start_is_monday():
    assert week_start(TODAY) == date(2026, 11, 23)
    assert week_start(date(2026, 11, 23)) == date(2026, 11, 23)


def test_rescue_rate():
    assert rescue_rate(3, 1) == 0.75
    assert rescue_rate(0, 0) is None
    assert rescue_rate(0, 2) == 0


def test_weekly_series_fills_empty_weeks_and_ignores_old():
    meals = [(date(2026, 11, 24), 2), (date(2026, 11, 26), 1), (date(2026, 11, 17), 3), (date(2026, 9, 1), 9)]
    discards = [date(2026, 11, 25), date(2026, 11, 10)]
    pts = weekly_series(meals, discards, TODAY, weeks=4)
    assert [p.week for p in pts] == [date(2026, 11, 2), date(2026, 11, 9), date(2026, 11, 16), date(2026, 11, 23)]
    assert [(p.rescued, p.discarded) for p in pts] == [(0, 0), (0, 1), (3, 0), (3, 1)]


def test_top_recipes_counts_and_ratings():
    rows = [("된장국", 1), ("된장국", None), ("계란찜", -1), ("된장국", 1), ("계란찜", None), (None, 1), ("국수", None)]
    top = top_recipes(rows, limit=2)
    assert [(t.title, t.count, t.likes, t.dislikes) for t in top] == [("된장국", 3, 2, 0), ("계란찜", 2, 0, 1)]
