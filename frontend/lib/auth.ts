/**
 * Minimal MVP authentication: a single administrator account configured
 * via server-only environment variables (never NEXT_PUBLIC_*, so the
 * password is never shipped to the client bundle), and a signed,
 * HttpOnly session cookie — no user database, no FastAPI backend
 * involvement, no roles/permissions.
 *
 * The cookie's signature is verified with HMAC-SHA256 via the Web Crypto
 * API (`crypto.subtle`), which is available in both the Node.js runtime
 * (route handlers) and the Edge runtime (middleware) without needing two
 * separate implementations or a runtime-specific config switch.
 */

export const SESSION_COOKIE_NAME = "eas_session";
export const SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 7; // 7 days

// Recent TypeScript DOM lib typings require `crypto.subtle` calls to
// receive an ArrayBuffer-backed view specifically (not the wider
// ArrayBufferLike that TextEncoder#encode()/Uint8Array construction
// produce). `.slice()` always returns a real ArrayBuffer, so this just
// narrows the type — it doesn't change any actual behavior.
function toArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

function getAuthSecret(): string {
  const secret = process.env.AUTH_SECRET;
  if (!secret) {
    throw new Error(
      "AUTH_SECRET environment variable is not set. Set it in frontend/.env.local " +
        "(see .env.example) before logging in.",
    );
  }
  return secret;
}

async function getHmacKey(): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    toArrayBuffer(new TextEncoder().encode(getAuthSecret())),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

function base64UrlEncode(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64UrlDecode(value: string): Uint8Array {
  const padLength = (4 - (value.length % 4)) % 4;
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat(padLength);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

interface SessionPayload {
  sub: string;
  exp: number; // epoch ms
}

export async function createSessionToken(username: string): Promise<string> {
  const payload: SessionPayload = {
    sub: username,
    exp: Date.now() + SESSION_MAX_AGE_SECONDS * 1000,
  };
  const payloadB64 = base64UrlEncode(new TextEncoder().encode(JSON.stringify(payload)));
  const key = await getHmacKey();
  const signature = await crypto.subtle.sign("HMAC", key, toArrayBuffer(new TextEncoder().encode(payloadB64)));
  const signatureB64 = base64UrlEncode(new Uint8Array(signature));
  return `${payloadB64}.${signatureB64}`;
}

export async function verifySessionToken(token: string | undefined | null): Promise<boolean> {
  if (!token) return false;
  const [payloadB64, signatureB64] = token.split(".");
  if (!payloadB64 || !signatureB64) return false;

  try {
    const key = await getHmacKey();
    const isValidSignature = await crypto.subtle.verify(
      "HMAC",
      key,
      toArrayBuffer(base64UrlDecode(signatureB64)),
      toArrayBuffer(new TextEncoder().encode(payloadB64)),
    );
    if (!isValidSignature) return false;

    const payload = JSON.parse(new TextDecoder().decode(base64UrlDecode(payloadB64))) as SessionPayload;
    return typeof payload.exp === "number" && payload.exp > Date.now();
  } catch {
    return false;
  }
}

export function verifyCredentials(username: string, password: string): boolean {
  const expectedUsername = process.env.ADMIN_USERNAME;
  const expectedPassword = process.env.ADMIN_PASSWORD;
  if (!expectedUsername || !expectedPassword) return false;
  return username === expectedUsername && password === expectedPassword;
}
