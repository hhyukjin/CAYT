# CAYT Backend

**Context-Aware YouTube Translator** - 맥락 기반 유튜브 자막 번역 백엔드 서버

## 요구 사항

- **Python**: 3.11.x (권장)
- **패키지 매니저**: [uv](https://github.com/astral-sh/uv)

## 프로젝트 구조

```
cayt-backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 애플리케이션 진입점
│   ├── models/
│   │   ├── __init__.py
│   │   └── subtitle.py      # Pydantic 데이터 모델
│   ├── modules/
│   │   ├── __init__.py
│   │   └── subtitle_extractor.py  # 자막 추출 핵심 모듈
│   └── utils/
│       ├── __init__.py
│       └── parsers.py       # URL 파싱, VTT 파싱 유틸리티
├── config/
│   ├── __init__.py
│   └── settings.py          # 환경 설정
├── tests/
│   ├── __init__.py
│   └── test_parsers.py      # 유틸리티 함수 테스트
├── .env.example             # 환경 변수 예시
├── .gitignore
├── pyproject.toml           # uv/pip 프로젝트 설정
├── requirements.txt         # pip 호환 의존성
└── README.md
```

## 설치 및 실행 (uv 사용)

### 1. 프로젝트 폴더 이동

```bash
cd cayt-backend
```

### 2. Python 3.11 가상환경 생성

```bash
# Python 3.11로 가상환경 생성
uv venv --python 3.11

# 가상환경 활성화
# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

### 3. 의존성 설치

```bash
# 기본 의존성 설치
uv pip install -r requirements.txt

# 또는 pyproject.toml 사용 (개발 의존성 포함)
uv pip install -e ".[dev]"
```

### 4. 환경 변수 설정

```bash
cp .env.example .env
# 필요시 .env 파일 수정
```

### 5. 서버 실행

```bash
# 개발 모드 (자동 리로드)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 또는
python app/main.py
```

### 6. API 문서 확인

서버 실행 후 브라우저에서:
- **Swagger UI**: http://127.0.0.1:8000/docs
- **ReDoc**: http://127.0.0.1:8000/redoc

## API 엔드포인트

### 자막 목록 조회

```bash
GET /api/v1/subtitles/list?video_url=VIDEO_URL_OR_ID
```

### 자막 추출

```bash
# GET 방식
GET /api/v1/subtitles/extract?video_url=VIDEO_URL&language=en&prefer_manual=true

# POST 방식
POST /api/v1/subtitles/extract
Content-Type: application/json

{
    "video_url": "https://www.youtube.com/watch?v=VIDEO_ID",
    "language": "en",
    "prefer_manual": true
}
```

### 전체 텍스트 추출 (LLM 컨텍스트용)

```bash
GET /api/v1/subtitles/text?video_url=VIDEO_URL&language=en
```

## 응답 예시

### 자막 추출 응답

```json
{
    "success": true,
    "message": "'en' 자막 추출 완료 (150개 세그먼트)",
    "data": {
        "video_id": "dQw4w9WgXcQ",
        "title": "Video Title",
        "language": "en",
        "subtitle_type": "manual",
        "segments": [
            {
                "start": 0.0,
                "end": 4.5,
                "text": "Hello, welcome to this video."
            },
            ...
        ]
    },
    "available_subtitles": [
        {
            "language": "en",
            "language_name": "English",
            "subtitle_type": "manual",
            "ext": "vtt"
        }
    ]
}
```

## 테스트 실행

```bash
pytest tests/ -v
```

## Phase 1 체크리스트

- [x] YouTube URL/ID 파싱
- [x] yt-dlp를 통한 자막 목록 조회
- [x] 수동/자동 자막 다운로드
- [x] VTT 파일 파싱 및 JSON 변환
- [x] FastAPI REST API 구현
- [x] 기본 테스트 코드 작성
- [ ] Chrome Extension 연동 테스트

## 향후 계획 (Phase 2+)

- [ ] Faster-Whisper STT 통합
- [ ] LLM(Ollama) 번역 모듈
- [ ] 컨텍스트 기반 프롬프트 생성
- [ ] 번역 캐싱 시스템
