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
  statuses,
} from "./primitives";
import { TicketTable } from "./project-pages";
import { DeleteEntityButton } from "./delete-entity-button";
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
        <DeleteEntityButton
          kind="workflow"
          id={wid}
          name={w.name}
          redirectTo={`/projects/${pid}`}
        />
        <Link
          className="btn btn-light"
          href={`/projects/${pid}/workflows/${wid}/edit`}
        >
          {w.graph.orchestrator ? "Cấu hình Orchestrator" : "Sửa luồng"}
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
      {w.graph.orchestrator && (
        <section className="card mb-5 text-sm">
          <h2 className="font-semibold">Orchestrator</h2>
          <p className="mt-2 whitespace-pre-wrap">
            {w.graph.orchestrator.instructions}
          </p>
          <p className="mt-2 text-xs text-stone-500">
            Giới hạn {w.graph.orchestrator.max_rounds} lượt điều phối trước khi
            hỏi người dùng.
          </p>
        </section>
      )}
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
