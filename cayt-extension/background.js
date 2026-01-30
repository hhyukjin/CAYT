/**
 * CAYT - Background Service Worker
 * 백엔드 API 통신 및 상태 관리를 담당합니다.
 */

const API_BASE_URL = 'http://localhost:8000';
const ENDPOINTS = {
  health: '/health',
  translate: '/api/v1/translate',
  cancel: '/api/v1/translate/cancel',
};

// 탭별 상태 저장
const tabStates = new Map();

// 진행 중인 요청 추적 (중복 방지)
const pendingRequests = new Map();

function initTabState(tabId) {
  const newState = {
    isActive: false,
    isLoading: false,
    subtitles: null,
    currentVideoId: null,
    currentTaskId: null,
    sourceType: null,
    error: null,
  };
  tabStates.set(tabId, newState);
  console.log(`[BG] Tab ${tabId} state initialized`);
  return newState;
}

function getTabState(tabId) {
  if (!tabStates.has(tabId)) {
    return initTabState(tabId);
  }
  return tabStates.get(tabId);
}

// ============================================
// API 통신
// ============================================

async function checkServerHealth() {
  try {
    const response = await fetch(`${API_BASE_URL}${ENDPOINTS.health}`);
    if (!response.ok) throw new Error('Server not healthy');
    const data = await response.json();
    return {
      success: true,
      ollama: data.ollama === 'connected',
      model: data.model,
      stt: data.stt === 'available',
    };
  } catch (error) {
    console.error('[BG] Health check failed:', error);
    return { success: false, error: '백엔드 서버에 연결할 수 없습니다.' };
  }
}

async function requestTranslation(videoUrl, sourceLang = 'en') {
  const url = new URL(`${API_BASE_URL}${ENDPOINTS.translate}`);
  url.searchParams.append('video_url', videoUrl);
  url.searchParams.append('source_lang', sourceLang);
  url.searchParams.append('use_context', 'true');

  console.log(`[BG] Translation request: ${url.toString()}`);

  const response = await fetch(url.toString());
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '번역 요청 실패');
  }
  
  return await response.json();
}

async function requestCancelByVideoId(videoId) {
  if (!videoId) {
    console.log('[BG] Cancel skipped: no videoId');
    return { success: false };
  }
  
  try {
    const url = new URL(`${API_BASE_URL}${ENDPOINTS.cancel}`);
    url.searchParams.append('video_id', videoId);
    
    console.log(`[BG] Cancel request for: ${videoId}`);
    const response = await fetch(url.toString(), { method: 'POST' });
    return await response.json();
  } catch (error) {
    console.error('[BG] Cancel request failed:', error);
    return { success: false, error: error.message };
  }
}

// ============================================
// 메시지 핸들러
// ============================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const tabId = sender.tab?.id || message.tabId;
  console.log(`[BG] Message: ${message.action} from tab ${tabId}`);
  handleMessage(message, tabId, sendResponse);
  return true;
});

async function handleMessage(message, tabId, sendResponse) {
  try {
    switch (message.action) {
      case 'checkHealth':
        sendResponse(await checkServerHealth());
        break;
        
      case 'translate':
        await handleTranslate(message, tabId, sendResponse);
        break;
        
      case 'cancelTranslation':
        await handleCancelTranslation(message, tabId, sendResponse);
        break;
        
      case 'getState':
        sendResponse(getTabState(tabId));
        break;
        
      case 'setState':
        Object.assign(getTabState(tabId), message.state);
        sendResponse({ success: true });
        break;
        
      default:
        sendResponse({ error: 'Unknown action' });
    }
  } catch (error) {
    console.error('[BG] Error:', error);
    sendResponse({ error: error.message });
  }
}

async function handleTranslate(message, tabId, sendResponse) {
  const state = getTabState(tabId);
  const videoId = extractVideoId(message.videoUrl);
  
  // 이미 같은 영상에 대한 요청이 진행 중인지 확인
  const requestKey = `${tabId}-${videoId}`;
  if (pendingRequests.has(requestKey)) {
    console.log(`[BG] ⚠️ 이미 요청 진행 중: ${requestKey}`);
    sendResponse({ success: false, error: '이미 번역 요청이 진행 중입니다.' });
    return;
  }
  
  // 다른 영상 번역 중이면 취소
  if (state.isLoading && state.currentVideoId && state.currentVideoId !== videoId) {
    console.log(`[BG] Cancelling previous translation: ${state.currentVideoId}`);
    await requestCancelByVideoId(state.currentVideoId);
  }
  
  // 요청 등록
  pendingRequests.set(requestKey, true);
  
  try {
    const health = await checkServerHealth();
    if (!health.success) throw new Error(health.error);
    if (!health.ollama) throw new Error('Ollama 서버가 실행 중이지 않습니다.');
    
    state.isLoading = true;
    state.currentVideoId = videoId;
    state.error = null;
    
    console.log(`[BG] 🚀 Starting translation for: ${videoId}`);
    
    // Content Script에 로딩 상태 전달
    try {
      await chrome.tabs.sendMessage(tabId, {
        action: 'updateState',
        state: { isLoading: true, videoId },
      });
    } catch (e) {}
    
    // 번역 요청
    const result = await requestTranslation(message.videoUrl, message.sourceLang);
    
    if (result.success) {
      state.subtitles = result.segments;
      state.currentTaskId = result.task_id;
      state.sourceType = result.source_type;
      state.isActive = true;
      state.isLoading = false;
      
      console.log(`[BG] ✅ Translation complete: ${result.total_segments} segments (${result.source_type}, cached: ${result.cached || false})`);
      
      sendResponse({
        success: true,
        data: {
          taskId: result.task_id,
          videoId: result.video_id,
          title: result.title,
          segments: result.segments,
          context: result.context,
          totalSegments: result.total_segments,
          sourceType: result.source_type,
          cached: result.cached || false,
        },
      });
    } else {
      state.isLoading = false;
      state.currentVideoId = null;
      sendResponse({
        success: false,
        cancelled: true,
        error: result.message || '번역이 취소되었습니다.',
      });
    }
  } catch (error) {
    state.isLoading = false;
    state.currentVideoId = null;
    state.error = error.message;
    console.error(`[BG] ❌ Translation error: ${error.message}`);
    sendResponse({ success: false, error: error.message });
  } finally {
    // 요청 완료, 등록 해제
    pendingRequests.delete(requestKey);
  }
}

async function handleCancelTranslation(message, tabId, sendResponse) {
  const state = getTabState(tabId);
  const videoId = message.videoId || state.currentVideoId;
  
  // 로딩 중이 아니면 취소할 필요 없음
  if (!state.isLoading) {
    console.log(`[BG] Cancel skipped: not loading (videoId: ${videoId})`);
    sendResponse({ success: true, message: 'Nothing to cancel' });
    return;
  }
  
  if (videoId) {
    console.log(`[BG] Cancelling translation for: ${videoId}`);
    
    // pending 요청 제거
    const requestKey = `${tabId}-${videoId}`;
    pendingRequests.delete(requestKey);
    
    const result = await requestCancelByVideoId(videoId);
    state.isLoading = false;
    state.currentVideoId = null;
    sendResponse(result);
  } else {
    sendResponse({ success: false, error: '취소할 작업이 없습니다.' });
  }
}

// ============================================
// 탭 이벤트 리스너
// ============================================

chrome.tabs.onRemoved.addListener((tabId) => {
  const state = tabStates.get(tabId);
  
  if (state?.isLoading && state?.currentVideoId) {
    requestCancelByVideoId(state.currentVideoId);
  }
  
  // 해당 탭의 pending 요청 정리
  for (const key of pendingRequests.keys()) {
    if (key.startsWith(`${tabId}-`)) {
      pendingRequests.delete(key);
    }
  }
  
  tabStates.delete(tabId);
  console.log(`[BG] Tab ${tabId} removed, state cleaned`);
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.url && changeInfo.url.includes('youtube.com')) {
    const state = tabStates.get(tabId);
    if (!state) return;
    
    const newVideoId = extractVideoId(changeInfo.url);
    
    // 다른 영상으로 이동했고 로딩 중이면 취소
    if (newVideoId !== state.currentVideoId && state.isLoading && state.currentVideoId) {
      console.log(`[BG] Tab URL changed while loading, cancelling: ${state.currentVideoId}`);
      requestCancelByVideoId(state.currentVideoId);
      
      // pending 요청 정리
      const requestKey = `${tabId}-${state.currentVideoId}`;
      pendingRequests.delete(requestKey);
      
      initTabState(tabId);
    }
  }
});

function extractVideoId(url) {
  try {
    return new URL(url).searchParams.get('v');
  } catch {
    return null;
  }
}

console.log('[BG] CAYT Service Worker initialized');
