import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});
vi.mock("next/navigation", () => ({
  usePathname: () => "/projects/p1",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
class Events {
  onmessage: ((event: { data: string }) => void) | null = null;
  close() {}
}
vi.stubGlobal("EventSource", Events);
