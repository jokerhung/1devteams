import type { Agent } from "@/lib/types";
import type { WorkflowGraph } from "./serialize";
export type ValidationIssue = { message: string; nodeId?: string };
function reachable(start: string, links: Map<string, string[]>) {
  const seen = new Set<string>();
  const pending = [start];
  while (pending.length) {
    const id = pending.pop()!;
    if (seen.has(id)) continue;
    seen.add(id);
    pending.push(...(links.get(id) || []));
  }
  return seen;
}
export function validateGraph(
  graph: WorkflowGraph,
  agents: Agent[],
): ValidationIssue[] {
  const errors: ValidationIssue[] = [];
  const add = (message: string, nodeId?: string) =>
    errors.push({
      message: nodeId ? `${nodeId}: ${message}` : message,
      nodeId,
    });
  const nodes = graph.nodes || [],
    edges = graph.edges || [];
  const byId = new Map(nodes.map((n) => [n.id, n]));
  if (byId.size !== nodes.length) add("ID node bị trùng");
  if (new Set(edges.map((e) => e.id)).size !== edges.length)
    add("ID cạnh bị trùng");
  const starts = nodes.filter((n) => n.type === "start"),
    ends = nodes.filter((n) => n.type === "end");
  if (starts.length !== 1 || !ends.length)
    add("Workflow cần đúng 1 start và ít nhất 1 end");
  const forward = new Map<string, string[]>(),
    backward = new Map<string, string[]>(),
    unsafe = new Map<string, string[]>();
  const handles = new Map<string, (string | null)[]>();
  const link = (map: Map<string, string[]>, from: string, to: string) =>
    map.set(from, [...(map.get(from) || []), to]);
  for (const edge of edges) {
    if (!byId.has(edge.source) || !byId.has(edge.target)) {
      add("Cạnh tham chiếu node không tồn tại");
      continue;
    }
    link(forward, edge.source, edge.target);
    link(backward, edge.target, edge.source);
    const handle =
      edge.sourceHandle === "default" ? null : edge.sourceHandle || null;
    handles.set(edge.source, [...(handles.get(edge.source) || []), handle]);
    if (!(
      byId.get(edge.source)?.type === "human_confirm" && handle === "approved"
    ))
      link(unsafe, edge.source, edge.target);
    if (edge.source === edge.target)
      add("Không nối node với chính nó", edge.source);
    if (byId.get(edge.target)?.type === "start")
      add("Start không có cạnh vào", edge.target);
  }
  if (starts.length === 1) {
    const reached = reachable(starts[0].id, forward);
    const toEnd = new Set(
      ends.flatMap((end) => [...reachable(end.id, backward)]),
    );
    nodes.forEach((n) => {
      if (!reached.has(n.id)) add("Không đi tới được từ start", n.id);
      if (!toEnd.has(n.id)) add("Không có đường tới end", n.id);
    });
  }
  for (const node of nodes) {
    const data = node.data || {},
      routing = data.routing || "none",
      actual = handles.get(node.id) || [];
    let required: (string | null)[] = [null];
    if (node.type === "end") required = [];
    if (node.type === "human_confirm") required = ["approved", "rejected"];
    if (node.type === "condition") {
      required = ["true", "false"];
      const expr = String(data.expression || "").trim();
      const match =
        /^(last_route\.([\w-]+)|iteration\.([\w-]+)|len\(modified_files\))\s*(==|!=|>=|<=|>|<)\s*("[^"\n]*"|\d+)$/.exec(
          expr,
        );
      if (
        !match ||
        match[1].startsWith("last_route.") !== match[5].startsWith('"')
      )
        add("expression không hợp lệ", node.id);
    }
    if (node.type === "agent") {
      if (routing === "ba") required = ["need_info", "ready"];
      else if (routing === "tester" || routing === "review")
        required = ["pass", "fail"];
      else if (routing !== "none") add("routing không hợp lệ", node.id);
    }
    if (node.type === "git_release")
      required = actual.length
        ? actual.every((h) => h === "success" || h === "failed")
          ? ["success"]
          : [null]
        : [];
    const permitted = [
      ...required,
      ...(node.type === "git_release" ? ["failed"] : []),
    ];
    if (
      required.some((h) => !actual.includes(h)) ||
      actual.some((h) => !permitted.includes(h)) ||
      new Set(actual).size !== actual.length
    )
      add(
        `Thiếu nhánh hoặc handle không hợp lệ (${required.map((h) => h || "default").join(", ")})`,
        node.id,
      );
    if (
      data.max_iterations != null &&
      (!Number.isInteger(data.max_iterations) ||
        Number(data.max_iterations) < 1 ||
        Number(data.max_iterations) > 1000)
    )
      add("Giới hạn vòng lặp phải là số nguyên dương", node.id);
    if (node.type === "agent" || node.type === "git_release") {
      const agent = agents.find((a) => a.id === data.agent_id && a.is_active);
      if (!agent) {
        add("Agent phải thuộc project và đang hoạt động", node.id);
        continue;
      }
      const write = data.requires_write || agent.role_key === "DEVELOPER",
        terminal = routing === "tester" || data.requires_terminal;
      if (
        agent.runtime === "openai-api" &&
        (node.type === "git_release" || write || terminal)
      )
        add(
          "OpenAI Custom chỉ trả lời văn bản, không sửa file / chạy test / phát hành Git",
          node.id,
        );
      if (write && !agent.permission_profile.allow_write)
        add("Node sửa file cần quyền ghi", node.id);
      if (terminal && !agent.permission_profile.allow_terminal)
        add("Tester cần quyền chạy terminal", node.id);
      if (node.type === "git_release") {
        if (!agent.permission_profile.can_git_release)
          add("Agent không có quyền phát hành Git", node.id);
        if (starts.length === 1 && reachable(starts[0].id, unsafe).has(node.id))
          add(
            "Mọi đường phát hành Git phải qua human_confirm nhánh approved",
            node.id,
          );
      }
    }
  }
  const remaining = new Set(
    nodes.filter((n) => n.type !== "agent").map((n) => n.id),
  );
  const degrees = new Map(
    [...remaining].map((id) => [
      id,
      (backward.get(id) || []).filter((s) => remaining.has(s)).length,
    ]),
  );
  const queue = [...degrees].filter(([, n]) => !n).map(([id]) => id);
  let processed = 0;
  while (queue.length) {
    const id = queue.shift()!;
    processed++;
    for (const target of forward.get(id) || []) {
      if (degrees.has(target)) {
        const value = degrees.get(target)! - 1;
        degrees.set(target, value);
        if (!value) queue.push(target);
      }
    }
  }
  if (processed !== remaining.size)
    add("Mỗi chu trình phải có ít nhất 1 agent node");
  return errors;
}
