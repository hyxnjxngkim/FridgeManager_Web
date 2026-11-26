#!/usr/bin/env bash
# 로컬 개발용 SSH 터널: 내 컴퓨터 localhost:5433 → EC2 → RDS:5432
# RDS는 EC2에서만 접속되도록 막혀 있어서, EC2를 거쳐 접속합니다.
# 사용법: ./scripts/tunnel.sh   (열어 둔 채로 다른 터미널에서 streamlit run app.py)
set -euo pipefail
cd "$(dirname "$0")/.."

# .env 에서 TUNNEL_* 값 읽기
set -a; [ -f .env ] && . ./.env; set +a

: "${TUNNEL_SSH_KEY:?.env 에 TUNNEL_SSH_KEY (EC2 접속 키 경로)를 넣어 주세요}"
: "${TUNNEL_EC2:?.env 에 TUNNEL_EC2 (예: ec2-user@1.2.3.4)를 넣어 주세요}"
: "${TUNNEL_RDS_HOST:?.env 에 TUNNEL_RDS_HOST (RDS 주소)를 넣어 주세요}"
LOCAL_PORT="${PG_PORT:-5433}"

echo "터널 열기: localhost:${LOCAL_PORT} → ${TUNNEL_RDS_HOST}:5432 (Ctrl+C로 종료)"
exec ssh -i "${TUNNEL_SSH_KEY/#\~/$HOME}" \
  -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -N -L "${LOCAL_PORT}:${TUNNEL_RDS_HOST}:5432" "${TUNNEL_EC2}"
