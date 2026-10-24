"use client";
import { useRef, useState, type ReactNode } from "react";
import dynamic from "next/dynamic";
import { PanelBottom, PanelLeft, X } from "lucide-react";

const RemoteTerminal = dynamic(() => import("./RemoteTerminal"), {
  ssr: false,
});

export function TerminalDock({
  projectId,
  open,
  created,
  onClose,
  children,
}: {
  projectId: string;
  open: boolean;
  created: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const [side, setSide] = useState<"left" | "bottom">("bottom");
  const [sizes, setSizes] = useState({ left: 40, bottom: 45 });
  const container = useRef<HTMLDivElement>(null);
  const drag = useRef<number | null>(null);
  const clamp = (value: number) => Math.min(70, Math.max(25, value));
  return (
    <div
      ref={container}
      className={`flex min-h-0 min-w-0 flex-1 overflow-hidden ${side === "left" ? "flex-row" : "flex-col"}`}
    >
      <section
        id="ticket-terminal-panel"
        aria-label="Bảng terminal"
        hidden={!open}
        style={{ flexBasis: `${sizes[side]}%` }}
        className={`min-h-0 min-w-0 shrink-0 overflow-hidden bg-stone-50 ${open ? "flex flex-col" : "hidden"} ${side === "bottom" ? "order-2" : ""}`}
      >
        <header className="flex shrink-0 items-center justify-between gap-2 border-b border-stone-200 px-3 py-2 text-xs">
          <b>Terminal</b>
          <div className="flex gap-1">
            <button
              className="btn btn-light"
              aria-label="Đặt terminal bên trái"
              title="Đặt bên trái"
              aria-pressed={side === "left"}
              onClick={() => setSide("left")}
            >
              <PanelLeft size={15} />
            </button>
            <button
              className="btn btn-light"
              aria-label="Đặt terminal bên dưới"
              title="Đặt bên dưới"
              aria-pressed={side === "bottom"}
              onClick={() => setSide("bottom")}
            >
              <PanelBottom size={15} />
            </button>
            <button
              className="btn btn-light"
              aria-label="Đóng terminal"
              onClick={onClose}
            >
              <X size={15} />
            </button>
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-auto p-2">
          {created && <RemoteTerminal projectId={projectId} docked />}
        </div>
      </section>
      {open && (
        <div
          role="separator"
          aria-label="Đổi kích thước terminal"
          aria-orientation={side === "left" ? "vertical" : "horizontal"}
          aria-valuenow={Math.round(sizes[side])}
          aria-valuemin={25}
          aria-valuemax={70}
          tabIndex={0}
          className={`shrink-0 touch-none bg-stone-200 hover:bg-sky-400 focus:bg-sky-400 ${side === "left" ? "w-1 cursor-col-resize" : "order-1 h-1 cursor-row-resize"}`}
          onPointerDown={(event) => {
            drag.current = event.pointerId;
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerUp={(event) => {
            drag.current = null;
            event.currentTarget.releasePointerCapture(event.pointerId);
          }}
          onPointerCancel={() => {
            drag.current = null;
          }}
          onPointerMove={(event) => {
            if (drag.current !== event.pointerId || !container.current) return;
            const box = container.current.getBoundingClientRect();
            const value =
              side === "left"
                ? ((event.clientX - box.left) / box.width) * 100
                : ((box.bottom - event.clientY) / box.height) * 100;
            setSizes((previous) => ({ ...previous, [side]: clamp(value) }));
          }}
          onKeyDown={(event) => {
            const delta =
              side === "left"
                ? ({ ArrowLeft: -5, ArrowRight: 5 } as Record<string, number>)[
                    event.key
                  ]
                : ({ ArrowUp: 5, ArrowDown: -5 } as Record<string, number>)[
                    event.key
                  ];
            if (delta) {
              event.preventDefault();
              setSizes((previous) => ({
                ...previous,
                [side]: clamp(previous[side] + delta),
              }));
            }
          }}
        />
      )}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        {children}
      </div>
    </div>
  );
}
