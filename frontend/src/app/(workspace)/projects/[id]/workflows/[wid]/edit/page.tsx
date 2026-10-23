import { WorkflowEditorPlaceholder } from "@/components/ui-app/workflow-pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string; wid: string }>;
}) {
  const p = await params;
  return <WorkflowEditorPlaceholder pid={p.id} wid={p.wid} />;
}
