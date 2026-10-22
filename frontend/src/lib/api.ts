const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export interface HealthResponse {
  status: "ok";
  acp: { claude: boolean; codex: boolean };
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { Accept: "application/json", ...options.headers },
    signal: options.signal ?? AbortSignal.timeout(10_000),
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`API ${response.status}: ${response.statusText}`);
  return (await response.json()) as T;
}

export const getHealth = (signal?: AbortSignal) => apiFetch<HealthResponse>("/api/health", { signal });
