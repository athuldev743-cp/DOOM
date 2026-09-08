// panels.js
// Memory drawer, document upload, and daily briefing.

import { addMessage } from './chat.js';
import { speak } from './audio.js';

let memoryOpen = false;

export async function toggleMemory() {
  memoryOpen = !memoryOpen;
  const panel = document.getElementById('memory-panel');
  panel.classList.toggle('open', memoryOpen);
  if (memoryOpen) {
    const res = await fetch('/memory');
    const data = await res.json();
    const content = document.getElementById('memory-content');
    let html = '<div class="section-label">PROFILE</div>';
    for (const [k, v] of Object.entries(data.profile)) {
      html += `<div class="memory-item">
        <div class="memory-key">${k}</div>
        <div class="memory-val">${v}</div>
      </div>`;
    }
    html += '<div class="section-label">CONTACTS</div>';
    html += `<div class="memory-item"><div class="memory-val" style="white-space:pre-wrap">${data.contacts}</div></div>`;
    content.innerHTML = html;
  }
}

export function closeMemory(e) {
  if (e.target === document.getElementById('memory-panel')) {
    memoryOpen = false;
    document.getElementById('memory-panel').classList.remove('open');
  }
}

export async function uploadDoc(input) {
  const file = input.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  const thinking = addMessage('doom', `<div class="thinking-dots"><span></span><span></span><span></span></div> Indexing ${file.name}...`);
  const res = await fetch('/upload', { method: 'POST', body: formData });
  const data = await res.json();
  thinking.innerHTML = `${data.result} — ask me anything about it.`;
}

export async function getBriefing() {
  const btn = document.querySelector('[title="Daily Briefing"]');
  if (btn) { btn.textContent = '⏳'; btn.style.pointerEvents = 'none'; }

  const thinking = addMessage('doom', '<div class="thinking-dots"><span></span><span></span><span></span></div>');

  try {
    const res = await fetch('/briefing');
    const data = await res.json();
    const formatted = data.briefing
      .replace(/\n\n/g, '<br/><br/>')
      .replace(/\n/g, '<br/>');
    thinking.innerHTML = formatted;
    speak(data.briefing);
  } catch (e) {
    thinking.innerHTML = 'Briefing error. Try again.';
  }

  if (btn) { btn.textContent = '☀️'; btn.style.pointerEvents = 'auto'; }
}