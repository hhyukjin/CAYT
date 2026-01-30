/**
 * CAYT - Content Script
 * YouTube 페이지에서 자막 오버레이를 관리합니다.
 * 광고 재생 시에도 번역 결과를 유지합니다.
 */

// ============================================
// 상태 관리
// ============================================

const state = {
  isActive: false,
  isLoading: false,
  isInitialized: false,
  subtitles: [],
  currentIndex: -1,
  currentTaskId: null,
  currentVideoId: null,
  showOriginal: false,
  subtitleSize: 'medium',
  isAdPlaying: false,
  cachedSubtitles: null,
  // 중복 요청 방지
  pendingRequest: null,
};

let videoElement = null;
let playerContainer = null;
let subtitleContainer = null;
let controlButton = null;
let loadingOverlay = null;
let adCheckInterval = null;
let urlCheckInterval = null;

// ============================================
// 초기화
// ============================================

function initialize() {
  if (!window.location.pathname.startsWith('/watch')) {
    console.log('[CAYT] Not a watch page, skipping init');
    return;
  }
  
  if (state.isInitialized) {
    console.log('[CAYT] Already initialized');
    return;
  }
  
  cleanupExistingElements();
  
  waitForElement('video').then((video) => {
    videoElement = video;
    playerContainer = document.querySelector('#movie_player');
    
    if (playerContainer) {
      createSubtitleContainer();
      createControlButton();
      createLoadingOverlay();
      setupVideoListeners();
      setupAdDetection();
      
      state.isInitialized = true;
      console.log('[CAYT] Initialized');
    }
  }).catch(err => {
    console.error('[CAYT] Init failed:', err);
  });
}

function cleanupExistingElements() {
  document.querySelectorAll('.cayt-control-container').forEach(el => el.remove());
  document.querySelectorAll('.cayt-subtitle-container').forEach(el => el.remove());
  document.querySelectorAll('.cayt-loading-overlay').forEach(el => el.remove());
  document.querySelectorAll('.cayt-error-message').forEach(el => el.remove());
}

function resetState() {
  console.log('[CAYT] Resetting state');
  state.isActive = false;
  state.isLoading = false;
  state.isInitialized = false;
  state.subtitles = [];
  state.currentIndex = -1;
  state.currentTaskId = null;
  state.currentVideoId = null;
  state.isAdPlaying = false;
  state.cachedSubtitles = null;
  state.pendingRequest = null;
  
  videoElement = null;
  playerContainer = null;
  subtitleContainer = null;
  controlButton = null;
  loadingOverlay = null;
  
  if (adCheckInterval) {
    clearInterval(adCheckInterval);
    adCheckInterval = null;
  }
}

function waitForElement(selector, timeout = 10000) {
  return new Promise((resolve, reject) => {
    const element = document.querySelector(selector);
    if (element) {
      resolve(element);
      return;
    }
    
    const observer = new MutationObserver((mutations, obs) => {
      const el = document.querySelector(selector);
      if (el) {
        obs.disconnect();
        resolve(el);
      }
    });
    
    observer.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => {
      observer.disconnect();
      reject(new Error(`Element ${selector} not found`));
    }, timeout);
  });
}

// ============================================
// 광고 감지 및 처리
// ============================================

function setupAdDetection() {
  if (adCheckInterval) clearInterval(adCheckInterval);
  adCheckInterval = setInterval(checkAdStatus, 1000);
}

function checkAdStatus() {
  if (!playerContainer) return;
  
  const adIndicators = [
    document.querySelector('.ad-showing'),
    document.querySelector('.ytp-ad-player-overlay'),
    document.querySelector('.ytp-ad-text'),
    playerContainer.classList.contains('ad-showing')
  ];
  
  const isAdNow = adIndicators.some(indicator => !!indicator);
  
  if (isAdNow && !state.isAdPlaying) {
    onAdStart();
  } else if (!isAdNow && state.isAdPlaying) {
    onAdEnd();
  }
}

function onAdStart() {
  console.log('[CAYT] 광고 시작 감지');
  state.isAdPlaying = true;
  
  if (state.isActive && state.subtitles.length > 0) {
    state.cachedSubtitles = {
      subtitles: [...state.subtitles],
      taskId: state.currentTaskId,
      videoId: state.currentVideoId
    };
    console.log('[CAYT] 자막 캐시 완료:', state.cachedSubtitles.subtitles.length, '개');
  }
  
  if (subtitleContainer) {
    subtitleContainer.classList.add('hidden');
  }
}

function onAdEnd() {
  console.log('[CAYT] 광고 종료 감지');
  state.isAdPlaying = false;
  
  const currentVideoId = new URL(window.location.href).searchParams.get('v');
  
  if (state.cachedSubtitles && currentVideoId === state.cachedSubtitles.videoId) {
    state.subtitles = state.cachedSubtitles.subtitles;
    state.currentTaskId = state.cachedSubtitles.taskId;
    state.currentVideoId = state.cachedSubtitles.videoId;
    state.isActive = true;
    
    console.log('[CAYT] 자막 복원 완료:', state.subtitles.length, '개');
    
    if (controlButton) controlButton.classList.add('active');
    if (subtitleContainer) subtitleContainer.classList.remove('hidden');
    
    updateSubtitle();
    state.cachedSubtitles = null;
  }
}

// ============================================
// UI 생성
// ============================================

function createSubtitleContainer() {
  if (document.querySelector('.cayt-subtitle-container')) {
    subtitleContainer = document.querySelector('.cayt-subtitle-container');
    return;
  }
  
  subtitleContainer = document.createElement('div');
  subtitleContainer.className = 'cayt-subtitle-container hidden';
  subtitleContainer.innerHTML = `<span class="cayt-subtitle-text size-${state.subtitleSize}"></span>`;
  playerContainer.appendChild(subtitleContainer);
}

function createControlButton() {
  document.querySelectorAll('.cayt-control-container').forEach(el => el.remove());
  
  const rightControls = document.querySelector('.ytp-right-controls');
  if (!rightControls) {
    console.error('[CAYT] Right controls not found');
    return;
  }
  
  const container = document.createElement('div');
  container.className = 'cayt-control-container';
  
  controlButton = document.createElement('button');
  controlButton.className = 'cayt-toggle-btn ytp-button';
  controlButton.title = 'CAYT 번역 자막';
  controlButton.innerHTML = `
    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" width="24" height="24">
      <path fill="currentColor" d="M12.87 15.07l-2.54-2.51.03-.03A17.52 17.52 0 0014.07 6H17V4h-7V2H8v2H1v2h11.17C11.5 7.92 10.44 9.75 9 11.35 8.07 10.32 7.3 9.19 6.69 8h-2c.73 1.63 1.73 3.17 2.98 4.56l-5.09 5.02L4 19l5-5 3.11 3.11.76-2.04M18.5 10h-2L12 22h2l1.12-3h4.75L21 22h2l-4.5-12m-2.62 7l1.62-4.33L19.12 17h-3.24z"/>
    </svg>
  `;
  
  controlButton.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    console.log('[CAYT] Button clicked!');
    handleToggleClick();
  });
  
  container.appendChild(controlButton);
  rightControls.insertBefore(container, rightControls.firstChild);
  
  console.log('[CAYT] Control button created');
}

function createLoadingOverlay() {
  if (document.querySelector('.cayt-loading-overlay')) {
    loadingOverlay = document.querySelector('.cayt-loading-overlay');
    return;
  }
  
  loadingOverlay = document.createElement('div');
  loadingOverlay.className = 'cayt-loading-overlay hidden';
  loadingOverlay.innerHTML = `
    <div class="cayt-loading-spinner"></div>
    <div class="cayt-loading-text">자막을 번역하고 있습니다...</div>
  `;
  playerContainer.appendChild(loadingOverlay);
}

// ============================================
// 이벤트 핸들러
// ============================================

async function handleToggleClick() {
  console.log('[CAYT] Toggle handler - loading:', state.isLoading, 'active:', state.isActive);
  
  if (state.isAdPlaying) {
    console.log('[CAYT] 광고 재생 중 - 대기');
    return;
  }
  
  // 이미 요청 진행 중이면 무시
  if (state.pendingRequest) {
    console.log('[CAYT] 이미 요청 진행 중 - 무시');
    return;
  }
  
  if (state.isLoading) {
    await cancelTranslation();
    return;
  }
  
  if (state.isActive) {
    deactivateSubtitles();
  } else {
    await activateSubtitles();
  }
}

async function cancelTranslation() {
  console.log('[CAYT] Cancelling, videoId:', state.currentVideoId);
  
  if (!state.currentVideoId) {
    setLoading(false);
    return;
  }
  
  try {
    await chrome.runtime.sendMessage({
      action: 'cancelTranslation',
      videoId: state.currentVideoId
    });
  } catch (error) {
    console.error('[CAYT] Cancel error:', error);
  }
  
  state.pendingRequest = null;
  setLoading(false);
}

async function activateSubtitles() {
  const videoUrl = window.location.href;
  const videoId = new URL(videoUrl).searchParams.get('v');
  
  // 중복 요청 방지
  if (state.pendingRequest === videoId) {
    console.log('[CAYT] 이미 이 영상 요청 중:', videoId);
    return;
  }
  
  console.log('[CAYT] Activating for video:', videoId);
  
  state.currentVideoId = videoId;
  state.pendingRequest = videoId;
  
  try {
    setLoading(true);
    
    const response = await chrome.runtime.sendMessage({
      action: 'translate',
      videoUrl,
      sourceLang: 'en',
    });
    
    // 응답이 왔을 때 여전히 같은 영상인지 확인
    if (state.pendingRequest !== videoId) {
      console.log('[CAYT] 영상이 변경됨, 응답 무시');
      return;
    }
    
    console.log('[CAYT] Response received:', response.success);
    
    if (response.success) {
      state.subtitles = response.data.segments;
      state.currentTaskId = response.data.taskId;
      state.isActive = true;
      
      if (controlButton) controlButton.classList.add('active');
      if (subtitleContainer) subtitleContainer.classList.remove('hidden');
      
      updateSubtitle();
      console.log(`[CAYT] Loaded ${response.data.totalSegments} subtitles (source: ${response.data.sourceType}, cached: ${response.data.cached || false})`);
    } else if (response.cancelled) {
      console.log('[CAYT] Translation cancelled');
      state.currentVideoId = null;
    } else {
      showError(response.error || '번역 실패');
      state.currentVideoId = null;
    }
  } catch (error) {
    console.error('[CAYT] Error:', error);
    showError(error.message);
    state.currentVideoId = null;
  } finally {
    state.pendingRequest = null;
    setLoading(false);
  }
}

function deactivateSubtitles() {
  console.log('[CAYT] Deactivating');
  
  state.isActive = false;
  state.subtitles = [];
  state.currentIndex = -1;
  state.currentTaskId = null;
  state.currentVideoId = null;
  state.cachedSubtitles = null;
  state.pendingRequest = null;
  
  if (controlButton) controlButton.classList.remove('active');
  if (subtitleContainer) subtitleContainer.classList.add('hidden');
}

function setLoading(isLoading) {
  state.isLoading = isLoading;
  
  if (isLoading) {
    if (controlButton) controlButton.classList.add('loading');
    if (loadingOverlay) loadingOverlay.classList.remove('hidden');
  } else {
    if (controlButton) controlButton.classList.remove('loading');
    if (loadingOverlay) loadingOverlay.classList.add('hidden');
  }
}

function showError(message) {
  console.error('[CAYT] Error:', message);
  
  if (!playerContainer) return;
  
  document.querySelectorAll('.cayt-error-message').forEach(el => el.remove());
  
  const errorDiv = document.createElement('div');
  errorDiv.className = 'cayt-error-message';
  errorDiv.textContent = message;
  playerContainer.appendChild(errorDiv);
  
  setTimeout(() => errorDiv.remove(), 5000);
}

// ============================================
// 비디오 동기화
// ============================================

function setupVideoListeners() {
  if (!videoElement) return;
  
  videoElement.removeEventListener('timeupdate', handleTimeUpdate);
  videoElement.removeEventListener('seeked', handleTimeUpdate);
  
  videoElement.addEventListener('timeupdate', handleTimeUpdate);
  videoElement.addEventListener('seeked', handleTimeUpdate);
}

function handleTimeUpdate() {
  if (state.isAdPlaying || !state.isActive || state.subtitles.length === 0) return;
  updateSubtitle();
}

function updateSubtitle() {
  if (!videoElement || !subtitleContainer) return;
  if (state.subtitles.length === 0) return;
  
  const currentTime = videoElement.currentTime;
  const subtitleIndex = state.subtitles.findIndex(
    sub => currentTime >= sub.start && currentTime < sub.end
  );
  
  if (subtitleIndex !== state.currentIndex) {
    state.currentIndex = subtitleIndex;
    
    const textElement = subtitleContainer.querySelector('.cayt-subtitle-text');
    if (!textElement) return;
    
    if (subtitleIndex >= 0) {
      const subtitle = state.subtitles[subtitleIndex];
      let content = subtitle.translated;
      
      if (state.showOriginal) {
        content += `<span class="cayt-subtitle-original">${subtitle.original}</span>`;
      }
      
      textElement.innerHTML = content;
      subtitleContainer.classList.remove('hidden');
    } else {
      textElement.textContent = '';
      subtitleContainer.classList.add('hidden');
    }
  }
}

// ============================================
// 메시지 수신
// ============================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('[CAYT] Message:', message.action);
  
  switch (message.action) {
    case 'updateState':
      if (message.state?.isLoading !== undefined) {
        setLoading(message.state.isLoading);
      }
      sendResponse({ success: true });
      break;
      
    case 'setOption':
      if (message.showOriginal !== undefined) {
        state.showOriginal = message.showOriginal;
      }
      if (message.subtitleSize !== undefined) {
        state.subtitleSize = message.subtitleSize;
        const textEl = subtitleContainer?.querySelector('.cayt-subtitle-text');
        if (textEl) textEl.className = `cayt-subtitle-text size-${state.subtitleSize}`;
      }
      sendResponse({ success: true });
      break;
      
    default:
      sendResponse({ error: 'Unknown action' });
  }
  return true;
});

// ============================================
// URL 변경 감지 (단일 방식으로 통합)
// ============================================

let lastVideoId = null;

function getCurrentVideoId() {
  if (!window.location.pathname.startsWith('/watch')) return null;
  return new URL(window.location.href).searchParams.get('v');
}

async function handleVideoChange() {
  const currentVideoId = getCurrentVideoId();
  
  // 같은 영상이면 무시
  if (currentVideoId === lastVideoId) return;
  
  console.log(`[CAYT] Video changed: ${lastVideoId || 'none'} -> ${currentVideoId || 'none'}`);
  
  const oldVideoId = lastVideoId;
  lastVideoId = currentVideoId;
  
  // 영상 페이지가 아니면 정리
  if (!currentVideoId) {
    if (state.isInitialized) {
      if (state.isLoading && state.currentVideoId) {
        try {
          await chrome.runtime.sendMessage({
            action: 'cancelTranslation',
            videoId: state.currentVideoId
          });
        } catch (e) {}
      }
      resetState();
      cleanupExistingElements();
    }
    return;
  }
  
  // 이전 영상 번역 중이면 취소
  if (state.isLoading && oldVideoId) {
    console.log('[CAYT] Cancelling translation for:', oldVideoId);
    try {
      await chrome.runtime.sendMessage({
        action: 'cancelTranslation',
        videoId: oldVideoId
      });
    } catch (e) {}
  }
  
  // 자막 비활성화
  if (state.isActive) {
    deactivateSubtitles();
  }
  
  resetState();
  cleanupExistingElements();
  
  // 새 영상 초기화
  setTimeout(initialize, 500);
}

// YouTube SPA 네비게이션 감지
document.addEventListener('yt-navigate-finish', () => {
  console.log('[CAYT] yt-navigate-finish event');
  handleVideoChange();
});

// 초기 로드 시 videoId 설정
lastVideoId = getCurrentVideoId();

// ============================================
// 실행
// ============================================

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initialize);
} else {
  initialize();
}

console.log('[CAYT] Content script loaded');
