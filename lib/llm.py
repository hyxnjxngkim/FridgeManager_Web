"""Claude 클라이언트 (AWS Bedrock, bedrock-runtime / InvokeModel).

이 AWS 계정은 bedrock-mantle 권한이 없고 bedrock-runtime 만 열려 있어서 AnthropicBedrock 을 써요.
인증은 AWS 기본 방식: EC2 에서는 서버 역할(IAM), 로컬에서는 `aws login` 등.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from anthropic import AnthropicBedrock

from lib.config import AWS_REGION


@lru_cache(maxsize=1)
def get_client() -> AnthropicBedrock:
    return AnthropicBedrock(aws_region=AWS_REGION)


def llm_unavailable_reason() -> Optional[str]:
    """Claude 를 부를 수 없으면 이유를, 부를 수 있으면 None 을 돌려줘요 (네트워크 호출 없음)."""
    try:
        import boto3

        if boto3.Session().get_credentials() is None:
            return "AWS 자격증명이 없어요. 로컬이면 `aws login`으로 로그인하거나 EC2에서 실행해 주세요."
    except Exception as e:  # boto3 설정 오류 등
        return f"AWS 설정을 읽지 못했어요: {e}"
    return None
