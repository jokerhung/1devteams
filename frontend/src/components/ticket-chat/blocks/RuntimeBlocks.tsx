import type { ChatEvent } from "../types";
export function ThinkingBlock({
  text,
  running,
}: {
  text: string;
  running: boolean;
}) {
  return text ? (
    <details className="my-2 text-xs text-stone-500">
      <summary className={`cursor-pointer ${running ? "animate-pulse" : ""}`}>
        {running ? "Đang suy nghĩ…" : "Suy nghĩ"}
      </summary>
      <p className="mt-2 whitespace-pre-wrap">{text}</p>
    </details>
  ) : null;
}
export function ToolCallChips({ tools }: { tools: ChatEvent[] }) {
  return (
    <div className="my-2 flex flex-wrap gap-1">
      {tools.map((e) => (
        <span
          key={e.id}
          className={`rounded-md border px-2 py-1 text-[11px] ${e.metadata.status === "failed" ? "border-red-200 text-red-700" : "border-stone-200 text-stone-500"}`}
        >
          {e.metadata.status === "completed"
            ? "✓"
            : e.metadata.status === "failed"
              ? "✕"
              : "◌"}{" "}
          {String(e.metadata.title || e.metadata.kind || e.content || "Tool")}
        </span>
      ))}
    </div>
  );
}
export function TerminalBlock({ event }: { event: ChatEvent }) {
  return (
    <details className="my-2 overflow-hidden rounded-lg bg-stone-950 p-3 font-mono text-[11px] text-stone-100">
      <summary className="cursor-pointer">
        $ {String(event.metadata.command || "Terminal")}{" "}
        {event.metadata.exit_code != null &&
          `· exit ${event.metadata.exit_code}`}
      </summary>
      <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap">
        {event.content}
      </pre>
    </details>
  );
}
export function PermissionLog({
  event,
  agent,
}: {
  event: ChatEvent;
  agent: string;
}) {
  return (
    <p className="my-2 text-xs text-red-700">
      Guard: Đã chặn{" "}
      {String(event.metadata.action || event.metadata.command || "tool")} của{" "}
      {agent} — {String(event.metadata.reason || event.content)}
    </p>
  );
}
export function PlanBlock({ event }: { event: ChatEvent }) {
  const entries = event.metadata.entries as
    { content?: string; status?: string }[] | undefined;
  return (
    <details className="my-2 text-xs">
      <summary className="cursor-pointer text-stone-500">Kế hoạch</summary>
      {entries ? (
        <ul>
          {entries.map((p, i) => (
            <li key={i}>
              {p.status === "completed" ? "✓" : "◌"} {p.content}
            </li>
          ))}
        </ul>
      ) : (
        <p className="whitespace-pre-wrap">
          {event.content || JSON.stringify(event.metadata)}
        </p>
      )}
    </details>
  );
}
