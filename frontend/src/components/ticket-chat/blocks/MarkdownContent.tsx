"use client";
import {
  Children,
  isValidElement,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import Markdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Agent } from "@/lib/types";
import { AgentPill } from "@/components/ui-app/primitives";
import { ChatImage } from "@/components/ui-app/chat-image";
import { assetUrl } from "@/lib/api";

function imageUrl(src: string) {
  return src.startsWith("/api/attachments/") ? assetUrl(src) : src;
}

function isImageLink(href: string) {
  return (
    /^data:image\/(?:png|jpeg|gif|webp);base64,/i.test(href) ||
    /\.(?:png|jpe?g|gif|webp|avif|bmp)(?:[?#]|$)/i.test(href)
  );
}
const emptyAgents: Agent[] = [];
function Highlight({
  code,
  language,
  enabled,
}: {
  code: string;
  language: string;
  enabled: boolean;
}) {
  const [html, setHtml] = useState("");
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    void (async () => {
      try {
        const { codeToHtml } = await import("shiki");
        const value = await codeToHtml(code, {
          lang: language,
          theme: "github-light",
        });
        if (active) setHtml(value);
      } catch {
        /* Unknown languages remain plain code. */
      }
    })();
    return () => {
      active = false;
    };
  }, [code, language, enabled]);
  return (
    <div
      className="my-2 overflow-x-auto rounded-lg bg-stone-50 p-3 font-mono text-xs leading-5 [&_pre]:m-0 [&_pre]:p-0 [&_pre]:font-[inherit] [&_code]:text-[inherit]"
      data-testid="code-block"
    >
      {enabled && html ? (
        <div dangerouslySetInnerHTML={{ __html: html }} />
      ) : (
        <pre>
          <code>{code}</code>
        </pre>
      )}
    </div>
  );
}
export function MarkdownContent({
  text,
  agents = emptyAgents,
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
  const components = useMemo<Components>(() => {
    const mention = (children: ReactNode): ReactNode =>
      Children.map(children, (child) => {
        if (typeof child !== "string") return child;
        return child.split(/(@[\w-]+)/g).map((part, i) => {
          const agent = agents.find((a) => a.handle === part);
          return agent ? <AgentPill key={i} agent={agent} /> : part;
        });
      });
    return {
      p: ({ children }) => <p>{mention(children)}</p>,
      li: ({ children }) => <li>{mention(children)}</li>,
      img: ({ src, alt }) =>
        typeof src === "string" && src ? (
          <ChatImage src={imageUrl(src)} alt={alt || "Ảnh trong hội thoại"} />
        ) : null,
      a: ({ children, href, node }) => {
        if (
          node?.children.some(
            (child) => child.type === "element" && child.tagName === "img",
          )
        )
          return <span>{children}</span>;
        if (href && isImageLink(href))
          return (
            <ChatImage
              src={imageUrl(href)}
              alt={
                Children.toArray(children)
                  .filter((child) => typeof child === "string")
                  .join("") || "Ảnh trong hội thoại"
              }
            />
          );
        return (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sky-700 underline"
          >
            {children}
          </a>
        );
      },
      pre: ({ children }) => {
        const child = Children.toArray(children)[0];
        if (isValidElement<{ className?: string; children?: string }>(child))
          return (
            <Highlight
              code={String(child.props.children || "")}
              language={
                /language-(\S+)/.exec(child.props.className || "")?.[1] ||
                "text"
              }
              enabled={!streaming}
            />
          );
        return <pre>{children}</pre>;
      },
      code: ({ children }) => (
        <code className="rounded bg-stone-100 px-1 font-mono text-xs">
          {children}
        </code>
      ),
    };
  }, [agents, streaming]);
  return (
    <div
      className="space-y-2 break-words text-[13.5px] leading-relaxed [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_table]:block [&_table]:overflow-x-auto [&_td]:border [&_td]:p-2 [&_th]:border [&_th]:p-2"
      data-testid="markdown-content"
    >
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={components}
        urlTransform={(url) =>
          /^data:image\/(?:png|jpeg|gif|webp);base64,/i.test(url)
            ? url
            : defaultUrlTransform(url)
        }
      >
        {streaming ? rendered : text}
      </Markdown>
    </div>
  );
}
