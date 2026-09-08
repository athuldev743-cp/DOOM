// auth.js
// Google Sign-In integration.

import { greetOwner } from './landing.js';

export function initGoogleAuth() {
  google.accounts.id.initialize({
    client_id: "1069358536248-fs6uak4fv0uof46l4usuir0tlmae2u9m.apps.googleusercontent.com",
    callback: handleGoogleSignIn,
    auto_select: true,
    itp_support: true
  });
  google.accounts.id.prompt();
}

function decodeJwtPayload(token) {
  const payload = token.split('.')[1];
  const json = decodeURIComponent(
    atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
      .split('')
      .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
      .join('')
  );
  return JSON.parse(json);
}

async function handleGoogleSignIn(response) {
  await fetch('/auth/google', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential: response.credential })
  });

  try {
    const { given_name, name } = decodeJwtPayload(response.credential);
    greetOwner(given_name || name);
  } catch (e) {
    console.log('Could not decode sign-in name for greeting:', e);
  }
  // The cookie is now set, and future /chat-stream requests will
  // automatically be treated as owner.
}