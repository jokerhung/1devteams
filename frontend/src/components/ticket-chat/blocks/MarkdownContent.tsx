"use client";
import {
  Children,
  isValidElement,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Agent } from "@/lib/types";
import { AgentPill } from "@/components/ui-app/primitives";
function Highlight({ code, language }: { code: string; language: string }) {
  const [html, setHtml] = useState("");
  useEffect(() => {
    let active = true;
    import("shiki").then(async ({ codeToHtml }) => {
      try {
        const value = await codeToHtml(code, {
          lang: language,
          theme: "github-light",
        });
        if (active) setHtml(value);
      } catch {
        /* Unknown languages remain plain code. */
      }
    });
    return () => {
      active = false;
    };
  }, [code, language]);
  return html ? (
    <div
      className="my-2 overflow-x-auto rounded-lg bg-stone-50 p-3 text-xs"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  ) : (
    <pre className="overflow-x-auto bg-stone-50 p-3">
      <code>{code}</code>
    </pre>
  );
}
export function MarkdownContent({
  text,
  agents = [],
  streaming = false,
}: {
  text: string;
  agents?: Agent[];
  streaming?: boolean;
}) {
  const latest = useRef(text);
  latest.current = text;
  const [rendered, setRendered] = useState(text);
  useEffect(() => {
    if (!streaming) return;
    const timer = setInterval(() => setRendered(latest.current), 200);
    return () => clearInterval(timer);
  }, [streaming]);
  const mention = (children: ReactNode): ReactNode =>
    Children.map(children, (child) => {
      if (typeof child !== "string") return child;
      return child.split(/(@[\w-]+)/g).map((part, i) => {
        const agent = agents.find((a) => a.handle === part);
        return agent ? <AgentPill key={i} agent={agent} /> : part;
      });
    });
  return (
    <div
      className="space-y-2 break-words text-[13.5px] leading-relaxed [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_table]:block [&_table]:overflow-x-auto [&_td]:border [&_td]:p-2 [&_th]:border [&_th]:p-2"
      data-testid="markdown-content"
    >
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p>{mention(children)}</p>,
          li: ({ children }) => <li>{mention(children)}</li>,
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sky-700 underline"
            >
              {children}
            </a>
          ),
          pre: ({ children }) => {
            const child = Children.toArray(children)[0];
            if (
              isValidElement<{ className?: string; children?: string }>(child)
            )
              return (
                <Highlight
                  code={String(child.props.children || "")}
                  language={
                    /language-(\S+)/.exec(child.props.className || "")?.[1] ||
                    "text"
                  }
                />
              );
            return <pre>{children}</pre>;
          },
          code: ({ children }) => (
            <code className="rounded bg-stone-100 px-1 font-mono text-xs">
              {children}
            </code>
          ),
        }}
      >
        {streaming ? rendered : text}
      </Markdown>
    </div>
  );
}
