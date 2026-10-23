import { ProjectMembers } from "@/components/ui-app/project-pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <ProjectMembers pid={(await params).id} />;
}
