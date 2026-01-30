/**
 * CAYT - Popup Script
 * 설정 UI 및 상태 표시를 관리합니다.
 */

const elements = {
  statusDot: document.getElementById('statusDot'),
  statusText: document.getElementById('statusText'),
  errorMessage: document.getElementById('errorMessage'),
  serverStatus: document.getElementById('serverStatus'),
  modelName: document.getElementById('modelName'),
  showOriginal: document.getElementById('showOriginal'),
  subtitleSize: document.getElementById('subtitleSize'),
};

document.addEventListener('DOMContentLoaded', async () => {
  await loadSettings();
  await checkServerStatus();
  setupEventListeners();
});

async function loadSettings() {
  const settings = await chrome.storage.sync.get({
    showOriginal: false,
    subtitleSize: 'medium',
  });
  
  elements.showOriginal.checked = settings.showOriginal;
  elements.subtitleSize.value = settings.subtitleSize;
}

async function saveSettings() {
  const settings = {
    showOriginal: elements.showOriginal.checked,
    subtitleSize: elements.subtitleSize.value,
  };
  
  await chrome.storage.sync.set(settings);
  
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab && tab.url?.includes('youtube.com/watch')) {
    chrome.tabs.sendMessage(tab.id, { action: 'setOption', ...settings });
  }
}

async function checkServerStatus() {
  try {
    const response = await chrome.runtime.sendMessage({ action: 'checkHealth' });
    
    if (response.success) {
      elements.statusDot.classList.add('connected');
      elements.statusText.textContent = '서버 연결됨';
      elements.serverStatus.textContent = '정상';
      elements.modelName.textContent = response.model || '-';
      
      if (!response.ollama) {
        showError('Ollama가 실행 중이지 않습니다. 터미널에서 "ollama serve"를 실행해주세요.');
        elements.statusText.textContent = 'Ollama 미연결';
        elements.statusDot.classList.remove('connected');
      }
    } else {
      elements.statusDot.classList.remove('connected');
      elements.statusText.textContent = '서버 미연결';
      elements.serverStatus.textContent = '오프라인';
      elements.modelName.textContent = '-';
      showError(response.error || '백엔드 서버에 연결할 수 없습니다.');
    }
  } catch (error) {
    elements.statusDot.classList.remove('connected');
    elements.statusText.textContent = '오류 발생';
    elements.serverStatus.textContent = '오류';
    showError(error.message);
  }
}

function showError(message) {
  elements.errorMessage.textContent = message;
  elements.errorMessage.classList.remove('hidden');
}

function setupEventListeners() {
  elements.showOriginal.addEventListener('change', saveSettings);
  elements.subtitleSize.addEventListener('change', saveSettings);
}
