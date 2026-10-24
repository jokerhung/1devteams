import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { Composer } from "@/components/ticket-chat/Composer";

it("allows drafting while history loads and prevents sending until ready", async () => {
  const onSend = vi.fn(async () => {});
  const props = {
    tid: "loading-ticket",
    userId: "test-user",
    slug: "test",
    agents: [],
    waiting: null,
    disabled: false,
    maxFiles: 5,
    maxMb: 10,
    onSend,
  };
  const { rerender } = render(<Composer {...props} sendDisabled />);
  const input = screen.getByRole("textbox");
  expect(input).toBeEnabled();
  fireEvent.change(input, {
    target: { value: "Draft before history arrives" },
  });
  await act(async () => {
    fireEvent.keyDown(input, { key: "Enter" });
  });
  expect(onSend).not.toHaveBeenCalled();
  expect(input).toHaveValue("Draft before history arrives");
  rerender(<Composer {...props} sendDisabled={false} />);
  await act(async () => {
    fireEvent.keyDown(input, { key: "Enter" });
  });
  expect(onSend).toHaveBeenCalledWith("Draft before history arrives", []);
});
