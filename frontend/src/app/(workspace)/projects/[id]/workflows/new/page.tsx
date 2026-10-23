import { NewWorkflow } from "@/components/ui-app/workflow-pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <NewWorkflow pid={(await params).id} />;
}
