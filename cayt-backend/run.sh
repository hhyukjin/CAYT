#!/bin/bash
# CAYT Backend 실행 스크립트
# STT 작업 중 reload로 인한 중단 방지

cd "$(dirname "$0")"

echo "CAYT Backend 시작..."
echo "서버: http://127.0.0.1:8000"
echo "문서: http://127.0.0.1:8000/docs"
echo ""
echo "종료: Ctrl+C"
echo ""

# --reload 옵션 제거 (STT 다운로드 중 재시작 방지)
# 개발 중 코드 변경 시 수동으로 재시작 필요
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 또는 reload 사용 시 (임시 폴더 제외):
# uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-exclude "*.mp3" --reload-exclude "*.m4a" --reload-exclude "*.webm"
