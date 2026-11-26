"""비밀번호 암호화 — 순수 함수 (테스트 가능). DB에는 bcrypt 해시만 저장해요."""
import bcrypt

MIN_LENGTH = 8
MAX_BYTES = 72  # bcrypt 한계


def check_password_rules(password: str) -> None:
    if len(password) < MIN_LENGTH:
        raise ValueError(f"비밀번호는 {MIN_LENGTH}자 이상이어야 해요.")
    if len(password.encode()) > MAX_BYTES:
        raise ValueError("비밀번호가 너무 길어요.")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:MAX_BYTES], password_hash.encode())
    except ValueError:
        return False


# 없는 이메일로 로그인할 때도 같은 시간이 걸리게 하려고 쓰는 가짜 해시
DUMMY_HASH = hash_password("not-a-real-password")
