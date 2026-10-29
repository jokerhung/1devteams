"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { OrchestratorTemplate } from "@/lib/types";
import {
  ErrorState,
  Loading,
  PageHeader,
} from "@/components/ui-app/primitives";
import { OrchestratorTemplateForm } from "@/components/workflow/OrchestratorTemplateForm";

export default function OrchestratorTemplatePage() {
  const { key } = useParams<{ key: string }>();
  const templates = useQuery({
    queryKey: ["orchestrator-templates"],
    queryFn: () => apiFetch<OrchestratorTemplate[]>("/orchestrator-templates"),
    enabled: key !== "new",
  });
  if (key === "new")
    return (
      <>
        <PageHeader title="Tạo template Orchestrator" />
        <OrchestratorTemplateForm />
      </>
    );
  if (templates.isPending) return <Loading />;
  if (templates.error) return <ErrorState error={templates.error} />;
  const template = templates.data?.find((t) => t.id === key);
  if (!template)
    return <p role="alert">Không tìm thấy template Orchestrator.</p>;
  return (
    <>
      <PageHeader title={`Template · ${template.name}`} />
      <OrchestratorTemplateForm key={key} template={template} />
    </>
  );
}
