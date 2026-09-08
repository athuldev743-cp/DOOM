const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('send');
const micBtn = document.getElementById('mic');
const voiceBanner = document.getElementById('voice-banner');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const speakBtn = document.getElementById('speak-btn');


window.onload = function () {
  google.accounts.id.initialize({
    client_id: "1069358536248-fs6uak4fv0uof46l4usuir0tlmae2u9m.apps.googleusercontent.com",
    callback: handleGoogleSignIn,
    auto_select: true,
    itp_support: true
  });
  google.accounts.id.prompt();
};

async function handleGoogleSignIn(response) {
  await fetch('/auth/google', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential: response.credential })
  });
  // No UI change needed here — the cookie is now set, and future
  // /chat-stream requests will automatically be treated as owner.
}


window._speakOutput = true;
speakBtn.classList.add('active');
speakBtn.textContent = '🔊';

let audioQueue = [];
let isPlaying = false;
let currentAudio = null;



function toggleSpeak() {
  window._speakOutput = !window._speakOutput;
  speakBtn.classList.toggle('active', window._speakOutput);
  speakBtn.textContent = window._speakOutput ? '🔊' : '🔇';
  if (!window._speakOutput) {
    audioQueue = [];
    isPlaying = false;
    if (currentAudio) { currentAudio.pause(); currentAudio = null; }
  }
}

function processQueue() {
  if (!window._speakOutput || audioQueue.length === 0) {
    isPlaying = false;
    currentAudio = null;
    return;
  }
  isPlaying = true;
  const audio = audioQueue.shift();
  currentAudio = audio;
  audio.onended = () => { currentAudio = null; processQueue(); };
  audio.onerror = () => { currentAudio = null; processQueue(); };
  audio.play().catch(() => processQueue());
}

function speak(text) {
  if (!window._speakOutput || !text || !text.trim()) return;

  const sentences = text.match(/[^.!?]+[.!?]+/g) || [text];

  sentences.forEach((sentence, i) => {
    const clean = sentence.trim();
    if (!clean) return;
    fetch('/speak', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: clean })
    })
    .then(r => r.blob())
    .then(blob => {
      const audio = new Audio(URL.createObjectURL(blob));
      audioQueue.push(audio);
      if (!isPlaying) processQueue();
    })
    .catch(e => console.log('TTS:', e));
  });
}

function setStatus(state) {
  if (state === 'thinking') {
    statusDot.className = 'status-dot thinking';
    statusText.textContent = 'thinking...';
  } else {
    statusDot.className = 'status-dot';
    statusText.textContent = 'online';
  }
}

function addMessage(role, html) {
  const row = document.createElement('div');
  row.className = `msg-row ${role}`;
  const avatar = document.createElement('div');
  avatar.className = `avatar ${role}`;
  avatar.textContent = role === 'doom' ? 'D' : 'A';
  const bubble = document.createElement('div');
  bubble.className = `bubble ${role}`;
  bubble.innerHTML = html;
  row.appendChild(avatar);
  row.appendChild(bubble);
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return bubble;
}

function handleSpecialResponse(response) {
  if (response.includes('JOBS_DATA:')) {
    try {
      const rawJson = response.replace('JOBS_DATA:', '').trim();
      const jobs = JSON.parse(rawJson);
      return renderJobCards(jobs);
    } catch (e) {
      console.error('Failed to parse jobs payload', e);
    }
  }

  if (response.includes('APPLY_REPORT:')) {
    return response.replace('APPLY_REPORT:', '').replace(/\n/g, '<br/>');
  }

  if (response.includes('CALL:')) {
    const match = response.match(/CALL:(\+?\d+):(.+)/);
    if (match) {
      if (confirm(`📞 Call ${match[2]}?`)) {
        window.location.href = `tel:${match[1]}`;
      }
      return `📞 Calling ${match[2]}...`;
    }
  }

  if (response.includes('WHATSAPP:')) {
    const match = response.match(/WHATSAPP:(\d+):([\s\S]*)/);
    if (match) {
      const number = match[1];
      const message = match[2] || '';
      const waApp = `whatsapp://send?phone=${number}&text=${encodeURIComponent(message)}`;
      const waWeb = `https://wa.me/${number}?text=${encodeURIComponent(message)}`;

      const link = document.createElement('a');
      link.href = waApp;
      link.style.display = 'none';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      setTimeout(() => {
        window.open(waWeb, '_blank');
      }, 1500);

      return `💬 Opening WhatsApp...`;
    }
  }

  if (response.includes('WA_NOT_FOUND:')) {
    const match = response.match(/WA_NOT_FOUND:(.+)/);
    const name = match ? match[1] : 'contact';
    return `❌ Contact "${name}" not found. Try: "add contact ${name} +91XXXXXXXXXX"`;
  }

  if (response.includes('CALL_NOT_FOUND:')) {
    const match = response.match(/CALL_NOT_FOUND:(.+)/);
    const name = match ? match[1] : 'contact';
    return `❌ Contact "${name}" not found. Try: "add contact ${name} +91XXXXXXXXXX"`;
  }

  if (response.includes('LINKEDIN_AUTH_REQUIRED')) {
    window.open('/linkedin/auth', '_blank');
    return '🔗 Opening LinkedIn login... Come back after connecting!';
  }

  return response;
}


// Multi-command batch handling.
// A multi-line message is treated as ONE user submission. Each line is
// processed independently, but the UI waits until ALL results are ready
// and then renders one modern grouped answer.
async function sendMessage(text) {
  text = text || inputEl.value;
  if (!text || !text.trim()) return;

  inputEl.value = '';
  inputEl.style.height = '28px';
  inputEl.scrollTop = 0;

  const commands = text
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean);

  if (!commands.length) return;

  // Normal single-command behavior stays unchanged.
  if (commands.length === 1) {
    await sendSingleMessage(commands[0]);
    return;
  }

  await sendBatchAsOneAnswer(commands);
}

async function sendBatchAsOneAnswer(commands) {
  audioQueue = [];
  isPlaying = false;
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }

  sendBtn.disabled = true;
  setStatus('thinking');

  // Show the complete user submission as one message, like modern LLMs.
  addMessage('user', commands.map(escapeHtml).join('<br>'));

  const resultBubble = addMessage(
    'doom',
    '<div class="thinking-dots"><span></span><span></span><span></span></div>'
  );

  try {
    const results = [];

    // Process through the SAME /chat-stream endpoint and response format
    // used by the existing single-message function. We intentionally wait
    // for each request here because the backend may use shared session/tool
    // state. The user sees nothing until all requested companies finish.
    for (const command of commands) {
      const result = await collectChatResult(command);
      results.push({ command, result });
    }

    resultBubble.innerHTML = renderBatchResults(results);

  } catch (e) {
    console.error('Batch processing error:', e);
    resultBubble.innerHTML =
      '❌ Could not complete the batch request.<br>' +
      '<span style="color:var(--text-dim)">Please try again.</span>';
  }

  sendBtn.disabled = false;
  setStatus('online');
  inputEl.focus();
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function collectChatResult(text) {
  const res = await fetch('/chat-stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: text })
  });

  if (!res.ok || !res.body) {
    throw new Error(`HTTP ${res.status || 'stream unavailable'}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalResponse = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';

    for (const evt of events) {
      const line = evt.trim();
      if (!line.startsWith('data: ')) continue;

      try {
        const data = JSON.parse(line.slice(6));

        if (data.type === 'text') {
          finalResponse = data.content || finalResponse;
        }

        if (data.type === 'audio' && window._speakOutput) {
          const audio = new Audio(data.url + '?t=' + Date.now());
          audioQueue.push(audio);
          if (!isPlaying) processQueue();
        }
      } catch (e) {
        console.error('SSE parse error:', e, line.slice(0, 200));
      }
    }
  }

  // Handle a final SSE event that did not end with \n\n.
  if (buffer.trim().startsWith('data: ')) {
    try {
      const data = JSON.parse(buffer.trim().slice(6));
      if (data.type === 'text') finalResponse = data.content || finalResponse;
    } catch (_) {}
  }

  return finalResponse || 'No result returned.';
}

function renderBatchResults(results) {
  return `<div class="batch-results">${results.map(({ command, result }) => {
    const company = extractCompanyName(command);
    const display = handleSpecialResponse(result);

    return `
      <section class="batch-result">
        <div class="batch-company">${escapeHtml(company)}</div>
        <div class="batch-finding">Finding HR email</div>
        <div class="batch-content">${display}</div>
      </section>
    `;
  }).join('')}</div>`;
}

function extractCompanyName(command) {
  const match = command.match(/^find\s+(?:the\s+)?(?:hr|human\s+resources)\s+email\s+for\s+(.+)$/i);
  if (match) return match[1].trim();

  const forMatch = command.match(/\bfor\s+(.+)$/i);
  return forMatch ? forMatch[1].trim() : command;
}

function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value == null ? '' : String(value);
  return div.innerHTML;
}

async function sendSingleMessage(text) {
  audioQueue = [];
  isPlaying = false;
  if (currentAudio) { currentAudio.pause(); currentAudio = null; }

  sendBtn.disabled = true;
  setStatus('thinking');

  addMessage('user', text);
  const thinking = addMessage('doom', '<div class="thinking-dots"><span></span><span></span><span></span></div>');

  try {
    const res = await fetch('/chat-stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop();

      for (const evt of events) {
        const line = evt.trim();
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.type === 'text') {
            const display = handleSpecialResponse(data.content);
            thinking.innerHTML = display;
          }
          if (data.type === 'audio' && window._speakOutput) {
            const audio = new Audio(data.url + '?t=' + Date.now());
            audioQueue.push(audio);
            if (!isPlaying) processQueue();
          }
        } catch (e) {
          console.error('SSE parse error:', e, line.slice(0, 200));
        }
      }
    }
  } catch (e) {
    thinking.innerHTML = 'Connection error. Is server running?';
  }

  sendBtn.disabled = false;
  setStatus('online');
  inputEl.focus();
}

function autoResizeInput() {
  inputEl.style.height = 'auto';
  const maxHeight = parseFloat(getComputedStyle(inputEl).maxHeight) || 180;
  const nextHeight = Math.min(inputEl.scrollHeight, maxHeight);
  inputEl.style.height = `${Math.max(26, nextHeight)}px`;
  inputEl.style.overflowY = inputEl.scrollHeight > maxHeight ? 'auto' : 'hidden';
}

inputEl.addEventListener('input', autoResizeInput);

sendBtn.onclick = () => sendMessage();

inputEl.onkeydown = e => {
  // Enter sends the current composer content.
  // Shift+Enter creates a new line, which can contain another command.
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
};

document.addEventListener('click', function unlock() {
  new Audio().play().catch(() => {});
  document.removeEventListener('click', unlock);
}, { once: true });

if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = new SR();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = 'en-US';
  let isListening = false;

  micBtn.onclick = () => {
    audioQueue = [];
    isPlaying = false;
    if (currentAudio) { currentAudio.pause(); currentAudio = null; }

    if (isListening) { recognition.stop(); return; }
    isListening = true;
    micBtn.classList.add('listening');
    micBtn.textContent = '⏹';
    voiceBanner.classList.add('active');
    inputEl.placeholder = 'Listening...';
    recognition.start();
  };

  recognition.onresult = e => {
    const transcript = Array.from(e.results).map(r => r[0].transcript).join('');
    inputEl.value = transcript;
    if (e.results[e.results.length - 1].isFinal) { stopListening(); sendMessage(transcript); }
  };

  recognition.onend = () => stopListening();
  recognition.onerror = () => stopListening();

  function stopListening() {
    isListening = false;
    micBtn.classList.remove('listening');
    micBtn.textContent = '🎤';
    voiceBanner.classList.remove('active');
    inputEl.placeholder = 'Message DOOM...';
    inputEl.value = '';
    autoResizeInput();
  }
} else { micBtn.style.display = 'none'; }

let memoryOpen = false;

async function toggleMemory() {
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

function closeMemory(e) {
  if (e.target === document.getElementById('memory-panel')) {
    memoryOpen = false;
    document.getElementById('memory-panel').classList.remove('open');
  }
}

async function clearChat() {
  await fetch('/reset', { method: 'DELETE' });
  messagesEl.innerHTML = '';
  addMessage('doom', 'Session cleared. Fresh start. 🔥');
}

async function uploadDoc(input) {
  const file = input.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  const thinking = addMessage('doom', `<div class="thinking-dots"><span></span><span></span><span></span></div> Indexing ${file.name}...`);
  const res = await fetch('/upload', { method: 'POST', body: formData });
  const data = await res.json();
  thinking.innerHTML = `${data.result} — ask me anything about it.`;
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js')
    .then(() => console.log('DOOM PWA ready'))
    .catch(e => console.log('SW:', e));
}

async function getBriefing() {
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
  } catch(e) {
    thinking.innerHTML = 'Briefing error. Try again.';
  }

  if (btn) { btn.textContent = '☀️'; btn.style.pointerEvents = 'auto'; }
}

// Global state for retrieved job dataset
window._loadedJobs = [];

function renderJobCards(payload) {
  const jobs = payload.jobs || payload; // supports old bare-array shape too, just in case
  const platformCounts = payload.platform_counts || {};
  window._loadedJobs = jobs;

  const countsLine = Object.entries(platformCounts)
    .map(([plat, count]) => `${plat}: ${count}`)
    .join(' &nbsp;|&nbsp; ');

  let html = `
    <div class="job-cards-toolbar" style="display:flex;flex-direction:column;gap:4px;margin-bottom:8px;">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;">
        <span style="font-size:12px;color:var(--text-dim);font-family:'DM Mono',monospace;">${jobs.length} jobs found</span>
        <div style="display:flex;gap:6px;">
          <button class="btn-view" id="email-all-btn" onclick="emailAllJobs()">Email All 📧</button>
          <button class="btn-apply" id="apply-all-btn" onclick="applyToAll()">Apply All 🚀</button>
        </div>
      </div>
      <div style="font-size:11px;color:var(--text-mid);font-family:'DM Mono',monospace;">${countsLine}</div>
    </div>
    <div class="job-cards-container">
  `;

  jobs.forEach((job, idx) => {
    html += `
      <div class="job-card" id="job-card-${idx}">
        <div class="job-card-title">${job.title}</div>
        <div class="job-card-company">${job.company}</div>
        <div style="margin-bottom:6px;"><span style="font-size:10px;color:var(--text-dim);">📍 ${job.platform}</span></div>
        <div class="job-card-snippet">${job.snippet || (job.description ? job.description.substring(0, 100) : '')}...</div>
        <div class="job-card-actions">
          <button class="btn-view" onclick="openJobModal(${idx})">📋 View Details</button>
          <button class="btn-apply" onclick="applySingleJob(${idx})">Apply 🚀</button>
        </div>
      </div>
    `;
  });

  html += '</div>';
  return html;
}



function removeJobCard(index) {
  const card = document.getElementById(`job-card-${index}`);
  if (card) {
    card.style.transition = 'opacity 0.3s ease';
    card.style.opacity = '0';
    setTimeout(() => card.remove(), 300);
  }
}

async function applySingleJob(index) {
  const job = window._loadedJobs[index];
  if (!job) return;

  const btn = document.querySelector(`#job-card-${index} .btn-apply`);
  if (btn) { btn.disabled = true; btn.textContent = 'Applying...'; }

  try {
    const res = await fetch('/api/apply-single-job', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ index })
    });
    const data = await res.json();

    if (data.apply_url) {
      window.open(data.apply_url, '_blank'); // manual platforms — open the real listing
    }

    if (data.success) {
      removeJobCard(index);
      updateSuccessRate();
    } else if (btn) {
      btn.disabled = false;
      btn.textContent = 'Apply 🚀';
    }
  } catch (e) {
    if (btn) { btn.disabled = false; btn.textContent = 'Apply 🚀'; }
  }
}

async function sendEmailForJob(index) {
  const btn = document.getElementById('modal-email-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Sending...'; }

  try {
    const res = await fetch('/api/send-email-job', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ index })
    });
    const data = await res.json();
    if (btn) {
      btn.disabled = false;
      btn.textContent = data.success ? '✅ Email Sent' : '📧 Send Email (retry)';
    }
    // No removeJobCard, no forceCloseJobModal — card stays, user can still Apply separately
  } catch (e) {
    if (btn) { btn.disabled = false; btn.textContent = '📧 Send Email'; }
  }
}

// NEW — "Email All" bulk button in the job-cards toolbar. Calls the
// BulkApplyTool-backed /api/send-email-all route added alongside this file
// split (replaces the previously broken /api/apply-all-channels route,
// which pointed at a tool that didn't exist in registry.py).
async function emailAllJobs() {
  if (window._emailAllRunning) return;
  if (!confirm('Send application emails for every job currently in the pool?')) return;

  window._emailAllRunning = true;
  const btn = document.getElementById('email-all-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Sending...'; }

  try {
    const res = await fetch('/api/send-email-all', { method: 'POST' });
    const data = await res.json();
    addMessage('doom', (data.result || 'No result returned.').replace(/\n/g, '<br/>'));
  } catch (e) {
    addMessage('doom', '❌ Email-all request failed.');
  }

  if (btn) { btn.disabled = false; btn.textContent = 'Email All 📧'; }
  window._emailAllRunning = false;
  updateSuccessRate();
}

function openJobModal(index) {
  const job = window._loadedJobs[index];
  if (!job) return;

  document.getElementById('modal-job-title').textContent = job.title;
  document.getElementById('modal-job-company').textContent = job.company;
  document.getElementById('modal-job-desc').textContent = job.description || job.snippet;
  document.getElementById('modal-job-url').href = job.url || '#';

  const applyBtn = document.getElementById('modal-apply-btn');
  applyBtn.disabled = false;
  applyBtn.textContent = 'Apply Now 🚀';
  applyBtn.onclick = () => {
    forceCloseJobModal();
    applySingleJob(index);
  };

  // Add/update the Send Email button — for after manually applying on the platform
  let emailBtn = document.getElementById('modal-email-btn');
  if (!emailBtn) {
    emailBtn = document.createElement('button');
    emailBtn.id = 'modal-email-btn';
    emailBtn.className = 'btn-view';
    emailBtn.style.marginRight = '8px';
    document.querySelector('.job-modal-footer').prepend(emailBtn);
  }
  emailBtn.disabled = false;
  emailBtn.textContent = '📧 Send Email';
  emailBtn.onclick = () => sendEmailForJob(index);

  document.getElementById('job-modal').classList.add('open');
}

function closeJobModal(e) {
  if (e.target === document.getElementById('job-modal')) {
    forceCloseJobModal();
  }
}

function forceCloseJobModal() {
  document.getElementById('job-modal').classList.remove('open');
}

function applyToJob(company, title, index) {
  const prompt = `Auto-apply for Job #${index} (${title} at ${company})`;
  sendMessage(prompt);
}


window._applyAllCancelled = false;

async function updateSuccessRate() {
  try {
    const res = await fetch('/api/stats/success-rate');
    const data = await res.json();
    const badge = document.getElementById('success-rate-badge');
    badge.textContent = data.total === 0
      ? '📊 No applications yet'
      : `📊 ${data.rate}% success (${data.applied}/${data.total})`;
  } catch (e) {
    console.log('Success rate fetch failed:', e);
  }
}

function cancelApplyAll() {
  window._applyAllCancelled = true;
  document.getElementById('apply-progress-panel').classList.remove('open');
}
async function applyToAll() {
  if (window._applyAllRunning) return;
  const jobs = window._loadedJobs;
  if (!jobs.length) return;

  if (!confirm(`Apply to all ${jobs.length} jobs (platform automation + email + direct links)?`)) return;

  window._applyAllRunning = true;
  window._applyAllCancelled = false;

  const btn = document.getElementById('apply-all-btn');
  if (btn) btn.disabled = true;

  const panel = document.getElementById('apply-progress-panel');
  const label = document.getElementById('apply-progress-label');
  const companyEl = document.getElementById('apply-progress-company');
  const fill = document.getElementById('apply-progress-fill');
  if (panel) panel.classList.add('open');

  let applied = 0, failed = 0;

  for (let i = 0; i < jobs.length; i++) {
    if (window._applyAllCancelled) break;
    if (!document.getElementById(`job-card-${i}`)) continue; // already removed individually earlier

    const job = jobs[i];
    if (label) label.textContent = `Applying ${i + 1}/${jobs.length}`;
    if (companyEl) companyEl.textContent = job.company || 'Hiring Company';
    if (fill) fill.style.width = `${Math.round(((i + 1) / jobs.length) * 100)}%`;

    try {
      const res = await fetch('/api/apply-single-job', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ index: i })
      });
      const data = await res.json();

      if (data.apply_url) window.open(data.apply_url, '_blank');

      if (data.success) {
        applied++;
        removeJobCard(i);
      } else {
        failed++;
      }
    } catch (e) {
      failed++;
    }

    await new Promise(r => setTimeout(r, 500));
  }

  if (label) {
    label.textContent = window._applyAllCancelled
      ? `Cancelled: ${applied} applied, ${failed} failed`
      : `Done: ${applied} applied, ${failed} failed`;
  }
  if (companyEl) companyEl.textContent = '';
  setTimeout(() => { if (panel) panel.classList.remove('open'); }, 2500);

  if (btn) { btn.disabled = false; btn.textContent = 'Apply All 🚀'; }
  window._applyAllRunning = false;
  updateSuccessRate();
}

async function applyPlatformsOnly() {
  if (window._applyAllRunning) return;
  const jobs = window._loadedJobs;
  const platformJobs = jobs
    .map((job, idx) => ({ job, idx }))
    .filter(({ job }) => job.auto_apply);

  if (!platformJobs.length) {
    alert('No platform-automatable jobs (Naukri/Wellfound) in this list.');
    return;
  }

  if (!confirm(`Queue ${platformJobs.length} jobs for Naukri/Wellfound automation + email?`)) return;

  window._applyAllRunning = true;
  const btn = document.getElementById('apply-platforms-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Queuing...'; }

  const panel = document.getElementById('apply-progress-panel');
  const label = document.getElementById('apply-progress-label');
  const companyEl = document.getElementById('apply-progress-company');
  const fill = document.getElementById('apply-progress-fill');
  if (panel) panel.classList.add('open');

  let applied = 0, failed = 0;

  for (let i = 0; i < platformJobs.length; i++) {
    if (window._applyAllCancelled) break;
    const { job, idx } = platformJobs[i];

    if (label) label.textContent = `Queuing ${i + 1}/${platformJobs.length}`;
    if (companyEl) companyEl.textContent = job.company || 'Hiring Company';
    if (fill) fill.style.width = `${Math.round(((i + 1) / platformJobs.length) * 100)}%`;

    try {
      const res = await fetch('/api/apply-single-job', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ index: idx })
      });
      const data = await res.json();
      if (data.success) {
        applied++;
        removeJobCard(idx);
      } else {
        failed++;
      }
    } catch (e) {
      failed++;
    }

    await new Promise(r => setTimeout(r, 500));
  }

  if (label) label.textContent = `Done: ${applied} queued, ${failed} failed`;
  if (companyEl) companyEl.textContent = '';
  setTimeout(() => { if (panel) panel.classList.remove('open'); }, 2500);

  if (btn) { btn.disabled = false; btn.textContent = '🤖 Platform Apply All'; }
  window._applyAllRunning = false;
  updateSuccessRate();
}