// core.js
// Shared DOM references, status indicator, and generic utilities.

export const dom = {
  messagesEl: document.getElementById('messages'),
  inputEl: document.getElementById('input'),
  sendBtn: document.getElementById('send'),
  micBtn: document.getElementById('mic'),
  voiceBanner: document.getElementById('voice-banner'),
  statusDot: document.getElementById('status-dot'),
  statusText: document.getElementById('status-text'),
  speakBtn: document.getElementById('speak-btn'),
};

export function setStatus(state) {
  if (state === 'thinking') {
    dom.statusDot.className = 'status-dot thinking';
    dom.statusText.textContent = 'thinking...';
  } else {
    dom.statusDot.className = 'status-dot';
    dom.statusText.textContent = 'online';
  }
}

export function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value == null ? '' : String(value);
  return div.innerHTML;
}