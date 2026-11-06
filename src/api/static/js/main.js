// main.js
import { dom } from './core.js';
import { initGoogleAuth } from './auth.js';
import { toggleSpeak, initVoiceInput } from './audio.js';
import { sendMessage, addMessage, clearChat, initChat } from './chat.js';
import { initJobs, closeJobModal, forceCloseJobModal, cancelApplyAll } from './jobs.js';
import { toggleMemory, closeMemory, uploadDoc, getBriefing } from './panels.js';
import { initLandingTimer, applyLandingGreeting, dismissHero } from './landing.js';
import { toggleLeadsPanel, closeLeadsPanel, closeLeadModal } from './leads.js';

initJobs({ sendMessage, addMessage });
initChat();
initVoiceInput(sendMessage);
initLandingTimer();

// Check the existing DOOM session before offering Google sign-in.

async function refreshIdentity() {
  try {
    const res = await fetch('/auth/whoami', {
      credentials: 'same-origin',
      cache: 'no-store'
    });

    if (!res.ok) throw new Error(`Identity request failed: ${res.status}`);

    const identity = await res.json();
    applyLandingGreeting(identity);

    const leadsButton = document.getElementById('leads-toggle-btn');
    const loginContainer = document.getElementById('google-login-container');

    if (leadsButton) leadsButton.style.display = identity.is_owner ? 'flex' : 'none';
    if (loginContainer) loginContainer.style.display = identity.is_owner ? 'none' : 'block';

    console.log('DOOM identity:', identity.is_owner ? 'Owner' : 'Guest');

    if (!identity.is_owner) initGoogleAuth(refreshIdentity);

    return identity;
  } catch (error) {
    console.error('Identity check failed:', error);
    return null;
  }
}

refreshIdentity();
// Dismiss the landing hero the moment the visitor engages with anything.
dom.inputEl.addEventListener('input', dismissHero, { once: true });
dom.sendBtn.addEventListener('click', dismissHero, { once: true });
dom.micBtn.addEventListener('click', dismissHero, { once: true });

// Audio toggle
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

// Leads sidebar (owner only — button stays hidden otherwise)
document.getElementById('leads-toggle-btn').addEventListener('click', toggleLeadsPanel);
document.getElementById('leads-panel').addEventListener('click', closeLeadsPanel);
document.getElementById('leads-close-btn').addEventListener('click', () => {
  document.getElementById('leads-panel').classList.remove('open');
});
document.getElementById('lead-modal').addEventListener('click', closeLeadModal);
document.getElementById('lead-modal-close-btn').addEventListener('click', () => closeLeadModal());

// Service worker
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js')
    .then(() => console.log('DOOM PWA ready'))
    .catch(e => console.log('SW:', e));
}