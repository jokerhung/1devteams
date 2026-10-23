"use client";
import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { Workflow, Ticket } from "@/lib/types";
import { keys } from "@/lib/query-keys";
import { CreateTicketDialog } from "./ticket-dialog";
import {
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  StatusBadge,
  statuses,
} from "./primitives";
import { TicketTable } from "./project-pages";
export { CreateWorkflowWizard as NewWorkflow } from "@/components/workflow/CreateWorkflowWizard";
export function WorkflowOverview({ pid, wid }: { pid: string; wid: string }) {
  const [create, setCreate] = useState(false);
  const [filter, setFilter] = useState("");
  const workflow = useQuery({
    queryKey: keys.workflow(wid),
    queryFn: () => apiFetch<Workflow>(`/workflows/${wid}`),
  });
  const tickets = useQuery({
    queryKey: [...keys.tickets(wid), filter],
    queryFn: () =>
      apiFetch<Ticket[]>(
        `/workflows/${wid}/tickets${filter ? `?status=${filter}` : ""}`,
      ),
  });
  if (workflow.isLoading) return <Loading />;
  if (!workflow.data) return <ErrorState error={workflow.error} />;
  const w = workflow.data;
  return (
    <>
      <PageHeader
        title={`${w.name} · ${w.ticket_prefix}`}
        description={
          w.published_version
            ? `Đã xuất bản v${w.published_version}`
            : "Workflow nháp — xuất bản trước khi tạo ticket"
        }
      >
        <Link
          className="btn btn-light"
          href={`/projects/${pid}/workflows/${wid}/edit`}
        >
          Sửa luồng
        </Link>
        {w.status === "DRAFT" && (
          <Link
            className="btn btn-light"
            href={`/projects/${pid}/workflows/${wid}/edit`}
          >
            Kiểm tra & xuất bản
          </Link>
        )}
        <button
          className="btn btn-dark"
          disabled={w.status !== "PUBLISHED"}
          title={
            w.status !== "PUBLISHED" ? "Xuất bản workflow trước" : "Tạo ticket"
          }
          onClick={() => setCreate(true)}
        >
          + Tạo ticket
        </button>
      </PageHeader>
      <label className="field mb-4 max-w-xs">
        Lọc trạng thái
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">Tất cả</option>
          {Object.entries(statuses).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <ErrorState error={tickets.error} />
      {tickets.isLoading ? (
        <Loading />
      ) : tickets.data?.length ? (
        <TicketTable pid={pid} tickets={tickets.data} />
      ) : (
        <EmptyState>Chưa có ticket trong workflow này.</EmptyState>
      )}
      {create && (
        <CreateTicketDialog
          pid={pid}
          wid={wid}
          onClose={() => setCreate(false)}
        />
      )}
    </>
  );
}
export function TicketPlaceholder({
  pid,
  wid,
  tid,
}: {
  pid: string;
  wid: string;
  tid: string;
}) {
  const ticket = useQuery({
    queryKey: ["ticket", tid],
    queryFn: () => apiFetch<Ticket>(`/tickets/${tid}`),
    refetchInterval: 5000,
  });
  if (ticket.isLoading) return <Loading />;
  if (!ticket.data) return <ErrorState error={ticket.error} />;
  return (
    <>
      <PageHeader
        title={`${ticket.data.code} · ${ticket.data.title}`}
        description={ticket.data.description}
      >
        <StatusBadge status={ticket.data.status} />
        <Link
          className="btn btn-light"
          href={`/projects/${pid}/workflows/${wid}`}
        >
          Về workflow
        </Link>
      </PageHeader>
      <EmptyState>
        Cửa sổ chat đầy đủ sẽ được triển khai ở Phase 6. Ticket đã được lưu và
        có thể chạy từ backend.
      </EmptyState>
    </>
  );
}
