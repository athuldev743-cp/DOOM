// main.js
import { dom } from './core.js';
import { initGoogleAuth } from './auth.js';
import { toggleSpeak, initVoiceInput } from './audio.js';
import { sendMessage, addMessage, clearChat, initChat } from './chat.js';
import { initJobs, closeJobModal, forceCloseJobModal, cancelApplyAll } from './jobs.js';
import { toggleMemory, closeMemory, uploadDoc, getBriefing } from './panels.js';
import { initLanding, dismissHero } from './landing.js';

initJobs({ sendMessage, addMessage });
initChat();
initVoiceInput(sendMessage);
initLanding();
window.addEventListener('load', initGoogleAuth);

// Dismiss the landing hero the moment the visitor engages with anything.
dom.inputEl.addEventListener('input', dismissHero, { once: true });
dom.sendBtn.addEventListener('click', dismissHero, { once: true });
dom.micBtn.addEventListener('click', dismissHero, { once: true });

// Audio toggle (now living on the right of the composer)
dom.speakBtn.addEventListener('click', toggleSpeak);

// "+" popover menu
const plusBtn = document.getElementById('plus-btn');
const plusMenu = document.getElementById('plus-menu');

plusBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  plusMenu.classList.toggle('open');
  plusBtn.classList.toggle('open');
});

document.addEventListener('click', (e) => {
  if (!plusMenu.contains(e.target) && e.target !== plusBtn) {
    plusMenu.classList.remove('open');
    plusBtn.classList.remove('open');
  }
});

function closePlusMenu() {
  plusMenu.classList.remove('open');
  plusBtn.classList.remove('open');
}

document.getElementById('menu-briefing-btn').addEventListener('click', () => {
  closePlusMenu();
  getBriefing();
});
document.getElementById('menu-memory-btn').addEventListener('click', () => {
  closePlusMenu();
  toggleMemory();
});
document.getElementById('menu-clear-btn').addEventListener('click', () => {
  closePlusMenu();
  clearChat();
});
document.getElementById('file-upload').addEventListener('change', function () {
  closePlusMenu();
  uploadDoc(this);
});

// Panels / modals (backdrop click to close)
document.getElementById('memory-panel').addEventListener('click', closeMemory);
document.getElementById('job-modal').addEventListener('click', closeJobModal);
document.getElementById('job-modal-close-btn').addEventListener('click', forceCloseJobModal);
document.getElementById('apply-progress-close-btn').addEventListener('click', cancelApplyAll);

// Service worker
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js')
    .then(() => console.log('DOOM PWA ready'))
    .catch(e => console.log('SW:', e));
}