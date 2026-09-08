// leads.js
// Admin-only visitor/lead sidebar — everyone who's chatted with DOOM as
// a non-owner, listed like a chat-history panel, with a detail popup.

import { escapeHtml } from './core.js';

let leads = [];

export async function loadLeads() {
  const listEl = document.getElementById('leads-list');
  listEl.innerHTML = '<div class="leads-empty">Loading…</div>';

  try {
    const res = await fetch('/api/leads');
    if (!res.ok) throw new Error('not authorized');
    const data = await res.json();
    leads = data.visitors || [];
    renderLeadsList();
  } catch (e) {
    listEl.innerHTML = '<div class="leads-empty">Could not load visitors.</div>';
  }
}

function renderLeadsList() {
  const listEl = document.getElementById('leads-list');

  if (!leads.length) {
    listEl.innerHTML = '<div class="leads-empty">No leads yet.</div>';
    return;
  }

  listEl.innerHTML = leads.map((v, idx) => `
    <div class="lead-item" data-idx="${idx}">
      <div class="lead-item-name">${escapeHtml(v.name || 'Unknown visitor')}</div>
      <div class="lead-item-meta">${escapeHtml([v.role, v.company].filter(Boolean).join(' · ') || 'No details yet')}</div>
    </div>
  `).join('');

  listEl.querySelectorAll('.lead-item').forEach(el => {
    el.addEventListener('click', () => openLeadModal(leads[Number(el.dataset.idx)]));
  });
}

function openLeadModal(lead) {
  document.getElementById('lead-modal-name').textContent = lead.name || 'Unknown visitor';
  document.getElementById('lead-modal-role').textContent =
    [lead.role, lead.company].filter(Boolean).join(' · ') || '—';

  document.getElementById('lead-modal-body').innerHTML = `
    <p><strong>Interested in:</strong><br>${escapeHtml(lead.interest || '—')}</p>
    <p style="margin-top:12px;"><strong>Summary:</strong><br>${escapeHtml(lead.summary || '—')}</p>
    <p style="margin-top:12px;font-size:11px;color:var(--text-dim);">
      First seen: ${lead.first_seen ? new Date(lead.first_seen).toLocaleString() : '—'}<br>
      Last seen: ${lead.last_seen ? new Date(lead.last_seen).toLocaleString() : '—'}
    </p>
  `;
  document.getElementById('lead-modal').classList.add('open');
}

export function toggleLeadsPanel() {
  const panel = document.getElementById('leads-panel');
  const opening = !panel.classList.contains('open');
  panel.classList.toggle('open', opening);
  if (opening) loadLeads();
}

export function closeLeadsPanel(e) {
  if (e.target === document.getElementById('leads-panel')) {
    document.getElementById('leads-panel').classList.remove('open');
  }
}

export function closeLeadModal(e) {
  if (!e || e.target === document.getElementById('lead-modal')) {
    document.getElementById('lead-modal').classList.remove('open');
  }
}