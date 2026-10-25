"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Eye, Pencil, Workflow } from "lucide-react";
import { apiFetch } from "@/lib/api";
import type { WorkflowGraph } from "@/components/workflow/serialize";

export default function TemplatesPage() {
  const templates = useQuery({
    queryKey: ["workflow-templates"],
    queryFn: () =>
      apiFetch<{ id: string; name: string; graph: WorkflowGraph }[]>(
        "/workflow-templates",
      ),
  });
  return (
    <section className="mx-auto max-w-6xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Template</h1>
        <p className="mt-2 text-sm text-stone-500">
          Workflow mẫu để áp dụng cho các project.
        </p>
      </header>
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
            <article
              key={template.id}
              className="flex flex-col rounded-2xl border border-stone-200 bg-white p-5"
            >
              <Workflow
                size={24}
                className="mb-4 text-sky-600"
                aria-hidden="true"
              />
              <h2 className="font-semibold">{template.name}</h2>
              <p className="mt-2 flex-1 text-sm leading-6 text-stone-500">
                {template.id === "add_feature"
                  ? "Phân tích yêu cầu, thiết kế, lập kế hoạch, triển khai và system test. User xác nhận trước khi DevOps phát hành."
                  : "Phân tích lỗi, sửa code, kiểm thử và xác nhận trước khi phát hành."}
              </p>
              <p className="my-4 text-xs text-stone-400">
                {
                  template.graph.nodes?.filter((n) =>
                    ["agent", "git_release"].includes(n.type),
                  ).length
                }{" "}
                bước agent · {(template.graph.nodes || []).length} node
              </p>
              <div className="flex gap-2">
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
              </div>
            </article>
          ))}
      </div>
    </section>
  );
}
