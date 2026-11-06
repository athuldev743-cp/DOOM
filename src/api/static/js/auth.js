// auth.js
// Google Sign-In integration.

// Google Sign-In integration.

export function initGoogleAuth(onAuthenticated) {
  if (!window.google?.accounts?.id) {
    console.error('Google Identity Services unavailable');
    return;
  }

  google.accounts.id.initialize({
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

        console.log('DOOM session created');

        if (onAuthenticated) {
          await onAuthenticated();
        }
      } catch (error) {
        console.error('Google sign-in failed:', error);
      }
    },
    auto_select: true,
    itp_support: true
  });

  google.accounts.id.prompt();
}

