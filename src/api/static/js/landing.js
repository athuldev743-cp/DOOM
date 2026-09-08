// landing.js
// The landing hero: greets the owner by name (once Google sign-in
// resolves) or shows a generic intro for everyone else, then fades
// out on first interaction.

const hero = document.getElementById('landing-hero');
const greetingEl = document.getElementById('hero-greeting');
const subEl = document.getElementById('hero-sub');

let dismissed = false;
let autoDismissTimer = null;

export function initLanding() {
  // Auto-dismiss after a few seconds if the visitor hasn't typed yet —
  // mirrors the ChatGPT-style "greeting fades, composer takes over" feel.
  autoDismissTimer = setTimeout(dismissHero, 4000);
}

export function greetOwner(name) {
  if (!name) return;
  greetingEl.textContent = `Hi ${name} 👋`;
  subEl.textContent = "Good to see you — what are we working on today?";
}

export function dismissHero() {
  if (dismissed) return;
  dismissed = true;
  clearTimeout(autoDismissTimer);
  hero.classList.add('hidden');
}