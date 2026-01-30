# CAYT Backend

**Context-Aware YouTube Translator** - 백엔드 서버

YouTube 영상의 자막을 추출하고 문맥 기반으로 번역하는 FastAPI 서버입니다.

## 📋 요구 사항

- **Python**: 3.11+
- **Ollama**: 로컬 LLM 서버
- **패키지 매니저**: [uv](https://github.com/astral-sh/uv) (권장) 또는 pip

## 🗂 프로젝트 구조

```
cayt-backend/
├── app/
│   ├── main.py                    # FastAPI 애플리케이션
│   ├── models/
│   │   └── subtitle.py            # Pydantic 데이터 모델
│   ├── modules/
│   │   ├── cache.py               # 번역 결과 캐싱
│   │   ├── context_manager.py     # 도메인/용어 분석
│   │   ├── stt.py                 # Faster-Whisper STT
│   │   ├── subtitle_extractor.py  # 자막 추출
│   │   └── translator.py          # 문맥 기반 번역
│   └── utils/
│       └── parsers.py             # URL/VTT 파싱
├── config/
│   └── settings.py                # 환경 설정
├── .env.example                   # 환경 변수 예시
├── requirements.txt               # 의존성
└── README.md
```

## 🚀 설치 및 실행

### 1. 가상환경 생성

```bash
cd cayt-backend

# uv 사용 (권장)
uv venv --python 3.11
source .venv/bin/activate

# 또는 venv 사용
python -m venv .venv
source .venv/bin/activate
```

### 2. 의존성 설치

```bash
uv pip install -r requirements.txt
# 또는
pip install -r requirements.txt
```

### 3. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일 주요 설정:
```env
# LLM 설정
OLLAMA_HOST=http://localhost:11434
LLM_MODEL=gemma3:4b

# STT 설정
ENABLE_STT_FALLBACK=true
STT_MODEL_SIZE=large-v3-turbo
```

### 4. Ollama 실행

```bash
# 터미널 1: Ollama 서버
ollama serve

# 터미널 2: 모델 다운로드
ollama pull gemma3:4b
```

### 5. 서버 실행

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 6. API 문서 확인

- **Swagger UI**: http://127.0.0.1:8000/docs
- **ReDoc**: http://127.0.0.1:8000/redoc

## 📡 API 엔드포인트

### Health Check

```bash
GET /health
```

### 자막 관련

```bash
# 사용 가능한 자막 목록
GET /api/v1/subtitles/list?video_url={VIDEO_URL}

# 자막 추출
GET /api/v1/subtitles/extract?video_url={VIDEO_URL}&language=en
```

### 번역

```bash
# 자막 번역
GET /api/v1/translate?video_url={VIDEO_URL}&source_lang=en

# 번역 취소
POST /api/v1/translate/cancel?video_id={VIDEO_ID}
```

### 캐시 관리

```bash
# 캐시 통계
GET /api/v1/cache/stats

# 특정 영상 캐시 삭제
DELETE /api/v1/cache/{video_id}

# 전체 캐시 삭제
DELETE /api/v1/cache
```

## 🔧 주요 모듈

### SubtitleExtractor
- yt-dlp를 사용한 YouTube 자막 추출
- 수동 자막 우선, 없으면 STT 사용

### SpeechToText (STT)
- Faster-Whisper 기반 음성 인식
- 자막 없는 영상 지원
- 오디오 파일 캐싱

### Translator
- 문맥 기반 번역 시스템
- 문장 경계 인식 및 병합
- 도메인별 용어 사전 적용

### ContextManager
- 도메인 자동 감지 (IT, 교육, 요리 등)
- 핵심 용어 추출 및 번역 사전 생성

### TranslationCache
- 번역 결과 메모리 캐싱
- TTL 기반 만료 관리
- 중복 요청 방지

## 📊 번역 흐름

```
1. 자막 추출
   └─ 수동 자막 있음 → 다운로드
   └─ 수동 자막 없음 → STT 음성 인식

2. 문맥 분석
   └─ 도메인 감지 (IT, 교육 등)
   └─ 용어 사전 생성

3. 문장 병합
   └─ 세그먼트를 문장 경계로 병합
   └─ 타임코드 유지

4. 번역
   └─ 문맥 정보 + 용어 사전 포함 프롬프트
   └─ 청크 단위 (30문장씩) 번역

5. 타임코드 매핑
   └─ 번역 결과를 원본 타임코드에 매핑
```

## 🧪 테스트

```bash
# API 테스트
curl http://localhost:8000/health

# 번역 테스트
curl "http://localhost:8000/api/v1/translate?video_url=https://www.youtube.com/watch?v=VIDEO_ID"
```

## ⚠️ 알려진 이슈

- 일부 YouTube 영상에서 오디오 다운로드 실패 가능 (YouTube 정책 변경)
- STT는 CPU에서 실행 시 시간이 오래 걸릴 수 있음

## 📄 라이선스

MIT License
