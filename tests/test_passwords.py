import pytest

from lib.passwords import check_password_rules, hash_password, verify_password


def test_hash_is_not_plaintext_and_verifies():
    h = hash_password("correct horse")
    assert "correct horse" not in h
    assert verify_password("correct horse", h)
    assert not verify_password("wrong horse!", h)


def test_same_password_gets_different_hash():
    assert hash_password("same-password") != hash_password("same-password")


def test_password_rules():
    check_password_rules("12345678")
    with pytest.raises(ValueError, match="8자 이상"):
        check_password_rules("short")
    with pytest.raises(ValueError, match="너무 길어"):
        check_password_rules("가" * 30)  # 90바이트


def test_verify_handles_garbage_hash():
    assert not verify_password("anything", "not-a-bcrypt-hash")
