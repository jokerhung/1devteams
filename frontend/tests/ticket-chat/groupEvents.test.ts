import { describe, it, expect } from "vitest";
import fixture from "./fixtures/bugfix-events.json";
import {
  cleanContent,
  groupEvents,
} from "@/components/ticket-chat/groupEvents";
import type { ChatEvent } from "@/components/ticket-chat/types";
const events = fixture as ChatEvent[];
describe("engine event grouping", () => {
  it("keeps the initial report and five agent turns, with resolved confirm on tester", () => {
    const groups = groupEvents(events);
    expect(groups[0].type).toBe("user");
    const turns = groups.filter((g) => g.type === "turn");
    expect(turns).toHaveLength(5);
    const tester = turns.find((g) => g.agent === "@tester")!;
    expect(tester.gate?.kind).toBe("human_confirm");
    expect(tester.gate?.resolved?.approved).toBe(true);
    expect(turns.every((g) => !!g.endedAt)).toBe(true);
    expect(
      turns.find((g) => g.agent === "@developer")?.permissions.length,
    ).toBeGreaterThan(0);
  });
  it("merges repeated edits from the original to the final text and tool updates", () => {
    const base = events.find((e) => e.event_type === "agent_turn_start")!;
    const edit = (
      seq: number,
      old_text: string,
      new_text: string,
    ): ChatEvent => ({
      ...base,
      seq,
      event_type: "file_edit",
      metadata: { path: "app.ts", old_text, new_text },
    });
    const groups = groupEvents([
      base,
      edit(100, "old\n", "middle\n"),
      edit(101, "middle\n", "final\n"),
      {
        ...base,
        seq: 102,
        event_type: "tool_call",
        metadata: { tool_call_id: "t", title: "Read app.ts" },
      },
      {
        ...base,
        seq: 103,
        event_type: "tool_call_update",
        metadata: { toolCallId: "t", status: "completed" },
      },
    ]);
    const turn = groups[0];
    expect(turn.type).toBe("turn");
    if (turn.type !== "turn") return;
    expect(turn.files["app.ts"].diff).toContain("-old\n+final");
    expect(turn.files["app.ts"].diff).not.toContain("middle");
    expect(Object.keys(turn.tools)).toHaveLength(1);
    expect(turn.tools.t.metadata.title).toBe("Read app.ts");
  });
  it("hides engine routing and release markers", () => {
    expect(cleanContent("Done\n@@ROUTE:ready\n@@RELEASE {}@@END")).toBe("Done");
  });
  it("appends terminal chunks by session without mutating source events or merging separate commands", () => {
    const base = events.find((e) => e.event_type === "agent_turn_start")!;
    const chunks: ChatEvent[] = [
      {
        ...base,
        id: "out-1",
        event_type: "terminal_output",
        content: "hello",
        metadata: { terminal_id: "one" },
      },
      {
        ...base,
        id: "out-2",
        event_type: "terminal_output",
        content: " world\n",
        metadata: { terminal_id: "one" },
      },
      {
        ...base,
        id: "out-3",
        event_type: "terminal_output",
        content: "other",
        metadata: { terminal_id: "two" },
      },
      {
        ...base,
        id: "out-4",
        event_type: "terminal_output",
        content: "git",
        metadata: { command: "git status" },
      },
    ];
    const first = groupEvents([base, ...chunks])[0];
    const second = groupEvents([base, ...chunks])[0];
    expect(first.type).toBe("turn");
    if (first.type !== "turn" || second.type !== "turn") return;
    expect(first.terminals).toHaveLength(3);
    expect(first.terminals[0].content).toBe("hello world\n");
    expect(second.terminals).toEqual(first.terminals);
    expect(chunks[0].content).toBe("hello");
  });
});
