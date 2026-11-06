// landing.js
// Show the owner's startup greeting only once per browser.

const hero = document.getElementById('landing-hero');
const greetingEl = document.getElementById('hero-greeting');
const subEl = document.getElementById('hero-sub');

const GREETING_KEY = 'doom_owner_greeting_seen_v1';

let dismissed = true;
let autoDismissTimer = null;

export function applyLandingGreeting(identity) {
  if (!hero || !greetingEl || !subEl) return;

  if (!identity?.is_owner || !identity.name) {
    hero.classList.add('hidden');
    return;
  }

  greetingEl.textContent = `Hi ${identity.name} 👋`;
  subEl.textContent = 'Good to see you — what are we working on today?';

  let alreadySeen = false;

  try {
    alreadySeen = localStorage.getItem(GREETING_KEY) === '1';
  } catch (error) {
    console.warn('Could not read greeting preference:', error);
  }

  if (alreadySeen) {
    hero.classList.add('hidden');
    return;
  }

  try {
    localStorage.setItem(GREETING_KEY, '1');
  } catch (error) {
    console.warn('Could not save greeting preference:', error);
  }

  dismissed = false;
  hero.classList.remove('hidden');

  clearTimeout(autoDismissTimer);
  autoDismissTimer = setTimeout(dismissHero, 4000);
}

export function dismissHero() {
  if (dismissed || !hero) return;

  dismissed = true;
  clearTimeout(autoDismissTimer);
  hero.classList.add('hidden');
}