import { WorkflowEditor } from "@/components/workflow/WorkflowEditor";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string; wid: string }>;
}) {
  const p = await params;
  return <WorkflowEditor pid={p.id} wid={p.wid} />;
}
