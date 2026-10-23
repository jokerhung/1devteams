import { ProjectSettings } from "@/components/ui-app/project-pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <ProjectSettings pid={(await params).id} />;
}
