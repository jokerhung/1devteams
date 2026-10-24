"use client";
import { useRef, useState, type ReactNode } from "react";
import dynamic from "next/dynamic";
import {
  PanelsTopLeft,
  PanelBottom,
  PanelLeft,
  PanelRight,
  RotateCw,
  X,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
} from "@/components/ui/dropdown-menu";

type DockSide = "left" | "right" | "bottom";

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
  const [side, setSide] = useState<DockSide>("bottom");
  const [locationOpen, setLocationOpen] = useState(false);
  const [sizes, setSizes] = useState({ left: 40, right: 40, bottom: 45 });
  const [reconnectKey, setReconnectKey] = useState(0);
  const [commandTarget, setCommandTarget] = useState<HTMLDivElement | null>(
    null,
  );
  const container = useRef<HTMLDivElement>(null);
  const drag = useRef<number | null>(null);
  const clamp = (value: number) => Math.min(70, Math.max(25, value));
  return (
    <div
      ref={container}
      className={`flex min-h-0 min-w-0 flex-1 overflow-hidden ${side === "bottom" ? "flex-col" : "flex-row"}`}
    >
      <section
        id="ticket-terminal-panel"
        aria-label="Bảng terminal"
        hidden={!open}
        style={{ flexBasis: `${sizes[side]}%` }}
        className={`min-h-0 min-w-0 shrink-0 overflow-hidden bg-stone-50 ${open ? "flex flex-col" : "hidden"} ${side === "left" ? "order-0" : "order-2"}`}
      >
        <header className="flex shrink-0 flex-wrap items-center gap-2 border-b border-stone-200 px-3 py-2 text-xs">
          <div className="flex items-center gap-2">
            <b>Terminal</b>
            <button
              className="btn btn-light"
              aria-label="Kết nối lại terminal"
              title="Kết nối lại terminal"
              onClick={() => setReconnectKey((key) => key + 1)}
            >
              <RotateCw size={15} aria-hidden="true" />
            </button>
          </div>
          <div ref={setCommandTarget} className="min-w-[120px] flex-1" />
          <div className="ml-auto flex shrink-0 gap-1">
            <DropdownMenu open={locationOpen} onOpenChange={setLocationOpen}>
              <DropdownMenuTrigger
                type="button"
                className="btn btn-light"
                aria-label="Vị trí terminal"
                title="Vị trí terminal"
              >
                <PanelsTopLeft size={15} aria-hidden="true" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44">
                <DropdownMenuRadioGroup
                  value={side}
                  onValueChange={(value) => {
                    setSide(value as DockSide);
                    setLocationOpen(false);
                  }}
                >
                  <DropdownMenuRadioItem value="left" className="min-h-10">
                    <PanelLeft size={15} aria-hidden="true" /> Bên trái
                  </DropdownMenuRadioItem>
                  <DropdownMenuRadioItem value="right" className="min-h-10">
                    <PanelRight size={15} aria-hidden="true" /> Bên phải
                  </DropdownMenuRadioItem>
                  <DropdownMenuRadioItem value="bottom" className="min-h-10">
                    <PanelBottom size={15} aria-hidden="true" /> Phía dưới
                  </DropdownMenuRadioItem>
                </DropdownMenuRadioGroup>
              </DropdownMenuContent>
            </DropdownMenu>
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
          {created && (
            <RemoteTerminal
              projectId={projectId}
              docked
              reconnectKey={reconnectKey}
              active={open}
              commandTarget={commandTarget}
            />
          )}
        </div>
      </section>
      {open && (
        <div
          role="separator"
          aria-label="Đổi kích thước terminal"
          aria-orientation={side === "bottom" ? "horizontal" : "vertical"}
          aria-valuenow={Math.round(sizes[side])}
          aria-valuemin={25}
          aria-valuemax={70}
          tabIndex={0}
          className={`order-1 shrink-0 touch-none bg-stone-200 hover:bg-sky-400 focus:bg-sky-400 ${side === "bottom" ? "h-1 cursor-row-resize" : "w-1 cursor-col-resize"}`}
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
                : side === "right"
                  ? ((box.right - event.clientX) / box.width) * 100
                  : ((box.bottom - event.clientY) / box.height) * 100;
            setSizes((previous) => ({ ...previous, [side]: clamp(value) }));
          }}
          onKeyDown={(event) => {
            const delta =
              side === "left"
                ? ({ ArrowLeft: -5, ArrowRight: 5 } as Record<string, number>)[
                    event.key
                  ]
                : side === "right"
                  ? (
                      { ArrowLeft: 5, ArrowRight: -5 } as Record<string, number>
                    )[event.key]
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
      <div
        className={`flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden ${side === "left" ? "order-2" : "order-0"}`}
      >
        {children}
      </div>
    </div>
  );
}
