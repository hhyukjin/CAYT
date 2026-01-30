# CAYT Chrome Extension

**Context-Aware YouTube Translator** - Chrome 확장 프로그램

YouTube 영상에서 문맥 기반 한국어 자막을 제공하는 Chrome 확장 프로그램입니다.

## ✨ 기능

- ✅ YouTube 영상 자막 자동 번역
- ✅ 문맥 기반 고품질 번역
- ✅ 자막 없는 영상도 STT로 지원
- ✅ 원문 함께 표시 옵션
- ✅ 자막 크기 조절
- ✅ 광고 재생 시 자막 유지
- ✅ 영상 재생 시간 동기화

## 🗂 파일 구조

```
cayt-extension/
├── manifest.json      # Extension 설정 (Manifest V3)
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

## 🚀 설치 방법

### 1. 아이콘 준비 (선택)

`icons` 폴더에 아이콘 파일이 없다면:
1. `icon-generator.html` 파일을 브라우저에서 열기
2. 각 크기별로 이미지 저장
3. `icons` 폴더에 저장

### 2. Chrome에 확장 프로그램 로드

1. Chrome 브라우저에서 `chrome://extensions` 열기
2. 우측 상단 **개발자 모드** 활성화
3. **압축해제된 확장 프로그램을 로드합니다** 클릭
4. `cayt-extension` 폴더 선택

### 3. 백엔드 서버 실행

```bash
# 터미널 1: Ollama 서버
ollama serve

# 터미널 2: 백엔드 서버
cd cayt-backend
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 📖 사용 방법

1. YouTube 영상 페이지로 이동
2. 플레이어 우측 하단의 **CAYT 버튼** (🌐) 클릭
3. 로딩 중에는 버튼에 스피너 표시
4. 번역이 완료되면 자막이 자동으로 표시됨
5. 다시 클릭하면 자막 숨김

### 설정 변경

Extension 아이콘 클릭 → 팝업에서:
- **원문 표시**: 번역문 아래 원문 함께 표시
- **자막 크기**: 작게 / 보통 / 크게

## 🔧 기술 상세

### Content Script (`content.js`)
- YouTube 플레이어에 자막 오버레이 생성
- 영상 재생 시간에 맞춰 자막 동기화
- 광고 감지 및 자막 캐시/복원
- 중복 요청 방지

### Background Worker (`background.js`)
- 백엔드 API 통신
- 탭별 상태 관리
- 요청 중복 방지 (pendingRequests)

### Popup (`popup.html/js`)
- 서버 상태 확인
- 사용자 설정 관리

## ❗ 문제 해결

### "서버 미연결" 오류
```bash
# 백엔드 서버 실행 확인
curl http://localhost:8000/health
```

### "Ollama 미연결" 오류
```bash
# Ollama 서버 실행
ollama serve
```

### 자막이 표시되지 않음
1. YouTube 페이지 새로고침
2. Extension 새로고침 (`chrome://extensions` → 새로고침 버튼)
3. 백엔드 서버 로그 확인

### 번역 버튼이 안 보임
1. YouTube 플레이어가 완전히 로드될 때까지 대기
2. 페이지 새로고침

### 번역이 느림
- 첫 번역은 모델 로딩으로 시간이 걸림
- 이후 요청은 캐시로 빠르게 응답
- STT 사용 시 추가 시간 소요

## 📄 라이선스

MIT License
