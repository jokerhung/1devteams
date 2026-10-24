import { afterEach, describe, expect, it, vi } from "vitest";
import { clientId } from "@/lib/client-id";

afterEach(() => vi.unstubAllGlobals());

describe("client UUIDs", () => {
  it("uses the browser UUID API when available", () => {
    const randomUUID = vi.fn(() => "4a06bf38-5092-4df6-8857-dd67c842b07c");
    vi.stubGlobal("crypto", { randomUUID });
    expect(clientId()).toBe("4a06bf38-5092-4df6-8857-dd67c842b07c");
    expect(randomUUID).toHaveBeenCalledOnce();
  });

  it("creates unique v4 UUIDs on HTTP without randomUUID", () => {
    const getRandomValues = globalThis.crypto.getRandomValues.bind(
      globalThis.crypto,
    );
    vi.stubGlobal("crypto", { getRandomValues });
    const ids = Array.from({ length: 100 }, clientId);
    expect(new Set(ids).size).toBe(100);
    expect(
      ids.every((id) =>
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(
          id,
        ),
      ),
    ).toBe(true);
  });
});
