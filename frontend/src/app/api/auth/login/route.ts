import { NextResponse } from "next/server";
import { backendUrl, sameOrigin, sessionCookie } from "@/lib/server-api";
export async function POST(request: Request) {
  if (!sameOrigin(request))
    return NextResponse.json(
      { detail: "Origin không hợp lệ" },
      { status: 403 },
    );
  try {
    const response = await fetch(`${backendUrl}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await request.text(),
      signal: AbortSignal.timeout(15000),
    });
    const data = await response.json();
    if (!response.ok)
      return NextResponse.json(data, { status: response.status });
    const result = NextResponse.json({ user: data.user });
    result.cookies.set(sessionCookie, data.access_token, {
      httpOnly: true,
      sameSite: "lax",
      secure: new URL(request.url).protocol === "https:",
      path: "/",
      maxAge: 86400,
    });
    return result;
  } catch {
    return NextResponse.json(
      { detail: "Không kết nối được backend" },
      { status: 502 },
    );
  }
}
