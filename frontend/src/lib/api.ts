export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api/backend${path.replace(/^\/api/, "")}`, {
    ...options,
    headers: {
      ...(options.body && !(options.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...options.headers,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const detail = data.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.detail ||
          detail?.message ||
          data.message ||
          (Array.isArray(detail)
            ? detail.map((d: { msg: string }) => d.msg).join("; ")
            : `Yêu cầu thất bại (${response.status})`);
    if (response.status === 401 && typeof window !== "undefined")
      window.location.assign("/login");
    throw new ApiError(response.status, message);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export const send = <T>(path: string, body?: unknown, method = "POST") =>
  apiFetch<T>(path, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
export const assetUrl = (url: string) =>
  `/api/backend${url.replace(/^\/api/, "")}`;
