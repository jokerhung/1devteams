"use client";
import { useState } from "react";
import type { Agent } from "@/lib/types";
import { Modal } from "@/components/ui-app/primitives";
import { WorkflowReadonlyGraph } from "@/components/workflow/WorkflowReadonlyGraph";
import type { WorkflowGraph } from "@/components/workflow/serialize";
import type { MessageGroup, RuntimeState } from "./types";
export function RightDrawer({
  graph,
  version,
  agents,
  groups,
  statuses,
  onClose,
}: {
  graph: WorkflowGraph;
  version: number;
  agents: Agent[];
  groups: MessageGroup[];
  statuses: RuntimeState["node_statuses"];
  onClose: () => void;
}) {
  const [tab, setTab] = useState("progress");
  return (
    <Modal title={`Tiến độ workflow v${version}`} wide onClose={onClose}>
      <div className="mb-3 flex gap-2">
        <button
          className="btn btn-light"
          aria-pressed={tab === "progress"}
          onClick={() => setTab("progress")}
        >
          Tiến độ
        </button>
        <button
          className="btn btn-light"
          aria-pressed={tab === "terminal"}
          onClick={() => setTab("terminal")}
        >
          Terminal
        </button>
      </div>
      {tab === "progress" ? (
        <>
          <WorkflowReadonlyGraph
            graph={graph}
            agents={agents}
            nodeStatuses={statuses}
          />
          <ol className="max-h-48 overflow-auto text-xs">
            {groups
              .filter((g) => g.type === "turn")
              .map((g) => (
                <li key={g.id} className="border-b border-stone-100 py-2">
                  {g.agent} · {g.nodeId} ·{" "}
                  {g.endedAt
                    ? `${((Date.parse(g.endedAt) - Date.parse(g.at)) / 1000).toFixed(1)}s`
                    : "Đang chạy"}
                </li>
              ))}
          </ol>
        </>
      ) : (
        <p className="py-10 text-center text-xs text-stone-500">
          Terminal tương tác sẽ có ở Phase 7. Output hiện tại nằm trong từng
          lượt agent.
        </p>
      )}
    </Modal>
  );
}
