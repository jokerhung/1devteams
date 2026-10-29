import type { Agent } from "@/lib/types";
import { apiFetch } from "@/lib/api";
import { deserialize, type WorkflowGraph, type NodeKind } from "./serialize";
import { autoLayout } from "./layout";
import { serialize } from "./serialize";
export const templateOptions = [
  { id: "blank", name: "Trống" },
  { id: "bugfix_default", name: "Fix Bug mặc định" },
  { id: "add_feature", name: "Add feature" },
  { id: "bugfix_with_security_review", name: "Fix Bug + Security Review" },
] as const;
export type TemplateId =
  (typeof templateOptions)[number]["id"] | `wf_${string}`;
export function roleAgent(agents: Agent[], role: string) {
  return agents.find(
    (a) =>
      a.is_active &&
      (a.role_key === role ||
        (role === "SECURITY" && a.handle === "@security_checker")),
  );
}
export function missingRoles(template: TemplateId, agents: Agent[]) {
  if (template.startsWith("wf_")) return [];
  return (
    template === "blank"
      ? []
      : [
          "BA",
          "DEVELOPER",
          "TESTER",
          "LEADER",
          ...(template === "add_feature"
            ? ["COORDINATOR", "DESIGNER", "PLANNER"]
            : []),
          ...(template === "bugfix_with_security_review" ? ["SECURITY"] : []),
        ]
  ).filter((role) => !roleAgent(agents, role));
}
export async function loadTemplateGraph(
  template: TemplateId,
  projectId: string,
): Promise<WorkflowGraph> {
  const templates = await apiFetch<{ id: string; graph: WorkflowGraph }[]>(
    `/workflow-templates?project_id=${projectId}`,
  );
  const entry = templates.find((item) => item.id === template);
  if (!entry) throw new Error("Không tìm thấy template");
  return serialize(autoLayout(deserialize(entry.graph)));
}
export function templateGraph(
  template: TemplateId,
  agents: Agent[],
): WorkflowGraph {
  if (template === "add_feature" || template.startsWith("wf_")) {
    throw new Error(
      "Template này cần tải định nghĩa từ API bằng loadTemplateGraph",
    );
  }
  const specs: [string, NodeKind, Record<string, unknown>][] =
    template === "blank"
      ? [
          ["start", "start", {}],
          ["end", "end", {}],
        ]
      : [
          ["start", "start", {}],
          [
            "n_ba",
            "agent",
            { agent_id: roleAgent(agents, "BA")?.id || null, routing: "ba" },
          ],
          [
            "g_clar",
            "human_input",
            {
              label: "BA hỏi lại người dùng",
              placeholder: "Bổ sung các bước tái tạo lỗi…",
            },
          ],
          [
            "n_dev",
            "agent",
            {
              agent_id: roleAgent(agents, "DEVELOPER")?.id || null,
              routing: "none",
              requires_write: true,
            },
          ],
          ...(template === "bugfix_with_security_review"
            ? [
                [
                  "n_security",
                  "agent",
                  {
                    agent_id: roleAgent(agents, "SECURITY")?.id || null,
                    routing: "review",
                  },
                ] as [string, NodeKind, Record<string, unknown>],
              ]
            : []),
          [
            "n_test",
            "agent",
            {
              agent_id: roleAgent(agents, "TESTER")?.id || null,
              routing: "tester",
            },
          ],
          [
            "g_conf",
            "human_confirm",
            {
              message: "Bạn xác nhận lỗi đã được sửa xong?",
              approved_label: "Đồng ý",
              rejected_label: "Từ chối",
            },
          ],
          [
            "n_lead",
            "git_release",
            { agent_id: roleAgent(agents, "LEADER")?.id || null, push: true },
          ],
          ["end", "end", {}],
        ];
  const links: [string, string, string | null][] =
    template === "blank"
      ? [["start", "end", null]]
      : [
          ["start", "n_ba", null],
          ["n_ba", "g_clar", "need_info"],
          ["g_clar", "n_ba", null],
          ["n_ba", "n_dev", "ready"],
          [
            "n_dev",
            template === "bugfix_with_security_review"
              ? "n_security"
              : "n_test",
            null,
          ],
          ...(template === "bugfix_with_security_review"
            ? ([
                ["n_security", "n_test", "pass"],
                ["n_security", "n_dev", "fail"],
              ] as [string, string, string][])
            : []),
          ["n_test", "n_dev", "fail"],
          ["n_test", "g_conf", "pass"],
          ["g_conf", "n_lead", "approved"],
          ["g_conf", "n_dev", "rejected"],
          ["n_lead", "end", "success"],
        ];
  const graph: WorkflowGraph = {
    nodes: specs.map(([id, type, data]) => ({
      id,
      type,
      data,
      position: { x: 0, y: 0 },
    })),
    edges: links.map(([source, target, sourceHandle], i) => ({
      id: `e${i}`,
      source,
      target,
      sourceHandle,
    })),
    viewport: { x: 0, y: 0, zoom: 1 },
  };
  return serialize(autoLayout(deserialize(graph)));
}
