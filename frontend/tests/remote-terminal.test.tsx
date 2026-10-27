import { act, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import RemoteTerminal from "@/components/ticket-chat/RemoteTerminal";

const terminal = vi.hoisted(() => ({
  input: (data: string) => {
    void data;
  },
  writes: [] as { data: string; parse: () => void }[],
}));
vi.mock("@xterm/xterm/css/xterm.css", () => ({}));
vi.mock("@xterm/xterm", () => ({
  Terminal: class {
    options: object;
    element?: HTMLElement;
    buffer = { active: { viewportY: 0, baseY: 0 } };
    constructor(options: object) {
      this.options = options;
    }
    loadAddon() {}
    onScroll() {}
    onWriteParsed() {}
    onResize() {}
    onData(callback: (data: string) => void) {
      terminal.input = callback;
    }
    open(element: HTMLElement) {
      this.element = element;
    }
    focus() {}
    reset() {}
    dispose() {}
    write(data: string, callback: () => void) {
      terminal.writes.push({
        data,
        parse: () => {
          if (data.includes("\x1b[c")) terminal.input("\x1b[?1;2c");
          callback();
        },
      });
    }
  },
}));
vi.mock("@xterm/addon-fit", () => ({
  FitAddon: class {
    fit() {}
  },
}));
vi.mock("@xterm/addon-web-links", () => ({ WebLinksAddon: class {} }));
vi.mock("@xterm/addon-webgl", () => ({
  WebglAddon: class {
    onContextLoss() {}
    dispose() {}
  },
}));

it("does not send protocol replies from replay, but preserves live negotiation and keyboard input", async () => {
  class Source {
    static current: Source;
    static OPEN = 1;
    readyState = 1;
    bufferedAmount = 0;
    sent: { type: string; data?: string }[] = [];
    send(data: string) {
      this.sent.push(JSON.parse(data));
    }
    onmessage: ((event: { data: string }) => void) | null = null;
    onerror = null;
    constructor() {
      Source.current = this;
    }
    close() {}
    frame(value: object) {
      this.onmessage?.({ data: JSON.stringify(value) });
    }
  }
  vi.stubGlobal("WebSocket", Source);
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  const input = () =>
    Source.current.sent.filter((f) => f.type === "input").map((f) => f.data);
  vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
    Response.json({ enabled: true }),
  );
  const { unmount } = render(<RemoteTerminal projectId="project-1" />);
  await waitFor(() => expect(Source.current).toBeDefined());
  act(() => {
    Source.current.frame({
      type: "ready",
      session_id: "existing-session",
      reset: true,
    });
    Source.current.frame({
      type: "output",
      data: "old prompt\x1b[c",
      replay: true,
      seq: 1,
    });
    Source.current.frame({ type: "output", data: "live query\x1b[c", seq: 2 });
    Source.current.frame({ type: "synced", seq: 1 });
  });
  expect(screen.getByTestId("remote-terminal")).toHaveAttribute(
    "data-connected",
    "true",
  );
  await waitFor(() => expect(terminal.writes).toHaveLength(1));
  act(() => terminal.writes[0].parse());
  expect(input()).toEqual([]);
  await waitFor(() => expect(terminal.writes).toHaveLength(2));
  act(() => terminal.writes[1].parse());
  await waitFor(() => expect(input()).toEqual(["\x1b[?1;2c"]));
  act(() => terminal.input("\x1b[A"));
  await waitFor(() => expect(input()).toEqual(["\x1b[?1;2c", "\x1b[A"]));
  unmount();
  vi.unstubAllGlobals();
});
