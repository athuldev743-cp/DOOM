// Google Sign-In: explicit button only. No automatic One Tap prompt.

let initialized = false;
let attempts = 0;

export function initGoogleAuth(onAuthenticated) {
  if (initialized) return;

  const googleId = window.google?.accounts?.id;

  if (!googleId) {
    if (attempts++ < 20) {
      setTimeout(() => initGoogleAuth(onAuthenticated), 300);
    } else {
      console.error('Google Identity Services failed to load.');
    }
    return;
  }

  initialized = true;

  googleId.initialize({
    client_id: "1069358536248-fs6uak4fv0uof46l4usuir0tlmae2u9m.apps.googleusercontent.com",
    callback: async (response) => {
      try {
        const res = await fetch('/auth/google', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ credential: response.credential })
        });

        const data = await res.json();

        if (!res.ok || data.status !== 'ok') {
          console.error('DOOM sign-in rejected:', data);
          return;
        }

        if (onAuthenticated) await onAuthenticated();
      } catch (error) {
        console.error('Google sign-in failed:', error);
      }
    }
  });

  googleId.renderButton(
    document.getElementById('google-signin-button'),
    { theme: 'outline', size: 'medium', text: 'signin_with', shape: 'pill' }
  );
}
