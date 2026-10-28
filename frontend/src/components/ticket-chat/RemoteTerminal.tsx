"use client";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebglAddon } from "@xterm/addon-webgl";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";
import { ApiError, apiFetch } from "@/lib/api";
import { TerminalOutput } from "@/lib/terminal-output";
import { MoreHorizontal, RotateCw } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";

const terminalKeys = [
  { label: "Ctrl+C", description: "Ngắt lệnh", data: "\x03" },
  { label: "Ctrl+D", description: "EOF / thoát shell", data: "\x04" },
  { label: "Ctrl+Z", description: "Tạm dừng tiến trình", data: "\x1a" },
  { label: "Ctrl+L", description: "Làm sạch màn hình", data: "\x0c" },
  { label: "Ctrl+U", description: "Xóa dòng nhập", data: "\x15" },
  { label: "Tab", description: "Hoàn thành", data: "\t" },
  { label: "Esc", description: "Escape", data: "\x1b" },
  { label: "Enter", description: "Xuống dòng", data: "\r" },
  { label: "↑", description: "Mũi tên lên", data: "\x1b[A" },
  { label: "↓", description: "Mũi tên xuống", data: "\x1b[B" },
  { label: "→", description: "Mũi tên phải", data: "\x1b[C" },
  { label: "←", description: "Mũi tên trái", data: "\x1b[D" },
];

export default function RemoteTerminal({
  projectId,
  docked = false,
  reconnectKey = 0,
  active = true,
  commandTarget,
}: {
  projectId?: string;
  docked?: boolean;
  reconnectKey?: number;
  active?: boolean;
  commandTarget?: HTMLDivElement | null;
}) {
  const host = useRef<HTMLDivElement>(null);
  const terminal = useRef<Terminal | null>(null);
  const write = useRef<(text: string) => boolean>(() => false);
  const [command, setCommand] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState("Đang kết nối…");
  const [session, setSession] = useState("");
  const [scroll, setScroll] = useState({ top: 0, max: 0 });
  const touch = useRef<{ y: number; top: number; scrolling: boolean } | null>(
    null,
  );
  useEffect(() => {
    if (!active) return;
    setStatus("Đang kết nối…");
    let disposed = false;
    let source: WebSocket | undefined;
    let sessionId = "";
    let lastSeq = 0;
    let webgl: WebglAddon | undefined;
    let observer: ResizeObserver | undefined;
    let ready = false;
    let authenticated = false;
    let stopped = false;
    let connecting = false;
    let generation = 0;
    let retries = 0;
    let lastFrame = Date.now();
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let readyTimer: ReturnType<typeof setTimeout> | undefined;
    let configRequest: AbortController | undefined;
    let scrollFrame = 0;
    setScroll({ top: 0, max: 0 });
    const term = new Terminal({
      fontFamily: "JetBrains Mono, Consolas, monospace",
      fontSize: 12,
      theme: { background: "#0c0a09" },
      scrollback: 3000,
      convertEol: false,
      disableStdin: true,
    });
    const fit = new FitAddon();
    const output = new TerminalOutput(term);
    term.loadAddon(fit);
    term.loadAddon(
      new WebLinksAddon((_event, uri) => {
        if (/^https?:\/\//i.test(uri))
          window.open(uri, "_blank", "noopener,noreferrer");
      }),
    );
    terminal.current = term;
    const syncScroll = () => {
      if (scrollFrame) return;
      scrollFrame = requestAnimationFrame(() => {
        scrollFrame = 0;
        if (disposed) return;
        const buffer = term.buffer.active;
        setScroll((previous) =>
          previous.top === buffer.viewportY && previous.max === buffer.baseY
            ? previous
            : { top: buffer.viewportY, max: buffer.baseY },
        );
      });
    };
    term.onScroll(syncScroll);
    term.onWriteParsed(syncScroll);
    term.onResize(syncScroll);
    const disconnect = () => {
      generation++;
      ready = false;
      authenticated = false;
      term.options.disableStdin = true;
      clearTimeout(readyTimer);
      configRequest?.abort();
      if (source) {
        source.onmessage = null;
        source.onerror = null;
        source.onclose = null;
        source.close();
        source = undefined;
      }
    };
    const reconnect = (delay?: number) => {
      if (disposed || stopped) return;
      disconnect();
      clearTimeout(retryTimer);
      if (!navigator.onLine) {
        setStatus("Mất mạng — terminal sẽ tự kết nối lại khi có mạng");
        return;
      }
      const wait =
        delay ?? Math.min(30_000, 2_000 * 2 ** Math.min(retries++, 4));
      setStatus(
        `Mất kết nối — tự kết nối lại sau ${Math.ceil(wait / 1000)} giây…`,
      );
      retryTimer = setTimeout(() => {
        retryTimer = undefined;
        void connect();
      }, wait);
    };
    const fail = (error: unknown) => {
      if (disposed) return;
      if (
        error instanceof ApiError &&
        [400, 401, 403, 404, 422].includes(error.status)
      ) {
        stopped = true;
        disconnect();
        clearTimeout(retryTimer);
        setStatus(error.message);
      } else reconnect();
    };
    const action = (body: object) => {
      if (!authenticated || !source || source.readyState !== WebSocket.OPEN)
        return false;
      if (source.bufferedAmount > 1024 * 1024) {
        reconnect();
        return false;
      }
      try {
        source.send(JSON.stringify(body));
        return true;
      } catch {
        reconnect();
        return false;
      }
    };
    write.current = (text) => {
      if (!ready || disposed) return false;
      // Split paste input without cutting a UTF-16 surrogate pair in half.
      for (let i = 0; i < text.length;) {
        let end = Math.min(i + 8192, text.length);
        if (end < text.length && /[\uD800-\uDBFF]/.test(text[end - 1])) end--;
        if (!action({ type: "input", data: text.slice(i, end) })) return false;
        i = end;
      }
      return true;
    };
    const resize = () => {
      if (
        !term.element ||
        !host.current?.clientWidth ||
        !host.current?.clientHeight
      )
        return;
      fit.fit();
      if (ready) action({ type: "resize", cols: term.cols, rows: term.rows });
    };
    term.onData((data) => {
      // Initial live negotiation may be parsed before the synced frame arrives.
      if (output.acceptsInput) action({ type: "input", data });
    });
    async function connect() {
      if (disposed || stopped || connecting) return;
      if (!navigator.onLine) {
        reconnect();
        return;
      }
      connecting = true;
      const version = generation;
      const request = new AbortController();
      configRequest = request;
      const configTimeout = setTimeout(() => request.abort(), 20_000);
      try {
        const config = await apiFetch<{ enabled: boolean }>(
          projectId ? `/projects/${projectId}/terminal` : "/workspace-terminal",
          { signal: request.signal },
        );
        if (disposed || version !== generation) return;
        if (!config.enabled) {
          stopped = true;
          setStatus("Remote terminal đã tắt (ENABLE_REMOTE_TERMINAL=false)");
          return;
        }
        if (!term.element) {
          term.open(host.current!);
          // Keep the default renderer if WebGL is unavailable or its context is lost.
          try {
            webgl = new WebglAddon();
            webgl.onContextLoss(() => {
              webgl?.dispose();
              webgl = undefined;
            });
            term.loadAddon(webgl);
          } catch {
            webgl?.dispose();
            webgl = undefined;
          }
          observer = new ResizeObserver(resize);
          observer.observe(host.current!);
          term.focus();
        }
        resize();
        const url = new URL(
          projectId ? `/ws/terminal/${projectId}` : "/ws/workspace-terminal",
          window.location.href,
        );
        url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
        if (sessionId) {
          url.searchParams.set("session_id", sessionId);
          url.searchParams.set("after_seq", String(lastSeq));
        }
        const stream = new WebSocket(url);
        source = stream;
        readyTimer = setTimeout(() => {
          if (source === stream && !ready) reconnect();
        }, 20_000);
        stream.onmessage = ({ data }) => {
          if (disposed || source !== stream) return;
          lastFrame = Date.now();
          const frame = JSON.parse(data);
          if (frame.type === "ready") {
            authenticated = true;
            if (frame.reset !== false || frame.session_id !== sessionId) {
              output.reset();
              lastSeq = 0;
            }
            sessionId = frame.session_id;
          } else if (frame.type === "synced") {
            clearTimeout(readyTimer);
            lastSeq = Math.max(lastSeq, frame.seq);
            ready = true;
            retries = 0;
            term.options.disableStdin = false;
            setStatus("Đã kết nối");
            setSession(sessionId);
            resize();
          } else if (frame.type === "output") {
            if (frame.seq <= lastSeq) return;
            if (!frame.replay && lastSeq && frame.seq !== lastSeq + 1) {
              reconnect(0);
              return;
            }
            lastSeq = frame.seq;
            output.write(frame.data, frame.replay === true);
          } else if (frame.type === "ping") {
            stream.send(JSON.stringify({ type: "pong" }));
          } else if (frame.type === "error" || frame.type === "exit") {
            if (frame.type === "error" && frame.retryable) reconnect();
            else {
              stopped = true;
              disconnect();
              setStatus(frame.data || "Shell đã kết thúc");
            }
          }
        };
        stream.onclose = () => {
          if (source === stream) reconnect();
        };
        stream.onerror = () => {
          if (source === stream) reconnect();
        };
      } catch (e) {
        if (version === generation) fail(e);
      } finally {
        clearTimeout(configTimeout);
        if (configRequest === request) configRequest = undefined;
        connecting = false;
        if (
          !disposed &&
          !stopped &&
          version !== generation &&
          !ready &&
          !source &&
          !retryTimer
        )
          reconnect();
      }
    }
    const wake = () => {
      if (!stopped && (!ready || Date.now() - lastFrame > 45_000))
        reconnect(500);
    };
    const focus = () => {
      if (!ready) wake();
    };
    const visibility = () => {
      if (document.visibilityState === "visible") wake();
    };
    const offline = () => {
      reconnect();
    };
    window.addEventListener("online", wake);
    window.addEventListener("offline", offline);
    window.addEventListener("focus", focus);
    document.addEventListener("visibilitychange", visibility);
    const heartbeat = setInterval(() => {
      if (
        ready &&
        document.visibilityState === "visible" &&
        Date.now() - lastFrame > 45_000
      )
        reconnect();
    }, 10_000);
    void connect();
    return () => {
      disposed = true;
      disconnect();
      clearTimeout(retryTimer);
      clearInterval(heartbeat);
      window.removeEventListener("online", wake);
      window.removeEventListener("offline", offline);
      window.removeEventListener("focus", focus);
      document.removeEventListener("visibilitychange", visibility);
      source?.close();
      cancelAnimationFrame(scrollFrame);
      touch.current = null;
      observer?.disconnect();
      output.dispose();
      term.dispose();
      terminal.current = null;
    };
  }, [projectId, attempt, reconnectKey, active]);
  const commandBox = (
    <form
      className="flex min-w-0 flex-1 items-center gap-1"
      aria-label="Gửi lệnh terminal"
      onSubmit={(event) => {
        event.preventDefault();
        if (active && command.trim() && write.current(command + "\r"))
          setCommand("");
      }}
    >
      <input
        type="text"
        aria-label="Type command"
        placeholder="Type command…"
        className="min-w-0 flex-1 rounded-md border border-stone-300 bg-white px-2 py-1 text-base text-stone-900 outline-none focus:border-sky-500"
        value={command}
        onChange={(event) => setCommand(event.target.value)}
        maxLength={8191}
        autoComplete="off"
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        enterKeyHint="send"
        onKeyDown={(event) => {
          if (
            event.key === "Enter" &&
            (event.nativeEvent.isComposing || event.keyCode === 229)
          )
            event.preventDefault();
        }}
      />
      <button
        type="submit"
        className="btn btn-light shrink-0"
        aria-label="Send command"
        disabled={!active || status !== "Đã kết nối" || !command.trim()}
      >
        Send
      </button>
      <DropdownMenu>
        <DropdownMenuTrigger
          type="button"
          className="btn btn-light shrink-0"
          aria-label="Phím đặc biệt terminal"
          title="Phím đặc biệt terminal"
          disabled={!active || status !== "Đã kết nối"}
        >
          <MoreHorizontal size={16} aria-hidden="true" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          {terminalKeys.map(({ label, description, data }) => (
            <DropdownMenuItem
              key={label}
              className="min-h-10 justify-between gap-4"
              disabled={!active || status !== "Đã kết nối"}
              onClick={() => {
                if (active && status === "Đã kết nối") write.current(data);
              }}
            >
              <span className="font-mono">{label}</span>
              <span className="text-xs text-muted-foreground">
                {description}
              </span>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </form>
  );
  return (
    <section
      aria-label="Remote terminal"
      className={docked ? "flex h-full min-h-0 flex-col" : undefined}
    >
      {!docked && (
        <header className="mb-2 flex flex-wrap items-center gap-2 text-xs">
          <b>Terminal</b>
          <button
            className="btn btn-light"
            aria-label="Kết nối lại terminal"
            title="Kết nối lại terminal"
            onClick={() => setAttempt((n) => n + 1)}
          >
            <RotateCw size={15} aria-hidden="true" />
          </button>
          {commandBox}
        </header>
      )}
      {docked && commandTarget && createPortal(commandBox, commandTarget)}
      {status !== "Đang kết nối…" && status !== "Đã kết nối" && (
        <p role="alert" className="mb-2 text-xs text-red-700">
          {status}
        </p>
      )}
      <div
        className={
          docked
            ? "relative flex min-h-0 flex-1 overflow-hidden rounded-lg bg-[#0c0a09]"
            : "relative flex h-[50vh] min-h-72 overflow-hidden rounded-lg bg-[#0c0a09]"
        }
      >
        <div
          ref={host}
          data-testid="remote-terminal"
          data-session-id={session}
          data-connected={status === "Đã kết nối"}
          className="remote-terminal-content min-h-0 min-w-0 flex-1 overflow-hidden rounded-lg bg-[#0c0a09] p-2"
          onTouchStart={(event) => {
            if (event.touches.length !== 1 || !terminal.current) {
              touch.current = null;
              return;
            }
            touch.current = {
              y: event.touches[0].clientY,
              top: terminal.current.buffer.active.viewportY,
              scrolling: false,
            };
          }}
          onTouchMove={(event) => {
            const start = touch.current;
            const term = terminal.current;
            if (
              !start ||
              !term ||
              event.touches.length !== 1 ||
              !term.buffer.active.baseY
            )
              return;
            const delta = start.y - event.touches[0].clientY;
            if (!start.scrolling && Math.abs(delta) < 6) return;
            start.scrolling = true;
            const lineHeight =
              (term.element?.querySelector(".xterm-screen")?.clientHeight ||
                event.currentTarget.clientHeight) / term.rows;
            term.scrollToLine(
              Math.max(
                0,
                Math.min(
                  term.buffer.active.baseY,
                  Math.round(start.top + delta / lineHeight),
                ),
              ),
            );
          }}
          onTouchEnd={() => {
            touch.current = null;
          }}
          onTouchCancel={() => {
            touch.current = null;
          }}
        />
        <div className="absolute inset-y-2 right-0 z-10 flex w-6 items-stretch justify-center">
          <input
            type="range"
            className="terminal-scrollbar"
            aria-label="Cuộn lịch sử terminal"
            aria-valuetext={`${scroll.top} / ${scroll.max}`}
            min={0}
            max={Math.max(1, scroll.max)}
            step={1}
            value={scroll.top}
            disabled={!scroll.max}
            onChange={(event) =>
              terminal.current?.scrollToLine(Number(event.target.value))
            }
          />
        </div>
      </div>
    </section>
  );
}
