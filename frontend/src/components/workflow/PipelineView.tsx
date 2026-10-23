"use client";
import type { Agent } from "@/lib/types";
import { PermissionBadges, Logo } from "@/components/ui-app/primitives";
import type { WorkflowGraph } from "./serialize";
import { nodeTitles, nodeIcons, handleLabels } from "./nodes/BaseNode";
export function mainPath(graph: WorkflowGraph) {
  const result: NonNullable<WorkflowGraph["nodes"]> = [],
    seen = new Set<string>();
  let node = graph.nodes?.find((n) => n.type === "start");
  const priority = ["ready", "pass", "approved", "success", "default", null];
  while (node && !seen.has(node.id)) {
    seen.add(node.id);
    result.push(node);
    const outgoing = (graph.edges || []).filter((e) => e.source === node!.id);
    const next =
      priority
        .map((h) => outgoing.find((e) => (e.sourceHandle || null) === h))
        .find(Boolean) || outgoing[0];
    node = graph.nodes?.find((n) => n.id === next?.target);
  }
  return result;
}
export function PipelineView({
  graph,
  agents,
  workspacePath,
}: {
  graph: WorkflowGraph;
  agents: Agent[];
  workspacePath: string;
}) {
  const route = mainPath(graph).filter(
    (n) => !["start", "end"].includes(n.type),
  );
  return (
    <section
      aria-label="Pipeline workflow"
      className="h-full overflow-y-auto bg-stone-50/50 p-6"
    >
      <p className="mb-6 text-xs leading-relaxed text-stone-500">
        Thư mục áp dụng: <code>{workspacePath}</code> — Chỉ agent có quyền phát
        hành Git mới được commit & push sau khi người dùng xác nhận.
      </p>
      <ol className="mx-auto max-w-3xl space-y-3">
        {route.map((node, i) => {
          const agent = agents.find((a) => a.id === node.data?.agent_id);
          const side = (graph.edges || []).filter(
            (e) =>
              e.source === node.id &&
              ["fail", "rejected", "need_info", "failed", "false"].includes(
                e.sourceHandle || "",
              ),
          );
          return (
            <li
              key={node.id}
              className="rounded-xl border border-stone-200 bg-white p-4"
            >
              <div className="flex items-center gap-3">
                <span className="flex size-7 items-center justify-center rounded-full bg-stone-100 text-xs font-bold">
                  {i + 1}
                </span>
                {agent ? (
                  <Logo entity={agent} size={28} />
                ) : (
                  <span>{nodeIcons[node.type]}</span>
                )}
                <h3 className="text-sm font-semibold">
                  {agent?.handle || nodeTitles[node.type]} —{" "}
                  {String(
                    node.data?.label ||
                      (node.type === "git_release"
                        ? "Review & Git Commit / Push"
                        : agent?.display_name || nodeTitles[node.type]),
                  )}
                </h3>
              </div>
              <p className="my-3 text-xs text-stone-500">
                {String(
                  node.data?.instructions ||
                    node.data?.message ||
                    node.data?.question ||
                    node.data?.expression ||
                    agent?.description ||
                    "",
                )}
              </p>
              {agent && <PermissionBadges profile={agent.permission_profile} />}
              {side.map((edge) => {
                const index = route.findIndex((n) => n.id === edge.target);
                return (
                  <p className="mt-2 text-[11px] text-amber-700" key={edge.id}>
                    ↺ {handleLabels[edge.sourceHandle!]}:{" "}
                    {index >= 0
                      ? `quay lại bước ${index + 1}`
                      : String(
                          graph.nodes?.find((n) => n.id === edge.target)?.data
                            ?.label || "chuyển sang nhánh phụ",
                        )}
                  </p>
                );
              })}
            </li>
          );
        })}
      </ol>
      {!route.length && (
        <p className="text-center text-xs text-stone-500">
          Chưa có bước thực hiện. Thêm agent vào canvas.
        </p>
      )}
    </section>
  );
}
