import { cookies } from "next/headers";
import { backendUrl, sameOrigin, sessionCookie } from "@/lib/server-api";
export async function GET(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  if (request.method !== "GET" && !sameOrigin(request))
    return Response.json({ detail: "Origin không hợp lệ" }, { status: 403 });
  const token = (await cookies()).get(sessionCookie)?.value;
  const { path } = await context.params;
  if (path.some((p) => p === ".." || /[\\/?#]/.test(p)))
    return new Response(null, { status: 400 });
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  try {
    const response = await fetch(
      `${backendUrl}/api/${path.map(encodeURIComponent).join("/")}${new URL(request.url).search}`,
      {
        method: request.method,
        headers,
        body: ["GET", "HEAD"].includes(request.method)
          ? undefined
          : await request.arrayBuffer(),
        cache: "no-store",
        signal: AbortSignal.timeout(120000),
        redirect: "error",
      },
    );
    const resultHeaders = new Headers({
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    });
    for (const name of ["content-type", "content-disposition"]) {
      const value = response.headers.get(name);
      if (value) resultHeaders.set(name, value);
    }
    return new Response(response.body, {
      status: response.status,
      headers: resultHeaders,
    });
  } catch {
    return Response.json(
      { detail: "Không kết nối được backend" },
      { status: 502 },
    );
  }
}
export { GET as POST, GET as PATCH, GET as PUT, GET as DELETE };
