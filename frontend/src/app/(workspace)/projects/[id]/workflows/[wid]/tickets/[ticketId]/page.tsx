import { TicketChannel } from "@/components/ticket-chat/TicketChannel";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string; wid: string; ticketId: string }>;
}) {
  const p = await params;
  return <TicketChannel pid={p.id} wid={p.wid} tid={p.ticketId} />;
}
