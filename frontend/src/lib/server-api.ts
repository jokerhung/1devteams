import "server-only";
export const backendUrl = (
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8060"
).replace(/\/$/, "");
export const sessionCookie = "aiteams_session";
export function sameOrigin(request: Request) {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  try {
    const source = new URL(origin);
    return (
      source.origin === new URL(request.url).origin ||
      source.host === request.headers.get("host")
    );
  } catch {
    return false;
  }
}
