// main.js
// App bootstrap: initializes each module and wires up static DOM
// event listeners (dynamically-generated job-card buttons are wired
// inside jobs.js itself, since they're built from template strings).

import { dom } from './core.js';
import { initGoogleAuth } from './auth.js';
import { toggleSpeak, initVoiceInput } from './audio.js';
import { sendMessage, addMessage, clearChat, initChat } from './chat.js';
import { initJobs, closeJobModal, forceCloseJobModal, cancelApplyAll } from './jobs.js';
import { toggleMemory, closeMemory, uploadDoc, getBriefing } from './panels.js';

// Break the chat.js <-> jobs.js circular dependency: jobs.js needs
// sendMessage (for "Auto-apply" prompts) and addMessage (for the
// email-all result bubble). Inject them here instead of importing
// jobs.js -> chat.js directly.
initJobs({ sendMessage, addMessage });

initChat();
initVoiceInput(sendMessage);
window.addEventListener('load', initGoogleAuth);

// Header buttons
dom.speakBtn.addEventListener('click', toggleSpeak);
document.querySelector('[title="Daily Briefing"]').addEventListener('click', getBriefing);
document.querySelector('[title="Memory"]').addEventListener('click', toggleMemory);
document.querySelector('[title="Clear"]').addEventListener('click', clearChat);

// Upload
document.getElementById('file-upload').addEventListener('change', function () {
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