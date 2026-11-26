"""레시피 검색 연결점 — Phase 4(A)는 이 파일을 통해서만 레시피를 찾아요.

B의 lib/recipes.py (Phase 3)가 main 에 들어오면 자동으로 그걸 쓰고,
아직 없으면 lib/fake_recipes.py 의 예시 레시피를 써요.
"""
from __future__ import annotations

try:
    from lib.recipes import search_recipes  # type: ignore[attr-defined]  # 팀원 B (Phase 3)

    USING_SAMPLE_RECIPES = False
except ImportError:
    from lib.fake_recipes import search_recipes  # noqa: F401

    USING_SAMPLE_RECIPES = True
