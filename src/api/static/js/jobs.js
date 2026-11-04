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
          <span style="font-size:11px;color:var(--text-dim);">Apply individually</span>
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
        <div style="margin-bottom:6px;"><span style="font-size:10px;color:var(--text-dim);">📍 ${job.location || job.market || "Location not specified"}${job.is_remote ? " · Remote" : ""} · ${job.platform}</span></div>
        <div class="job-card-snippet">${job.snippet || (job.description ? job.description.substring(0, 100) : '')}...</div>
        <div class="job-card-actions">
          <button class="btn-view" onclick="openJobModal(${idx})">📋 View Details</button>
          <button class="btn-apply" onclick="prepareJobApplication(${idx})">${job.application_status && job.application_status !== "discovered" ? "Review Application" : "Prepare CV"}</button>
          <button class="btn-view" id="confirm-job-${idx}" style="display:none" onclick="confirmJobSubmitted(${idx})">Confirm Submitted</button>
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
  if (!job || !job.db_id) return false;
  const btn = document.querySelector('#job-card-' + index + ' .btn-apply');
  if (btn) { btn.disabled = true; btn.textContent = 'Opening...'; }
  const popup = window.open('about:blank', '_blank');
  try {
    const res = await fetch('/api/jobs/open', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ job_id: job.db_id }) });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.detail || 'Could not open job');
    if (popup) popup.location.href = data.apply_url;
    if (btn) { btn.disabled = false; btn.textContent = 'Listing Opened ↗'; }
    const confirmBtn = document.getElementById('confirm-job-' + index);
    if (confirmBtn) confirmBtn.style.display = 'inline-block';
    return true;
  } catch (e) {
    if (popup) popup.close();
    if (btn) { btn.disabled = false; btn.textContent = 'Review Application'; }
    deps.addMessage('doom', 'Could not open job: ' + e.message);
    return false;
  }
}

function showApplicationReview(index, data, approved = false) {
  const job = loadedJobs[index];
  if (!job) return;
  const existing = document.getElementById('application-review-overlay');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.id = 'application-review-overlay';
  overlay.style.cssText = 'position:fixed;inset:0;z-index:10050;background:rgba(0,0,0,.72);display:flex;align-items:center;justify-content:center;padding:16px;';
  overlay.innerHTML = [
    '<section style="background:var(--panel,#111827);color:var(--text,#f8fafc);width:min(760px,96vw);max-height:90vh;overflow:auto;border:1px solid var(--border,#475569);border-radius:14px;padding:20px;box-shadow:0 20px 60px rgba(0,0,0,.4);">',
    '<div style="display:flex;justify-content:space-between;gap:12px;align-items:center;"><h3 style="margin:0;">Application review</h3><button id="review-close" class="btn-view" type="button">Close</button></div>',
    '<p id="review-job-title" style="font-weight:600;margin:12px 0 2px;"></p><p id="review-company" style="opacity:.75;margin:0 0 12px;"></p>',
    '<p style="margin:8px 0;"><a id="review-cv-link" target="_blank" rel="noopener noreferrer">Download tailored CV (PDF)</a></p>',
    '<label for="review-cover-letter" style="display:block;margin:12px 0 5px;">Cover letter — review and edit before approval</label>',
    '<textarea id="review-cover-letter" rows="12" style="width:100%;box-sizing:border-box;padding:10px;border-radius:8px;background:var(--input-bg,#0f172a);color:inherit;border:1px solid var(--border,#475569);resize:vertical;"></textarea>',
    '<label for="review-recipient" style="display:block;margin:12px 0 5px;">Recruiter email (optional; required only for email applications)</label>',
    '<input id="review-recipient" type="email" placeholder="recruiter@company.com" style="width:100%;box-sizing:border-box;padding:10px;border-radius:8px;background:var(--input-bg,#0f172a);color:inherit;border:1px solid var(--border,#475569);" />',
    '<div id="review-actions" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:14px;">',
    '<button id="review-approve" class="btn-apply" type="button">Approve CV &amp; Cover Letter</button>',
    '<button id="review-open" class="btn-view" type="button" style="display:none;">Open Original Listing</button>',
    '<button id="review-send" class="btn-view" type="button" style="display:none;">Send Approved Email + CV</button>',
    '<button id="review-confirm-submit" class="btn-view" type="button" style="display:none;">Confirm Submitted</button>',
    '</div><p id="review-status" role="status" style="font-size:12px;opacity:.8;margin:12px 0 0;"></p></section>'
  ].join('');
  document.body.appendChild(overlay);

  const title = overlay.querySelector('#review-job-title');
  const company = overlay.querySelector('#review-company');
  title.textContent = data.title || job.title || '';
  company.textContent = data.company || job.company || '';
  const cvLink = overlay.querySelector('#review-cv-link');
  cvLink.href = data.cv_url || job.cv_url || ('/api/jobs/' + job.db_id + '/cv');
  const letter = overlay.querySelector('#review-cover-letter');
  letter.value = data.cover_letter || job.cover_letter || '';
  const recipient = overlay.querySelector('#review-recipient');
  recipient.value = data.recipient_email || job.recipient_email || '';
  const status = overlay.querySelector('#review-status');
  status.textContent = data.status ? ('Status: ' + data.status) : 'Review both documents before approving.';
  overlay.querySelector('#review-close').onclick = () => overlay.remove();

  const approveButton = overlay.querySelector('#review-approve');
  const openButton = overlay.querySelector('#review-open');
  const sendButton = overlay.querySelector('#review-send');
  const confirmButton = overlay.querySelector('#review-confirm-submit');
  const currentStatus = data.status || job.application_status || 'prepared';

  if (approved || ['approved', 'opened', 'email_sent', 'submitted'].includes(currentStatus)) {
    approveButton.style.display = 'none';
    letter.readOnly = true;
    recipient.readOnly = true;
    openButton.style.display = ['approved', 'opened', 'email_sent'].includes(currentStatus) ? 'inline-block' : 'none';
    sendButton.style.display = ['approved', 'opened'].includes(currentStatus) && !!(data.recipient_email || job.recipient_email) ? 'inline-block' : 'none';
    confirmButton.style.display = (currentStatus === 'opened' || currentStatus === 'email_sent') ? 'inline-block' : 'none';
    if (currentStatus === 'email_sent') status.textContent = 'Approved application email sent.';
    if (currentStatus === 'submitted') status.textContent = 'Platform submission confirmed.';
  } else {
    openButton.style.display = 'none';
    sendButton.style.display = 'none';
    confirmButton.style.display = 'none';
  }

  approveButton.onclick = async () => {
    approveButton.disabled = true;
    approveButton.textContent = 'Approving...';
    try {
      const response = await fetch('/api/jobs/approve', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          job_id: job.db_id,
          cover_letter: letter.value,
          recipient_email: recipient.value.trim() || null
        })
      });
      const result = await response.json();
      if (!response.ok || !result.success) throw new Error(result.detail || 'Approval failed');
      job.application_status = 'approved';
      job.cover_letter = letter.value;
      job.recipient_email = recipient.value.trim();
      showApplicationReview(index, {
        ...data, status: 'approved', cover_letter: letter.value,
        recipient_email: recipient.value.trim(), cv_url: cvLink.href
      }, true);
    } catch (error) {
      status.textContent = error.message;
      approveButton.disabled = false;
      approveButton.textContent = 'Approve CV & Cover Letter';
    }
  };

  openButton.onclick = async () => {
    const opened = await applySingleJob(index);
    if (opened) {
      if (job.application_status !== 'email_sent') job.application_status = 'opened';
      status.textContent = 'Listing opened. Complete the application on the employer platform, then confirm below.';
      confirmButton.style.display = 'inline-block';
    }
  };

  sendButton.onclick = async () => {
    if (!confirm('Send the approved cover letter with the tailored CV attached to ' + recipient.value + '?')) return;
    sendButton.disabled = true;
    sendButton.textContent = 'Sending...';
    try {
      const response = await fetch('/api/jobs/send-email', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({job_id: job.db_id})
      });
      const result = await response.json();
      if (!response.ok || !result.success) throw new Error(result.detail || 'Email sending failed');
      job.application_status = 'email_sent';
      status.textContent = 'Email sent successfully.';
      sendButton.textContent = 'Email Sent';
    } catch (error) {
      status.textContent = error.message;
      sendButton.disabled = false;
      sendButton.textContent = 'Send Approved Email + CV';
    }
  };

  confirmButton.onclick = () => confirmJobSubmitted(index);
}

export async function prepareJobApplication(index) {
  const job = loadedJobs[index];
  if (!job || !job.db_id) return;
  if (job.application_status && job.application_status !== 'discovered') {
    showApplicationReview(index, {
      title: job.title, company: job.company,
      status: job.application_status, cv_url: job.cv_url,
      cover_letter: job.cover_letter, recipient_email: job.recipient_email
    }, job.application_status !== 'prepared');
    return;
  }

  const button = document.querySelector('#job-card-' + index + ' .btn-apply');
  if (button) { button.disabled = true; button.textContent = 'Preparing...'; }
  try {
    const response = await fetch('/api/jobs/prepare', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({job_id: job.db_id})
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.detail || 'CV preparation failed');
    job.application_status = 'prepared';
    job.cv_url = data.cv_url;
    job.cover_letter = data.cover_letter;
    showApplicationReview(index, data, false);
    if (button) button.textContent = 'Review Application';
  } catch (error) {
    deps.addMessage('doom', 'Could not prepare application: ' + error.message);
    if (button) { button.disabled = false; button.textContent = 'Prepare CV'; }
  }
}

export async function confirmJobSubmitted(index) {
  const job = loadedJobs[index];
  if (!job || !job.db_id) return;
  if (!confirm('Have you completed and submitted this application on the employer platform?')) return;
  const btn = document.getElementById('review-confirm-submit') || document.getElementById('confirm-job-' + index);
  if (btn) { btn.disabled = true; btn.textContent = 'Saving...'; }
  try {
    const res = await fetch('/api/jobs/confirm-submitted', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ job_id: job.db_id }) });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.detail || 'Could not save status');
    job.application_status = 'submitted';
    if (btn) { btn.textContent = '✓ Submitted'; btn.disabled = true; }
    const status = document.getElementById('review-status');
    if (status) status.textContent = 'Submission confirmed and saved.';
    updateSuccessRate();
  } catch (e) {
    if (btn) { btn.disabled = false; btn.textContent = 'Confirm Submitted'; }
    deps.addMessage('doom', 'Could not confirm submission: ' + e.message);
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
  applyBtn.textContent = 'Prepare CV & Review';
  applyBtn.onclick = () => {
    forceCloseJobModal();
    prepareJobApplication(index);
  };


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
window.confirmJobSubmitted = confirmJobSubmitted;
window.prepareJobApplication = prepareJobApplication;