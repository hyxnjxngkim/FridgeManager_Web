from datetime import date

from lib.models import Preference, Recipe, RecipeIngredient as I, RecipeMatch
from lib.personalize import RecipeHistory, personalize

TODAY = date(2026, 11, 26)


def m(title, score, ings=(), tags=()):
    return RecipeMatch(Recipe(title, title, [I(n) for n in ings], "", tags=list(tags)), score)


def titles(ms):
    return [x.recipe.title for x in ms]


def test_liked_recipe_moves_up_disliked_moves_down():
    ms = [m("A", 3), m("B", 3), m("C", 3)]
    hist = {"B": RecipeHistory(1.0, date(2026, 11, 1)), "A": RecipeHistory(-1.0, date(2026, 11, 1))}
    assert titles(personalize(ms, hist, [], TODAY)) == ["B", "C", "A"]


def test_recently_cooked_is_penalized():
    ms = [m("된장국", 3), m("계란찜", 2)]
    hist = {"된장국": RecipeHistory(None, date(2026, 11, 24))}  # 2일 전에 먹음
    assert titles(personalize(ms, hist, [], TODAY)) == ["계란찜", "된장국"]


def test_dislike_and_like_preferences():
    ms = [m("매운 떡볶이", 3, ["떡"], ["매운맛"]), m("오이무침", 3, ["오이"]), m("샐러드", 2, ["양상추"], ["다이어트"])]
    prefs = [Preference("1", "dislike", "매운맛", 1), Preference("2", "diet", "다이어트", 1)]
    out = personalize(ms, {}, prefs, TODAY)
    assert titles(out) == ["샐러드", "오이무침", "매운 떡볶이"]  # 3점 동점은 이름순
    assert out[0].score == 3  # 샐러드 2 + 다이어트 1


def test_strength_multiplies_and_like_is_capped():
    prefs = [Preference("1", "like", "두부", 5)]
    out = personalize([m("두부조림", 0, ["두부"])], {}, prefs, TODAY)
    assert out[0].score == 3  # 최대 +3


def test_original_matches_not_mutated():
    ms = [m("A", 1)]
    personalize(ms, {"A": RecipeHistory(1.0, None)}, [], TODAY)
    assert ms[0].score == 1
