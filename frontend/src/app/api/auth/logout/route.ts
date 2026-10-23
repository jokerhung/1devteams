import { NextResponse } from "next/server";
import { sameOrigin, sessionCookie } from "@/lib/server-api";
export async function POST(request: Request) {
  if (!sameOrigin(request))
    return NextResponse.json(
      { detail: "Origin không hợp lệ" },
      { status: 403 },
    );
  const result = NextResponse.json({ ok: true });
  result.cookies.set(sessionCookie, "", {
    path: "/",
    maxAge: 0,
    httpOnly: true,
    sameSite: "lax",
  });
  return result;
}
