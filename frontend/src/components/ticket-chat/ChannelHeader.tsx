"use client";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { SquareTerminal } from "lucide-react";
import type { Project, Workflow, Ticket } from "@/lib/types";
import { StatusBadge, ConfirmDialog } from "@/components/ui-app/primitives";
export function ChannelHeader({
  ticket,
  project,
  workflow,
  status,
  memberCount,
  canReport,
  canRelease,
  onDrawer,
  terminalOpen,
  onTerminal,
  onAction,
}: {
  ticket: Ticket;
  project: Project;
  workflow: Workflow;
  status: string;
  memberCount: number;
  canReport: boolean;
  canRelease: boolean;
  onDrawer: () => void;
  terminalOpen: boolean;
  onTerminal: () => void;
  onAction: (action: "cancel" | "retry" | "force-release") => Promise<void>;
}) {
  const [cancel, setCancel] = useState(false);
  const [releasing, setReleasing] = useState(false);
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
          <button
            className="btn btn-light"
            aria-label="Bật/tắt terminal"
            aria-pressed={terminalOpen}
            aria-controls="ticket-terminal-panel"
            title="Bật/tắt terminal"
            onClick={onTerminal}
          >
            <SquareTerminal size={16} aria-hidden="true" />
          </button>
          <details className="relative">
            <summary
              aria-label="Thao tác ticket"
              className="cursor-pointer list-none px-2"
            >
              ⋯
            </summary>
            <div className="absolute right-0 z-20 w-64 rounded-lg border border-stone-200 bg-white p-2 shadow-lg">
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
              {canRelease && !["CANCELLED", "COMPLETED"].includes(status) && (
                <button
                  className="side-item w-full text-xs"
                  disabled={
                    releasing ||
                    (status === "RUNNING" &&
                      !!ticket.result.force_release_running)
                  }
                  title="Dừng agent, commit toàn bộ code và push nhánh hiện tại, sau đó đóng ticket"
                  onClick={async () => {
                    setReleasing(true);
                    try {
                      await onAction("force-release");
                      toast.success("Đang commit, push và đóng ticket");
                    } catch (error) {
                      toast.error(
                        error instanceof Error
                          ? error.message
                          : "Không thể commit",
                      );
                    } finally {
                      setReleasing(false);
                    }
                  }}
                >
                  {releasing ||
                  (status === "RUNNING" && ticket.result.force_release_running)
                    ? "Đang commit & đóng ticket…"
                    : "Commit toàn bộ & đóng ticket"}
                </button>
              )}
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
