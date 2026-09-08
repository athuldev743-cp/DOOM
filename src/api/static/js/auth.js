// auth.js
// Google Sign-In integration.

export function initGoogleAuth() {
  google.accounts.id.initialize({
    client_id: "1069358536248-fs6uak4fv0uof46l4usuir0tlmae2u9m.apps.googleusercontent.com",
    callback: handleGoogleSignIn,
    auto_select: true,
    itp_support: true
  });
  google.accounts.id.prompt();
}

async function handleGoogleSignIn(response) {
  await fetch('/auth/google', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential: response.credential })
  });
  // No UI change needed here — the cookie is now set, and main.js's
  // initIdentity() (via /auth/whoami) picks up the name on next load.
}
