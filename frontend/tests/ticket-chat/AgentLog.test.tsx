import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { AgentLog } from "@/components/ticket-chat/AgentLog";
import type { LogLine } from "@/components/ticket-chat/types";

it("shows only the latest line, preserves expansion during streaming and opens ticket history", () => {
  const lines: LogLine[] = [{ seq: 1, at: "2026-10-23T10:00:00", agent: "@developer", kind: "deny", text: "permission git commit DENY" }, { seq: 2, at: "2026-10-23T10:00:01", agent: "@developer", kind: "tool", text: "Edit app.ts" }];
  const onFull = vi.fn();
  const { rerender } = render(<AgentLog lines={lines} running onFull={onFull} />);
  expect(screen.queryByText(/DENY/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Mở log lượt agent" }));
  expect(screen.getByText(/DENY/)).toBeInTheDocument();
  rerender(<AgentLog lines={[...lines, { ...lines[1], seq: 3, kind: "ok", text: "push successful" }]} running={false} onFull={onFull} />);
  expect(screen.getByRole("button", { name: "Mở log lượt agent" })).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText(/DENY/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Xem toàn bộ log/ }));
  expect(onFull).toHaveBeenCalledOnce();
});
