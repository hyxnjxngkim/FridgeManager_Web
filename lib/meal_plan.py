"""주간 식단 저장·조회 (meal_plans). 레시피는 그때 모습 그대로 jsonb 로 저장해요."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Optional

from psycopg.types.json import Jsonb

from lib.db import fetch_all, transaction
from lib.meal_plan_rules import PlannedMeal
from lib.models import Recipe, RecipeIngredient


@dataclass
class SavedMeal:
    day: date
    recipe: Recipe
    servings: Optional[int]
    reason: str


def recipe_to_json(recipe: Recipe) -> dict:
    return asdict(recipe)


def recipe_from_json(data: dict) -> Recipe:
    data = dict(data)
    data["ingredients"] = [RecipeIngredient(**i) for i in data.get("ingredients", [])]
    known = Recipe.__dataclass_fields__
    return Recipe(**{k: v for k, v in data.items() if k in known})


def save_week(user_id: str, start: date, meals: list[PlannedMeal], days: int = 7) -> None:
    """start 부터 days 일 동안의 식단을 새로 짠 것으로 바꿔요 (한 번에)."""
    end = start + timedelta(days=days - 1)
    with transaction() as conn:
        conn.execute("delete from meal_plans where user_id = %s and date between %s and %s", (user_id, start, end))
        for m in meals:
            if m.match is None:
                continue
            r = m.match.recipe
            conn.execute(
                "insert into meal_plans (user_id, date, recipe_id, recipe_title, recipe, servings, reason)"
                " values (%s, %s, %s, %s, %s, %s, %s)",
                (user_id, m.day, r.id, r.title, Jsonb(recipe_to_json(r)), m.servings, m.reason),
            )


def get_week(user_id: str, start: date, days: int = 7) -> list[SavedMeal]:
    rows = fetch_all(
        "select date, recipe, servings, reason from meal_plans"
        " where user_id = %s and date between %s and %s order by date",
        (user_id, start, start + timedelta(days=days - 1)),
    )
    return [SavedMeal(r["date"], recipe_from_json(r["recipe"]), r["servings"], r["reason"] or "") for r in rows]


def get_plans_between(user_id: str, start: date, end: date) -> list[tuple[date, str]]:
    """달력용: (날짜, 메뉴 이름)"""
    rows = fetch_all(
        "select date, recipe_title from meal_plans where user_id = %s and date between %s and %s order by date",
        (user_id, start, end),
    )
    return [(r["date"], r["recipe_title"]) for r in rows]
