import { ProjectOverview } from "@/components/ui-app/project-pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <ProjectOverview pid={(await params).id} workflowsOnly />;
}
