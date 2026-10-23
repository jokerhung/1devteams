"use client";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import type { Project, Workflow, Ticket } from "@/lib/types";
import { StatusBadge, ConfirmDialog } from "@/components/ui-app/primitives";
export function ChannelHeader({
  ticket,
  project,
  workflow,
  status,
  memberCount,
  canReport,
  onDrawer,
  onAction,
}: {
  ticket: Ticket;
  project: Project;
  workflow: Workflow;
  status: string;
  memberCount: number;
  canReport: boolean;
  onDrawer: () => void;
  onAction: (action: "cancel" | "retry") => Promise<void>;
}) {
  const [cancel, setCancel] = useState(false);
  return (
    <header className="shrink-0 border-b border-stone-200 px-5 py-3">
      <nav className="mb-1 text-[11px] text-stone-400">
        <Link href={`/projects/${project.id}`}>{project.name}</Link> /{" "}
        <Link href={`/projects/${project.id}/workflows/${workflow.id}`}>
          ⑂ {workflow.name} (v{ticket.workflow_version})
        </Link>{" "}
        / {ticket.code}
      </nav>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-sm font-bold">
            # {ticket.channel_slug}
          </h1>
          <p className="truncate font-mono text-[11px] text-stone-500">
            {project.workspace_path} (
            {String(ticket.result.branch || project.default_branch)})
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span
            title="Người dùng và agent trong project"
            className="hidden text-xs text-stone-500 sm:inline"
          >
            ♙ {memberCount}
          </span>
          <StatusBadge status={status} />
          <button
            className="btn btn-light"
            aria-label="Xem workflow của ticket"
            onClick={onDrawer}
          >
            ⚙
          </button>
          <details className="relative">
            <summary
              aria-label="Thao tác ticket"
              className="cursor-pointer list-none px-2"
            >
              ⋯
            </summary>
            <div className="absolute right-0 z-20 w-44 rounded-lg border border-stone-200 bg-white p-2 shadow-lg">
              <button
                className="side-item w-full text-xs"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(location.href);
                    toast.success("Đã sao chép link");
                  } catch {
                    toast.error("Không thể sao chép link");
                  }
                }}
              >
                Sao chép link
              </button>
              {canReport && status === "FAILED" && (
                <button
                  className="side-item w-full text-xs"
                  onClick={() =>
                    void onAction("retry").catch((e) => toast.error(e.message))
                  }
                >
                  Thử lại
                </button>
              )}
              {canReport && !["CANCELLED", "COMPLETED"].includes(status) && (
                <button
                  className="side-item w-full text-xs text-red-700"
                  onClick={() => setCancel(true)}
                >
                  Huỷ ticket
                </button>
              )}
            </div>
          </details>
        </div>
      </div>
      {cancel && (
        <ConfirmDialog
          title="Huỷ ticket"
          onClose={() => setCancel(false)}
          onConfirm={async () => {
            await onAction("cancel");
            setCancel(false);
          }}
        >
          Dừng xử lý {ticket.code}?
        </ConfirmDialog>
      )}
    </header>
  );
}
