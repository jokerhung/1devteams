"use client";
import Link from "next/link";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { Workflow, Agent } from "@/lib/types";
import { send } from "@/lib/api";
import {
  Modal,
  ConfirmDialog,
  StatusBadge,
} from "@/components/ui-app/primitives";
import { mainPath } from "./PipelineView";
import { DeleteEntityButton } from "@/components/ui-app/delete-entity-button";
export function WorkflowCard({
  workflow: w,
  agents,
  onTicket,
}: {
  workflow: Workflow;
  agents: Agent[];
  onTicket: () => void;
}) {
  const client = useQueryClient();
  const [action, setAction] = useState<"archive" | "unarchive" | null>(null),
    [edit, setEdit] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const base = `/projects/${w.project_id}/workflows/${w.id}`;
  const invalidate = () =>
    Promise.all([
      client.invalidateQueries({ queryKey: ["projects"] }),
      client.invalidateQueries({ queryKey: ["workflows", w.id] }),
    ]);
  return (
    <article className="card" aria-label={`Workflow ${w.name}`}>
      <div className="flex items-center gap-2">
        <span>{w.icon}</span>
        <Link href={base} className="text-sm font-semibold hover:underline">
          {w.name}
        </Link>
        <span className="badge font-mono">{w.ticket_prefix}</span>
        {w.graph.orchestrator && <span className="badge">Orchestrator</span>}
        <span className="badge ml-auto">
          {w.status === "PUBLISHED"
            ? `Đã xuất bản v${w.published_version}`
            : w.status === "DRAFT"
              ? "Nháp"
              : "Lưu trữ"}
        </span>
        <DeleteEntityButton kind="workflow" id={w.id} name={w.name} />
        <details className="relative">
          <summary
            aria-label={`Thao tác ${w.name}`}
            className="cursor-pointer list-none rounded px-2 py-1"
          >
            ⋯
          </summary>
          <div className="absolute right-0 z-20 w-44 space-y-1 rounded-lg border border-stone-200 bg-white p-2 shadow-lg">
            <button
              className="side-item w-full text-xs"
              onClick={() => setEdit(true)}
            >
              Sửa thông tin
            </button>
            <Link
              className="side-item text-xs"
              href={`/projects/${w.project_id}/workflows/new?duplicate=${w.id}`}
            >
              Nhân bản
            </Link>
            <button
              className="side-item w-full text-xs"
              onClick={() =>
                setAction(w.status === "ARCHIVED" ? "unarchive" : "archive")
              }
            >
              {w.status === "ARCHIVED" ? "Khôi phục" : "Lưu trữ"}
            </button>
          </div>
        </details>
      </div>
      <p className="mt-3 text-xs text-stone-500">{w.description}</p>
      <p className="my-3 truncate font-mono text-[11px] text-stone-500">
        {mainPath(w.graph)
          .filter((n) =>
            ["agent", "human_confirm", "git_release"].includes(n.type),
          )
          .map((n) =>
            n.type === "human_confirm"
              ? "✋"
              : agents.find((a) => a.id === n.data?.agent_id)?.handle ||
                "Chưa chọn agent",
          )
          .join(" → ")}
      </p>
      <div className="mb-3 flex flex-wrap gap-1">
        {Object.entries(w.ticket_counts || {}).map(([status, count]) => (
          <span key={status} className="flex items-center gap-1 text-[10px]">
            <StatusBadge status={status} />
            {count}
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <button
          className="btn btn-dark"
          disabled={w.status !== "PUBLISHED"}
          title={
            w.status !== "PUBLISHED" ? "Xuất bản workflow trước" : "Tạo ticket"
          }
          onClick={onTicket}
        >
          Tạo ticket
        </button>
        <Link className="btn btn-light" href={`${base}/edit`}>
          {w.graph.orchestrator
            ? "Cấu hình"
            : w.status === "ARCHIVED"
              ? "Xem luồng"
              : "Sửa luồng"}
        </Link>
        <Link className="btn btn-light" href={base}>
          Chi tiết
        </Link>
      </div>
      {action && (
        <ConfirmDialog
          title={`${action === "archive" ? "Lưu trữ" : "Khôi phục"} workflow`}
          onClose={() => setAction(null)}
          onConfirm={async () => {
            await send(`/workflows/${w.id}/${action}`, undefined, "POST");
            await invalidate();
            setAction(null);
            toast.success("Đã cập nhật workflow");
          }}
        >
          <p>
            {w.name} ({w.ticket_prefix})
          </p>
        </ConfirmDialog>
      )}
      {edit && (
        <Modal title="Sửa thông tin workflow" onClose={() => setEdit(false)}>
          <form
            className="space-y-4"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try {
                await send(
                  `/workflows/${w.id}`,
                  Object.fromEntries(new FormData(e.currentTarget)),
                  "PATCH",
                );
                await invalidate();
                setEdit(false);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label className="field">
              Tên workflow
              <input
                name="name"
                defaultValue={w.name}
                required
                maxLength={200}
              />
            </label>
            <label className="field">
              Prefix ticket
              <input
                name="ticket_prefix"
                defaultValue={w.ticket_prefix}
                pattern="[A-Z]{2,10}"
                required
              />
            </label>
            <label className="field">
              Mô tả
              <textarea name="description" defaultValue={w.description} />
            </label>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <button className="btn btn-dark" disabled={busy}>
              Lưu thông tin
            </button>
          </form>
        </Modal>
      )}
    </article>
  );
}
