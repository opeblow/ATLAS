const DOMAIN = process.env.NEXT_PUBLIC_COGNITO_DOMAIN || "";
const CLIENT_ID = process.env.NEXT_PUBLIC_COGNITO_APP_CLIENT_ID || "";
const REDIRECT_URI =
  process.env.NEXT_PUBLIC_COGNITO_REDIRECT_URI ||
  (typeof window === "undefined" ? "" : `${window.location.origin}/auth/callback`);
const STATE_KEY = "atlas_oauth_state";
const VERIFIER_KEY = "atlas_pkce_verifier";
export let authenticatedUserId = "";
let accessToken: string | null = null;

function decodeClaims(token: string): Record<string, unknown> | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "=")));
  } catch {
    return null;
  }
}

export function getAccessToken(): string | null {
  const token = accessToken;
  if (!token) return null;
  const claims = decodeClaims(token);
  if (
    typeof claims?.exp !== "number" ||
    claims.exp <= Math.floor(Date.now() / 1000) ||
    typeof claims.sub !== "string"
  ) {
    accessToken = null;
    authenticatedUserId = "";
    return null;
  }
  return token;
}

export function getAuthenticatedUserId(): string {
  const token = getAccessToken();
  const claims = token ? decodeClaims(token) : null;
  if (typeof claims?.sub !== "string") {
    throw new Error("Sign in to use ATLAS.");
  }
  authenticatedUserId = claims.sub;
  return authenticatedUserId;
}

export function getCognitoConfiguration(): { domain: string; clientId: string; redirectUri: string } {
  return { domain: DOMAIN.replace(/\/$/, ""), clientId: CLIENT_ID, redirectUri: REDIRECT_URI };
}

export async function beginSignIn(): Promise<void> {
  if (!DOMAIN || !CLIENT_ID || !REDIRECT_URI) {
    throw new Error("Cognito domain, app client ID, and redirect URI must be configured.");
  }
  const state = crypto.randomUUID();
  const random = crypto.getRandomValues(new Uint8Array(32));
  const verifier = btoa(String.fromCharCode(...random))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  const challenge = btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");

  sessionStorage.setItem(STATE_KEY, state);
  sessionStorage.setItem(VERIFIER_KEY, verifier);
  const authorize = new URL(`${DOMAIN}/oauth2/authorize`);
  authorize.search = new URLSearchParams({
    client_id: CLIENT_ID,
    response_type: "code",
    scope: "openid email",
    redirect_uri: REDIRECT_URI,
    state,
    code_challenge_method: "S256",
    code_challenge: challenge,
  }).toString();
  window.location.assign(authorize.toString());
}

export async function completeSignIn(): Promise<string> {
  const url = new URL(window.location.href);
  const error = url.searchParams.get("error_description") || url.searchParams.get("error");
  if (error) throw new Error(error);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const expectedState = sessionStorage.getItem(STATE_KEY);
  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  if (!code || !state || !expectedState || state !== expectedState || !verifier) {
    throw new Error("Sign-in response could not be verified. Please try again.");
  }
  if (!DOMAIN || !CLIENT_ID || !REDIRECT_URI) {
    throw new Error("Cognito domain, app client ID, and redirect URI must be configured.");
  }

  const response = await fetch(`${DOMAIN}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: CLIENT_ID,
      code,
      redirect_uri: REDIRECT_URI,
      code_verifier: verifier,
    }),
  });
  if (!response.ok) throw new Error(`Cognito token exchange failed (${response.status}).`);
  const result: { access_token?: string } = await response.json();
  if (!result.access_token || !decodeClaims(result.access_token)?.sub) {
    throw new Error("Cognito returned no usable access token.");
  }
  accessToken = result.access_token;
  sessionStorage.removeItem(STATE_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);
  window.history.replaceState({}, document.title, "/auth/callback");
  return getAuthenticatedUserId();
}

export function signOut(): void {
  authenticatedUserId = "";
  accessToken = null;
  sessionStorage.removeItem(STATE_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);
  if (DOMAIN && CLIENT_ID && REDIRECT_URI) {
    const logout = new URL(`${DOMAIN}/logout`);
    logout.search = new URLSearchParams({
      client_id: CLIENT_ID,
      logout_uri: new URL("/", REDIRECT_URI).toString(),
    }).toString();
    window.location.assign(logout.toString());
  } else {
    window.location.assign("/");
  }
}
