# CAYT Chrome Extension

**Context-Aware YouTube Translator** - Chrome Extension

YouTube 영상에서 맥락 기반 한국어 자막을 제공하는 Chrome 확장 프로그램입니다.

## 설치 방법

### 1. 아이콘 준비

`icons` 폴더에 다음 파일들이 필요합니다:
- `icon16.png` (16x16)
- `icon48.png` (48x48)
- `icon128.png` (128x128)

간단한 아이콘 생성 방법:
1. `icon-generator.html` 파일을 브라우저에서 열기
2. 각 크기별로 이미지 저장
3. `icons` 폴더에 저장

### 2. Chrome에 확장 프로그램 로드

1. Chrome 브라우저에서 `chrome://extensions` 열기
2. 우측 상단 "개발자 모드" 활성화
3. "압축해제된 확장 프로그램을 로드합니다" 클릭
4. `cayt-extension` 폴더 선택

### 3. 백엔드 서버 실행

```bash
# 터미널 1: Ollama 서버
ollama serve

# 터미널 2: 백엔드 서버
cd cayt-backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

## 사용 방법

1. YouTube 영상 페이지로 이동
2. 플레이어 우측 하단의 번역 아이콘(🌐) 클릭
3. 번역이 완료되면 자막이 자동으로 표시됨

## 기능

- ✅ YouTube 영상 자막 자동 번역
- ✅ 맥락 기반 고품질 번역
- ✅ 원문 함께 표시 옵션
- ✅ 자막 크기 조절
- ✅ 영상 재생 시간 동기화

## 파일 구조

```
cayt-extension/
├── manifest.json      # Extension 설정
├── background.js      # Service Worker (API 통신)
├── content.js         # YouTube 페이지 스크립트
├── popup.html         # 설정 팝업 UI
├── popup.js           # 팝업 스크립트
├── styles.css         # 자막 오버레이 스타일
└── icons/
    ├── icon16.png
    ├── icon48.png
    └── icon128.png
```

## 문제 해결

### "서버 미연결" 오류
- 백엔드 서버가 실행 중인지 확인: `http://localhost:8000/health`

### "Ollama 미연결" 오류
- Ollama 서버 실행: `ollama serve`

### 자막이 표시되지 않음
- YouTube 페이지 새로고침 후 재시도
- 영상에 영어 자막이 있는지 확인
