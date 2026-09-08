// audio.js
// Text-to-speech playback (queue + toggle) and speech-to-text mic input.

import { dom } from './core.js';

let speakOutput = true;
dom.speakBtn.classList.add('active');
dom.speakBtn.textContent = '🔊';

let audioQueue = [];
let isPlaying = false;
let currentAudio = null;

export function isSpeakEnabled() {
  return speakOutput;
}

export function toggleSpeak() {
  speakOutput = !speakOutput;
  dom.speakBtn.classList.toggle('active', speakOutput);
  dom.speakBtn.textContent = speakOutput ? '🔊' : '🔇';
  if (!speakOutput) stopAudio();
}

export function stopAudio() {
  audioQueue = [];
  isPlaying = false;
  if (currentAudio) { currentAudio.pause(); currentAudio = null; }
}

function processQueue() {
  if (!speakOutput || audioQueue.length === 0) {
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

// Used when the backend sends an SSE 'audio' event with a URL to a clip.
export function enqueueAudioUrl(url) {
  if (!speakOutput) return;
  const audio = new Audio(url + '?t=' + Date.now());
  audioQueue.push(audio);
  if (!isPlaying) processQueue();
}

// Used for on-demand TTS of arbitrary text (e.g. the daily briefing).
export function speak(text) {
  if (!speakOutput || !text || !text.trim()) return;

  const sentences = text.match(/[^.!?]+[.!?]+/g) || [text];

  sentences.forEach((sentence) => {
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

// Unlocks autoplay on the first user interaction (browser audio policy).
document.addEventListener('click', function unlock() {
  new Audio().play().catch(() => {});
  document.removeEventListener('click', unlock);
}, { once: true });

// --- Voice input (speech-to-text) ---

export function initVoiceInput(onFinalTranscript) {
  if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
    dom.micBtn.style.display = 'none';
    return;
  }

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = new SR();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = 'en-US';
  let isListening = false;

  dom.micBtn.onclick = () => {
    stopAudio();

    if (isListening) { recognition.stop(); return; }
    isListening = true;
    dom.micBtn.classList.add('listening');
    dom.micBtn.textContent = '⏹';
    dom.voiceBanner.classList.add('active');
    dom.inputEl.placeholder = 'Listening...';
    recognition.start();
  };

  recognition.onresult = e => {
    const transcript = Array.from(e.results).map(r => r[0].transcript).join('');
    dom.inputEl.value = transcript;
    if (e.results[e.results.length - 1].isFinal) {
      stopListening();
      onFinalTranscript(transcript);
    }
  };

  recognition.onend = () => stopListening();
  recognition.onerror = () => stopListening();

  function stopListening() {
    isListening = false;
    dom.micBtn.classList.remove('listening');
    dom.micBtn.textContent = '🎤';
    dom.voiceBanner.classList.remove('active');
    dom.inputEl.placeholder = 'Message DOOM...';
    dom.inputEl.value = '';
    // Let chat.js's own 'input' listener handle the resize — avoids
    // audio.js needing to import chat.js just for autoResizeInput().
    dom.inputEl.dispatchEvent(new Event('input'));
  }
}