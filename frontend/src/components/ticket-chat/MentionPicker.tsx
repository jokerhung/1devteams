"use client";
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import type { Agent } from "@/lib/types";
import { Logo } from "@/components/ui-app/primitives";
import { useChatPrefs } from "@/stores/chat-prefs";
export function MentionPicker({
  agents,
  open,
  onOpen,
  onPick,
  disabled,
}: {
  agents: Agent[];
  open: boolean;
  onOpen: (open: boolean) => void;
  onPick: (agent: Agent) => void;
  disabled: boolean;
}) {
  const prefs = useChatPrefs();
  const root = useRef<HTMLDivElement>(null);
  const current = agents.find((a) => a.id === prefs.agentId);
  useEffect(() => {
    if (!open) return;
    const click = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) onOpen(false);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onOpen(false);
    };
    document.addEventListener("mousedown", click);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", click);
      document.removeEventListener("keydown", key);
    };
  }, [open, onOpen]);
  return (
    <div className="relative" ref={root}>
      <button
        type="button"
        className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-stone-600 hover:bg-stone-100"
        aria-label="Chọn agent mặc định"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => onOpen(!open)}
      >
        {current ? (
          <>
            <Logo entity={current} size={18} />
            {current.handle} ⌃
          </>
        ) : (
          "@ Chọn agent"
        )}
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Gửi tới agent"
          className="absolute bottom-full left-0 z-30 mb-2 w-72 rounded-xl border border-stone-200 bg-white p-2 shadow-xl"
        >
          <p className="p-2 text-xs font-semibold">
            Gửi tới agent (lưu làm mặc định)
          </p>
          <div className="max-h-64 overflow-y-auto">
            {agents.map((a) => (
              <button
                type="button"
                key={a.id}
                className="flex w-full items-center gap-2 rounded-lg p-2 text-left text-xs hover:bg-stone-50"
                onClick={async () => {
                  try {
                    await prefs.choose(a.id);
                    onPick(a);
                    onOpen(false);
                    toast.success(
                      `Mặc định gửi tới ${a.handle} cho các chat tiếp theo`,
                    );
                  } catch (e) {
                    toast.error((e as Error).message);
                  }
                }}
              >
                <Logo entity={a} size={24} />
                <span className="flex-1">
                  <b className="font-mono">{a.handle}</b>
                  <span className="block text-stone-400">{a.display_name}</span>
                </span>
                {a.id === current?.id && "✓"}
              </button>
            ))}
          </div>
          {current && (
            <button
              type="button"
              className="w-full border-t border-stone-100 p-2 text-left text-xs"
              onClick={async () => {
                try {
                  await prefs.choose(null);
                  onOpen(false);
                } catch (e) {
                  toast.error((e as Error).message);
                }
              }}
            >
              Bỏ mặc định
            </button>
          )}
        </div>
      )}
    </div>
  );
}
