# CAYT - Context-Aware YouTube Translator

> 🌐 **문맥 기반 유튜브 자막 번역기**

YouTube 영상의 자막을 전체 문맥을 분석하여 고품질 한국어로 번역하는 프로젝트입니다.

## 📋 프로젝트 구조

```
CAYT/
├── cayt-backend/      # Python FastAPI 백엔드 서버
└── cayt-extension/    # Chrome 확장 프로그램
```

## ✨ 주요 기능

### 문맥 기반 번역
- 영상 전체 텍스트를 분석하여 도메인(IT, 교육, 요리 등) 자동 감지
- 도메인별 용어 사전을 활용한 일관된 번역
- 문장 경계를 인식하여 자연스러운 번역 제공

### STT (Speech-to-Text)
- 자막이 없는 영상도 Faster-Whisper를 통해 음성 인식
- 수동 자막 우선, 없으면 자동 STT 처리

### 캐싱 시스템
- 번역 결과 메모리 캐싱
- 오디오 파일 캐싱으로 재요청 시 빠른 응답

## 🚀 빠른 시작

### 1. 사전 요구사항

- **Python** 3.11+
- **Ollama** (로컬 LLM)
- **Chrome** 브라우저

### 2. Ollama 설치 및 모델 다운로드

```bash
# Ollama 설치 (macOS)
brew install ollama

# 서버 실행
ollama serve

# 번역 모델 다운로드 (새 터미널)
ollama pull gemma3:4b
```

### 3. 백엔드 서버 실행

```bash
cd cayt-backend

# 가상환경 생성 및 활성화
uv venv --python 3.11
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 의존성 설치
uv pip install -r requirements.txt

# 환경 변수 설정
cp .env.example .env

# 서버 실행
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 4. Chrome Extension 설치

1. Chrome에서 `chrome://extensions` 열기
2. **개발자 모드** 활성화
3. **압축해제된 확장 프로그램을 로드합니다** 클릭
4. `cayt-extension` 폴더 선택

### 5. 사용

1. YouTube 영상 페이지로 이동
2. 플레이어 우측 하단의 **CAYT 버튼** 클릭
3. 번역 완료 후 자막 자동 표시

## 📁 상세 문서

- [Backend 문서](./cayt-backend/README.md)
- [Extension 문서](./cayt-extension/README.md)

## 🛠 기술 스택

| 구분 | 기술 |
|------|------|
| **Backend** | Python, FastAPI, yt-dlp |
| **STT** | Faster-Whisper |
| **LLM** | Ollama (Gemma, Llama 등) |
| **Extension** | JavaScript, Chrome Extension API |

## 📈 개발 로드맵

### Phase 1 ✅
- YouTube 자막 추출 (yt-dlp)
- 기본 번역 파이프라인
- Chrome Extension 기본 UI

### Phase 2 ✅
- Faster-Whisper STT 통합
- 문맥 기반 번역 시스템
- 도메인별 용어 사전
- 캐싱 시스템

### Phase 3 (예정)
- GPU 가속 최적화
- 화자 식별 (Diarization)
- 다국어 지원 확대

## 📄 라이선스

MIT License
