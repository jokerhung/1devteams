import { afterEach, expect, it, vi } from "vitest";
import { TerminalOutput } from "@/lib/terminal-output";

afterEach(() => vi.unstubAllGlobals());

it("echoes small chunks immediately, batches bursts, and keeps replay/reset ordered", () => {
  let frame: FrameRequestCallback | undefined;
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    frame = callback;
    return 1;
  });
  vi.stubGlobal("cancelAnimationFrame", () => {
    frame = undefined;
  });
  const tick = () => {
    const callback = frame;
    frame = undefined;
    callback?.(0);
  };
  const writes: { data: string; done: () => void; replayBlocked: boolean }[] =
    [];
  const reset = vi.fn();
  const output = new TerminalOutput({
    reset,
    write(data, done) {
      writes.push({ data, done, replayBlocked: !output.acceptsInput });
    },
  });
  output.write("a");
  expect(writes.map((w) => w.data)).toEqual(["a"]);
  writes[0].done();
  output.write("x".repeat(1024));
  output.write("y".repeat(1024));
  expect(writes).toHaveLength(1);
  tick();
  expect(writes[1].data).toBe("x".repeat(1024) + "y".repeat(1024));
  output.write("discard before reset");
  output.reset();
  output.write("history query", true);
  output.write("live query");
  tick(); // In-flight parsing must finish before resetting the terminal.
  expect(reset).not.toHaveBeenCalled();
  writes[1].done();
  tick();
  expect(reset).toHaveBeenCalledOnce();
  expect(writes[2]).toMatchObject({
    data: "history query",
    replayBlocked: true,
  });
  writes[2].done();
  tick();
  expect(writes[3]).toMatchObject({ data: "live query", replayBlocked: false });
  output.dispose();
  writes[3].done();
  expect(frame).toBeUndefined();
});
