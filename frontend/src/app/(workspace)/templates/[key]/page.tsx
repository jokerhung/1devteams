"use client";

import { useParams, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { Agent } from "@/lib/types";
import type { WorkflowGraph } from "@/components/workflow/serialize";
import { TemplateEditor } from "@/components/workflow/TemplateEditor";

export default function TemplatePage() {
  const { key } = useParams<{ key: string }>();
  const search = useSearchParams();
  const templates = useQuery({
    queryKey: ["workflow-templates"],
    queryFn: () =>
      apiFetch<{ id: string; name: string; graph: WorkflowGraph }[]>(
        "/workflow-templates",
      ),
  });
  const agents = useQuery({
    queryKey: ["agents"],
    queryFn: () => apiFetch<Agent[]>("/agents"),
  });
  if (templates.error || agents.error)
    return (
      <p role="alert" className="error">
        {templates.error?.message || agents.error?.message}
      </p>
    );
  if (!templates.data || !agents.data)
    return <p role="status">Đang tải template…</p>;
  const template = templates.data.find((t) => t.id === key && t.id !== "blank");
  if (!template) return <p role="alert">Không tìm thấy template.</p>;
  return (
    <TemplateEditor
      key={key}
      template={template}
      agents={agents.data}
      editable={search.get("edit") === "1"}
    />
  );
}
