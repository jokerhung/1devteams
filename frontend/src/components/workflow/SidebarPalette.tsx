"use client";
import type { Agent } from "@/lib/types";
import { Logo } from "@/components/ui-app/primitives";
import { nodeIcons, nodeTitles } from "./nodes/BaseNode";
import type { NodeKind } from "./serialize";
export type PaletteItem = { type: NodeKind; agent_id?: string };
export function SidebarPalette({
  agents,
  onAdd,
  disabled,
  agentLabel = "Agent trong project",
}: {
  agents: Agent[];
  onAdd: (item: PaletteItem) => void;
  disabled?: boolean;
  agentLabel?: string;
}) {
  const item = (payload: PaletteItem, title: string, icon: React.ReactNode) => (
    <button
      key={payload.agent_id || payload.type}
      type="button"
      disabled={disabled}
      draggable={!disabled}
      onDragStart={(e) => {
        e.dataTransfer.setData(
          "application/aiteams-node",
          JSON.stringify(payload),
        );
        e.dataTransfer.effectAllowed = "move";
      }}
      onClick={() => onAdd(payload)}
      className="flex w-full cursor-grab items-center gap-2 rounded-lg border border-stone-200 bg-white p-2 text-left text-xs hover:border-stone-400 disabled:opacity-50"
      aria-label={`Thêm ${title}`}
      title="Kéo vào canvas hoặc bấm để thêm"
    >
      {icon}
      <span className="truncate">{title}</span>
    </button>
  );
  return (
    <aside
      aria-label="Khối workflow"
      className="w-52 shrink-0 space-y-2 overflow-y-auto border-r border-stone-200 bg-stone-50/70 p-3 max-xl:w-40"
    >
      <h2 className="mb-3 text-[10px] font-bold text-stone-500">
        KHỐI ĐIỀU KHIỂN
      </h2>
      {(
        [
          "start",
          "condition",
          "human_input",
          "human_confirm",
          "git_release",
          "end",
        ] as NodeKind[]
      ).map((type) =>
        item({ type }, nodeTitles[type], <span>{nodeIcons[type]}</span>),
      )}
      <h2 className="pt-5 pb-2 text-[10px] font-bold text-stone-500">
        {agentLabel}
      </h2>
      {agents
        .filter((a) => a.is_active)
        .map((a) =>
          item(
            {
              type: a.permission_profile.can_git_release
                ? "git_release"
                : "agent",
              agent_id: a.id,
            },
            a.handle,
            <Logo entity={a} size={22} />,
          ),
        )}
      {!agents.length && (
        <p className="text-xs text-amber-700">
          Thêm AI Team hoặc agent vào project để sử dụng.
        </p>
      )}
      <p className="pt-3 text-[10px] text-stone-400">
        Delete xoá · Ctrl+D nhân bản · Ctrl+Z/Y hoàn tác · Ctrl+S lưu
      </p>
    </aside>
  );
}
