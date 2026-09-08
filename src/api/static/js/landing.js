// landing.js
// The landing hero: greets the owner by name, or shows the generic
// intro for visitors, then fades out on first interaction.

const hero = document.getElementById('landing-hero');
const greetingEl = document.getElementById('hero-greeting');
const subEl = document.getElementById('hero-sub');

let dismissed = false;
let autoDismissTimer = null;

export function initLandingTimer() {
  autoDismissTimer = setTimeout(dismissHero, 4000);
}

export function applyLandingGreeting(identity) {
  if (identity.is_owner && identity.name) {
    greetingEl.textContent = `Hi ${identity.name} 👋`;
    subEl.textContent = "Good to see you — what are we working on today?";
  }
}

export function dismissHero() {
  if (dismissed) return;
  dismissed = true;
  clearTimeout(autoDismissTimer);
  hero.classList.add('hidden');
}