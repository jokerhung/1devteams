import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { ActionTimeline } from "@/components/ui-app/action-timeline";

it("collapses older actions, shows file changes and the current command with elapsed time", () => {
  const actions = Array.from({ length: 6 }, (_, index) => ({
    id: String(index),
    title: `src/file${index}.tsx`,
    status: "completed",
    kind: "file" as const,
    added: 4,
    removed: 2,
  }));
  render(
    <ActionTimeline
      actions={[
        ...actions,
        { id: "command", title: "npm run typecheck", status: "in_progress" },
      ]}
      startedAt={Date.now() - 12000}
      label="Agent"
    />,
  );
  const summary = screen.getByText("2 thao tác trước");
  expect(summary.closest("details")).not.toHaveAttribute("open");
  fireEvent.click(summary);
  expect(summary.closest("details")).toHaveAttribute("open");
  expect(
    within(
      screen.getByRole("list", { name: "5 hành động gần nhất" }),
    ).getAllByRole("listitem"),
  ).toHaveLength(5);
  expect(screen.getAllByText("+4")).toHaveLength(6);
  expect(
    within(screen.getByRole("status")).getByText("npm run typecheck"),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Thời gian chạy")).toHaveTextContent("12s");
  expect(screen.getByLabelText("Đang xử lý")).toHaveClass("animate-spin");
});
