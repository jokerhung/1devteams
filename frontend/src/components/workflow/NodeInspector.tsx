"use client";
import type { Agent } from "@/lib/types";
import type { FlowNode } from "./serialize";
import { nodeTitles, outputHandles } from "./nodes/BaseNode";
export function NodeInspector({
  node,
  nodes,
  agents,
  disabled,
  onChange,
  onDelete,
  onEditAgent,
}: {
  node?: FlowNode;
  nodes: FlowNode[];
  agents: Agent[];
  disabled?: boolean;
  onChange: (data: Record<string, unknown>) => void;
  onDelete: () => void;
  onEditAgent: (agent: Agent) => void;
}) {
  const data = node?.data || {};
  const expression = String(data.expression || "len(modified_files) > 0");
  const match =
    /^(last_route\.[\w-]+|iteration\.[\w-]+|len\(modified_files\))\s*(==|!=|>=|<=|>|<)\s*(.*)$/.exec(
      expression,
    );
  const variable = match?.[1] || "len(modified_files)",
    operator = match?.[2] || ">",
    right = match?.[3]?.replace(/^"|"$/g, "") || "0";
  const condition = (v: string, op: string, value: string) =>
    onChange({
      expression: `${v} ${op} ${v.startsWith("last_route.") ? JSON.stringify(value.replaceAll('"', "").replaceAll("\n", "")) : String(Math.max(0, Math.floor(Number(value) || 0)))}`,
    });
  const agent = agents.find((a) => a.id === data.agent_id);
  const field = (key: string, title: string, textarea = false) => (
    <label className="field">
      {title}
      {textarea ? (
        <textarea
          value={String(data[key] || "")}
          onChange={(e) => onChange({ [key]: e.target.value })}
        />
      ) : (
        <input
          value={String(data[key] || "")}
          onChange={(e) => onChange({ [key]: e.target.value })}
        />
      )}
    </label>
  );
  return (
    <aside
      aria-label="Cấu hình node"
      className="w-72 shrink-0 overflow-y-auto border-l border-stone-200 bg-white p-4 max-xl:w-60"
    >
      <h2 className="mb-4 text-xs font-bold">Cấu hình node</h2>
      {node ? (
        <fieldset disabled={disabled} className="space-y-4">
          <p className="font-mono text-[10px] text-stone-400">
            {node.id} · {nodeTitles[node.type!]}
          </p>
          {field("label", "Tên bước")}
          {["agent", "git_release"].includes(node.type!) && (
            <>
              <label className="field">
                Agent
                <select
                  value={String(data.agent_id || "")}
                  onChange={(e) =>
                    onChange({ agent_id: e.target.value || null })
                  }
                >
                  <option value="">Chọn agent</option>
                  {agents
                    .filter(
                      (a) =>
                        a.is_active &&
                        (node.type !== "git_release" ||
                          a.permission_profile.can_git_release),
                    )
                    .map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.handle} — {a.display_name}
                      </option>
                    ))}
                </select>
              </label>
              {agent && (
                <button
                  type="button"
                  className="text-xs underline"
                  onClick={() => onEditAgent(agent)}
                >
                  Sửa agent {agent.handle}
                </button>
              )}
            </>
          )}
          {node.type === "agent" && (
            <>
              <label className="field">
                Routing
                <select
                  value={String(data.routing || "none")}
                  onChange={(e) => onChange({ routing: e.target.value })}
                >
                  {["none", "ba", "tester", "review"].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </label>
              {field("instructions", "Hướng dẫn bổ sung cho bước này", true)}
              <label className="field">
                Giới hạn vòng lặp
                <input
                  type="number"
                  min={1}
                  max={1000}
                  placeholder="Theo MAX_NODE_ITERATIONS"
                  value={
                    data.max_iterations == null
                      ? ""
                      : Number(data.max_iterations)
                  }
                  onChange={(e) =>
                    onChange({
                      max_iterations: e.target.value
                        ? Number(e.target.value)
                        : undefined,
                    })
                  }
                />
              </label>
              <label className="flex gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={!!data.requires_write}
                  onChange={(e) =>
                    onChange({ requires_write: e.target.checked })
                  }
                />
                Bước cần sửa file
              </label>
              <label className="flex gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={!!data.requires_terminal}
                  onChange={(e) =>
                    onChange({ requires_terminal: e.target.checked })
                  }
                />
                Bước cần terminal
              </label>
            </>
          )}
          {node.type === "human_confirm" && (
            <>
              {field("message", "Nội dung xác nhận", true)}
              {field("approved_label", "Nhãn đồng ý")}
              {field("rejected_label", "Nhãn từ chối")}
            </>
          )}
          {node.type === "human_input" && (
            <>
              {field("placeholder", "Gợi ý trong ô chat", true)}
              {field("question", "Câu hỏi cho người dùng", true)}
            </>
          )}
          {node.type === "git_release" && (
            <label className="flex gap-2 text-xs">
              <input
                type="checkbox"
                checked={data.push !== false}
                onChange={(e) => onChange({ push: e.target.checked })}
              />
              Push sau commit (tắt = chỉ commit local)
            </label>
          )}
          {node.type === "condition" && (
            <>
              <label className="field">
                Biến
                <select
                  value={variable}
                  onChange={(e) =>
                    condition(
                      e.target.value,
                      operator,
                      e.target.value.startsWith("last_route.") ? "pass" : "0",
                    )
                  }
                >
                  <option value="len(modified_files)">Số file thay đổi</option>
                  {nodes
                    .filter((n) => n.type === "agent")
                    .flatMap((n) => [
                      <option key={`r${n.id}`} value={`last_route.${n.id}`}>
                        Kết quả {n.id}
                      </option>,
                      <option key={`i${n.id}`} value={`iteration.${n.id}`}>
                        Số lượt {n.id}
                      </option>,
                    ])}
                </select>
              </label>
              <label className="field">
                Toán tử
                <select
                  value={operator}
                  onChange={(e) => condition(variable, e.target.value, right)}
                >
                  {["==", "!=", ">", ">=", "<", "<="].map((op) => (
                    <option key={op}>{op}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                Giá trị
                <input
                  value={right}
                  type={variable.startsWith("last_route.") ? "text" : "number"}
                  min={0}
                  onChange={(e) =>
                    condition(variable, operator, e.target.value)
                  }
                />
              </label>
              <p className="break-all font-mono text-[10px]">{expression}</p>
            </>
          )}
          <p className="text-[10px] text-stone-500">
            Nhánh ra: {outputHandles(node.type!, data).join(", ") || "Không có"}
            . Đổi routing có thể cần nối lại dây.
          </p>
          <button
            type="button"
            className="btn btn-light text-red-700"
            onClick={onDelete}
          >
            Xoá node
          </button>
        </fieldset>
      ) : (
        <p className="text-xs text-stone-500">
          Chọn một node để chỉnh sửa. Kéo khối từ bảng trái hoặc bấm để thêm vào
          canvas.
        </p>
      )}
    </aside>
  );
}
