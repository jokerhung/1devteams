import { OrchestratorForm } from "@/components/workflow/OrchestratorForm";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <OrchestratorForm pid={(await params).id} />;
}
