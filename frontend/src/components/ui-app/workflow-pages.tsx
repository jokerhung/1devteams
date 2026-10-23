"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiFetch, send } from "@/lib/api";
import type { Workflow, Ticket, Agent } from "@/lib/types";
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
export function NewWorkflow({ pid }: { pid: string }) {
  const router = useRouter();
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const agents = useQuery({
    queryKey: keys.effective(pid),
    queryFn: () => apiFetch<Agent[]>(`/projects/${pid}/effective-agents`),
  });
  return (
    <>
      <PageHeader
        title="Tạo workflow"
        description="Bắt đầu từ mẫu. Canvas chỉnh sửa chi tiết sẽ có ở Phase 5."
      />
      <p className="mb-6 text-xs text-stone-400">
        1. Project › <b className="text-stone-900">2. Workflow</b> › 3. Ticket ›
        4. Chat
      </p>
      {agents.data?.length === 0 && (
        <p className="error mb-4">
          Chưa có agent nào —{" "}
          <Link className="underline" href={`/projects/${pid}/members`}>
            hãy thêm AI Team trước khi tạo workflow.
          </Link>
        </p>
      )}
      <form
        className="max-w-xl space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          const form = new FormData(e.currentTarget);
          setBusy(true);
          try {
            const flow = await send<Workflow>(`/projects/${pid}/workflows`, {
              name: form.get("name"),
              ticket_prefix: String(form.get("ticket_prefix")).toUpperCase(),
              template: form.get("template"),
            });
            await client.invalidateQueries({ queryKey: ["projects"] });
            toast.success("Đã tạo workflow nháp. Xuất bản để nhận ticket.");
            router.push(`/projects/${pid}/workflows/${flow.id}`);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label className="field">
          Tên workflow
          <input name="name" required defaultValue="Fix Bug" />
        </label>
        <label className="field">
          Prefix ticket
          <input
            name="ticket_prefix"
            required
            defaultValue="BUG"
            pattern="[A-Za-z]{2,10}"
            maxLength={10}
          />
        </label>
        <label className="field">
          Mẫu workflow
          <select name="template">
            <option value="bugfix_default">Fix Bug</option>
            <option value="bugfix_with_security_review">
              Fix Bug + Security Review
            </option>
            <option value="blank">Trống</option>
          </select>
        </label>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <Link className="btn btn-light" href={`/projects/${pid}`}>
            Huỷ
          </Link>
          <button
            className="btn btn-dark"
            disabled={busy || !agents.data?.length}
          >
            Tạo workflow nháp
          </button>
        </div>
      </form>
    </>
  );
}
export function WorkflowOverview({ pid, wid }: { pid: string; wid: string }) {
  const client = useQueryClient();
  const [create, setCreate] = useState(false);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
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
          <button
            className="btn btn-light"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await send(`/workflows/${wid}/publish`);
                await client.invalidateQueries({
                  queryKey: keys.workflow(wid),
                });
                await client.invalidateQueries({ queryKey: ["projects"] });
                toast.success("Đã xuất bản workflow");
              } catch (e) {
                toast.error((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Xuất bản workflow
          </button>
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
export function WorkflowEditorPlaceholder({
  pid,
  wid,
}: {
  pid: string;
  wid: string;
}) {
  return (
    <>
      <PageHeader
        title="Canvas workflow"
        description="Trình chỉnh sửa kéo thả được triển khai ở Phase 5."
      >
        <Link
          className="btn btn-light"
          href={`/projects/${pid}/workflows/${wid}`}
        >
          Về workflow
        </Link>
      </PageHeader>
      <EmptyState>
        Workflow đã được lưu. Bạn có thể xuất bản mẫu từ trang tổng quan
        workflow.
      </EmptyState>
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
