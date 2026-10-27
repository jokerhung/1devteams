import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

it.each([
  [
    "![Screenshot](https://example.test/result.png)",
    "https://example.test/result.png",
  ],
  [
    "[Screenshot](https://example.test/result.png)",
    "https://example.test/result.png",
  ],
  [
    "[![Screenshot](https://example.test/result.png)](https://example.test/result.png)",
    "https://example.test/result.png",
  ],
  [
    "![Screenshot](data:image/png;base64,iVBORw0KGgo=)",
    "data:image/png;base64,iVBORw0KGgo=",
  ],
  ["![Screenshot](/api/attachments/a1)", "/api/backend/attachments/a1"],
])(
  "opens markdown image in a popup without a new-tab link: %s",
  async (text, src) => {
    const user = userEvent.setup();
    const { container } = render(<MarkdownContent text={text} />);
    expect(container.querySelector('a[target="_blank"]')).toBeNull();
    await user.click(
      screen.getByRole("button", { name: "Phóng to Screenshot" }),
    );
    const popup = await screen.findByRole("dialog", { name: "Screenshot" });
    expect(
      within(popup).getByRole("img", { name: "Ảnh phóng to: Screenshot" }),
    ).toHaveAttribute("src", src);
    expect(
      within(popup).getByRole("link", { name: "Tải ảnh xuống" }),
    ).toHaveAttribute("download");
    await user.keyboard("{Escape}");
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  },
);

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
