import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS, createSessionToken, verifyCredentials } from "@/lib/auth";

export async function POST(request: NextRequest) {
  let body: { username?: unknown; password?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body." }, { status: 400 });
  }

  const username = typeof body.username === "string" ? body.username : "";
  const password = typeof body.password === "string" ? body.password : "";

  if (!process.env.ADMIN_USERNAME || !process.env.ADMIN_PASSWORD) {
    return NextResponse.json(
      { detail: "Administrator credentials are not configured on the server (ADMIN_USERNAME / ADMIN_PASSWORD)." },
      { status: 500 },
    );
  }

  if (!username || !password || !verifyCredentials(username, password)) {
    return NextResponse.json({ detail: "Invalid username or password." }, { status: 401 });
  }

  const token = await createSessionToken(username);
  const response = NextResponse.json({ ok: true });
  // `secure` must reflect whether *this request* actually arrived over
  // HTTPS, not just NODE_ENV: a production build served over plain HTTP
  // (e.g. a bare IP:port with no TLS) would otherwise get a cookie the
  // browser silently refuses to store, making login look broken.
  // `x-forwarded-proto` covers being behind a TLS-terminating reverse proxy.
  const forwardedProto = request.headers.get("x-forwarded-proto");
  const isHttps = forwardedProto ? forwardedProto === "https" : request.nextUrl.protocol === "https:";
  response.cookies.set(SESSION_COOKIE_NAME, token, {
    httpOnly: true,
    secure: isHttps,
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE_SECONDS,
  });
  return response;
}
