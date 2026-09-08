// chat.js
// Chat message rendering, special backend response handling, and the
// send flow (single message + multi-line batch mode).

import { dom, setStatus, escapeHtml } from './core.js';
import { stopAudio, enqueueAudioUrl } from './audio.js';
import { renderJobCards } from './jobs.js';

export function addMessage(role, html) {
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
  dom.messagesEl.appendChild(row);
  dom.messagesEl.scrollTop = dom.messagesEl.scrollHeight;
  return bubble;
}

export function handleSpecialResponse(response) {
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

// --- Sending messages ---

export async function sendMessage(text) {
  text = text || dom.inputEl.value;
  if (!text || !text.trim()) return;

  dom.inputEl.value = '';
  dom.inputEl.style.height = '28px';
  dom.inputEl.scrollTop = 0;

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

async function sendSingleMessage(text) {
  stopAudio();

  dom.sendBtn.disabled = true;
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
          if (data.type === 'audio') {
            enqueueAudioUrl(data.url);
          }
        } catch (e) {
          console.error('SSE parse error:', e, line.slice(0, 200));
        }
      }
    }
  } catch (e) {
    thinking.innerHTML = 'Connection error. Is server running?';
  }

  dom.sendBtn.disabled = false;
  setStatus('online');
  dom.inputEl.focus();
}

// Multi-command batch handling.
// A multi-line message is treated as ONE user submission. Each line is
// processed independently, but the UI waits until ALL results are ready
// and then renders one modern grouped answer.
async function sendBatchAsOneAnswer(commands) {
  stopAudio();

  dom.sendBtn.disabled = true;
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

  dom.sendBtn.disabled = false;
  setStatus('online');
  dom.inputEl.focus();
  dom.messagesEl.scrollTop = dom.messagesEl.scrollHeight;
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

        if (data.type === 'audio') {
          enqueueAudioUrl(data.url);
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

// --- Composer / misc chat controls ---

function autoResizeInput() {
  dom.inputEl.style.height = 'auto';
  const maxHeight = parseFloat(getComputedStyle(dom.inputEl).maxHeight) || 180;
  const nextHeight = Math.min(dom.inputEl.scrollHeight, maxHeight);
  dom.inputEl.style.height = `${Math.max(26, nextHeight)}px`;
  dom.inputEl.style.overflowY = dom.inputEl.scrollHeight > maxHeight ? 'auto' : 'hidden';
}

export async function clearChat() {
  await fetch('/reset', { method: 'DELETE' });
  dom.messagesEl.innerHTML = '';
  addMessage('doom', 'Session cleared. Fresh start. 🔥');
}

export function initChat() {
  dom.inputEl.addEventListener('input', autoResizeInput);
  dom.sendBtn.addEventListener('click', () => sendMessage());
  dom.inputEl.addEventListener('keydown', e => {
    // Enter sends the current composer content.
    // Shift+Enter creates a new line, which can contain another command.
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
}