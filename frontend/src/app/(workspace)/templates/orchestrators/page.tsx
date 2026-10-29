"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Pencil, Plus } from "lucide-react";
import { apiFetch } from "@/lib/api";
import type { OrchestratorTemplate } from "@/lib/types";
import { ErrorState, Loading } from "@/components/ui-app/primitives";
import { TemplateCard } from "@/components/workflow/TemplateCard";

export default function OrchestratorTemplatesPage() {
  const templates = useQuery({
    queryKey: ["orchestrator-templates"],
    queryFn: () => apiFetch<OrchestratorTemplate[]>("/orchestrator-templates"),
  });
  return (
    <div className="space-y-5">
      <div className="flex min-h-9 flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-stone-500">
          Điều phối agent bằng instruction và vai trò của từng thành viên.
        </p>
        <Link className="btn btn-dark" href="/templates/orchestrators/new">
          <Plus size={14} /> Tạo template
        </Link>
      </div>
      <ErrorState error={templates.error} />
      {templates.isPending && <Loading />}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {templates.data?.map((t) => (
          <TemplateCard
            key={t.id}
            name={t.name}
            kind="Orchestrator"
            builtin={t.builtin}
            description={t.description || ""}
            summary={
              <>
                {t.coordinator_handle || t.coordinator_role} ·{" "}
                {t.workers.length} thành viên
              </>
            }
          >
            <Link
              className="btn btn-light"
              href={`/templates/orchestrators/${t.id}`}
            >
              <Pencil size={14} /> Xem & sửa
            </Link>
          </TemplateCard>
        ))}
      </div>
    </div>
  );
}
