"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Eye, Pencil, Plus } from "lucide-react";
import { apiFetch } from "@/lib/api";
import type { WorkflowGraph } from "@/components/workflow/serialize";
import { TemplateCard } from "@/components/workflow/TemplateCard";
import { CreateWorkflowTemplateDialog } from "@/components/workflow/CreateWorkflowTemplateDialog";

export default function TemplatesPage() {
  const [creating, setCreating] = useState(false);
  const templates = useQuery({
    queryKey: ["workflow-templates"],
    queryFn: () =>
      apiFetch<
        {
          id: string;
          name: string;
          description?: string;
          builtin?: boolean;
          graph: WorkflowGraph;
        }[]
      >("/workflow-templates"),
  });
  return (
    <div className="space-y-5">
      <div className="flex min-h-9 flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-stone-500">
          Thiết kế luồng xử lý bằng các bước và kết nối giữa agent.
        </p>
        <button
          className="btn btn-dark"
          disabled={!templates.data}
          onClick={() => setCreating(true)}
        >
          <Plus size={14} /> Tạo template
        </button>
      </div>
      {templates.isPending && <p role="status">Đang tải template…</p>}
      {templates.error && (
        <p role="alert" className="error">
          {templates.error.message}
        </p>
      )}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {templates.data
          ?.filter((t) => t.id !== "blank")
          .map((template) => (
            <TemplateCard
              key={template.id}
              name={template.name}
              kind="Workflow"
              builtin={template.builtin !== false}
              description={
                template.description ||
                (template.builtin === false
                  ? "Template Workflow do bạn tạo."
                  : template.id === "add_feature"
                    ? "Phân tích yêu cầu, thiết kế, lập kế hoạch, triển khai và system test. User xác nhận trước khi DevOps phát hành."
                    : "Phân tích lỗi, sửa code, kiểm thử và xác nhận trước khi phát hành.")
              }
              summary={
                <>
                  {
                    template.graph.nodes?.filter((n) =>
                      ["agent", "git_release"].includes(n.type),
                    ).length
                  }{" "}
                  bước agent · {(template.graph.nodes || []).length} node
                </>
              }
            >
              <Link
                className="btn btn-light gap-2"
                href={`/templates/${template.id}`}
              >
                <Eye size={14} />
                Xem
              </Link>
              <Link
                className="btn btn-dark gap-2"
                href={`/templates/${template.id}?edit=1`}
              >
                <Pencil size={14} />
                Sửa
              </Link>
            </TemplateCard>
          ))}
      </div>
      {creating && templates.data && (
        <CreateWorkflowTemplateDialog
          templates={templates.data}
          onClose={() => setCreating(false)}
        />
      )}
    </div>
  );
}
