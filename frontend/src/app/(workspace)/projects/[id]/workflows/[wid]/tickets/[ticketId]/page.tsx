import { TicketPlaceholder } from "@/components/ui-app/workflow-pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string; wid: string; ticketId: string }>;
}) {
  const p = await params;
  return <TicketPlaceholder pid={p.id} wid={p.wid} tid={p.ticketId} />;
}
