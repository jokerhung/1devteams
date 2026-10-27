export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
async function apiResponse(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
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
  return response;
}
export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await apiResponse(path, options);
  return response.status === 204 ? (undefined as T) : response.json();
}

export async function apiStream<T>(
  path: string,
  options: RequestInit,
  onEvent: (event: T) => void,
): Promise<void> {
  const response = await apiResponse(path, {
    ...options,
    headers: { ...options.headers, Accept: "text/event-stream" },
  });
  if (!response.headers.get("content-type")?.includes("text/event-stream")) {
    onEvent({ type: "reply", ...(await response.json()) } as T);
    return;
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error("Không nhận được luồng phản hồi của agent.");
  const decoder = new TextDecoder();
  let buffer = "";
  const dispatch = (frame: string) => {
    const data = frame
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (data) onEvent(JSON.parse(data) as T);
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += done
        ? decoder.decode()
        : decoder.decode(value, { stream: true });
      let match;
      while ((match = /\r?\n\r?\n/.exec(buffer))) {
        dispatch(buffer.slice(0, match.index));
        buffer = buffer.slice(match.index + match[0].length);
      }
      if (done) {
        if (buffer.trim()) dispatch(buffer);
        break;
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
export const send = <T>(path: string, body?: unknown, method = "POST") =>
  apiFetch<T>(path, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
export const assetUrl = (url: string) =>
  `/api/backend${url.replace(/^\/api/, "")}`;
