// jobs.js
// Job search results: card rendering, detail modal, single/bulk apply
// flows, bulk email flow, and success-rate stats.

let loadedJobs = [];
let emailAllRunning = false;
let applyAllRunning = false;
let applyAllCancelled = false;

// sendMessage/addMessage are injected from main.js rather than imported
// directly, to avoid a circular import with chat.js (chat.js needs
// renderJobCards from here; this file needs sendMessage/addMessage from
// there).
let deps = { sendMessage: () => {}, addMessage: () => {} };

export function initJobs({ sendMessage, addMessage }) {
  deps = { sendMessage, addMessage };
}

export function renderJobCards(payload) {
  const jobs = payload.jobs || payload; // supports old bare-array shape too, just in case
  const platformCounts = payload.platform_counts || {};
  loadedJobs = jobs;

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

export function removeJobCard(index) {
  const card = document.getElementById(`job-card-${index}`);
  if (card) {
    card.style.transition = 'opacity 0.3s ease';
    card.style.opacity = '0';
    setTimeout(() => card.remove(), 300);
  }
}

// --- Single job actions ---

export async function applySingleJob(index) {
  const job = loadedJobs[index];
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

export function applyToJob(company, title, index) {
  const prompt = `Auto-apply for Job #${index} (${title} at ${company})`;
  deps.sendMessage(prompt);
}

// --- Job detail modal ---

export function openJobModal(index) {
  const job = loadedJobs[index];
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

export function closeJobModal(e) {
  if (e.target === document.getElementById('job-modal')) {
    forceCloseJobModal();
  }
}

export function forceCloseJobModal() {
  document.getElementById('job-modal').classList.remove('open');
}

// --- Email actions ---

export async function sendEmailForJob(index) {
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

// "Email All" bulk button in the job-cards toolbar. Calls the
// BulkApplyTool-backed /api/send-email-all route.
export async function emailAllJobs() {
  if (emailAllRunning) return;
  if (!confirm('Send application emails for every job currently in the pool?')) return;

  emailAllRunning = true;
  const btn = document.getElementById('email-all-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Sending...'; }

  try {
    const res = await fetch('/api/send-email-all', { method: 'POST' });
    const data = await res.json();
    deps.addMessage('doom', (data.result || 'No result returned.').replace(/\n/g, '<br/>'));
  } catch (e) {
    deps.addMessage('doom', '❌ Email-all request failed.');
  }

  if (btn) { btn.disabled = false; btn.textContent = 'Email All 📧'; }
  emailAllRunning = false;
  updateSuccessRate();
}



// --- Bulk apply ---

export function cancelApplyAll() {
  applyAllCancelled = true;
  document.getElementById('apply-progress-panel').classList.remove('open');
}

export async function applyToAll() {
  if (applyAllRunning) return;
  const jobs = loadedJobs;
  if (!jobs.length) return;

  if (!confirm(`Apply to all ${jobs.length} jobs (platform automation + email + direct links)?`)) return;

  applyAllRunning = true;
  applyAllCancelled = false;

  const btn = document.getElementById('apply-all-btn');
  if (btn) btn.disabled = true;

  const panel = document.getElementById('apply-progress-panel');
  const label = document.getElementById('apply-progress-label');
  const companyEl = document.getElementById('apply-progress-company');
  const fill = document.getElementById('apply-progress-fill');
  if (panel) panel.classList.add('open');

  let applied = 0, failed = 0;

  for (let i = 0; i < jobs.length; i++) {
    if (applyAllCancelled) break;
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
    label.textContent = applyAllCancelled
      ? `Cancelled: ${applied} applied, ${failed} failed`
      : `Done: ${applied} applied, ${failed} failed`;
  }
  if (companyEl) companyEl.textContent = '';
  setTimeout(() => { if (panel) panel.classList.remove('open'); }, 2500);

  if (btn) { btn.disabled = false; btn.textContent = 'Apply All 🚀'; }
  applyAllRunning = false;
  updateSuccessRate();
}

export async function applyPlatformsOnly() {
  if (applyAllRunning) return;
  const jobs = loadedJobs;
  const platformJobs = jobs
    .map((job, idx) => ({ job, idx }))
    .filter(({ job }) => job.auto_apply);

  if (!platformJobs.length) {
    alert('No platform-automatable jobs (Naukri/Wellfound) in this list.');
    return;
  }

  if (!confirm(`Queue ${platformJobs.length} jobs for Naukri/Wellfound automation + email?`)) return;

  applyAllRunning = true;
  const btn = document.getElementById('apply-platforms-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Queuing...'; }

  const panel = document.getElementById('apply-progress-panel');
  const label = document.getElementById('apply-progress-label');
  const companyEl = document.getElementById('apply-progress-company');
  const fill = document.getElementById('apply-progress-fill');
  if (panel) panel.classList.add('open');

  let applied = 0, failed = 0;

  for (let i = 0; i < platformJobs.length; i++) {
    if (applyAllCancelled) break;
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
  applyAllRunning = false;
  updateSuccessRate();
}
// --- Stats ---

export async function updateSuccessRate() {
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

// Expose the handful of functions referenced inside dynamically-generated
// job-card HTML — template strings can't reach module-scoped bindings,
// so these specifically need to live on window. Everything else in this
// file stays module-private.
window.openJobModal = openJobModal;
window.applySingleJob = applySingleJob;
window.emailAllJobs = emailAllJobs;
window.applyToAll = applyToAll;