import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE_NAME, verifySessionToken } from "@/lib/auth";

export async function proxy(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE_NAME)?.value;
  const isAuthenticated = await verifySessionToken(token);
  const { pathname } = request.nextUrl;

  if (pathname === "/login") {
    if (isAuthenticated) {
      return NextResponse.redirect(new URL("/", request.url));
    }
    return NextResponse.next();
  }

  if (!isAuthenticated) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  // Everything except the login API routes and Next's own static assets —
  // those must stay reachable to unauthenticated users (the login route
  // handlers issue/clear the session cookie; the login page needs to
  // render at all before a session exists).
  matcher: ["/((?!api/auth|_next/static|_next/image|favicon.ico).*)"],
};
