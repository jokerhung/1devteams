"use client";
import { useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";
import { apiFetch, send } from "@/lib/api";

export default function RemoteTerminal({
  projectId,
  docked = false,
}: {
  projectId: string;
  docked?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const terminal = useRef<Terminal | null>(null);
  const write = useRef<(text: string) => void>(() => {});
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState("Đang kết nối…");
  const [session, setSession] = useState("");
  useEffect(() => {
    let disposed = false;
    let source: EventSource | undefined;
    let observer: ResizeObserver | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let input = "";
    let ready = false;
    let pending: Promise<unknown> = Promise.resolve();
    const term = new Terminal({
      fontFamily: "JetBrains Mono, Consolas, monospace",
      fontSize: 12,
      theme: { background: "#0c0a09" },
      scrollback: 3000,
      convertEol: false,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.loadAddon(
      new WebLinksAddon((_event, uri) => {
        if (/^https?:\/\//i.test(uri))
          window.open(uri, "_blank", "noopener,noreferrer");
      }),
    );
    terminal.current = term;
    const action = (body: object) => {
      pending = pending
        .then(() =>
          disposed
            ? undefined
            : send(`/projects/${projectId}/terminal/input`, body),
        )
        .catch((e) => {
          if (!disposed) setStatus(e.message);
        });
    };
    const flush = () => {
      if (input) {
        const data = input;
        input = "";
        for (let i = 0; i < data.length; i += 8192)
          action({ type: "input", data: data.slice(i, i + 8192) });
      }
    };
    write.current = (text) => {
      input += text;
      clearTimeout(timer);
      timer = setTimeout(flush, 25);
    };
    async function connect() {
      try {
        const config = await apiFetch<{ enabled: boolean }>(
          `/projects/${projectId}/terminal`,
        );
        if (disposed) return;
        if (!config.enabled) {
          setStatus("Remote terminal đã tắt (ENABLE_REMOTE_TERMINAL=false)");
          return;
        }
        term.open(host.current!);
        fit.fit();
        const resize = () => {
          if (!host.current?.clientWidth || !host.current?.clientHeight) return;
          fit.fit();
          if (ready)
            action({ type: "resize", cols: term.cols, rows: term.rows });
        };
        source = new EventSource(`/api/events?channel=terminal/${projectId}`);
        source.onmessage = ({ data }) => {
          const frame = JSON.parse(data);
          if (frame.type === "ready") {
            ready = true;
            setStatus("Đã kết nối");
            setSession(frame.session_id);
            resize();
          } else if (frame.type === "output") term.write(frame.data);
          else if (frame.type === "error" || frame.type === "exit") {
            setStatus(frame.data || "Shell đã kết thúc");
            source?.close();
          }
        };
        source.onerror = () => {
          source?.close();
          setStatus("Mất kết nối — bấm Kết nối lại để tiếp tục phiên");
        };
        term.onData((data) => write.current(data));
        observer = new ResizeObserver(resize);
        observer.observe(host.current!);
        term.focus();
      } catch (e) {
        if (!disposed) setStatus((e as Error).message);
      }
    }
    void connect();
    return () => {
      disposed = true;
      clearTimeout(timer);
      source?.close();
      observer?.disconnect();
      term.dispose();
      terminal.current = null;
    };
  }, [projectId, attempt]);
  return (
    <section
      aria-label="Remote terminal"
      className={docked ? "flex h-full min-h-0 flex-col" : undefined}
    >
      <p className="mb-2 rounded bg-amber-50 p-2 text-xs text-amber-900">
        Terminal chạy lệnh trực tiếp với quyền của bạn, không qua Permission
        Guard của agent.
      </p>
      <div className="mb-2 flex flex-wrap gap-2 text-xs">
        <button
          className="btn btn-light"
          onClick={() => setAttempt((n) => n + 1)}
        >
          Kết nối lại
        </button>
        <button
          className="btn btn-light"
          onClick={() => terminal.current?.clear()}
        >
          Xoá màn hình
        </button>
        <button
          className="btn btn-light"
          onClick={() =>
            navigator.clipboard
              .writeText(terminal.current?.getSelection() || "")
              .catch(() => setStatus("Không thể copy"))
          }
        >
          Copy
        </button>
        {["git status", "git log --oneline -10", "npm test"].map((cmd) => (
          <button
            key={cmd}
            disabled={status !== "Đã kết nối"}
            className="btn btn-light"
            onClick={() => write.current(cmd + "\r")}
          >
            {cmd}
          </button>
        ))}
      </div>
      <p role="status" className="mb-2 text-xs text-stone-500">
        {status}
      </p>
      <div
        ref={host}
        data-testid="remote-terminal"
        data-session-id={session}
        className={
          docked
            ? "min-h-0 flex-1 overflow-hidden rounded-lg bg-[#0c0a09] p-2"
            : "h-[50vh] min-h-72 overflow-hidden rounded-lg bg-[#0c0a09] p-2"
        }
      />
    </section>
  );
}
