import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { MarkdownContent } from "@/components/ticket-chat/blocks/MarkdownContent";

const { codeToHtml } = vi.hoisted(() => ({ codeToHtml: vi.fn() }));
vi.mock("shiki", () => ({ codeToHtml }));

beforeEach(() => {
  codeToHtml.mockReset();
  codeToHtml.mockResolvedValue(
    '<pre class="shiki"><code>highlighted code</code></pre>',
  );
});

it("keeps highlighted code mounted when other message content changes", async () => {
  const code = "```ts\nconst value = 1;\n```";
  const { rerender } = render(<MarkdownContent text={code} />);
  const block = screen.getByTestId("code-block");
  const typography = block.className;
  await screen.findByText("highlighted code");
  rerender(<MarkdownContent text={`${code}\n\nAnother paragraph.`} />);
  expect(screen.getByTestId("code-block")).toBe(block);
  expect(block.className).toBe(typography);
  expect(block).toHaveTextContent("highlighted code");
  expect(codeToHtml).toHaveBeenCalledOnce();
});

it("uses stable plain code during streaming and highlights only after completion", async () => {
  const { rerender } = render(
    <MarkdownContent text={"```ts\nconst value = 1;\n```"} streaming />,
  );
  const typography = screen.getByTestId("code-block").className;
  rerender(<MarkdownContent text={"```ts\nconst value = 2;\n```"} streaming />);
  await waitFor(() =>
    expect(screen.getByTestId("code-block")).toHaveTextContent(
      "const value = 2;",
    ),
  );
  expect(codeToHtml).not.toHaveBeenCalled();
  expect(screen.getByTestId("code-block").className).toBe(typography);
  rerender(<MarkdownContent text={"```ts\nconst value = 2;\n```"} />);
  await screen.findByText("highlighted code");
  expect(codeToHtml).toHaveBeenCalledOnce();
  expect(screen.getByTestId("code-block").className).toBe(typography);
});
