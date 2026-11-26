import base64
import io
from datetime import date

from PIL import Image

from lib.ingest_rules import MAX_IMAGE_SIDE, parse_extraction, parse_shelf_estimates, prepare_image

TODAY = date(2026, 11, 26)


def test_parse_extraction_validates_and_defaults():
    raw = {
        "purchase_date": "2026.11.25",
        "items": [
            {"name": "  두부 ", "quantity": 2, "unit": "모", "confidence": 0.9},
            {"name": "우유", "quantity": "많이", "unit": "", "expires_at": "2026-12-03", "confidence": 1.4},
            {"name": "", "quantity": 1},
            {"name": "가" * 51, "quantity": 1},
            {"name": "대파", "quantity": -3, "unit": "아주아주아주긴단위이름", "confidence": "x"},
            "junk",
        ],
    }
    out = parse_extraction(raw, TODAY)
    assert [(d.name, d.quantity, d.unit) for d in out] == [("두부", 2, "모"), ("우유", 1, None), ("대파", 1, None)]
    assert all(d.purchased_at == date(2026, 11, 25) for d in out)
    assert out[1].expires_at == date(2026, 12, 3) and out[1].confidence == 1.0
    assert out[2].confidence == 0.5 and out[2].is_low_confidence


def test_future_or_missing_purchase_date_becomes_today():
    assert parse_extraction({"purchase_date": "2027-01-01", "items": [{"name": "두부", "quantity": 1}]}, TODAY)[0].purchased_at == TODAY
    assert parse_extraction({"items": [{"name": "두부", "quantity": 1}]}, TODAY)[0].purchased_at == TODAY
    assert parse_extraction("nope", TODAY) == [] and parse_extraction({"items": "x"}, TODAY) == []


def test_parse_shelf_estimates_only_asked_and_in_range():
    raw = {"items": [
        {"name": "고수", "category": "채소", "shelf_days": 5, "storage": "fridge"},
        {"name": "안물어봄", "shelf_days": 3, "storage": "fridge"},
        {"name": "할라피뇨", "shelf_days": 0, "storage": "fridge"},
        {"name": "미소", "shelf_days": 180, "storage": "basement"},
    ]}
    out = parse_shelf_estimates(raw, ["고수", "할라피뇨", "미소"])
    assert [(e.name, e.shelf_days, e.storage) for e in out] == [("고수", 5, "fridge"), ("미소", 180, "fridge")]


def test_prepare_image_resizes_and_converts_to_jpeg():
    buf = io.BytesIO()
    Image.new("RGBA", (4000, 2000), (255, 0, 0, 128)).save(buf, format="PNG")
    media_type, data = prepare_image(buf.getvalue())
    assert media_type == "image/jpeg"
    with Image.open(io.BytesIO(base64.b64decode(data))) as img:
        assert img.format == "JPEG" and max(img.size) == MAX_IMAGE_SIDE and img.size == (1568, 784)


def test_safety_nets_non_food_and_name_swap():
    raw = {"items": [
        {"line_text": "고수", "is_food": True, "name": "고추", "quantity": 1, "confidence": 0.9},  # 바꿔치기 → 원문
        {"line_text": "깨끗한나라 키친타올", "is_food": True, "name": "키친타올", "quantity": 1},  # 생활용품 단어
        {"line_text": "비닐봉투 20L", "is_food": False, "name": "봉투", "quantity": 1},
        {"line_text": "대파(1단)", "is_food": True, "name": "대파", "quantity": 1},
        {"line_text": "서울우유 1L", "is_food": True, "name": "우유", "quantity": 1},  # 원문이 길면 Claude 이름 유지
        {"line_text": "CJ 비비고 왕교자 1.05kg", "is_food": True, "name": "냉동만두", "quantity": 1},
    ]}
    assert [d.name for d in parse_extraction(raw, TODAY)] == ["고수", "대파", "우유", "냉동만두"]


def test_shelf_estimates_skip_non_food():
    raw = {"items": [{"name": "키친타올", "is_food": True, "shelf_days": 180, "storage": "room"},
                     {"name": "세탁볼", "is_food": False, "shelf_days": 365, "storage": "room"},
                     {"name": "고수", "is_food": True, "shelf_days": 5, "storage": "fridge"}]}
    assert [e.name for e in parse_shelf_estimates(raw, ["키친타올", "세탁볼", "고수"])] == ["고수"]
