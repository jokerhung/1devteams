import { NextRequest, NextResponse } from "next/server";
export function middleware(request: NextRequest) {
  if (!request.cookies.get("aiteams_session")?.value) {
    const login = new URL("/login", request.url);
    login.host =
      request.headers.get("x-forwarded-host") ||
      request.headers.get("host") ||
      login.host;
    return NextResponse.redirect(login);
  }
  return NextResponse.next();
}
export const config = {
  matcher: [
    "/",
    "/agents/:path*",
    "/templates/:path*",
    "/teams/:path*",
    "/projects/:path*",
    "/notifications/:path*",
  ],
};
